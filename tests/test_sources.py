"""Source-viewer route tests. DB is monkeypatched so these run offline."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src import auth, config
from src.api.app import create_app

USER = {
    "id": 3,
    "username": "casey",
    "display_name": "Casey",
    "password_hash": "x",
    "role": "user",
    "persona": "mieter",
    "is_active": True,
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-0123456789abcdef-0123456789")
    monkeypatch.setattr(auth, "get_user", lambda name: USER if name == "casey" else None)
    return TestClient(create_app())


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token('casey', 'user')}"}


class _FakeConn:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def execute(self, *_a: Any, **_k: Any) -> "_FakeConn":
        return self

    def fetchall(self) -> list[Any]:
        return self._rows


def test_sources_requires_auth(client: TestClient) -> None:
    assert client.get("/api/sources?collection=statutes&url=x").status_code == 401


def test_sources_rejects_unknown_collection(client: TestClient) -> None:
    res = client.get("/api/sources?collection=bogus&url=x", headers=headers())
    assert res.status_code == 422


def test_sources_404_when_no_rows(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.api.routers.sources.db.get_connection", lambda: _FakeConn([]))
    res = client.get("/api/sources?collection=statutes&url=missing", headers=headers())
    assert res.status_code == 404


def test_sources_reassembles_statute_in_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Rows arrive out of order; the route sorts by chunk_id's numeric parts.
    rows = [
        ("(2) Zweiter Absatz.", {"chunk_id": "§ 551_Abs. 2_1", "absatz": "Abs. 2",
                                  "section": "§ 551", "title": "Mietsicherheiten", "url": "u/551"}),
        ("(1) Erster Absatz.", {"chunk_id": "§ 551_Abs. 1_1", "absatz": "Abs. 1",
                                 "section": "§ 551", "title": "Mietsicherheiten", "url": "u/551"}),
    ]
    monkeypatch.setattr("src.api.routers.sources.db.get_connection", lambda: _FakeConn(rows))
    body = client.get("/api/sources?collection=statutes&url=u/551", headers=headers()).json()
    assert body["title"] == "§ 551 – Mietsicherheiten"
    assert [b["heading"] for b in body["blocks"]] == ["Abs. 1", "Abs. 2"]
    assert body["blocks"][0]["content"].startswith("(1)")


def test_sources_dedupes_and_cleans_whitespace(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The corpus repeats some absätze verbatim and carries stray HTML whitespace
    # (leading indentation, blank-line runs, repeated spaces). The viewer must
    # de-duplicate blocks and tidy the text.
    messy = "\n\n            (3)   Ergänzend    gilt:\n\n\n\n   Nummer eins.\n\n"
    rows = [
        ("(1) Erster Absatz.", {"chunk_id": "§ 543_Abs. 1_1", "absatz": "Abs. 1", "url": "u/543"}),
        ("(1) Erster Absatz.", {"chunk_id": "§ 543_Abs. 1_2", "absatz": "Abs. 1", "url": "u/543"}),
        (messy, {"chunk_id": "§ 543_Abs. 3_1", "absatz": "Abs. 3", "url": "u/543"}),
    ]
    monkeypatch.setattr("src.api.routers.sources.db.get_connection", lambda: _FakeConn(rows))
    body = client.get("/api/sources?collection=statutes&url=u/543", headers=headers()).json()

    contents = [b["content"] for b in body["blocks"]]
    # The duplicated "Abs. 1" chunk is dropped.
    assert contents.count("(1) Erster Absatz.") == 1
    assert len(body["blocks"]) == 2
    # Whitespace is tidy: no leading indentation, no 3+ space runs, no blank-line runs.
    cleaned = contents[1]
    assert cleaned == "(3) Ergänzend gilt:\n\nNummer eins."
    assert not any(line.startswith(" ") for line in cleaned.splitlines())
