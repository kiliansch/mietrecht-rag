from unittest.mock import MagicMock

from src.ingest.contextual import (
    _generate_gist,
    _metadata_prefix,
    format_prefix,
    generate_prefixes,
)

_ROW = {
    "id": 42,
    "court": {"name": "Bundesgerichtshof"},
    "file_number": "VIII ZR 305/19",
    "date": "2021-03-18",
    "markdown_content": "## Tenor\nDie Revision wird zurückgewiesen.",
}


def test_metadata_prefix_joins_available_fields():
    assert _metadata_prefix(_ROW) == "Bundesgerichtshof – VIII ZR 305/19 – 2021-03-18"


def test_metadata_prefix_tolerates_missing_fields():
    assert _metadata_prefix({"court": None}) == "Gericht"


def test_format_prefix_with_gist():
    prefix = format_prefix(_ROW, "Modernisierungsankündigung muss drei Monate vorher erfolgen.")
    assert prefix.startswith("[Kontext: Bundesgerichtshof – VIII ZR 305/19 – 2021-03-18: ")
    assert prefix.endswith("]\n\n")
    assert "Modernisierungsankündigung" in prefix


def test_format_prefix_without_gist_is_metadata_only():
    prefix = format_prefix(_ROW, "")
    assert prefix == "[Kontext: Bundesgerichtshof – VIII ZR 305/19 – 2021-03-18]\n\n"


def test_generate_gist_returns_empty_on_llm_failure():
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("boom")
    assert _generate_gist(_ROW, llm) == ""


def test_generate_gist_strips_and_collapses_whitespace():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="  Es geht um\n  Modernisierung.  ")
    assert _generate_gist(_ROW, llm) == "Es geht um Modernisierung."


def test_generate_gist_empty_source_skips_llm():
    llm = MagicMock()
    assert _generate_gist({"markdown_content": "   "}, llm) == ""
    llm.invoke.assert_not_called()


def test_generate_prefixes_empty_input():
    assert generate_prefixes([]) == []
