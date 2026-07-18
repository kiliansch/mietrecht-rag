"""HITL case-tool tests: interrupt → approve/reject via a minimal in-memory graph.

Follows the documented langgraph test recipe: a StateGraph containing just a
ToolNode + InMemorySaver, driven by an AIMessage with a pending tool call. The
first invoke parks on `__interrupt__`; `Command(resume={id: decision})` re-enters
the tools node where `interrupt()` returns the decision.
"""

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from src.agent.state import Context
from src.tools import ALL_TOOLS, APPROVAL_TOOLS, create_deadline, save_draft


def _graph():
    g = StateGraph(MessagesState, context_schema=Context)
    g.add_node("tools", ToolNode([create_deadline, save_draft]))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile(checkpointer=InMemorySaver())


def _invoke_tool(name: str, args: dict[str, Any], decision: str, case_id: str | None = "c1") -> str:
    """Run one gated tool through interrupt + resume; return the ToolMessage text."""
    graph = _graph()
    config = {"configurable": {"thread_id": "t1"}}
    ctx = Context(user_name="casey", case_id=case_id)
    ai = AIMessage(content="", tool_calls=[{"id": "tc1", "name": name, "args": args}])

    first = graph.invoke({"messages": [ai]}, config=config, context=ctx)
    assert "__interrupt__" in first
    (it,) = first["__interrupt__"]
    assert it.value["action"] == name
    # Payload args carry everything the caller sent (plus tool-arg defaults).
    assert args.items() <= it.value["args"].items()

    result = graph.invoke(Command(resume={it.id: decision}), config=config, context=ctx)
    return str(result["messages"][-1].content)


def test_approval_tools_are_registered() -> None:
    names = {t.name for t in ALL_TOOLS}
    assert APPROVAL_TOOLS <= names
    assert APPROVAL_TOOLS == {"create_deadline", "save_draft"}


def test_create_deadline_approved_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    written: dict[str, Any] = {}

    def fake_add(case_id: str, **kw: Any) -> dict[str, Any]:
        written.update({"case_id": case_id, **kw})
        return {"id": "f1"}

    monkeypatch.setattr("src.cases.store.add_deadline", fake_add)
    out = _invoke_tool(
        "create_deadline",
        {"title": "Widerspruch", "due_date": "2026-08-15", "note": "aus Schreiben"},
        "approve",
    )
    assert "Widerspruch" in out and "2026-08-15" in out
    assert written == {
        "case_id": "c1",
        "title": "Widerspruch",
        "due_date": "2026-08-15",
        "note": "aus Schreiben",
        "created_by": "agent",
    }


def test_create_deadline_rejected_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("must not write on reject")

    monkeypatch.setattr("src.cases.store.add_deadline", boom)
    out = _invoke_tool(
        "create_deadline", {"title": "Widerspruch", "due_date": "2026-08-15"}, "reject"
    )
    assert "abgelehnt" in out


def test_create_deadline_invalid_date_after_approve(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("must not write an invalid date")

    monkeypatch.setattr("src.cases.store.add_deadline", boom)
    out = _invoke_tool(
        "create_deadline", {"title": "Widerspruch", "due_date": "15.08.2026"}, "approve"
    )
    assert "Ungültiges Datum" in out


def test_create_deadline_inert_without_case(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("must not write without a case")

    monkeypatch.setattr("src.cases.store.add_deadline", boom)
    out = _invoke_tool(
        "create_deadline", {"title": "X", "due_date": "2026-08-15"}, "approve", case_id=None
    )
    assert "Keine Akte aktiv" in out


def test_save_draft_approved_writes_document(monkeypatch: pytest.MonkeyPatch) -> None:
    written: dict[str, Any] = {}

    def fake_add(case_id: str, **kw: Any) -> dict[str, Any]:
        written.update({"case_id": case_id, **kw})
        return {"id": "d1"}

    monkeypatch.setattr("src.cases.store.add_document", fake_add)
    out = _invoke_tool(
        "save_draft", {"title": "Widerspruch NK-Abrechnung", "content": "Sehr geehrte …"}, "approve"
    )
    assert "gespeichert" in out
    assert written == {
        "case_id": "c1",
        "kind": "draft",
        "title": "Widerspruch NK-Abrechnung",
        "content": "Sehr geehrte …",
    }
