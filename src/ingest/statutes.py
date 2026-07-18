"""Ingest `data/laws/rag_documents.json` into the `statutes` pgvector collection.

Writes dense (embedding) + lexical (generated tsvector column, see `src.db`) +
provenance (`embedding_model`/`embedding_dim` per chunk and in `collection_meta`).
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src import config, db
from src.ingest.chunking import get_statute_splitter

logger = logging.getLogger(__name__)

DEFAULT_RAG_DOCUMENTS_PATH = Path("data/laws/rag_documents.json")


def _load_documents(path: Path) -> list[Document]:
    with path.open(encoding="utf-8") as fh:
        raw: list[dict[str, Any]] = json.load(fh)
    return [
        Document(page_content=str(item["page_content"]), metadata=dict(item["metadata"]))
        for item in raw
    ]


def _chunk_documents(documents: list[Document]) -> list[Document]:
    """Token-aware chunking, preserving metadata and assigning stable chunk ids."""
    splitter = get_statute_splitter()
    chunks = splitter.split_documents(documents)

    section_counters: dict[str, int] = {}
    for chunk in chunks:
        section = str(chunk.metadata.get("section", "unknown"))
        absatz = str(chunk.metadata.get("absatz", ""))
        key = f"{section}_{absatz}" if absatz else section
        idx = section_counters.get(key, 0)
        section_counters[key] = idx + 1
        chunk.metadata["chunk_id"] = f"{key}_{idx}"
        chunk.metadata["embedding_model"] = config.EMBEDDING_MODEL
        chunk.metadata["embedding_dim"] = config.EMBEDDING_DIM
    return chunks


def ingest_statutes(
    rag_documents_path: Path = DEFAULT_RAG_DOCUMENTS_PATH,
    force: bool = False,
) -> int:
    """Chunk and embed the statute corpus into the `statutes` collection.

    Returns the number of chunks written (0 if already populated and `force` is False).
    """
    existing = db.collection_row_count(config.STATUTES_COLLECTION)
    if existing > 0 and not force:
        logger.info(
            "'%s' already has %d chunks; skipping (use --force to re-ingest).",
            config.STATUTES_COLLECTION,
            existing,
        )
        return 0
    if existing > 0:
        logger.info("--force: clearing %d existing chunks from '%s'.", existing, config.STATUTES_COLLECTION)
        db.clear_collection(config.STATUTES_COLLECTION)

    documents = _load_documents(rag_documents_path)
    logger.info("Loaded %d statute documents from %s", len(documents), rag_documents_path)

    chunks = _chunk_documents(documents)
    logger.info(
        "Split into %d token-aware chunks (size=%d tokens, overlap=%d).",
        len(chunks),
        config.STATUTE_CHUNK_TOKENS,
        config.STATUTE_CHUNK_OVERLAP,
    )

    ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"statutes:{c.metadata['chunk_id']}")) for c in chunks]

    vectorstore = db.get_vectorstore(config.STATUTES_COLLECTION)
    logger.info(
        "Embedding %d chunks with '%s' (dim=%d)...", len(chunks), config.EMBEDDING_MODEL, config.EMBEDDING_DIM
    )
    vectorstore.add_documents(chunks, ids=ids)
    db.record_embedding_provenance(config.STATUTES_COLLECTION)

    logger.info("Ingested %d chunks into '%s'.", len(chunks), config.STATUTES_COLLECTION)
    return len(chunks)
