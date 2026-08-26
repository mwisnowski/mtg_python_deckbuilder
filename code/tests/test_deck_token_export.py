"""Tests for the 'Tokens & Emblems Created' export section (roadmap_39, Milestone 5)."""
from __future__ import annotations

import csv
import sys
import types
from pathlib import Path

import pytest

from code.deck_builder.phases.phase6_reporting import ReportingMixin
from code.deck_builder.tokens import DetectedTokenSource, TokenRef


class _TokenBuilder(ReportingMixin):
    def __init__(self) -> None:
        self.card_library = {
            "Krenko, Mob Boss": {
                "Card Type": "Legendary Creature", "Count": 1,
                "Mana Cost": "{2}{R}{R}", "Mana Value": "4", "Role": "Commander", "Tags": [],
            },
            "Sol Ring": {
                "Card Type": "Artifact", "Count": 1,
                "Mana Cost": "{1}", "Mana Value": "1", "Role": "Ramp", "Tags": [],
            },
        }
        self.commander_name = "Krenko, Mob Boss"
        self.color_identity = ["R"]
        self.output_func = lambda *_args, **_kwargs: None
        self._full_cards_df = None
        self._combined_cards_df = None
        self.custom_export_base = "krenko_tokens_test"


def _suppress_color_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = types.ModuleType("deck_builder.builder_utils")
    stub.compute_color_source_matrix = lambda *_args, **_kwargs: {}
    stub.multi_face_land_info = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "deck_builder.builder_utils", stub)


def _fake_detect(_names):
    return [
        DetectedTokenSource(
            token=TokenRef(
                name="Goblin", type="Token Creature — Goblin",
                power="1", toughness="1", text="", is_emblem=False,
            ),
            created_by=["Krenko, Mob Boss"],
        ),
    ]


def test_build_deck_summary_includes_tokens_created(monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    monkeypatch.setattr("deck_builder.tokens.detect_tokens_created", _fake_detect)
    builder = _TokenBuilder()
    summary = builder.build_deck_summary()
    token = _fake_detect(None)[0].token
    assert summary["tokens_created"] == [
        {
            "token": {
                "name": "Goblin", "type": "Token Creature — Goblin", "power": "1", "toughness": "1",
                "is_emblem": False, "colors": "", "key": token.identity_key(), "text_hash": token.text_hash(),
            },
            "created_by": ["Krenko, Mob Boss"],
        }
    ]


def test_csv_export_appends_tokens_section_without_polluting_real_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _suppress_color_matrix(monkeypatch)
    monkeypatch.setattr("deck_builder.tokens.detect_tokens_created", _fake_detect)
    builder = _TokenBuilder()
    csv_path = Path(builder.export_decklist_csv(directory=str(tmp_path), filename="deck.csv"))

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    real_names = {
        row[0] for row in rows[1:]
        if row and row[0] and not row[0].startswith("#") and row[0] != "Total"
    }
    assert real_names == {"Krenko, Mob Boss", "Sol Ring"}

    token_rows = [row for row in rows if row and row[0].startswith("# Goblin")]
    assert len(token_rows) == 1
    assert token_rows[0][0] == "# Goblin (1/1)"
    assert token_rows[0][2] == "Token"
    assert "created by: Krenko, Mob Boss" in token_rows[0][15]


def test_text_export_appends_tokens_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _suppress_color_matrix(monkeypatch)
    monkeypatch.setattr("deck_builder.tokens.detect_tokens_created", _fake_detect)
    builder = _TokenBuilder()
    text_path = Path(builder.export_decklist_text(directory=str(tmp_path), filename="deck.txt"))
    lines = text_path.read_text(encoding="utf-8").splitlines()

    assert "# Tokens & Emblems Created (informational only, not part of deck count)" in lines
    assert "# Goblin (1/1) - created by: Krenko, Mob Boss" in lines

    # Every non-comment, non-blank line must still be a "count name" real card line.
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split(" ", 1)
        assert parts[0].isdigit()
