"""Logging package: persistent per-session trace callbacks."""

from __future__ import annotations

from src.logging.callbacks import PersistentTraceCallback

_callback_singleton: PersistentTraceCallback | None = None


def get_trace_callback() -> PersistentTraceCallback:
    """Return the process-level singleton PersistentTraceCallback.

    The file is created on first access and reused for the lifetime of the
    process, so all chains and LLM calls within one run share one JSONL file.
    """
    global _callback_singleton
    if _callback_singleton is None:
        _callback_singleton = PersistentTraceCallback()
    return _callback_singleton
