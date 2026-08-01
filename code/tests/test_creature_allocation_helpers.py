"""Unit tests for roadmap 33 creature allocation helpers (no full deck build required)."""
from __future__ import annotations

from code.deck_builder import builder_utils as bu
from code.deck_builder.builder import DeckBuilder


def _make_builder(**ideal_overrides) -> DeckBuilder:
    b = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    b.ideal_counts.update(ideal_overrides)
    return b


def test_normalize_creature_ideal_keys_backfills_max_from_legacy_creatures():
    b = _make_builder(creatures=25)
    b._normalize_creature_ideal_keys()
    assert b.ideal_counts["creatures_max"] == 25
    assert b.ideal_counts["creatures_min"] == 0
    assert b.ideal_counts["on_theme_creatures"] == 25


def test_normalize_creature_ideal_keys_clamps_min_and_on_theme_to_max():
    b = _make_builder(creatures_max=10, creatures_min=50, on_theme_creatures=99, creature_tolerance=5.0)
    b._normalize_creature_ideal_keys()
    assert b.ideal_counts["creatures_min"] == 10
    assert b.ideal_counts["on_theme_creatures"] == 10
    assert b.ideal_counts["creature_tolerance"] == 0.15
    assert b.ideal_counts["creatures"] == 10


def test_creature_phase_target_modern_uses_on_theme_creatures():
    b = _make_builder(creatures_max=28, on_theme_creatures=20)
    b.creature_builder_mode = "modern"
    assert b._creature_phase_target() == 20


def test_creature_phase_target_legacy_uses_creatures():
    b = _make_builder(creatures=28, on_theme_creatures=20)
    b.creature_builder_mode = "legacy"
    assert b._creature_phase_target() == 28


def test_creature_phase_should_skip_when_max_is_zero():
    b = _make_builder(creatures_max=0)
    assert b._creature_phase_should_skip() is True


def test_creature_phase_should_not_skip_when_max_positive():
    b = _make_builder(creatures_max=28)
    assert b._creature_phase_should_skip() is False


def test_creature_cap_with_tolerance_applies_percentage():
    b = _make_builder(creatures_max=20, creature_tolerance=0.10)
    assert bu.creature_cap_with_tolerance(b) == 22


def test_creature_room_remaining_unlimited_in_legacy_mode():
    b = _make_builder(creatures_max=5, creature_tolerance=0.0)
    b.creature_builder_mode = "legacy"
    b._creature_count_in_library = lambda: 999
    assert bu.creature_room_remaining(b) == 10 ** 9


def test_creature_room_remaining_capped_in_modern_mode():
    b = _make_builder(creatures_max=5, creature_tolerance=0.0)
    b.creature_builder_mode = "modern"
    b._creature_count_in_library = lambda: 3
    assert bu.creature_room_remaining(b) == 2


def test_creature_room_remaining_zero_when_at_or_over_cap():
    b = _make_builder(creatures_max=5, creature_tolerance=0.0)
    b.creature_builder_mode = "modern"
    b._creature_count_in_library = lambda: 5
    assert bu.creature_room_remaining(b) == 0


def test_is_creature_row_case_insensitive():
    assert bu.is_creature_row({"type": "Legendary Creature — Goblin"}) is True
    assert bu.is_creature_row({"type": "artifact creature - equipment"}) is True
    assert bu.is_creature_row({"type": "Instant"}) is False
    assert bu.is_creature_row({}) is False
