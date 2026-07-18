"""Pydantic request/response DTOs for the API. Data shapes only — no logic.

Identity note: no request body carries a user name. The acting user is always
derived server-side from the JWT (`src.api.deps.get_current_user`).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class PersonaUpdateRequest(BaseModel):
    persona: str


class CreateUserRequest(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: str = "user"


class UserActiveRequest(BaseModel):
    is_active: bool


class ValidateRequest(BaseModel):
    text: str


class ValidateResponse(BaseModel):
    error: str | None


class ChatRequest(BaseModel):
    # Free chat: the client owns thread_id. Case chat: case_id is set and the
    # server uses the case's own thread (client thread_id is ignored).
    thread_id: str | None = None
    case_id: str | None = None
    role: str = "mieter"
    model: str
    message: str
    language: str = "de"  # answer language ("de" | "en"); retrieval stays German

    @field_validator("thread_id", "case_id")
    @classmethod
    def _ids_are_uuids(cls, v: str | None) -> str | None:
        # Validate client-owned ids so they can't address an arbitrary
        # long-term-memory / checkpoint namespace.
        if v is not None:
            uuid.UUID(v)
        return v


class ReviewRequest(BaseModel):
    role: str = "mieter"


class FeedbackRequest(BaseModel):
    thread_id: str
    question: str
    answer: str
    rating: int
    comment: str = ""


class ResumeRequest(BaseModel):
    """Continue a thread parked on a tool-approval interrupt."""

    # Case chat resumes resolve the thread from the case; free chat sends thread_id.
    case_id: str | None = None
    thread_id: str | None = None
    interrupt_id: str
    decision: str  # "approve" | "reject"
    language: str = "de"  # answer language ("de" | "en"); must survive the resume
    # When the paused turn was a document analysis: persist the continuation's final
    # answer as that document's analysis summary (must belong to the case).
    document_id: str | None = None

    @field_validator("thread_id", "case_id", "document_id")
    @classmethod
    def _ids_are_uuids(cls, v: str | None) -> str | None:
        if v is not None:
            uuid.UUID(v)
        return v

    @field_validator("decision")
    @classmethod
    def _decision_is_known(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("decision muss 'approve' oder 'reject' sein")
        return v


class CaseCreateRequest(BaseModel):
    title: str


class ChatRenameRequest(BaseModel):
    title: str


class DeadlineCreateRequest(BaseModel):
    title: str
    due_date: str  # ISO YYYY-MM-DD, validated in the router
    note: str = ""


class DeadlineStatusRequest(BaseModel):
    status: str  # open | done | missed


class ClauseInfo(BaseModel):
    index: int
    heading: str


class UploadResponse(BaseModel):
    contract_id: str
    filename: str
    risky_count: int
    total_clauses: int
    clauses: list[ClauseInfo]
