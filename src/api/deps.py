"""Shared FastAPI dependencies and process-local state.

Holds the auth dependencies plus the pieces of state that cannot live in the
(stateless) client: the chat rate limiter, the short-lived contract-upload store, and
the background eval-job state. All are process-local — run uvicorn single-worker.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException

from src import auth

# --- Authentication ------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated request identity, loaded fresh from the users table."""

    username: str
    display_name: str
    role: str  # "user" | "admin"  (authorisation role, not the legal persona)
    persona: str  # "mieter" | "vermieter" | "jurist"


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve `Authorization: Bearer <jwt>` to a live user. 401/403 on failure.

    The user row is re-read on every request (cheap unique-index lookup) so a
    deactivated account is cut off immediately, not at token expiry.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    claims = auth.decode_token(authorization[7:].strip())
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Sitzung abgelaufen oder ungültig.")
    user = auth.get_user(str(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Unbekannter Benutzer.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Konto ist deaktiviert.")
    return CurrentUser(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
        persona=user["persona"],
    )


def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Gate admin-only routes on the authenticated role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Administratoren.")
    return user


# --- Chat rate limiter (sliding window, per user_name) -----------------------------

_RATE_LIMIT_REQUESTS = 5
_RATE_LIMIT_WINDOW = 60  # seconds
_request_log: dict[str, list[float]] = {}
_rl_lock = threading.Lock()


def check_rate_limit(user_name: str) -> None:
    """Per-user sliding-window limit on chat turns. Raises 429 when exceeded."""
    now = time.time()
    key = user_name or "anon"
    with _rl_lock:
        timestamps = [t for t in _request_log.get(key, []) if now - t < _RATE_LIMIT_WINDOW]
        if len(timestamps) >= _RATE_LIMIT_REQUESTS:
            wait = max(1, int(_RATE_LIMIT_WINDOW - (now - timestamps[0])) + 1)
            _request_log[key] = timestamps
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Zu viele Anfragen — maximal {_RATE_LIMIT_REQUESTS} pro Minute. "
                    f"Bitte warten Sie noch {wait} Sekunden."
                ),
            )
        timestamps.append(now)
        _request_log[key] = timestamps


# --- Login rate limiter (per client IP, pre-auth brute-force guard) -----------------

_LOGIN_LIMIT_REQUESTS = 10
_LOGIN_LIMIT_WINDOW = 60  # seconds
_login_log: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def check_login_rate_limit(client_ip: str) -> None:
    """Throttle login attempts per client IP (bcrypt is otherwise the only brake).

    Process-local like `check_rate_limit` (single-worker). Behind a reverse proxy
    all clients may share one peer IP, so this is a coarse brute-force brake, not a
    per-user guarantee — pair with real network-level limits in production."""
    now = time.time()
    key = client_ip or "unknown"
    with _login_lock:
        timestamps = [t for t in _login_log.get(key, []) if now - t < _LOGIN_LIMIT_WINDOW]
        if len(timestamps) >= _LOGIN_LIMIT_REQUESTS:
            wait = max(1, int(_LOGIN_LIMIT_WINDOW - (now - timestamps[0])) + 1)
            _login_log[key] = timestamps
            raise HTTPException(
                status_code=429,
                detail=f"Zu viele Anmeldeversuche. Bitte warten Sie noch {wait} Sekunden.",
            )
        timestamps.append(now)
        _login_log[key] = timestamps


# --- Background eval job state -----------------------------------------------------

EVAL_RESULTS_PATH = Path("data/eval_results.json")


class EvalJob:
    """Single-flight state for the long-running RAGAs evaluation."""

    def __init__(self) -> None:
        self.status: str = "idle"  # idle | running | done | error
        self.results: dict[str, Any] | None = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def start(self) -> bool:
        """Mark the job running. Returns False if a run is already in flight."""
        with self.lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.error = None
            return True

    def run(self) -> None:
        """Execute `run_eval` to completion, recording results or the error."""
        from src.eval.runner import run_eval

        try:
            self.results = run_eval(output_path=EVAL_RESULTS_PATH)
            self.status = "done"
        except Exception as exc:  # noqa: BLE001 — surface any failure as job state
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = "error"


eval_job = EvalJob()
