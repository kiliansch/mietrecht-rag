"""Postgres engine/connection helpers, one-time schema setup, and the embedding-model
provenance guard.

`setup_db()` is the only place that creates tables/extensions/indexes. It is idempotent
and must never run inside the request path (see CLAUDE.md / docs/mietrecht_agentic_rewrite_spec.md).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psycopg
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_postgres.v2.indexes import HNSWIndex
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from src import config

logger = logging.getLogger(__name__)

# Postgres text-search configuration used for all FTS columns/queries.
FTS_LANGUAGE = "german"


def _async_url(database_url: str) -> str:
    """Rewrite a plain psycopg DSN into the SQLAlchemy async URL PGEngine requires."""
    scheme, _, rest = database_url.partition("://")
    if "+" in scheme:
        return database_url
    return f"{scheme}+psycopg://{rest}"


def get_engine() -> PGEngine:
    """Return a PGEngine (async SQLAlchemy engine) for PGVectorStore."""
    return PGEngine.from_connection_string(_async_url(config.DATABASE_URL))


def get_connection() -> psycopg.Connection:
    """Open a new synchronous psycopg3 connection for raw SQL (FTS, provenance)."""
    return psycopg.connect(config.DATABASE_URL)


def get_embeddings() -> OpenAIEmbeddings:
    """Return the embeddings client (OpenRouter-hosted, OpenAI-compatible)."""
    return OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        dimensions=config.EMBEDDING_DIM,
        base_url=config.LLM_BASE_URL,
        api_key=SecretStr(os.environ.get("OPENAI_API_KEY", "")),
    )


def _table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_fts_column(conn: psycopg.Connection, table_name: str, content_column: str = "content") -> None:
    """Add a generated tsvector column + GIN index for German full-text search."""
    tsv_column = f"{content_column}_tsv"
    conn.execute(
        sql.SQL(
            "ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {tsv_col} tsvector "
            "GENERATED ALWAYS AS (to_tsvector({lang}, {content_col})) STORED"
        ).format(
            table=sql.Identifier(table_name),
            tsv_col=sql.Identifier(tsv_column),
            lang=sql.Literal(FTS_LANGUAGE),
            content_col=sql.Identifier(content_column),
        )
    )
    conn.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {table} USING GIN ({tsv_col})").format(
            idx=sql.Identifier(f"{table_name}_{tsv_column}_idx"),
            table=sql.Identifier(table_name),
            tsv_col=sql.Identifier(tsv_column),
        )
    )


def _ensure_collection_table(engine: PGEngine, collection: str) -> None:
    with get_connection() as conn:
        conn.autocommit = True
        if not _table_exists(conn, collection):
            engine.init_vectorstore_table(collection, vector_size=config.EMBEDDING_DIM)
        _ensure_fts_column(conn, collection)

    store = PGVectorStore.create_sync(engine, get_embeddings(), collection)
    try:
        store.apply_vector_index(HNSWIndex())
    except Exception as exc:  # index already exists, or pgvector version quirk
        logger.debug("Vector index for %s not (re)created: %s", collection, exc)


def _ensure_collection_meta_table(conn: psycopg.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS collection_meta ("
        "  collection_name TEXT PRIMARY KEY,"
        "  embedding_model TEXT NOT NULL,"
        "  embedding_dim INTEGER NOT NULL"
        ")"
    )


def _ensure_case_law_parents_table(conn: psycopg.Connection) -> None:
    """Non-embedded store for the larger case-law parent sections (small-to-big
    retrieval). Children are embedded in the `case_law` collection and carry a
    `parent_id`; the parent text is fetched by id at retrieval time."""
    conn.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {table} ("
            "  parent_id TEXT PRIMARY KEY,"
            "  content TEXT NOT NULL,"
            "  metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb"
            ")"
        ).format(table=sql.Identifier(config.CASE_LAW_PARENTS_TABLE))
    )


def _ensure_app_tables(conn: psycopg.Connection) -> None:
    """Application tables (auth + cases). Real SQL tables, unlike the KV memory store,
    because they need relational queries (per-user listings, due-date ordering)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "  id SERIAL PRIMARY KEY,"
        "  username TEXT NOT NULL UNIQUE,"  # lowercased; the store namespace key
        "  display_name TEXT NOT NULL,"
        "  password_hash TEXT NOT NULL,"  # bcrypt
        "  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),"
        "  persona TEXT NOT NULL DEFAULT 'mieter'"
        "    CHECK (persona IN ('mieter','vermieter','jurist')),"
        "  is_active BOOLEAN NOT NULL DEFAULT TRUE,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    # A case ("Mietfall-Akte") is a named workspace with its own LangGraph chat
    # thread, attached documents (contract/letters/drafts) and legal deadlines.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cases ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  title TEXT NOT NULL,"
        "  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),"
        "  thread_id UUID NOT NULL DEFAULT gen_random_uuid(),"  # one thread per case
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS cases_user_idx ON cases(user_id)")
    # Saved free-chat conversations ("Verlauf"). The messages themselves live in the
    # LangGraph checkpointer (keyed by thread_id); this table just gives each user a
    # named, listable index of their threads so past chats can be reopened.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_threads ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  thread_id UUID NOT NULL,"
        "  title TEXT NOT NULL,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  UNIQUE (user_id, thread_id)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS chat_threads_user_idx "
        "ON chat_threads(user_id, updated_at DESC)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS case_documents ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,"
        "  kind TEXT NOT NULL CHECK (kind IN ('contract','letter','draft')),"
        "  filename TEXT,"
        "  title TEXT NOT NULL,"
        "  content TEXT NOT NULL,"  # sanitised extracted text / generated draft markdown
        "  analysis JSONB,"
        "  sources JSONB,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS case_documents_case_idx ON case_documents(case_id)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS deadlines ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,"
        "  document_id UUID REFERENCES case_documents(id) ON DELETE SET NULL,"
        "  title TEXT NOT NULL,"
        "  due_date DATE NOT NULL,"
        "  note TEXT NOT NULL DEFAULT '',"
        "  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','missed')),"
        "  created_by TEXT NOT NULL DEFAULT 'agent',"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS deadlines_case_due_idx ON deadlines(case_id, due_date)"
    )


