from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


def test_random_build_api_commander_and_seed(monkeypatch):
    # Enable Random Modes and use tiny dataset
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


def test_random_build_api_partial_auto_fill(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {
        "seed": 98765,
        "primary_theme": "Aggro",
        "auto_fill_secondary_enabled": True,
        "auto_fill_tertiary_enabled": False,
    }
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seed"] == 98765
    assert data.get("auto_fill_enabled") is True
    assert data.get("auto_fill_secondary_enabled") is True
    assert data.get("auto_fill_tertiary_enabled") is False
    assert data.get("auto_fill_applied") in (True, False)
    assert isinstance(data.get("auto_filled_themes"), list)


def test_random_build_api_tertiary_requires_secondary(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {
        "seed": 192837,
        "primary_theme": "Aggro",
        "auto_fill_secondary_enabled": False,
        "auto_fill_tertiary_enabled": True,
    }
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seed"] == 192837
    assert data.get("auto_fill_enabled") is True
    assert data.get("auto_fill_secondary_enabled") is True
    assert data.get("auto_fill_tertiary_enabled") is True
    assert data.get("auto_fill_applied") in (True, False)
    assert isinstance(data.get("auto_filled_themes"), list)


def test_random_build_api_reports_auto_filled_themes(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    import code.web.app as app_module
    import code.deck_builder.random_entrypoint as random_entrypoint
    import deck_builder.random_entrypoint as random_entrypoint_pkg

    def fake_auto_fill(
        df,
        commander,
        rng,
        *,
        primary_theme,
        secondary_theme,
        tertiary_theme,
        allowed_pool,
        fill_secondary,
        fill_tertiary,
    ):
        return "Tokens", "Sacrifice", ["Tokens", "Sacrifice"]

    monkeypatch.setattr(random_entrypoint, "_auto_fill_missing_themes", fake_auto_fill)
    monkeypatch.setattr(random_entrypoint_pkg, "_auto_fill_missing_themes", fake_auto_fill)

    client = TestClient(app_module.app)

    payload = {
        "seed": 654321,
        "primary_theme": "Aggro",
        "auto_fill_enabled": True,
        "auto_fill_secondary_enabled": True,
        "auto_fill_tertiary_enabled": True,
    }
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seed"] == 654321
    assert data.get("auto_fill_enabled") is True
    assert data.get("auto_fill_applied") is True
    assert data.get("auto_fill_secondary_enabled") is True
    assert data.get("auto_fill_tertiary_enabled") is True
    assert data.get("auto_filled_themes") == ["Tokens", "Sacrifice"]
