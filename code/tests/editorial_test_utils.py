from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / 'config' / 'themes'
CATALOG_DIR = THEMES_DIR / 'catalog'
FIXTURE_ROOT = Path(__file__).resolve().parent / 'fixtures' / 'editorial_catalog'


def ensure_editorial_fixtures(force: bool | None = None) -> None:
    """Populate minimal editorial catalog fixtures when real data is absent.

    The repository intentionally does not track `config/themes/catalog` because the
    production catalog is generated dynamically. For CI we stage a small curated
    sample so governance tests can exercise logic without requiring the full data
    dump. Existing files are left untouched to avoid clobbering local updates.
    """
    if force is None:
        flag = os.environ.get('EDITORIAL_TEST_USE_FIXTURES', '').strip().lower()
        force = flag in {'1', 'true', 'yes', 'on'}

    if not FIXTURE_ROOT.exists():
        return

    catalog_fixture = FIXTURE_ROOT / 'catalog'
    if catalog_fixture.exists():
        CATALOG_DIR.mkdir(parents=True, exist_ok=True)
        for src in catalog_fixture.glob('*.yml'):
            dest = CATALOG_DIR / src.name
            if force or not dest.exists():
                shutil.copy(src, dest)

    theme_list_fixture = FIXTURE_ROOT / 'theme_list.json'
    theme_list_target = THEMES_DIR / 'theme_list.json'
    if theme_list_fixture.exists() and (force or not theme_list_target.exists()):
        theme_list_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(theme_list_fixture, theme_list_target)
