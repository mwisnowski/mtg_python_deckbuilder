from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


def test_random_full_build_api_returns_deck_and_permalink(monkeypatch):
    # Enable Random Modes and use tiny dataset
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
    # Permalink present and shaped like /build/from?state=...
    assert data.get("permalink")
    assert "/build/from?state=" in data["permalink"]
