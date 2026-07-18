"""Unit tests for src/contracts/parse.py, segment.py, and review.py."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from src.contracts.parse import extract_text
from src.contracts.segment import MAX_CLAUSE_CHARS, Clause, risk_filter, segment_clauses
from src.contracts.review import review_clause


# ---------------------------------------------------------------------------
# extract_text — TXT
# ---------------------------------------------------------------------------


def test_extract_text_txt() -> None:
    data = "Hallo Mietvertrag".encode("utf-8")
    assert extract_text(data, "vertrag.txt") == "Hallo Mietvertrag"


# ---------------------------------------------------------------------------
# extract_text — PDF (text path)
# ---------------------------------------------------------------------------


def test_extract_text_pdf_text() -> None:
    page = MagicMock()
    page.extract_text.return_value = "§ 1 Mietgegenstand\nDie Wohnung liegt in Berlin." * 3
    with patch("pypdf.PdfReader") as mock_reader:
        mock_reader.return_value.pages = [page]
        result = extract_text(b"%PDF-fake", "vertrag.pdf")
    assert "Mietgegenstand" in result


# ---------------------------------------------------------------------------
# extract_text — PDF OCR fallback
# ---------------------------------------------------------------------------


def test_extract_text_pdf_ocr_fallback() -> None:
    page = MagicMock()
    page.extract_text.return_value = "tiny"  # < 100 chars → OCR fallback
    fake_img = MagicMock()
    with (
        patch("pypdf.PdfReader") as mock_reader,
        patch("shutil.which", return_value="/usr/bin/pdftoppm"),
        patch("pdf2image.convert_from_bytes", return_value=[fake_img]),
        patch("pytesseract.image_to_string", return_value="OCR Ergebnis"),
    ):
        mock_reader.return_value.pages = [page]
        result = extract_text(b"%PDF-fake", "scan.pdf")
    assert result == "OCR Ergebnis"


# ---------------------------------------------------------------------------
# extract_text — image OCR
# ---------------------------------------------------------------------------


def test_extract_text_image() -> None:
    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    with (
        patch("shutil.which", return_value="/usr/bin/tesseract"),
        patch("pytesseract.image_to_string", return_value="Kaution Klausel"),
    ):
        result = extract_text(png_bytes, "page.png")
    assert "Kaution" in result


# ---------------------------------------------------------------------------
# extract_text — unsupported format
# ---------------------------------------------------------------------------


def test_extract_text_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(b"data", "file.xls")


# ---------------------------------------------------------------------------
# extract_text — missing binary raises ImportError
# ---------------------------------------------------------------------------


def test_extract_text_missing_binary() -> None:
    page = MagicMock()
    page.extract_text.return_value = "x"  # short → triggers OCR path
    with (
        patch("pypdf.PdfReader") as mock_reader,
        patch("shutil.which", return_value=None),  # binary missing
    ):
        mock_reader.return_value.pages = [page]
        with pytest.raises(ImportError, match="pdftoppm"):
            extract_text(b"%PDF-fake", "scan.pdf")


# ---------------------------------------------------------------------------
# segment_clauses — § heading splitting
# ---------------------------------------------------------------------------


def test_segment_clauses_paragraph_split() -> None:
    text = "§ 1 Mietgegenstand\nDie Wohnung.\n§ 2 Mietzins\nDie Miete beträgt 800 Euro."
    clauses = segment_clauses(text)
    assert len(clauses) == 2
    assert clauses[0]["heading"] == "§ 1 Mietgegenstand"
    assert "Wohnung" in clauses[0]["text"]
    assert clauses[1]["heading"] == "§ 2 Mietzins"
    assert clauses[0]["index"] == 0
    assert clauses[1]["index"] == 1


# ---------------------------------------------------------------------------
# segment_clauses — numbered heading splitting
# ---------------------------------------------------------------------------


def test_segment_clauses_numbered_split() -> None:
    text = "1. Vertragsparteien\nMieter: Max Mustermann\n2. Mietobjekt\nWohnung in München"
    clauses = segment_clauses(text)
    assert len(clauses) >= 2


# ---------------------------------------------------------------------------
# segment_clauses — size guard on contracts without clean §/numbered markers
# ---------------------------------------------------------------------------


def test_segment_clauses_named_headings_without_paragraph_markers() -> None:
    """A contract using named headings (no line-anchored § / numbers) must still
    split into multiple atomic clauses rather than one whole-contract clause."""
    text = (
        "Mietvertrag zwischen den Parteien.\n"
        "Mietsache\n"
        "Die Wohnung liegt in Berlin und umfasst 72 m².\n"
        "Miete\n"
        "Die monatliche Nettokaltmiete beträgt 850 Euro.\n"
        "Betriebskosten\n"
        "Die Betriebskosten werden jährlich abgerechnet.\n"
        "Kaution\n"
        "Die Kaution beträgt drei Nettokaltmieten.\n"
    ) * 20  # inflate well past MAX_CLAUSE_CHARS so the size guard engages
    clauses = segment_clauses(text)
    assert len(clauses) > 1
    # No returned clause may be the whole contract (the bug we are fixing).
    assert all(len(c["text"]) <= MAX_CLAUSE_CHARS for c in clauses)


def test_segment_clauses_named_headings_short_contract_splits() -> None:
    """A short contract (below the size guard) that uses plain named headings must
    still split per-clause, so each clause is reviewed on its own."""
    text = (
        "Mietsache\nDie Wohnung liegt in Berlin.\n"
        "Kaution\nDie Kaution beträgt vier Nettokaltmieten.\n"
        "Tierhaltung\nJede Tierhaltung ist verboten.\n"
    )
    assert len(text) < MAX_CLAUSE_CHARS
    clauses = segment_clauses(text)
    headings = [c["heading"] for c in clauses]
    assert "Kaution" in headings
    assert "Tierhaltung" in headings
    assert len(clauses) >= 3


def test_segment_clauses_flattened_text_is_chunked() -> None:
    """Even fully flattened text (no newlines, no headings) is capped by the guard
    so review_clause never receives a whole contract."""
    text = ("Die Miete ist monatlich im Voraus zu zahlen. " * 200).strip()
    clauses = segment_clauses(text)
    assert len(clauses) > 1
    assert all(len(c["text"]) <= MAX_CLAUSE_CHARS for c in clauses)


def test_segment_clauses_small_clause_not_split() -> None:
    """A normal, well-formed § clause below the cap is left intact."""
    text = "§ 5 Kaution\nDie Kaution beträgt drei Monatsmieten und wird verzinst."
    clauses = segment_clauses(text)
    assert len(clauses) == 1
    assert clauses[0]["heading"] == "§ 5 Kaution"


# ---------------------------------------------------------------------------
# segment_clauses — empty text
# ---------------------------------------------------------------------------


def test_segment_clauses_empty() -> None:
    assert segment_clauses("") == []


# ---------------------------------------------------------------------------
# risk_filter — risky keyword retained
# ---------------------------------------------------------------------------


def test_risk_filter_keeps_risky() -> None:
    clauses: list[Clause] = [
        Clause(index=0, heading="§ 1 Kaution", text="Die Kaution beträgt drei Monatsmieten."),
        Clause(index=1, heading="§ 2 Hausordnung", text="Ruhezeiten sind einzuhalten."),
    ]
    result = risk_filter(clauses)
    assert len(result) == 1
    assert result[0]["heading"] == "§ 1 Kaution"


# ---------------------------------------------------------------------------
# risk_filter — no risky clauses → empty result
# ---------------------------------------------------------------------------


def test_risk_filter_empty_when_no_match() -> None:
    clauses: list[Clause] = [
        Clause(index=0, heading="§ 1 Parteien", text="Mieter und Vermieter schließen ab.")
    ]
    assert risk_filter(clauses) == []


# ---------------------------------------------------------------------------
# risk_filter — Schönheitsreparatur detected
# ---------------------------------------------------------------------------


def test_risk_filter_schoenheitsreparatur() -> None:
    clauses: list[Clause] = [
        Clause(
            index=0,
            heading="§ 9",
            text="Der Mieter trägt alle Schönheitsreparaturen.",
        ),
    ]
    assert len(risk_filter(clauses)) == 1


# ---------------------------------------------------------------------------
# review_clause — wirksam verdict
# ---------------------------------------------------------------------------


def test_review_clause_wirksam() -> None:
    clause = Clause(
        index=0, heading="§ 1 Mietzins", text="Die Miete beträgt 800 Euro monatlich."
    )
    mock_answer = "Bewertung: wirksam\nBegründung: Standardklausel.\n§-Referenz: §535 BGB"
    with patch("src.contracts.review.agent_graph.review", return_value=(mock_answer, [])):
        finding = review_clause(clause, thread_id="t1", user_name="max", role="mieter")
    assert finding["verdict"] == "wirksam"
    assert "Standardklausel" in finding["reasoning"]
    assert finding["sources"] == []


# ---------------------------------------------------------------------------
# review_clause — unwirksam verdict
# ---------------------------------------------------------------------------


def test_review_clause_unwirksam() -> None:
    clause = Clause(
        index=0,
        heading="§ 9 Schönheitsreparaturen",
        text="Der Mieter ist verpflichtet, alle Schönheitsreparaturen zu tragen.",
    )
    mock_answer = (
        "Bewertung: unwirksam\nBegründung: Klausel ist zu weit gefasst.\n§-Referenz: §535 BGB"
    )
    with patch("src.contracts.review.agent_graph.review", return_value=(mock_answer, [])):
        finding = review_clause(clause, thread_id="t2", user_name="max", role="mieter")
    assert finding["verdict"] == "unwirksam"
    assert "zu weit gefasst" in finding["reasoning"]


# ---------------------------------------------------------------------------
# review_clause — unknown verdict defaults to bedenklich
# ---------------------------------------------------------------------------


def test_review_clause_unknown_verdict_defaults() -> None:
    clause = Clause(index=0, heading="§ 5", text="Diverse Regelungen.")
    mock_answer = "Keine klare Bewertung möglich."  # no "Bewertung:" line
    with patch("src.contracts.review.agent_graph.review", return_value=(mock_answer, [])):
        finding = review_clause(clause, thread_id="t3", user_name="max", role="mieter")
    assert finding["verdict"] == "bedenklich"
