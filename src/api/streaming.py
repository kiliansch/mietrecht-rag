"""Shared translation of agent-graph `stream()` updates into SSE frames.

Used by the chat turn, the case letter analysis, and the approval-resume endpoint so
the event protocol (`usage`, `tool_call`, `tool_result`, `source`, `final`, `done`,
`error`) stays identical on every streaming path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from src.api.sse import sse_event
from src.tools.retrieval_tools import parse_citations

logger = logging.getLogger(__name__)

_CITATION_TOOLS = ("search_law",)


def _error_event(exc: Exception) -> str:
    error_str = str(exc)
    if "429" in error_str or "rate limit" in error_str.lower():
        message = "API-Limit erreicht. Bitte warten Sie einen Moment und versuchen Sie es erneut."
    elif "timeout" in error_str.lower() or "connection" in error_str.lower():
        message = "Verbindungsfehler zum KI-Dienst. Bitte prüfen Sie Ihre Internetverbindung."
    else:
        # Don't leak internal exception text to the client; full detail is logged.
        message = "Unerwarteter Fehler bei der Verarbeitung. Bitte versuchen Sie es erneut."
    return sse_event("error", {"type": type(exc).__name__, "message": message})


def agent_sse_events(
    updates: Iterator[dict[str, Any]],
    *,
    on_final: Callable[[str], None] | None = None,
) -> Iterator[str]:
    """Map graph updates to SSE frames; ends with `done` (or `error`).

    `on_final` receives the final answer text (used to persist analysis results
    after the stream has been fully delivered).

    Approval interrupts (`langgraph.types.interrupt` inside a gated tool) surface as
    an `approval_required` event followed by `done {"paused": true}` — the HTTP
    stream ends while the thread stays parked in the checkpointer until
    `/api/chat/resume` continues it.
    """
    try:
        for update in updates:
            if "__interrupt__" in update:
                for it in update["__interrupt__"]:
                    payload = it.value if isinstance(it.value, dict) else {}
                    yield sse_event(
                        "approval_required",
                        {
                            "interrupt_id": it.id,
                            "action": payload.get("action", "unknown"),
                            "args": payload.get("args", {}),
                        },
                    )
                yield sse_event("done", {"paused": True})
                return
            for node_name, value in update.items():
                for msg in (value or {}).get("messages", []):
                    if node_name == "agent":
                        usage = getattr(msg, "usage_metadata", None) or {}
                        if usage:
                            yield sse_event(
                                "usage",
                                {
                                    "input_tokens": usage.get("input_tokens", 0),
                                    "output_tokens": usage.get("output_tokens", 0),
                                },
                            )
                        if getattr(msg, "tool_calls", None):
                            for tc in msg.tool_calls:
                                yield sse_event(
                                    "tool_call",
                                    {"id": tc["id"], "name": tc["name"], "args": tc["args"]},
                                )
                        else:
                            content = str(msg.content)
                            if on_final is not None:
                                on_final(content)
                            yield sse_event("final", {"content": content})
                    elif node_name == "tools":
                        yield sse_event(
                            "tool_result",
                            {
                                "id": getattr(msg, "tool_call_id", None),
                                "result": str(msg.content),
                            },
                        )
                        if getattr(msg, "name", "") in _CITATION_TOOLS:
                            for src in parse_citations(str(msg.content)):
                                yield sse_event("source", src)
                    elif node_name == "validate_input":
                        yield sse_event("final", {"content": str(msg.content)})
        yield sse_event("done", {})
    except Exception as exc:  # noqa: BLE001 — report any failure to the client as SSE
        logger.exception("Unhandled exception during agent stream")
        yield _error_event(exc)
