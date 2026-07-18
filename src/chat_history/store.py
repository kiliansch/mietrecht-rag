"""Chat-thread index persistence (the "Verlauf" list).

Real SQL table (`chat_threads`, created in `src.db.setup_db`) giving each user a
named, listable index of their free-chat threads. The messages themselves live in
the LangGraph checkpointer keyed by `thread_id`; this module only tracks
title/ordering. `_owned(username, thread_id)` is the ownership gate for the API.
"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor

from src.db import get_connection

# Chat titles are derived from the first user message; keep them short.
_TITLE_MAX_CHARS = 80


def _rows_to_dicts(cur: Cursor[Any]) -> list[dict[str, Any]]:
    assert cur.description is not None
    keys = [c.name for c in cur.description]
    return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def _derive_title(first_message: str) -> str:
    title = " ".join(first_message.split()).strip()
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rstrip() + "…"
    return title or "Neue Unterhaltung"


def touch_thread(username: str, thread_id: str, first_message: str) -> None:
    """Upsert the thread for `username`: create it (title from the first message) or
    just bump `updated_at`. Silently no-ops if the user is unknown."""
    with get_connection() as conn:
        conn.autocommit = True
        conn.execute(
            "INSERT INTO chat_threads (user_id, thread_id, title) "
            "SELECT id, %s, %s FROM users WHERE username = %s "
            "ON CONFLICT (user_id, thread_id) DO UPDATE SET updated_at = now()",
            (thread_id, _derive_title(first_message), username),
        )


def list_threads(username: str) -> list[dict[str, Any]]:
    """The user's saved chats, most-recently-updated first."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT t.thread_id::text AS thread_id, t.title, "
            "t.created_at::text AS created_at, t.updated_at::text AS updated_at "
            "FROM chat_threads t JOIN users u ON u.id = t.user_id "
            "WHERE u.username = %s ORDER BY t.updated_at DESC",
            (username,),
        )
        return _rows_to_dicts(cur)


def owns_thread(username: str, thread_id: str) -> bool:
    """Ownership gate: True iff `thread_id` belongs to `username`."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM chat_threads t JOIN users u ON u.id = t.user_id "
            "WHERE t.thread_id = %s AND u.username = %s",
            (thread_id, username),
        )
        return cur.fetchone() is not None


def claimed_by_other(username: str, thread_id: str) -> bool:
    """True iff `thread_id` is already indexed by a DIFFERENT user.

    Guards the free-chat path: `thread_id` is a client-supplied UUID and the
    checkpointer is keyed by it alone, so without this check a user could adopt
    another user's thread (`touch_thread`) and read its history. A thread nobody
    has claimed yet is fair game (empty conversation)."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM chat_threads t JOIN users u ON u.id = t.user_id "
            "WHERE t.thread_id = %s AND u.username <> %s",
            (thread_id, username),
        )
        return cur.fetchone() is not None


def rename_thread(username: str, thread_id: str, title: str) -> bool:
    """Rename a thread. Returns False on miss/foreign thread."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "UPDATE chat_threads t SET title = %s FROM users u "
            "WHERE t.user_id = u.id AND t.thread_id = %s AND u.username = %s",
            (_derive_title(title), thread_id, username),
        )
        return cur.rowcount > 0


def delete_thread(username: str, thread_id: str) -> bool:
    """Delete a thread from the index. Returns False on miss/foreign thread.

    The checkpointer's messages for the thread are left in place (harmless and
    orphaned); only the user-visible index entry is removed.
    """
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "DELETE FROM chat_threads t USING users u "
            "WHERE t.user_id = u.id AND t.thread_id = %s AND u.username = %s",
            (thread_id, username),
        )
        return cur.rowcount > 0
