"""Case ("Mietfall-Akte") persistence: cases, case documents, and legal deadlines.

Real SQL tables (created in `src.db.setup_db`), not the KV memory store, because
deadlines need due-date ordering and cases need per-user listings with aggregates.

Ownership model: `get_case(username, case_id)` is THE ownership gate — API routes
resolve it first (404 on miss/foreign case) and only then act on the raw `case_id`.
Agent tools may call the raw `add_*` functions directly because their `case_id`
comes from the server-derived runtime `Context`, never from the client.

Privacy note (conscious departure from "raw text never persisted"): document text is
stored — sanitised via `src.agent.security.sanitise_text` — because the agent must be
able to re-read case letters/contracts across turns.
"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor
from psycopg.types.json import Json

from src.agent.security import sanitise_text
from src.db import get_connection

# Compact prompt-block caps, keeping injected case context bounded.
_BLOCK_MAX_DOCS = 10
_BLOCK_MAX_DEADLINES = 10
_BLOCK_TITLE_CHARS = 120

_KIND_LABELS = {"contract": "Vertrag", "letter": "Schreiben", "draft": "Entwurf"}


def _rows_to_dicts(cur: Cursor[Any]) -> list[dict[str, Any]]:
    assert cur.description is not None
    keys = [c.name for c in cur.description]
    return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def _row_to_dict(cur: Cursor[Any]) -> dict[str, Any] | None:
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


# --- Cases ---------------------------------------------------------------------------

_CASE_COLUMNS = (
    "c.id::text AS id, c.title, c.status, c.thread_id::text AS thread_id, "
    "c.created_at::text AS created_at"
)


def create_case(username: str, title: str) -> dict[str, Any] | None:
    """Create a case for `username`. Returns the row, or None if the user is unknown."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "INSERT INTO cases (user_id, title) "
            "SELECT id, %s FROM users WHERE username = %s "
            "RETURNING id::text AS id, title, status, thread_id::text AS thread_id, "
            "created_at::text AS created_at",
            (title.strip(), username),
        )
        return _row_to_dict(cur)


def list_cases(username: str) -> list[dict[str, Any]]:
    """The user's cases, newest first, with deadline aggregates for the list view."""
    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT {_CASE_COLUMNS}, "  # noqa: S608 — constant column list
            "  (SELECT count(*) FROM deadlines d "
            "     WHERE d.case_id = c.id AND d.status = 'open') AS open_deadlines, "
            "  (SELECT min(d.due_date)::text FROM deadlines d "
            "     WHERE d.case_id = c.id AND d.status = 'open') AS next_due, "
            "  (SELECT count(*) FROM case_documents cd WHERE cd.case_id = c.id) AS document_count "
            "FROM cases c JOIN users u ON u.id = c.user_id "
            "WHERE u.username = %s ORDER BY c.created_at DESC",
            (username,),
        )
        return _rows_to_dicts(cur)


def get_case(username: str, case_id: str) -> dict[str, Any] | None:
    """The ownership gate: the case row iff it belongs to `username`, else None."""
    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT {_CASE_COLUMNS} "  # noqa: S608 — constant column list
            "FROM cases c JOIN users u ON u.id = c.user_id "
            "WHERE c.id = %s AND u.username = %s",
            (case_id, username),
        )
        return _row_to_dict(cur)


def delete_case(username: str, case_id: str) -> bool:
    """Delete a case (documents/deadlines cascade). Returns False on miss/foreign case."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "DELETE FROM cases c USING users u "
            "WHERE c.id = %s AND c.user_id = u.id AND u.username = %s",
            (case_id, username),
        )
        return cur.rowcount > 0


# --- Documents -----------------------------------------------------------------------

_DOC_META_COLUMNS = (
    "id::text AS id, case_id::text AS case_id, kind, filename, title, "
    "analysis, sources, created_at::text AS created_at"
)


def add_document(
    case_id: str,
    *,
    kind: str,
    title: str,
    content: str,
    filename: str | None = None,
    analysis: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Insert a document into a case (ownership must already be checked)."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "INSERT INTO case_documents (case_id, kind, filename, title, content, analysis, sources) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            f"RETURNING {_DOC_META_COLUMNS}",  # noqa: S608 — constant column list
            (
                case_id,
                kind,
                filename,
                title.strip(),
                content,
                Json(analysis) if analysis is not None else None,
                Json(sources) if sources is not None else None,
            ),
        )
        row = _row_to_dict(cur)
        assert row is not None
        return row


def list_documents(case_id: str) -> list[dict[str, Any]]:
    """Document metadata (no content) for a case, oldest first."""
    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT {_DOC_META_COLUMNS} FROM case_documents "  # noqa: S608
            "WHERE case_id = %s ORDER BY created_at",
            (case_id,),
        )
        return _rows_to_dicts(cur)


def get_document(case_id: str, doc_id: str) -> dict[str, Any] | None:
    """One document including its full content, or None."""
    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT {_DOC_META_COLUMNS}, content FROM case_documents "  # noqa: S608
            "WHERE id = %s AND case_id = %s",
            (doc_id, case_id),
        )
        return _row_to_dict(cur)


def set_document_analysis(doc_id: str, analysis: dict[str, Any]) -> None:
    """Persist the agent's analysis (summary / contract findings) for a document."""
    with get_connection() as conn:
        conn.autocommit = True
        conn.execute(
            "UPDATE case_documents SET analysis = %s WHERE id = %s",
            (Json(analysis), doc_id),
        )


