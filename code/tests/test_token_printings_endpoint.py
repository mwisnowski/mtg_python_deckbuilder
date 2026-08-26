"""Tests for the public `GET /api/token-printings/{name}` endpoint, which
mirrors `/api/printings/{name}` for real cards but is keyed by a token's
full identity (name + type + power/toughness + colors + text hash) since
tokens can share a name with an unrelated real card or another token.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_get_token_printings_returns_identity_scoped_printings(monkeypatch):
    from code.web.app import app
    import code.web.routes.api as api_routes

    mock_cache = MagicMock()
    mock_cache.get_token_printings.return_value = [
        {"scryfall_id": "elemental-1-1", "set": "l12", "collector_number": "1"}
    ]
    mock_cache.get_default_token_printing_id.return_value = "elemental-1-1"
    monkeypatch.setattr(api_routes, "_image_cache", mock_cache)

    with TestClient(app) as client:
        resp = client.get(
            "/api/token-printings/Elemental",
            params={"power": "1", "toughness": "1", "type_line": "Token Creature — Elemental", "colors": "R"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_scryfall_id"] == "elemental-1-1"
    assert data["printings"] == [{"scryfall_id": "elemental-1-1", "set": "l12", "collector_number": "1"}]
    mock_cache.get_token_printings.assert_called_once_with("Elemental", "1", "1", "Token Creature — Elemental", "R", None)
