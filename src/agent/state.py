"""Graph state and runtime context for the Mietrecht agent.

`AgentState` extends `MessagesState` with fields written by individual nodes.
New fields are `NotRequired` (with nodes defaulting via `.get(...)`) so older
checkpoints without these keys remain loadable.

`Context` carries per-invocation identity/role through `graph.invoke(..., context=...)`
rather than through state. `user_name` is the authenticated username (derived
server-side from the JWT; the CLI passes it directly) and is the long-term-memory
namespace key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NotRequired

from langgraph.graph import MessagesState

from src import config


class AgentState(MessagesState):
    """Conversation state. `messages` comes from `MessagesState`."""

    input_valid: NotRequired[bool]
    memory_block: NotRequired[str]


@dataclass
class Context:
    """Per-invocation identity/role, passed via `graph.invoke(..., context=...)`.

    NOTE: context is NOT checkpointed — resuming an interrupted thread must re-pass
    the full Context, derived server-side (auth + case row), never from the client.
    """

    user_name: str = "anon"
    role: str = "mieter"
    task: str = "chat"  # "chat" | "contract_review" | "letter_analysis"
    model: str = field(default_factory=lambda: config.LLM_MAIN)
    temperature: float = field(default_factory=lambda: config.DEFAULT_TEMPERATURE)
    top_p: float | None = field(default_factory=lambda: config.DEFAULT_TOP_P)
    enabled_tools: tuple[str, ...] = ()
    # The active case ("Akte"); scopes the case tools and the prompt context block.
    case_id: str | None = None
    # Answer language ("de" | "en"). Retrieval stays German (the corpora are German);
    # only the generated answer is localised via the system prompt.
    language: str = "de"
