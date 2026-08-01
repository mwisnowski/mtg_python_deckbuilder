"""Integration-level tests for roadmap 33 creature allocation (modern vs legacy mode).

Full end-to-end deck builds need a rich card pool to exercise theme-based creature
selection realistically, which the tiny `csv_files/testdata` fixture doesn't provide.
These tests instead:
  - Exercise `_backfill_creature_floor()` directly against a synthetic creature pool
    (the real production method, just fed deterministic data).
  - Run the full headless pipeline against `csv_files/testdata` to confirm the
    legacy/modern mode selection actually threads end-to-end through the CLI-scripted
    input flow (Milestone 5) without depending on pool richness.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from code.deck_builder.builder import DeckBuilder
from code.headless_runner import run


def _make_builder(**ideal_overrides) -> DeckBuilder:
    b = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    b.ideal_counts.update(ideal_overrides)
    b._normalize_creature_ideal_keys()
    return b


def _synthetic_creature_pool(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": [f"Test Creature {i}" for i in range(n)],
            "type": ["Creature — Test"] * n,
            "manaCost": ["{1}"] * n,
            "manaValue": [1] * n,
            "creatureTypes": [[] for _ in range(n)],
            "themeTags": [[] for _ in range(n)],
            "edhrecRank": list(range(n)),
            "_multiMatch": [0] * n,
        }
    )


def test_backfill_creature_floor_adds_up_to_shortfall():
    b = _make_builder(creatures_max=20, creatures_min=5, on_theme_creatures=0)
    b._prepare_creature_pool = lambda: _synthetic_creature_pool(10)
    b._backfill_creature_floor()
    assert b._creature_count_in_library() == 5


def test_backfill_creature_floor_noop_when_floor_already_met():
    b = _make_builder(creatures_max=20, creatures_min=1, on_theme_creatures=0)
    b.add_card("Existing Creature", card_type="Creature")
    b._prepare_creature_pool = lambda: _synthetic_creature_pool(10)
    b._backfill_creature_floor()
    # Floor of 1 already satisfied by the pre-existing creature; no backfill added.
    assert b._creature_count_in_library() == 1


def test_backfill_creature_floor_noop_in_legacy_mode():
    b = _make_builder(creatures_max=20, creatures_min=10, on_theme_creatures=0)
    b.creature_builder_mode = "legacy"
    b._prepare_creature_pool = lambda: _synthetic_creature_pool(10)
    b._backfill_creature_floor()
    assert b._creature_count_in_library() == 0


def test_backfill_creature_floor_partial_when_pool_short():
    b = _make_builder(creatures_max=20, creatures_min=8, on_theme_creatures=0)
    b._prepare_creature_pool = lambda: _synthetic_creature_pool(3)
    b._backfill_creature_floor()
    assert b._creature_count_in_library() == 3


@pytest.fixture(autouse=True)
def _use_testdata(monkeypatch):
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))


def test_headless_legacy_mode_threads_end_to_end():
    builder = run(
        command_name="Krenko",
        seed=42,
        creature_builder_mode="legacy",
        ideal_counts={"creatures": 10, "creatures_min": 8, "on_theme_creatures": 2},
    )
    assert builder.creature_builder_mode == "legacy"
    # Modern-only ideal keys are still normalized/stored but ignored by the legacy phase target.
    assert builder._creature_phase_target() == builder.ideal_counts["creatures"]


def test_headless_modern_zero_max_adds_no_creatures():
    builder = run(
        command_name="Krenko",
        seed=42,
        creature_builder_mode="modern",
        ideal_counts={"creatures_max": 0},
    )
    assert builder.creature_builder_mode == "modern"
    assert builder._creature_phase_should_skip() is True
    assert builder._creature_count_in_library() == 0
