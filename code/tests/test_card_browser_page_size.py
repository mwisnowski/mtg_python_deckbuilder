"""
Tests for the card browser's configurable page size: CARD_BROWSER_PAGE_SIZE=0
(or unset) falls back to the legacy infinite-scroll "Load More" experience,
served by the paginated main route plus the new /cards/grid batch endpoint.
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


def test_infinite_scroll_mode_renders_load_more_button(monkeypatch):
    monkeypatch.setattr(card_browser, "CARD_BROWSER_PAGE_SIZE", 0)
    df = pd.DataFrame([_fake_card(f"Card {i}") for i in range(3)])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/")
    assert resp.status_code == 200
    assert 'id="load-more-container"' in resp.text  # container always renders in this mode
    assert "/cards/grid?page=" not in resp.text  # but no next batch, only 3 cards


def test_infinite_scroll_grid_endpoint_returns_next_batch(monkeypatch):
    monkeypatch.setattr(card_browser, "CARD_BROWSER_PAGE_SIZE", 0)
    df = pd.DataFrame([_fake_card(f"Card {i}") for i in range(120)])
    with _client(monkeypatch, df) as client:
        first = client.get("/cards/")
        assert "/cards/grid?page=2" in first.text

        second = client.get("/cards/grid", params={"page": 2})
    assert second.status_code == 200
    assert second.text.count("card-tile") > 0
    assert 'hx-swap-oob="true"' in second.text



def test_paginated_mode_has_no_load_more_button(monkeypatch):
    monkeypatch.setattr(card_browser, "CARD_BROWSER_PAGE_SIZE", 50)
    df = pd.DataFrame([_fake_card(f"Card {i}") for i in range(120)])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/")
    assert resp.status_code == 200
    assert 'id="load-more-container"' not in resp.text
    assert "card-browser-page-jump" in resp.text
