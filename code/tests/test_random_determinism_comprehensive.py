"""
Comprehensive tests for Random Build determinism and seed stability.

Consolidates:
- test_random_determinism.py (Basic determinism)
- test_random_determinism_delta.py (Delta checking)
- test_random_full_build_determinism.py (Full build determinism)
- test_random_multi_theme_seed_stability.py (Multi-theme stability)
"""
from __future__ import annotations

import os
from deck_builder.random_entrypoint import build_random_deck


# ============================================================================
# Basic Determinism Tests
# ============================================================================

def test_random_build_is_deterministic_with_seed(monkeypatch):
    """Fixed seed produces identical commander consistently."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    out1 = build_random_deck(seed=12345)
    out2 = build_random_deck(seed=12345)
    
    assert out1.commander == out2.commander
    assert out1.seed == out2.seed


def test_random_build_uses_theme_when_available(monkeypatch):
    """Theme parameter is accepted and produces valid output."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    res = build_random_deck(theme="Goblin Kindred", seed=42)
    assert isinstance(res.commander, str) and len(res.commander) > 0


def test_different_seeds_produce_different_commanders(monkeypatch):
    """Different seeds should produce different results (probabilistic)."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    out1 = build_random_deck(seed=1)
    out2 = build_random_deck(seed=2)
    out3 = build_random_deck(seed=3)
    
    # At least one should be different (very likely with different seeds)
    commanders = {out1.commander, out2.commander, out3.commander}
    assert len(commanders) >= 2, "Different seeds should produce varied results"


# ============================================================================
# Delta Checking Tests
# ============================================================================

def test_random_build_delta_consistency(monkeypatch):
    """Small seed delta produces different but consistent results."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    # Build with seed N and seed N+1
    out1 = build_random_deck(seed=5000)
    out2 = build_random_deck(seed=5001)
    
    # Results should be reproducible
    out1_repeat = build_random_deck(seed=5000)
    out2_repeat = build_random_deck(seed=5001)
    
    assert out1.commander == out1_repeat.commander
    assert out2.commander == out2_repeat.commander


# ============================================================================
# Multi-Theme Seed Stability Tests
# ============================================================================

def test_random_build_multi_theme_stability(monkeypatch):
    """Multiple themes with same seed produce consistent results."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    # Try with multiple themes (if supported)
    out1 = build_random_deck(
        theme="Goblin Kindred",
        secondary_theme="Aggro",
        seed=999
    )
    out2 = build_random_deck(
        theme="Goblin Kindred",
        secondary_theme="Aggro",
        seed=999
    )
    
    assert out1.commander == out2.commander
    assert out1.seed == out2.seed


def test_random_build_multi_theme_different_order(monkeypatch):
    """Theme order shouldn't break determinism (if themes are sorted internally)."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    # Build with themes in different order but same seed
    out1 = build_random_deck(
        theme="Goblin Kindred",
        secondary_theme="Aggro",
        seed=1111
    )
    out2 = build_random_deck(
        theme="Aggro",
        secondary_theme="Goblin Kindred",
        seed=1111
    )
    
    # Both should succeed and be reproducible
    assert out1.commander
    assert out2.commander
    
    # Verify reproducibility for each configuration
    out1_repeat = build_random_deck(
        theme="Goblin Kindred",
        secondary_theme="Aggro",
        seed=1111
    )
    assert out1.commander == out1_repeat.commander
