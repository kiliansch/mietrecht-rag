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
import tiktoken
from langchain_core.documents import Document

from src import config, db
from src.ingest.chunking import chunk_case_law_hierarchical
from src.ingest.contextual import format_prefix, generate_prefixes

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


# Parent row as written to `case_law_parents`: (parent_id, parent_text, metadata).
ParentRow = tuple[str, str, dict[str, Any]]


def _decision_to_chunks(
    row: dict[str, Any], context_prefix: str = ""
) -> tuple[list[Document], list[ParentRow]]:
    """Parent-document chunking of one decision.

    Returns `(child_documents, parent_rows)`: the small child chunks that get
    embedded into `case_law` (each tagged with its `parent_id`), and the larger
    parent sections that get stored (non-embedded) in `case_law_parents` and joined
    back in at retrieval time.

    `context_prefix` (contextual retrieval): when non-empty, it is prepended to every
    CHILD chunk's embedded/FTS text so ambiguous fragments carry their decision context.
    The PARENT text stored for the model to read is left unmodified.
    """
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
    children: list[Document] = []
    parents: list[ParentRow] = []
    for unit in chunk_case_law_hierarchical(markdown):
        parent_id = f"{row.get('id')}_{unit.parent_idx}"
        parent_meta = {
            "section_heading": unit.section_heading,
            "court_name": base_metadata["court_name"],
            "file_number": base_metadata["file_number"],
            "date": base_metadata["date"],
            "ecli": base_metadata["ecli"],
            "url": base_metadata["url"],
            "doc_id": base_metadata["doc_id"],
        }
        parents.append((parent_id, unit.parent_text, parent_meta))
        for child_idx, text in enumerate(unit.children):
            metadata = dict(base_metadata)
            metadata["section_heading"] = unit.section_heading
            metadata["parent_id"] = parent_id
            metadata["chunk_id"] = f"{row.get('id')}_{unit.parent_idx}_{child_idx}"
            children.append(Document(page_content=f"{context_prefix}{text}", metadata=metadata))
    return children, parents


