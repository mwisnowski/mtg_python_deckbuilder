"""
Unit tests for `set:`/`s:`/`e:`/`edition:` set-name resolution in
code/web/services/card_search.py (Roadmap 38, Milestone 1).
"""
from __future__ import annotations

import pandas as pd
import pytest

import code.web.services.card_search as card_search
from code.web.services.card_search import parse_search_query


@pytest.fixture(autouse=True)
def _reset_set_index_cache():
    """The set name/code index is cached as module globals for process
    lifetime -- reset before/after each test so fixtures don't leak."""
    card_search._SET_NAME_MAP = None
    card_search._SET_CODES = None
    card_search._SET_RELEASE_BY_CODE = None
    yield
    card_search._SET_NAME_MAP = None
    card_search._SET_CODES = None
    card_search._SET_RELEASE_BY_CODE = None


@pytest.fixture()
def printings_index(tmp_path, monkeypatch):
    """Write a small fixture card_printings.parquet and point card_search at it."""
    df = pd.DataFrame(
        {
            "set": ["khm", "eld", "aaa", "bbb", "ccc"],
            "set_name": [
                "Kaldheim",
                "Throne of Eldraine",
                "Commander One",
                "Commander One Two",
                "Commander Three",
            ],
            "released_at": ["2021-02-05", "2019-10-04", "2020-01-01", "2020-01-01", "2020-01-01"],
        }
    )
    path = tmp_path / "card_printings.parquet"
    df.to_parquet(path, engine="pyarrow")
    monkeypatch.setattr(card_search, "card_files_processed_dir", lambda: str(tmp_path))
    return path


def test_set_flag_still_resolves_code(printings_index):
    parsed = parse_search_query("set:khm")
    assert parsed.set_include == {"KHM"}
    assert parsed.notices == []


def test_set_flag_resolves_full_name(printings_index):
    parsed = parse_search_query("set:kaldheim")
    assert parsed.set_include == {"KHM"}
    assert parsed.notices == []


def test_set_flag_resolves_name_with_punctuation(printings_index):
    parsed = parse_search_query('set:"Throne of Eldraine"')
    assert parsed.set_include == {"ELD"}


def test_set_flag_ambiguous_name_picks_shortest_and_notices(printings_index):
    parsed = parse_search_query("set:commander")
    # "Commander One" (13 chars) is the shortest/closest match among the
    # three candidates containing "commander".
    assert parsed.set_include == {"AAA"}
    assert len(parsed.notices) == 1
    assert "Commander One Two (BBB)" in parsed.notices[0] or "Commander Three (CCC)" in parsed.notices[0]


def test_set_flag_unknown_value_falls_back_to_raw_code(printings_index):
    parsed = parse_search_query("set:zzz999")
    assert parsed.set_include == {"ZZZ999"}
    assert parsed.notices == []


def test_set_flag_falls_back_when_printings_index_missing(monkeypatch, tmp_path):
    # No card_printings.parquet exists at this path.
    monkeypatch.setattr(card_search, "card_files_processed_dir", lambda: str(tmp_path))
    parsed = parse_search_query("set:kaldheim")
    assert parsed.set_include == {"KALDHEIM"}
    assert parsed.notices == []


def test_set_exclude_flag_resolves_name(printings_index):
    parsed = parse_search_query("-set:kaldheim")
    assert parsed.set_exclude == {"KHM"}
    assert parsed.set_include == set()
