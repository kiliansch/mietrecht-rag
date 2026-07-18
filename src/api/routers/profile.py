"""Profile (the "Mein Mietfall" panel data) and feedback writes."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from src.agent.graph import get_store
from src.api.deps import CurrentUser, get_current_user
from src.api.schemas import FeedbackRequest
from src.feedback.store import write_feedback
from src.memory import store as memory_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile")
def get_profile(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, Any]:
    """Role and tenancy facts (+ provenance). Contracts now live inside cases."""
    store = get_store()
    profile = memory_store.get_profile_data(store, user.username)
    return {
        "role": profile.get("role"),
        "facts": profile.get("facts", {}),
        "facts_source": profile.get("facts_source", {}),
    }


@router.post("/feedback", status_code=204)
def feedback(
    req: FeedbackRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    """Persist a thumbs up/down (+ optional comment) for an assistant answer."""
    try:
        write_feedback(
            thread_id=req.thread_id,
            user_name=user.username,
            question=req.question,
            answer=req.answer,
            rating=req.rating,
            comment=req.comment,
        )
    except Exception:
        logger.exception("Failed to write feedback")
    return Response(status_code=204)
