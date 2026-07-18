"""Hand-built LangGraph `StateGraph` for the Mietrecht agent (ReAct loop).

Nodes: `validate_input` -> `load_memory` -> `agent` <-> `tools` -> `write_memory`.
Compiled with `PostgresSaver` (short-term, per-`thread_id` checkpoints) and
`PostgresStore` (long-term, per-`user_name` memory), backed by a single shared
connection pool.

`run(...)` is the single entrypoint used identically by the CLI and the UI, so the
role-aware system prompt (`src.agent.prompts.build_system_prompt`) is applied on
every path.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import psycopg
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.postgres import PostgresStore
from langgraph.types import Command
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from src import config
from src.agent import nodes
from src.agent.state import AgentState, Context
from src.tools import ALL_TOOLS
from src.tools.retrieval_tools import parse_citations

# Bounds the agent <-> tools loop (validate_input/load_memory/write_memory each add 1).
RECURSION_LIMIT = 25

_pool: ConnectionPool[psycopg.Connection[DictRow]] | None = None
_graph: CompiledStateGraph[AgentState, Context, AgentState, AgentState] | None = None


def _get_pool() -> ConnectionPool[psycopg.Connection[DictRow]]:
    """Return the shared connection pool, created lazily on first use."""
    global _pool
    if _pool is None:
        _pool = cast(
            "ConnectionPool[psycopg.Connection[DictRow]]",
            ConnectionPool(
                config.DATABASE_URL,
                min_size=1,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            ),
        )
    return _pool


def close_pool() -> None:
    """Close the shared connection pool (and drop the cached graph).

    Wired into the FastAPI shutdown so the server releases DB connections cleanly;
    the CLI relies on process exit. Idempotent."""
    global _pool, _graph
    if _pool is not None:
        _pool.close()
        _pool = None
    _graph = None


def get_store() -> PostgresStore:
    """Return a `PostgresStore` on the shared pool for direct long-term reads/writes.

    Lets callers outside a graph run (e.g. the UI status panel and contract
    persistence) use the same store the graph nodes do. `store.setup()` already ran
    in `setup_db`, so no schema work happens here.
    """
    return PostgresStore(_get_pool())


def _route_after_validation(state: AgentState) -> str:
    return "load_memory" if state.get("input_valid", True) else END


def build_graph() -> CompiledStateGraph[AgentState, Context, AgentState, AgentState]:
    """Build and compile the agent graph with Postgres-backed checkpointer + store.

    Compiled once and cached: the graph is stateless per run (conversation state
    lives in the checkpointer, identity in the per-invoke `Context`), so every
    `run`/`stream`/`resume`/`review` call reuses the same compiled instance.
    """
    global _graph
    if _graph is not None:
        return _graph
    pool = _get_pool()
    saver = PostgresSaver(pool)
    store = PostgresStore(pool)

    graph = StateGraph(AgentState, context_schema=Context)
    graph.add_node("validate_input", nodes.validate_input)
    graph.add_node("load_memory", nodes.load_memory)
    graph.add_node("agent", nodes.call_model)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_node("write_memory", nodes.write_memory)

    graph.add_edge(START, "validate_input")
    graph.add_conditional_edges(
        "validate_input", _route_after_validation, {"load_memory": "load_memory", END: END}
    )
    graph.add_edge("load_memory", "agent")
    graph.add_conditional_edges(
        "agent", tools_condition, {"tools": "tools", "__end__": "write_memory"}
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("write_memory", END)

    _graph = graph.compile(checkpointer=saver, store=store)
    return _graph


def run(
    user_input: str,
    *,
    thread_id: str,
    user_name: str,
    role: str = "mieter",
    model: str = config.LLM_MAIN,
    temperature: float = config.DEFAULT_TEMPERATURE,
    top_p: float | None = config.DEFAULT_TOP_P,
    enabled_tools: tuple[str, ...] = (),
    case_id: str | None = None,
    language: str = "de",
) -> str:
    """Run one turn of the agent and return the final answer text."""
    graph = build_graph()
    result = graph.invoke(
        {"messages": [HumanMessage(content=user_input)]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT},
        context=Context(
            user_name=user_name,
            role=role,
            task="chat",
            model=model,
            temperature=temperature,
            top_p=top_p,
            enabled_tools=enabled_tools,
            case_id=case_id,
            language=language,
        ),
    )
    return str(result["messages"][-1].content)


def stream(
    user_input: str,
    *,
    thread_id: str,
    user_name: str,
    role: str = "mieter",
    model: str = config.LLM_MAIN,
    temperature: float = config.DEFAULT_TEMPERATURE,
    top_p: float | None = config.DEFAULT_TOP_P,
    enabled_tools: tuple[str, ...] = (),
    case_id: str | None = None,
    task: str = "chat",
    language: str = "de",
    callbacks: list[Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream per-node state updates for one turn (`stream_mode="updates"`).

    Each yielded item is `{node_name: state_update}`, e.g. `{"agent": {"messages":
    [AIMessage(...)]}}` or `{"tools": {"messages": [ToolMessage(...), ...]}}`. Used by
    the UI to render intermediate tool calls/results and the final answer without any
    prompt-building or tool-loop logic of its own.

    `callbacks`, when given, are attached to the run so LLM usage from the agent AND its
    tools (e.g. multi-query expansion) is captured, not just the agent node's message.
    """
    graph = build_graph()
    yield from graph.stream(
        {"messages": [HumanMessage(content=user_input)]},
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": callbacks or [],
        },
        context=Context(
            user_name=user_name,
            role=role,
            task=task,
            model=model,
            temperature=temperature,
            top_p=top_p,
            enabled_tools=enabled_tools,
            case_id=case_id,
            language=language,
        ),
        stream_mode="updates",
    )


