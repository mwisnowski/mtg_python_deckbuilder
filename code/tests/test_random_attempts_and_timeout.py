from __future__ import annotations

import importlib
import os
from starlette.testclient import TestClient


def _mk_client(monkeypatch):
    # Enable Random Modes and point to test CSVs
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    # Keep defaults small for speed
    monkeypatch.setenv("RANDOM_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("RANDOM_TIMEOUT_MS", "200")
    # Re-import app to pick up env
    app_module = importlib.import_module('code.web.app')
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_retries_exhausted_flag_propagates(monkeypatch):
    client = _mk_client(monkeypatch)
    # Force rejection of every candidate to simulate retries exhaustion
    payload = {"seed": 1234, "constraints": {"reject_all": True}, "attempts": 2, "timeout_ms": 200}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    diag = data.get("diagnostics") or {}
    assert diag.get("attempts") >= 1
    assert diag.get("retries_exhausted") is True
    assert diag.get("timeout_hit") in {True, False}


def test_timeout_hit_flag_propagates(monkeypatch):
    client = _mk_client(monkeypatch)
    # Force the time source in random_entrypoint to advance rapidly so the loop times out immediately
    re = importlib.import_module('deck_builder.random_entrypoint')
    class _FakeClock:
        def __init__(self):
            self.t = 0.0
        def time(self):
            # Advance time by 0.2s every call
            self.t += 0.2
            return self.t
    fake = _FakeClock()
    monkeypatch.setattr(re, 'time', fake, raising=True)
    # Use small timeout and large attempts; timeout path should be taken deterministically
    payload = {"seed": 4321, "attempts": 1000, "timeout_ms": 100}
    r = client.post('/api/random_full_build', json=payload)
    assert r.status_code == 200
    data = r.json()
    diag = data.get("diagnostics") or {}
    assert diag.get("attempts") >= 1
    assert diag.get("timeout_hit") is True


def test_hx_fragment_includes_diagnostics_when_enabled(monkeypatch):
    client = _mk_client(monkeypatch)
    # Enable diagnostics in templates
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    app_module = importlib.import_module('code.web.app')
    importlib.reload(app_module)
    client = TestClient(app_module.app)

    headers = {
        "HX-Request": "true",
        "Content-Type": "application/json",
        "Accept": "text/html, */*; q=0.1",
    }
    r = client.post("/hx/random_reroll", data='{"seed": 10, "constraints": {"reject_all": true}, "attempts": 2, "timeout_ms": 200}', headers=headers)
    assert r.status_code == 200
    html = r.text
    # Should include attempts and at least one of the diagnostics flags text when enabled
    assert "attempts=" in html
    assert ("Retries exhausted" in html) or ("Timeout hit" in html)
