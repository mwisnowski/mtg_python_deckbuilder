"""Tests for PriceService - price lookup, caching, and batch operations."""
from __future__ import annotations

import json
import os
import time
import threading
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

from code.web.services.price_service import PriceService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bulk_line(name: str, usd: str = None, eur: str = None, usd_foil: str = None) -> str:
    """Return a JSON line matching Scryfall bulk data format."""
    card: Dict[str, Any] = {
        "object": "card",
        "name": name,
        "prices": {
            "usd": usd,
            "usd_foil": usd_foil,
            "eur": eur,
            "eur_foil": None,
            "tix": None,
        },
    }
    return json.dumps(card)


def _write_bulk_data(path: str, cards: list) -> None:
    """Write a minimal Scryfall bulk data JSON array (one card per line)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("[\n")
        for i, card in enumerate(cards):
            suffix = "," if i < len(cards) - 1 else ""
            fh.write(json.dumps(card) + suffix + "\n")
        fh.write("]\n")


@pytest.fixture
def bulk_data_file(tmp_path):
    """Minimal Scryfall bulk data with known prices."""
    cards = [
        {"object": "card", "name": "Lightning Bolt", "prices": {"usd": "0.50", "usd_foil": "2.00", "eur": "0.40", "eur_foil": None, "tix": None}},
        {"object": "card", "name": "Sol Ring", "prices": {"usd": "2.00", "usd_foil": "5.00", "eur": "1.80", "eur_foil": None, "tix": None}},
        {"object": "card", "name": "Mana Crypt", "prices": {"usd": "150.00", "usd_foil": "300.00", "eur": "120.00", "eur_foil": None, "tix": None}},
        # Card with no price
        {"object": "card", "name": "Unpriced Card", "prices": {"usd": None, "usd_foil": None, "eur": None, "eur_foil": None, "tix": None}},
        # Second printing of Lightning Bolt (cheaper)
        {"object": "card", "name": "Lightning Bolt", "prices": {"usd": "0.25", "usd_foil": "1.00", "eur": "0.20", "eur_foil": None, "tix": None}},
        # DFC card
        {"object": "card", "name": "Delver of Secrets // Insectile Aberration", "prices": {"usd": "1.50", "usd_foil": "8.00", "eur": "1.20", "eur_foil": None, "tix": None}},
    ]
    path = str(tmp_path / "scryfall_bulk_data.json")
    _write_bulk_data(path, cards)
    return path


@pytest.fixture
def price_svc(bulk_data_file, tmp_path):
    """PriceService pointed at the test bulk data, with a temporary cache path."""
    cache_path = str(tmp_path / "prices_cache.json")
    return PriceService(bulk_data_path=bulk_data_file, cache_path=cache_path, cache_ttl=3600)


# ---------------------------------------------------------------------------
# Tests: single price lookup
# ---------------------------------------------------------------------------

def test_get_price_known_card(price_svc):
    price = price_svc.get_price("Lightning Bolt")
    # Should return the cheapest printing (0.25, not 0.50)
    assert price == pytest.approx(0.25)


def test_get_price_case_insensitive(price_svc):
    assert price_svc.get_price("lightning bolt") == price_svc.get_price("LIGHTNING BOLT")


def test_get_price_foil(price_svc):
    foil = price_svc.get_price("Lightning Bolt", foil=True)
    # Cheapest foil printing
    assert foil == pytest.approx(1.00)


def test_get_price_eur_region(price_svc):
    price = price_svc.get_price("Sol Ring", region="eur")
    assert price == pytest.approx(1.80)


def test_get_price_unknown_card_returns_none(price_svc):
    assert price_svc.get_price("Nonexistent Card Name XYZ") is None


def test_get_price_unpriced_card_returns_none(price_svc):
    assert price_svc.get_price("Unpriced Card") is None


def test_get_price_expensive_card(price_svc):
    assert price_svc.get_price("Mana Crypt") == pytest.approx(150.00)


# ---------------------------------------------------------------------------
# Tests: DFC card name indexing
# ---------------------------------------------------------------------------

def test_get_price_dfc_combined_name(price_svc):
    price = price_svc.get_price("Delver of Secrets // Insectile Aberration")
    assert price == pytest.approx(1.50)


def test_get_price_dfc_front_face_name(price_svc):
    """Front face name alone should resolve to the DFC price."""
    price = price_svc.get_price("Delver of Secrets")
    assert price == pytest.approx(1.50)


def test_get_price_dfc_back_face_name(price_svc):
    """Back face name alone should also resolve."""
    price = price_svc.get_price("Insectile Aberration")
    assert price == pytest.approx(1.50)


# ---------------------------------------------------------------------------
# Tests: batch lookup
# ---------------------------------------------------------------------------

def test_get_prices_batch_all_found(price_svc):
    result = price_svc.get_prices_batch(["Lightning Bolt", "Sol Ring"])
    assert result["Lightning Bolt"] == pytest.approx(0.25)
    assert result["Sol Ring"] == pytest.approx(2.00)


def test_get_prices_batch_mixed_found_missing(price_svc):
    result = price_svc.get_prices_batch(["Lightning Bolt", "Unknown Card"])
    assert result["Lightning Bolt"] is not None
    assert result["Unknown Card"] is None


def test_get_prices_batch_empty_list(price_svc):
    assert price_svc.get_prices_batch([]) == {}


def test_get_prices_batch_preserves_original_case(price_svc):
    result = price_svc.get_prices_batch(["LIGHTNING BOLT"])
    # Key should match input case exactly
    assert "LIGHTNING BOLT" in result
    assert result["LIGHTNING BOLT"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Tests: cache persistence
# ---------------------------------------------------------------------------

def test_rebuild_writes_cache_file(price_svc, tmp_path):
    # Trigger load → rebuild
    price_svc.get_price("Sol Ring")
    assert os.path.exists(price_svc._cache_path)


def test_cache_file_has_expected_structure(price_svc, tmp_path):
    price_svc.get_price("Sol Ring")
    with open(price_svc._cache_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert "prices" in data
    assert "built_at" in data
    assert "sol ring" in data["prices"]


def test_fresh_cache_loaded_without_rebuild(bulk_data_file, tmp_path):
    """Second PriceService instance should load from cache, not rebuild."""
    cache_path = str(tmp_path / "prices_cache.json")

    svc1 = PriceService(bulk_data_path=bulk_data_file, cache_path=cache_path)
    svc1.get_price("Sol Ring")  # triggers rebuild → writes cache

    rebuild_calls = []
    svc2 = PriceService(bulk_data_path=bulk_data_file, cache_path=cache_path)
    orig_rebuild = svc2._rebuild_cache

    def patched_rebuild():
        rebuild_calls.append(1)
        orig_rebuild()

    svc2._rebuild_cache = patched_rebuild
    svc2.get_price("Sol Ring")  # should load from cache, not rebuild

    assert rebuild_calls == [], "Second instance should not rebuild when cache is fresh"


def test_stale_cache_triggers_rebuild(bulk_data_file, tmp_path):
    """Cache older than TTL should trigger a rebuild."""
    cache_path = str(tmp_path / "prices_cache.json")

    # Write a valid but stale cache file
    stale_data = {
        "prices": {"sol ring": {"usd": 2.0}},
        "built_at": time.time() - 99999,  # very old
    }
    with open(cache_path, "w") as fh:
        json.dump(stale_data, fh)
    # Set mtime to old as well
    old_time = time.time() - 99999
    os.utime(cache_path, (old_time, old_time))

    rebuild_calls = []
    svc = PriceService(bulk_data_path=bulk_data_file, cache_path=cache_path, cache_ttl=3600)
    orig_rebuild = svc._rebuild_cache

    def patched_rebuild():
        rebuild_calls.append(1)
        orig_rebuild()

    svc._rebuild_cache = patched_rebuild
    svc.get_price("Sol Ring")

    assert rebuild_calls == [1], "Stale cache should trigger a rebuild"


# ---------------------------------------------------------------------------
# Tests: cache stats / telemetry
# ---------------------------------------------------------------------------

def test_cache_stats_structure(price_svc):
    price_svc.get_price("Sol Ring")
    stats = price_svc.cache_stats()
    assert "total_entries" in stats
    assert "hit_count" in stats
    assert "miss_count" in stats
    assert "hit_rate" in stats
    assert "loaded" in stats
    assert stats["loaded"] is True


def test_cache_stats_hit_miss_counts(price_svc):
    price_svc.get_price("Sol Ring")       # hit
    price_svc.get_price("Unknown Card")   # miss
    stats = price_svc.cache_stats()
    assert stats["hit_count"] >= 1
    assert stats["miss_count"] >= 1


def test_cache_stats_hit_rate_zero_before_load():
    """Before any lookups, hit_rate should be 0."""
    svc = PriceService(bulk_data_path="/nonexistent", cache_path="/nonexistent/cache.json")
    # Don't trigger _ensure_loaded - call cache_stats indirectly via a direct check
    # We expect loaded=False and hit_rate=0
    # Note: cache_stats calls _ensure_loaded, so bulk_data missing → cache remains empty
    stats = svc.cache_stats()
    assert stats["hit_rate"] == 0.0


# ---------------------------------------------------------------------------
# Tests: background refresh
# ---------------------------------------------------------------------------

def test_refresh_cache_background_starts_thread(price_svc):
    price_svc.get_price("Sol Ring")  # ensure loaded
    price_svc.refresh_cache_background()
    # Allow thread to start
    time.sleep(0.05)
    # Thread should have run (or be running)
    assert price_svc._refresh_thread is not None


def test_refresh_cache_background_no_duplicate_threads(price_svc):
    price_svc.get_price("Sol Ring")
    price_svc.refresh_cache_background()
    t1 = price_svc._refresh_thread
    price_svc.refresh_cache_background()  # second call while thread running
    t2 = price_svc._refresh_thread
    assert t1 is t2, "Should not spawn a second refresh thread"


# ---------------------------------------------------------------------------
# Tests: missing / corrupted bulk data
# ---------------------------------------------------------------------------

def test_missing_bulk_data_returns_none(tmp_path):
    svc = PriceService(
        bulk_data_path=str(tmp_path / "nonexistent.json"),
        cache_path=str(tmp_path / "cache.json"),
    )
    assert svc.get_price("Sol Ring") is None


def test_corrupted_bulk_data_line_skipped(tmp_path):
    """Malformed JSON lines should be skipped without crashing."""
    bulk_path = str(tmp_path / "bulk.json")
    with open(bulk_path, "w") as fh:
        fh.write("[\n")
        fh.write('{"object":"card","name":"Sol Ring","prices":{"usd":"2.00","usd_foil":null,"eur":null,"eur_foil":null,"tix":null}}\n')
        fh.write("NOT VALID JSON,,,,\n")
        fh.write("]")

    svc = PriceService(
        bulk_data_path=bulk_path,
        cache_path=str(tmp_path / "cache.json"),
    )
    # Should still find Sol Ring despite corrupted line
    assert svc.get_price("Sol Ring") == pytest.approx(2.00)
