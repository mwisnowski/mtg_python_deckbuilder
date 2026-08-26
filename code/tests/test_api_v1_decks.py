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
def client(_isolated_db, _isolated_deck_exports, monkeypatch):
    from code.web.app import app
    # Each test uses a fresh tmp_path, so the module-level public-decks cache
    # (keyed only by a 60s TTL, not by directory) must be reset per test.
    import code.web.routes.decks as decks_routes
    monkeypatch.setitem(decks_routes._PUBLIC_DECKS_CACHE, "data", None)
    monkeypatch.setitem(decks_routes._PUBLIC_DECKS_CACHE, "ts", 0.0)
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


def test_deck_detail_excludes_tokens_and_emblems_section(client, auth, tmp_path):
    """The roadmap_39 '# Tokens & Emblems Created' CSV section is
    informational-only and must never appear in the API's card list (it
    previously leaked into the mobile app's deck view under "Other")."""
    user, headers = auth
    deck_dir = tmp_path / "deck_files" / user["id"]
    deck_dir.mkdir(parents=True, exist_ok=True)
    csv_path = deck_dir / "Token Deck.csv"
    csv_path.write_text(
        "Name,Count,Type,ManaValue,Colors,Role,Tags\n"
        "Sol Ring,1,Artifact,1,Colorless,Ramp,Ramp\n"
        "# Tokens & Emblems Created,,,,,,\n"
        "# Treasure,1,Token,,,,,\n"
        "Total,1,,,,,\n",
        encoding="utf-8",
    )
    (deck_dir / "Token Deck.txt").write_text("1 Sol Ring\n", encoding="utf-8")

    resp = client.get("/api/v1/decks/Token Deck.csv", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Sol Ring"}
    assert data["card_count"] == 1


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


def test_deck_analysis_fallback_no_sidecar(client, auth, tmp_path):
    """Without a `.summary.json` sidecar, falls back to a CSV-only curve
    reconstruction (pips/sources default to zero, per `_read_csv_summary`)."""
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv/analysis", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["commander"] == "Test Deck"
    assert data["mana_curve"]["1"] == 2
    assert data["pip_distribution"]["counts"] == {c: 0 for c in ("W", "U", "B", "R", "G")}


def test_deck_analysis_not_found(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/decks/Nope.csv/analysis", headers=headers)
    assert resp.status_code == 404


def test_deck_analysis_honors_printing_map(client, auth, tmp_path, monkeypatch):
    """`total_price` must price each card via its saved printing override
    (the CSV's `ScryfallID` column), not always the cheapest known printing
    for that name -- this is what the mobile app's deck total reads."""
    user, headers = auth
    deck_dir = tmp_path / "deck_files" / user["id"]
    deck_dir.mkdir(parents=True, exist_ok=True)
    csv_path = deck_dir / "Priced Deck.csv"
    csv_path.write_text(
        "Name,Count,Type,ManaValue,Colors,Role,Tags,ScryfallID\n"
        "Sol Ring,1,Artifact,1,Colorless,Ramp,Ramp,abc123\n"
        "Total,1,,,,,,\n",
        encoding="utf-8",
    )
    (deck_dir / "Priced Deck.txt").write_text("1 Sol Ring\n", encoding="utf-8")

    captured: dict = {}

    class _StubPriceService:
        def get_prices_batch(self, names, region="usd", foil=False, printing_map=None, foil_map=None):
            captured["printing_map"] = printing_map
            return {n: 20.0 for n in names}

    import code.web.services.price_service as price_service_mod
    monkeypatch.setattr(price_service_mod, "get_price_service", lambda: _StubPriceService())

    resp = client.get("/api/v1/decks/Priced Deck.csv/analysis", headers=headers)
    assert resp.status_code == 200
    assert captured["printing_map"] == {"sol ring": "abc123"}
    assert resp.json()["data"]["total_price"] == 20.0


def test_deck_analysis_token_printing_override_applies(client, auth, tmp_path):
    """Persisting a token/emblem printing via POST /token-printing (the
    mobile app's "Change Printing" action) must show up in the very next
    GET /analysis response, keyed by the token's stable `key` -- this is
    what makes the choice actually stick instead of being forgotten."""
    user, headers = auth
    csv_path = _write_sample_deck(user["id"], tmp_path)
    sidecar = csv_path.parent / (csv_path.stem + ".summary.json")
    sidecar.write_text(
        json.dumps(
            {
                "summary": {
                    "tokens_created": [
                        {
                            "token": {
                                "name": "Treasure",
                                "type": "Token Artifact — Treasure",
                                "power": None,
                                "toughness": None,
                                "is_emblem": False,
                                "colors": "",
                                "key": "treasure|token artifact — treasure|||treasurehash",
                                "text_hash": "treasurehash",
                                "text": "Sacrifice this artifact: Add one mana of any color.",
                            },
                            "created_by": ["Sol Ring"],
                        }
                    ]
                },
                "meta": {"commander": "Test Deck"},
            }
        ),
        encoding="utf-8",
    )

    resp = client.get("/api/v1/decks/Test Deck.csv/analysis", headers=headers)
    assert resp.status_code == 200
    tokens = resp.json()["data"]["tokens_created"]
    assert tokens[0]["token"].get("scryfall_id") is None

    key = tokens[0]["token"]["key"]
    resp = client.post(
        "/api/v1/decks/Test Deck.csv/token-printing",
        headers=headers,
        json={"key": key, "scryfall_id": "abc123"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"key": key, "scryfall_id": "abc123"}

    resp = client.get("/api/v1/decks/Test Deck.csv/analysis", headers=headers)
    assert resp.status_code == 200
    tokens = resp.json()["data"]["tokens_created"]
    assert tokens[0]["token"]["scryfall_id"] == "abc123"


def test_deck_compliance_reads_sidecar(client, auth, tmp_path):
    user, headers = auth
    csv_path = _write_sample_deck(user["id"], tmp_path)
    report = {
        "bracket": "core",
        "level": 2,
        "overall": "PASS",
        "categories": {
            "game_changers": {"count": 0, "limit": 3, "flagged": [], "status": "PASS", "notes": []},
        },
        "messages": ["All categories within limits."],
    }
    sidecar = csv_path.parent / (csv_path.stem + "_compliance.json")
    sidecar.write_text(json.dumps(report), encoding="utf-8")

    resp = client.get("/api/v1/decks/Test Deck.csv/compliance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["overall"] == "PASS"
    assert data["categories"]["game_changers"]["limit"] == 3


def test_deck_compliance_missing_sidecar(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.get("/api/v1/decks/Test Deck.csv/compliance", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "COMPLIANCE_NOT_FOUND"


def test_deck_compliance_deck_not_found(client, auth):
    _, headers = auth
    resp = client.get("/api/v1/decks/Nope.csv/compliance", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "DECK_NOT_FOUND"


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


def test_deck_upgrades_swap_requires_auth(client):
    resp = client.post(
        "/api/v1/decks/Test Deck.csv/upgrades/swap",
        json={"remove": "Lightning Bolt", "add": "Swords to Plowshares"},
    )
    assert resp.status_code == 401


def test_deck_upgrades_swap_applies_change(client, auth, tmp_path):
    user, headers = auth
    csv_path = _write_sample_deck(user["id"], tmp_path)
    resp = client.post(
        "/api/v1/decks/Test Deck.csv/upgrades/swap",
        headers=headers,
        json={"remove": "Lightning Bolt", "add": "Swords to Plowshares"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"removed": "Lightning Bolt", "added": "Swords to Plowshares"}
    contents = csv_path.read_text(encoding="utf-8")
    assert "Swords to Plowshares" in contents
    assert "Lightning Bolt" not in contents
    txt_contents = csv_path.with_suffix(".txt").read_text(encoding="utf-8")
    assert "1 Swords to Plowshares" in txt_contents


def test_deck_upgrades_swap_card_not_in_deck(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.post(
        "/api/v1/decks/Test Deck.csv/upgrades/swap",
        headers=headers,
        json={"remove": "Nonexistent Card", "add": "Swords to Plowshares"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "CARD_NOT_IN_DECK"


def test_deck_upgrades_swap_add_already_in_deck(client, auth, tmp_path):
    user, headers = auth
    _write_sample_deck(user["id"], tmp_path)
    resp = client.post(
        "/api/v1/decks/Test Deck.csv/upgrades/swap",
        headers=headers,
        json={"remove": "Lightning Bolt", "add": "Sol Ring"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "CARD_ALREADY_IN_DECK"


def test_deck_upgrades_swap_cannot_remove_commander(client, auth, tmp_path):
    user, headers = auth
    deck_dir = tmp_path / "deck_files" / user["id"]
    deck_dir.mkdir(parents=True, exist_ok=True)
    csv_path = deck_dir / "Cmdr Deck.csv"
    csv_path.write_text(
        "Name,Count,Type,ManaValue,Colors,Role,Tags\n"
        "Some Commander,1,Legendary Creature - Commander,3,G,Commander,\n"
        "Sol Ring,1,Artifact,1,Colorless,Ramp,Ramp\n"
        "Total,2,,,,,\n",
        encoding="utf-8",
    )
    (deck_dir / "Cmdr Deck.txt").write_text("1 Some Commander\n1 Sol Ring\n", encoding="utf-8")
    resp = client.post(
        "/api/v1/decks/Cmdr Deck.csv/upgrades/swap",
        headers=headers,
        json={"remove": "Some Commander", "add": "Swords to Plowshares"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "CANNOT_REMOVE_COMMANDER"


def test_deck_upgrades_swap_deck_not_found(client, auth):
    _, headers = auth
    resp = client.post(
        "/api/v1/decks/Nope.csv/upgrades/swap",
        headers=headers,
        json={"remove": "Lightning Bolt", "add": "Swords to Plowshares"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "DECK_NOT_FOUND"


def _mark_public(tmp_path, user_id: str, deck_stem: str) -> None:
    sidecar = tmp_path / "deck_files" / user_id / f"{deck_stem}.summary.json"
    sidecar.write_text(json.dumps({"meta": {"visibility": "public"}}), encoding="utf-8")


def test_public_decks_listing_requires_no_auth(client, auth, tmp_path):
    """Other users' public decks and guest builds are visible with no Authorization header."""
    user, _headers = auth
    _write_sample_deck(user["id"], tmp_path)
    _mark_public(tmp_path, user["id"], "Test Deck")
    _write_sample_deck("guest", tmp_path, name="Guest Deck.csv")

    resp = client.get("/api/v1/decks/public")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [d["name"] for d in data["public"]] == ["Test Deck.csv"]
    assert data["public"][0]["username"] == "iris"
    assert [d["name"] for d in data["guest"]] == ["Guest Deck.csv"]


def test_public_decks_listing_excludes_private_decks(client, auth, tmp_path):
    user, _headers = auth
    _write_sample_deck(user["id"], tmp_path)  # no sidecar -> defaults to private

    resp = client.get("/api/v1/decks/public")
    assert resp.status_code == 200
    assert resp.json()["data"]["public"] == []


def test_public_decks_listing_excludes_own_decks_when_authenticated(client, auth, tmp_path):
    """A logged-in caller's own public decks are excluded (already shown under "My Decks")."""
    from code.web.services.user_db import create_user

    user, headers = auth
    _write_sample_deck(user["id"], tmp_path, name="My Deck.csv")
    _mark_public(tmp_path, user["id"], "My Deck")

    other = create_user("otheruser", "other@example.com", "pw")
    _write_sample_deck(other["id"], tmp_path, name="Other Deck.csv")
    _mark_public(tmp_path, other["id"], "Other Deck")

    resp = client.get("/api/v1/decks/public", headers=headers)
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["data"]["public"]]
    assert names == ["Other Deck.csv"]

    # No Authorization header at all -> nothing excluded, both decks show.
    resp_anon = client.get("/api/v1/decks/public")
    assert resp_anon.status_code == 200
    anon_names = {d["name"] for d in resp_anon.json()["data"]["public"]}
    assert anon_names == {"My Deck.csv", "Other Deck.csv"}


def test_public_deck_detail_no_auth_required(client, auth, tmp_path):
    user, _headers = auth
    _write_sample_deck(user["id"], tmp_path)
    _mark_public(tmp_path, user["id"], "Test Deck")

    resp = client.get(f"/api/v1/decks/public/{user['id']}/Test Deck.csv")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["card_count"] == 2


def test_public_deck_detail_404_when_private(client, auth, tmp_path):
    user, _headers = auth
    _write_sample_deck(user["id"], tmp_path)  # defaults to private, no sidecar

    resp = client.get(f"/api/v1/decks/public/{user['id']}/Test Deck.csv")
    assert resp.status_code == 404


def test_guest_deck_detail_always_readable(client, tmp_path):
    """Guest/community decks don't need a visibility sidecar to be readable."""
    _write_sample_deck("guest", tmp_path, name="Guest Deck.csv")

    resp = client.get("/api/v1/decks/public/guest/Guest Deck.csv")
    assert resp.status_code == 200
    assert resp.json()["data"]["card_count"] == 2


def test_public_deck_export_csv(client, auth, tmp_path):
    user, _headers = auth
    _write_sample_deck(user["id"], tmp_path)
    _mark_public(tmp_path, user["id"], "Test Deck")

    resp = client.get(f"/api/v1/decks/public/{user['id']}/Test Deck.csv/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
