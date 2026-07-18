#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_legal_data.py

Retrieves German rental law norms from the Open Legal Data API
(https://de.openlegaldata.io/api) and prepares them for a LangChain RAG
pipeline focused on BGB §§535–577 (Mietrecht).

Target law books:
  bgb     – Bürgerliches Gesetzbuch (primary source, Mietrecht §§535–577)
  betrkv  – Betriebskostenverordnung
  wistg   – Wirtschaftsstrafgesetz 1954 (not present in API; warning logged)
  wogg    – Wohngeldgesetz

Endpoint facts confirmed via live API and SDK documentation:
  - Base URL          : https://de.openlegaldata.io/api
  - Law books list    : GET /law_books/   (underscore, not hyphen)
  - Slug filter       : /law_books/?slug={slug}&limit=1
  - Norms list        : GET /laws/?book__slug={slug}&limit=100&offset=0
  - Norm detail       : GET /laws/{id}/
  - Auth header       : api_key: <KEY>   (NOT Authorization: Token ...)
  - Section format    : "§ 535" — use re.search() not re.match()
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL = "https://de.openlegaldata.io/api"

# Delay (seconds) between individual detail-fetch requests to avoid bursting the
# rate limit before the retry logic is even needed.
INTER_REQUEST_DELAY = 0.25

# Extended retry parameters used exclusively for HTTP 429 responses.
RATE_LIMIT_RETRIES = 8
RATE_LIMIT_BACKOFF = [2, 4, 8, 16, 32, 60, 60, 60]  # seconds

# Note: "wistg" (Wirtschaftsstrafgesetz 1954) was confirmed absent from the
# Open Legal Data API (slug and code searches return 0 results). It is kept
# as a target so the warning is emitted and logged, but it will be skipped.
TARGET_SLUGS = ["bgb", "betrkv", "wistg", "wogg"]

OUTPUT_DIR = Path("data/laws")
LOG_FILE = Path("data/retrieval.log")
LOG_JSON_FILE = Path("data/retrieval_log.json")
SUMMARY_FILE = Path("data/retrieval_summary.txt")

# Matches Absatz markers such as (1), (2), (1a) at the start of the string or
# after one or more newlines.  Used by _split_by_absatz() to slice norm content
# into individual Absatz chunks before RAG document preparation.
_ABSATZ_RE = re.compile(r"(?:^|\n+)\((\d+[a-z]?)\)\s?")


# ── Logging setup ──────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure logging to stdout AND data/retrieval.log at INFO level."""
    Path("data").mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not root.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)

        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


# ── Retrieval log ──────────────────────────────────────────────────────────────

