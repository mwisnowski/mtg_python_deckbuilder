"""Tests for the public API's theme catalog endpoints (Roadmap 28, Milestone 6).

Uses the real theme catalog (config/themes/), matching the existing
convention in test_preview_export_endpoints.py / test_scryfall_name_normalization.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def sample_theme():
    from code.web.services.theme_catalog_loader import load_index

    idx = load_index()
    if not idx.catalog.themes:
        pytest.skip("No theme catalog available")
    # Prefer a plain alphabetic theme name (some entries have symbols like
    # "+1/+1 Counters" that don't round-trip cleanly through a URL path).
    for entry in idx.catalog.themes:
        if entry.theme.replace(" ", "").isalpha():
            return entry.theme
    return idx.catalog.themes[0].theme


def test_list_themes_no_filters(client, sample_theme):
    resp = client.get("/api/v1/themes")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_count"] >= 1
    assert len(data["themes"]) >= 1


def test_list_themes_by_query(client, sample_theme):
    resp = client.get("/api/v1/themes", params={"q": sample_theme})
    data = resp.json()["data"]
    names = {t["theme"] for t in data["themes"]}
    assert sample_theme in names


def test_list_themes_pagination(client):
    resp = client.get("/api/v1/themes", params={"page": 1, "page_size": 5})
    data = resp.json()["data"]
    assert len(data["themes"]) <= 5
    assert data["page"] == 1
    assert data["page_size"] == 5


def test_theme_detail(client, sample_theme):
    resp = client.get(f"/api/v1/themes/{sample_theme}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["theme"] == sample_theme


def test_theme_detail_not_found(client):
    resp = client.get("/api/v1/themes/definitely-not-a-real-theme-xyz")
    assert resp.status_code == 404
    assert resp.json()["code"] == "THEME_NOT_FOUND"


def test_theme_detail_with_slash_in_name(client):
    """Theme names like '+1/+1 Counters' contain a literal slash; the route
    must use a :path converter to handle this correctly."""
    resp = client.get("/api/v1/themes/+1/+1 Counters")
    assert resp.status_code == 200
    assert resp.json()["data"]["theme"] == "+1/+1 Counters"
