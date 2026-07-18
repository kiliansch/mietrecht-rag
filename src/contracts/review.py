"""Per-clause contract review: sanitise, call the agent, parse the verdict.

The agent is run in contract_review mode (Context.task = "contract_review"),
which uses build_contract_review_prompt and bypasses the chat input validator.
All clause text is treated as UNTRUSTED (OWASP LLM05).
"""

from __future__ import annotations

import re
from typing import TypedDict

from src.agent import graph as agent_graph
from src.agent.security import delimit, sanitise_text
from src.contracts.segment import Clause
from src.tools.retrieval_tools import parse_citations

_CONTRACT_SNIPPET_MAX = 4000  # chars fed to the agent per clause

_VERDICT_RE = re.compile(r"Bewertung:\s*(wirksam|bedenklich|unwirksam)", re.IGNORECASE)
_REASONING_RE = re.compile(r"Begründung:\s*(.+?)(?:\n§-Referenz:|\Z)", re.DOTALL | re.IGNORECASE)


class Finding(TypedDict):
    clause: Clause
    verdict: str  # "wirksam" | "bedenklich" | "unwirksam"
    reasoning: str
    sources: list[dict]


def _parse_verdict(answer: str) -> str:
    m = _VERDICT_RE.search(answer)
    return m.group(1).lower() if m else "bedenklich"


def _parse_reasoning(answer: str) -> str:
    m = _REASONING_RE.search(answer)
    return m.group(1).strip() if m else answer.strip()


def review_clause(
    clause: Clause,
    *,
    thread_id: str,
    user_name: str,
    role: str = "mieter",
) -> Finding:
    """Review a single clause. Sanitises + delimits the text, calls the agent."""
    sanitised = sanitise_text(clause["text"], max_chars=_CONTRACT_SNIPPET_MAX)
    delimited = delimit(sanitised, "contract_clause")
    heading_hint = f"Klausel: {clause['heading']}\n\n" if clause["heading"] else ""
    query = (
        f"{heading_hint}"
        f"Prüfe diese Vertragsklausel auf ihre Rechtswirksamkeit nach deutschem Mietrecht:\n\n"
        f"{delimited}"
    )
    answer, tool_outputs = agent_graph.review(
        query,
        thread_id=thread_id,
        user_name=user_name,
        role=role,
    )
    sources: list[dict] = []
    for output in tool_outputs:
        sources.extend(parse_citations(output))
    return Finding(
        clause=clause,
        verdict=_parse_verdict(answer),
        reasoning=_parse_reasoning(answer),
        sources=sources,
    )
