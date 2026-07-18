#!/bin/sh
# Backend container entrypoint: idempotent schema setup (also seeds the admin
# account from ADMIN_USERNAME/ADMIN_PASSWORD), then the API server. Runs before
# uvicorn starts, so schema work never happens in the request path.
set -e

uv run python main.py setup-db
exec uv run python main.py serve --host 0.0.0.0 --port 8000
