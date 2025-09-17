from __future__ import annotations

import os
from deck_builder.random_entrypoint import build_random_full_deck


def test_random_full_build_is_deterministic_on_frozen_dataset(monkeypatch):
    # Use frozen dataset for determinism
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # Fixed seed should produce the same compact decklist
    out1 = build_random_full_deck(theme="Goblin Kindred", seed=777)
    out2 = build_random_full_deck(theme="Goblin Kindred", seed=777)

    assert out1.seed == out2.seed == 777
    assert out1.commander == out2.commander
    assert isinstance(out1.decklist, list) and isinstance(out2.decklist, list)
    assert out1.decklist == out2.decklist
