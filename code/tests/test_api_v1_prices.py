"""Tests for the public API's price lookup endpoint (Roadmap 28, Milestone 8).

Public endpoint (no auth). The real PriceService is monkeypatched with a
stub so tests don't depend on real price cache files being present.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _StubPriceService:
    def get_price(self, name, region="usd", foil=False):
        return 1.23 if name == "Sol Ring" else None

    def get_ck_price(self, name):
        return 4.56 if name == "Sol Ring" else None


@pytest.fixture()
def client(monkeypatch):
    import code.web.routes.api_v1.prices as prices_mod

    monkeypatch.setattr(prices_mod, "get_price_service", lambda: _StubPriceService())
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_price_found(client):
    resp = client.get("/api/v1/prices/Sol Ring")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["price"] == 1.23
    assert data["ck_price"] == 4.56
    assert data["found"] is True


def test_price_not_found(client):
    resp = client.get("/api/v1/prices/Nonexistent Card")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["price"] is None
    assert data["found"] is False


def test_price_no_auth_required(client):
    """Prices are public -- no Authorization header needed."""
    resp = client.get("/api/v1/prices/Sol Ring")
    assert resp.status_code == 200
