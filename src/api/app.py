"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import config
from src.agent.graph import close_pool
from src.api.routers import admin, auth, cases, chat, chat_history, profile, sources


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Release the shared DB connection pool on shutdown."""
    yield
    close_pool()


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS + the feature routers."""
    app = FastAPI(title="Mietrecht-Assistent API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(chat_history.router)
    app.include_router(cases.router)
    app.include_router(profile.router)
    app.include_router(sources.router)
    app.include_router(admin.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
