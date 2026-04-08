"""Tests for isNew card column computation (Roadmap 23, M0)."""
from __future__ import annotations

import datetime
import json
import os
import tempfile

import pytest


def _write_bulk(cards: list[dict], path: str) -> None:
    """Write cards in scryfall bulk-data line-per-object format."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, card in enumerate(cards):
            f.write(json.dumps(card))
            if i < len(cards) - 1:
                f.write(",")
            f.write("\n")
        f.write("]\n")


TODAY = datetime.date(2026, 4, 6)
ROLLING_CUTOFF = TODAY - datetime.timedelta(days=6 * 30)  # ~2025-10-07

CARDS = [
    # Window 1 (2026-03-07): TMT expansion + TMC commander precon
    {"name": "New Expansion Card", "set": "TMT", "set_type": "expansion", "released_at": "2026-03-07", "reprint": False},
    {"name": "New Precon Card", "set": "TMC", "set_type": "commander", "released_at": "2026-03-07", "reprint": False},
    # Window 2 (2026-01-17): ECL
    {"name": "Window2 Card", "set": "ECL", "set_type": "expansion", "released_at": "2026-01-17", "reprint": False},
    # Window 3 (2025-11-07): TLA
    {"name": "Window3 Card", "set": "TLA", "set_type": "expansion", "released_at": "2025-11-07", "reprint": False},
    # Window 4 (2023-02-03): outside top-3 set window AND outside rolling 6-month window
    {"name": "Old Expansion Card", "set": "ONE", "set_type": "expansion", "released_at": "2023-02-03", "reprint": False},
    # Reprint within window 1 — should be excluded
    {"name": "Reprint Card", "set": "TMT", "set_type": "expansion", "released_at": "2026-03-07", "reprint": True},
    # Future spoiler — released_at > today
    {"name": "Future Card", "set": "SOS", "set_type": "expansion", "released_at": "2026-04-24", "reprint": False},
    # DFC: combined name AND each face should be indexed
    {"name": "DFC New // Back Face", "set": "TMT", "set_type": "expansion", "released_at": "2026-03-07", "reprint": False},
    # Promo card within rolling 6-month window (non-expansion set_type)
    {"name": "Rolling Window Card", "set": "PROMO", "set_type": "promo", "released_at": "2025-11-01", "reprint": False},
]


@pytest.fixture()
def bulk_path(tmp_path):
    path = str(tmp_path / "scryfall_bulk_data.json")
    _write_bulk(CARDS, path)
    return path


def test_new_card_in_window(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "new expansion card" in result
    assert "new precon card" in result
    assert "window2 card" in result
    assert "window3 card" in result


def test_future_card_excluded(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "future card" not in result


def test_reprint_excluded(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "reprint card" not in result


def test_old_card_outside_window_excluded(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "old expansion card" not in result


def test_dfc_faces_indexed(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "dfc new" in result
    assert "back face" in result


def test_rolling_window_non_expansion_included(bulk_path):
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk(bulk_path, 6, TODAY)
    assert "rolling window card" in result


def test_missing_bulk_file_returns_empty():
    from code.file_setup.setup import _compute_is_new_from_bulk
    result = _compute_is_new_from_bulk("/nonexistent/path.json", 6, TODAY)
    assert result == frozenset()


def test_get_new_card_names_returns_frozenset():
    from code.file_setup.setup import get_new_card_names
    # Works even without parquet present; returns frozenset
    result = get_new_card_names()
    assert isinstance(result, frozenset)
