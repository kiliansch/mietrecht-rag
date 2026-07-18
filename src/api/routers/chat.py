"""Chat: bootstrap config, fast input validation, and the streaming agent turn."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src import config
from src.agent import nodes
from src.agent.graph import resume_stream
from src.agent.graph import stream as agent_stream
from src.agent.prompts import ROLE_LABELS
from src.api.deps import CurrentUser, check_rate_limit, get_current_user
from src.api.schemas import ChatRequest, ResumeRequest, ValidateRequest, ValidateResponse
from src.api.sse import SSE_HEADERS
from src.api.streaming import agent_sse_events
from src.cases import store as cases_store
from src.chat_history import store as chat_history_store
from src.usage import make_usage_callback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/config")
def get_config() -> dict[str, Any]:
    """Everything the frontend needs to build selectors without hardcoding config."""
    return {
        "roles": [{"key": k, "label": v} for k, v in ROLE_LABELS.items()],
        "models": [{"value": v, "label": k} for k, v in config.LLM_CHOICES.items()],
        "pricing": config.MODEL_PRICING,
        "thresholds": config.THRESHOLDS,
        "rate_limit": {"requests": 5, "window_secs": 60},
        "max_upload_bytes": config.MAX_UPLOAD_BYTES,
    }


@router.post("/chat/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest) -> ValidateResponse:
    """Fast client-side precheck mirroring the graph's validate_input node."""
    return ValidateResponse(error=nodes.validation_error(req.text.strip()))


@router.post("/chat")
def chat(
    req: ChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream one agent turn as SSE. Rate-limited before streaming begins.

    With a `case_id`, the turn runs on the case's own persistent thread (the
    client-sent thread_id is ignored) after an ownership check.
    """
    check_rate_limit(user.username)

    case_id: str | None = None
    if req.case_id:
        case = cases_store.get_case(user.username, req.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Akte nicht gefunden.")
        thread_id = case["thread_id"]
        case_id = case["id"]
    elif req.thread_id:
        thread_id = req.thread_id
        # Free chat: never run on a thread another user already owns (the client
        # supplies the id and the checkpointer is keyed by it alone).
        if chat_history_store.claimed_by_other(user.username, thread_id):
            raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden.")
        # Index the thread under the user so it shows up in "Verlauf" and can be
        # reopened later (best-effort — never block the turn).
        try:
            chat_history_store.touch_thread(user.username, thread_id, req.message)
        except Exception:
            logger.exception("Failed to index chat thread")
    else:
        raise HTTPException(status_code=422, detail="thread_id oder case_id erforderlich.")

    usage_cb = make_usage_callback()
    updates = agent_stream(
        req.message,
        thread_id=thread_id,
        user_name=user.username,
        role=req.role or user.persona,
        model=req.model,
        enabled_tools=(),
        case_id=case_id,
        language="en" if req.language == "en" else "de",
        callbacks=[usage_cb],
    )
    return StreamingResponse(
        agent_sse_events(updates, usage_cb=usage_cb),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/chat/resume")
def chat_resume(
    req: ResumeRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Continue a thread parked on a tool-approval interrupt (approve/reject).

    The Context is not checkpointed, so it is re-derived here — from the token and
    the case row, never from the client. The continuation streams the same event
    protocol as `/api/chat` (and may pause again on another approval).
    """
    check_rate_limit(user.username)

    case_id: str | None = None
    if req.case_id:
        case = cases_store.get_case(user.username, req.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Akte nicht gefunden.")
        thread_id = case["thread_id"]
        case_id = case["id"]
    elif req.thread_id:
        thread_id = req.thread_id
        if chat_history_store.claimed_by_other(user.username, thread_id):
            raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden.")
    else:
        raise HTTPException(status_code=422, detail="thread_id oder case_id erforderlich.")

    # If the interrupted turn was a document analysis, persist the continuation's
    # final answer as that document's analysis (the analyse stream ended at the pause).
    on_final = None
    if case_id and req.document_id:
        doc = cases_store.get_document(case_id, req.document_id)
        if doc is not None:

            def persist_summary(text: str, doc_id: str = doc["id"]) -> None:
                try:
                    cases_store.set_document_analysis(doc_id, {"summary": text})
                except Exception:
                    logger.exception("Failed to persist analysis after resume")

            on_final = persist_summary

    usage_cb = make_usage_callback()
    updates = resume_stream(
        {req.interrupt_id: req.decision},
        thread_id=thread_id,
        user_name=user.username,
        role=user.persona,
        case_id=case_id,
        language="en" if req.language == "en" else "de",
        callbacks=[usage_cb],
    )
    return StreamingResponse(
        agent_sse_events(updates, on_final=on_final, usage_cb=usage_cb),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
