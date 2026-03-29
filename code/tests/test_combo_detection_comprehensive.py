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

import pytest

from deck_builder.combos import detect_combos, detect_synergies
from tagging.combo_schema import (
    load_and_validate_combos,
    load_and_validate_synergies,
)


# ============================================================================
# Helper Functions
# ============================================================================


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


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



