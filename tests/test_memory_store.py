from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

from src.memory.store import get_profile_data, load_memory, write_facts, write_memory


def test_load_memory_empty_for_unknown_user():
    store = InMemoryStore()
    assert load_memory(store, "neu") == ""


def test_get_profile_data_empty_for_unknown_user():
    store = InMemoryStore()
    assert get_profile_data(store, "neu") == {"role": None, "facts": {}, "facts_source": {}}


def test_get_profile_data_returns_structured_role_and_facts():
    store = InMemoryStore()
    write_memory(
        store,
        "demo",
        "mieter",
        [AIMessage(content="", tool_calls=[{"id": "1", "name": "x", "args": {"floor_area_sqm": 72.0}}])],
    )
    data = get_profile_data(store, "demo")
    assert data["role"] == "mieter"
    assert data["facts"]["floor_area_sqm"] == 72.0


def test_write_memory_persists_role():
    store = InMemoryStore()
    write_memory(store, "demo", "vermieter", [])
    block = load_memory(store, "demo")
    assert "Rolle: vermieter" in block


def test_write_memory_extracts_tenancy_facts_from_tool_calls():
    store = InMemoryStore()
    messages = [
        HumanMessage(content="Wie hoch darf meine Kaution sein?"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "calculate_deposit_limit",
                    "args": {"monthly_net_rent": 800.0},
                }
            ],
        ),
    ]
    write_memory(store, "demo", "mieter", messages)
    block = load_memory(store, "demo")
    assert "monthly_net_rent: 800.0" in block


def test_write_memory_ignores_unrelated_tool_call_args():
    store = InMemoryStore()
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "search_law", "args": {"query": "Kaution"}}],
        ),
    ]
    write_memory(store, "demo", "mieter", messages)
    block = load_memory(store, "demo")
    # Only the role line is recorded; "query" is not a tenancy fact key.
    assert "query" not in block


def test_write_memory_facts_persist_across_calls():
    store = InMemoryStore()
    write_memory(
        store,
        "demo",
        "mieter",
        [AIMessage(content="", tool_calls=[{"id": "1", "name": "x", "args": {"monthly_net_rent": 800.0}}])],
    )
    write_memory(
        store,
        "demo",
        "mieter",
        [AIMessage(content="", tool_calls=[{"id": "2", "name": "x", "args": {"tenancy_years": 3}}])],
    )
    block = load_memory(store, "demo")
    assert "monthly_net_rent: 800.0" in block
    assert "tenancy_years: 3" in block


def test_write_facts_upserts_facts_and_provenance():
    store = InMemoryStore()
    write_facts(store, "demo", {"floor_area_sqm": 72.0}, source="contract")
    data = get_profile_data(store, "demo")
    assert data["facts"]["floor_area_sqm"] == 72.0
    assert data["facts_source"]["floor_area_sqm"] == "contract"


def test_write_facts_without_source_does_not_set_provenance():
    store = InMemoryStore()
    write_facts(store, "demo", {"floor_area_sqm": 72.0})
    data = get_profile_data(store, "demo")
    assert data["facts"]["floor_area_sqm"] == 72.0
    assert data["facts_source"] == {}


def test_write_memory_clears_provenance_for_keys_it_overwrites():
    store = InMemoryStore()
    write_facts(store, "demo", {"monthly_net_rent": 850.0}, source="contract")
    data = get_profile_data(store, "demo")
    assert data["facts_source"]["monthly_net_rent"] == "contract"

    # Tool-confirmed value for the same key must clear the "contract" provenance.
    write_memory(
        store,
        "demo",
        "mieter",
        [AIMessage(content="", tool_calls=[{"id": "1", "name": "x", "args": {"monthly_net_rent": 900.0}}])],
    )
    data = get_profile_data(store, "demo")
    assert data["facts"]["monthly_net_rent"] == 900.0
    assert "monthly_net_rent" not in data["facts_source"]
