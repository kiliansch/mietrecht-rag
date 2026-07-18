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
# Small embedding model used only for RAGAs answer-similarity metrics, never for storage.
RAGAS_EMBEDDING_MODEL = "text-embedding-3-small"

# --- Chunking ---
# cl100k_base is the tokenizer for the text-embedding-3-* family and the practical
# proxy for the OpenRouter-hosted answer-generator models (no public exact tokenizer).
TOKENIZER = "cl100k_base"
STATUTE_CHUNK_TOKENS = 320
STATUTE_CHUNK_OVERLAP = 64
# Court reasoning runs long; case-law chunks are larger than statute chunks.
CASE_LAW_CHUNK_TOKENS = 640
CASE_LAW_CHUNK_OVERLAP = 96

# --- Retrieval ---
RETRIEVAL_K = 6
# The single `search_law` tool queries BOTH corpora per call; this caps how many
# (already hybrid-fused + reranked) snippets each corpus contributes. Set to
# RETRIEVAL_K so one merged call matches the recall of the previous two separate
# tool calls (6 statutes + 6 case-law); precision has ample headroom after reranking.
SEARCH_LAW_PER_CORPUS_K = RETRIEVAL_K
# (dense_weight, lexical_weight) for EnsembleRetriever reciprocal rank fusion.
ENSEMBLE_WEIGHTS = (0.5, 0.5)
# Per-snippet cap (after sanitisation) for retrieval-tool output, keeping the
# untrusted context fed back to the model bounded.
RETRIEVAL_SNIPPET_MAX_CHARS = 1500

# --- Reranking ---
# OpenRouter exposes rerank models on a dedicated endpoint (POST
# f"{LLM_BASE_URL}/rerank"), same credentials as the chat models. Used to fix
# precision/recall on long case-law decisions where many near-identical chunks
# from the same decision compete for the same RETRIEVAL_K slot.
RERANK_MODEL = "cohere/rerank-4-fast"
# Wider per-sub-retriever pool fetched before fusion+reranking; RETRIEVAL_K stays
# the final count returned after reranking.
RERANK_CANDIDATE_K = 20

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
