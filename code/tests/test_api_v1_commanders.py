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
    assert data["is_rulebreaker"] is False
    assert data["rulebreaker_rule_type"] is None


def test_commander_detail_rulebreaker_metadata(client, monkeypatch):
    """Roadmap 35, Milestone 7: a Rulebreaker commander's detail response
    includes archetype metadata the mobile client uses to show the optional
    color picker / deck-size field."""
    from code.web.services.commander_catalog_loader import CommanderRecord, find_commander_record
    import code.web.routes.api_v1.commanders as commanders_route

    fake_record = CommanderRecord(
        name="Tolabow, Loch Rascal",
        face_name="Tolabow, Loch Rascal",
        display_name="Tolabow, Loch Rascal",
        slug="tolabow-loch-rascal",
        color_identity=("U",),
        color_identity_key="U",
        is_colorless=False,
        colors=("U",),
        mana_cost="{1}{U}",
        mana_value=2.0,
        type_line="Legendary Creature — Human Rogue",
        creature_types=("Human", "Rogue"),
        oracle_text="Rulebreaker — Instants and sorceries you cast can include one color of your choice not in your commander's color identity.",
        power=None,
        toughness=None,
        keywords=(),
        themes=(),
        theme_tokens=(),
        edhrec_rank=None,
        layout="normal",
        side=None,
        image_small_url="",
        image_normal_url="",
        partner_with=(),
        has_plain_partner=False,
        is_partner=False,
        supports_backgrounds=False,
        is_background=False,
        is_doctor=False,
        is_doctors_companion=False,
        restricted_partner_labels=(),
        search_haystack="tolabow, loch rascal",
    )
    monkeypatch.setattr(commanders_route, "find_commander_record", lambda name: fake_record)

    resp = client.get("/api/v1/commanders/Tolabow, Loch Rascal")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_rulebreaker"] is True
    assert data["rulebreaker_rule_type"] == "instant_sorcery_extra_color"
    assert data["rulebreaker_no_max_deck_size"] is False


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
