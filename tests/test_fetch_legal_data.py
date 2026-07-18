"""
tests/test_fetch_legal_data.py

Tests for the two bug fixes in fetch_legal_data.py:
  1. 429 Too Many Requests extended retry logic (Bug #1)
  2. enrich_norms() covers BGB §535–§577, all BetrKV, and all WoGG (Bug #2)

All tests use unittest.mock — no real HTTP calls, no real file I/O for the
api_get tests, and time.sleep is always patched to prevent real waits.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from fetch_legal_data import (
    RATE_LIMIT_RETRIES,
    _should_enrich,
    api_get,
    enrich_norms,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_response(status_code: int, body: Any = None) -> MagicMock:
    """Return a mock requests.Response with the given status code and JSON body."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
    if status_code >= 400:
        http_err = requests.HTTPError(response=resp)
        resp.raise_for_status.side_effect = http_err
    else:
        resp.raise_for_status.return_value = None
    return resp


def _make_norm(section: str, norm_id: int, book_slug: str = "bgb") -> dict:
    return {"id": norm_id, "section": section, "book_slug": book_slug}


def _minimal_detail(norm_id: int, section: str, book_slug: str) -> dict:
    return {
        "id": norm_id,
        "section": section,
        "title": f"Title {norm_id}",
        "content": f"<p>Content for {section}</p>",
        "book_slug": book_slug,
        "slug": section.replace("§ ", ""),
        "updated_date": "2026-01-01T00:00:00Z",
    }


# ── Bug #1: 429 retry logic ────────────────────────────────────────────────────


