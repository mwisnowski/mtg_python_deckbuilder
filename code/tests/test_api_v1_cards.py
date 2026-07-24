"""Tests for the public API's card browser endpoints (Roadmap 28, Milestone 4).

Uses a small fixture DataFrame (written to a temp parquet) instead of the
real all_cards.parquet -- no auth required, so no user_db fixture is needed.
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def sample_parquet_file(tmp_path):
    df = pd.DataFrame(
        {
            "name": ["Sol Ring", "Lightning Bolt", "Fire // Ice", "Counterspell", "Chandra, Torch of Defiance", "Old Homestead Guru"],
            "colorIdentity": ["Colorless", "R", "UR", "U", "R", "G"],
            "type": ["Artifact", "Instant", "Instant // Instant", "Instant", "Legendary Creature — Human Wizard", "Legendary Planeswalker — Vivien"],
            "manaValue": [1.0, 1.0, 2.0, 2.0, 4.0, 3.0],
            "rarity": ["uncommon", "common", "uncommon", "common", "mythic", "rare"],
            "themeTags": [["Ramp"], ["Removal", "Burn"], ["Removal", "Burn"], ["Counterspell"], [], []],
            "edhrecRank": [1.0, 50.0, 500.0, 20.0, 300.0, 4000.0],
            "scryfallID": ["sol-ring-id", "bolt-id", "fire-ice-id", "", "chandra-id", "guru-id"],
            "text": ["Add {C}{C}.", "Deal 3 damage.", "Deal 2 damage. // Tap target.", "Counter target spell.", "+1: ... -3: ... -7: ...", "+1: ... -X: ..."],
            "power": [None, None, None, None, None, None],
            "toughness": [None, None, None, None, None, None],
            "loyalty": [None, None, None, None, "4", "X"],
            "printings": ["LEA", "LEA", "APC", "LEA", "KLD", "TST"],
            "layout": ["normal", "normal", "split", "normal", "normal", "normal"],
            "isNew": [False, False, False, False, False, False],
        }
    )
    path = tmp_path / "all_cards.parquet"
    df.to_parquet(path, engine="pyarrow")
    return str(path)


@pytest.fixture(autouse=True)
def _patched_loader(sample_parquet_file, monkeypatch):
    import code.web.routes.api_v1.cards as cards_route
    from code.services.all_cards_loader import AllCardsLoader

    cards_route._loader = AllCardsLoader(file_path=sample_parquet_file)
    cards_route._similarity = None
    yield
    cards_route._loader = None
    cards_route._similarity = None


@pytest.fixture()
def client():
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_list_cards_no_filters(client):
    resp = client.get("/api/v1/cards")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_count"] == 6
    assert len(data["cards"]) == 6


def test_list_cards_by_query(client):
    resp = client.get("/api/v1/cards", params={"q": "bolt"})
    data = resp.json()["data"]
    assert data["total_count"] == 1
    assert data["cards"][0]["name"] == "Lightning Bolt"


def test_list_cards_by_colors(client):
    resp = client.get("/api/v1/cards", params={"colors": "U"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Counterspell"}


def test_list_cards_by_tags_and_logic(client):
    resp = client.get("/api/v1/cards", params={"tags": "Removal,Burn"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Lightning Bolt", "Fire // Ice"}


def test_list_cards_cmc_range(client):
    resp = client.get("/api/v1/cards", params={"min_cmc": 2, "max_cmc": 2})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Fire // Ice", "Counterspell"}


def test_list_cards_pagination(client):
    resp = client.get("/api/v1/cards", params={"page": 1, "page_size": 2})
    data = resp.json()["data"]
    assert len(data["cards"]) == 2
    assert data["total_pages"] == 3


def test_list_cards_loyalty_numeric(client):
    resp = client.get("/api/v1/cards", params={"q": "loy>=4"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Chandra, Torch of Defiance"}


def test_list_cards_loyalty_excludes_non_numeric(client):
    # "X" loyalty (Old Homestead Guru) should be excluded from numeric
    # comparisons rather than crashing the request.
    resp = client.get("/api/v1/cards", params={"q": "loy>0"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Chandra, Torch of Defiance"}


def test_card_detail_found(client):
    resp = client.get("/api/v1/cards/Sol Ring")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Sol Ring"
    assert data["text"] == "Add {C}{C}."


def test_card_detail_with_slash_in_name(client):
    resp = client.get("/api/v1/cards/Fire // Ice")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Fire // Ice"


def test_card_detail_not_found(client):
    resp = client.get("/api/v1/cards/Nonexistent Card")
    assert resp.status_code == 404
    assert resp.json()["code"] == "CARD_NOT_FOUND"


def test_card_similar(client):
    resp = client.get("/api/v1/cards/Lightning Bolt/similar")
    assert resp.status_code == 200
    similar_names = {c["name"] for c in resp.json()["data"]}
    assert "Fire // Ice" in similar_names


def test_card_rulings_uses_scryfall_id(client, monkeypatch):
    import code.web.routes.api_v1.cards as cards_route

    async def _fake_get_rulings(scryfall_id):
        assert scryfall_id == "bolt-id"
        return [{"published_at": "2020-01-01", "source": "wotc", "comment": "Test ruling."}]

    monkeypatch.setattr(cards_route, "get_rulings", _fake_get_rulings)

    resp = client.get("/api/v1/cards/Lightning Bolt/rulings")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["comment"] == "Test ruling."


def test_card_rulings_empty_scryfall_id(client):
    resp = client.get("/api/v1/cards/Counterspell/rulings")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
