"""
Comprehensive Theme Validation Test Suite

This file consolidates all theme validation, matching, and related functionality tests.
Consolidates 5 source files into organized sections for easier maintenance and execution.

Source Files Consolidated:
1. test_theme_input_validation.py - API input validation and sanitization
2. test_theme_matcher.py - Theme matching, fuzzy search, and resolution logic
3. test_theme_description_fallback_regression.py - Editorial description fallback guardrails
4. test_theme_legends_historics_noise_filter.py - Noise filtering for synergies
5. test_theme_preview_ordering.py - Preview display and ordering logic

Total Tests: 16
Sections:
- Input Validation Tests (3)
- Theme Matcher Tests (8)
- Fallback & Regression Tests (1)
- Noise Filter Tests (1)
- Preview Ordering Tests (2)
- Shared Fixtures & Helpers (3)
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from code.deck_builder.theme_catalog_loader import ThemeCatalogEntry
from code.deck_builder.theme_matcher import (
    ACCEPT_MATCH_THRESHOLD,
    SUGGEST_MATCH_THRESHOLD,
    ThemeMatcher,
    normalize_theme,
)
from code.web.services.theme_catalog_loader import load_index, project_detail, slugify
from code.web.services.theme_preview import get_theme_preview

# ==============================================================================
# SHARED FIXTURES & HELPERS
# ==============================================================================


@pytest.fixture()
def sample_entries() -> list[ThemeCatalogEntry]:
    """Sample theme entries for matcher testing."""
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


def _client(monkeypatch):
    """Create test client with random modes and testdata CSV dir."""
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    app_module = importlib.import_module('code.web.app')
    return TestClient(app_module.app)


def _build_catalog():
    """Build theme catalog with no limit and return parsed JSON."""
    ROOT = Path(__file__).resolve().parents[2]
    BUILD_SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
    OUTPUT_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'
    
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), '--limit', '0'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"build_theme_catalog failed: {result.stderr or result.stdout}"
    assert OUTPUT_JSON.exists(), 'theme_list.json not emitted'
    return json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))


# ==============================================================================
# INPUT VALIDATION TESTS
# ==============================================================================


def test_theme_rejects_disallowed_chars(monkeypatch):
    """Theme input should reject SQL injection and other malicious characters."""
    client = _client(monkeypatch)
    bad = {"seed": 10, "theme": "Bad;DROP TABLE"}
    r = client.post('/api/random_full_build', json=bad)
    assert r.status_code == 200
    data = r.json()
    # Theme should be None or absent because it was rejected
    assert data.get('theme') in (None, '')


def test_theme_rejects_long(monkeypatch):
    """Theme input should reject excessively long strings."""
    client = _client(monkeypatch)
    long_theme = 'X'*200
    r = client.post('/api/random_full_build', json={"seed": 11, "theme": long_theme})
    assert r.status_code == 200
    assert r.json().get('theme') in (None, '')


def test_theme_accepts_normal(monkeypatch):
    """Theme input should accept valid theme names."""
    client = _client(monkeypatch)
    r = client.post('/api/random_full_build', json={"seed": 12, "theme": "Tokens"})
    assert r.status_code == 200
    assert r.json().get('theme') == 'Tokens'


# ==============================================================================
# THEME MATCHER TESTS
# ==============================================================================


def test_normalize_theme_collapses_spaces() -> None:
    """Normalization should collapse multiple spaces and trim whitespace."""
    assert normalize_theme("  Life   Gain \t") == "life gain"


def test_exact_match_case_insensitive(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Exact match should work case-insensitively with 100% confidence."""
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("aristocrats")
    assert result.matched_theme == "Aristocrats"
    assert result.score == pytest.approx(100.0)
    assert result.reason == "high_confidence"