def delete_document(case_id: str, doc_id: str) -> bool:
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "DELETE FROM case_documents WHERE id = %s AND case_id = %s", (doc_id, case_id)
        )
        return cur.rowcount > 0


# --- Deadlines -----------------------------------------------------------------------

_DEADLINE_COLUMNS = (
    "id::text AS id, case_id::text AS case_id, document_id::text AS document_id, "
    "title, due_date::text AS due_date, note, status, created_by, "
    "created_at::text AS created_at"
)


def add_deadline(
    case_id: str,
    *,
    title: str,
    due_date: str,
    note: str = "",
    document_id: str | None = None,
    created_by: str = "agent",
) -> dict[str, Any]:
    """Insert a legal deadline (Frist). `due_date` must be ISO YYYY-MM-DD."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "INSERT INTO deadlines (case_id, document_id, title, due_date, note, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            f"RETURNING {_DEADLINE_COLUMNS}",  # noqa: S608 — constant column list
            (case_id, document_id, title.strip(), due_date, note, created_by),
        )
        row = _row_to_dict(cur)
        assert row is not None
        return row


def list_deadlines(case_id: str) -> list[dict[str, Any]]:
    """All deadlines for a case, soonest first."""
    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT {_DEADLINE_COLUMNS} FROM deadlines "  # noqa: S608
            "WHERE case_id = %s ORDER BY due_date, created_at",
            (case_id,),
        )
        return _rows_to_dicts(cur)


def set_deadline_status(case_id: str, deadline_id: str, status: str) -> bool:
    if status not in ("open", "done", "missed"):
        raise ValueError("Status muss 'open', 'done' oder 'missed' sein.")
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "UPDATE deadlines SET status = %s WHERE id = %s AND case_id = %s",
            (status, deadline_id, case_id),
        )
        return cur.rowcount > 0


def delete_deadline(case_id: str, deadline_id: str) -> bool:
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "DELETE FROM deadlines WHERE id = %s AND case_id = %s", (deadline_id, case_id)
        )
        return cur.rowcount > 0


# --- Prompt context ------------------------------------------------------------------


def build_context_block(
    case: dict[str, Any],
    documents: list[dict[str, Any]],
    deadlines: list[dict[str, Any]],
) -> str:
    """Format the case summary injected into the system prompt.

    Built exclusively from our own structured fields (titles, kinds, dates) — never
    from document content, which stays behind `<untrusted_context>` delimiting.
    Split out from `case_context_block` so it is testable without a database.
    """
    # Titles are user-supplied (case title, uploaded filename, deadline title); this
    # block is injected into the system prompt, so sanitise them (neutralise forged
    # role headers / delimiters) even though they are not document *content*.
    def _title(value: str) -> str:
        return sanitise_text(value, _BLOCK_TITLE_CHARS)

    lines = [f"Aktuelle Akte: {_title(case['title'])} (Status: {case['status']})"]
    if documents:
        lines.append("Dokumente in der Akte:")
        for doc in documents[:_BLOCK_MAX_DOCS]:
            label = _KIND_LABELS.get(doc["kind"], doc["kind"])
            analysed = " — bereits analysiert" if doc.get("analysis") else ""
            lines.append(f"- [{label}] {_title(doc['title'])}{analysed}")
    open_deadlines = [d for d in deadlines if d["status"] == "open"]
    if open_deadlines:
        lines.append("Offene Fristen:")
        for d in open_deadlines[:_BLOCK_MAX_DEADLINES]:
            lines.append(f"- {d['due_date']}: {_title(d['title'])}")
    else:
        lines.append("Offene Fristen: keine")
    return "\n".join(lines)


def case_context_block(username: str, case_id: str) -> str:
    """The prompt block for a case, or "" when the case is missing/foreign."""
    case = get_case(username, case_id)
    if case is None:
        return ""
    return build_context_block(case, list_documents(case_id), list_deadlines(case_id))
