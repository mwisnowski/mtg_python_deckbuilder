"""Tests for deck-level token/emblem detection (roadmap_39, Milestone 5)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from code.deck_builder.tokens import detect_tokens_created


def _row(**overrides):
    base = {
        "name": "Goblin", "layout": "token", "type": "Token Creature — Goblin",
        "text": "", "power": "1", "toughness": "1", "isEmblem": False,
        "relatedCards": ["Krenko, Mob Boss"],
    }
    base.update(overrides)
    return base


def _write_tokens(rows: list[dict], tmp_path: Path) -> Path:
    path = tmp_path / "tokens.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_detects_token_created_by_single_card(tmp_path: Path):
    path = _write_tokens([_row()], tmp_path)
    result = detect_tokens_created(["Krenko, Mob Boss", "Sol Ring"], tokens_path=path)
    assert len(result) == 1
    assert result[0].token.name == "Goblin"
    assert result[0].created_by == ["Krenko, Mob Boss"]


def test_dedupes_identical_token_created_by_multiple_cards(tmp_path: Path):
    path = _write_tokens(
        [
            _row(relatedCards=["Krenko, Mob Boss"]),
            _row(relatedCards=["Goblin Rabblemaster"]),
        ],
        tmp_path,
    )
    result = detect_tokens_created(["Krenko, Mob Boss", "Goblin Rabblemaster"], tokens_path=path)
    assert len(result) == 1
    assert set(result[0].created_by) == {"Krenko, Mob Boss", "Goblin Rabblemaster"}


def test_commander_as_creator_is_detected(tmp_path: Path):
    path = _write_tokens([_row(relatedCards=["Krenko, Mob Boss"])], tmp_path)
    result = detect_tokens_created(["Krenko, Mob Boss"], tokens_path=path)
    assert len(result) == 1


def test_modal_multi_token_card_lists_all_possible_tokens(tmp_path: Path):
    path = _write_tokens(
        [
            _row(name="Soldier", type="Token Creature — Soldier", relatedCards=["Modal Card"]),
            _row(name="Bear", type="Token Creature — Bear", power="2", toughness="2", relatedCards=["Modal Card"]),
        ],
        tmp_path,
    )
    result = detect_tokens_created(["Modal Card"], tokens_path=path)
    names = {entry.token.name for entry in result}
    assert names == {"Soldier", "Bear"}


def test_no_token_creating_cards_returns_empty_list(tmp_path: Path):
    path = _write_tokens([_row()], tmp_path)
    result = detect_tokens_created(["Sol Ring", "Arcane Signet"], tokens_path=path)
    assert result == []


def test_missing_tokens_parquet_returns_empty_list_gracefully(tmp_path: Path):
    result = detect_tokens_created(["Krenko, Mob Boss"], tokens_path=tmp_path / "missing.parquet")
    assert result == []


def test_non_creature_token_has_none_power_toughness_not_nan(tmp_path: Path):
    path = _write_tokens(
        [
            _row(
                name="Treasure", type="Token Artifact — Treasure",
                power=float("nan"), toughness=float("nan"),
                relatedCards=["An Offer You Can't Refuse"],
            ),
        ],
        tmp_path,
    )
    result = detect_tokens_created(["An Offer You Can't Refuse"], tokens_path=path)
    assert len(result) == 1
    assert result[0].token.power is None
    assert result[0].token.toughness is None
