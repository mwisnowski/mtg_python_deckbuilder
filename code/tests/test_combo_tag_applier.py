from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tagging.combo_tag_applier import apply_combo_tags


def _write_csv(dirpath: Path, color: str, rows: list[dict]):
    df = pd.DataFrame(rows)
    df.to_csv(dirpath / f"{color}_cards.csv", index=False)


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
