"""Contextual retrieval for case law (Anthropic-style, per-decision granularity).

One LLM call per court decision produces a short German context blurb — court, file
number, date and a one-sentence gist of the legal issue/holding — which is prepended to
each of that decision's CHILD chunks before embedding + FTS. This situates fragments that
would otherwise be ambiguous ("the claim is dismissed") so the reranker can tell which
decision a chunk belongs to. The PARENT text (what the model reads at answer time) is
never modified.

Generation runs concurrently (`config.CONTEXTUAL_MAX_WORKERS`) over the ~15.6k kept
decisions; a failed or empty generation degrades to a deterministic metadata-only prefix
so ingestion never blocks on the LLM.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.runnables import Runnable

from src import config

logger = logging.getLogger(__name__)

_PROMPT = (
    "Du erstellst Kontext-Sätze für die Suche in deutscher Rechtsprechung (Mietrecht). "
    "Fasse die folgende Gerichtsentscheidung in EINEM kurzen deutschen Satz zusammen: "
    "worum es rechtlich geht und, falls erkennbar, die Kernaussage. Nenne keine "
    "Formalien wie Gericht oder Aktenzeichen (die werden separat ergänzt). Antworte nur "
    "mit dem Satz.\n\n"
    "Gericht: {court}\nAktenzeichen: {file_number}\nDatum: {date}\n\n"
    "Entscheidungstext (Auszug):\n{text}"
)


def _get_llm() -> Runnable:
    return init_chat_model(
        config.CONTEXTUAL_MODEL,
        model_provider="openai",
        base_url=config.LLM_BASE_URL,
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        temperature=0.0,
    )


def _metadata_prefix(row: dict[str, Any]) -> str:
    """Deterministic fallback prefix (no LLM) from decision metadata."""
    court = (row.get("court") or {}).get("name") or "Gericht"
    parts = [str(court)]
    if row.get("file_number"):
        parts.append(str(row["file_number"]))
    if row.get("date"):
        parts.append(str(row["date"]))
    return " – ".join(parts)


def format_prefix(row: dict[str, Any], gist: str) -> str:
    """Build the `[Kontext: ...]` line prepended to each child chunk.

    Always carries the court/Az/date (deterministic); appends the LLM gist when present.
    """
    head = _metadata_prefix(row)
    body = f"{head}: {gist}" if gist else head
    return f"[Kontext: {body}]\n\n"


def _generate_gist(row: dict[str, Any], llm: Runnable) -> str:
    """Return the one-sentence gist for `row`, or "" on any failure/empty output."""
    text = (row.get("markdown_content") or "")[: config.CONTEXTUAL_SOURCE_MAX_CHARS]
    if not text.strip():
        return ""
    prompt = _PROMPT.format(
        court=(row.get("court") or {}).get("name") or "",
        file_number=row.get("file_number") or "",
        date=row.get("date") or "",
        text=text,
    )
    try:
        return " ".join(str(llm.invoke(prompt).content).split())
    except Exception:
        logger.warning("Contextual gist generation failed for doc %s.", row.get("id"), exc_info=True)
        return ""


def generate_prefixes(rows: list[dict[str, Any]]) -> list[str]:
    """Concurrently build the context prefix for each decision in `rows` (order preserved).

    One shared LLM client, `config.CONTEXTUAL_MAX_WORKERS` threads. A row whose gist
    generation fails still gets a deterministic metadata-only prefix.
    """
    if not rows:
        return []
    llm = _get_llm()
    with ThreadPoolExecutor(max_workers=config.CONTEXTUAL_MAX_WORKERS) as pool:
        gists = list(pool.map(lambda r: _generate_gist(r, llm), rows))
    return [format_prefix(row, gist) for row, gist in zip(rows, gists)]
