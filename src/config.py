"""Single source of truth for models, database, chunking, retrieval and eval settings.

No module outside this file should hardcode a model id, DSN, chunk size, or threshold.
"""

import os

# --- LLMs (OpenRouter via init_chat_model with model_provider="openai") ---
# LLM_MAIN must be a key value in LLM_CHOICES (the curated UI list, below) so the
# default and the contract-review model are always a real, selectable model.
LLM_MAIN = "anthropic/claude-haiku-4.5"  # agent + judge default
LLM_JUDGE = "google/gemini-2.5-flash"  # RAGAs evaluation judge
LLM_BASE_URL = "https://openrouter.ai/api/v1"

# --- Database ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://mietrecht:mietrecht@localhost:5432/mietrecht"
)

# --- API / frontend (FastAPI layer + React client) ---
# Seed credentials for the predefined admin account: `setup-db` creates the user
# ADMIN_USERNAME with this password (bcrypt-hashed) if it does not exist yet. It is
# never used for request auth directly — login goes through the users table + JWT.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
# HS256 signing secret for the session JWTs. When empty, login is disabled (503)
# rather than falling back to a hardcoded secret.
AUTH_SECRET = os.environ.get("AUTH_SECRET", "")
AUTH_TOKEN_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "72"))
# Browser origins allowed by CORS (comma-separated). Default is the Vite dev server.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
# Hard cap on contract-upload size, enforced before any text extraction (OCR is slow).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
# Character cap for sanitised case-document text persisted in `case_documents.content`
# (a conscious, documented departure from "raw text never persisted": the agent must
# be able to re-read case letters/contracts across turns).
CASE_DOC_MAX_CHARS = 80_000

# --- Vector collections (pgvector tables) ---
STATUTES_COLLECTION = "statutes"
CASE_LAW_COLLECTION = "case_law"

# --- Embeddings ---
# text-embedding-3-large via OpenRouter, requested at a reduced output dimension
# (OpenAI's native "dimensions" truncation, not naive slicing). 3072 (the model's
# native size) exceeds pgvector's 2000-dim limit for HNSW/IVFFlat indexes, so 1536
# is used here to keep vector indexing available while retaining strong quality.
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 1536
# Per-1M-token price (USD) for EMBEDDING_MODEL — used ONLY by the case-law
# ingestion dry-run to project embedding spend before the paid run (no other
# code path spends on embeddings). Verify against the live catalogue.
EMBEDDING_PRICE_PER_1M = 0.13
# Small embedding model used only for RAGAs answer-similarity metrics, never for storage.
RAGAS_EMBEDDING_MODEL = "text-embedding-3-small"

# --- Chunking ---
# cl100k_base is the tokenizer for the text-embedding-3-* family and the practical
# proxy for the OpenRouter-hosted answer-generator models (no public exact tokenizer).
TOKENIZER = "cl100k_base"
STATUTE_CHUNK_TOKENS = 320
STATUTE_CHUNK_OVERLAP = 64
# Case-law uses parent-document (small-to-big) chunking: small CHILD chunks are the
# precise unit that gets embedded + FTS-indexed, while the larger PARENT window is
# what retrieval returns for context (see src.retrieval.hybrid._ParentExpandingRetriever).
# Children are smaller than statute chunks so near-identical siblings in a long
# decision compete on a finer grain; the parent restores the surrounding reasoning.
CASE_LAW_CHILD_CHUNK_TOKENS = 320
CASE_LAW_CHILD_CHUNK_OVERLAP = 64
# Court reasoning runs long; the parent window is capped so one huge
# "Entscheidungsgründe" section cannot dominate a returned slot. No overlap: parents
# are retrieved by id (never re-embedded), so boundary continuity does not matter.
CASE_LAW_PARENT_CHUNK_TOKENS = 1024
CASE_LAW_PARENT_CHUNK_OVERLAP = 0

