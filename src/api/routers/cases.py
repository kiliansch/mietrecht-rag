"""Case ("Mietfall-Akte") routes: CRUD, document ingestion + analysis, deadlines.

Every route resolves ownership through `cases_store.get_case(username, case_id)`
first (404 on miss/foreign case) before touching documents or deadlines.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from src import config
from src.agent.graph import get_store
from src.agent.graph import stream as agent_stream
from src.agent.prompts import build_letter_analysis_instruction
from src.agent.security import delimit, sanitise_text
from src.api.deps import CurrentUser, check_rate_limit, get_current_user
from src.api.schemas import CaseCreateRequest, DeadlineCreateRequest, DeadlineStatusRequest
from src.api.sse import SSE_HEADERS, sse_event
from src.api.streaming import agent_sse_events
from src.cases import store as cases_store
from src.contracts.extract_facts import extract_tenancy_facts
from src.contracts.parse import extract_text
from src.contracts.review import Finding, review_clause
from src.contracts.segment import risk_filter, segment_clauses
from src.memory import store as memory_store
from src.usage import make_usage_callback, summarize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cases", tags=["cases"])

_DOCUMENT_KINDS = ("letter", "contract")


def _require_case(user: CurrentUser, case_id: str) -> dict[str, Any]:
    case = cases_store.get_case(user.username, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Akte nicht gefunden.")
    return case


def _require_document(case_id: str, doc_id: str) -> dict[str, Any]:
    doc = cases_store.get_document(case_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    return doc


# --- Case CRUD -----------------------------------------------------------------------


@router.get("")
def cases_list(user: Annotated[CurrentUser, Depends(get_current_user)]) -> list[dict[str, Any]]:
    return cases_store.list_cases(user.username)


@router.post("", status_code=201)
def cases_create(
    req: CaseCreateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Titel darf nicht leer sein.")
    case = cases_store.create_case(user.username, title)
    if case is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden.")
    return case


@router.get("/{case_id}")
def cases_get(
    case_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """The case with its documents (metadata only) and deadlines — one call per view."""
    case = _require_case(user, case_id)
    return {
        **case,
        "documents": cases_store.list_documents(case["id"]),
        "deadlines": cases_store.list_deadlines(case["id"]),
    }


@router.delete("/{case_id}", status_code=204)
def cases_delete(
    case_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    if not cases_store.delete_case(user.username, case_id):
        raise HTTPException(status_code=404, detail="Akte nicht gefunden.")
    return Response(status_code=204)


# --- Documents -----------------------------------------------------------------------


@router.post("/{case_id}/documents", status_code=201)
async def documents_upload(
    case_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "letter",
) -> dict[str, Any]:
    """Ingest a legal communication or contract into the case (sanitised text)."""
    case = _require_case(user, case_id)
    if kind not in _DOCUMENT_KINDS:
        raise HTTPException(status_code=422, detail="kind muss 'letter' oder 'contract' sein.")

    # Read at most one byte past the cap so an oversized upload is rejected without
    # buffering the whole (possibly multi-GB) body into memory.
    raw = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß (max. {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    filename = file.filename or ("Vertrag" if kind == "contract" else "Schreiben")
    try:
        text = extract_text(raw, filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=f"Dateiformat nicht unterstützt: {exc}") from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"System-Voraussetzung fehlt: {exc}") from exc

    # Untrusted document text: sanitise before persisting (OWASP LLM05).
    content = sanitise_text(text, config.CASE_DOC_MAX_CHARS)

    # Contract uploads may yield tenancy facts (rent, floor area) for the profile.
    # Surface what was extracted so the UI can confirm it instead of failing silently.
    facts: dict[str, float] = {}
    if kind == "contract":
        facts = extract_tenancy_facts(text)
        if facts:
            try:
                memory_store.write_facts(get_store(), user.username, facts, source="contract")
            except Exception:
                logger.exception("Failed to persist contract-derived tenancy facts")

    document = cases_store.add_document(
        case["id"], kind=kind, title=filename, content=content, filename=filename
    )
    return {**document, "extracted_facts": facts}


@router.get("/{case_id}/documents/{doc_id}")
def documents_get(
    case_id: str,
    doc_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    case = _require_case(user, case_id)
    return _require_document(case["id"], doc_id)


@router.delete("/{case_id}/documents/{doc_id}", status_code=204)
def documents_delete(
    case_id: str,
    doc_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    case = _require_case(user, case_id)
    if not cases_store.delete_document(case["id"], doc_id):
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    return Response(status_code=204)


@router.post("/{case_id}/documents/{doc_id}/analyse")
def documents_analyse(
    case_id: str,
    doc_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream the agent's analysis of a letter on the case's own thread.

    The turn lives on the case thread, so follow-up chat has full context. The final
    answer is persisted as the document's analysis summary after the stream ends.
    """
    check_rate_limit(user.username)
    case = _require_case(user, case_id)
    doc = _require_document(case["id"], doc_id)
    if doc["kind"] != "letter":
        raise HTTPException(status_code=422, detail="Nur Schreiben können analysiert werden.")

    message = (
        build_letter_analysis_instruction(doc["title"])
        + "\n\n"
        + delimit(doc["content"], source=doc["title"])
    )
    usage_cb = make_usage_callback()
    updates = agent_stream(
        message,
        thread_id=case["thread_id"],
        user_name=user.username,
        role=user.persona,
        model=config.LLM_MAIN,
        enabled_tools=(),
        case_id=case["id"],
        task="letter_analysis",
        callbacks=[usage_cb],
    )

    def persist_summary(text: str) -> None:
        try:
            cases_store.set_document_analysis(doc["id"], {"summary": text})
        except Exception:
            logger.exception("Failed to persist letter analysis")

    return StreamingResponse(
        agent_sse_events(updates, on_final=persist_summary, usage_cb=usage_cb),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _contract_review_events(
    case: dict[str, Any], doc: dict[str, Any], role: str, username: str
) -> Iterator[str]:
    """Per-clause review of a case contract; findings persist into the document."""
    clauses = segment_clauses(doc["content"])
    risky = risk_filter(clauses)
    total = len(risky)
    if total == 0:
        yield sse_event("summary", {"wirksam": 0, "bedenklich": 0, "unwirksam": 0, "total_clauses": len(clauses)})
        yield sse_event("done", {})
        return

    usage_cb = make_usage_callback()
    findings: list[Finding] = []
    for i, clause in enumerate(risky):
        heading = clause["heading"] or f"Klausel {clause['index'] + 1}"
        yield sse_event("progress", {"index": i, "total": total, "heading": heading})
        try:
            finding = review_clause(
                clause,
                thread_id=str(uuid_mod.uuid4()),
                user_name=username,
                role=role,
                usage_cb=usage_cb,
            )
        except Exception:  # noqa: BLE001 — one clause failing must not abort the rest
            logger.exception("Clause review failed")
            finding = Finding(
                clause=clause,
                verdict="bedenklich",
                reasoning="Diese Klausel konnte nicht geprüft werden. Bitte erneut versuchen.",
                sources=[],
            )
        findings.append(finding)
        yield sse_event(
            "finding",
            {
                "heading": heading,
                "verdict": finding["verdict"],
                "reasoning": finding["reasoning"],
                "sources": finding["sources"],
            },
        )

    summary = {v: sum(1 for f in findings if f["verdict"] == v) for v in ("wirksam", "bedenklich", "unwirksam")}
    yield sse_event("summary", {**summary, "total_clauses": len(clauses)})
    try:
        cases_store.set_document_analysis(
            doc["id"],
            {
                "findings": [
                    {
                        "heading": f["clause"]["heading"] or f"Klausel {f['clause']['index'] + 1}",
                        "verdict": f["verdict"],
                        "reasoning": f["reasoning"],
                        "sources": f["sources"],
                    }
                    for f in findings
                ],
                "summary": summary,
                "total_clauses": len(clauses),
            },
        )
    except Exception:
        logger.exception("Failed to persist contract review")
    usage = summarize(usage_cb)
    yield sse_event(
        "usage",
        {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]},
    )
    yield sse_event("done", {})


