"""Agentic-RAG retrieval: one tool `search_law` over BOTH corpora (statutes + case law).

Consolidated so every legal query is grounded in the statute wording AND the relevant
case law in a single call — the model no longer has to remember to query both sources
separately. Each corpus is fetched through its hybrid (dense + German FTS) + reranked
retriever (`src.retrieval.hybrid`), then the two result sets are merged into ONE
length-bounded `<untrusted_context>` block of sanitised, source-tagged,
citation-annotated snippets — DATA for the model to cite as evidence, never instructions.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_core.tools import tool

from src import config
from src.agent.security import delimit, sanitise_text
from src.retrieval.hybrid import get_hybrid_retriever

_NO_RESULTS = "Keine passenden Treffer gefunden."

# Per-citation source tag (rendered in each "### Quelle N [<tag>]" line) → the
# `source` key used by the UI and eval. One block now mixes both corpora, so the
# tag — not a block-level source — is what maps a citation back to its collection.
_LABEL_STATUTE = "Gesetz"
_LABEL_CASE_LAW = "Rechtsprechung"
_LABEL_TO_SOURCE = {_LABEL_STATUTE: "statutes", _LABEL_CASE_LAW: "case_law"}

# Header is greedy so a header containing " (" (e.g. a title with parentheses)
# still parses — the URL is the final parenthesised group on the line.
_CITATION_RE = re.compile(
    r"^### Quelle \d+ \[(?P<label>Gesetz|Rechtsprechung)\]: "
    r"(?P<header>.+) \((?P<url>[^()]*)\)\s*$",
    re.MULTILINE,
)

# Short caps for the citation header/url — they come from retrieved (untrusted,
# scraped) metadata and are sanitised before entering the <untrusted_context> block.
_HEADER_MAX_CHARS = 200
_URL_MAX_CHARS = 300


def _statute_header(doc: Document) -> str:
    meta = doc.metadata
    parts = [str(meta[k]) for k in ("section", "absatz") if meta.get(k)]
    if meta.get("title"):
        parts.append(str(meta["title"]))
    return " – ".join(parts) if parts else "Gesetzestext"


def _case_law_header(doc: Document) -> str:
    meta = doc.metadata
    parts = [str(meta[k]) for k in ("court_name", "file_number", "date") if meta.get(k)]
    if meta.get("ecli"):
        parts.append(f"ECLI: {meta['ecli']}")
    if meta.get("section_heading"):
        parts.append(str(meta["section_heading"]))
    return " – ".join(parts) if parts else "Gerichtsentscheidung"


def _snippet(
    index: int,
    label: str,
    header: str,
    url: str,
    content: str,
    max_chars: int = config.RETRIEVAL_SNIPPET_MAX_CHARS,
) -> str:
    # Header/url are retrieved metadata (untrusted) — sanitise them too, not just the
    # body, so a forged role header/delimiter in a scraped field can't inject. The
    # header keeps its own parentheses (the greedy citation regex tolerates them);
    # only the url is stripped of parens, since it is the regex's closing delimiter.
    safe_header = sanitise_text(header, _HEADER_MAX_CHARS)
    safe_url = sanitise_text(url, _URL_MAX_CHARS).replace("(", "").replace(")", "")
    text = sanitise_text(content, max_chars)
    return f"### Quelle {index} [{label}]: {safe_header} ({safe_url})\n{text}"


@tool
def search_law(query: str) -> str:
    """Durchsucht deutsches Mietrecht – Gesetzestexte (BGB, BetrKV, WoGG) UND
    Gerichtsentscheidungen – und liefert die einschlägigen Stellen aus beiden Quellen.

    Rufe dieses Werkzeug bei JEDER materiellen Rechtsfrage auf. EIN Aufruf durchsucht
    sowohl den Gesetzeswortlaut als auch die Rechtsprechung – du musst keine zwei
    getrennten Suchen ausführen. Werte Gesetz und Rechtsprechung gemeinsam aus.

    Args:
        query: Suchanfrage in natürlicher Sprache (z. B. "Kündigungsfrist Mieter",
            "Eigenbedarfskündigung Härtefall").
    """
    per_corpus_k = config.SEARCH_LAW_PER_CORPUS_K
    statute_docs = get_hybrid_retriever(config.STATUTES_COLLECTION).invoke(query)[:per_corpus_k]
    case_docs = get_hybrid_retriever(config.CASE_LAW_COLLECTION).invoke(query)[:per_corpus_k]

    blocks: list[str] = []
    index = 1
    if statute_docs:
        blocks.append("GESETZE:")
        for doc in statute_docs:
            blocks.append(
                _snippet(
                    index, _LABEL_STATUTE, _statute_header(doc),
                    str(doc.metadata.get("url", "")), doc.page_content,
                )
            )
            index += 1
    if case_docs:
        blocks.append("RECHTSPRECHUNG:")
        for doc in case_docs:
            blocks.append(
                _snippet(
                    index, _LABEL_CASE_LAW, _case_law_header(doc),
                    str(doc.metadata.get("url", "")).rstrip("/"), doc.page_content,
                    max_chars=config.CASE_LAW_PARENT_SNIPPET_MAX_CHARS,
                )
            )
            index += 1

    body = "\n\n".join(blocks) if blocks else _NO_RESULTS
    return delimit(body, source="law")


def parse_citations(tool_output: str) -> list[dict[str, str]]:
    """Extract `{source, header, url}` citations from a `search_law` tool output.

    Reads each snippet's `[Gesetz]/[Rechtsprechung]` tag so a mixed-source block maps
    every citation back to its collection. Returns `[]` for `_NO_RESULTS` or
    non-retrieval tool output.
    """
    return [
        {
            "source": _LABEL_TO_SOURCE[m.group("label")],
            "header": m.group("header"),
            "url": m.group("url"),
        }
        for m in _CITATION_RE.finditer(tool_output)
    ]
