"""Token-aware and heading-aware text splitters shared by both ingestion pipelines.

Chunk sizes/overlaps come from `src.config` (the single source of truth); never
hardcode sizes here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src import config

# Matches a markdown heading line (court-decision section headings such as
# Tenor / Tatbestand / Entscheidungsgründe / Gründe use "##" or deeper levels).
_HEADING_RE = re.compile(r"^#{2,6}\s+(.+)$", re.MULTILINE)


def get_statute_splitter() -> RecursiveCharacterTextSplitter:
    """Return the token-aware splitter for statute chunks."""
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=config.TOKENIZER,
        chunk_size=config.STATUTE_CHUNK_TOKENS,
        chunk_overlap=config.STATUTE_CHUNK_OVERLAP,
    )


def get_case_law_parent_splitter() -> RecursiveCharacterTextSplitter:
    """Return the token-aware splitter for the larger case-law PARENT windows.

    Parents are the context unit returned by retrieval (never re-embedded), so a
    coarser size with no overlap is used.
    """
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=config.TOKENIZER,
        chunk_size=config.CASE_LAW_PARENT_CHUNK_TOKENS,
        chunk_overlap=config.CASE_LAW_PARENT_CHUNK_OVERLAP,
    )


def get_case_law_child_splitter() -> RecursiveCharacterTextSplitter:
    """Return the token-aware splitter for the small case-law CHILD chunks.

    Children are the precise unit that gets embedded + FTS-indexed.
    """
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=config.TOKENIZER,
        chunk_size=config.CASE_LAW_CHILD_CHUNK_TOKENS,
        chunk_overlap=config.CASE_LAW_CHILD_CHUNK_OVERLAP,
    )


def split_by_heading(markdown: str) -> list[tuple[str, str]]:
    """Split `markdown` on top-level "## Heading" lines.

    Returns a list of `(heading, section_text)` pairs, in document order. Any text
    appearing before the first heading is returned with heading `""`. Empty
    sections are dropped.
    """
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        text = markdown.strip()
        return [("", text)] if text else []

    sections: list[tuple[str, str]] = []
    preamble = markdown[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))

    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        text = markdown[start:end].strip()
        if text:
            sections.append((heading, text))
    return sections


@dataclass(frozen=True)
class ParentUnit:
    """One parent window of a court decision and the child chunks embedded from it.

    `parent_idx` is the running index of this parent across the whole decision
    (used to build a stable `parent_id`); `children` are the small chunks that get
    embedded, while `parent_text` is the larger context returned at retrieval time.
    """

    section_heading: str
    parent_idx: int
    parent_text: str
    children: list[str]


def chunk_case_law_hierarchical(markdown: str) -> list[ParentUnit]:
    """Heading-aware, two-level (parent-document) chunking of a court decision.

    For each `(heading, section_text)` from `split_by_heading`, the section is first
    split into larger PARENT windows, then each parent is split into small CHILD
    chunks. Parents are indexed sequentially across the whole decision so a stable
    `{doc_id}_{parent_idx}` key can be formed downstream. Parents with no non-empty
    children are dropped.
    """
    parent_splitter = get_case_law_parent_splitter()
    child_splitter = get_case_law_child_splitter()
    units: list[ParentUnit] = []
    parent_idx = 0
    for heading, text in split_by_heading(markdown):
        for parent_text in parent_splitter.split_text(text):
            children = [c for c in child_splitter.split_text(parent_text) if c.strip()]
            if not children:
                continue
            units.append(ParentUnit(heading, parent_idx, parent_text, children))
            parent_idx += 1
    return units
