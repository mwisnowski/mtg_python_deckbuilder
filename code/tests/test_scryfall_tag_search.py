"""
Unit tests for the art:/atag:/arttag: search flag in
code/web/services/card_search.py.
"""
from __future__ import annotations

import pandas as pd

from code.web.services.card_search import (
    apply_extra_clauses,
    has_structured_flags,
    parse_search_query,
)


def _df():
    return pd.DataFrame({
        "name": ["Card A", "Card B", "Card C"],
        "artTags": [["blue glow", "squirrel"], ["squirrel"], []],
    })


def test_parse_art_flag_aliases():
    for flag in ("art", "atag", "arttag"):
        parsed = parse_search_query(f'{flag}:"blue glow"')
        assert parsed.art_tags == {"blue glow"}


def test_art_flag_negation():
    parsed = parse_search_query("-art:squirrel")
    assert parsed.art_tags_exclude == {"squirrel"}
    assert parsed.art_tags is None


def test_apply_extra_clauses_filters_by_art_tag():
    parsed = parse_search_query('art:squirrel')
    result = apply_extra_clauses(_df(), parsed)
    assert set(result["name"]) == {"Card A", "Card B"}


def test_apply_extra_clauses_excludes_by_art_tag():
    parsed = parse_search_query('-art:squirrel')
    result = apply_extra_clauses(_df(), parsed)
    assert set(result["name"]) == {"Card C"}


def test_apply_extra_clauses_noop_when_column_missing():
    parsed = parse_search_query('art:squirrel')
    df = _df().drop(columns=["artTags"])
    result = apply_extra_clauses(df, parsed)
    assert len(result) == len(df)


def test_has_structured_flags_true_for_art_tags():
    parsed = parse_search_query('art:squirrel')
    assert has_structured_flags(parsed)


def test_existing_theme_tag_flag_unaffected():
    parsed = parse_search_query('tag:Ramp')
    assert parsed.tags == {"ramp"}
    assert parsed.art_tags is None


def test_parse_metadata_flag_aliases():
    for flag in ("metadata", "mtag", "metatag"):
        parsed = parse_search_query(f'{flag}:"Bracket:GameChanger"')
        assert parsed.metadata_tags == {"bracket:gamechanger"}


def test_metadata_flag_negation():
    parsed = parse_search_query("-metadata:Bracket:GameChanger")
    assert parsed.metadata_tags_exclude == {"bracket:gamechanger"}
    assert parsed.metadata_tags is None


def test_apply_extra_clauses_filters_by_metadata_tag():
    df = pd.DataFrame({
        "name": ["Card A", "Card B", "Card C"],
        "metadataTags": [["Bracket:GameChanger"], ["Token Detail: 1/1 Soldier"], []],
    })
    parsed = parse_search_query('metadata:"Bracket:GameChanger"')
    result = apply_extra_clauses(df, parsed)
    assert set(result["name"]) == {"Card A"}


def test_has_structured_flags_true_for_metadata_tags():
    parsed = parse_search_query('metadata:Bracket:GameChanger')
    assert has_structured_flags(parsed)
