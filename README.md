# mietrecht-rag

## Overview

**mietrecht-rag** is a retrieval-augmented knowledge assistant for German rental law
(*Mietrecht*). **The problem it solves:** the rules that decide everyday tenancy
disputes — how high a deposit may be, whether a termination is valid, which operating
costs are billable — are scattered across the German Civil Code (BGB §§ 535–577), the
Operating Costs Ordinance (BetrKV) and the Housing Allowance Act (WoGG), and their
real-world meaning turns on court decisions that non-lawyers can rarely find or read;
a plain chatbot, meanwhile, will confidently invent legal "facts." **The goal:** give
tenants and landlords precise, trustworthy answers that are grounded in the actual law
*and* the case law, with citations they can verify. **How it works:** a hand-built
LangGraph agent answers each question by first retrieving the relevant material from
both corpora at once — a single `search_law` tool runs a hybrid German full-text +
vector search over the statutes *and* the court rulings and reranks the results — then
reasons only over that retrieved evidence and replies with the legal answer plus exact
§-references and case citations, each clickable to read the full source in-app. It
refuses to answer when the sources do not cover the question, and a RAGAs evaluation
harness continuously scores faithfulness and retrieval quality against a labelled
dataset. Beyond one-off questions, users can open a case ("Akte") to upload a contract
or letter, get a per-clause validity review or a deadline-aware analysis, and have the
assistant draft a grounded reply — with every data-writing action gated behind explicit
human approval.

---

An agentic RAG assistant for German rental law (**Mietrecht**), built as a hand-written
LangGraph `StateGraph` with hybrid (Postgres FTS + pgvector) retrieval over two corpora —
**BGB §§ 535–577 / BetrkV / WoGG** statutes and Open Legal Data **court decisions** — plus
Postgres-backed short- and long-term memory, JWT authentication (user/admin roles),
case-based workspaces ("Mietfall-Akten") with document ingestion, legal-deadline tracking
and approval-gated agent actions, and a React frontend. Fully dockerised.

## Feature overview

- **Login & roles** — accounts live in Postgres (bcrypt + JWT). No self-registration:
  the predefined **admin** account (seeded from `ADMIN_USERNAME`/`ADMIN_PASSWORD` by
  `setup-db`) creates users via the *Benutzer* view. Admins additionally see the RAGAs
  *Evaluation* view. The server derives all identity from the token — the client never
  sends a user name.
- **Free chat** — streaming agent turns (SSE) grounded via one `search_law` tool that
  queries **both** corpora at once, plus three calculators, per-user long-term memory and
  a role persona (mieter/vermieter/jurist). Each answer carries a **groundedness badge**
  and **clickable citations** that open the full statute/decision text in-app; past
  conversations are saved to a **"Verlauf"** history, and a **DE/EN toggle** switches
  both the UI and the assistant's answers.
- **Akten (cases)** — each case has its own persistent chat thread (LangGraph
  checkpointer), attached documents and deadlines:
  - **Ingest legal communications** (PDF/DOCX/TXT/images, OCR fallback): the text is
    sanitised (OWASP LLM05) and stored with the case; "Analysieren" streams a summary,
    the legal position with citations, and identified **Fristen**.
  - **Contract review** inside the case: per-clause verdicts (wirksam/bedenklich/
    unwirksam), persisted with the document.
  - **Legal deadlines** — inferred from analysed documents or added manually; overdue
    deadlines are highlighted in the case list and case view.
  - **Approval-gated agent actions (HITL)** — the agent *proposes* `create_deadline`
    and `save_draft` via LangGraph `interrupt()`; nothing is written until the user
    confirms in the chat (Bestätigen/Ablehnen). Rejections resume the thread with the
    refusal.
  - **Response drafts** — ask the agent to draft a reply letter (grounded, with
    §-references); approved drafts are saved to the case and exportable as PDF.

## Project structure

```
.
├── data/
│   └── laws/
│       └── rag_documents.json   # statute corpus (input to ingest-statutes)
├── src/
│   ├── config.py                # single source of truth: models, DSN, chunk sizes, thresholds
│   ├── db.py                    # schema setup: pgvector/FTS, users/cases/deadlines, provenance guard
│   ├── auth.py                  # bcrypt + JWT + users-table CRUD, admin seeding
│   ├── ingest/                  # token-aware chunking, statute + case-law ingestion
│   ├── retrieval/hybrid.py      # hybrid (dense + German FTS) EnsembleRetriever
│   ├── tools/
│   │   ├── retrieval_tools.py   # search_law (queries both corpora at once)
│   │   ├── case_tools.py        # create_deadline, save_draft (approval-gated, interrupt())
│   │   └── …                    # three calculators
│   ├── agent/
│   │   ├── state.py             # AgentState, Context (incl. case_id; not checkpointed)
│   │   ├── prompts.py           # role-aware system prompt + case mode + letter analysis
│   │   ├── security.py          # sanitise/delimit untrusted text (OWASP LLM05)
│   │   ├── nodes.py             # validate_input, load_memory, call_model, write_memory
│   │   └── graph.py             # build_graph(), run/stream/resume_stream
│   ├── cases/store.py           # cases, case_documents, deadlines (psycopg, ownership-gated)
│   ├── memory/store.py          # long-term memory (role, tenancy facts) via PostgresStore
│   ├── api/                     # FastAPI: auth, chat (+resume), cases, profile, admin routers
│   ├── eval/                    # single EVAL_DATASET + single RAGAs runner
│   └── logging/callbacks.py     # PersistentTraceCallback (standalone, kept utility)
├── frontend/                    # React + Vite + TS (Dockerfile: nginx serving dist + /api proxy)
├── tests/                       # offline pytest suite (fakes, no DB/LLM required)
├── docker/entrypoint.sh         # backend container: setup-db (idempotent) then uvicorn
├── docker-compose.yml           # db (pgvector) + backend + frontend
├── Dockerfile                   # backend image (uv + tesseract-deu + poppler)
├── main.py                      # CLI entrypoint
└── pyproject.toml
```