class TestApiGet429Retries:
    """api_get() must use extended backoff for 429 before giving up."""

    @patch("fetch_legal_data.time.sleep")
    @patch("requests.get")
    def test_api_get_retries_on_429_and_succeeds(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """
        Two consecutive 429 responses followed by a 200 must return the 200 body.
        Exactly 3 HTTP calls must be made in total.
        """
        ok_body = {"id": 42, "name": "test"}
        mock_get.side_effect = [
            _make_response(429),
            _make_response(429),
            _make_response(200, ok_body),
        ]

        result = api_get(
            "https://example.com/api/laws/1/",
            params={},
            headers={"api_key": "test"},
        )

        assert result == ok_body
        assert mock_get.call_count == 3

    @patch("fetch_legal_data.time.sleep")
    @patch("requests.get")
    def test_api_get_raises_after_all_429_retries_exhausted(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """
        RATE_LIMIT_RETRIES consecutive 429 responses after the first attempt
        must cause api_get() to return None.
        """
        # Initial call + RATE_LIMIT_RETRIES retries, all 429
        mock_get.side_effect = [_make_response(429)] * (RATE_LIMIT_RETRIES + 1)

        result = api_get(
            "https://example.com/api/laws/2/",
            params={},
            headers={"api_key": "test"},
        )

        assert result is None

    @patch("fetch_legal_data.time.sleep")
    @patch("requests.get")
    def test_api_get_standard_errors_use_default_backoff(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """
        Non-429 HTTP errors keep the original 3-retry / 2-4-8 s behaviour.
        Exactly 3 calls and None returned.
        """
        mock_get.side_effect = [_make_response(500)] * 3

        result = api_get(
            "https://example.com/api/laws/3/",
            params={},
            headers={"api_key": "test"},
        )

        assert result is None
        assert mock_get.call_count == 3


# ── Bug #2: enrich_norms covers all books ─────────────────────────────────────


class TestEnrichNorms:
    """enrich_norms() must process BGB §535–577, all BetrKV, and all WoGG."""

    def _norms_by_slug(self) -> dict[str, list[dict]]:
        return {
            "bgb": [
                _make_norm("§ 542", 1, "bgb"),  # in range → enriched
                _make_norm("§ 100", 2, "bgb"),  # out of range → skipped
            ],
            "betrkv": [
                _make_norm("§ 2", 3, "betrkv"),  # always enriched
            ],
            "wogg": [
                _make_norm("§ 27", 4, "wogg"),  # always enriched
            ],
        }

    @patch("fetch_legal_data.time.sleep")
    @patch("fetch_legal_data._safe_write_json")
    @patch("fetch_legal_data.api_get")
    def test_enrich_norms_includes_betrkv_and_wogg(
        self,
        mock_api_get: MagicMock,
        mock_write: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """
        Should enrich §542 bgb, the betrkv norm, and the wogg norm — 3 total.
        §100 bgb must be skipped (outside §535–§577).
        """
        mock_api_get.side_effect = [
            _minimal_detail(1, "§ 542", "bgb"),
            _minimal_detail(3, "§ 2", "betrkv"),
            _minimal_detail(4, "§ 27", "wogg"),
        ]

        result = enrich_norms(self._norms_by_slug(), api_key="test")

        assert len(result) == 3
        slugs = {r["book_slug"] for r in result}
        assert slugs == {"bgb", "betrkv", "wogg"}
        sections = {r["section"] for r in result}
        assert "§ 542" in sections
        assert "§ 100" not in sections

    @patch("fetch_legal_data.time.sleep")
    @patch("fetch_legal_data._safe_write_json")
    @patch("fetch_legal_data.api_get")
    def test_enrich_norms_raises_on_permanent_api_failure(
        self,
        mock_api_get: MagicMock,
        mock_write: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """
        api_get() returning None (exhausted retries) must cause RuntimeError.
        The pipeline must never silently skip a norm.
        """
        mock_api_get.return_value = None

        norms_by_slug = {
            "betrkv": [_make_norm("§ 1", 10, "betrkv")],
        }

        with pytest.raises(RuntimeError, match="Failed to enrich norm"):
            enrich_norms(norms_by_slug, api_key="test")


# ── _should_enrich routing ─────────────────────────────────────────────────────


class TestShouldEnrich:
    """_should_enrich() must route correctly for all books and boundary values."""

    @pytest.mark.parametrize(
        "section, book_slug, expected",
        [
            ("§ 534", "bgb", False),   # below range
            ("§ 535", "bgb", True),    # lower boundary
            ("§ 577", "bgb", True),    # upper boundary
            ("§ 578", "bgb", False),   # above range
            ("§ 1",   "betrkv", True),
            ("§ 27",  "wogg", True),
            ("§ 1",   "wistg", False),
        ],
    )
    def test_should_enrich_routing(
        self, section: str, book_slug: str, expected: bool
    ) -> None:
        norm = {"section": section, "id": 999}
        assert _should_enrich(norm, book_slug) is expected


# ── _split_by_absatz ──────────────────────────────────────────────────────────────

class TestSplitByAbsatz:
    """_split_by_absatz() must correctly parse Absatz markers from norm content."""

    def test_multi_absatz_splits_correctly(self) -> None:
        """Content with (1), (2) markers must produce two labelled chunks."""
        from fetch_legal_data import _split_by_absatz

        content = (
            "(1) Der Vermieter ist verpflichtet, die Wohnung zu übergeben.\n\n\n"
            "(2) Der Mieter ist zur Mietzahlung verpflichtet."
        )
        result = _split_by_absatz(content)
        assert len(result) == 2
        assert result[0][0] == "Abs. 1"
        assert result[1][0] == "Abs. 2"
        assert "(1)" in result[0][1]
        assert "(2)" in result[1][1]

    def test_absatz_label_format_with_letter_variant(self) -> None:
        """Labels must be 'Abs. N' format, including lettered variants like (1a)."""
        from fetch_legal_data import _split_by_absatz

        content = (
            "(1) Erster Absatz.\n\n\n"
            "(1a) Eingefügter Absatz.\n\n\n"
            "(2) Zweiter Absatz."
        )
        result = _split_by_absatz(content)
        labels = [r[0] for r in result]
        assert labels == ["Abs. 1", "Abs. 1a", "Abs. 2"]

    def test_single_block_norm_returns_empty_label(self) -> None:
        """Content without Absatz markers must return one chunk with empty label."""
        from fetch_legal_data import _split_by_absatz

        content = "Kennt der Mieter bei Vertragsschluss den Mangel, stehen ihm die Rechte nicht zu."
        result = _split_by_absatz(content)
        assert len(result) == 1
        assert result[0][0] == ""
        assert result[0][1] == content.strip()
