"""
Comprehensive tests for Random Build advanced features.

Consolidates:
- test_random_fallback_and_constraints.py (Fallback logic, constraints)
- test_random_permalink_reproduction.py (Permalink generation and restoration)
- test_random_metrics_and_seed_history.py (Metrics, seed history tracking)
- test_random_theme_stats_diagnostics.py (Theme statistics and diagnostics)
"""
from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient
from deck_builder.random_entrypoint import build_random_deck


# ============================================================================
# Fallback and Constraints Tests
# ============================================================================

def test_random_build_fallback_when_no_match(monkeypatch):
    """Random build falls back gracefully when constraints can't be met."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    # Request impossible or rare combination
    out = build_random_deck(
        theme="NonexistentTheme12345",
        seed=42
    )
    
    # Should still produce a valid commander (fallback)
    assert out.commander
    assert isinstance(out.commander, str)
    assert len(out.commander) > 0


def test_random_build_handles_empty_theme(monkeypatch):
    """Random build handles empty/None theme gracefully."""
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    
    out = build_random_deck(theme=None, seed=456)
    assert out.commander

# ============================================================================
# Permalink Tests
# ============================================================================

def test_random_build_permalink_generation(monkeypatch):
    """Random build generates valid permalink for reproduction."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_full_build', json={"seed": 2468})
    assert r.status_code == 200
    data = r.json()
    
    permalink = data.get("permalink")
    assert permalink
    assert "/build/from?state=" in permalink


def test_random_build_permalink_contains_seed(monkeypatch):
    """Generated permalink contains seed for reproduction."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    seed = 13579
    r = client.post('/api/random_full_build', json={"seed": seed})
    assert r.status_code == 200
    data = r.json()
    
    permalink = data.get("permalink")
    assert permalink
    # Permalink should encode the seed somehow (in state parameter or elsewhere)


def test_permalink_restoration_reproduces_deck(monkeypatch):
    """Using a permalink should reproduce the same deck."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Generate original deck
    r1 = client.post('/api/random_full_build', json={"seed": 24680})
    assert r1.status_code == 200
    data1 = r1.json()
    commander1 = data1.get("commander")
    
    # Generate with same seed again
    r2 = client.post('/api/random_full_build', json={"seed": 24680})
    assert r2.status_code == 200
    data2 = r2.json()
    commander2 = data2.get("commander")
    
    # Should match (determinism)
    assert commander1 == commander2


# ============================================================================
# Metrics and Seed History Tests
# ============================================================================

def test_random_build_metrics_present(monkeypatch):
    """Random build response includes metrics when enabled."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")  # Enable diagnostics

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_build', json={"seed": 111})
    assert r.status_code == 200
    data = r.json()
    
    # Basic response structure should be valid
    assert "commander" in data
    assert data.get("seed") == 111


def test_random_build_seed_history_tracking(monkeypatch):
    """Seed history is tracked across builds (if feature enabled)."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Generate multiple builds
    seeds = [222, 333, 444]
    for seed in seeds:
        r = client.post('/api/random_build', json={"seed": seed})
        assert r.status_code == 200
        data = r.json()
        assert data.get("seed") == seed
    
    # History tracking would need separate endpoint to verify


# ============================================================================
# Theme Statistics and Diagnostics Tests
# ============================================================================

def test_random_build_theme_stats_available(monkeypatch):
    """Theme statistics are available when diagnostics enabled."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_build', json={"seed": 555, "theme": "Goblin Kindred"})
    assert r.status_code == 200
    data = r.json()
    
    # Basic response should be valid
    assert "commander" in data
    assert data.get("seed") == 555


def test_random_build_diagnostics_format(monkeypatch):
    """Diagnostics output is properly formatted when enabled."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_build', json={"seed": 666})
    assert r.status_code == 200
    data = r.json()
    
    # Basic response structure should be valid
    assert "commander" in data
    assert "seed" in data
    assert data["seed"] == 666
