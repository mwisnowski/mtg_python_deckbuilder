import ast
import json
from pathlib import Path

import pandas as pd
import pytest

import headless_runner as hr
from exceptions import CommanderValidationError
from file_setup import setup_utils as su
from file_setup.setup_utils import filter_dataframe, process_legendary_cards
import settings


@pytest.fixture
def tmp_csv_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "CSV_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(settings, "CSV_DIRECTORY", str(tmp_path))
    import importlib

    setup_module = importlib.import_module("file_setup.setup")
    monkeypatch.setattr(setup_module, "CSV_DIRECTORY", str(tmp_path))
    return Path(tmp_path)


def _make_card_row(
    *,
    name: str,
    face_name: str,
    type_line: str,
    side: str | None,
    layout: str,
    text: str = "",
    power: str | None = None,
    toughness: str | None = None,
) -> dict:
    return {
        "name": name,
        "faceName": face_name,
        "edhrecRank": 1000,
        "colorIdentity": "B",
        "colors": "B",
        "manaCost": "3B",
        "manaValue": 4,
        "type": type_line,
        "creatureTypes": "['Demon']" if "Creature" in type_line else "[]",
        "text": text,
        "power": power,
        "toughness": toughness,
        "keywords": "",
        "themeTags": "[]",
        "layout": layout,
        "side": side,
        "availability": "paper",
        "promoTypes": "",
        "securityStamp": "",
        "printings": "SET",
    }


def test_secondary_face_only_commander_removed(tmp_csv_dir):
    name = "Elbrus, the Binding Blade // Withengar Unbound"
    df = pd.DataFrame(
        [
            _make_card_row(
                name=name,
                face_name="Elbrus, the Binding Blade",
                type_line="Legendary Artifact — Equipment",
                side="a",
                layout="transform",
            ),
            _make_card_row(
                name=name,
                face_name="Withengar Unbound",
                type_line="Legendary Creature — Demon",
                side="b",
                layout="transform",
                power="13",
                toughness="13",
            ),
        ]
    )

    processed = process_legendary_cards(df)
    assert processed.empty

    exclusion_path = tmp_csv_dir / ".commander_exclusions.json"
    assert exclusion_path.exists(), "Expected commander exclusion diagnostics to be written"
    data = json.loads(exclusion_path.read_text(encoding="utf-8"))
    entries = data.get("secondary_face_only", [])
    assert any(entry.get("name") == name for entry in entries)


def test_primary_face_retained_and_log_cleared(tmp_csv_dir):
    name = "Birgi, God of Storytelling // Harnfel, Horn of Bounty"
    df = pd.DataFrame(
        [
            _make_card_row(
                name=name,
                face_name="Birgi, God of Storytelling",
                type_line="Legendary Creature — God",
                side="a",
                layout="modal_dfc",
                power="3",
                toughness="3",
            ),
            _make_card_row(
                name=name,
                face_name="Harnfel, Horn of Bounty",
                type_line="Legendary Artifact",
                side="b",
                layout="modal_dfc",
            ),
        ]
    )

    processed = process_legendary_cards(df)
    assert len(processed) == 1
    assert processed.iloc[0]["faceName"] == "Birgi, God of Storytelling"

    # Downstream filter should continue to succeed with a single primary row
    filtered = filter_dataframe(processed, [])
    assert len(filtered) == 1

    exclusion_path = tmp_csv_dir / ".commander_exclusions.json"
    assert not exclusion_path.exists(), "No exclusion log expected when primary face remains"


def test_headless_validation_reports_secondary_face(monkeypatch):
    monkeypatch.setattr(hr, "_load_commander_name_lookup", lambda: set())

    exclusion_entry = {
        "name": "Elbrus, the Binding Blade // Withengar Unbound",
        "primary_face": "Elbrus, the Binding Blade",
        "eligible_faces": ["Withengar Unbound"],
    }

    monkeypatch.setattr(hr, "lookup_commander_detail", lambda name: exclusion_entry if "Withengar" in name else None)

    with pytest.raises(CommanderValidationError) as excinfo:
        hr._validate_commander_available("Withengar Unbound")

    message = str(excinfo.value)
    assert "secondary face" in message.lower()
    assert "Withengar" in message


def test_commander_theme_tags_enriched(tmp_csv_dir):
    import importlib

    setup_module = importlib.import_module("file_setup.setup")

    name = "Eddie Brock // Venom, Lethal Protector"
    front_face = "Venom, Eddie Brock"
    back_face = "Venom, Lethal Protector"

    cards_df = pd.DataFrame(
        [
            _make_card_row(
                name=name,
                face_name=front_face,
                type_line="Legendary Creature — Symbiote",
                side="a",
                layout="modal_dfc",
                power="3",
                toughness="3",
                text="Other creatures you control get +1/+1.",
            ),
            _make_card_row(
                name=name,
                face_name=back_face,
                type_line="Legendary Creature — Horror",
                side="b",
                layout="modal_dfc",
                power="5",
                toughness="5",
                text="Menace",
            ),
        ]
    )
    cards_df.to_csv(tmp_csv_dir / "cards.csv", index=False)

    color_df = pd.DataFrame(
        [
            {
                "name": name,
                "faceName": front_face,
                "themeTags": "['Aggro', 'Counters']",
                "creatureTypes": "['Human', 'Warrior']",
                "roleTags": "['Commander']",
            },
            {
                "name": name,
                "faceName": back_face,
                "themeTags": "['Graveyard']",
                "creatureTypes": "['Demon']",
                "roleTags": "['Finisher']",
            },
        ]
    )
    color_df.to_csv(tmp_csv_dir / "black_cards.csv", index=False)

    setup_module.determine_commanders()

    commander_path = tmp_csv_dir / "commander_cards.csv"
    assert commander_path.exists(), "Expected commander CSV to be generated"

    commander_df = pd.read_csv(
        commander_path,
        converters={
            "themeTags": ast.literal_eval,
            "creatureTypes": ast.literal_eval,
            "roleTags": ast.literal_eval,
        },
    )
    assert "themeTags" in commander_df.columns

    row = commander_df[commander_df["faceName"] == front_face].iloc[0]
    assert set(row["themeTags"]) == {"Aggro", "Counters", "Graveyard"}
    assert set(row["creatureTypes"]) == {"Human", "Warrior", "Demon"}
    assert set(row["roleTags"]) == {"Commander", "Finisher"}
