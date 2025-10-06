import json
import os
from pathlib import Path
import subprocess

import pytest

from code.tests.editorial_test_utils import ensure_editorial_fixtures

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

USE_FIXTURES = (
    os.environ.get('EDITORIAL_TEST_USE_FIXTURES', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    or not CATALOG_DIR.exists()
    or not any(CATALOG_DIR.glob('*.yml'))
)

ensure_editorial_fixtures(force=USE_FIXTURES)


def run(cmd, env=None):
    env_vars = os.environ.copy()
    # Ensure code/ is on PYTHONPATH for script relative imports
    existing_pp = env_vars.get('PYTHONPATH', '')
    code_path = str(ROOT / 'code')
    if code_path not in existing_pp.split(os.pathsep):
        env_vars['PYTHONPATH'] = (existing_pp + os.pathsep + code_path) if existing_pp else code_path
    if env:
        env_vars.update(env)
    result = subprocess.run(cmd, cwd=ROOT, env=env_vars, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result.stdout, result.stderr


def test_synergy_pairs_fallback_and_metadata_info(tmp_path):
    """Validate that a theme with empty curated_synergies in YAML picks up fallback from synergy_pairs.yml
    and that backfill stamps metadata_info (formerly provenance) + popularity/description when forced.
    """
    # Pick a catalog file we can safely mutate (copy to temp and operate on copy via output override, then force backfill real one)
    # We'll choose a theme that likely has few curated synergies to increase chance fallback applies; if not found, just assert mapping works generically.
    out_path = tmp_path / 'theme_list.json'
    # Limit to keep runtime fast but ensure target theme appears
    run(['python', str(SCRIPT), '--output', str(out_path)], env={'EDITORIAL_SEED': '42'})
    data = json.loads(out_path.read_text(encoding='utf-8'))
    themes = {t['theme']: t for t in data['themes']}
    # Pick one known from synergy_pairs.yml (e.g., 'Treasure', 'Tokens', 'Proliferate')
    candidate = None
    search_pool = (
        'Treasure','Tokens','Proliferate','Aristocrats','Sacrifice','Landfall','Graveyard','Reanimate'
    )
    for name in search_pool:
        if name in themes:
            candidate = name
            break
    if not candidate:  # If still none, skip test rather than fail (environmental variability)
        pytest.skip('No synergy pair seed theme present in catalog output')
    candidate_entry = themes[candidate]
    # Must have at least one synergy (fallback or curated)
    assert candidate_entry.get('synergies'), f"{candidate} has no synergies; fallback failed"
    # Force backfill (real JSON path triggers backfill) with environment to ensure provenance stamping
    run(['python', str(SCRIPT), '--force-backfill-yaml', '--backfill-yaml'], env={'EDITORIAL_INCLUDE_FALLBACK_SUMMARY': '1'})
    # Locate YAML and verify metadata_info (or legacy provenance) inserted
    yaml_path = CATALOG_DIR / f"{candidate.lower().replace(' ', '-')}.yml"
    if not yaml_path.exists():
        pytest.skip('Catalog YAML directory missing expected theme; fixture was not staged.')
    raw = yaml_path.read_text(encoding='utf-8').splitlines()
    has_meta = any(line.strip().startswith(('metadata_info:','provenance:')) for line in raw)
    assert has_meta, 'metadata_info block missing after forced backfill'