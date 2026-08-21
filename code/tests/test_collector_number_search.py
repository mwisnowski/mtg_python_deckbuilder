"""
Unit tests for `cn:`/`number:` collector number filtering
(Roadmap 38, Milestone 3): code/web/services/card_search.py.
"""
from __future__ import annotations

import pandas as pd
import pytest

import code.web.services.card_search as card_search
from code.web.services.card_search import (
    apply_extra_clauses,
    parse_search_query,
    resolve_collector_number_printings,
)


@pytest.fixture(autouse=True)
def _reset_printings_index_cache():
    card_search._PRINTINGS_INDEX_DF = None
    card_search._PRINTINGS_INDEX_LOADED = False
    yield
    card_search._PRINTINGS_INDEX_DF = None
    card_search._PRINTINGS_INDEX_LOADED = False


@pytest.fixture()
def printings_index(tmp_path, monkeypatch):
    """Write a small fixture card_printings.parquet, simulating Modern
    Horizons 3 Commander's four Sol Ring printings (211-214)."""
    df = pd.DataFrame(
        [
            {"face_name": "Sol Ring", "set": "MSC", "collector_number": "211", "scryfall_id": "sol-211", "score": 10, "released_at": "2024-06-01"},
            {"face_name": "Sol Ring", "set": "MSC", "collector_number": "212", "scryfall_id": "sol-212", "score": 20, "released_at": "2024-06-01"},
            {"face_name": "Sol Ring", "set": "MSC", "collector_number": "213", "scryfall_id": "sol-213", "score": 5, "released_at": "2024-06-01"},
            {"face_name": "Sol Ring", "set": "MSC", "collector_number": "214", "scryfall_id": "sol-214", "score": 15, "released_at": "2024-06-01"},
            {"face_name": "Lightning Bolt", "set": "MSC", "collector_number": "007", "scryfall_id": "bolt-7", "score": 10, "released_at": "2024-06-01"},
            {"face_name": "Weird Card", "set": "MSC", "collector_number": "099a", "scryfall_id": "weird-99a", "score": 10, "released_at": "2024-06-01"},
            {"face_name": "Promo Card", "set": "MSC", "collector_number": "★", "scryfall_id": "promo-star", "score": 10, "released_at": "2024-06-01"},
        ]
    )
    path = tmp_path / "card_printings.parquet"
    df.to_parquet(path, engine="pyarrow")
    monkeypatch.setattr(card_search, "card_files_processed_dir", lambda: str(tmp_path))
    return path


def _all_cards_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Sol Ring", "Lightning Bolt", "Weird Card", "Promo Card"],
            "printings": ["MSC, LEA", "MSC, LEA", "MSC", "MSC"],
        }
    )


def test_exact_cn_isolates_one_printing(printings_index):
    parsed = parse_search_query("set:msc cn:212")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert list(df["name"]) == ["Sol Ring"]

    overlay = resolve_collector_number_printings(parsed)
    assert overlay == {"sol ring": "sol-212"}


def test_range_cn_matches_all_four_and_picks_best_scored(printings_index):
    parsed = parse_search_query("set:msc cn>210")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert list(df["name"]) == ["Sol Ring"]

    # 212 has the highest score (20) among the matched range -- wins the image.
    overlay = resolve_collector_number_printings(parsed)
    assert overlay == {"sol ring": "sol-212"}


def test_cn_without_set_is_noop_with_notice(printings_index):
    parsed = parse_search_query("cn:212")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert len(df) == 4  # unfiltered
    assert any("requires a set:" in n for n in parsed.notices)
    assert resolve_collector_number_printings(parsed) == {}


def test_leading_zero_normalization(printings_index):
    parsed = parse_search_query("set:msc cn:7")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert list(df["name"]) == ["Lightning Bolt"]


def test_suffixed_collector_number_exact_match(printings_index):
    parsed = parse_search_query("set:msc cn:99a")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert list(df["name"]) == ["Weird Card"]


def test_non_numeric_collector_number_excluded_from_range(printings_index):
    # "★" has no numeric prefix at all -- excluded from range comparisons
    # rather than erroring or being treated as 0.
    parsed = parse_search_query("set:msc cn>0")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert "Promo Card" not in list(df["name"])


def test_missing_printings_index_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(card_search, "card_files_processed_dir", lambda: str(tmp_path))  # no parquet written
    parsed = parse_search_query("set:msc cn:212")
    df = apply_extra_clauses(_all_cards_df(), parsed)
    assert len(df) == 4  # falls back to no cn filtering, no crash
    assert resolve_collector_number_printings(parsed) == {}


def test_get_set_collector_number_sort_map(printings_index):
    from code.web.services.card_search import get_set_collector_number_sort_map

    sort_map = get_set_collector_number_sort_map("MSC")
    # Sol Ring has 4 printings in MSC; the best-scored one (212) wins.
    assert sort_map["sol ring"] == 212
    assert sort_map["lightning bolt"] == 7  # leading zero stripped
    assert sort_map["weird card"] == 99  # numeric prefix of "099a"
    assert sort_map["promo card"] == float("inf")  # no numeric prefix ("★")


def test_get_set_collector_number_sort_map_unknown_set(printings_index):
    from code.web.services.card_search import get_set_collector_number_sort_map

    assert get_set_collector_number_sort_map("ZZZ") == {}

