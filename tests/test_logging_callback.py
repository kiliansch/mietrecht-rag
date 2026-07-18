"""Unit tests for PersistentTraceCallback."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


from src.logging.callbacks import PersistentTraceCallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cb(tmp_path: Path) -> PersistentTraceCallback:
    return PersistentTraceCallback(traces_dir=tmp_path)


def _read_events(cb: PersistentTraceCallback) -> list[dict]:
    return [json.loads(line) for line in cb._path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPersistentTraceCallback:
    def test_file_created_on_init(self, tmp_path: Path) -> None:
        cb = _make_cb(tmp_path)
        # File is created lazily on first write; directory must exist
        assert cb._path.parent.exists()

    def test_llm_start_writes_event(self, tmp_path: Path) -> None:
        cb = _make_cb(tmp_path)
        run_id = uuid.uuid4()
        cb.on_llm_start(
            serialized={"name": "ChatOpenAI", "kwargs": {"model_name": "test-model"}},
            prompts=["Hello, world!"],
            run_id=run_id,
        )
        events = _read_events(cb)
        assert len(events) == 1
        e = events[0]
        assert e["event"] == "llm_start"
        assert e["model"] == "test-model"
        assert e["prompt_chars"] == len("Hello, world!")
        assert e["run_id"] == str(run_id)

    def test_llm_end_writes_event_with_latency(self, tmp_path: Path) -> None:
        from langchain_core.outputs import ChatGeneration, LLMResult

        cb = _make_cb(tmp_path)
        run_id = uuid.uuid4()
        cb.on_llm_start(
            serialized={"name": "ChatOpenAI", "kwargs": {"model_name": "test-model"}},
            prompts=["Prompt"],
            run_id=run_id,
        )

        from langchain_core.messages import AIMessage

        result = LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="Answer"))]],
            llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 3}},
        )
        cb.on_llm_end(result, run_id=run_id)

        events = _read_events(cb)
        assert len(events) == 2
        end_event = events[1]
        assert end_event["event"] == "llm_end"
        assert "latency_ms" in end_event
        assert isinstance(end_event["latency_ms"], int)
        assert end_event["token_usage"]["prompt_tokens"] == 5

    def test_retriever_start_and_end(self, tmp_path: Path) -> None:
        from langchain_core.documents import Document

        cb = _make_cb(tmp_path)
        run_id = uuid.uuid4()
        cb.on_retriever_start(
            serialized={"name": "Chroma"},
            query="Mieterhöhung §558",
            run_id=run_id,
        )
        docs = [
            Document(
                page_content="§558 BGB ...",
                metadata={"section": "§558", "absatz": "(1)", "title": "Mieterhöhung"},
            )
        ]
        cb.on_retriever_end(docs, run_id=run_id)

        events = _read_events(cb)
        assert len(events) == 2
        start = events[0]
        assert start["event"] == "retriever_start"
        assert start["query"] == "Mieterhöhung §558"

        end = events[1]
        assert end["event"] == "retriever_end"
        assert end["doc_count"] == 1
        assert end["docs"][0]["section"] == "§558"
        assert "latency_ms" in end

    def test_chain_start_and_end(self, tmp_path: Path) -> None:
        cb = _make_cb(tmp_path)
        run_id = uuid.uuid4()
        cb.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={"question": "Was ist eine Mietkaution?"},
            run_id=run_id,
        )
        cb.on_chain_end(outputs={"output": "Antwort..."}, run_id=run_id)

        events = _read_events(cb)
        assert len(events) == 2
        assert events[0]["event"] == "chain_start"
        assert events[0]["chain"] == "RunnableSequence"
        assert events[1]["event"] == "chain_end"
        assert "latency_ms" in events[1]

    def test_error_events_are_written(self, tmp_path: Path) -> None:
        cb = _make_cb(tmp_path)
        run_id = uuid.uuid4()
        cb.on_llm_error(ValueError("timeout"), run_id=run_id)
        cb.on_retriever_error(RuntimeError("chroma down"), run_id=run_id)

        events = _read_events(cb)
        assert events[0]["event"] == "llm_error"
        assert "timeout" in events[0]["error"]
        assert events[1]["event"] == "retriever_error"

    def test_multiple_runs_share_one_file(self, tmp_path: Path) -> None:
        cb = _make_cb(tmp_path)
        for _ in range(3):
            run_id = uuid.uuid4()
            cb.on_retriever_start(serialized={}, query="q", run_id=run_id)
            cb.on_retriever_end([], run_id=run_id)

        events = _read_events(cb)
        assert len(events) == 6  # 3 start + 3 end

    def test_each_instance_gets_unique_file(self, tmp_path: Path) -> None:
        import time
        cb1 = _make_cb(tmp_path)
        time.sleep(0.01)  # ensure different timestamp in filename
        cb2 = _make_cb(tmp_path)
        assert cb1._path != cb2._path
