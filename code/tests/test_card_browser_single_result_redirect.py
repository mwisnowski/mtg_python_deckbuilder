"""
Tests for the card browser's single-result auto-redirect: a search that
narrows to exactly one card skips the results grid and redirects straight
to that card's detail page, carrying over any `set:`-scoped printing.
"""
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from code.web.app import app  # noqa: F401  (import first to avoid a card_browser circular import)
import code.web.routes.card_browser as card_browser


def _fake_card(name: str, **overrides) -> dict:
    base = {
        "name": name,
        "type": "Artifact",
        "text": "Add one mana of any color.",
        "manaValue": 1,
        "power": None,
        "toughness": None,
        "edhrecRank": 1,
        "rarity": "uncommon",
        "colors": [],
        "colorIdentity": "C",
        "scryfallID": "test-scryfall-id",
        "themeTags": "",
        "artTags": "",
        "metadataTags": "",
        "isNew": False,
        "price": None,
        "ck_price": None,
        "side": None,
        "printings": "LEA",
    }
    base.update(overrides)
    return base


def _client(monkeypatch, df: pd.DataFrame) -> TestClient:
    loader_mock = MagicMock()
    loader_mock.load.return_value = df
    monkeypatch.setattr(card_browser, "get_loader", lambda: loader_mock)

    sim_mock = MagicMock()
    sim_mock.find_similar.return_value = []
    monkeypatch.setattr(card_browser, "get_similarity", lambda: sim_mock)

    return TestClient(app)


def test_single_exact_name_match_redirects_to_detail_page(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring"), _fake_card("Lightning Bolt")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "Sol Ring"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/cards/Sol%20Ring"


def test_multiple_matches_do_not_redirect(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring"), _fake_card("Solemn Simulacrum")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "sol"}, follow_redirects=False)
    assert resp.status_code == 200


def test_empty_search_does_not_redirect_even_with_one_card(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", follow_redirects=False)
    assert resp.status_code == 200


def test_set_scoped_printing_carries_over_after_redirect(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring", printings="KHM, LEA"), _fake_card("Lightning Bolt")])
    monkeypatch.setattr(
        card_browser._image_cache, "get_printing_id_for_set",
        lambda name, code: "sol-khm-id" if name == "Sol Ring" and code.upper() == "KHM" else None,
    )
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "name:sol-ring set:khm"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/cards/Sol%20Ring"

        detail = client.get(resp.headers["location"])
        assert detail.status_code == 200
        assert "sol-khm-id" in detail.text