def resume_stream(
    resume_map: dict[str, Any],
    *,
    thread_id: str,
    user_name: str,
    role: str = "mieter",
    model: str = config.LLM_MAIN,
    temperature: float = config.DEFAULT_TEMPERATURE,
    top_p: float | None = config.DEFAULT_TOP_P,
    enabled_tools: tuple[str, ...] = (),
    case_id: str | None = None,
    task: str = "chat",
    language: str = "de",
    callbacks: list[Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Resume an interrupted thread with `{interrupt_id: "approve" | "reject"}`.

    Identical to `stream()` except the input is `Command(resume=...)`. The Context
    is NOT checkpointed, so the caller must re-pass it — derived server-side from
    auth + the case row, never from the client (incl. `language`, else the
    continuation answer would revert to the German default).
    """
    graph = build_graph()
    yield from graph.stream(
        Command(resume=resume_map),
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": callbacks or [],
        },
        context=Context(
            user_name=user_name,
            role=role,
            task=task,
            model=model,
            temperature=temperature,
            top_p=top_p,
            enabled_tools=enabled_tools,
            case_id=case_id,
            language=language,
        ),
        stream_mode="updates",
    )


def get_thread_messages(thread_id: str) -> list[dict[str, Any]]:
    """Reconstruct a thread's user/assistant turns (with citations) from the
    checkpointer, for the saved-chat reload view.

    Intermediate tool-call steps are collapsed: a `search_law` result's citations
    attach to the assistant answer that follows it. Returns `[]` for an unknown thread.
    """
    graph = build_graph()
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    messages = (snapshot.values or {}).get("messages", []) if snapshot else []

    out: list[dict[str, Any]] = []
    pending_sources: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": str(msg.content), "sources": []})
            pending_sources = []
        elif isinstance(msg, ToolMessage):
            if getattr(msg, "name", "") == "search_law":
                pending_sources.extend(parse_citations(str(msg.content)))
        elif isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                continue  # intermediate tool-call step, not a final answer
            out.append(
                {"role": "assistant", "content": str(msg.content), "sources": pending_sources}
            )
            pending_sources = []
    return out


def review(
    clause_text: str,
    *,
    thread_id: str,
    user_name: str,
    role: str = "mieter",
    callbacks: list[Any] | None = None,
) -> tuple[str, list[str]]:
    """Run a contract-clause review. Returns (final_answer, tool_output_strings).

    tool_output_strings are the raw search_law outputs, used by the caller to
    extract citations via parse_citations. `callbacks`, when given, capture the
    clause's LLM usage (agent + tools).
    """
    graph = build_graph()
    final_answer = ""
    tool_outputs: list[str] = []
    for update in graph.stream(
        {"messages": [HumanMessage(content=clause_text)]},
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": callbacks or [],
        },
        context=Context(
            user_name=user_name,
            role=role,
            task="contract_review",
            model=config.LLM_MAIN,
            temperature=0.0,
        ),
        stream_mode="updates",
    ):
        for node_name, value in update.items():
            for msg in (value or {}).get("messages", []):
                if node_name == "agent" and not getattr(msg, "tool_calls", None):
                    final_answer = str(msg.content)
                elif node_name == "tools":
                    if getattr(msg, "name", "") == "search_law":
                        tool_outputs.append(str(msg.content))
    return final_answer, tool_outputs
