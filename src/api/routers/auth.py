"""Login and current-user endpoints (JWT bearer sessions)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src import auth, config
from src.api.deps import CurrentUser, check_login_rate_limit, get_current_user
from src.api.schemas import LoginRequest, PersonaUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(user: CurrentUser) -> dict[str, Any]:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "persona": user.persona,
    }


@router.post("/login")
def login(req: LoginRequest, request: Request) -> dict[str, Any]:
    """Verify credentials and mint a session token.

    Deliberately generic 401 (no username enumeration — including timing: an
    unknown user still incurs one bcrypt verify). Rate-limited per client IP.
    503 when auth is not configured, mirroring the old admin-gate behaviour.
    """
    if not config.AUTH_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Anmeldung ist deaktiviert (AUTH_SECRET nicht konfiguriert).",
        )
    check_login_rate_limit(request.client.host if request.client else "unknown")
    user = auth.get_user(req.username)
    # Always run one bcrypt verify (real hash or a dummy) so response time does not
    # reveal whether the username exists.
    password_hash = user["password_hash"] if user is not None else auth.DUMMY_PASSWORD_HASH
    if not auth.verify_password(req.password, password_hash) or user is None:
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Konto ist deaktiviert.")
    token = auth.create_token(user["username"], user["role"])
    current = CurrentUser(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
        persona=user["persona"],
    )
    return {"token": token, "user": _public_user(current)}


@router.get("/me")
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, Any]:
    """The authenticated user's public profile."""
    return _public_user(user)


@router.patch("/me")
def update_me(
    req: PersonaUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Persist the user's legal-persona preference (mieter/vermieter/jurist)."""
    try:
        auth.update_persona(user.username, req.persona)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**_public_user(user), "persona": req.persona}
