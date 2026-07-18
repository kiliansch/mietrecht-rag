"""Chat-history ("Verlauf") route tests. Store + graph helper are monkeypatched."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src import auth, config
from src.api.app import create_app

USER = {
    "id": 5,
    "username": "casey",
    "display_name": "Casey",
    "password_hash": "x",
    "role": "user",
    "persona": "mieter",
    "is_active": True,
}
TID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    monkeypatch.setattr(auth, "get_user", lambda name: USER if name == "casey" else None)
    return TestClient(create_app())


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token('casey', 'user')}"}


def _mock(monkeypatch: pytest.MonkeyPatch, name: str, value: Any) -> None:
    monkeypatch.setattr(f"src.api.routers.chat_history.{name}", value)


def test_chats_require_auth(client: TestClient) -> None:
    assert client.get("/api/chats").status_code == 401


def test_chats_list(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, "chat_store.list_threads",
          lambda u: [{"thread_id": TID, "title": "Kaution?", "created_at": "x", "updated_at": "y"}])
    body = client.get("/api/chats", headers=headers()).json()
    assert body[0]["title"] == "Kaution?"


def test_chat_messages_404_when_not_owned(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, "chat_store.owns_thread", lambda u, t: False)
    res = client.get(f"/api/chats/{TID}/messages", headers=headers())
    assert res.status_code == 404


def test_chat_messages_reconstructs(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, "chat_store.owns_thread", lambda u, t: True)
    _mock(monkeypatch, "get_thread_messages", lambda t: [
        {"role": "user", "content": "Wie hoch darf die Kaution sein?", "sources": []},
        {"role": "assistant", "content": "Höchstens drei Monatsmieten.",
         "sources": [{"source": "statutes", "header": "§ 551", "url": "u"}]},
    ])
    body = client.get(f"/api/chats/{TID}/messages", headers=headers()).json()
    assert body[1]["role"] == "assistant"
    assert body[1]["sources"][0]["source"] == "statutes"


def test_chat_delete(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, "chat_store.delete_thread", lambda u, t: True)
    assert client.delete(f"/api/chats/{TID}", headers=headers()).status_code == 204
    _mock(monkeypatch, "chat_store.delete_thread", lambda u, t: False)
    assert client.delete(f"/api/chats/{TID}", headers=headers()).status_code == 404
