"""Auth unit tests: password hashing and JWT round-trips. Offline (no DB)."""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from src import auth, config


def test_password_hash_roundtrip() -> None:
    h = auth.hash_password("geheim-passwort")
    assert h != "geheim-passwort"
    assert auth.verify_password("geheim-passwort", h)
    assert not auth.verify_password("falsch-passwort", h)


def test_password_rules() -> None:
    assert auth.validate_password("kurz") is not None  # too short
    assert auth.validate_password("a" * 100) is not None  # > 72 bytes
    assert auth.validate_password("acht-zeichen") is None
    with pytest.raises(ValueError):
        auth.hash_password("kurz")


def test_verify_password_malformed_hash_is_false() -> None:
    assert not auth.verify_password("whatever-pw", "not-a-bcrypt-hash")


def test_token_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    token = auth.create_token("demo", "admin")
    claims = auth.decode_token(token)
    assert claims is not None
    assert claims["sub"] == "demo"
    assert claims["role"] == "admin"


def test_token_bad_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    token = auth.create_token("demo", "user")
    monkeypatch.setattr(config, "AUTH_SECRET", "other-secret-0123456789abcdef-012345678")
    assert auth.decode_token(token) is None


def test_token_expiry_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    expired = pyjwt.encode(
        {"sub": "demo", "role": "user", "exp": datetime.now(UTC) - timedelta(hours=1)},
        "test-secret-0123456789abcdef-0123456789",
        algorithm="HS256",
    )
    assert auth.decode_token(expired) is None


def test_token_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUTH_SECRET", "")
    with pytest.raises(RuntimeError):
        auth.create_token("demo", "user")
    assert auth.decode_token("anything") is None


def test_normalise_username() -> None:
    assert auth.normalise_username("  Demo ") == "demo"
    assert auth.normalise_username("anna.m-2") == "anna.m-2"
    for bad in ("", "a", "UPPER SPACE", "-leading", "ä-umlaut", "x" * 51):
        with pytest.raises(ValueError):
            auth.normalise_username(bad)
