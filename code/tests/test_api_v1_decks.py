"""Tests for the public API's deck management endpoints (Roadmap 28, Milestone 5).

Uses a temp `DECK_EXPORTS` directory (matching decks.py's own env override)
so no real deck_files/ state is touched.
"""
from __future__ import annotations

import json

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
def _isolated_deck_exports(tmp_path, monkeypatch):
    monkeypatch.setenv("DECK_EXPORTS", str(tmp_path / "deck_files"))
    yield


@pytest.fixture()
def client(_isolated_db, _isolated_deck_exports):
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("iris", "iris@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    return user, {"Authorization": f"Bearer {key_plain}"}


def _write_sample_deck(user_id: str, tmp_path, name: str = "Test Deck.csv"):
    import os

    deck_dir = tmp_path / "deck_files" / user_id
    deck_dir.mkdir(parents=True, exist_ok=True)
    csv_path = deck_dir / name
    csv_path.write_text(
        "Name,Count,Type,ManaValue,Colors,Role,Tags\n"
        "Sol Ring,1,Artifact,1,Colorless,Ramp,Ramp\n"
        "Lightning Bolt,1,Instant,1,R,Removal,Removal;Burn\n"
        "Total,2,,,,,\n",
        encoding="utf-8",
    )
    (deck_dir / (csv_path.stem + ".txt")).write_text("1 Sol Ring\n1 Lightning Bolt\n", encoding="utf-8")
    return csv_path


def test_list_decks_requires_auth(client):
    resp = client.get("/api/v1/decks")
    assert resp.status_code == 401


def test_list_decks(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks", headers=headers)
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["data"]]
    assert "Test Deck.csv" in names


def test_deck_detail(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["card_count"] == 2
    names = {c["name"] for c in data["cards"]}
    assert names == {"Sol Ring", "Lightning Bolt"}


def test_deck_detail_not_found(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/decks/Nope.csv", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "DECK_NOT_FOUND"


def test_deck_detail_wrong_user_isolated(client, tmp_path):
    """A deck saved under one user's folder must not be visible to another user."""
    from code.web.services.user_db import create_user, create_api_key

    owner = create_user("owner", "owner@example.com", "pw")
    _write_sample_deck(owner["id"], tmp_path)

    other = create_user("other", "other@example.com", "pw")
    other_key, _ = create_api_key(other["id"])

    resp = client.get(
        "/api/v1/decks/Test Deck.csv",
        headers={"Authorization": f"Bearer {other_key}"},
    )
    assert resp.status_code == 404


def test_export_csv(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv/export", headers=headers, params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_export_txt(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv/export", headers=headers, params={"format": "txt"})
    assert resp.status_code == 200
    assert "Sol Ring" in resp.text


def test_export_json(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv/export", headers=headers, params={"format": "json"})
    assert resp.status_code == 200
    payload = json.loads(resp.text)
    assert payload["card_count"] == 2


def test_delete_deck(client, auth, tmp_path):
    user, headers = auth
    csv_path = _write_sample_deck(user["id"], tmp_path)
    resp = client.request("DELETE", "/api/v1/decks/Test Deck.csv", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True
    assert not csv_path.exists()
    assert not csv_path.with_suffix(".txt").exists()


# ---------------------------------------------------------------------------
# Milestone 8: upgrade suggestions
# ---------------------------------------------------------------------------

def test_deck_upgrades_requires_auth(client):
    resp = client.get("/api/v1/decks/Test Deck.csv/upgrades")
    assert resp.status_code == 401


def test_deck_upgrades_not_found(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/decks/Nope.csv/upgrades", headers=headers)
    assert resp.status_code == 404


def test_deck_upgrades_general_section(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get(
        "/api/v1/decks/Test Deck.csv/upgrades",
        headers=headers,
        params={"section": "general"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["section"] == "general"
    assert isinstance(data["cards"], list)