def _append_retrieval_log(
    step: str,
    status: str,
    message: str,
    data: dict,
) -> None:
    """Append one structured entry to data/retrieval_log.json."""
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": step,
        "status": status,
        "message": message,
        "data": data,
    }
    entries: list = []
    if LOG_JSON_FILE.exists():
        try:
            entries = json.loads(LOG_JSON_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(entry)
    LOG_JSON_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Safe file write ────────────────────────────────────────────────────────────

def _safe_write_json(path: Path, data: object) -> None:
    """
    If path already exists, rename it with a UTC timestamp suffix, then write.
    All output uses UTF-8, ensure_ascii=False, indent=2.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.stem}_{ts}{path.suffix}")
        path.rename(backup)
        logging.info("Renamed existing %s → %s", path, backup)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── api_get ────────────────────────────────────────────────────────────────────

def api_get(
    url: str,
    params: dict,
    headers: dict,
    retries: int = 3,
) -> "dict | None":
    """
    HTTP GET with exponential-backoff retry.

    Retries on: requests.HTTPError, requests.ConnectionError, requests.Timeout.
    For HTTP 429 responses uses an extended retry sequence (RATE_LIMIT_RETRIES /
    RATE_LIMIT_BACKOFF). For all other errors keeps the 3-retry / 2-4-8 s
    behaviour controlled by the ``retries`` parameter.
    Returns parsed JSON dict, or None on permanent failure.
    """
    default_backoff = [2, 4, 8]
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            # ── 429 Too Many Requests — extended retry sequence ────────────
            if exc.response is not None and exc.response.status_code == 429:
                for rl_attempt in range(RATE_LIMIT_RETRIES):
                    wait = RATE_LIMIT_BACKOFF[rl_attempt] if rl_attempt < len(RATE_LIMIT_BACKOFF) else 60
                    logging.warning(
                        "HTTP 429 (attempt %d/%d) for %s — retrying in %ds",
                        rl_attempt + 1,
                        RATE_LIMIT_RETRIES,
                        url,
                        wait,
                    )
                    time.sleep(wait)
                    try:
                        resp2 = requests.get(url, params=params, headers=headers, timeout=30)
                        resp2.raise_for_status()
                        return resp2.json()
                    except requests.HTTPError as exc2:
                        if exc2.response is None or exc2.response.status_code != 429:
                            # Non-429 error inside 429-retry loop — fall through
                            logging.error(
                                "Non-429 error during 429-retry for %s: %s",
                                url,
                                exc2,
                            )
                            return None
                    except (requests.ConnectionError, requests.Timeout) as exc2:
                        logging.error(
                            "Connection/timeout error during 429-retry for %s: %s",
                            url,
                            exc2,
                        )
                        return None
                logging.error(
                    "Permanent 429 failure for %s after %d rate-limit retries",
                    url,
                    RATE_LIMIT_RETRIES,
                )
                return None
            # ── Other HTTP errors — standard backoff ───────────────────────
            wait = default_backoff[attempt] if attempt < len(default_backoff) else 8
            if attempt < retries - 1:
                logging.warning(
                    "Request failed (attempt %d/%d) for %s: %s — retrying in %ds",
                    attempt + 1,
                    retries,
                    url,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logging.error(
                    "Permanent failure for %s (status=%s): %s",
                    url,
                    exc.response.status_code if exc.response is not None else "N/A",
                    exc,
                )
        except (requests.ConnectionError, requests.Timeout) as exc:
            wait = default_backoff[attempt] if attempt < len(default_backoff) else 8
            if attempt < retries - 1:
                logging.warning(
                    "Request failed (attempt %d/%d) for %s: %s — retrying in %ds",
                    attempt + 1,
                    retries,
                    url,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logging.error("Permanent failure for %s: %s", url, exc)
    return None


# ── resolve_book_ids ───────────────────────────────────────────────────────────

def resolve_book_ids(api_key: str) -> "dict[str, dict]":
    """
    Resolve each target slug to its book metadata via GET /law_books/?slug={slug}&limit=1.

    Uses the slug filter directly — never paginates all 9 000+ books.
    Exact-matches the returned object where b["slug"] == target_slug.

    Returns:
        { slug: { "id": int, "name": str, "slug": str, "code": str } }

    Logs a warning for any slug not found; does not abort.
    """
    headers = {"api_key": api_key}
    books: dict = {}

    for slug in TARGET_SLUGS:
        logging.info("Resolving book: slug=%s", slug)
        data = api_get(
            f"{BASE_URL}/law_books/",
            params={"slug": slug, "limit": 1},
            headers=headers,
        )
        if data is None:
            logging.warning("No API response for slug=%s", slug)
            _append_retrieval_log(
                "resolve_book_ids",
                "warning",
                f"No response for slug={slug}",
                {"slug": slug},
            )
            continue

        results = data.get("results", [])
        matched = next((b for b in results if b.get("slug") == slug), None)
        if matched is None:
            logging.warning("Book slug=%s not found in results", slug)
            _append_retrieval_log(
                "resolve_book_ids",
                "warning",
                f"Book slug={slug} not found in results",
                {"slug": slug, "returned_slugs": [b.get("slug") for b in results]},
            )
            continue

        books[slug] = {
            "id": matched.get("id"),
            "name": matched.get("title") or matched.get("name", ""),
            "slug": matched.get("slug"),
            "code": matched.get("code", ""),
        }
        logging.info(
            "Resolved: slug=%s code=%s id=%s",
            slug,
            matched.get("code"),
            matched.get("id"),
        )

    _append_retrieval_log(
        "resolve_book_ids",
        "ok",
        f"Resolved {len(books)}/{len(TARGET_SLUGS)} books",
        {"resolved": list(books.keys())},
    )
    return books


# ── fetch_all_norms ────────────────────────────────────────────────────────────

def fetch_all_norms(book: dict, api_key: str) -> "list[dict]":
    """
    Paginate GET /laws/?book__slug={slug}&limit=100 until "next" is null.
    Sleeps 0.5 s between page requests.

    Saves raw list to data/laws/{slug}_norms.json (with safe rename if exists).
    Returns full list of norm dicts.
    """
    headers = {"api_key": api_key}
    slug = book["slug"]
    norms: list = []
    offset = 0
    limit = 100

    logging.info("Fetching norms for book slug=%s", slug)

    while True:
        data = api_get(
            f"{BASE_URL}/laws/",
            params={"book__slug": slug, "limit": limit, "offset": offset},
            headers=headers,
        )
        if data is None:
            logging.warning(
                "Failed to fetch norms page for slug=%s at offset=%d", slug, offset
            )
            break

        results = data.get("results", [])
        norms.extend(results)
        logging.info(
            "  slug=%s offset=%d → %d norms (total so far: %d)",
            slug,
            offset,
            len(results),
            len(norms),
        )

        if not data.get("next"):
            break

        offset += limit
        time.sleep(0.5)

    out_path = OUTPUT_DIR / f"{slug}_norms.json"
    _safe_write_json(out_path, norms)
    logging.info("Saved %d norms for slug=%s → %s", len(norms), slug, out_path)

    _append_retrieval_log(
        "fetch_all_norms",
        "ok",
        f"Fetched {len(norms)} norms for slug={slug}",
        {"slug": slug, "count": len(norms)},
    )
    return norms


# ── enrich_norms ──────────────────────────────────────────────────────────────

def _should_enrich(norm: dict, book_slug: str) -> bool:
    """
    Return True when a norm should be fetched in full.

    Rules:
      bgb    — only §535–§577 inclusive
      betrkv — all norms
      wogg   — all norms
      other  — never
    """
    if book_slug == "bgb":
        match = re.search(r"(\d+)", norm.get("section", ""))
        if not match:
            return False
        return 535 <= int(match.group(1)) <= 577
    if book_slug in ("betrkv", "wogg"):
        return True
    return False


def enrich_norms(norms_by_slug: "dict[str, list]", api_key: str) -> "list[dict]":
    """
    Enrich norms from all books according to _should_enrich() rules:
      - BGB  : §535–§577 only
      - BetrKV: all norms
      - WoGG : all norms

    Fetches the full detail record (GET /laws/{id}/) for each candidate,
    strips HTML from the content field, and sleeps INTER_REQUEST_DELAY seconds
    before every detail request to avoid bursting the rate limit.

    Raises RuntimeError if api_get() returns None for any norm (i.e. all
    retries are exhausted) — norms are never silently dropped.

    Saves to data/laws/bgb_mietrecht_norms_enriched.json (name kept for
    backward compatibility with downstream consumers).
    """
    headers = {"api_key": api_key}
    enriched: list = []

    # Build flat candidate list: (norm dict, book_slug)
    candidates: list[tuple[dict, str]] = []
    for slug, norms in norms_by_slug.items():
        for norm in norms:
            if _should_enrich(norm, slug):
                candidates.append((norm, slug))

    logging.info("Enriching %d norm(s) across all books", len(candidates))

    for norm, book_slug in candidates:
        section_str = norm.get("section", "")
        norm_id = norm.get("id")
        if norm_id is None:
            logging.warning("Norm %s (book=%s) has no id — skipping", section_str, book_slug)
            continue

        time.sleep(INTER_REQUEST_DELAY)

        detail = api_get(
            f"{BASE_URL}/laws/{norm_id}/",
            params={},
            headers=headers,
        )
        if detail is None:
            raise RuntimeError(
                f"Failed to enrich norm id={norm_id} ({section_str}, {book_slug}) "
                "after all retries. Re-run the script or increase "
                "RATE_LIMIT_RETRIES / INTER_REQUEST_DELAY."
            )

        raw_html = detail.get("content") or ""
        plain_text = BeautifulSoup(raw_html, "html.parser").get_text(separator="\n")

        resolved_slug = (
            detail.get("book_slug")
            or norm.get("book_slug", book_slug)
        )

        # The API detail response has no 'revision_date' or 'url' field.
        # Use 'updated_date' as the revision date and build the canonical
        # web URL from book_slug + slug.
        norm_slug = detail.get("slug") or ""
        revision_date = detail.get("updated_date") or detail.get("created_date") or ""
        url = (
            f"https://de.openlegaldata.io/law/{resolved_slug}/{norm_slug}"
            if resolved_slug and norm_slug
            else ""
        )

        enriched.append(
            {
                "id": detail.get("id"),
                "section": detail.get("section", section_str),
                "title": detail.get("title") or "",
                "content": plain_text,
                "revision_date": revision_date,
                "url": url,
                "book_slug": resolved_slug,
            }
        )
        logging.info("Enriched %s (book=%s, id=%s)", section_str, book_slug, norm_id)

    out_path = OUTPUT_DIR / "bgb_mietrecht_norms_enriched.json"
    _safe_write_json(out_path, enriched)
    logging.info("Saved %d enriched norms → %s", len(enriched), out_path)

    _append_retrieval_log(
        "enrich_norms",
        "ok",
        f"Enriched {len(enriched)} norms (BGB §535–§577, all BetrKV, all WoGG)",
        {"enriched": len(enriched)},
    )
    return enriched


# ── _split_by_absatz ──────────────────────────────────────────────────────────

def _split_by_absatz(content: str) -> "list[tuple[str, str]]":
    """
    Split a norm's plain-text content into per-Absatz chunks.

    Returns a list of ``(absatz_label, text)`` tuples:
    - ``absatz_label``: e.g. ``"Abs. 1"``, ``"Abs. 1a"``, ``"Abs. 2"`` — or
      the empty string ``""`` when the norm has no Absatz structure.
    - ``text``: trimmed Absatz text that retains its ``(N) …`` marker prefix.

    Norms without any ``(N)`` markers (e.g. §536b) return
    ``[("" , content.strip())]``.
    """
    matches = list(_ABSATZ_RE.finditer(content))
    if not matches:
        return [("", content.strip())]

    chunks: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        absatz_num = match.group(1)
        label = f"Abs. {absatz_num}"
        # match.group(0) may be prefixed with newlines; skip them so the chunk
        # text starts at the '(' character: "(N) remainder of Absatz…".
        paren_pos = match.start() + match.group(0).index("(")
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = content[paren_pos:text_end].strip()
        chunks.append((label, text))
    return chunks


# ── prepare_rag_documents ──────────────────────────────────────────────────────

def prepare_rag_documents(enriched: "list[dict]") -> "list[dict]":
    """
    Map each enriched norm to a serialisable Document dict compatible with
    LangChain's Document schema.

    Saves to data/laws/rag_documents.json.
    """
    docs: list = []
    for norm in enriched:
        for absatz_label, chunk_text in _split_by_absatz(norm["content"]):
            metadata: dict = {
                "source": "openlegaldata",
                "book_slug": norm["book_slug"],
                "section": norm["section"],
                "title": norm["title"],
                "revision_date": norm["revision_date"],
                "url": norm["url"],
            }
            if absatz_label:
                metadata["absatz"] = absatz_label
            docs.append({"page_content": chunk_text, "metadata": metadata})

    out_path = OUTPUT_DIR / "rag_documents.json"
    _safe_write_json(out_path, docs)
    logging.info("Saved %d RAG documents → %s", len(docs), out_path)

    _append_retrieval_log(
        "prepare_rag_documents",
        "ok",
        f"Prepared {len(docs)} RAG documents",
        {"count": len(docs)},
    )
    return docs


# ── validate_and_report ────────────────────────────────────────────────────────

def validate_and_report(
    books_norms: "dict[str, list]",
    enriched: "list[dict]",
    docs: "list[dict]",
) -> None:
    """
    Print and save a summary table to data/retrieval_summary.txt.
    Flags documents where len(page_content.strip()) < 50.
    """
    short_docs = [
        d for d in docs if len(d.get("page_content", "").strip()) < 50
    ]

    lines = [
        "=" * 70,
        "LEGAL DATA RETRIEVAL SUMMARY",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "=" * 70,
        "",
        "Norms fetched per book:",
    ]
    for slug in TARGET_SLUGS:
        count = len(books_norms.get(slug, []))
        lines.append(f"  {slug:<12} {count:>6} norms")

    lines += [
        "",
        f"BGB Mietrecht norms enriched (§535–§577) : {len(enriched)}",
        f"RAG documents prepared                   : {len(docs)}",
        "",
    ]

    if short_docs:
        lines.append(
            f"WARNING: {len(short_docs)} document(s) with < 50 chars of content "
            "(potentially incomplete):"
        )
        for d in short_docs:
            lines.append(f"  section={d['metadata'].get('section', '?')}")
    else:
        lines.append("All documents appear complete (>=50 chars of content).")

    lines += ["", "=" * 70]
    report = "\n".join(lines)
    print(report)

    if SUMMARY_FILE.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = SUMMARY_FILE.with_name(f"{SUMMARY_FILE.stem}_{ts}{SUMMARY_FILE.suffix}")
        SUMMARY_FILE.rename(backup)
        logging.info("Renamed existing %s → %s", SUMMARY_FILE, backup)
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.write_text(report, encoding="utf-8")
    logging.info("Summary saved → %s", SUMMARY_FILE)

    _append_retrieval_log(
        "validate_and_report",
        "ok" if not short_docs else "warning",
        f"Report saved; {len(short_docs)} short document(s)",
        {
            "total_docs": len(docs),
            "short_docs": len(short_docs),
            "short_sections": [
                d["metadata"].get("section") for d in short_docs
            ],
        },
    )


# ── main ───────────────────────────────────────────────────────────────────────

def _load_env_file(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (if not already set)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> None:
    """Execute the full retrieval and preparation pipeline."""
    setup_logging()
    _load_env_file()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("OLDP_API_KEY", "")
    if not api_key:
        logging.error(
            "OLDP_API_KEY environment variable is not set. "
            "Export it before running this script."
        )
        raise SystemExit(1)

    logging.info("Starting legal data retrieval pipeline")

    # Phase 1: Resolve book metadata (id, slug, code, name)
    books = resolve_book_ids(api_key)
    if not books:
        logging.error("No books resolved — aborting pipeline")
        raise SystemExit(1)

    # Phase 2: Fetch all norms for each resolved book
    books_norms: dict = {}
    for slug, book in books.items():
        books_norms[slug] = fetch_all_norms(book, api_key)

    # Phase 3: Enrich norms — BGB §535–§577, all BetrKV, all WoGG
    enriched = enrich_norms(books_norms, api_key)

    # Phase 4: Prepare RAG documents
    docs = prepare_rag_documents(enriched)

    # Phase 5: Validate and report
    validate_and_report(books_norms, enriched, docs)

    logging.info("Pipeline completed successfully")


if __name__ == "__main__":
    main()
