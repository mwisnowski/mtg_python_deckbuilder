"""
Unit tests for hyphen-as-space search matching in
code/web/services/card_search.py -- lets users type e.g. `rabbit-battery`
or `t:legendary-creature` instead of quoting spaces.
"""
from __future__ import annotations

import pandas as pd

from code.web.services.card_search import (
    apply_extra_clauses,
    apply_name_clauses,
    apply_text_clauses,
    filter_names_fuzzy,
    parse_search_query,
)


def test_name_search_with_dash_matches_spaced_name():
    df = pd.DataFrame({"name": ["Rabbit Battery", "Other Card"]})
    result = apply_name_clauses(df, ["rabbit-battery"], [])
    assert list(result["name"]) == ["Rabbit Battery"]


def test_name_search_with_literal_hyphen_still_matches():
    df = pd.DataFrame({"name": ["Krark-Clan Ogre", "Other Card"]})
    result = apply_name_clauses(df, ["krark-clan"], [])
    assert list(result["name"]) == ["Krark-Clan Ogre"]


def test_filter_names_fuzzy_with_dash():
    names = ["Rabbit Battery", "Other Card"]
    assert filter_names_fuzzy(names, ["rabbit-battery"], []) == ["Rabbit Battery"]


def test_type_flag_with_dash_matches_spaced_type():
    df = pd.DataFrame({"type": ["Legendary Creature - Human Wizard", "Instant"]})
    result = apply_text_clauses(df, "type", ["legendary-creature"], [])
    assert len(result) == 1


def test_oracle_flag_with_dash_matches_spaced_text():
    df = pd.DataFrame({"text": ["Draw a card.", "Nothing here."]})
    result = apply_text_clauses(df, "text", ["draw-a-card"], [])
    assert len(result) == 1


def test_tag_flag_with_dash_matches_spaced_tag():
    df = pd.DataFrame({
        "name": ["Card A", "Card B"],
        "themeTags": [["Spot Removal"], ["Ramp"]],
    })
    parsed = parse_search_query("tag:spot-removal")
    result = apply_extra_clauses(df, parsed)
    assert list(result["name"]) == ["Card A"]


def test_art_tag_flag_with_dash_matches_spaced_tag():
    df = pd.DataFrame({
        "name": ["Card A", "Card B"],
        "artTags": [["blue glow"], ["squirrel"]],
    })
    parsed = parse_search_query("art:blue-glow")
    result = apply_extra_clauses(df, parsed)
    assert list(result["name"]) == ["Card A"]


def test_tag_with_literal_hyphen_keyword_still_matches():
    df = pd.DataFrame({
        "name": ["Card A", "Card B"],
        "themeTags": [["Jump-start"], ["Ramp"]],
    })
    parsed = parse_search_query("tag:jump-start")
    result = apply_extra_clauses(df, parsed)
    assert list(result["name"]) == ["Card A"]
