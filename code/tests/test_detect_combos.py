from __future__ import annotations

import json
from pathlib import Path

from deck_builder.combos import detect_combos, detect_synergies


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


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

    deck = ["Thassa’s Oracle", "Demonic Consultation", "Island"]
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