@router.post("/{case_id}/documents/{doc_id}/review")
def documents_review(
    case_id: str,
    doc_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream the per-clause review of a case contract (same events as the old flow)."""
    check_rate_limit(user.username)
    case = _require_case(user, case_id)
    doc = _require_document(case["id"], doc_id)
    if doc["kind"] != "contract":
        raise HTTPException(status_code=422, detail="Nur Verträge können geprüft werden.")
    return StreamingResponse(
        _contract_review_events(case, doc, user.persona, user.username),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# --- Deadlines -----------------------------------------------------------------------


def _validate_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="due_date muss das Format JJJJ-MM-TT haben."
        ) from exc


@router.post("/{case_id}/deadlines", status_code=201)
def deadlines_create(
    case_id: str,
    req: DeadlineCreateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    case = _require_case(user, case_id)
    if not req.title.strip():
        raise HTTPException(status_code=422, detail="Titel darf nicht leer sein.")
    return cases_store.add_deadline(
        case["id"],
        title=req.title,
        due_date=_validate_iso_date(req.due_date),
        note=req.note,
        created_by="user",
    )


@router.patch("/{case_id}/deadlines/{deadline_id}")
def deadlines_set_status(
    case_id: str,
    deadline_id: str,
    req: DeadlineStatusRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    case = _require_case(user, case_id)
    try:
        ok = cases_store.set_deadline_status(case["id"], deadline_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Frist nicht gefunden.")
    return {"id": deadline_id, "status": req.status}


@router.delete("/{case_id}/deadlines/{deadline_id}", status_code=204)
def deadlines_delete(
    case_id: str,
    deadline_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    case = _require_case(user, case_id)
    if not cases_store.delete_deadline(case["id"], deadline_id):
        raise HTTPException(status_code=404, detail="Frist nicht gefunden.")
    return Response(status_code=204)