# --- Retrieval ---
RETRIEVAL_K = 6
# The single `search_law` tool queries BOTH corpora per call; this caps how many
# (already hybrid-fused + reranked) snippets each corpus contributes. Set to
# RETRIEVAL_K so one merged call matches the recall of the previous two separate
# tool calls (6 statutes + 6 case-law); precision has ample headroom after reranking.
SEARCH_LAW_PER_CORPUS_K = RETRIEVAL_K
# (dense_weight, lexical_weight) for EnsembleRetriever reciprocal rank fusion.
# Env-overridable ("dense,lexical", e.g. "0.4,0.6") so the precision sweep can favour
# the lexical side (legal text is keyword-driven) without a code edit.
ENSEMBLE_WEIGHTS = tuple(  # type: ignore[assignment]
    float(w) for w in os.environ.get("ENSEMBLE_WEIGHTS", "0.5,0.5").split(",")
)
# Per-snippet cap (after sanitisation) for retrieval-tool output, keeping the
# untrusted context fed back to the model bounded.
RETRIEVAL_SNIPPET_MAX_CHARS = 1500
# Relaxed per-snippet cap for CASE-LAW parent sections in `search_law`: a returned
# parent window (see CASE_LAW_PARENT_CHUNK_TOKENS) is deliberately larger than a
# statute snippet, so it gets its own higher bound. Statutes keep the tighter cap.
CASE_LAW_PARENT_SNIPPET_MAX_CHARS = 3000

# --- Case-law parent-document (small-to-big) retrieval ---
# Feature toggle (env-overridable) so the parent-expansion change can be A/B-measured
# against the child-chunk baseline without a re-ingestion or a code edit: retrieval
# reads this at call time. "0"/"false"/"no" disable it; anything else (default) enables.
# Kept ON: the A/B (docs/parent_document_retrieval_eval.md) showed case-law
# context_recall 0.567 -> 0.800 for a -0.048 precision trade on the n=20 eval set.
CASE_LAW_PARENT_EXPANSION = os.environ.get("CASE_LAW_PARENT_EXPANSION", "1").lower() not in (
    "0",
    "false",
    "no",
)
# How many reranked CHILD chunks to consider before de-duplicating up to
# CASE_LAW_PARENT_K distinct PARENTS. Wider than the returned count because several top
# children often share one parent; this leaves enough distinct parents to fill the slots.
CASE_LAW_CHILD_FANOUT_K = 12
# How many distinct PARENT sections the case-law retriever returns. Fewer parents ->
# higher precision (the lowest-ranked, least-relevant contexts drop out) at some recall
# cost; env-overridable so this precision/recall trade can be swept. Defaults to
# RETRIEVAL_K (parity with the statute side).
CASE_LAW_PARENT_K = int(os.environ.get("CASE_LAW_PARENT_K", str(RETRIEVAL_K)))
# Rerank the assembled PARENT sections against the query before returning the top
# CASE_LAW_PARENT_K. Children are reranked to pick WHICH decisions; this second pass
# orders the whole parent sections by relevance so the most on-point ruling lands at
# rank 1 (context_precision is rank-weighted, so ordering matters). Env-overridable.
CASE_LAW_PARENT_RERANK = os.environ.get("CASE_LAW_PARENT_RERANK", "1").lower() not in (
    "0",
    "false",
    "no",
)
# Non-embedded table holding the larger parent sections, keyed by parent_id and
# joined in at retrieval time (children live in CASE_LAW_COLLECTION as usual).
CASE_LAW_PARENTS_TABLE = "case_law_parents"

