"""
Comprehensive Combo Detection Test Suite

This file consolidates tests from 5 source files:
1. test_detect_combos.py (3 tests)
2. test_detect_combos_expanded.py (1 test)
3. test_detect_combos_more_new.py (1 test)
4. test_combo_schema_validation.py (3 tests)
5. test_combo_tag_applier.py (3 tests)

Total: 11 tests organized into 3 sections:
- Combo Detection Tests (5 tests)
- Schema Validation Tests (3 tests)
- Tag Applier Tests (3 tests)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from deck_builder.combos import detect_combos, detect_synergies
from tagging.combo_schema import (
    load_and_validate_combos,
    load_and_validate_synergies,
)
from tagging.combo_tag_applier import apply_combo_tags


# ============================================================================
# Helper Functions
# ============================================================================


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_csv(dirpath: Path, color: str, rows: list[dict]):
    df = pd.DataFrame(rows)
    df.to_csv(dirpath / f"{color}_cards.csv", index=False)


# ============================================================================
# Section 1: Combo Detection Tests
# ============================================================================
# Tests for combo and synergy detection functionality, including basic
# detection, expanded pairs, and additional combo pairs.
# ============================================================================


def test_detect_combos_positive(tmp_path: Path):
    combos = {
        "list_version": "0.1.0",
        "pairs": [
            {"a": "Thassa's Oracle", "b": "Demonic Consultation", "cheap_early": True, "tags": ["wincon"]},
            {"a": "Kiki-Jiki, Mirror Breaker", "b": "Zealous Conscripts"},
        ],
    }
    cpath = tmp_path / "config/card_lists/combos.json"
    _write_json(cpath, combos)

    deck = ["Thassa's Oracle", "Demonic Consultation", "Island"]
    found = detect_combos(deck, combos_path=str(cpath))
    assert any((fc.a.startswith("Thassa") and fc.b.startswith("Demonic")) for fc in found)
    assert any(fc.cheap_early for fc in found)


def test_detect_synergies_positive(tmp_path: Path):
    syn = {
        "list_version": "0.1.0",
        "pairs": [
            {"a": "Grave Pact", "b": "Phyrexian Altar", "tags": ["aristocrats"]},
        ],
    }
    spath = tmp_path / "config/card_lists/synergies.json"
    _write_json(spath, syn)

    deck = ["Swamp", "Grave Pact", "Phyrexian Altar"]
    found = detect_synergies(deck, synergies_path=str(spath))
    assert any((fs.a == "Grave Pact" and fs.b == "Phyrexian Altar") for fs in found)


def test_detect_combos_negative(tmp_path: Path):
    combos = {"list_version": "0.1.0", "pairs": [{"a": "A", "b": "B"}]}
    cpath = tmp_path / "config/card_lists/combos.json"
    _write_json(cpath, combos)
    found = detect_combos(["A"], combos_path=str(cpath))
    assert not found


def test_detect_expanded_pairs():
    names = [
        "Isochron Scepter",
        "Dramatic Reversal",
        "Basalt Monolith",
        "Rings of Brighthearth",
        "Some Other Card",
    ]
    combos = detect_combos(names, combos_path="config/card_lists/combos.json")
    found = {(c.a, c.b) for c in combos}
    assert ("Isochron Scepter", "Dramatic Reversal") in found
    assert ("Basalt Monolith", "Rings of Brighthearth") in found


def test_detect_more_new_pairs():
    names = [
        "Godo, Bandit Warlord",
        "Helm of the Host",
        "Narset, Parter of Veils",
        "Windfall",
        "Grand Architect",
        "Pili-Pala",
    ]
    combos = detect_combos(names, combos_path="config/card_lists/combos.json")
    pairs = {(c.a, c.b) for c in combos}
    assert ("Godo, Bandit Warlord", "Helm of the Host") in pairs
    assert ("Narset, Parter of Veils", "Windfall") in pairs
    assert ("Grand Architect", "Pili-Pala") in pairs


# ============================================================================
# Section 2: Schema Validation Tests
# ============================================================================
# Tests for combo and synergy JSON schema validation, ensuring proper
# structure and error handling for invalid data.
# ============================================================================


def test_validate_combos_schema_ok(tmp_path: Path):
    combos_dir = tmp_path / "config" / "card_lists"
    combos_dir.mkdir(parents=True)
    combos = {
        "list_version": "0.1.0",
        "generated_at": None,
        "pairs": [
            {"a": "Thassa's Oracle", "b": "Demonic Consultation", "cheap_early": True, "tags": ["wincon"]},
            {"a": "Kiki-Jiki, Mirror Breaker", "b": "Zealous Conscripts", "setup_dependent": False},
        ],
    }
    path = combos_dir / "combos.json"
    path.write_text(json.dumps(combos), encoding="utf-8")
    model = load_and_validate_combos(str(path))
    assert len(model.pairs) == 2
    assert model.pairs[0].a == "Thassa's Oracle"


def test_validate_synergies_schema_ok(tmp_path: Path):
    syn_dir = tmp_path / "config" / "card_lists"
    syn_dir.mkdir(parents=True)
    syn = {
        "list_version": "0.1.0",
        "generated_at": None,
        "pairs": [
            {"a": "Grave Pact", "b": "Phyrexian Altar", "tags": ["aristocrats"]},
        ],
    }
    path = syn_dir / "synergies.json"
    path.write_text(json.dumps(syn), encoding="utf-8")
    model = load_and_validate_synergies(str(path))
    assert len(model.pairs) == 1
    assert model.pairs[0].b == "Phyrexian Altar"


def test_validate_combos_schema_invalid(tmp_path: Path):
    combos_dir = tmp_path / "config" / "card_lists"
    combos_dir.mkdir(parents=True)
    invalid = {
        "list_version": "0.1.0",
        "pairs": [
            {"a": 123, "b": "Demonic Consultation"},  # a must be str
        ],
    }
    path = combos_dir / "bad_combos.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(Exception):
        load_and_validate_combos(str(path))


# ============================================================================
# Section 3: Tag Applier Tests
# ============================================================================
# Tests for applying combo tags to cards, including bidirectional tagging,
# name normalization, and split card face matching.
# Note: These tests are marked as skipped due to M4 architecture changes.
# ============================================================================


@pytest.mark.skip(reason="M4: apply_combo_tags no longer accepts colors/csv_dir parameters - uses unified Parquet")
def test_apply_combo_tags_bidirectional(tmp_path: Path):
    # Arrange: create a minimal CSV for blue with two combo cards
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True)
    rows = [
        {"name": "Thassa's Oracle", "themeTags": "[]", "creatureTypes": "[]"},
        {"name": "Demonic Consultation", "themeTags": "[]", "creatureTypes": "[]"},
        {"name": "Zealous Conscripts", "themeTags": "[]", "creatureTypes": "[]"},
    ]
    _write_csv(csv_dir, "blue", rows)

    # And a combos.json in a temp location
    combos_dir = tmp_path / "config" / "card_lists"
    combos_dir.mkdir(parents=True)
    combos = {
        "list_version": "0.1.0",
        "generated_at": None,
        "pairs": [
            {"a": "Thassa's Oracle", "b": "Demonic Consultation"},
            {"a": "Kiki-Jiki, Mirror Breaker", "b": "Zealous Conscripts"},
        ],
    }
    combos_path = combos_dir / "combos.json"
    combos_path.write_text(json.dumps(combos), encoding="utf-8")

    # Act
    counts = apply_combo_tags(colors=["blue"], combos_path=str(combos_path), csv_dir=str(csv_dir))

    # Assert
    assert counts.get("blue", 0) > 0
    df = pd.read_csv(csv_dir / "blue_cards.csv")
    # Oracle should list Consultation
    row_oracle = df[df["name"] == "Thassa's Oracle"].iloc[0]
    assert "Demonic Consultation" in row_oracle["comboTags"]
    # Consultation should list Oracle
    row_consult = df[df["name"] == "Demonic Consultation"].iloc[0]
    assert "Thassa's Oracle" in row_consult["comboTags"]
    # Zealous Conscripts is present but not its partner in this CSV; we still record the partner name
    row_conscripts = df[df["name"] == "Zealous Conscripts"].iloc[0]
    assert "Kiki-Jiki, Mirror Breaker" in row_conscripts.get("comboTags")


@pytest.mark.skip(reason="M4: apply_combo_tags no longer accepts colors/csv_dir parameters - uses unified Parquet")
def test_name_normalization_curly_apostrophes(tmp_path: Path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True)
    # Use curly apostrophe in CSV name, straight in combos
    rows = [
        {"name": "Thassa's Oracle", "themeTags": "[]", "creatureTypes": "[]"},
        {"name": "Demonic Consultation", "themeTags": "[]", "creatureTypes": "[]"},
    ]
    _write_csv(csv_dir, "blue", rows)

    combos_dir = tmp_path / "config" / "card_lists"
    combos_dir.mkdir(parents=True)
    combos = {
        "list_version": "0.1.0",
        "generated_at": None,
        "pairs": [{"a": "Thassa's Oracle", "b": "Demonic Consultation"}],
    }
    combos_path = combos_dir / "combos.json"
    combos_path.write_text(json.dumps(combos), encoding="utf-8")

    counts = apply_combo_tags(colors=["blue"], combos_path=str(combos_path), csv_dir=str(csv_dir))
    assert counts.get("blue", 0) >= 1
    df = pd.read_csv(csv_dir / "blue_cards.csv")
    row = df[df["name"] == "Thassa's Oracle"].iloc[0]
    assert "Demonic Consultation" in row["comboTags"]


@pytest.mark.skip(reason="M4: apply_combo_tags no longer accepts colors/csv_dir parameters - uses unified Parquet")
def test_split_card_face_matching(tmp_path: Path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True)
    # Card stored as split name in CSV
    rows = [
        {"name": "Fire // Ice", "themeTags": "[]", "creatureTypes": "[]"},
        {"name": "Isochron Scepter", "themeTags": "[]", "creatureTypes": "[]"},
    ]
    _write_csv(csv_dir, "izzet", rows)

    combos_dir = tmp_path / "config" / "card_lists"
    combos_dir.mkdir(parents=True)
    combos = {
        "list_version": "0.1.0",
        "generated_at": None,
        "pairs": [{"a": "Ice", "b": "Isochron Scepter"}],
    }
    combos_path = combos_dir / "combos.json"
    combos_path.write_text(json.dumps(combos), encoding="utf-8")

    counts = apply_combo_tags(colors=["izzet"], combos_path=str(combos_path), csv_dir=str(csv_dir))
    assert counts.get("izzet", 0) >= 1
    df = pd.read_csv(csv_dir / "izzet_cards.csv")
    row = df[df["name"] == "Fire // Ice"].iloc[0]
    assert "Isochron Scepter" in row["comboTags"]
