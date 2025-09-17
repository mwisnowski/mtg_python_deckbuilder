from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


def test_random_build_api_commander_and_seed(monkeypatch):
    # Enable Random Modes and use tiny dataset
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    payload = {"seed": 12345, "theme": "Goblin Kindred"}
    r = client.post('/api/random_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["seed"] == 12345
    assert isinstance(data.get("commander"), str)
    assert data.get("commander")
