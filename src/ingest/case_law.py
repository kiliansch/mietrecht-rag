"""Filter and ingest German court decisions (Open Legal Data) into `case_law`.

Reads a LOCAL parquet dump only — no network calls during filtering/chunking.
Writes dense (embedding) + lexical (generated tsvector column, see `src.db`) +
provenance (`embedding_model`/`embedding_dim` per chunk and in `collection_meta`).
"""

from __future__ import annotations

import heapq
import logging
import math
import re
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from langchain_core.documents import Document

from src import config, db
from src.ingest.chunking import chunk_case_law_text

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(
    f"(?:{config.MIETRECHT_BGB_SECTION_REGEX})|(?:{config.MIETRECHT_RELATED_STATUTES_REGEX})"
)

# How often filter_mietrecht_decisions logs scan progress (the dump has ~424K rows).
_PROGRESS_LOG_EVERY = 50_000


def iter_parquet_rows(dump_path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield decision rows (as dicts) from every `*.parquet` shard under `dump_path`."""
    shards = sorted(Path(dump_path).glob("*.parquet"))
    if not shards:
        raise FileNotFoundError(f"No parquet shards found under {dump_path}")
    logger.info("Found %d parquet shard(s) under %s", len(shards), dump_path)
    for i, shard in enumerate(shards, start=1):
        table = pq.read_table(shard)
        logger.info("Reading shard %d/%d: %s (%d rows)", i, len(shards), shard.name, table.num_rows)
        for batch in table.to_batches():
            yield from batch.to_pylist()


def filter_mietrecht_decisions(
    rows: Iterable[dict[str, Any]],
    max_decisions: int = config.MAX_DECISIONS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep decisions relevant to Mietrecht, in two precision tiers.

    Tier 1 (always kept, uncapped): the `markdown_content` cites a section of
    BGB §535-577, BetrKV, WoGG or HeizkostenV (`_SECTION_RE`) — an explicit
    statute citation is precise enough to guarantee relevance, so no cap can
    ever drop one of these.

    Tier 2 (capped at `max_decisions`): no statute citation, but at least
    `config.MIETRECHT_MIN_KEYWORD_HITS` distinct terms from
    `config.MIETRECHT_KEYWORDS` occur (a single incidental hit, e.g.
    "Kündigung" in an unrelated dispute, is not enough). Ranked by number of
    keyword hits when over the cap.

    `rows` is consumed lazily; tier 2 only ever holds `max_decisions`
    candidates in memory, so the full corpus never needs to be materialized.

    Returns `(kept_rows, report)`. `report` has keys `total`, `regex_matches`,
    `keyword_matches`, `relevant`, `kept`. `relevant` is the combined tier 1 +
    tier 2 candidate pool size (before the tier 2 cap is applied).
    """
    regex_kept: list[dict[str, Any]] = []
    keyword_heap: list[tuple[int, int, dict[str, Any]]] = []
    total = 0
    regex_matches = 0
    keyword_matches = 0
    keyword_only_relevant = 0

    for counter, row in enumerate(rows):
        total += 1
        text = row.get("markdown_content") or ""
        has_regex = bool(_SECTION_RE.search(text))
        hits = [kw for kw in config.MIETRECHT_KEYWORDS if kw in text]

        if hits:
            keyword_matches += 1

        if has_regex:
            regex_matches += 1
            regex_kept.append(row)
        elif len(hits) >= config.MIETRECHT_MIN_KEYWORD_HITS:
            keyword_only_relevant += 1
            score = len(hits)
            if len(keyword_heap) < max_decisions:
                heapq.heappush(keyword_heap, (score, counter, row))
            elif max_decisions > 0 and score > keyword_heap[0][0]:
                heapq.heapreplace(keyword_heap, (score, counter, row))

        if total % _PROGRESS_LOG_EVERY == 0:
            logger.info(
                "Scored %d decisions so far (%d statute-citing, %d keyword-only candidates, heap %d/%d)",
                total,
                regex_matches,
                keyword_only_relevant,
                len(keyword_heap),
                max_decisions,
            )

    ranked_keyword = sorted(keyword_heap, key=lambda item: (item[0], -item[1]), reverse=True)
    kept = regex_kept + [row for _, _, row in ranked_keyword]

    report = {
        "total": total,
        "regex_matches": regex_matches,
        "keyword_matches": keyword_matches,
        "relevant": regex_matches + keyword_only_relevant,
        "kept": len(kept),
    }
    return kept, report


def _decision_url(slug: str) -> str:
    return f"https://de.openlegaldata.io/case/{slug}/"


def _decision_to_chunks(row: dict[str, Any]) -> list[Document]:
    """Heading-aware + token-bound chunking of one decision into Documents."""
    court = row.get("court") or {}
    base_metadata = {
        "source": "openlegaldata-court",
        "doc_id": row.get("id"),
        "slug": row.get("slug"),
        "court_name": court.get("name"),
        "court_slug": court.get("slug"),
        "jurisdiction": court.get("jurisdiction"),
        "level_of_appeal": court.get("level_of_appeal"),
        "state": court.get("state"),
        "file_number": row.get("file_number"),
        "ecli": row.get("ecli"),
        "date": row.get("date"),
        "type": row.get("type"),
        "url": _decision_url(str(row.get("slug", ""))),
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": config.EMBEDDING_DIM,
    }

    markdown = row.get("markdown_content") or ""
    chunks: list[Document] = []
    for idx, (heading, text) in enumerate(chunk_case_law_text(markdown)):
        metadata = dict(base_metadata)
        metadata["section_heading"] = heading
        metadata["chunk_id"] = f"{row.get('id')}_{idx}"
        chunks.append(Document(page_content=text, metadata=metadata))
    return chunks


def ingest_case_law(
    dump_path: str | Path = config.CASE_LAW_DUMP_PATH,
    max_decisions: int = config.MAX_DECISIONS,
    force: bool = False,
) -> dict[str, int]:
    """Filter, chunk, embed and write Mietrecht-relevant decisions to `case_law`.

    Returns the filter report (see `filter_mietrecht_decisions`) extended with
    `chunks_written` (0 if already populated and `force` is False).
    """
    existing = db.collection_row_count(config.CASE_LAW_COLLECTION)
    if existing > 0 and not force:
        logger.info(
            "'%s' already has %d chunks; skipping (use --force to re-ingest).",
            config.CASE_LAW_COLLECTION,
            existing,
        )
        return {"chunks_written": 0}
    if existing > 0:
        logger.info("--force: clearing %d existing chunks from '%s'.", existing, config.CASE_LAW_COLLECTION)
        db.clear_collection(config.CASE_LAW_COLLECTION)

    kept, report = filter_mietrecht_decisions(iter_parquet_rows(dump_path), max_decisions=max_decisions)
    logger.info("Read %d decisions from %s", report["total"], dump_path)
    logger.info(
        "Mietrecht filter: %d total, %d regex matches, %d keyword matches, "
        "%d relevant, %d kept (cap=%d).",
        report["total"],
        report["regex_matches"],
        report["keyword_matches"],
        report["relevant"],
        report["kept"],
        max_decisions,
    )

    vectorstore = db.get_vectorstore(config.CASE_LAW_COLLECTION)
    batch_size = config.CASE_LAW_INGEST_BATCH_DECISIONS
    num_batches = math.ceil(len(kept) / batch_size) if kept else 0
    chunks_written = 0

    for batch_num, start in enumerate(range(0, len(kept), batch_size), start=1):
        batch_chunks: list[Document] = []
        for decision in kept[start : start + batch_size]:
            batch_chunks.extend(_decision_to_chunks(decision))
        if not batch_chunks:
            continue

        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_DNS, f"case_law:{c.metadata['chunk_id']}"))
            for c in batch_chunks
        ]
        vectorstore.add_documents(batch_chunks, ids=ids)
        if chunks_written == 0:
            db.record_embedding_provenance(config.CASE_LAW_COLLECTION)
        chunks_written += len(batch_chunks)
        logger.info(
            "Batch %d/%d: embedded+wrote %d chunks (running total %d).",
            batch_num,
            num_batches,
            len(batch_chunks),
            chunks_written,
        )

    report["chunks_written"] = chunks_written
    if chunks_written:
        logger.info("Ingested %d chunks into '%s'.", chunks_written, config.CASE_LAW_COLLECTION)
    return report
