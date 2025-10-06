"""Enforcement Test: Minimum example_commanders threshold.

This test asserts that when enforcement flag is active (env EDITORIAL_MIN_EXAMPLES_ENFORCE=1)
no theme present in the merged catalog falls below the configured minimum (default 5).

Rationale: Guards against regressions where a future edit drops curated coverage
below the policy threshold after Phase D close-out.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import pytest

from code.tests.editorial_test_utils import ensure_editorial_fixtures

ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = ROOT / 'config' / 'themes'
CATALOG_DIR = THEMES_DIR / 'catalog'
CATALOG = THEMES_DIR / 'theme_list.json'
FIXTURE_THEME_LIST = Path(__file__).resolve().parent / 'fixtures' / 'editorial_catalog' / 'theme_list.json'

USE_FIXTURES = (
    os.environ.get('EDITORIAL_TEST_USE_FIXTURES', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    or not CATALOG_DIR.exists()
    or not any(CATALOG_DIR.glob('*.yml'))
)

ensure_editorial_fixtures(force=USE_FIXTURES)


def test_all_themes_meet_minimum_examples():
    os.environ['EDITORIAL_MIN_EXAMPLES_ENFORCE'] = '1'
    min_required = int(os.environ.get('EDITORIAL_MIN_EXAMPLES', '5'))
    source = FIXTURE_THEME_LIST if USE_FIXTURES else CATALOG
    if not source.exists():
        pytest.skip('theme list unavailable; editorial fixtures not staged.')
    data = json.loads(source.read_text(encoding='utf-8'))
    assert 'themes' in data
    short = []
    for entry in data['themes']:
        # Skip synthetic / alias entries if any (identified by metadata_info.alias_of later if introduced)
        if entry.get('alias_of'):
            continue
        examples = entry.get('example_commanders') or []
        if len(examples) < min_required:
            short.append(f"{entry.get('theme')}: {len(examples)} < {min_required}")
    assert not short, 'Themes below minimum examples: ' + ', '.join(short)
