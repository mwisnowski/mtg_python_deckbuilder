"""Tests for the public API's user auth endpoints (Roadmap 28, Milestone 10).

register/login/forgot are unauthenticated; logout/me require an API key.
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


def _register(client, username="regtest", email="regtest@example.com", password="password123"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def test_register_success(client):
    resp = _register(client)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["username"] == "regtest"


def test_register_duplicate(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 409
    assert resp.json()["code"] == "USER_EXISTS"


def test_register_short_password(client):
    resp = _register(client, password="short")
    assert resp.status_code == 422  # pydantic min_length validation


def test_login_success(client):
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"login": "regtest", "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["api_key"]
    assert data["user"]["username"] == "regtest"


def test_login_wrong_password(client):
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"login": "regtest", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


def test_login_device_label_reuses_key(client):
    _register(client)
    first = client.post(
        "/api/v1/auth/login",
        json={"login": "regtest", "password": "password123", "device_label": "phone"},
    )
    second = client.post(
        "/api/v1/auth/login",
        json={"login": "regtest", "password": "password123", "device_label": "phone"},
    )
    assert first.json()["data"]["api_key"] is not None
    assert second.json()["data"]["api_key"] is None
    assert first.json()["data"]["key_id"] == second.json()["data"]["key_id"]


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_profile(client):
    _register(client)
    login_resp = client.post("/api/v1/auth/login", json={"login": "regtest", "password": "password123"})
    key = login_resp.json()["data"]["api_key"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "regtest"


def test_logout_revokes_key(client):
    _register(client)
    login_resp = client.post("/api/v1/auth/login", json={"login": "regtest", "password": "password123"})
    key = login_resp.json()["data"]["api_key"]
    headers = {"Authorization": f"Bearer {key}"}

    resp = client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["loggedOut"] is True

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401


def test_forgot_always_reports_submitted(client):
    resp = client.post("/api/v1/auth/forgot", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json()["data"]["submitted"] is True
