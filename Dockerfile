# Backend image: FastAPI + LangGraph agent, managed by uv.
# System deps: tesseract (German OCR) + poppler for scanned-contract parsing
# (src/contracts/parse.py), curl for the compose healthcheck.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-deu poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer-cache the dependency install: lockfile first, project code second.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# setup-db (idempotent, seeds admin) then single-worker uvicorn — the API keeps
# process-local state (rate limiter, contract sessions), never add --workers.
ENTRYPOINT ["./docker/entrypoint.sh"]
