from __future__ import annotations
import importlib
import os
from starlette.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    app_module = importlib.import_module('code.web.app')
    return TestClient(app_module.app)


def test_same_seed_same_theme_same_constraints_identical(monkeypatch):
    client = _client(monkeypatch)
    body = {'seed': 2025, 'theme': 'Tokens'}
    r1 = client.post('/api/random_full_build', json=body)
    r2 = client.post('/api/random_full_build', json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert d1['commander'] == d2['commander']
    assert d1['decklist'] == d2['decklist']


def test_different_seed_yields_difference(monkeypatch):
    client = _client(monkeypatch)
    b1 = {'seed': 1111}
    b2 = {'seed': 1112}
    r1 = client.post('/api/random_full_build', json=b1)
    r2 = client.post('/api/random_full_build', json=b2)
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    # Commander or at least one decklist difference
    if d1['commander'] == d2['commander']:
        assert d1['decklist'] != d2['decklist'], 'Expected decklist difference for different seeds'
    else:
        assert True
