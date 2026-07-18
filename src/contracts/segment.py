"""Segment a rental-contract text into individual clauses and filter risky ones.

Primary clause detection splits on § numbers (§ 1, § 1a, …) or numbered headings
(1., 2., … at line start).  Real-world contracts, however, often arrive without
those clean line-anchored markers — PDF/OCR extraction can drop or mangle the §
glyph, flatten line breaks, or use named headings ("Mietsache", "Nebenkosten")
with no number at all.  When that happens the primary split yields a single part
covering the whole contract, which would then be handed to the reviewer as one
"clause" (the agent rightly refuses a whole contract as a single-clause request).

To stay robust we add a **size guard**: any part longer than `MAX_CLAUSE_CHARS`
is sub-split — first on named-heading boundaries, then on paragraph/line/sentence
boundaries — so `review_clause` never receives a whole contract regardless of
formatting.  Each Clause carries its sequential index, the detected heading line,
and the clause body text.
"""

from __future__ import annotations

import re
from typing import TypedDict

from src import config

# Longest clause body handed to the reviewer before the size guard sub-splits it.
# Single real clauses are almost always well under this; whole contracts are far
# above it, so this reliably separates the two.
MAX_CLAUSE_CHARS = 1500

# Primary split: a § marker or a numbered heading at the start of a line.
_SPLIT_RE = re.compile(r"(?m)^(?=§\s*\d+[a-z]?\b|\d+(?:\.\d+)*\.?\s+[A-ZÜÖÄ])")

# Common German Mietvertrag section headings that appear without a § or number.
# Ordered longest-first within families so the alternation matches the most
# specific term. Used only inside the size guard (scoped to oversized blocks) to
# avoid fragmenting normal clause bodies that merely start a line with "Miete".
_NAMED_HEADINGS = (
    r"Mietgegenstand", r"Mietsache", r"Mietobjekt", r"Mietr[aä]ume",
    r"Mietverh[aä]ltnis", r"Mietbeginn", r"Mietzeit", r"Mietdauer",
    r"Nettokaltmiete", r"Grundmiete", r"Kaltmiete", r"Mietzins", r"Miete",
    r"Betriebskostenabrechnung", r"Betriebskosten", r"Nebenkosten", r"Heizkosten",
    r"Mietsicherheit", r"Kaution",
    r"Sch[oö]nheitsreparaturen", r"Kleinreparaturen", r"Instandhaltung",
    r"Instandsetzung",
    r"Haustierhaltung", r"Tierhaltung",
    r"Untervermietung", r"Gebrauchs[uü]berlassung",
    r"K[uü]ndigungsverzicht", r"K[uü]ndigung",
    r"Zahlungsweise", r"Zahlung", r"SEPA(?:-Lastschrift)?", r"Lastschrift",
    r"Bankeinzug",
    r"Staffelmiete", r"Indexmiete", r"Wertsicherung",
    r"Hausordnung",
    r"Wohnfl[aä]chenabweichung", r"Wohnfl[aä]che",
    r"Schlussbestimmungen", r"Sonstiges",
)
# Split before a line that looks like a heading: optional §/number prefix, a named
# term, and only a short remainder up to end-of-line (so body sentences that begin
# with a common word are not mistaken for headings).
_NAMED_SPLIT_RE = re.compile(
    r"(?im)^(?=[ \t]*(?:(?:§\s*\d+[a-z]?|\d+(?:\.\d+)*\.?)[ \t]+)?"
    r"(?:" + "|".join(_NAMED_HEADINGS) + r")\b[^\n]{0,40}$)"
)


class Clause(TypedDict):
    index: int
    heading: str
    text: str


def _split_atoms(text: str) -> list[str]:
    """Break `text` into the finest natural units available (paragraphs → lines →
    sentences) for size-based packing."""
    for pattern in (r"\n\s*\n", r"\n"):
        parts = re.split(pattern, text)
        if len(parts) > 1:
            return parts
    return re.split(r"(?<=[.!?])\s+", text)


def _pack(text: str, max_chars: int) -> list[str]:
    """Greedily pack natural atoms of `text` into chunks no longer than `max_chars`.

    Atoms larger than `max_chars` on their own (e.g. one enormous line) are
    hard-sliced so every returned chunk respects the cap.
    """
    chunks: list[str] = []
    current = ""
    for atom in _split_atoms(text):
        atom = atom.strip()
        if not atom:
            continue
        if len(atom) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(atom), max_chars):
                chunks.append(atom[i : i + max_chars])
            continue
        if current and len(current) + 1 + len(atom) > max_chars:
            chunks.append(current)
            current = atom
        else:
            current = f"{current}\n{atom}" if current else atom
    if current:
        chunks.append(current)
    return chunks


def _guard_split(part: str) -> list[str]:
    """Sub-split an oversized part so no single piece exceeds `MAX_CLAUSE_CHARS`.

    Tries named-heading boundaries first (recovers proper clauses from contracts
    with no §/numbered markers), then falls back to size-based packing.
    """
    if len(part) <= MAX_CLAUSE_CHARS:
        return [part]

    named = [p.strip() for p in _NAMED_SPLIT_RE.split(part) if p.strip()]
    if len(named) > 1:
        pieces: list[str] = []
        for piece in named:
            pieces.extend(_pack(piece, MAX_CLAUSE_CHARS) if len(piece) > MAX_CLAUSE_CHARS else [piece])
        return pieces

    return _pack(part, MAX_CLAUSE_CHARS)


def segment_clauses(text: str) -> list[Clause]:
    """Split *text* into clauses on § or numbered-heading boundaries.

    Any preamble before the first heading is returned as its own clause (skipped
    by risk_filter if it contains no risky keywords). Oversized parts — including
    a whole contract with no recognised markers — are sub-split by the size guard
    so each returned clause stays reviewable in isolation.
    """
    parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
    # No §/numbered structure found (the whole text came back as one part): fall
    # back to named-heading boundaries so contracts that use plain headings
    # ("Mietsache", "Kaution", …) still split into individual clauses regardless
    # of length — not only once they exceed the size guard.
    if len(parts) <= 1:
        named = [p.strip() for p in _NAMED_SPLIT_RE.split(text) if p.strip()]
        if len(named) > 1:
            parts = named

    clauses: list[Clause] = []
    for part in parts:
        for piece in _guard_split(part):
            piece = piece.strip()
            if not piece:
                continue
            # First line is the heading; rest is the body.
            lines = piece.split("\n", 1)
            heading = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            clauses.append(Clause(index=0, heading=heading, text=body or piece))
    # Re-index sequentially
    for idx, clause in enumerate(clauses):
        clause["index"] = idx
    return clauses


def risk_filter(clauses: list[Clause]) -> list[Clause]:
    """Return only clauses matching at least one risky-topic pattern from config."""
    patterns = [re.compile(p, re.IGNORECASE) for p in config.CONTRACT_RISKY_PATTERNS]
    result = []
    for clause in clauses:
        combined = clause["heading"] + " " + clause["text"]
        if any(pat.search(combined) for pat in patterns):
            result.append(clause)
    return result
