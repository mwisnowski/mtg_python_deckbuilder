from __future__ import annotations

import time

import pytest

from code.deck_builder.theme_catalog_loader import ThemeCatalogEntry
from code.deck_builder.theme_matcher import (
    ACCEPT_MATCH_THRESHOLD,
    SUGGEST_MATCH_THRESHOLD,
    ThemeMatcher,
    normalize_theme,
)


@pytest.fixture()
def sample_entries() -> list[ThemeCatalogEntry]:
    themes = [
        "Aristocrats",
        "Sacrifice Matters",
        "Life Gain",
        "Token Swarm",
        "Control",
        "Superfriends",
        "Spellslinger",
        "Artifact Tokens",
        "Treasure Storm",
        "Graveyard Loops",
    ]
    return [ThemeCatalogEntry(theme=theme, commander_count=0, card_count=0) for theme in themes]


def test_normalize_theme_collapses_spaces() -> None:
    assert normalize_theme("  Life   Gain \t") == "life gain"


def test_exact_match_case_insensitive(sample_entries: list[ThemeCatalogEntry]) -> None:
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("aristocrats")
    assert result.matched_theme == "Aristocrats"
    assert result.score == pytest.approx(100.0)
    assert result.reason == "high_confidence"


def test_minor_typo_accepts_with_high_score(sample_entries: list[ThemeCatalogEntry]) -> None:
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("aristrocrats")
    assert result.matched_theme == "Aristocrats"
    assert result.score >= ACCEPT_MATCH_THRESHOLD
    assert result.reason in {"high_confidence", "accepted_confidence"}


def test_multi_typo_only_suggests(sample_entries: list[ThemeCatalogEntry]) -> None:
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("arzstrcrats")
    assert result.matched_theme is None
    assert result.score >= SUGGEST_MATCH_THRESHOLD
    assert result.reason == "suggestions"
    assert any(s.theme == "Aristocrats" for s in result.suggestions)


def test_no_match_returns_empty(sample_entries: list[ThemeCatalogEntry]) -> None:
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("planeship")
    assert result.matched_theme is None
    assert result.suggestions == []
    assert result.reason in {"no_candidates", "no_match"}


def test_short_input_requires_exact(sample_entries: list[ThemeCatalogEntry]) -> None:
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("ar")
    assert result.matched_theme is None
    assert result.reason == "input_too_short"

    result_exact = matcher.resolve("lo")
    assert result_exact.matched_theme is None


def test_resolution_speed(sample_entries: list[ThemeCatalogEntry]) -> None:
    many_entries = [
        ThemeCatalogEntry(theme=f"Theme {i}", commander_count=0, card_count=0) for i in range(400)
    ]
    matcher = ThemeMatcher(many_entries)
    matcher.resolve("theme 42")

    start = time.perf_counter()
    for _ in range(20):
        matcher.resolve("theme 123")
    duration = time.perf_counter() - start
    # Observed ~0.03s per resolution (<=0.65s for 20 resolves) on dev machine (2025-10-02).
    assert duration < 0.7
