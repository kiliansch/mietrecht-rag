"""Sanitisation and delimiting helpers for untrusted tool/retrieved text (OWASP LLM05).

Retrieved document text (statutes, case law) and other tool output are DATA, never
instructions. Every retrieval tool must pass its output through `sanitise_text` and
`delimit` before returning it, so the agent prompt can frame `<untrusted_context>`
blocks as evidence-only and the model cannot be steered by injected role headers or
forged delimiters embedded in the source text.
"""

from __future__ import annotations

import re

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Fake chat role headers (e.g. "System:", "Assistant:") at the start of a line, a
# common prompt-injection pattern in scraped/retrieved text.
_ROLE_HEADER_RE = re.compile(r"(?im)^[ \t]*(system|assistant|user|human|developer)\s*:")
# Characters that could break out of the `source="..."` delimiter attribute.
_SOURCE_UNSAFE_RE = re.compile(r'["<>\r\n]+')
_SOURCE_MAX_CHARS = 120


def sanitise_text(text: str, max_chars: int) -> str:
    """Strip control characters, neutralise fake role headers, and cap to `max_chars`."""
    cleaned = _CONTROL_CHARS_RE.sub("", text)
    cleaned = cleaned.replace("<untrusted_context", "<untrusted-context").replace(
        "</untrusted_context>", "</untrusted-context>"
    )
    cleaned = _ROLE_HEADER_RE.sub(lambda m: f"[{m.group(1)}]", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "…"
    return cleaned


def delimit(text: str, source: str) -> str:
    """Wrap already-sanitised `text` in a labelled untrusted-content block.

    The `source` label is often user-controlled (e.g. an uploaded filename), so it
    is stripped of quotes/angle-brackets/newlines and capped to keep it from
    breaking out of the `source="..."` attribute."""
    safe_source = _SOURCE_UNSAFE_RE.sub("", source)[:_SOURCE_MAX_CHARS]
    return f'<untrusted_context source="{safe_source}">\n{text}\n</untrusted_context>'
