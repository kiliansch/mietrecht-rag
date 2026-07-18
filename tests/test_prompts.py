import pytest

from src.agent.prompts import ROLE_LABELS, build_system_prompt


def test_role_labels_cover_all_roles():
    assert set(ROLE_LABELS) == {"mieter", "vermieter", "jurist"}


@pytest.mark.parametrize("role", ["mieter", "vermieter", "jurist"])
def test_build_system_prompt_returns_string_for_known_roles(role):
    prompt = build_system_prompt(role)
    assert isinstance(prompt, str)
    assert "niemals" in prompt
    assert "Floskeln" in prompt


def test_build_system_prompt_english_language_directive():
    # Default (German) has no English directive; language="en" adds it.
    assert "write your entire answer in English" not in build_system_prompt("mieter")
    en = build_system_prompt("mieter", language="en")
    assert "write your entire answer in English" in en
    # Retrieval still targets German sources — the German grounding rules remain.
    assert "Gesetzeswortlaut" in en


def test_build_system_prompt_unknown_role_raises():
    with pytest.raises(ValueError, match="Unknown role"):
        build_system_prompt("unknown_role")


def test_build_system_prompt_mentions_retrieval_tool():
    prompt = build_system_prompt("mieter")
    assert "search_law" in prompt


def test_build_system_prompt_instructs_consulting_both_corpora():
    # One search_law call covers statutes AND case law; the prompt must say both
    # source types are weighed together, not either/or.
    prompt = build_system_prompt("mieter")
    assert "Gesetzeswortlaut" in prompt and "Rechtsprechung" in prompt


def test_build_system_prompt_appends_memory_block():
    memory_block = "Bekannt über diesen Nutzer:\n- Rolle: mieter"
    prompt = build_system_prompt("mieter", memory_block)
    assert prompt.endswith(memory_block)


def test_build_system_prompt_without_memory_block_omits_it():
    prompt = build_system_prompt("mieter")
    assert "Bekannt über diesen Nutzer" not in prompt
