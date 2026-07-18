"""Saved free-chat conversations ("Verlauf"): list, reopen, rename, delete.

Every route resolves ownership through `chat_store.owns_thread(username, thread_id)`
(or a user-scoped query) before touching a thread.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from src.agent.graph import get_thread_messages
from src.api.deps import CurrentUser, get_current_user
from src.api.schemas import ChatRenameRequest
from src.chat_history import store as chat_store

router = APIRouter(prefix="/api/chats", tags=["chat-history"])


@router.get("")
def chats_list(user: Annotated[CurrentUser, Depends(get_current_user)]) -> list[dict[str, Any]]:
    return chat_store.list_threads(user.username)


@router.get("/{thread_id}/messages")
def chat_messages(
    thread_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    """The reconstructed user/assistant turns of a saved thread (with citations)."""
    if not chat_store.owns_thread(user.username, thread_id):
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden.")
    return get_thread_messages(thread_id)


@router.patch("/{thread_id}")
def chat_rename(
    thread_id: str,
    req: ChatRenameRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    if not req.title.strip():
        raise HTTPException(status_code=422, detail="Titel darf nicht leer sein.")
    if not chat_store.rename_thread(user.username, thread_id, req.title):
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden.")
    return {"thread_id": thread_id, "title": req.title.strip()}


@router.delete("/{thread_id}", status_code=204)
def chat_delete(
    thread_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    if not chat_store.delete_thread(user.username, thread_id):
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden.")
    return Response(status_code=204)
