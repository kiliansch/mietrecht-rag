"""API-layer tests. The agent graph and the users table are monkeypatched so these
run offline (no DB/LLM). `auth_headers` mints a real JWT against a fake user row —
the same code path production requests take through `get_current_user`."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from src import auth, config
from src.agent.prompts import ROLE_LABELS
from src.api.app import create_app

FAKE_USERS: dict[str, dict[str, Any]] = {
    "demo": {
        "id": 1,
        "username": "demo",
        "display_name": "Demo",
        "password_hash": "x",
        "role": "user",
        "persona": "mieter",
        "is_active": True,
    },
    "admin": {
        "id": 2,
        "username": "admin",
        "display_name": "Admin",
        "password_hash": "x",
        "role": "admin",
        "persona": "mieter",
        "is_active": True,
    },
    "inactive": {
        "id": 3,
        "username": "inactive",
        "display_name": "Weg",
        "password_hash": "x",
        "role": "user",
        "persona": "mieter",
        "is_active": False,
    },
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.api import deps

    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    monkeypatch.setattr(auth, "get_user", lambda name: FAKE_USERS.get(name))
    deps._request_log.clear()  # the rate limiters are module-global; isolate tests
    deps._login_log.clear()
    return TestClient(create_app())


def auth_headers(username: str = "demo") -> dict[str, str]:
    user = FAKE_USERS[username]
    token = auth.create_token(user["username"], user["role"])
    return {"Authorization": f"Bearer {token}"}


# --- Public endpoints ----------------------------------------------------------------


def test_config_exposes_models_roles_thresholds(client: TestClient) -> None:
    body = client.get("/api/config").json()
    assert len(body["models"]) == len(config.LLM_CHOICES)
    assert {r["key"] for r in body["roles"]} == set(ROLE_LABELS)
    assert set(body["thresholds"]) == set(config.THRESHOLDS)


def test_validate_wraps_validation_error(client: TestClient) -> None:
    assert client.post("/api/chat/validate", json={"text": "kurz"}).json()["error"]
    ok = client.post("/api/chat/validate", json={"text": "Wie hoch darf die Kaution sein?"})
    assert ok.json()["error"] is None


# --- Auth flow -----------------------------------------------------------------------


def test_chat_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/api/chat",
        json={"thread_id": "00000000-0000-0000-0000-000000000001", "model": "m", "message": "hallo welt hier"},
    )
    assert res.status_code == 401


def test_bad_token_is_401(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert res.status_code == 401


def test_inactive_user_is_403(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers=auth_headers("inactive"))
    assert res.status_code == 403


def test_me_returns_public_profile(client: TestClient) -> None:
    body = client.get("/api/auth/me", headers=auth_headers()).json()
    assert body == {"username": "demo", "display_name": "Demo", "role": "user", "persona": "mieter"}


def test_login_disabled_without_secret(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUTH_SECRET", "")
    res = client.post("/api/auth/login", json={"username": "demo", "password": "pw"})
    assert res.status_code == 503


def test_login_success_and_generic_401(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    real_hash = auth.hash_password("korrektes-pw")
    users = {**FAKE_USERS, "demo": {**FAKE_USERS["demo"], "password_hash": real_hash}}
    monkeypatch.setattr(auth, "get_user", lambda name: users.get(name))

    ok = client.post("/api/auth/login", json={"username": "demo", "password": "korrektes-pw"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["user"]["username"] == "demo"
    assert auth.decode_token(body["token"])["sub"] == "demo"  # type: ignore[index]

    # Wrong password and unknown user return the same generic 401.
    wrong = client.post("/api/auth/login", json={"username": "demo", "password": "falsches-pw"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "egal-egal"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


# --- Chat ------------------------------------------------------------------------------


def test_chat_bad_thread_id_is_422(client: TestClient) -> None:
    res = client.post(
        "/api/chat",
        json={"thread_id": "not-a-uuid", "model": "m", "message": "hallo welt hier"},
        headers=auth_headers(),
    )
    assert res.status_code == 422


def test_chat_streams_mapped_sse_events(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen_kwargs: dict[str, Any] = {}

    def fake_stream(_msg: str, **kw: Any) -> Iterator[dict[str, Any]]:
        seen_kwargs.update(kw)
        ai = AIMessage(
            content="",
            tool_calls=[{"id": "t1", "name": "search_law", "args": {"query": "Kaution"}}],
        )
        ai.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}  # type: ignore[assignment]
        yield {"agent": {"messages": [ai]}}
        tool = ToolMessage(content="kein Treffer", tool_call_id="t1", name="search_law")
        yield {"tools": {"messages": [tool]}}
        yield {"agent": {"messages": [AIMessage(content="Die Kaution beträgt höchstens drei Monatsmieten.")]}}

    monkeypatch.setattr("src.api.routers.chat.agent_stream", fake_stream)
    # Keep this test about SSE mapping, not live thread state.
    monkeypatch.setattr("src.api.routers.chat.chat_history_store.claimed_by_other", lambda u, t: False)
    monkeypatch.setattr("src.api.routers.chat.chat_history_store.touch_thread", lambda *a: None)

    res = client.post(
        "/api/chat",
        json={
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "role": "mieter",
            "model": "m",
            "message": "Wie hoch darf die Kaution sein?",
        },
        headers=auth_headers(),
    )
    assert res.status_code == 200
    events = [line[len("event: ") :] for line in res.text.splitlines() if line.startswith("event: ")]
    assert events == ["usage", "tool_call", "tool_result", "final", "done"]
    assert "Monatsmieten" in res.text
    # Identity comes from the token, never from the request body.
    assert seen_kwargs["user_name"] == "demo"


def test_chat_rejects_thread_owned_by_another_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1: a free-chat thread_id already claimed by another user is 404 (not run)."""
    monkeypatch.setattr(
        "src.api.routers.chat.chat_history_store.claimed_by_other", lambda u, t: True
    )
    body = {
        "thread_id": "00000000-0000-0000-0000-000000000009",
        "role": "mieter",
        "model": "m",
        "message": "Wie hoch darf die Kaution sein?",
    }
    assert client.post("/api/chat", json=body, headers=auth_headers()).status_code == 404
    resume = {
        "thread_id": "00000000-0000-0000-0000-000000000009",
        "interrupt_id": "i1",
        "decision": "approve",
    }
    assert client.post("/api/chat/resume", json=resume, headers=auth_headers()).status_code == 404


