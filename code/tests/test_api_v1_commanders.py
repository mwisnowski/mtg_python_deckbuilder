"""Tests for the public API's commander catalog endpoints (Roadmap 28, Milestone 6).

Uses the real commander catalog (testdata CSV set) rather than a synthetic
fixture, matching the existing convention in test_commanders_route.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    from code.web.services.commander_catalog_loader import clear_commander_catalog_cache

    csv_dir = Path("csv_files/testdata").resolve()
    monkeypatch.setenv("CSV_FILES_DIR", str(csv_dir))
    clear_commander_catalog_cache()
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    clear_commander_catalog_cache()


@pytest.fixture()
def sample_commander():
    from code.web.services.commander_catalog_loader import load_commander_catalog

    catalog = load_commander_catalog()
    if not catalog.entries:
        pytest.skip("No commander catalog available")
    return catalog.entries[0]


def test_list_commanders_no_filters(client, sample_commander):
    resp = client.get("/api/v1/commanders")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_count"] >= 1
    assert len(data["commanders"]) >= 1


def test_list_commanders_by_query(client, sample_commander):
    resp = client.get("/api/v1/commanders", params={"q": sample_commander.display_name})
    data = resp.json()["data"]
    names = {c["name"] for c in data["commanders"]}
    assert sample_commander.display_name in names


def test_commander_detail(client, sample_commander):
    resp = client.get(f"/api/v1/commanders/{sample_commander.display_name}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == sample_commander.display_name
    assert "oracle_text" in data


def test_commander_detail_not_found(client):
    resp = client.get("/api/v1/commanders/Definitely Not A Real Commander XYZ")
    assert resp.status_code == 404
    assert resp.json()["code"] == "COMMANDER_NOT_FOUND"


def test_commander_partners(client, sample_commander):
    resp = client.get(f"/api/v1/commanders/{sample_commander.display_name}/partners")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "options" in data
    assert isinstance(data["options"], list)


def test_commander_partners_not_found(client):
    resp = client.get("/api/v1/commanders/Definitely Not A Real Commander XYZ/partners")
    assert resp.status_code == 404
