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
from langchain.chat_models import init_chat_model
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from psycopg import sql

from src import config, db

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE)

# Court cues → a flat-equality case-law metadata filter. `court_name` is exact
# ("Bundesgerichtshof"), `level_of_appeal="Bundesgericht"` groups all federal courts;
# both are stored on every case-law chunk (see `_decision_to_chunks` base_metadata).
_COURT_CUES: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    (re.compile(r"\bBVerfG\b|Bundesverfassungsgericht", re.IGNORECASE),
     {"court_name": "Bundesverfassungsgericht"}),
    (re.compile(r"\bBGH\b|Bundesgerichtshof", re.IGNORECASE),
     {"court_name": "Bundesgerichtshof"}),
    (re.compile(r"höchstrichterlich|Bundesgericht", re.IGNORECASE),
     {"level_of_appeal": "Bundesgericht"}),
)


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


def _extract_court_filter(query: str) -> dict[str, str] | None:
    """Return a case-law court-level metadata filter when `query` names a higher court.

    E.g. a query mentioning "BGH"/"höchstrichterlich" narrows to federal-court rulings.
    Returns the FIRST matching cue (most specific first) or None. Applied only for the
    case-law collection, always with a fallback-to-unfiltered guard so it cannot zero out
    recall (mirrors the statute §-narrowing).
    """
    for pattern, filter_dict in _COURT_CUES:
        if pattern.search(query):
            return dict(filter_dict)
    return None


_MULTI_QUERY_PROMPT = (
    "Du bist ein Assistent für die Recherche in deutscher Rechtsprechung (Mietrecht). "
    "Formuliere zu der folgenden Nutzerfrage {n} alternative, kurze Suchanfragen, die "
    "dieselbe Rechtsfrage mit anderen Formulierungen, Synonymen oder einschlägigen "
    "Fachbegriffen (z. B. Paragraphen, Rechtsbegriffe) abdecken. Gib ausschließlich die "
    "Suchanfragen zurück, eine pro Zeile, ohne Nummerierung.\n\nFrage: {query}"
)


def _expand_queries(query: str) -> list[str]:
    """Expand `query` into `config.MULTI_QUERY_N` German search variants via one LLM call.

    Returns only the generated variants (the caller keeps the original separately). On any
    failure returns `[]` so retrieval degrades to the single original query.
    """
    try:
        llm = init_chat_model(
            config.MULTI_QUERY_MODEL,
            model_provider="openai",
            base_url=config.LLM_BASE_URL,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            temperature=0.0,
        )
        prompt = _MULTI_QUERY_PROMPT.format(n=config.MULTI_QUERY_N, query=query)
        text = str(llm.invoke(prompt).content)
    except Exception:
        logger.warning("Multi-query expansion failed; using the single query.", exc_info=True)
        return []
    variants = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    # Drop echoes of the original and cap to the configured count.
    seen = {query.strip().lower()}
    out: list[str] = []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[: config.MULTI_QUERY_N]


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


class _ParentExpandingRetriever(BaseRetriever):
    """Case-law small-to-big: reranks CHILD chunks, then returns their PARENT sections.

    Walks the reranked children collecting distinct `parent_id`s (so several
    near-identical siblings from one long decision can never occupy more than one slot —
    this subsumes a same-decision cap), fetches the larger parent text by id, then
    optionally reranks the whole parent sections against the query so the most on-point
    ruling lands at rank 1 (`config.CASE_LAW_PARENT_RERANK`; `context_precision` is
    rank-weighted). Up to `candidate_k` distinct parents are gathered so that second
    rerank has real choice; `top_k` are returned. A child without a `parent_id`, or whose
    parent row is missing, degrades gracefully to the child's own content.
    """

    inner: BaseRetriever
    top_k: int = config.RETRIEVAL_K
    candidate_k: int = config.CASE_LAW_CHILD_FANOUT_K

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        children = self.inner.invoke(query)
        # Gather more distinct parents than we return, so the parent rerank can choose.
        gather = max(self.top_k, self.candidate_k) if config.CASE_LAW_PARENT_RERANK else self.top_k
        ordered_parent_ids: list[str] = []
        first_child: dict[str, Document] = {}
        fallbacks: list[Document] = []
        for child in children:
            parent_id = child.metadata.get("parent_id")
            if not parent_id:
                fallbacks.append(child)
                continue
            if parent_id not in first_child:
                first_child[parent_id] = child
                ordered_parent_ids.append(parent_id)
            if len(ordered_parent_ids) >= gather:
                break

        parents = db.fetch_case_law_parents(ordered_parent_ids)
        results: list[Document] = []
        for parent_id in ordered_parent_ids:
            child = first_child[parent_id]
            fetched = parents.get(parent_id)
            content = fetched[0] if fetched else child.page_content
            results.append(Document(page_content=content, metadata=child.metadata))
        # If no children carried a parent_id (unexpected), fall back to child chunks.
        if not results:
            return fallbacks[: self.top_k]
        if config.CASE_LAW_PARENT_RERANK and len(results) > 1:
            try:
                return _rerank(query, results, self.top_k)
            except Exception:
                logger.warning("Parent rerank failed; keeping child-rank order.", exc_info=True)
        return results[: self.top_k]


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


