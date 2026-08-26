"""
Tests for routing tokens/emblems into the card browser (roadmap_39
follow-up): hidden by default, surfaced only via an explicit
`type:token`/`type:emblem` search, and never triggering the single-result
auto-redirect (tokens have no detail page).
"""
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from code.web.app import app  # noqa: F401  (import first to avoid a card_browser circular import)
import code.web.routes.card_browser as card_browser
import code.web.services.card_search as card_search


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


def _fake_token_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "name": "Goblin",
            "type": "Token Creature — Goblin",
            "text": "",
            "colors": "R",
            "colorIdentity": "R",
            "power": "1",
            "toughness": "1",
            "layout": "token",
            "themeTags": ["Creature Token", "Goblin Token"],
            "metadataTags": ["Token Detail: 1/1 Red Goblin"],
            "manaValue": 0.0,
            "manaCost": "",
            "loyalty": None,
            "rarity": "",
            "artTags": None,
            "isNew": False,
            "isReprint": False,
            "printings": "",
            "edhrecRank": None,
            "is_token": True,
            "is_emblem": False,
            "text_hash": "abc123",
        }
    ])


def _client(monkeypatch, df: pd.DataFrame) -> TestClient:
    loader_mock = MagicMock()
    loader_mock.load.return_value = df
    monkeypatch.setattr(card_browser, "get_loader", lambda: loader_mock)

    sim_mock = MagicMock()
    sim_mock.find_similar.return_value = []
    monkeypatch.setattr(card_browser, "get_similarity", lambda: sim_mock)

    return TestClient(app)


def test_type_token_search_surfaces_tokens_and_hides_real_cards(monkeypatch):
    monkeypatch.setattr(card_search, "load_tokens_browser_df", _fake_token_df)
    df = pd.DataFrame([_fake_card("Sol Ring"), _fake_card("Lightning Bolt")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "type:token"})
    assert resp.status_code == 200
    assert "Goblin" in resp.text
    assert "Sol Ring" not in resp.text


def test_plain_search_never_shows_tokens(monkeypatch):
    monkeypatch.setattr(card_search, "load_tokens_browser_df", _fake_token_df)
    df = pd.DataFrame([_fake_card("Sol Ring"), _fake_card("Goblin Recruiter")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "goblin"})
    assert resp.status_code == 200
    assert "Goblin Recruiter" in resp.text
    # The token catalog's "Goblin" token must not leak into a plain name search.
    assert "token-browser-tile" not in resp.text


def test_single_token_result_does_not_redirect(monkeypatch):
    monkeypatch.setattr(card_search, "load_tokens_browser_df", _fake_token_df)
    df = pd.DataFrame([_fake_card("Sol Ring")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/", params={"search": "type:token"}, follow_redirects=False)
    # Exactly one token result -- must render the grid, not 302 to /cards/Goblin
    # (tokens have no detail page).
    assert resp.status_code == 200
