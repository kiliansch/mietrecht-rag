"""Deterministic, regex-based extraction of tenancy facts from raw contract text.

Mirrors the conservative philosophy of `src.memory.store`: no LLM extraction, no
guessing. Only confidently-matched values are returned; anything else is omitted
so we never overwrite a user-confirmed fact with a false positive scraped from
unrelated contract text (e.g. an address number or a clause index).

Only keys present in `src.memory.store._TENANCY_FACT_KEYS` are produced — currently
`floor_area_sqm` and `monthly_net_rent`.
"""

from __future__ import annotations

import re

_FLOOR_AREA_RE = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:m\s*²|m2|qm|quadratmeter)",
    re.IGNORECASE,
)

_NET_RENT_RE = re.compile(
    r"(?:nettokaltmiete|kaltmiete|grundmiete|nettomiete)"
    r"[^\d€]{0,40}"
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
    r"\s*(?:€|eur|euro)",
    re.IGNORECASE,
)


def _parse_german_number(s: str) -> float:
    """Parse a German-formatted number string into a float.

    Handles thousands-dot + decimal-comma (``1.200,50``), plain decimal-comma
    (``72,5``), and plain integers/decimals (``850``).
    """
    s = s.strip()
    if "," in s:
        # German decimal comma; dots (if any) are thousands separators.
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def extract_tenancy_facts(text: str) -> dict[str, float]:
    """Extract confidently-recognised tenancy facts from contract `text`.

    Returns a dict containing only the keys it could confidently parse, drawn
    from: ``floor_area_sqm`` (e.g. "72 m²", "72,5 qm", "72 Quadratmeter") and
    ``monthly_net_rent`` (a "Nettokaltmiete"/"Kaltmiete"/"Grundmiete"/
    "Nettomiete" label followed by an amount with "€"/"EUR"/"Euro"). Patterns
    that do not match are simply omitted — no guessing.
    """
    facts: dict[str, float] = {}

    area_match = _FLOOR_AREA_RE.search(text)
    if area_match:
        try:
            facts["floor_area_sqm"] = _parse_german_number(area_match.group(1))
        except ValueError:
            pass

    rent_match = _NET_RENT_RE.search(text)
    if rent_match:
        try:
            facts["monthly_net_rent"] = _parse_german_number(rent_match.group(1))
        except ValueError:
            pass

    return facts
