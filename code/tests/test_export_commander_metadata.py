from __future__ import annotations

import csv
from pathlib import Path
import sys
import types

import pytest

from code.deck_builder.combined_commander import CombinedCommander, PartnerMode
from code.deck_builder.phases.phase6_reporting import ReportingMixin


class MetadataBuilder(ReportingMixin):
    def __init__(self) -> None:
        self.card_library = {
            "Halana, Kessig Ranger": {
                "Card Type": "Legendary Creature",
                "Count": 1,
                "Mana Cost": "{3}{G}",
                "Mana Value": "4",
                "Role": "Commander",
                "Tags": ["Partner"],
            },
            "Alena, Kessig Trapper": {
                "Card Type": "Legendary Creature",
                "Count": 1,
                "Mana Cost": "{4}{R}",
                "Mana Value": "5",
                "Role": "Commander",
                "Tags": ["Partner"],
            },
            "Gruul Signet": {
                "Card Type": "Artifact",
                "Count": 1,
                "Mana Cost": "{2}",
                "Mana Value": "2",
                "Role": "Ramp",
                "Tags": [],
            },
        }
        self.output_func = lambda *_args, **_kwargs: None
        self.combined_commander = CombinedCommander(
            primary_name="Halana, Kessig Ranger",
            secondary_name="Alena, Kessig Trapper",
            partner_mode=PartnerMode.PARTNER,
            color_identity=("G", "R"),
            theme_tags=("counters", "aggro"),
            raw_tags_primary=("counters",),
            raw_tags_secondary=("aggro",),
            warnings=(),
        )
        self.commander_name = "Halana, Kessig Ranger"
        self.secondary_commander = "Alena, Kessig Trapper"
        self.partner_mode = PartnerMode.PARTNER
        self.combined_color_identity = ("G", "R")
        self.color_identity = ["G", "R"]
        self.selected_tags = ["Counters", "Aggro"]
        self.primary_tag = "Counters"
        self.secondary_tag = "Aggro"
        self.tertiary_tag = None
        self.custom_export_base = "metadata_builder"


def _suppress_color_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = types.ModuleType("deck_builder.builder_utils")
    stub.compute_color_source_matrix = lambda *_args, **_kwargs: {}
    stub.multi_face_land_info = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "deck_builder.builder_utils", stub)


def test_csv_header_includes_commander_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    csv_path = Path(builder.export_decklist_csv(directory=str(tmp_path), filename="deck.csv"))
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert reader.fieldnames[-1] == "Commanders: Halana, Kessig Ranger, Alena, Kessig Trapper"
        rows = list(reader)
    assert any(row["Name"] == "Gruul Signet" for row in rows)


def test_text_export_includes_commander_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    text_path = Path(builder.export_decklist_text(directory=str(tmp_path), filename="deck.txt"))
    lines = text_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Commanders: Halana, Kessig Ranger, Alena, Kessig Trapper"
    assert lines[1] == "# Partner Mode: partner"
    assert lines[2] == "# Colors: G, R"
    assert lines[4].startswith("1 Halana, Kessig Ranger")


def test_summary_contains_combined_commander_block(monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    builder = MetadataBuilder()
    summary = builder.build_deck_summary()
    commander_block = summary["commander"]
    assert commander_block["names"] == [
        "Halana, Kessig Ranger",
        "Alena, Kessig Trapper",
    ]
    assert commander_block["partner_mode"] == "partner"
    assert commander_block["color_identity"] == ["G", "R"]
    combined = commander_block["combined"]
    assert combined["primary_name"] == "Halana, Kessig Ranger"
    assert combined["secondary_name"] == "Alena, Kessig Trapper"
    assert combined["partner_mode"] == "partner"
    assert combined["color_identity"] == ["G", "R"]
