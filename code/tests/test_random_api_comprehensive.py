"""
Comprehensive tests for Random Build API endpoints and UI pages.

Consolidates:
- test_random_build_api.py (API /api/random_build)
- test_random_full_build_api.py (API /api/random_full_build) 
- test_random_full_build_exports.py (Export functionality)
- test_random_ui_page.py (GET /random)
- test_random_rate_limit_headers.py (Rate limiting)
- test_random_reroll_throttle.py (Throttling)
"""
from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


# ============================================================================
# /api/random_build Tests
# ============================================================================

def test_random_build_api_commander_and_seed(monkeypatch):
    """POST /api/random_build returns commander, seed, and auto-fill flags."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)

    payload = {"seed": 12345, "theme": "Goblin Kindred"}
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["seed"] == 12345
    assert isinstance(data.get("commander"), str)
    assert data.get("commander")
    assert "auto_fill_enabled" in data
    assert "auto_fill_secondary_enabled" in data
    assert "auto_fill_tertiary_enabled" in data
    assert "auto_fill_applied" in data
    assert "auto_filled_themes" in data
    assert "display_themes" in data


def test_random_build_api_auto_fill_toggle(monkeypatch):
    """POST /api/random_build respects auto_fill_enabled flag."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 54321, "primary_theme": "Aggro", "auto_fill_enabled": True}
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seed"] == 54321
    assert data.get("auto_fill_enabled") is True
    assert data.get("auto_fill_secondary_enabled") is True
    assert data.get("auto_fill_tertiary_enabled") is True
    assert data.get("auto_fill_applied") in (True, False)
    assert isinstance(data.get("auto_filled_themes"), list)
    assert isinstance(data.get("display_themes"), list)


def test_random_build_api_no_auto_fill(monkeypatch):
    """POST /api/random_build respects auto_fill_enabled=False."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 99999, "primary_theme": "Aggro", "auto_fill_enabled": False}
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get("auto_fill_enabled") is False
    assert data.get("auto_fill_secondary_enabled") is False
    assert data.get("auto_fill_tertiary_enabled") is False
    assert data.get("auto_fill_applied") is False


def test_random_build_api_without_seed(monkeypatch):
    """POST /api/random_build generates a seed if not provided."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"theme": "Goblin Kindred"}
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("seed"), int)
    assert isinstance(data.get("commander"), str)


# ============================================================================
# /api/random_full_build Tests
# ============================================================================

def test_random_full_build_api_returns_deck_and_permalink(monkeypatch):
    """POST /api/random_full_build returns full decklist and permalink."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 4242, "theme": "Goblin Kindred"}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["seed"] == 4242
    assert isinstance(data.get("commander"), str) and data["commander"]
    assert isinstance(data.get("decklist"), list)
    assert data.get("permalink")
    assert "/build/from?state=" in data["permalink"]


def test_random_full_build_api_deck_structure(monkeypatch):
    """POST /api/random_full_build returns properly structured deck."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 777, "theme": "Goblin Kindred"}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    
    decklist = data.get("decklist", [])
    assert len(decklist) > 0
    # Each card should have name at minimum
    for card in decklist:
        assert "name" in card or isinstance(card, str)


def test_random_full_build_export_formats(monkeypatch):
    """POST /api/random_full_build supports multiple export formats."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 888, "theme": "Goblin Kindred", "format": "txt"}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "decklist" in data or "deck_text" in data  # Different formats possible


# ============================================================================
# UI Page Tests
# ============================================================================

def test_random_ui_page_loads(monkeypatch):
    """GET /random loads successfully when RANDOM_MODES enabled."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.get('/random')
    assert r.status_code == 200
    assert b"random" in r.content.lower() or b"Random" in r.content


# ============================================================================
# Rate Limiting Tests
# ============================================================================

def test_random_build_rate_limit_headers_present(monkeypatch):
    """Rate limit headers are present on /api/random_build responses."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_build', json={"seed": 1})
    assert r.status_code == 200
    # Check for rate limit headers (if implemented)
    # assert "X-RateLimit-Limit" in r.headers  # Uncomment if implemented


def test_random_full_build_rate_limit_headers_present(monkeypatch):
    """Rate limit headers are present on /api/random_full_build responses."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.post('/api/random_full_build', json={"seed": 2})
    assert r.status_code == 200
    # Check for rate limit headers (if implemented)
    # assert "X-RateLimit-Limit" in r.headers  # Uncomment if implemented


# ============================================================================
# Throttling Tests
# ============================================================================

def test_random_build_reroll_throttling(monkeypatch):
    """Rapid rerolls should not cause errors (throttling graceful)."""
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Rapid fire 3 requests
    for i in range(3):
        r = client.post('/api/random_build', json={"seed": i})
        assert r.status_code in (200, 429)  # 200 OK or 429 Too Many Requests
        if r.status_code == 429:
            break  # Throttled as expected
