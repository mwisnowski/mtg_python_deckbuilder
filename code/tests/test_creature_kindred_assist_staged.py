"""Tests for Changeling/assist-card visibility during staged creature addition
(the web build's per-role Creatures: Primary/Secondary/Tertiary steps) and in
the manual builder's card pool, not just the end-of-build Creature Floor
Backfill step.
"""
from __future__ import annotations

import pandas as pd

from code.deck_builder.builder import DeckBuilder
from code.web.services import manual_builder_service as mbs


def _make_builder(**ideal_overrides) -> DeckBuilder:
    b = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    b.ideal_counts.update(ideal_overrides)
    b._normalize_creature_ideal_keys()
    return b


def _kindred_pool_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Plain Otter", "Morophon, the Boundless", "Off Theme Bear"],
            "type": ["Creature — Otter", "Legendary Creature — Shapeshifter", "Creature — Bear"],
            "manaCost": ["{1}{G}", "{3}{W}{U}{B}{R}{G}", "{2}{G}"],
            "manaValue": [2, 8, 3],
            "creatureTypes": [["Otter"], ["Shapeshifter"], ["Bear"]],
            "themeTags": [["Otter Kindred"], ["Changeling"], []],
            "metadataTags": [[], [], []],
            "edhrecRank": [100, 50, 200],
        }
    )


def test_add_creatures_for_role_includes_changeling_assist():
    """The staged per-role step (used by the real web build flow) should pull
    in a Changeling creature for a selected Kindred theme, not just the final
    Creature Floor Backfill fallback.
    """
    b = _make_builder(creatures_max=20, creatures_min=0, on_theme_creatures=2)
    b.primary_tag = "Otter Kindred"
    b._combined_cards_df = _kindred_pool_df()
    b._add_creatures_for_role("primary")
    assert set(b.card_library.keys()) == {"Plain Otter", "Morophon, the Boundless"}


def test_prepare_creature_pool_multi_match_counts_changeling_assist():
    b = _make_builder(creatures_max=20, creatures_min=0, on_theme_creatures=2)
    b.primary_tag = "Otter Kindred"
    b._combined_cards_df = _kindred_pool_df()
    pool = b._prepare_creature_pool()
    row = pool.loc[pool["name"] == "Morophon, the Boundless"].iloc[0]
    assert row["_multiMatch"] == 1
    off_theme = pool.loc[pool["name"] == "Off Theme Bear"].iloc[0]
    assert off_theme["_multiMatch"] == 0


def test_manual_builder_pool_theme_matches_include_changeling_assist():
    sess = {"tags": ["Otter Kindred"], "commander": None}
    sess["_pool_df"] = mbs._ensure_computed_columns(_kindred_pool_df())
    # Recompute _theme_matches the way get_card_pool() does (module-level
    # session cache bypassed here since we're feeding a pre-built pool).
    selected_lower = {"otter kindred"}
    selected_lower_to_orig = {"otter kindred": "Otter Kindred"}
    pool = sess["_pool_df"]
    pool["_theme_matches"] = [
        mbs._theme_matches_for_row(tags, meta, selected_lower, selected_lower_to_orig)
        for tags, meta in zip(pool["_tags"], pool["_metadata_tags"])
    ]
    changeling_matches = pool.loc[pool["name"] == "Morophon, the Boundless", "_theme_matches"].iloc[0]
    assert changeling_matches == ["Otter Kindred"]
    # Its own themeTags stay untouched -- only the ranking/category column is widened.
    changeling_tags = pool.loc[pool["name"] == "Morophon, the Boundless", "_tags"].iloc[0]
    assert changeling_tags == ["Changeling"]
