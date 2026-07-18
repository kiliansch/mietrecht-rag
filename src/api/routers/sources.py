"""Source viewer: return the full statute-§ / court-decision text behind a citation.

Read-only lookups into the (public legal text) `statutes` / `case_law` collections so
the UI can let a user click a citation in an answer and read the primary source it
rests on. Chunks are reassembled in document order and length-capped.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import sql

from src import config, db
from src.api.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["sources"])

_COLLECTIONS = {config.STATUTES_COLLECTION, config.CASE_LAW_COLLECTION}
# Guard against pathologically long decisions blowing up the response.
_SOURCE_MAX_CHARS = 60_000

_NUM_RE = re.compile(r"\d+")
_WS_RUN = re.compile(r"[ \t]+")


def _natural_key(chunk_id: str) -> list[Any]:
    """Sort key that orders `§ 551_Abs. 2_1` / `58904_10` by their numeric parts."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", chunk_id or "")]


def _normalise(text: str) -> str:
    """Tidy the raw (HTML-scraped) chunk text for display: drop the stray leading
    indentation and repeated interior spaces, and collapse runs of blank lines to one.
    The underlying corpus keeps its original text; this only cleans the viewer output.
    """
    lines = [_WS_RUN.sub(" ", raw.strip()) for raw in text.splitlines()]
    out: list[str] = []
    prev_blank = False
    for line in lines:
        blank = line == ""
        if blank and prev_blank:
            continue  # collapse 2+ consecutive blank lines into one
        out.append(line)
        prev_blank = blank
    return "\n".join(out).strip()


def _statute_title(meta: dict[str, Any]) -> str:
    parts = [str(meta[k]) for k in ("section",) if meta.get(k)]
    if meta.get("title"):
        parts.append(str(meta["title"]))
    return " – ".join(parts) or "Gesetzestext"


def _case_law_title(meta: dict[str, Any]) -> str:
    parts = [str(meta[k]) for k in ("court_name", "file_number", "date") if meta.get(k)]
    if meta.get("ecli"):
        parts.append(f"ECLI: {meta['ecli']}")
    return " – ".join(parts) or "Gerichtsentscheidung"


@router.get("/sources")
def get_source(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    collection: Annotated[str, Query()],
    url: Annotated[str, Query()],
) -> dict[str, Any]:
    """Return the full source text (all chunks, in order) for a citation's `url`."""
    if collection not in _COLLECTIONS:
        raise HTTPException(status_code=422, detail="Unbekannte Sammlung.")

    # Citations strip a trailing slash from case-law URLs; the stored value keeps it.
    stmt = sql.SQL(
        "SELECT content, langchain_metadata FROM {table} "
        "WHERE rtrim(langchain_metadata->>'url', '/') = rtrim(%s, '/')"
    ).format(table=sql.Identifier(collection))
    with db.get_connection() as conn:
        rows = conn.execute(stmt, (url,)).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Quelle nicht gefunden.")

    is_statute = collection == config.STATUTES_COLLECTION
    heading_key = "absatz" if is_statute else "section_heading"
    ordered = sorted(rows, key=lambda r: _natural_key(str((r[1] or {}).get("chunk_id", ""))))

    blocks: list[dict[str, str]] = []
    seen_join = ""  # accumulated block text, for de-duplicating repeated/overlapping chunks
    total = 0
    for content, meta in ordered:
        text = _normalise(str(content))
        # Skip empty chunks and ones already shown (exact repeats or overlap contained
        # in what we've emitted) — the corpus has duplicated absätze for some statutes.
        if not text or text in seen_join:
            continue
        if total + len(text) > _SOURCE_MAX_CHARS:
            text = text[: max(0, _SOURCE_MAX_CHARS - total)]
        heading = _normalise(str((meta or {}).get(heading_key) or ""))
        blocks.append({"heading": heading, "content": text})
        seen_join += "\n" + text
        total += len(text)
        if total >= _SOURCE_MAX_CHARS:
            break

    meta0 = ordered[0][1] or {}
    title = _statute_title(meta0) if is_statute else _case_law_title(meta0)
    return {
        "collection": collection,
        "url": str(meta0.get("url") or url),
        "title": title,
        "blocks": blocks,
    }