def _case_law_ensemble(
    query: str, base_filter: dict[str, Any] | None, candidate_k: int
) -> list[Document]:
    """Fetch case-law candidates for one `query`, applying optional court-level narrowing.

    When `config.CASE_LAW_COURT_FILTER` is on and `query` names a higher court, the search
    is narrowed to that court, falling back to the unfiltered pool if the narrowed search
    returns nothing (the same recall guard as `_StatutesRetriever`).
    """
    if config.CASE_LAW_COURT_FILTER:
        court_filter = _extract_court_filter(query)
        base_keys = base_filter or {}
        if court_filter and not (set(court_filter) & set(base_keys)):
            narrowed = {**base_keys, **court_filter}
            docs = _build_ensemble(config.CASE_LAW_COLLECTION, narrowed, candidate_k).invoke(query)
            if docs:
                return docs
    return _build_ensemble(config.CASE_LAW_COLLECTION, base_filter, candidate_k).invoke(query)


class _CaseLawInnerRetriever(BaseRetriever):
    """Case-law candidate stage feeding the reranker: optional multi-query expansion +
    optional court-level metadata narrowing, fused into one deduplicated candidate list.

    Both levers are query-time and independently toggled (`config.CASE_LAW_MULTI_QUERY`,
    `config.CASE_LAW_COURT_FILTER`); with both off this is exactly `_build_ensemble`, so
    the parent-document baseline is preserved bit-for-bit.
    """

    metadata_filter: dict[str, Any] | None
    candidate_k: int

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        queries = [query]
        if config.CASE_LAW_MULTI_QUERY:
            queries.extend(_expand_queries(query))

        merged: dict[str, Document] = {}
        order: list[str] = []
        for i, q in enumerate(queries):
            for j, doc in enumerate(_case_law_ensemble(q, self.metadata_filter, self.candidate_k)):
                # Dedup across query variants by chunk_id (the ensemble's own id key);
                # fall back to a positional key if a doc somehow lacks it.
                key = str(doc.metadata.get("chunk_id") or f"{i}:{j}:{doc.page_content[:64]}")
                if key not in merged:
                    merged[key] = doc
                    order.append(key)
        return [merged[k] for k in order]


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
        return _RerankingRetriever(inner=inner, top_k=config.RETRIEVAL_K)

    # Case-law: query-time candidate stage (optional multi-query + court narrowing) ->
    # rerank. When parent-document expansion is enabled, rerank a wider CHILD fan-out then
    # expand to distinct PARENT sections; otherwise return the reranked child chunks (the
    # baseline the parent-document change is A/B-measured against). Any other collection
    # keeps the plain fused ensemble.
    if collection == config.CASE_LAW_COLLECTION:
        inner = _CaseLawInnerRetriever(
            metadata_filter=metadata_filter, candidate_k=candidate_k
        )
        if config.CASE_LAW_PARENT_EXPANSION:
            reranked = _RerankingRetriever(inner=inner, top_k=config.CASE_LAW_CHILD_FANOUT_K)
            return _ParentExpandingRetriever(inner=reranked, top_k=config.CASE_LAW_PARENT_K)
        return _RerankingRetriever(inner=inner, top_k=config.CASE_LAW_PARENT_K)

    inner = _build_ensemble(collection, metadata_filter, candidate_k)
    return _RerankingRetriever(inner=inner, top_k=config.RETRIEVAL_K)
