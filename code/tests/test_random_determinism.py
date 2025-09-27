from __future__ import annotations

import os
from deck_builder.random_entrypoint import build_random_deck


def test_random_build_is_deterministic_with_seed(monkeypatch):
    # Force deterministic tiny dataset
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # Fixed seed should produce same commander consistently
    out1 = build_random_deck(seed=12345)
    out2 = build_random_deck(seed=12345)
    assert out1.commander == out2.commander
    assert out1.seed == out2.seed


def test_random_build_uses_theme_when_available(monkeypatch):
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # On tiny dataset, provide a theme that exists or not; either path should not crash
    res = build_random_deck(theme="Goblin Kindred", seed=42)
    assert isinstance(res.commander, str) and len(res.commander) > 0
