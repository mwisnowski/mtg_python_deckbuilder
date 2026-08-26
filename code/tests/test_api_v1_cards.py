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


def test_list_cards_by_set_code(client):
    # api_v1/cards.py doesn't call the shared apply_extra_clauses(), so the
    # set: filter needs its own mirrored block (Roadmap 38, M1).
    resp = client.get("/api/v1/cards", params={"q": "set:LEA"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Sol Ring", "Lightning Bolt", "Counterspell"}


def test_list_cards_by_negative_set_code(client):
    resp = client.get("/api/v1/cards", params={"q": "-set:LEA"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert "Sol Ring" not in names
    assert "Fire // Ice" in names


def test_list_cards_response_includes_notices_key(client):
    resp = client.get("/api/v1/cards", params={"q": "set:LEA"})
    data = resp.json()["data"]
    assert "notices" in data
    assert data["notices"] == []


def test_list_cards_by_collector_number(client, tmp_path, monkeypatch):
    # api_v1/cards.py doesn't call the shared apply_extra_clauses(), so
    # cn:/number: needs its own mirrored block too (Roadmap 38, M3).
    import code.web.services.card_search as card_search

    printings_df = pd.DataFrame(
        [
            {"face_name": "Sol Ring", "set": "LEA", "collector_number": "211", "scryfall_id": "sol-211", "score": 5, "released_at": "2024-01-01"},
            {"face_name": "Sol Ring", "set": "LEA", "collector_number": "212", "scryfall_id": "sol-212", "score": 20, "released_at": "2024-01-01"},
        ]
    )
    printings_df.to_parquet(tmp_path / "card_printings.parquet", engine="pyarrow")
    monkeypatch.setattr(card_search, "card_files_processed_dir", lambda: str(tmp_path))
    card_search._PRINTINGS_INDEX_DF = None
    card_search._PRINTINGS_INDEX_LOADED = False

    resp = client.get("/api/v1/cards", params={"q": "set:LEA cn:212"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Sol Ring"}

    resp = client.get("/api/v1/cards", params={"q": "cn:212"})
    data = resp.json()["data"]
    assert data["total_count"] == 6  # no set: -- no-op, unfiltered
    assert any("requires a set:" in n for n in data["notices"])

    card_search._PRINTINGS_INDEX_DF = None
    card_search._PRINTINGS_INDEX_LOADED = False


def test_list_cards_includes_resolved_printing_id_for_set_scoped_search(client):
    # Mobile/web parity: a set: search resolves each card to its printing in
    # that set (mirrors card_browser.py's _set_scoped_printings()), surfaced
    # via a resolvedPrintingId field so the mobile app can request that
    # printing's artwork instead of the card's global default.
    import code.web.routes.api_v1.cards as cards_route

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cards_route._image_cache, "get_printing_id_for_set", lambda name, code: f"{name}-{code}".lower())
        resp = client.get("/api/v1/cards", params={"q": "set:LEA"})
    data = resp.json()["data"]
    sol_ring = next(c for c in data["cards"] if c["name"] == "Sol Ring")
    assert sol_ring["resolvedPrintingId"] == "sol ring-lea"

    resp = client.get("/api/v1/cards", params={"q": ""})
    data = resp.json()["data"]
    assert all(c["resolvedPrintingId"] is None for c in data["cards"])


def test_list_cards_includes_set_badge_for_single_set_search(client):
    # Roadmap 38 M5 API parity: a single set: search also surfaces a
    # setBadge (set/setName/collectorNumber) per card, mirroring the web
    # UI's card tile/detail badge, so the mobile app can render the same info.
    import code.web.routes.api_v1.cards as cards_route

    def _fake_get_printing_meta(name, *, scryfall_id=None, set_code=None):
        assert set_code == "LEA"
        return {"set": "LEA", "set_name": "Limited Edition Alpha", "collector_number": "1"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cards_route._image_cache, "get_printing_meta", _fake_get_printing_meta)
        resp = client.get("/api/v1/cards", params={"q": "set:LEA"})
    data = resp.json()["data"]
    sol_ring = next(c for c in data["cards"] if c["name"] == "Sol Ring")
    assert sol_ring["setBadge"] == {"set": "LEA", "setName": "Limited Edition Alpha", "collectorNumber": "1"}

    # No set: filter, or more than one -- ambiguous/not scoped, no badge.
    resp = client.get("/api/v1/cards", params={"q": ""})
    data = resp.json()["data"]
    assert all(c["setBadge"] is None for c in data["cards"])


def test_list_cards_by_tags_and_logic(client):
    resp = client.get("/api/v1/cards", params={"tags": "Removal,Burn"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Lightning Bolt", "Fire // Ice"}


def test_list_cards_by_negative_tag_flag(client):
    # `-tag:` should exclude cards with that tag, not silently be treated
    # as another required (AND) positive tag.
    resp = client.get("/api/v1/cards", params={"q": 'tag:Removal -tag:Burn'})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == set()  # every "Removal" card here also has "Burn"

    resp = client.get("/api/v1/cards", params={"q": "-tag:Burn"})
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert "Lightning Bolt" not in names
    assert "Fire // Ice" not in names
    assert "Sol Ring" in names


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


def test_list_cards_type_token_surfaces_token_catalog(client, monkeypatch):
    """`type:token` must merge in the separate tokens/emblems catalog (it's
    otherwise excluded from all_cards.parquet search entirely), matching the
    HTML card browser's `type:token` behavior."""
    import code.web.services.card_search as card_search

    token_df = pd.DataFrame(
        [
            {
                "name": "Goblin",
                "type": "Token Creature — Goblin",
                "colorIdentity": "R",
                "colors": "R",
                "manaValue": 0.0,
                "rarity": "",
                "themeTags": [],
                "edhrecRank": None,
                "scryfallID": "",
                "text": "",
                "power": "1",
                "toughness": "1",
                "loyalty": None,
                "printings": "",
                "layout": "token",
                "isNew": False,
                "is_token": True,
                "is_emblem": False,
                "text_hash": "abc123",
            }
        ]
    )
    monkeypatch.setattr(card_search, "load_tokens_browser_df", lambda: token_df)

    resp = client.get("/api/v1/cards", params={"q": "type:token"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {c["name"] for c in data["cards"]}
    assert names == {"Goblin"}
    assert "Sol Ring" not in names
    goblin = next(c for c in data["cards"] if c["name"] == "Goblin")
    assert goblin["isToken"] is True
    assert goblin["isEmblem"] is False
    assert goblin["power"] == "1"
    assert goblin["toughness"] == "1"
    assert goblin["colors"] == "R"
    assert goblin["textHash"] == "abc123"


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
