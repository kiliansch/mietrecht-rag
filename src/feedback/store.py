"""Persist user feedback (thumbs up/down + optional comment) to PostgresStore.

Feedback entries are stored under namespace ("feedback", user_name) so they are
per-user and queryable from the same Postgres instance used for memories.
"""

from __future__ import annotations

import datetime
import uuid

from langgraph.store.postgres import PostgresStore

from src.agent.graph import _get_pool


def write_feedback(
    *,
    thread_id: str,
    user_name: str,
    question: str,
    answer: str,
    rating: int,
    comment: str = "",
) -> None:
    """Write a feedback entry (rating: 1 = positive, -1 = negative) to PostgresStore."""
    pool = _get_pool()
    store = PostgresStore(pool)
    namespace = ("feedback", user_name or "anon")
    key = str(uuid.uuid4())
    value: dict = {
        "thread_id": thread_id,
        "question": question,
        "answer": answer,
        "rating": rating,
        "comment": comment,
        "ts": datetime.datetime.utcnow().isoformat(),
    }
    store.put(namespace, key, value)
