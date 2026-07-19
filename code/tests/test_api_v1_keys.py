"""Tests for the public API's key management (Roadmap 28, Milestones 1-2).

Covers: user_db API key CRUD, and the /api/v1/keys routes via TestClient
(bearer-token auth, plaintext-once, revoke, 401 on invalid/missing token).
Uses an isolated user DB so no real data/users.db is touched.
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


@pytest.fixture()
def client(_isolated_db):
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# user_db CRUD
# ---------------------------------------------------------------------------

def test_create_and_verify_api_key():
    from code.web.services.user_db import create_user, create_api_key, verify_api_key

    user = create_user("alice", "alice@example.com", "hunter2")
    key_plain, api_key = create_api_key(user["id"], label="laptop")
    assert api_key["label"] == "laptop"
    assert api_key["is_active"] is True

    verified = verify_api_key(key_plain)
    assert verified is not None
    assert verified["id"] == user["id"]


def test_verify_api_key_wrong_or_revoked():
    from code.web.services.user_db import create_user, create_api_key, verify_api_key, revoke_api_key

    user = create_user("bob", "bob@example.com", "pw")
    key_plain, api_key = create_api_key(user["id"])

    assert verify_api_key("not-a-real-key") is None

    revoke_api_key(api_key["id"], user["id"])
    assert verify_api_key(key_plain) is None


def test_list_api_keys_never_reveals_plaintext():
    from code.web.services.user_db import create_user, create_api_key, list_api_keys

    user = create_user("carol", "carol@example.com", "pw")
    create_api_key(user["id"], label="phone")
    keys = list_api_keys(user["id"])
    assert len(keys) == 1
    assert "key_hash" not in keys[0]
    assert "key" not in keys[0]


def test_revoke_api_key_wrong_owner_raises():
    from code.web.services.user_db import create_user, create_api_key, revoke_api_key

    owner = create_user("dave", "dave@example.com", "pw")
    other = create_user("erin", "erin@example.com", "pw")
    _, api_key = create_api_key(owner["id"])
    with pytest.raises(ValueError):
        revoke_api_key(api_key["id"], other["id"])


# ---------------------------------------------------------------------------
# /api/v1/keys routes
# ---------------------------------------------------------------------------

def test_keys_route_requires_bearer_token(client):
    resp = client.get("/api/v1/keys")
    assert resp.status_code == 401
    body = resp.json()
    assert body["ok"] is False


def test_keys_route_rejects_invalid_token(client):
    resp = client.get("/api/v1/keys", headers={"Authorization": "Bearer not-a-real-key"})
    assert resp.status_code == 401


def test_create_list_and_revoke_key_via_routes(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("frank", "frank@example.com", "pw")
    bootstrap_plain, _ = create_api_key(user["id"], label="bootstrap")
    headers = {"Authorization": f"Bearer {bootstrap_plain}"}

    resp = client.post("/api/v1/keys", json={"label": "second-device"}, headers=headers)
    assert resp.status_code == 201
    created = resp.json()["data"]
    assert "key" in created and created["key"]
    new_key_id = created["id"]

    resp = client.get("/api/v1/keys", headers=headers)
    assert resp.status_code == 200
    labels = {k["label"] for k in resp.json()["data"]}
    assert labels == {"bootstrap", "second-device"}

    resp = client.delete(f"/api/v1/keys/{new_key_id}", headers=headers)
    assert resp.status_code == 200

    resp = client.get("/api/v1/keys", headers=headers)
    labels = {k["label"] for k in resp.json()["data"]}
    assert labels == {"bootstrap"}


def test_revoke_missing_key_returns_404_envelope(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("gina", "gina@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    headers = {"Authorization": f"Bearer {key_plain}"}

    resp = client.delete("/api/v1/keys/does-not-exist", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["code"] == "KEY_NOT_FOUND"
