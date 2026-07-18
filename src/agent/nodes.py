"""The five nodes of the agent's hand-built `StateGraph` ReAct loop.

`validate_input` -> `load_memory` -> `agent` <-> `tools` -> `write_memory`

`agent` (`call_model`) and `tools` (a `ToolNode`) form the ReAct loop; `tools`
loops back to `agent` until the model returns a final (non-tool-call) answer.
"""

from __future__ import annotations

import os
import re

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime

from src import config
from src.agent.prompts import build_contract_review_prompt, build_system_prompt
from src.agent.state import AgentState, Context
from src.cases import store as cases_store
from src.memory import store as memory_store
from src.tools import ALL_TOOLS

_MIN_WORDS = 2
_EXAMPLE_QUESTIONS = (
    "z. B. *Wie hoch darf meine Kaution sein?* oder "
    "*Was sind die Pflichten des Vermieters nach §535 BGB?*"
)
# A bare arithmetic expression (digits/operators only, no letters).
_ARITHMETIC_RE = re.compile(r"[\d\s.,€%+\-*/=()]+")

_llm_cache: dict[tuple, Runnable] = {}


def _get_llm(
    model: str,
    temperature: float,
    top_p: float | None,
    enabled_tools: tuple[str, ...],
) -> Runnable:
    key = (model, temperature, top_p, enabled_tools)
    if key not in _llm_cache:
        extra: dict = {}
        if top_p is not None:
            extra["top_p"] = top_p
        llm = init_chat_model(
            model,
            model_provider="openai",
            base_url=config.LLM_BASE_URL,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            temperature=temperature,
            **extra,
        )
        tool_map = {t.name: t for t in ALL_TOOLS}
        active_tools = (
            [tool_map[n] for n in enabled_tools if n in tool_map]
            if enabled_tools
            else list(ALL_TOOLS)
        )
        _llm_cache[key] = llm.bind_tools(active_tools)
    return _llm_cache[key]


def validation_error(text: str) -> str | None:
    """Return a German error string if `text` fails basic domain validation, else None.

    Shared by the `validate_input` node and the UI's fast client-side pre-check.
    """
    if len(text.split()) < _MIN_WORDS:
        return (
            f"Bitte formulieren Sie Ihre Frage mit mindestens {_MIN_WORDS} Wörtern. "
            f"{_EXAMPLE_QUESTIONS}"
        )
    if not any(c.isalpha() for c in text):
        return (
            f"Bitte stellen Sie eine Frage in verständlicher Sprache. "
            f"{_EXAMPLE_QUESTIONS}"
        )
    if _ARITHMETIC_RE.fullmatch(text):
        return (
            f"Bitte stellen Sie eine konkrete Mietrechtsfrage, keine reine Rechenaufgabe. "
            f"{_EXAMPLE_QUESTIONS}"
        )
    return None


def validate_input(state: AgentState, runtime: Runtime[Context]) -> dict:
    """Entry node: only plain chat input is validated; internal tasks
    (contract_review, letter_analysis) carry server-built messages and always pass."""
    if runtime.context.task != "chat":
        return {"input_valid": True}
    last_message = state["messages"][-1]
    text = str(last_message.content)
    error = validation_error(text)
    if error:
        return {"messages": [AIMessage(content=error)], "input_valid": False}
    return {"input_valid": True}


def load_memory(state: AgentState, runtime: Runtime[Context]) -> dict:
    """Read long-term facts (+ the active case summary) into `memory_block`."""
    assert runtime.store is not None
    ctx = runtime.context
    block = memory_store.load_memory(runtime.store, ctx.user_name)
    if ctx.case_id:
        case_block = cases_store.case_context_block(ctx.user_name, ctx.case_id)
        if case_block:
            block = f"{block}\n\n{case_block}" if block else case_block
    return {"memory_block": block}


def call_model(state: AgentState, runtime: Runtime[Context]) -> dict:
    """Invoke the LLM (with context-controlled tools/model) with the appropriate system prompt."""
    ctx = runtime.context
    if ctx.task == "contract_review":
        system_prompt = build_contract_review_prompt(ctx.role)
    else:
        system_prompt = build_system_prompt(
            ctx.role,
            state.get("memory_block", ""),
            case_mode=ctx.case_id is not None,
            language=ctx.language,
        )
    messages = [SystemMessage(content=system_prompt), *state["messages"]]
    llm = _get_llm(ctx.model, ctx.temperature, ctx.top_p, ctx.enabled_tools)
    response = llm.invoke(messages)
    return {"messages": [response]}


def write_memory(state: AgentState, runtime: Runtime[Context]) -> dict:
    """After a final answer, upsert the active role and tool-call args for the user."""
    assert runtime.store is not None
    memory_store.write_memory(
        runtime.store, runtime.context.user_name, runtime.context.role, list(state["messages"])
    )
    return {}