# --- Case-law query-time precision levers (all env-overridable, case-law only) ---
# Court-level metadata narrowing: when the query names a higher court (BGH / BVerfG /
# "höchstrichterlich"), restrict to that court level (mirrors the statute §-narrowing),
# with a fallback to the unfiltered pool so it can never zero out recall.
CASE_LAW_COURT_FILTER = os.environ.get("CASE_LAW_COURT_FILTER", "0").lower() not in (
    "0",
    "false",
    "no",
)
# Multi-query: one LLM call expands the question into several German query variants; the
# case-law ensemble runs for each and the results are fused before reranking. Adds a
# per-`search_law` LLM call (latency), so it is a deliberate on/off choice.
CASE_LAW_MULTI_QUERY = os.environ.get("CASE_LAW_MULTI_QUERY", "0").lower() not in (
    "0",
    "false",
    "no",
)
# Number of query variants the multi-query expander generates (the original question is
# always included in addition to these).
MULTI_QUERY_N = int(os.environ.get("MULTI_QUERY_N", "3"))
# Cheap/fast model for the multi-query expansion (bounds the added per-query latency).
MULTI_QUERY_MODEL = os.environ.get("MULTI_QUERY_MODEL", "google/gemini-2.5-flash")

# --- Case-law contextual retrieval (ingestion-time) ---
# When ingesting with --contextual, one LLM call per DECISION generates a short German
# context blurb (court, Az, date, one-sentence gist) that is prepended to each CHILD
# chunk before embedding + FTS (the parent text the model reads stays clean). This
# situates otherwise-ambiguous fragments so the reranker can surface the right decision.
CONTEXTUAL_MODEL = os.environ.get("CONTEXTUAL_MODEL", "google/gemini-2.5-flash")
# How much of the decision text (chars) to feed the context generator — enough to cover
# Tenor / Leitsatz / start of the reasoning without paying for the whole ruling.
CONTEXTUAL_SOURCE_MAX_CHARS = int(os.environ.get("CONTEXTUAL_SOURCE_MAX_CHARS", "6000"))
# Client-side concurrency for the per-decision generation calls (bounds wall-clock time
# over ~15.6k decisions without hammering the provider).
CONTEXTUAL_MAX_WORKERS = int(os.environ.get("CONTEXTUAL_MAX_WORKERS", "12"))
# Per-1M-token price (input, output) for CONTEXTUAL_MODEL — used only by the dry-run to
# project the context-generation spend (the re-embedding spend uses EMBEDDING_PRICE_PER_1M).
CONTEXTUAL_MODEL_PRICE_PER_1M = (0.15, 0.60)

# --- Reranking ---
# OpenRouter exposes rerank models on a dedicated endpoint (POST
# f"{LLM_BASE_URL}/rerank"), same credentials as the chat models. Used to fix
# precision/recall on long case-law decisions where many near-identical chunks
# from the same decision compete for the same RETRIEVAL_K slot.
RERANK_MODEL = "cohere/rerank-4-fast"
# Wider per-sub-retriever pool fetched before fusion+reranking; RETRIEVAL_K stays
# the final count returned after reranking. Env-overridable so the precision sweep can
# widen the candidate pool (more choices for the reranker -> tighter top-k).
RERANK_CANDIDATE_K = int(os.environ.get("RERANK_CANDIDATE_K", "20"))

