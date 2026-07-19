"""Tests for the public API's config management endpoints (Roadmap 28, Milestone 9).

Uses a temp `DECK_CONFIG` env var (matching configs.py's own env override)
so no real config/ state is touched.
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
def _isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DECK_CONFIG", str(tmp_path / "config" / "deck.json"))
    yield


@pytest.fixture()
def client(_isolated_db, _isolated_config_dir):
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("configuser", "configs@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    return user, {"Authorization": f"Bearer {key_plain}"}


def test_configs_require_auth(client):
    assert client.get("/api/v1/configs").status_code == 401
    assert client.get("/api/v1/configs/deck.json").status_code == 401
    assert client.post("/api/v1/configs/deck.json", json={}).status_code == 401
    assert client.request("DELETE", "/api/v1/configs/deck.json").status_code == 401


def test_save_and_get_config(client, auth):
    _, headers = auth
    body = {"commander": "Krenko, Mob Boss", "primary_tag": "Goblins"}
    resp = client.post("/api/v1/configs/goblins.json", headers=headers, json=body)
    assert resp.status_code == 200
    assert resp.json()["data"]["saved"] is True

    resp = client.get("/api/v1/configs/goblins.json", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["config"]["commander"] == "Krenko, Mob Boss"


def test_list_configs(client, auth):
    _, headers = auth
    client.post("/api/v1/configs/goblins.json", headers=headers, json={"commander": "Krenko"})
    resp = client.get("/api/v1/configs", headers=headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["data"]["configs"]]
    assert "goblins.json" in names


def test_get_config_not_found(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/configs/nope.json", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CONFIG_NOT_FOUND"


def test_save_config_requires_json_extension(client, auth):
    _, headers = auth
    resp = client.post("/api/v1/configs/goblins.txt", headers=headers, json={"commander": "Krenko"})
    assert resp.status_code == 400


def test_delete_config(client, auth):
    _, headers = auth
    client.post("/api/v1/configs/goblins.json", headers=headers, json={"commander": "Krenko"})
    resp = client.request("DELETE", "/api/v1/configs/goblins.json", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True

    resp = client.get("/api/v1/configs/goblins.json", headers=headers)
    assert resp.status_code == 404


def test_configs_cross_user_isolated(client):
    from code.web.services.user_db import create_user, create_api_key

    a = create_user("cfga", "cfga@example.com", "pw")
    a_key, _ = create_api_key(a["id"])
    b = create_user("cfgb", "cfgb@example.com", "pw")
    b_key, _ = create_api_key(b["id"])

    client.post(
        "/api/v1/configs/secret.json",
        headers={"Authorization": f"Bearer {a_key}"},
        json={"commander": "Krenko"},
    )
    resp = client.get(
        "/api/v1/configs/secret.json",
        headers={"Authorization": f"Bearer {b_key}"},
    )
    assert resp.status_code == 404
