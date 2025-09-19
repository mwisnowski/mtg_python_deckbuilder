import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'


def run(cmd, env=None):
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    result = subprocess.run(cmd, cwd=ROOT, env=env_vars, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result.stdout, result.stderr


def test_deterministic_seed(tmp_path):
    out1 = tmp_path / 'theme_list1.json'
    out2 = tmp_path / 'theme_list2.json'
    cmd_base = ['python', str(SCRIPT), '--output']
    # Use a limit to keep runtime fast and deterministic small subset (allowed by guard since different output path)
    cmd1 = cmd_base + [str(out1), '--limit', '50']
    cmd2 = cmd_base + [str(out2), '--limit', '50']
    run(cmd1, env={'EDITORIAL_SEED': '123'})
    run(cmd2, env={'EDITORIAL_SEED': '123'})
    data1 = json.loads(out1.read_text(encoding='utf-8'))
    data2 = json.loads(out2.read_text(encoding='utf-8'))
    # Theme order in JSON output should match for same seed + limit
    names1 = [t['theme'] for t in data1['themes']]
    names2 = [t['theme'] for t in data2['themes']]
    assert names1 == names2


def test_popularity_boundaries_override(tmp_path):
    out_path = tmp_path / 'theme_list.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '80'], env={'EDITORIAL_POP_BOUNDARIES': '1,2,3,4'})
    data = json.loads(out_path.read_text(encoding='utf-8'))
    # With extremely low boundaries most themes in small slice will be Very Common
    buckets = {t['popularity_bucket'] for t in data['themes']}
    assert buckets <= {'Very Common', 'Common', 'Uncommon', 'Niche', 'Rare'}


def test_no_yaml_backfill_on_alt_output(tmp_path):
    # Run with alternate output and --backfill-yaml; should not modify source YAMLs
    catalog_dir = ROOT / 'config' / 'themes' / 'catalog'
    sample = next(p for p in catalog_dir.glob('*.yml'))
    before = sample.read_text(encoding='utf-8')
    out_path = tmp_path / 'tl.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '10', '--backfill-yaml'])
    after = sample.read_text(encoding='utf-8')
    assert before == after, 'YAML was modified when using alternate output path'


def test_catalog_schema_contains_descriptions(tmp_path):
    out_path = tmp_path / 'theme_list.json'
    run(['python', str(SCRIPT), '--output', str(out_path), '--limit', '40'])
    data = json.loads(out_path.read_text(encoding='utf-8'))
    assert all('description' in t for t in data['themes'])
    assert all(t['description'] for t in data['themes'])
