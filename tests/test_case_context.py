"""Pure tests for the case prompt-context block (no database)."""

from src.cases.store import build_context_block

CASE = {"id": "c1", "title": "Nebenkostenabrechnung 2025", "status": "open"}


def test_block_contains_title_documents_and_open_deadlines() -> None:
    docs = [
        {"kind": "contract", "title": "Mietvertrag.pdf", "analysis": None},
        {"kind": "letter", "title": "Abrechnung.pdf", "analysis": {"summary": "…"}},
    ]
    deadlines = [
        {"title": "Widerspruch einlegen", "due_date": "2026-08-15", "status": "open"},
        {"title": "Erledigt", "due_date": "2026-01-01", "status": "done"},
    ]
    block = build_context_block(CASE, docs, deadlines)
    assert "Nebenkostenabrechnung 2025" in block
    assert "[Vertrag] Mietvertrag.pdf" in block
    assert "[Schreiben] Abrechnung.pdf — bereits analysiert" in block
    assert "2026-08-15: Widerspruch einlegen" in block
    # Non-open deadlines never appear.
    assert "Erledigt" not in block


def test_block_without_docs_or_deadlines() -> None:
    block = build_context_block(CASE, [], [])
    assert "Offene Fristen: keine" in block
    assert "Dokumente" not in block


def test_block_caps_lists_and_title_lengths() -> None:
    docs = [{"kind": "letter", "title": f"Brief {i}", "analysis": None} for i in range(30)]
    deadlines = [
        {"title": "x" * 500, "due_date": "2026-08-15", "status": "open"} for _ in range(30)
    ]
    block = build_context_block(CASE, docs, deadlines)
    assert block.count("[Schreiben]") == 10
    assert block.count("2026-08-15") == 10
    # Long titles are truncated.
    assert "x" * 121 not in block
