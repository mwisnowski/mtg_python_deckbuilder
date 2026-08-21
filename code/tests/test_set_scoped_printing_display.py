"""
Tests for the set-scoped default printing overlay (Roadmap 38, Milestone 2):
`ImageCache.get_printing_id_for_set()` and card_browser.py's
`_set_scoped_printings()` / `_apply_set_scoped_printings()`.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from code.file_setup.image_cache import ImageCache
from code.web.app import app  # noqa: F401  (import first to avoid a card_browser circular import)
import code.web.routes.card_browser as card_browser
from code.web.services.card_search import ParsedSearch


def _printings_df():
    return pd.DataFrame(
        [
            {
                "name": "Sol Ring", "face_name": "Sol Ring", "scryfall_id": "sol-khm",
                "set": "khm", "set_name": "Kaldheim", "collector_number": "1",
                "released_at": "2021-02-05", "finishes": ["nonfoil"], "score": 15,
                "image_url_small": "s", "image_url_normal": "n", "is_default": False,
            },
            {
                "name": "Sol Ring", "face_name": "Sol Ring", "scryfall_id": "sol-znr",
                "set": "znr", "set_name": "Zendikar Rising", "collector_number": "2",
                "released_at": "2020-09-25", "finishes": ["nonfoil"], "score": 15,
                "image_url_small": "s", "image_url_normal": "n", "is_default": False,
            },
            {
                "name": "Sol Ring", "face_name": "Sol Ring", "scryfall_id": "sol-lea",
                "set": "lea", "set_name": "Limited Edition Alpha", "collector_number": "3",
                "released_at": "1993-08-05", "finishes": ["nonfoil"], "score": 5,
                "image_url_small": "s", "image_url_normal": "n", "is_default": True,
            },
        ]
    )


@pytest.fixture()
def cache(tmp_path: Path) -> ImageCache:
    c = ImageCache(base_dir=str(tmp_path / "images"))
    c.printings_index_path = tmp_path / "card_printings.parquet"
    _printings_df().to_parquet(c.printings_index_path, index=False)
    return c


def test_get_printing_id_for_set_matches_code(cache: ImageCache):
    assert cache.get_printing_id_for_set("Sol Ring", "khm") == "sol-khm"
    assert cache.get_printing_id_for_set("Sol Ring", "KHM") == "sol-khm"  # case-insensitive


def test_get_printing_id_for_set_no_match_returns_none(cache: ImageCache):
    assert cache.get_printing_id_for_set("Sol Ring", "znc") is None
    assert cache.get_printing_id_for_set("Nonexistent Card", "khm") is None


def test_get_printing_id_for_set_missing_index_returns_none(tmp_path: Path):
    cache = ImageCache(base_dir=str(tmp_path / "images"))
    cache.printings_index_path = tmp_path / "card_printings.parquet"  # never written
    assert cache.get_printing_id_for_set("Sol Ring", "khm") is None


def test_set_scoped_printings_skips_manual_picks_and_notices_alternates():
    parsed = ParsedSearch(set_include={"KHM", "ZNR"})
    cards_list = [{"name": "Sol Ring"}, {"name": "Manually Picked Card"}]
    base_printings = {"manually picked card": "user-choice-id"}

    def _fake_get_printing_id_for_set(name, code):
        return {"khm": "sol-khm", "znr": "sol-znr"}.get(code.lower()) if name == "Sol Ring" else None

    with patch.object(card_browser._image_cache, "get_printing_id_for_set", side_effect=_fake_get_printing_id_for_set):
        overlay = card_browser._set_scoped_printings(cards_list, parsed, base_printings)

    assert overlay == {"sol ring": "sol-khm"}  # sorted set codes -> KHM before ZNR
    assert "Manually Picked Card" not in "".join(parsed.notices)
    assert len(parsed.notices) == 1
    assert "Sol Ring" in parsed.notices[0]


# --- Milestone 5: set + collector number badge ------------------------------

def test_get_printing_meta_by_scryfall_id(cache: ImageCache):
    meta = cache.get_printing_meta("Sol Ring", scryfall_id="sol-znr")
    assert meta == {"set": "ZNR", "set_name": "Zendikar Rising", "collector_number": "2"}


def test_get_printing_meta_by_set_code_falls_back_to_best_score(cache: ImageCache):
    # khm and znr tie at score=15; khm has the more recent released_at.
    meta = cache.get_printing_meta("Sol Ring", set_code="khm")
    assert meta == {"set": "KHM", "set_name": "Kaldheim", "collector_number": "1"}


def test_get_printing_meta_no_match_returns_none(cache: ImageCache):
    assert cache.get_printing_meta("Sol Ring", scryfall_id="not-a-real-id") is None
    assert cache.get_printing_meta("Nonexistent Card", set_code="khm") is None


def test_set_number_badges_only_when_exactly_one_set():
    cards_list = [{"name": "Sol Ring"}]

    def _fake_get_printing_meta(name, *, scryfall_id=None, set_code=None):
        assert set_code == "KHM"
        return {"set": "khm", "set_name": "Kaldheim", "collector_number": "1"}

    with patch.object(card_browser._image_cache, "get_printing_meta", side_effect=_fake_get_printing_meta):
        # No set: filter -> no badges.
        assert card_browser._set_number_badges(cards_list, ParsedSearch(), {}) == {}
        # Multiple set: filters -> ambiguous, no badges.
        assert card_browser._set_number_badges(cards_list, ParsedSearch(set_include={"KHM", "ZNR"}), {}) == {}
        # Exactly one set: filter -> badge populated.
        badges = card_browser._set_number_badges(cards_list, ParsedSearch(set_include={"KHM"}), {})
        assert badges == {"sol ring": {"set": "khm", "set_name": "Kaldheim", "collector_number": "1"}}


def test_set_scoped_printings_no_set_filter_returns_empty():
    assert card_browser._set_scoped_printings([{"name": "Sol Ring"}], None, {}) == {}
    assert card_browser._set_scoped_printings([{"name": "Sol Ring"}], ParsedSearch(), {}) == {}


def test_apply_set_scoped_printings_session_lifecycle(monkeypatch):
    session_store: dict = {}
    monkeypatch.setattr(card_browser, "get_session", lambda sid: session_store)

    parsed_khm = ParsedSearch(set_include={"KHM"})
    with patch.object(card_browser._image_cache, "get_printing_id_for_set", return_value="sol-khm"):
        result = card_browser._apply_set_scoped_printings("sid1", [{"name": "Sol Ring"}], parsed_khm, {})
    assert result == {"sol ring": "sol-khm"}
    assert session_store["search_set_printings"]["codes"] == ["KHM"]

    # Same set query, next page (pagination) -- accumulates rather than replacing.
    with patch.object(card_browser._image_cache, "get_printing_id_for_set", return_value="lotus-khm"):
        result = card_browser._apply_set_scoped_printings("sid1", [{"name": "Black Lotus"}], parsed_khm, {})
    assert result == {"sol ring": "sol-khm", "black lotus": "lotus-khm"}

    # A different set query replaces the stored overlay outright.
    parsed_znr = ParsedSearch(set_include={"ZNR"})
    with patch.object(card_browser._image_cache, "get_printing_id_for_set", return_value="sol-znr"):
        result = card_browser._apply_set_scoped_printings("sid1", [{"name": "Sol Ring"}], parsed_znr, {})
    assert result == {"sol ring": "sol-znr"}
    assert session_store["search_set_printings"]["codes"] == ["ZNR"]

    # A manual pick always wins over the auto overlay.
    with patch.object(card_browser._image_cache, "get_printing_id_for_set", return_value="sol-znr"):
        result = card_browser._apply_set_scoped_printings(
            "sid1", [{"name": "Sol Ring"}], parsed_znr, {"sol ring": "user-choice-id"}
        )
    assert result["sol ring"] == "user-choice-id"

    # No set filter clears the stored overlay.
    result = card_browser._apply_set_scoped_printings("sid1", [{"name": "Sol Ring"}], None, {})
    assert result == {}
    assert session_store["search_set_printings"] == {}
