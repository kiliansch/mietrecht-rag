from src.ingest.chunking import (
    chunk_case_law_hierarchical,
    get_case_law_child_splitter,
    get_case_law_parent_splitter,
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


def test_chunk_case_law_hierarchical_preserves_headings():
    markdown = "## Tenor\n" + ("Wort " * 1000)
    units = chunk_case_law_hierarchical(markdown)
    assert units
    assert all(unit.section_heading == "Tenor" for unit in units)
    assert all(unit.parent_text for unit in units)
    assert all(unit.children for unit in units)


def test_chunk_case_law_hierarchical_indexes_parents_sequentially():
    markdown = "## Tenor\n" + ("Wort " * 2000) + "\n## Gründe\n" + ("Satz " * 2000)
    units = chunk_case_law_hierarchical(markdown)
    # Parent indices are unique and contiguous from 0 across the whole decision.
    assert [u.parent_idx for u in units] == list(range(len(units)))
    # More than one parent is produced (the long sections split), and both headings appear.
    assert len(units) > 1
    assert {u.section_heading for u in units} == {"Tenor", "Gründe"}


def test_chunk_case_law_hierarchical_children_come_from_parent():
    markdown = "## Gründe\n" + ("Der Mieter zahlt die Miete nicht rechtzeitig. " * 200)
    units = chunk_case_law_hierarchical(markdown)
    # Every child chunk is a substring of its own parent window (small-to-big).
    for unit in units:
        assert all(child.strip() for child in unit.children)
        assert all(child in unit.parent_text for child in unit.children)


def test_chunk_case_law_hierarchical_empty_input():
    assert chunk_case_law_hierarchical("") == []


def test_get_statute_splitter_uses_configured_sizes():
    from src import config

    splitter = get_statute_splitter()
    assert splitter._chunk_size == config.STATUTE_CHUNK_TOKENS
    assert splitter._chunk_overlap == config.STATUTE_CHUNK_OVERLAP


def test_get_case_law_child_splitter_uses_configured_sizes():
    from src import config

    splitter = get_case_law_child_splitter()
    assert splitter._chunk_size == config.CASE_LAW_CHILD_CHUNK_TOKENS
    assert splitter._chunk_overlap == config.CASE_LAW_CHILD_CHUNK_OVERLAP


def test_get_case_law_parent_splitter_uses_configured_sizes():
    from src import config

    splitter = get_case_law_parent_splitter()
    assert splitter._chunk_size == config.CASE_LAW_PARENT_CHUNK_TOKENS
    assert splitter._chunk_overlap == config.CASE_LAW_PARENT_CHUNK_OVERLAP
