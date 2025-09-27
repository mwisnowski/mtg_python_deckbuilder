from __future__ import annotations
import importlib
import os
from starlette.testclient import TestClient

def _client(monkeypatch):
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    app_module = importlib.import_module('code.web.app')
    return TestClient(app_module.app)


def test_theme_rejects_disallowed_chars(monkeypatch):
    client = _client(monkeypatch)
    bad = {"seed": 10, "theme": "Bad;DROP TABLE"}
    r = client.post('/api/random_full_build', json=bad)
    assert r.status_code == 200
    data = r.json()
    # Theme should be None or absent because it was rejected
    assert data.get('theme') in (None, '')


def test_theme_rejects_long(monkeypatch):
    client = _client(monkeypatch)
    long_theme = 'X'*200
    r = client.post('/api/random_full_build', json={"seed": 11, "theme": long_theme})
    assert r.status_code == 200
    assert r.json().get('theme') in (None, '')


def test_theme_accepts_normal(monkeypatch):
    client = _client(monkeypatch)
    r = client.post('/api/random_full_build', json={"seed": 12, "theme": "Tokens"})
    assert r.status_code == 200
    assert r.json().get('theme') == 'Tokens'