def setup_db() -> None:
    """Idempotent one-time setup: extensions, memory tables, vector collections, FTS, HNSW."""
    from src.auth import seed_admin  # local import — src.auth imports this module

    with get_connection() as conn:
        conn.autocommit = True
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        _ensure_collection_meta_table(conn)
        _ensure_case_law_parents_table(conn)
        _ensure_app_tables(conn)

    try:
        if seed_admin():
            logger.info("Seeded admin account '%s'.", config.ADMIN_USERNAME)
    except ValueError as exc:
        # A weak/invalid ADMIN_PASSWORD must not break schema setup — but say so loudly.
        logger.warning("Admin account NOT seeded: %s", exc)

    with PostgresSaver.from_conn_string(config.DATABASE_URL) as saver:
        saver.setup()
    with PostgresStore.from_conn_string(config.DATABASE_URL) as store:
        store.setup()

    engine = get_engine()
    for collection in (config.STATUTES_COLLECTION, config.CASE_LAW_COLLECTION):
        _ensure_collection_table(engine, collection)

    logger.info("Database setup complete.")


def get_vectorstore(collection: str) -> PGVectorStore:
    """Return the PGVectorStore for `collection`, after checking embedding-model provenance."""
    assert_embedding_model(collection)
    engine = get_engine()
    return PGVectorStore.create_sync(engine, get_embeddings(), collection, k=config.RETRIEVAL_K)


def assert_embedding_model(collection: str) -> None:
    """Raise RuntimeError if `collection`'s recorded embedding model/dim differs from config.

    A missing record (collection not yet ingested) is not an error.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT embedding_model, embedding_dim FROM collection_meta WHERE collection_name = %s",
            (collection,),
        ).fetchone()
    if row is None:
        return
    model, dim = row
    if model != config.EMBEDDING_MODEL or dim != config.EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding model mismatch for collection '{collection}': "
            f"stored model={model!r} (dim={dim}) but config.EMBEDDING_MODEL="
            f"{config.EMBEDDING_MODEL!r} (dim={config.EMBEDDING_DIM}). "
            "Re-ingest this collection with the configured model, or fix config.py."
        )


def record_embedding_provenance(collection: str) -> None:
    """Upsert the configured embedding model/dim as the provenance record for `collection`."""
    with get_connection() as conn:
        conn.autocommit = True
        conn.execute(
            "INSERT INTO collection_meta (collection_name, embedding_model, embedding_dim) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (collection_name) DO UPDATE SET "
            "embedding_model = EXCLUDED.embedding_model, embedding_dim = EXCLUDED.embedding_dim",
            (collection, config.EMBEDDING_MODEL, config.EMBEDDING_DIM),
        )


def collection_row_count(collection: str) -> int:
    """Return the number of chunks currently stored in `collection` (0 if table absent)."""
    with get_connection() as conn:
        if not _table_exists(conn, collection):
            return 0
        row = conn.execute(sql.SQL("SELECT count(*) FROM {table}").format(table=sql.Identifier(collection))).fetchone()
    return int(row[0]) if row else 0


def clear_collection(collection: str) -> None:
    """Delete all rows from `collection` (used by --force re-ingestion)."""
    with get_connection() as conn:
        conn.autocommit = True
        if _table_exists(conn, collection):
            conn.execute(sql.SQL("TRUNCATE TABLE {table}").format(table=sql.Identifier(collection)))


def clear_case_law_parents() -> None:
    """Truncate the case-law parent store (used by --force re-ingestion of case_law)."""
    with get_connection() as conn:
        conn.autocommit = True
        if _table_exists(conn, config.CASE_LAW_PARENTS_TABLE):
            conn.execute(
                sql.SQL("TRUNCATE TABLE {table}").format(
                    table=sql.Identifier(config.CASE_LAW_PARENTS_TABLE)
                )
            )


def upsert_case_law_parents(rows: list[tuple[str, str, dict[str, Any]]]) -> None:
    """Insert/replace parent rows `(parent_id, content, metadata)` into the parent store."""
    if not rows:
        return
    stmt = sql.SQL(
        "INSERT INTO {table} (parent_id, content, metadata) VALUES (%s, %s, %s) "
        "ON CONFLICT (parent_id) DO UPDATE SET "
        "content = EXCLUDED.content, metadata = EXCLUDED.metadata"
    ).format(table=sql.Identifier(config.CASE_LAW_PARENTS_TABLE))
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.executemany(stmt, [(pid, content, Jsonb(meta)) for pid, content, meta in rows])


def fetch_case_law_parents(parent_ids: list[str]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return `{parent_id: (content, metadata)}` for the given ids (one round-trip)."""
    if not parent_ids:
        return {}
    stmt = sql.SQL(
        "SELECT parent_id, content, metadata FROM {table} WHERE parent_id = ANY(%s)"
    ).format(table=sql.Identifier(config.CASE_LAW_PARENTS_TABLE))
    with get_connection() as conn:
        rows = conn.execute(stmt, (parent_ids,)).fetchall()
    return {pid: (content, dict(meta or {})) for pid, content, meta in rows}
