from __future__ import annotations

import os

from deck_builder.random_entrypoint import build_random_deck


def _use_testdata(monkeypatch) -> None:
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))


def test_multi_theme_same_seed_same_result(monkeypatch) -> None:
    _use_testdata(monkeypatch)
    kwargs = {
        "primary_theme": "Goblin Kindred",
        "secondary_theme": "Token Swarm",
        "tertiary_theme": "Treasure Support",
        "seed": 4040,
    }
    res_a = build_random_deck(**kwargs)
    res_b = build_random_deck(**kwargs)

    assert res_a.seed == res_b.seed == 4040
    assert res_a.commander == res_b.commander
    assert res_a.resolved_themes == res_b.resolved_themes


def test_legacy_theme_and_primary_equivalence(monkeypatch) -> None:
    _use_testdata(monkeypatch)

    legacy = build_random_deck(theme="Goblin Kindred", seed=5151)
    multi = build_random_deck(primary_theme="Goblin Kindred", seed=5151)

    assert legacy.commander == multi.commander
    assert legacy.seed == multi.seed == 5151


def test_string_seed_coerces_to_int(monkeypatch) -> None:
    _use_testdata(monkeypatch)

    result = build_random_deck(primary_theme="Goblin Kindred", seed="6262")

    assert result.seed == 6262
    # Sanity check that commander selection remains deterministic once coerced
    repeat = build_random_deck(primary_theme="Goblin Kindred", seed="6262")
    assert repeat.commander == result.commander
