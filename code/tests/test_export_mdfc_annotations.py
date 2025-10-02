from __future__ import annotations

import csv
from pathlib import Path

import pytest

from code.deck_builder.phases.phase6_reporting import ReportingMixin


class DummyBuilder(ReportingMixin):
    def __init__(self) -> None:
        self.card_library = {
            "Valakut Awakening // Valakut Stoneforge": {
                "Card Type": "Instant",
                "Count": 2,
                "Mana Cost": "{2}{R}",
                "Mana Value": "3",
                "Role": "",
                "Tags": [],
            },
            "Mountain": {
                "Card Type": "Land",
                "Count": 1,
                "Mana Cost": "",
                "Mana Value": "0",
                "Role": "",
                "Tags": [],
            },
        }
        self.color_identity = ["R"]
        self.output_func = lambda *_args, **_kwargs: None  # silence export logs
        self._full_cards_df = None
        self._combined_cards_df = None
        self.custom_export_base = "test_dfc_export"


@pytest.fixture()
def builder(monkeypatch: pytest.MonkeyPatch) -> DummyBuilder:
    matrix = {
        "Valakut Awakening // Valakut Stoneforge": {
            "R": 1,
            "_dfc_land": True,
            "_dfc_counts_as_extra": True,
        },
        "Mountain": {"R": 1},
    }

    def _fake_compute(card_library, *_args, **_kwargs):
        return matrix

    monkeypatch.setattr(
        "deck_builder.builder_utils.compute_color_source_matrix",
        _fake_compute,
    )
    return DummyBuilder()


def test_export_decklist_csv_includes_dfc_note(tmp_path: Path, builder: DummyBuilder) -> None:
    csv_path = Path(builder.export_decklist_csv(directory=str(tmp_path)))
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = {row["Name"]: row for row in reader}

    valakut_row = rows["Valakut Awakening // Valakut Stoneforge"]
    assert valakut_row["DFCNote"] == "MDFC: Adds extra land slot"

    mountain_row = rows["Mountain"]
    assert mountain_row["DFCNote"] == ""


def test_export_decklist_text_appends_dfc_annotation(tmp_path: Path, builder: DummyBuilder) -> None:
    text_path = Path(builder.export_decklist_text(directory=str(tmp_path)))
    lines = text_path.read_text(encoding="utf-8").splitlines()

    valakut_line = next(line for line in lines if line.startswith("2 Valakut Awakening"))
    assert "[MDFC: Adds extra land slot]" in valakut_line

    mountain_line = next(line for line in lines if line.strip().endswith("Mountain"))
    assert "MDFC" not in mountain_line
