"""Tests for the public API's owned-cards endpoints (Roadmap 28, Milestone 7).

Uses a temp `OWNED_CARDS_DIR` (matching owned_store.py's own env override)
so no real owned_cards/ state is touched.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    yield


@pytest.fixture(autouse=True)
def _isolated_owned_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OWNED_CARDS_DIR", str(tmp_path / "owned_cards"))
    yield


@pytest.fixture()
def client(_isolated_db, _isolated_owned_dir):
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("owneduser", "owned@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    return user, {"Authorization": f"Bearer {key_plain}"}


def test_owned_requires_auth(client):
    assert client.get("/api/v1/owned").status_code == 401
    assert client.post("/api/v1/owned", content="Sol Ring").status_code == 401
    assert client.request("DELETE", "/api/v1/owned").status_code == 401


def test_get_owned_empty(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/owned", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"names": [], "count": 0}


def test_upload_replaces_list(client, auth):
    _, headers = auth
    resp = client.post("/api/v1/owned", headers=headers, content="Sol Ring\n1x Lightning Bolt\n")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 2

    resp = client.get("/api/v1/owned", headers=headers)
    names = {n.lower() for n in resp.json()["data"]["names"]}
    assert names == {"sol ring", "lightning bolt"}

    # Second upload should REPLACE, not append.
    resp = client.post("/api/v1/owned", headers=headers, content="Counterspell\n")
    assert resp.status_code == 200
    resp = client.get("/api/v1/owned", headers=headers)
    names = {n.lower() for n in resp.json()["data"]["names"]}
    assert names == {"counterspell"}


def test_clear_owned(client, auth):
    _, headers = auth
    client.post("/api/v1/owned", headers=headers, content="Sol Ring\n")
    resp = client.request("DELETE", "/api/v1/owned", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["cleared"] is True

    resp = client.get("/api/v1/owned", headers=headers)
    assert resp.json()["data"]["count"] == 0


def test_owned_cross_user_isolated(client, tmp_path):
    from code.web.services.user_db import create_user, create_api_key

    a = create_user("owna", "owna@example.com", "pw")
    a_key, _ = create_api_key(a["id"])
    b = create_user("ownb", "ownb@example.com", "pw")
    b_key, _ = create_api_key(b["id"])

    client.post("/api/v1/owned", headers={"Authorization": f"Bearer {a_key}"}, content="Black Lotus\n")

    resp = client.get("/api/v1/owned", headers={"Authorization": f"Bearer {b_key}"})
    assert resp.json()["data"] == {"names": [], "count": 0}
