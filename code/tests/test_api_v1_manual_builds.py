"""Tests for the public API's manual-build endpoints (roadmap_25 Milestone 8).

Mocks `builds_route._start_manual_session_sync` (commander validation +
color identity) and `manual_builder_service.AllCardsLoader` (the card pool),
mirroring the conventions in test_api_v1_builds.py and test_manual_builder.py
respectively, to avoid touching real commander/card data.
"""
from __future__ import annotations

import pandas as pd
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


@pytest.fixture()
def auth_headers(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("mira", "mira@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    return {"Authorization": f"Bearer {key_plain}"}


def _sample_pool_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"name": "Rampant Growth", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Ramp"], "edhrecRank": 500.0, "isNew": False},
        {"name": "Lightning Bolt", "colorIdentity": "R", "type": "Instant", "manaValue": 1.0,
         "themeTags": ["Removal"], "edhrecRank": 100.0, "isNew": False},
    ])


@pytest.fixture()
def manual_build_id(client, auth_headers, monkeypatch, tmp_path):
    """Create a manual-mode build, mocking commander validation + the pool,
    and routing the per-user deck directory to an isolated tmp_path so a
    later save doesn't touch the real deck_files/ tree.
    """
    import code.web.routes.api_v1.builds as builds_route
    import code.web.routes.decks as decks_route
    import code.web.services.manual_builder_service as manual_builder_service

    monkeypatch.setattr(builds_route, "_start_manual_session_sync", lambda *a, **k: ["R", "G"])
    monkeypatch.setattr(builds_route, "_deck_dir", lambda uid: tmp_path)
    monkeypatch.setattr(decks_route, "_deck_dir", lambda uid: tmp_path)

    class _FakeLoader:
        def load(self):
            return _sample_pool_df()

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)

    resp = client.post(
        "/api/v1/builds",
        json={"commander": "Some Commander", "mode": "manual", "bracket": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "manual"
    assert data["status"] == "ready"
    return data["build_id"]


def test_create_manual_build(manual_build_id):
    assert manual_build_id


def test_create_build_rejects_invalid_mode(client, auth_headers):
    resp = client.post(
        "/api/v1/builds", json={"commander": "X", "mode": "bogus"}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_MODE"


def test_manual_pool_categorized_overview(client, auth_headers, manual_build_id):
    resp = client.get(f"/api/v1/builds/{manual_build_id}/pool", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "categories" in data
    assert "category_keys" in data


def test_manual_pool_single_category(client, auth_headers, manual_build_id):
    resp = client.get(
        f"/api/v1/builds/{manual_build_id}/pool", params={"category": "ramp"}, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["category"] == "ramp"
    assert any(c["name"] == "Rampant Growth" for c in data["cards"])


def test_manual_add_and_remove_card(client, auth_headers, manual_build_id):
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/add",
        json={"name": "Rampant Growth"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "added"
    assert data["deck"]["total_cards"] == 1

    # Duplicate non-basic-land cards are blocked (Commander singleton rule).
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/add",
        json={"name": "Rampant Growth"},
        headers=auth_headers,
    )
    assert resp.json()["data"]["status"] == "duplicate"

    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/remove",
        json={"name": "Rampant Growth"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "removed"
    assert data["deck"]["total_cards"] == 0


def test_manual_add_unknown_card_404(client, auth_headers, manual_build_id):
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/add",
        json={"name": "Not A Real Card"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "CARD_NOT_FOUND"


def test_manual_search(client, auth_headers, manual_build_id):
    resp = client.get(
        f"/api/v1/builds/{manual_build_id}/manual/search", params={"q": "Bolt"}, headers=auth_headers
    )
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["data"]["cards"]}
    assert "Lightning Bolt" in names


def test_manual_suggestions(client, auth_headers, manual_build_id):
    resp = client.get(
        f"/api/v1/builds/{manual_build_id}/manual/suggestions",
        params={"card": "Rampant Growth"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


def test_manual_save_writes_deck_and_appears_in_decks_list(client, auth_headers, manual_build_id):
    client.post(
        f"/api/v1/builds/{manual_build_id}/manual/add",
        json={"name": "Rampant Growth"},
        headers=auth_headers,
    )
    resp = client.post(f"/api/v1/builds/{manual_build_id}/manual/save", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["csv_path"].endswith(".csv")

    resp = client.get("/api/v1/decks", headers=auth_headers)
    assert resp.status_code == 200
    names = {d.get("name") for d in resp.json()["data"]}
    assert any("Some_Commander" in (n or "") for n in names)


def test_manual_set_count_clamps_non_unlimited_card(client, auth_headers, manual_build_id):
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/set-count",
        json={"name": "Rampant Growth", "count": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "set"
    assert data["count"] == 1
    assert data["deck"]["total_cards"] == 1


def test_manual_land_package_adds_lands(client, auth_headers, manual_build_id):
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/land-package", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "added"
    assert data["count"] > 0
    assert data["deck"]["total_cards"] == data["count"]


def test_manual_endpoints_require_ownership(client, auth_headers, manual_build_id):
    from code.web.services.user_db import create_user, create_api_key

    other_user = create_user("other", "other@example.com", "pw")
    other_key, _ = create_api_key(other_user["id"])
    resp = client.get(
        f"/api/v1/builds/{manual_build_id}/pool", headers={"Authorization": f"Bearer {other_key}"}
    )
    assert resp.status_code == 404


def test_manual_get_deck_state_includes_mana_overview(client, auth_headers, manual_build_id):
    resp = client.get(f"/api/v1/builds/{manual_build_id}/manual/deck", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "deck" in data and "role_bar" in data and "mana_overview" in data
    assert "pips" in data["mana_overview"]
    assert "sources" in data["mana_overview"]
    assert "curve" in data["mana_overview"]


def test_manual_add_response_includes_mana_overview(client, auth_headers, manual_build_id):
    resp = client.post(
        f"/api/v1/builds/{manual_build_id}/manual/add",
        json={"name": "Lightning Bolt"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # +1 for the commander itself, which counts toward curve/mana totals too.
    assert data["mana_overview"]["curve_total"] == 2
