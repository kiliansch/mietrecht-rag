"""PersistentTraceCallback — writes one JSONL trace file per process run.

Each JSON line records one LangChain event (llm_start, llm_end,
retriever_start, retriever_end, chain_start, chain_end, or an error).
Files land in  data/traces/YYYY-MM-DD_HH-MM-SS_<run_id>.jsonl .
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

_TRACES_DIR = Path("data/traces")


class PersistentTraceCallback(BaseCallbackHandler):
    """Appends structured JSON lines to a local trace file."""

    def __init__(self, traces_dir: Path = _TRACES_DIR) -> None:
        super().__init__()
        traces_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        run_id = uuid.uuid4().hex[:8]
        self._path = traces_dir / f"{ts}_{run_id}.jsonl"
        # Track start times keyed by run_id string for latency calculation
        self._start_times: dict[str, float] = {}
        logger.info("PersistentTraceCallback: tracing to %s", self._path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, event: dict[str, Any]) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("PersistentTraceCallback: write failed: %s", exc)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _run_key(run_id: uuid.UUID | None) -> str:
        return str(run_id) if run_id else ""

    # ------------------------------------------------------------------
    # LLM events
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times[key] = time.monotonic()
        model_name = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("name", "unknown")
        )
        self._write(
            {
                "event": "llm_start",
                "timestamp": self._now(),
                "run_id": key,
                "model": model_name,
                "prompt_chars": sum(len(p) for p in prompts),
                "prompts": prompts,
            }
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        latency_ms = round((time.monotonic() - self._start_times.pop(key, time.monotonic())) * 1000)
        token_usage: dict[str, Any] = {}
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})

        texts = [
            gen.text
            for gens in response.generations
            for gen in gens
        ]
        self._write(
            {
                "event": "llm_end",
                "timestamp": self._now(),
                "run_id": key,
                "latency_ms": latency_ms,
                "token_usage": token_usage,
                "response_chars": sum(len(t) for t in texts),
                "responses": texts,
            }
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times.pop(key, None)
        self._write(
            {
                "event": "llm_error",
                "timestamp": self._now(),
                "run_id": key,
                "error": str(error),
            }
        )

    # ------------------------------------------------------------------
    # Retriever events
    # ------------------------------------------------------------------

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times[key] = time.monotonic()
        self._write(
            {
                "event": "retriever_start",
                "timestamp": self._now(),
                "run_id": key,
                "query": query,
            }
        )

    def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        latency_ms = round((time.monotonic() - self._start_times.pop(key, time.monotonic())) * 1000)
        doc_summaries = [
            {
                "section": d.metadata.get("section", ""),
                "absatz": d.metadata.get("absatz", ""),
                "title": d.metadata.get("title", ""),
                "chars": len(d.page_content),
            }
            for d in documents
        ]
        self._write(
            {
                "event": "retriever_end",
                "timestamp": self._now(),
                "run_id": key,
                "latency_ms": latency_ms,
                "doc_count": len(documents),
                "docs": doc_summaries,
            }
        )

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times.pop(key, None)
        self._write(
            {
                "event": "retriever_error",
                "timestamp": self._now(),
                "run_id": key,
                "error": str(error),
            }
        )

    # ------------------------------------------------------------------
    # Chain events
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times[key] = time.monotonic()
        chain_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1]
        self._write(
            {
                "event": "chain_start",
                "timestamp": self._now(),
                "run_id": key,
                "chain": chain_name,
                "input_keys": list(inputs.keys()) if isinstance(inputs, dict) else [],
            }
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        latency_ms = round((time.monotonic() - self._start_times.pop(key, time.monotonic())) * 1000)
        self._write(
            {
                "event": "chain_end",
                "timestamp": self._now(),
                "run_id": key,
                "latency_ms": latency_ms,
                "output_keys": list(outputs.keys()) if isinstance(outputs, dict) else [],
            }
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = self._run_key(run_id)
        self._start_times.pop(key, None)
        self._write(
            {
                "event": "chain_error",
                "timestamp": self._now(),
                "run_id": key,
                "error": str(error),
            }
        )
