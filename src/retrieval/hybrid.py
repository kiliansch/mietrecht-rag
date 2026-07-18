"""Hybrid (dense pgvector + Postgres German FTS) retrieval over a collection.

One `EnsembleRetriever` per collection, fusing:
- Dense: `PGVectorStore` cosine similarity search.
- Lexical: `PostgresFTSRetriever`, ranking `websearch_to_tsquery('german', ...)` matches
  by `ts_rank_cd` against the generated `content_tsv` column (see `src.db`).

Both halves accept the same optional flat-equality `metadata_filter` dict, applied
against `langchain_metadata`. Fusion weights come from `src.config`.

`get_hybrid_retriever` wraps the fused result in two extra layers, both folded in
here (rather than in the tools or the eval runner) so every caller benefits
identically:

1. For the `statutes` collection, an explicit "§NNN" citation in the query narrows
   the candidate pool to that section (falling back to the unfiltered pool if the
   narrowed search returns nothing) — adjacent sections are otherwise topically
   similar enough to dilute precision.
2. A reranking pass over a wider `RERANK_CANDIDATE_K` candidate pool, via
   OpenRouter's rerank endpoint. Long case-law decisions can produce dozens of
   chunks under the same coarse heading; reranking lets the model that actually
   contains the cited holding win out over its near-identical siblings, which a
   fixed top-`RETRIEVAL_K` per sub-retriever cannot reliably surface.

Both collections are consumed by the single `search_law` tool, which fetches from
each and merges the results into one grounded context block.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from psycopg import sql

from src import config, db

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE)


class PostgresFTSRetriever(BaseRetriever):
    """Lexical retriever: `websearch_to_tsquery('german', ...)` ranked by `ts_rank_cd`."""

    collection: str
    k: int = config.RETRIEVAL_K
    metadata_filter: dict[str, Any] | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        where_clauses = [
            sql.SQL("content_tsv @@ websearch_to_tsquery({lang}, {query})").format(
                lang=sql.Literal(db.FTS_LANGUAGE), query=sql.Literal(query)
            )
        ]
        for key, value in (self.metadata_filter or {}).items():
            where_clauses.append(
                sql.SQL("langchain_metadata ->> {key} = {value}").format(
                    key=sql.Literal(key), value=sql.Literal(str(value))
                )
            )

        stmt = sql.SQL(
            "SELECT langchain_id, content, langchain_metadata, "
            "ts_rank_cd(content_tsv, websearch_to_tsquery({lang}, {query})) AS rank "
            "FROM {table} WHERE {where} ORDER BY rank DESC LIMIT {k}"
        ).format(
            lang=sql.Literal(db.FTS_LANGUAGE),
            query=sql.Literal(query),
            table=sql.Identifier(self.collection),
            where=sql.SQL(" AND ").join(where_clauses),
            k=sql.Literal(self.k),
        )

        with db.get_connection() as conn:
            rows = conn.execute(stmt).fetchall()

        documents = []
        for langchain_id, content, metadata, _rank in rows:
            doc_metadata = dict(metadata or {})
            doc_metadata["id"] = str(langchain_id)
            documents.append(Document(page_content=content, metadata=doc_metadata))
        return documents


def _build_ensemble(
    collection: str, metadata_filter: dict[str, Any] | None, k: int
) -> EnsembleRetriever:
    """Fuse dense + lexical results for `collection` at candidate pool size `k`."""
    dense = db.get_vectorstore(collection).as_retriever(
        search_kwargs={"k": k, "filter": metadata_filter}
    )
    lexical = PostgresFTSRetriever(collection=collection, k=k, metadata_filter=metadata_filter)
    return EnsembleRetriever(
        retrievers=[dense, lexical],
        weights=list(config.ENSEMBLE_WEIGHTS),
        id_key="chunk_id",
    )


def _extract_section_filter(query: str) -> dict[str, str] | None:
    """Return `{"section": "§ NNN"}` when `query` cites an explicit §-section.

    Must match the exact stored metadata format (space after "§", optional
    trailing letter, e.g. "§ 535", "§ 555d", "§ 558b") since the metadata filter
    on both sub-retrievers is flat equality, not partial matching.
    """
    match = _SECTION_RE.search(query)
    if not match:
        return None
    return {"section": f"§ {match.group(1)}"}


def _rerank(query: str, docs: list[Document], top_n: int) -> list[Document]:
    """Rerank `docs` against `query` via OpenRouter's rerank endpoint.

    Raises on any HTTP/network failure — callers are responsible for fallback.
    """
    response = requests.post(
        f"{config.LLM_BASE_URL}/rerank",
        json={
            "model": config.RERANK_MODEL,
            "query": query,
            "documents": [doc.page_content for doc in docs],
            "top_n": top_n,
        },
        headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
        timeout=15,
    )
    response.raise_for_status()
    results = response.json()["results"]
    return [docs[result["index"]] for result in results]


class _RerankingRetriever(BaseRetriever):
    """Fetches a wide candidate pool from `inner`, then reranks down to `top_k`.

    Falls back to `inner`'s own fused order (truncated to `top_k`) if the rerank
    call fails — a rerank outage must degrade gracefully rather than break every
    `search_statutes`/`search_case_law` tool call.
    """

    inner: BaseRetriever
    top_k: int = config.RETRIEVAL_K

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        candidates = self.inner.invoke(query)
        if not candidates:
            return []
        try:
            return _rerank(query, candidates, self.top_k)
        except Exception:
            logger.warning("Rerank call failed; falling back to fused order.", exc_info=True)
            return candidates[: self.top_k]


class _StatutesRetriever(BaseRetriever):
    """For `statutes`: narrows to an explicitly-cited §-section when present in the
    query, falling back to the unfiltered candidate pool if that yields nothing
    (a section-format mismatch must never zero out recall by over-filtering).
    """

    metadata_filter: dict[str, Any] | None
    candidate_k: int

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        section_filter = _extract_section_filter(query)
        if section_filter and "section" not in (self.metadata_filter or {}):
            narrowed = {**(self.metadata_filter or {}), **section_filter}
            docs = _build_ensemble(
                config.STATUTES_COLLECTION, narrowed, self.candidate_k
            ).invoke(query)
            if docs:
                return docs
        return _build_ensemble(
            config.STATUTES_COLLECTION, self.metadata_filter, self.candidate_k
        ).invoke(query)


def get_hybrid_retriever(
    collection: str, metadata_filter: dict[str, Any] | None = None
) -> BaseRetriever:
    """Return the retriever for `collection`: hybrid fusion, optional §-section
    narrowing (statutes only), then reranking down to `config.RETRIEVAL_K`.

    Raises `RuntimeError` (via `db.assert_embedding_model`) if the collection's
    recorded embedding model/dim no longer matches `config.EMBEDDING_MODEL`/
    `EMBEDDING_DIM`.
    """
    candidate_k = config.RERANK_CANDIDATE_K
    if collection == config.STATUTES_COLLECTION:
        db.assert_embedding_model(collection)
        inner: BaseRetriever = _StatutesRetriever(
            metadata_filter=metadata_filter, candidate_k=candidate_k
        )
    else:
        inner = _build_ensemble(collection, metadata_filter, candidate_k)

    return _RerankingRetriever(inner=inner, top_k=config.RETRIEVAL_K)
