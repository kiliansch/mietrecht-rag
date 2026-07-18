from src.ingest.chunking import (
    chunk_case_law_text,
    get_case_law_splitter,
    get_statute_splitter,
    split_by_heading,
)


def test_split_by_heading_basic():
    markdown = "## Tenor\nDie Klage wird abgewiesen.\n## Gründe\nDer Mieter unterliegt."
    sections = split_by_heading(markdown)
    assert sections == [
        ("Tenor", "Die Klage wird abgewiesen."),
        ("Gründe", "Der Mieter unterliegt."),
    ]


def test_split_by_heading_preamble_before_first_heading():
    markdown = "Vorbemerkung.\n## Tenor\nInhalt."
    sections = split_by_heading(markdown)
    assert sections[0] == ("", "Vorbemerkung.")
    assert sections[1] == ("Tenor", "Inhalt.")


def test_split_by_heading_no_headings_returns_whole_text():
    markdown = "Nur Fließtext ohne Überschriften."
    assert split_by_heading(markdown) == [("", markdown)]


def test_split_by_heading_empty_input_returns_empty_list():
    assert split_by_heading("") == []
    assert split_by_heading("   ") == []


def test_split_by_heading_drops_empty_sections():
    markdown = "## Leer\n## Tenor\nInhalt."
    sections = split_by_heading(markdown)
    assert sections == [("Tenor", "Inhalt.")]


def test_chunk_case_law_text_preserves_headings():
    markdown = "## Tenor\n" + ("Wort " * 1000)
    chunks = chunk_case_law_text(markdown)
    assert chunks
    assert all(heading == "Tenor" for heading, _ in chunks)
    assert all(text for _, text in chunks)


def test_get_statute_splitter_uses_configured_sizes():
    from src import config

    splitter = get_statute_splitter()
    assert splitter._chunk_size == config.STATUTE_CHUNK_TOKENS
    assert splitter._chunk_overlap == config.STATUTE_CHUNK_OVERLAP


def test_get_case_law_splitter_uses_configured_sizes():
    from src import config

    splitter = get_case_law_splitter()
    assert splitter._chunk_size == config.CASE_LAW_CHUNK_TOKENS
    assert splitter._chunk_overlap == config.CASE_LAW_CHUNK_OVERLAP
