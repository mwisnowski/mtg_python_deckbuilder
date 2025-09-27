from __future__ import annotations
import importlib
import os
from starlette.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    app_module = importlib.import_module('code.web.app')
    return TestClient(app_module.app)


def test_reroll_diagnostics_match_full_build(monkeypatch):
    client = _client(monkeypatch)
    base = client.post('/api/random_full_build', json={'seed': 321})
    assert base.status_code == 200
    seed = base.json()['seed']
    reroll = client.post('/api/random_reroll', json={'seed': seed})
    assert reroll.status_code == 200
    d_base = base.json().get('diagnostics') or {}
    d_reroll = reroll.json().get('diagnostics') or {}
    # Allow reroll to omit elapsed_ms difference but keys should at least cover attempts/timeouts flags
    for k in ['attempts', 'timeout_hit', 'retries_exhausted']:
        assert k in d_base and k in d_reroll
