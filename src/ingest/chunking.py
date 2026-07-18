"""Token-aware and heading-aware text splitters shared by both ingestion pipelines.

Chunk sizes/overlaps come from `src.config` (the single source of truth); never
hardcode sizes here.
"""

from __future__ import annotations

import re

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


def get_case_law_splitter() -> RecursiveCharacterTextSplitter:
    """Return the token-aware splitter for within-section case-law chunks."""
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=config.TOKENIZER,
        chunk_size=config.CASE_LAW_CHUNK_TOKENS,
        chunk_overlap=config.CASE_LAW_CHUNK_OVERLAP,
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


def chunk_case_law_text(markdown: str) -> list[tuple[str, str]]:
    """Heading-aware then token-bound chunking of a court decision.

    Returns a list of `(section_heading, chunk_text)` pairs.
    """
    splitter = get_case_law_splitter()
    result: list[tuple[str, str]] = []
    for heading, text in split_by_heading(markdown):
        for chunk in splitter.split_text(text):
            result.append((heading, chunk))
    return result