# --- Case-law ingestion ---
# Path to the local Open Legal Data court-decisions dump (parquet shards). No default:
# set CASE_LAW_DUMP_PATH in the environment or pass --dump-path to `ingest-case-law`.
CASE_LAW_DUMP_PATH = os.environ.get("CASE_LAW_DUMP_PATH", "")
# Caps only the precision-checked keyword-only tier (see
# `src.ingest.case_law.filter_mietrecht_decisions`); decisions that cite a
# Mietrecht statute directly are always kept in full regardless of this value.
MAX_DECISIONS = 10000
# §535-§577 BGB cover the Mietrecht (rental law) chapter.
MIETRECHT_BGB_SECTION_REGEX = r"§{1,2}\s*5(3[5-9]|[4-6]\d|7[0-7])[a-z]?\s*(Abs\.?\s*\d+\s*)?BGB"
# BetrKV, WoGG and HeizkostenV are the other Mietrecht-specific statutes in
# this project's domain (operating costs, housing allowance, heating costs).
MIETRECHT_RELATED_STATUTES_REGEX = r"§{1,2}\s*\d+[a-z]?\s*(Abs\.?\s*\d+\s*)?(BetrKV|WoGG|HeizkostenV)"
MIETRECHT_KEYWORDS = [
    "Miete",
    "Mieter",
    "Mietvertrag",
    "Vermieter",
    "Mietverhältnis",
    "Kaution",
    "Betriebskosten",
    "Nebenkosten",
    "Kündigung",
    "Mietminderung",
    "Mietspiegel",
    "Mietpreisbremse",
    "Wohnraum",
    "Nebenkostenabrechnung",
    "Modernisierung",
    "Eigenbedarf",
]
# Minimum distinct MIETRECHT_KEYWORDS hits for a decision without a direct
# statute citation to be considered relevant (precision bar for the
# keyword-only tier — a single incidental hit, e.g. "Kündigung" in an
# unrelated employment dispute, is not enough).
MIETRECHT_MIN_KEYWORD_HITS = 2
# Number of `kept` decisions chunked, embedded and written per
# `add_documents()` call in `ingest_case_law`. Bounds memory to roughly this
# many decisions' worth of chunks+embeddings regardless of how large the
# two-tier filter's `kept` list grows, and makes each batch's embedding spend
# land in `case_law` immediately (no all-or-nothing run).
CASE_LAW_INGEST_BATCH_DECISIONS = 200

# --- Evaluation ---
# Adopted from src/eval/ragas_eval.py (empirically tuned) as the single threshold set.
THRESHOLDS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.75,
    "context_precision": 0.90,
    "context_recall": 0.75,
    # Deterministic, judge-free case-law retrieval metrics (see src.eval.runner): does the
    # retriever surface the specific gold decision (hit_rate@k) and rank it high (MRR)?
    # These complement the LLM RAGAs metrics, which — with parent-document retrieval
    # returning several valid decisions per query against a single-sentence ground truth —
    # structurally understate precision. Targets reflect that a single hand-picked gold is
    # a floor (equally valid rulings can be surfaced instead). Non-case-law tables report
    # these as N/A.
    "hit_rate": 0.75,
    "mrr": 0.60,
}

# --- LLM model choices for UI selector ---
# Curated spread (cheapest -> premium) of tool-capable chat models from the
# available OpenRouter catalogue. Embedding, rerank, image and speech models are
# deliberately excluded: this agent is a tool-calling ReAct loop and those model
# classes cannot drive it. Keep this list short and focused.
# NOTE: the slugs/prices below must match the live OpenRouter catalogue
# (https://openrouter.ai/models). A wrong slug raises at call time inside
# init_chat_model, so verify before shipping.
LLM_CHOICES: dict[str, str] = {
    "Claude Haiku 4.5 (schnell)": "anthropic/claude-haiku-4.5",
    "Gemini 2.5 Flash (günstig)": "google/gemini-2.5-flash",
    "GPT-4.1 Mini (ausgewogen)": "openai/gpt-4.1-mini",
    "GPT-5 Mini (stark)": "openai/gpt-5-mini",
    "GPT-5.4 (Premium)": "openai/gpt-5.4",
}

# Per-1M-token pricing (input, output) in USD — used for cost display. Keys must
# stay in sync with LLM_CHOICES values; verify rates against the live catalogue.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "openai/gpt-5-mini": (0.25, 2.00),
    "openai/gpt-5.4": (1.25, 10.00),
}

# Default LLM parameters.
DEFAULT_TEMPERATURE: float = 0.0
DEFAULT_TOP_P: float | None = None

# Contract clause checker: risky topics to screen (compiled to re.search patterns).
CONTRACT_RISKY_PATTERNS: list[str] = [
    r"Schönheitsreparatur",
    r"Kleinreparatur",
    r"Kaution",
    r"Endrenovierung",
    r"Tierhaltung|Haustier",
    r"Untervermietung",
    r"Staffelmiete|Indexmiete",
    r"Kündigungsverzicht",
]