def test_login_is_rate_limited(client: TestClient) -> None:
    """F2: repeated login attempts from one client are throttled with 429."""
    codes = [
        client.post("/api/auth/login", json={"username": "demo", "password": "x"}).status_code
        for _ in range(12)
    ]
    assert 429 in codes
    assert codes[-1] == 429  # once tripped, stays limited within the window


def test_resume_forwards_language(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """F6: the answer language survives an approval resume (not reset to German)."""
    seen: dict[str, Any] = {}

    def fake_resume(_rmap: dict[str, Any], **kw: Any) -> Iterator[dict[str, Any]]:
        seen.update(kw)
        yield {"agent": {"messages": [AIMessage(content="Answer: at most three months' rent.")]}}

    monkeypatch.setattr("src.api.routers.chat.resume_stream", fake_resume)
    monkeypatch.setattr(
        "src.api.routers.chat.chat_history_store.claimed_by_other", lambda u, t: False
    )
    res = client.post(
        "/api/chat/resume",
        json={
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "interrupt_id": "i1",
            "decision": "approve",
            "language": "en",
        },
        headers=auth_headers(),
    )
    assert res.status_code == 200
    assert seen["language"] == "en"


# --- Admin ----------------------------------------------------------------------------


def test_admin_routes_require_admin_role(client: TestClient) -> None:
    assert client.get("/api/admin/users").status_code == 401  # no token
    assert client.get("/api/admin/users", headers=auth_headers("demo")).status_code == 403
    assert client.get("/api/admin/eval/status", headers=auth_headers("demo")).status_code == 403


def test_admin_user_crud(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    def fake_create(username: str, display_name: str, password: str, role: str = "user") -> dict[str, Any]:
        created.update({"username": username, "role": role})
        return {
            "id": 9,
            "username": username,
            "display_name": display_name,
            "password_hash": "x",
            "role": role,
            "persona": "mieter",
            "is_active": True,
        }

    monkeypatch.setattr("src.api.routers.admin.auth.list_users", lambda: [])
    monkeypatch.setattr("src.api.routers.admin.auth.create_user", fake_create)
    monkeypatch.setattr("src.api.routers.admin.auth.set_active", lambda name, active: name == "demo")

    assert client.get("/api/admin/users", headers=auth_headers("admin")).json() == []

    res = client.post(
        "/api/admin/users",
        json={"username": "neu", "display_name": "Neu", "password": "acht-zeichen", "role": "user"},
        headers=auth_headers("admin"),
    )
    assert res.status_code == 201
    assert created == {"username": "neu", "role": "user"}
    assert "password_hash" not in res.json()

    ok = client.patch(
        "/api/admin/users/demo", json={"is_active": False}, headers=auth_headers("admin")
    )
    assert ok.json() == {"username": "demo", "is_active": False}

    missing = client.patch(
        "/api/admin/users/ghost", json={"is_active": False}, headers=auth_headers("admin")
    )
    assert missing.status_code == 404


def test_admin_cannot_deactivate_self(client: TestClient) -> None:
    res = client.patch(
        "/api/admin/users/admin", json={"is_active": False}, headers=auth_headers("admin")
    )
    assert res.status_code == 422


def test_admin_create_duplicate_is_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_dup(*_a: Any, **_kw: Any) -> dict[str, Any]:
        raise ValueError("Benutzername 'neu' ist bereits vergeben.")

    monkeypatch.setattr("src.api.routers.admin.auth.create_user", raise_dup)
    res = client.post(
        "/api/admin/users",
        json={"username": "neu", "display_name": "Neu", "password": "acht-zeichen", "role": "user"},
        headers=auth_headers("admin"),
    )
    assert res.status_code == 409
