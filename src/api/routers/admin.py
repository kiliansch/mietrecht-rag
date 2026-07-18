"""Admin-only routes: user management + RAGAs evaluation. Gated on role == "admin"."""

from __future__ import annotations

import json
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from src import auth
from src.api.deps import EVAL_RESULTS_PATH, CurrentUser, eval_job, require_admin
from src.api.schemas import CreateUserRequest, UserActiveRequest

# Every route here requires an authenticated admin (JWT role claim + users table).
router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- User management -----------------------------------------------------------------


@router.get("/users")
def users_list(_admin: Annotated[CurrentUser, Depends(require_admin)]) -> list[dict[str, Any]]:
    """All accounts (no password hashes)."""
    return auth.list_users()


@router.post("/users", status_code=201)
def users_create(
    req: CreateUserRequest,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Create an account (no self-registration — admin is the only entry point)."""
    try:
        user = auth.create_user(req.username, req.display_name, req.password, role=req.role)
    except ValueError as exc:
        status = 409 if "vergeben" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    user.pop("password_hash", None)
    user.pop("id", None)
    return user


@router.patch("/users/{username}")
def users_set_active(
    username: str,
    req: UserActiveRequest,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Activate/deactivate an account. Admins cannot deactivate themselves."""
    if username.strip().lower() == admin.username and not req.is_active:
        raise HTTPException(status_code=422, detail="Eigenes Konto kann nicht deaktiviert werden.")
    if not auth.set_active(username, req.is_active):
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden.")
    return {"username": username.strip().lower(), "is_active": req.is_active}


# --- Evaluation ----------------------------------------------------------------------


@router.get("/eval/results")
def eval_results(_admin: Annotated[CurrentUser, Depends(require_admin)]) -> dict[str, Any] | None:
    """Return the last saved evaluation results, or null."""
    if EVAL_RESULTS_PATH.exists():
        return json.loads(EVAL_RESULTS_PATH.read_text(encoding="utf-8"))
    return None


@router.post("/eval/run", status_code=202)
def eval_run(_admin: Annotated[CurrentUser, Depends(require_admin)]) -> dict[str, str]:
    """Kick off the (minutes-long) evaluation in the background. Single-flight."""
    if not eval_job.start():
        return {"status": "running"}
    threading.Thread(target=eval_job.run, daemon=True).start()
    return {"status": "started"}


@router.get("/eval/status")
def eval_status(_admin: Annotated[CurrentUser, Depends(require_admin)]) -> dict[str, Any]:
    """Poll the background eval job."""
    return {"status": eval_job.status, "results": eval_job.results, "error": eval_job.error}
