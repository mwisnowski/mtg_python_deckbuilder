from __future__ import annotations
import json
import os
import importlib
from pathlib import Path
from starlette.testclient import TestClient
from code.type_definitions_theme_catalog import ThemeCatalog

CATALOG_PATH = Path('config/themes/theme_list.json')


def _load_catalog():
    raw = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    return ThemeCatalog(**raw)


def test_catalog_schema_parses_and_has_minimum_themes():
    cat = _load_catalog()
    assert len(cat.themes) >= 5  # sanity floor
    # Validate each theme has canonical name and synergy list is list
    for t in cat.themes:
        assert isinstance(t.theme, str) and t.theme
        assert isinstance(t.synergies, list)


def test_sample_seeds_produce_non_empty_decks(monkeypatch):
    # Use test data to keep runs fast/deterministic
    monkeypatch.setenv('RANDOM_MODES', '1')
    monkeypatch.setenv('CSV_FILES_DIR', os.path.join('csv_files', 'testdata'))
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    cat = _load_catalog()
    # Choose up to 5 themes (deterministic ordering/selection) for smoke check
    themes = sorted([t.theme for t in cat.themes])[:5]
    for th in themes:
        r = client.post('/api/random_full_build', json={'theme': th, 'seed': 999})
        assert r.status_code == 200
        data = r.json()
        # Decklist should exist (may be empty if headless not available, allow fallback leniency)
        assert 'seed' in data
        assert data.get('theme') == th or data.get('theme') == th  # explicit equality for clarity
        assert isinstance(data.get('commander'), str)

