"""Authentication: bcrypt password hashing, JWT session tokens, and users-table CRUD.

The `users` table (created in `src.db.setup_db`) is the single identity source. The
authenticated `username` replaces the old client-supplied `user_name` everywhere: it
is the namespace key for long-term memory, feedback and contracts. `role` here is the
authorisation role (`user`/`admin`) — orthogonal to the legal persona
(mieter/vermieter/jurist), which is a per-user preference stored alongside.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from src import config
from src.db import get_connection

# bcrypt truncates silently beyond 72 bytes — reject instead.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_CHARS = 8

# Usernames become store-namespace keys and URL path segments — keep them tame.
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,49}$")

_USER_COLUMNS = "id, username, display_name, password_hash, role, persona, is_active"


# --- Passwords -----------------------------------------------------------------------


def validate_password(password: str) -> str | None:
    """Return a human-readable problem with `password`, or None if acceptable."""
    if len(password) < MIN_PASSWORD_CHARS:
        return f"Passwort muss mindestens {MIN_PASSWORD_CHARS} Zeichen lang sein."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Passwort darf höchstens {MAX_PASSWORD_BYTES} Bytes lang sein."
    return None


def hash_password(password: str) -> str:
    """Bcrypt-hash `password`. Raises ValueError on an invalid password."""
    problem = validate_password(password)
    if problem:
        raise ValueError(problem)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt check (bcrypt.checkpw handles timing internally)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # malformed hash
        return False


# A fixed bcrypt hash used to equalise login timing for unknown usernames: the
# login route always runs one verify (real or against this) so response time does
# not reveal whether an account exists.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode("ascii")


# --- Tokens --------------------------------------------------------------------------


def create_token(username: str, role: str) -> str:
    """Mint an HS256 session JWT. Requires config.AUTH_SECRET to be set."""
    if not config.AUTH_SECRET:
        raise RuntimeError("AUTH_SECRET is not configured")
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(hours=config.AUTH_TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, config.AUTH_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a session JWT. Returns the claims, or None on any failure."""
    if not config.AUTH_SECRET:
        return None
    try:
        return jwt.decode(token, config.AUTH_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


# --- Users table CRUD ----------------------------------------------------------------


def normalise_username(username: str) -> str:
    """Lowercase/strip a username; raise ValueError if the result is not allowed."""
    name = username.strip().lower()
    if not _USERNAME_RE.match(name):
        raise ValueError(
            "Benutzername: 2-50 Zeichen, nur Kleinbuchstaben, Ziffern, '._-', "
            "beginnend mit Buchstabe/Ziffer."
        )
    return name


def _row_to_user(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = [c.strip() for c in _USER_COLUMNS.split(",")]
    return dict(zip(keys, row, strict=True))


def get_user(username: str) -> dict[str, Any] | None:
    """Fetch one user row as a dict, or None."""
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE username = %s",  # noqa: S608 — constant columns
            (username.strip().lower(),),
        ).fetchone()
    return _row_to_user(row) if row else None


def list_users() -> list[dict[str, Any]]:
    """All users (without password hashes), newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT username, display_name, role, persona, is_active, created_at "
            "FROM users ORDER BY created_at DESC"
        ).fetchall()
    keys = ["username", "display_name", "role", "persona", "is_active", "created_at"]
    return [dict(zip(keys, row, strict=True)) for row in rows]


def create_user(
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
    persona: str = "mieter",
) -> dict[str, Any]:
    """Insert a new user. Raises ValueError on bad input or duplicate username."""
    name = normalise_username(username)
    if role not in ("user", "admin"):
        raise ValueError("Rolle muss 'user' oder 'admin' sein.")
    password_hash = hash_password(password)
    with get_connection() as conn:
        conn.autocommit = True
        existing = conn.execute("SELECT 1 FROM users WHERE username = %s", (name,)).fetchone()
        if existing:
            raise ValueError(f"Benutzername '{name}' ist bereits vergeben.")
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, persona) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, display_name.strip() or name, password_hash, role, persona),
        )
    user = get_user(name)
    assert user is not None
    return user


def set_active(username: str, is_active: bool) -> bool:
    """Activate/deactivate a user. Returns False if the user does not exist."""
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "UPDATE users SET is_active = %s WHERE username = %s",
            (is_active, username.strip().lower()),
        )
        return cur.rowcount > 0


def update_persona(username: str, persona: str) -> bool:
    """Persist the user's legal-persona preference. Returns False if user missing."""
    if persona not in ("mieter", "vermieter", "jurist"):
        raise ValueError("Unbekannte Rolle (Persona).")
    with get_connection() as conn:
        conn.autocommit = True
        cur = conn.execute(
            "UPDATE users SET persona = %s WHERE username = %s",
            (persona, username.strip().lower()),
        )
        return cur.rowcount > 0


def seed_admin() -> bool:
    """Insert the predefined admin account if missing (never overwrites).

    Uses config.ADMIN_USERNAME / config.ADMIN_PASSWORD. Returns True if a row was
    created. No-op (False) when the password is unset or the user already exists.
    """
    if not config.ADMIN_PASSWORD:
        return False
    name = normalise_username(config.ADMIN_USERNAME)
    if get_user(name) is not None:
        return False
    create_user(name, "Admin", config.ADMIN_PASSWORD, role="admin")
    return True
