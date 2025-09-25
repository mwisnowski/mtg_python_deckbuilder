from __future__ import annotations
import os
from fastapi.testclient import TestClient

def test_metrics_and_seed_history(monkeypatch):
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('RANDOM_UI', '1')
    monkeypatch.setenv('RANDOM_TELEMETRY', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    from code.web.app import app
    client = TestClient(app)

    # Build + reroll to generate metrics and seed history
    r1 = client.post('/api/random_full_build', json={'seed': 9090})
    assert r1.status_code == 200, r1.text
    r2 = client.post('/api/random_reroll', json={'seed': 9090})
    assert r2.status_code == 200, r2.text

    # Metrics
    m = client.get('/status/random_metrics')
    assert m.status_code == 200, m.text
    mj = m.json()
    assert mj.get('ok') is True
    metrics = mj.get('metrics') or {}
    assert 'full_build' in metrics and 'reroll' in metrics

    # Seed history
    sh = client.get('/api/random/seeds')
    assert sh.status_code == 200
    sj = sh.json()
    seeds = sj.get('seeds') or []
    assert any(s == 9090 for s in seeds) and sj.get('last') in seeds
