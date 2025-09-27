"""Enforcement Test: Minimum example_commanders threshold.

This test asserts that when enforcement flag is active (env EDITORIAL_MIN_EXAMPLES_ENFORCE=1)
no theme present in the merged catalog falls below the configured minimum (default 5).

Rationale: Guards against regressions where a future edit drops curated coverage
below the policy threshold after Phase D close-out.
"""
from __future__ import annotations

import os
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'config' / 'themes' / 'theme_list.json'


def test_all_themes_meet_minimum_examples():
    os.environ['EDITORIAL_MIN_EXAMPLES_ENFORCE'] = '1'
    min_required = int(os.environ.get('EDITORIAL_MIN_EXAMPLES', '5'))
    assert CATALOG.exists(), 'theme_list.json missing (run build script before tests)'
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
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
