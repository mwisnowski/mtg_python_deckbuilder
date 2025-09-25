from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


def _mk_client(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    app_module = importlib.import_module('code.web.app')
    return TestClient(app_module.app)


def test_invalid_theme_triggers_fallback_and_echoes_original_theme(monkeypatch):
    client = _mk_client(monkeypatch)
    payload = {"seed": 777, "theme": "this theme does not exist"}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    # Fallback flag should be set with original_theme echoed
    assert data.get("fallback") is True
    assert data.get("original_theme") == payload["theme"]
    # Theme is still the provided theme (we indicate fallback via the flag)
    assert data.get("theme") == payload["theme"]
    # Commander/decklist should be present
    assert isinstance(data.get("commander"), str) and data["commander"]
    assert isinstance(data.get("decklist"), list)


def test_constraints_impossible_returns_422_with_detail(monkeypatch):
    client = _mk_client(monkeypatch)
    # Set an unrealistically high requirement to force impossible constraint
    payload = {"seed": 101, "constraints": {"require_min_candidates": 1000000}}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 422
    data = r.json()
    # Structured error payload
    assert data.get("status") == 422
    detail = data.get("detail")
    assert isinstance(detail, dict)
    assert detail.get("error") == "constraints_impossible"
    assert isinstance(detail.get("pool_size"), int)