---

## Requirements

- Docker + Docker Compose (that's all for the containerised app)
- For local development additionally: Python 3.11+, [uv](https://github.com/astral-sh/uv), Node 20+
- An **OpenRouter** API key — register at <https://openrouter.ai/>
  (agent LLM, RAGAs judge, and embeddings via an OpenAI-compatible API)
- An **Open Legal Data** API key — <https://de.openlegaldata.io/> (only to re-run
  `fetch_legal_data.py`)

## Quick start (Docker)

```bash
cp .env.example .env
# fill in: OPENAI_API_KEY (OpenRouter), AUTH_SECRET (openssl rand -hex 32),
#          ADMIN_PASSWORD (min. 8 characters — seeds the admin account)

docker compose up --build -d
```

- Frontend: <http://localhost:8080> — log in as `admin` (or `ADMIN_USERNAME`) with your
  `ADMIN_PASSWORD`, then create user accounts in the **Benutzer** view.
- The backend container runs `setup-db` on start (idempotent; also seeds the admin).
- Ingest the corpora once, inside the container:

```bash
docker compose exec backend uv run python main.py ingest-statutes
docker compose exec backend uv run python main.py ingest-case-law --dump-path PATH
```

> Compose runs the DB with its port published (`5432`), so the local dev flow below
> works against the same data. Inside the network the backend overrides
> `DATABASE_URL` to point at the `db` service. The API keeps process-local state
> (rate limiter, eval job) — it must stay single-worker.

## Local development

```bash
uv sync --dev
cp .env.example .env          # fill in OPENAI_API_KEY, AUTH_SECRET, ADMIN_PASSWORD
docker compose up -d db
uv run python main.py setup-db

# Terminal 1 — API
uv run python main.py serve --reload             # http://localhost:8000

# Terminal 2 — frontend (Vite dev server, proxies /api to :8000)
cd frontend && npm install && npm run dev        # http://localhost:5173
```

Accounts can also be bootstrapped from the CLI: `uv run python main.py create-user
--username anna --role user` (prompts for the password).

### Ingest the corpora

```bash
uv run python main.py ingest-statutes [--force]
uv run python main.py ingest-case-law --dump-path PATH [--max-decisions N] [--force]
```

Both are idempotent (`--force` re-ingests) and record `embedding_model`/`embedding_dim`
on every chunk and in `collection_meta`; queries against a mismatched collection raise.

### CLI chat (trusted local tool)

```bash
uv run python main.py ask -q "Wie hoch darf meine Kaution sein?" --user demo --role mieter
uv run python main.py chat --thread t1 --user demo --role mieter
```

The CLI talks to the graph directly and deliberately bypasses the API's JWT auth —
`--user` selects the memory namespace. Use usernames that match real accounts if the
data should be visible in the web app.

### Evaluate

```bash
uv run python main.py eval
```

Runs the single RAGAs runner (`src/eval/runner.py`) against `src/eval/dataset.py`:
agent end-to-end metrics (faithfulness, answer_relevancy, context_precision,
context_recall) plus retrieval-only `context_precision`/`context_recall` per
collection, scored against `config.THRESHOLDS`. Results land in
`data/eval_results.json` and in the admin **Evaluation** view.

---

## Security & privacy notes

- **Identity is server-side**: every API route derives the user from the JWT
  (`Authorization: Bearer`); memory, cases and feedback are namespaced by the
  authenticated username. Case access is ownership-checked on every route.
- **Untrusted text discipline (OWASP LLM05)**: retrieved snippets and ingested
  documents are sanitised and wrapped in `<untrusted_context>` blocks — data, never
  instructions.
- **Human-in-the-loop writes**: the agent cannot create deadlines or save drafts
  without an explicit user confirmation (LangGraph interrupt + resume).
- **Persistence trade-off**: case documents store their **sanitised** text (capped at
  `CASE_DOC_MAX_CHARS`) so the agent can re-read them across turns — a conscious,
  documented departure from the earlier "raw contract text is never persisted" rule.
  Deleting a case cascades to its documents and deadlines.

## Ethical considerations

Legal information touches people's homes and money, so the design makes a few
deliberate ethical trade-offs:

- **Not legal advice.** The assistant explains the law; it is not a lawyer. Answers to
  action questions ("can I terminate?", "should I sue?") append a fixed disclaimer
  directing the user to a Rechtsanwalt, and the UI repeats that caveat. Every citation
  is clickable so a user can verify the answer against the primary source rather than
  trusting the model.
- **Grounding over fluency (hallucination mitigation).** The agent may answer *only*
  from tool results; it is instructed to add nothing from training memory and to reply
  "Diese Information ist in den verfügbaren Quellen nicht enthalten." when the sources
  do not cover the question. The evaluation set includes a **planted hallucination**
  (the 20%-vs-10% Mietpreisbremse misconception) so the RAGAs `faithfulness` metric
  actively guards against plausible-sounding but ungrounded answers, and a per-answer
  **groundedness badge** shows how many statutes/rulings back each response.
- **Data privacy.** Identity is derived server-side from the JWT on every request;
  memory, cases, feedback and chat history are namespaced by the authenticated user and
  case access is ownership-checked. There is no self-registration — accounts are
  provisioned by an admin. Uploaded documents are sanitised (OWASP LLM05) and capped
  before storage, and deleting a case cascades to its documents and deadlines. Untrusted
  text (retrieved snippets, uploaded files, user input) is wrapped in
  `<untrusted_context>` and treated as data, never instructions.
- **Bias, coverage & limitations.** The corpora are **not exhaustive**: the statutes
  cover BGB §§ 535–577, BetrKV and WoGG, and the case law is a filtered sample of Open
  Legal Data decisions — so some questions (especially newer or niche case-law topics)
  may have no matching ruling, which the assistant will say rather than guess. The
  system is specific to **German** rental law and reflects the language, jurisdiction
  and any selection bias of those sources. Retrieval quality is measured per corpus (the
  case-law retriever is the current weak spot and is tracked in the eval), and the
  linked sources let users catch model errors the metrics miss.
- **Human-in-the-loop for writes.** The agent can never create a deadline or save a
  draft on its own — those actions pause on a LangGraph `interrupt()` and only execute
  after the user explicitly approves.

## Development gate

```bash
uv run ruff check .   # lint
uv run mypy src       # type-check
uv run pytest         # run all tests (no Postgres/API keys required)
```

All tests run offline against pure functions, `InMemoryStore`/`InMemorySaver` fakes and
a monkeypatched agent graph — no live Postgres or OpenRouter calls.

---

## Fetching the statute corpus (optional)

Skip this if `data/laws/rag_documents.json` already exists.

```bash
uv run python fetch_legal_data.py
```

Runs five sequential phases against the Open Legal Data API:

| Phase | Function | Output |
|---|---|---|
| 1 | `resolve_book_ids` | Resolves bgb, betrkv, wogg book IDs via `/law_books/?slug=` |
| 2 | `fetch_all_norms` | Paginates all norms per book → `data/laws/{slug}_norms.json` |
| 3 | `enrich_norms` | Fetches full detail for BGB §535–§577, all BetrKV norms, and all WoGG norms; strips HTML → `bgb_mietrecht_norms_enriched.json` |
| 4 | `prepare_rag_documents` | Maps to LangChain Document schema → `rag_documents.json` |
| 5 | `validate_and_report` | Prints summary table, flags short docs → `data/retrieval_summary.txt` |

## API notes (`fetch_legal_data.py`)

- Base URL: `https://de.openlegaldata.io/api`
- Auth header: `api_key: <YOUR_KEY>` (not `Authorization: Token ...`)
- Law books endpoint: `/law_books/` (underscore — `/law-books/` returns 404)
- Norm list does **not** include content body — detail endpoint `GET /laws/{id}/` is required
- Rate limit: 5 000 requests/hour (authenticated)
- OpenRouter base URL for LLM + embeddings: `https://openrouter.ai/api/v1`

### Rate-limit behaviour

The pipeline inserts a `INTER_REQUEST_DELAY` (0.25 s) sleep before every individual
norm detail fetch to avoid bursting the rate limit in the first place.

If a 429 Too Many Requests response is received despite the delay, `api_get()` enters
an extended retry loop: up to `RATE_LIMIT_RETRIES` (8) attempts with backoff intervals
of 2, 4, 8, 16, 32, 60, 60, 60 seconds (controlled by `RATE_LIMIT_BACKOFF`).

If all 8 retries are exhausted and the server still returns 429, the pipeline aborts
with a `RuntimeError` — it **never** silently skips a norm due to a recoverable API
error. Re-run the script or increase `RATE_LIMIT_RETRIES` / `INTER_REQUEST_DELAY` in
`fetch_legal_data.py` if this happens.

> **Estimated run time:** roughly 10–20 minutes (INTER_REQUEST_DELAY adds ~0.25 s per detail request)
