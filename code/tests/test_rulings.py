"""Tests for card rulings — service and route integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Service unit tests (code.web.services.rulings)
# ---------------------------------------------------------------------------

class TestRulingsService:
    def _run(self, coro):
        return asyncio.run(coro)

    def setup_method(self):
        # Reset module-level cache before each test
        import code.web.services.rulings as svc
        svc._rulings_cache = None

    def test_get_rulings_returns_cached(self, tmp_path, monkeypatch):
        """Cache hit: returns data without making a network call."""
        import code.web.services.rulings as svc

        fake_cache = {
            "abc-123": [
                {"published_at": "2022-10-14", "source": "wotc", "comment": "Test ruling."}
            ]
        }
        monkeypatch.setattr(svc, "RULINGS_CACHE_PATH", tmp_path / "rulings_cache.json")
        (tmp_path / "rulings_cache.json").write_text(json.dumps(fake_cache))

        result = self._run(svc.get_rulings("abc-123"))

        assert len(result) == 1
        assert result[0]["comment"] == "Test ruling."

    def test_get_rulings_live_fallback(self, tmp_path, monkeypatch):
        """Cache miss: fetches from Scryfall live and caches result."""
        import code.web.services.rulings as svc

        # Empty cache file
        monkeypatch.setattr(svc, "RULINGS_CACHE_PATH", tmp_path / "rulings_cache.json")
        (tmp_path / "rulings_cache.json").write_text(json.dumps({}))

        live_rulings = [
            {"published_at": "2023-01-01", "source": "scryfall", "comment": "Editorial note."}
        ]

        async def mock_live_fetch(scryfall_id):
            return live_rulings

        monkeypatch.setattr(svc, "_live_fetch", mock_live_fetch)

        result = self._run(svc.get_rulings("def-456"))

        assert result == live_rulings
        # Result should now be in memory cache
        assert svc._rulings_cache is not None
        assert "def-456" in svc._rulings_cache

    def test_get_rulings_network_error_returns_empty(self, tmp_path, monkeypatch):
        """Network failure during live fetch returns empty list."""
        import code.web.services.rulings as svc

        monkeypatch.setattr(svc, "RULINGS_CACHE_PATH", tmp_path / "rulings_cache.json")
        (tmp_path / "rulings_cache.json").write_text(json.dumps({}))

        async def mock_live_fetch_fail(scryfall_id):
            return []

        monkeypatch.setattr(svc, "_live_fetch", mock_live_fetch_fail)

        result = self._run(svc.get_rulings("missing-card"))
        assert result == []

    def test_get_rulings_empty_scryfall_id(self):
        """Empty scryfall_id returns [] without any cache/network access."""
        import code.web.services.rulings as svc
        result = self._run(svc.get_rulings(""))
        assert result == []


# ---------------------------------------------------------------------------
# Route integration test
# ---------------------------------------------------------------------------

class TestCardDetailRulings:
    """Verify rulings section is present in card detail page HTML."""

    def test_card_detail_renders_rulings_section(self, monkeypatch):
        """Card detail page includes a Rulings section."""
        import sys
        import pandas as pd
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock

        # Import app first so card_browser is fully initialized before patching
        from code.web.app import app
        import code.web.routes.card_browser as cb
        import code.web.services.rulings as svc

        # Minimal card dataframe
        fake_df = pd.DataFrame([{
            "name": "Sol Ring",
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
            "isNew": False,
            "price": None,
            "ck_price": None,
            "side": None,
        }])

        fake_rulings = [
            {"published_at": "2022-10-14", "source": "wotc", "comment": "Mana from Sol Ring is colorless."}
        ]

        loader_mock = MagicMock()
        loader_mock.load.return_value = fake_df
        monkeypatch.setattr(cb, "get_loader", lambda: loader_mock)

        sim_mock = MagicMock()
        sim_mock.find_similar.return_value = []
        monkeypatch.setattr(cb, "get_similarity", lambda: sim_mock)

        # Pre-populate rulings service cache (no network call)
        monkeypatch.setattr(svc, "_rulings_cache", {"test-scryfall-id": fake_rulings})

        with TestClient(app) as client:
            resp = client.get("/cards/Sol Ring")

        assert resp.status_code == 200
        assert "Rulings" in resp.text
        assert "Mana from Sol Ring is colorless." in resp.text
