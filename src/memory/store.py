"""Long-term, cross-thread memory backed by `PostgresStore`.

Namespace `("memories", user_name)`, stable keys `profile`, `tenancy_facts`,
`preferences`. Plain namespaced key lookup — no embeddings/semantic search, since the
fact set this assistant needs is small and structured (see
docs/mietrecht_agentic_rewrite_spec.md <memory>).

`write_memory` is a deterministic extractor: it records the active role and any
calculator tool-call arguments the user supplied in the latest exchange. No LLM
extraction is used.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.store.base import BaseStore

from src.agent.security import sanitise_text

_NAMESPACE = "memories"
# Fact keys/values are echoed into the system prompt; keep each rendered line short
# and free of forged role headers/delimiters.
_FACT_MAX_CHARS = 120

# Tool-call argument names worth persisting as durable tenancy facts so the
# calculators don't need to re-ask for them in later turns/threads.
_TENANCY_FACT_KEYS = {
    "monthly_net_rent",
    "current_rent",
    "local_comparable_rent",
    "floor_area_sqm",
    "built_after_oct_2014",
    "comprehensively_modernised",
    "tenancy_years",
    "tenancy_type",
    "payment_interval",
}


def load_memory(store: BaseStore, user_name: str) -> str:
    """Return a "Known about this user" block for the system prompt, or "" if empty."""
    namespace = (_NAMESPACE, user_name)

    lines: list[str] = []

    profile = store.get(namespace, "profile")
    if profile and profile.value.get("role"):
        lines.append(f"- Rolle: {profile.value['role']}")

    tenancy_facts = store.get(namespace, "tenancy_facts")
    if tenancy_facts:
        for key, value in tenancy_facts.value.items():
            lines.append(f"- {sanitise_text(str(key), _FACT_MAX_CHARS)}: "
                         f"{sanitise_text(str(value), _FACT_MAX_CHARS)}")

    preferences = store.get(namespace, "preferences")
    if preferences:
        for key, value in preferences.value.items():
            lines.append(f"- {sanitise_text(str(key), _FACT_MAX_CHARS)}: "
                         f"{sanitise_text(str(value), _FACT_MAX_CHARS)}")

    if not lines:
        return ""
    return "Bekannt über diesen Nutzer:\n" + "\n".join(lines)


def get_profile_data(store: BaseStore, user_name: str) -> dict[str, Any]:
    """Return structured `{"role", "facts", "facts_source"}` for UI display.

    Unlike `load_memory` (which formats a prompt block), this exposes the raw
    profile role, tenancy facts and their provenance so the UI can render them
    as a table.
    """
    namespace = (_NAMESPACE, user_name)
    profile = store.get(namespace, "profile")
    tenancy_facts = store.get(namespace, "tenancy_facts")
    facts_source = store.get(namespace, "facts_source")
    return {
        "role": profile.value.get("role") if profile else None,
        "facts": dict(tenancy_facts.value) if tenancy_facts else {},
        "facts_source": dict(facts_source.value) if facts_source else {},
    }


def write_facts(
    store: BaseStore,
    user_name: str,
    facts: dict[str, Any],
    *,
    source: str | None = None,
) -> None:
    """Upsert `facts` into the user's `tenancy_facts`, optionally tagging provenance.

    Same merge semantics as the tenancy-fact writing in `write_memory`. When
    `source` is given, also records it under the `"facts_source"` key, mapping
    each written fact-key to that source string (e.g. `"contract"`), so the UI
    can label contract-derived values as such.
    """
    if not facts:
        return
    namespace = (_NAMESPACE, user_name)

    existing_facts = store.get(namespace, "tenancy_facts")
    tenancy_facts = dict(existing_facts.value) if existing_facts else {}
    tenancy_facts.update(facts)
    store.put(namespace, "tenancy_facts", tenancy_facts)

    if source is not None:
        existing_source = store.get(namespace, "facts_source")
        facts_source = dict(existing_source.value) if existing_source else {}
        for key in facts:
            facts_source[key] = source
        store.put(namespace, "facts_source", facts_source)


def write_memory(
    store: BaseStore, user_name: str, role: str, messages: Sequence[BaseMessage]
) -> None:
    """Upsert the active role and any calculator tool-call args from `messages`."""
    namespace = (_NAMESPACE, user_name)

    existing_profile = store.get(namespace, "profile")
    profile = dict(existing_profile.value) if existing_profile else {}
    if profile.get("role") != role:
        profile["role"] = role
        store.put(namespace, "profile", profile)

    facts: dict[str, Any] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for tool_call in message.tool_calls:
            for key, value in tool_call.get("args", {}).items():
                if key in _TENANCY_FACT_KEYS and value is not None:
                    facts[key] = value

    if facts:
        existing_facts = store.get(namespace, "tenancy_facts")
        tenancy_facts = dict(existing_facts.value) if existing_facts else {}
        tenancy_facts.update(facts)
        store.put(namespace, "tenancy_facts", tenancy_facts)

        # A tool-confirmed value must not stay labelled as contract-derived.
        existing_source = store.get(namespace, "facts_source")
        if existing_source:
            facts_source = dict(existing_source.value)
            changed = False
            for key in facts:
                if facts_source.pop(key, None) is not None:
                    changed = True
            if changed:
                store.put(namespace, "facts_source", facts_source)