def test_minor_typo_accepts_with_high_score(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Minor typos should still accept match with high confidence score."""
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("aristrocrats")
    assert result.matched_theme == "Aristocrats"
    assert result.score >= ACCEPT_MATCH_THRESHOLD
    assert result.reason in {"high_confidence", "accepted_confidence"}


def test_multi_typo_only_suggests(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Multiple typos should only suggest, not auto-accept."""
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("arzstrcrats")
    assert result.matched_theme is None
    assert result.score >= SUGGEST_MATCH_THRESHOLD
    assert result.reason == "suggestions"
    assert any(s.theme == "Aristocrats" for s in result.suggestions)


def test_no_match_returns_empty(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Complete mismatch should return empty result."""
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("planeship")
    assert result.matched_theme is None
    assert result.suggestions == []
    assert result.reason in {"no_candidates", "no_match"}


def test_short_input_requires_exact(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Short input (< 3 chars) should require exact match."""
    matcher = ThemeMatcher(sample_entries)
    result = matcher.resolve("ar")
    assert result.matched_theme is None
    assert result.reason == "input_too_short"

    result_exact = matcher.resolve("lo")
    assert result_exact.matched_theme is None


def test_resolution_speed(sample_entries: list[ThemeCatalogEntry]) -> None:
    """Theme resolution should complete within reasonable time bounds."""
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


# ==============================================================================
# FALLBACK & REGRESSION TESTS
# ==============================================================================


def test_generic_description_regression():
    """Regression test: ensure generic fallback descriptions remain below acceptable threshold."""
    ROOT = Path(__file__).resolve().parents[2]
    SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
    OUTPUT = ROOT / 'config' / 'themes' / 'theme_list_test_regression.json'
    
    # Run build with summary enabled directed to temp output
    env = os.environ.copy()
    env['EDITORIAL_INCLUDE_FALLBACK_SUMMARY'] = '1'
    # Avoid writing real catalog file; just produce alternate output
    cmd = [sys.executable, str(SCRIPT), '--output', str(OUTPUT)]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    data = json.loads(OUTPUT.read_text(encoding='utf-8'))
    summary = data.get('description_fallback_summary') or {}
    # Guardrails tightened (second wave). Prior baseline: ~357 generic (309 + 48).
    # New ceiling: <= 365 total generic and <52% share. Future passes should lower further.
    assert summary.get('generic_total', 0) <= 365, summary
    assert summary.get('generic_pct', 100.0) < 52.0, summary
    # Basic shape checks
    assert 'top_generic_by_frequency' in summary
    assert isinstance(summary['top_generic_by_frequency'], list)
    # Clean up temp output file
    try:
        OUTPUT.unlink()
    except Exception:
        pass


# ==============================================================================
# NOISE FILTER TESTS
# ==============================================================================


def test_legends_historics_noise_filtered():
    """Tests for suppression of noisy Legends/Historics synergies.
    
    Phase B build should remove Legends Matter / Historics Matter from every theme's synergy
    list except:
     - Legends Matter may list Historics Matter
     - Historics Matter may list Legends Matter
    No other theme should include either.
    """
    data = _build_catalog()
    legends_entry = None
    historics_entry = None
    for t in data['themes']:
        if t['theme'] == 'Legends Matter':
            legends_entry = t
        elif t['theme'] == 'Historics Matter':
            historics_entry = t
        else:
            assert 'Legends Matter' not in t['synergies'], f"Noise synergy 'Legends Matter' leaked into {t['theme']}"  # noqa: E501
            assert 'Historics Matter' not in t['synergies'], f"Noise synergy 'Historics Matter' leaked into {t['theme']}"  # noqa: E501
    # Mutual allowance
    if legends_entry:
        assert 'Historics Matter' in legends_entry['synergies'], 'Legends Matter should keep Historics Matter'
    if historics_entry:
        assert 'Legends Matter' in historics_entry['synergies'], 'Historics Matter should keep Legends Matter'


# ==============================================================================
# PREVIEW ORDERING TESTS
# ==============================================================================


@pytest.mark.parametrize("limit", [8, 12])
def test_preview_role_ordering(limit):
    """Ensure preview cards are ordered correctly: example → curated_synergy → other roles."""
    # Pick a deterministic existing theme (first catalog theme)
    idx = load_index()
    assert idx.catalog.themes, "No themes available for preview test"
    theme = idx.catalog.themes[0].theme
    preview = get_theme_preview(theme, limit=limit)
    # Ensure curated examples (role=example) all come before any curated_synergy, which come before any payoff/enabler/support/wildcard
    roles = [c["roles"][0] for c in preview["sample"] if c.get("roles")]
    # Find first indices
    first_curated_synergy = next((i for i, r in enumerate(roles) if r == "curated_synergy"), None)
    first_non_curated = next((i for i, r in enumerate(roles) if r not in {"example", "curated_synergy"}), None)
    # If both present, ordering constraints
    if first_curated_synergy is not None and first_non_curated is not None:
        assert first_curated_synergy < first_non_curated, "curated_synergy block should precede sampled roles"
    # All example indices must be < any curated_synergy index
    if first_curated_synergy is not None:
        for i, r in enumerate(roles):
            if r == "example":
                assert i < first_curated_synergy, "example card found after curated_synergy block"


def test_synergy_commanders_no_overlap_with_examples():
    """Synergy commanders should not include example commanders."""
    idx = load_index()
    theme_entry = idx.catalog.themes[0]
    slug = slugify(theme_entry.theme)
    detail = project_detail(slug, idx.slug_to_entry[slug], idx.slug_to_yaml, uncapped=False)
    examples = set(detail.get("example_commanders") or [])
    synergy_commanders = detail.get("synergy_commanders") or []
    assert not (examples.intersection(synergy_commanders)), "synergy_commanders should not include example_commanders"
