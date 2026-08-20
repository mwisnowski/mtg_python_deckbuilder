"""
Render smoke tests for the "Art Tags" collapsed section on the card detail
page (code/web/templates/browse/cards/detail.html). Uses TestClient since
Jinja template errors aren't caught by static analysis.
"""
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


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
    }
    base.update(overrides)
    return base


def _client(monkeypatch, df: pd.DataFrame) -> TestClient:
    from code.web.app import app
    import code.web.routes.card_browser as cb

    loader_mock = MagicMock()
    loader_mock.load.return_value = df
    monkeypatch.setattr(cb, "get_loader", lambda: loader_mock)

    sim_mock = MagicMock()
    sim_mock.find_similar.return_value = []
    monkeypatch.setattr(cb, "get_similarity", lambda: sim_mock)

    return TestClient(app)


def test_art_tags_section_present_when_tags_exist(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring", artTags=["blue glow", "squirrel"])])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/Sol Ring")
    assert resp.status_code == 200
    assert "Art Tags" in resp.text
    # Displayed Title Case, but the search link keeps the raw lowercase value.
    assert "Blue Glow" in resp.text
    assert "Squirrel" in resp.text
    assert "art%3A%22blue" in resp.text
    assert "glow%22" in resp.text


def test_art_tags_section_absent_when_no_tags(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring", artTags="")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/Sol Ring")
    assert resp.status_code == 200
    assert "Art Tags" not in resp.text


def test_metadata_tags_section_present_when_tags_exist(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring", metadataTags=["Bracket:GameChanger"])])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/Sol Ring")
    assert resp.status_code == 200
    assert "Metadata Tags" in resp.text
    assert "Bracket:GameChanger" in resp.text
    assert "metadata%3A%22Bracket" in resp.text


def test_metadata_tags_section_absent_when_no_tags(monkeypatch):
    df = pd.DataFrame([_fake_card("Sol Ring", metadataTags="")])
    with _client(monkeypatch, df) as client:
        resp = client.get("/cards/Sol Ring")
    assert resp.status_code == 200
    assert "Metadata Tags" not in resp.text
