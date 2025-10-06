"""Phase D Close-Out Governance Tests

These tests enforce remaining non-UI editorial guarantees before Phase E.

Coverage:
 - Deterministic build under EDITORIAL_SEED (structure equality ignoring metadata_info timestamps)
 - KPI history JSONL integrity (monotonic timestamps, schema fields, ratio consistency)
 - metadata_info block coverage across YAML catalog (>=95%)
 - synergy_commanders do not duplicate (base) example_commanders
 - Mapping trigger specialization guard: any theme name matching a description mapping trigger
   must NOT retain a generic fallback description ("Builds around ..."). Tribal phrasing beginning
   with "Focuses on getting" is allowed.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set

import pytest

from code.tests.editorial_test_utils import ensure_editorial_fixtures


ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = ROOT / 'config' / 'themes'
CATALOG_JSON = THEMES_DIR / 'theme_list.json'
CATALOG_DIR = THEMES_DIR / 'catalog'
HISTORY = THEMES_DIR / 'description_fallback_history.jsonl'
MAPPING = THEMES_DIR / 'description_mapping.yml'

USE_FIXTURES = (
    os.environ.get('EDITORIAL_TEST_USE_FIXTURES', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    or not CATALOG_DIR.exists()
    or not any(CATALOG_DIR.glob('*.yml'))
)

ensure_editorial_fixtures(force=USE_FIXTURES)


def _load_catalog() -> Dict[str, Any]:
    data = json.loads(CATALOG_JSON.read_text(encoding='utf-8'))
    assert 'themes' in data and isinstance(data['themes'], list)
    return data


def test_deterministic_build_under_seed():
    # Import build after setting seed env
    os.environ['EDITORIAL_SEED'] = '999'
    from scripts.build_theme_catalog import build_catalog  # type: ignore
    first = build_catalog(limit=0, verbose=False)
    second = build_catalog(limit=0, verbose=False)
    # Drop volatile metadata_info/timestamp fields before comparison
    for d in (first, second):
        d.pop('metadata_info', None)
        d.pop('yaml_catalog', None)
    assert first == second, "Catalog build not deterministic under identical EDITORIAL_SEED"


def test_kpi_history_integrity():
    assert HISTORY.exists(), "KPI history file missing"
    lines = [line.strip() for line in HISTORY.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert lines, "KPI history empty"
    prev_ts: datetime | None = None
    for ln in lines:
        rec = json.loads(ln)
        for field in ['timestamp', 'total_themes', 'generic_total', 'generic_with_synergies', 'generic_plain', 'generic_pct']:
            assert field in rec, f"History record missing field {field}"
        # Timestamp parse & monotonic (allow equal for rapid successive builds)
        ts = datetime.fromisoformat(rec['timestamp'])
        if prev_ts:
            assert ts >= prev_ts, "History timestamps not monotonic non-decreasing"
        prev_ts = ts
        total = max(1, int(rec['total_themes']))
        recomputed_pct = 100.0 * int(rec['generic_total']) / total
        # Allow small rounding drift
        assert abs(recomputed_pct - float(rec['generic_pct'])) <= 0.2, "generic_pct inconsistent with totals"


def test_metadata_info_block_coverage():
    import yaml  # type: ignore
    if not CATALOG_DIR.exists() or not any(CATALOG_DIR.glob('*.yml')):
        pytest.skip('Catalog YAML directory missing; editorial fixtures not staged.')
    total = 0
    with_prov = 0
    for p in CATALOG_DIR.glob('*.yml'):
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            continue
        # Skip deprecated alias placeholders
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        if not data.get('display_name'):
            continue
        total += 1
        meta = data.get('metadata_info') or data.get('provenance')
        if isinstance(meta, dict) and meta.get('last_backfill') and meta.get('script'):
            with_prov += 1
    assert total > 0, "No YAML files discovered for provenance check"
    coverage = with_prov / total
    assert coverage >= 0.95, f"metadata_info coverage below threshold: {coverage:.2%} (wanted >=95%)"


def test_synergy_commanders_exclusion_of_examples():
    import yaml  # type: ignore
    pattern = re.compile(r" - Synergy \(.*\)$")
    violations: List[str] = []
    for p in CATALOG_DIR.glob('*.yml'):
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not data.get('display_name'):
            continue
        ex_cmd = data.get('example_commanders') or []
        sy_cmd = data.get('synergy_commanders') or []
        if not (isinstance(ex_cmd, list) and isinstance(sy_cmd, list)):
            continue
        base_examples = {pattern.sub('', e) for e in ex_cmd if isinstance(e, str)}
        for s in sy_cmd:
            if not isinstance(s, str):
                continue
            base = pattern.sub('', s)
            if base in base_examples:
                violations.append(f"{data.get('display_name')}: '{s}' duplicates example '{base}'")
    assert not violations, 'synergy_commanders contain duplicates of example_commanders: ' + '; '.join(violations)


def test_mapping_trigger_specialization_guard():
    import yaml  # type: ignore
    assert MAPPING.exists(), "description_mapping.yml missing"
    mapping_yaml = yaml.safe_load(MAPPING.read_text(encoding='utf-8')) or []
    triggers: Set[str] = set()
    for item in mapping_yaml:
        if isinstance(item, dict) and 'triggers' in item and isinstance(item['triggers'], list):
            for t in item['triggers']:
                if isinstance(t, str) and t.strip():
                    triggers.add(t.lower())
    catalog = _load_catalog()
    generic_themes: List[str] = []
    for entry in catalog['themes']:
        theme = str(entry.get('theme') or '')
        desc = str(entry.get('description') or '')
        lower = theme.lower()
        if not theme or not desc:
            continue
        # Generic detection: Starts with 'Builds around' (tribal phrasing allowed as non-generic)
        if not desc.startswith('Builds around'):
            continue
        if any(trig in lower for trig in triggers):
            generic_themes.append(theme)
    assert not generic_themes, (
        'Themes matched by description mapping triggers still have generic fallback descriptions: ' + ', '.join(sorted(generic_themes))
    )
