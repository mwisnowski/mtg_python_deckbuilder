from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagging.combo_schema import (
    load_and_validate_combos,
    load_and_validate_synergies,
)


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