def ingest_case_law(
    dump_path: str | Path = config.CASE_LAW_DUMP_PATH,
    max_decisions: int = config.MAX_DECISIONS,
    force: bool = False,
    contextual: bool = False,
) -> dict[str, int]:
    """Filter, chunk, embed and write Mietrecht-relevant decisions to `case_law`.

    Returns the filter report (see `filter_mietrecht_decisions`) extended with
    `chunks_written` (0 if already populated and `force` is False).

    `contextual` (contextual retrieval): when True, one LLM call per decision generates a
    context blurb that is prepended to each child chunk before embedding + FTS (see
    `src.ingest.contextual`); generation runs per batch, concurrently.
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
    # Parents are keyed by a deterministic parent_id (upsert), but --force means a
    # fresh run: truncate so parents from decisions no longer kept cannot linger.
    if force:
        db.clear_case_law_parents()

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
        batch_decisions = kept[start : start + batch_size]
        # Contextual retrieval: generate one prefix per decision (concurrently) for this
        # batch, so the LLM spend lands incrementally alongside the embedding spend.
        prefixes = generate_prefixes(batch_decisions) if contextual else [""] * len(batch_decisions)
        batch_chunks: list[Document] = []
        batch_parents: list[ParentRow] = []
        for decision, prefix in zip(batch_decisions, prefixes):
            children, parents = _decision_to_chunks(decision, context_prefix=prefix)
            batch_chunks.extend(children)
            batch_parents.extend(parents)
        if not batch_chunks:
            continue

        # Write parents first so a child is never retrievable before its parent exists.
        db.upsert_case_law_parents(batch_parents)
        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_DNS, f"case_law:{c.metadata['chunk_id']}"))
            for c in batch_chunks
        ]
        vectorstore.add_documents(batch_chunks, ids=ids)
        if chunks_written == 0:
            db.record_embedding_provenance(config.CASE_LAW_COLLECTION)
        chunks_written += len(batch_chunks)
        logger.info(
            "Batch %d/%d: embedded+wrote %d child chunks / %d parents (running total %d).",
            batch_num,
            num_batches,
            len(batch_chunks),
            len(batch_parents),
            chunks_written,
        )

    report["chunks_written"] = chunks_written
    if chunks_written:
        logger.info("Ingested %d chunks into '%s'.", chunks_written, config.CASE_LAW_COLLECTION)
    return report


# Rough gist size assumed for the contextual dry-run (a one-sentence German blurb) and
# the fixed prompt overhead per generation call. Estimates only — the paid run measures
# the real spend batch by batch.
_ASSUMED_GIST_TOKENS = 45
_CONTEXTUAL_PROMPT_OVERHEAD_TOKENS = 130


def estimate_case_law_ingestion(
    dump_path: str | Path = config.CASE_LAW_DUMP_PATH,
    max_decisions: int = config.MAX_DECISIONS,
    contextual: bool = False,
) -> dict[str, Any]:
    """Cost gate: size a re-ingestion WITHOUT embedding, generating or writing anything.

    Runs the same two-tier filter + parent-document chunking as `ingest_case_law`, then
    counts kept decisions, child chunks, parent sections and total CHILD tokens (parents
    are never embedded) and projects the embedding spend at `config.EMBEDDING_PRICE_PER_1M`.

    With `contextual=True` it also adds (a) the per-child context-prefix tokens to the
    embedding total and (b) the per-decision context-GENERATION spend at
    `config.CONTEXTUAL_MODEL_PRICE_PER_1M`, so the projected cost reflects the full
    contextual re-ingest (re-embedding + generation).

    Returns the filter report extended with `child_chunks`, `parent_sections`,
    `child_tokens`, `projected_usd` (and, when contextual, `embedding_usd`,
    `generation_usd`). Pure CPU: no API calls, no DB writes.
    """
    kept, report = filter_mietrecht_decisions(iter_parquet_rows(dump_path), max_decisions=max_decisions)
    encoding = tiktoken.get_encoding(config.TOKENIZER)
    child_chunks = 0
    parent_sections = 0
    child_tokens = 0
    gen_input_tokens = 0
    gen_output_tokens = 0
    price_in, price_out = config.CONTEXTUAL_MODEL_PRICE_PER_1M
    for decision in kept:
        # A representative prefix (deterministic head + an assumed gist) added to each child.
        prefix = format_prefix(decision, "") if contextual else ""
        prefix_tokens = (len(encoding.encode(prefix)) + _ASSUMED_GIST_TOKENS) if contextual else 0
        children, parents = _decision_to_chunks(decision)
        child_chunks += len(children)
        parent_sections += len(parents)
        child_tokens += sum(len(encoding.encode(c.page_content)) for c in children)
        child_tokens += prefix_tokens * len(children)
        if contextual:
            src = (decision.get("markdown_content") or "")[: config.CONTEXTUAL_SOURCE_MAX_CHARS]
            gen_input_tokens += len(encoding.encode(src)) + _CONTEXTUAL_PROMPT_OVERHEAD_TOKENS
            gen_output_tokens += _ASSUMED_GIST_TOKENS

    embedding_usd = child_tokens / 1_000_000 * config.EMBEDDING_PRICE_PER_1M
    generation_usd = gen_input_tokens / 1_000_000 * price_in + gen_output_tokens / 1_000_000 * price_out
    projected_usd = embedding_usd + generation_usd
    estimate: dict[str, Any] = dict(report)
    estimate["child_chunks"] = child_chunks
    estimate["parent_sections"] = parent_sections
    estimate["child_tokens"] = child_tokens
    estimate["embedding_usd"] = round(embedding_usd, 2)
    estimate["generation_usd"] = round(generation_usd, 2)
    estimate["projected_usd"] = round(projected_usd, 2)
    logger.info(
        "Dry run%s: %d decisions kept -> %d child chunks (%d parents), %d child tokens. "
        "Projected: embedding $%.2f + generation $%.2f = $%.2f.",
        " (contextual)" if contextual else "",
        report["kept"],
        child_chunks,
        parent_sections,
        child_tokens,
        embedding_usd,
        generation_usd,
        projected_usd,
    )
    return estimate
