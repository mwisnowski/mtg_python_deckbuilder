import subprocess
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
VALIDATE = ROOT / 'code' / 'scripts' / 'validate_description_mapping.py'
TEMP_OUT = ROOT / 'config' / 'themes' / 'theme_list_mapping_test.json'


def test_description_mapping_validator_runs():
    res = subprocess.run([sys.executable, str(VALIDATE)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr or res.stdout
    assert 'Mapping OK' in (res.stdout + res.stderr)


def test_mapping_applies_to_catalog():
    env = os.environ.copy()
    env['EDITORIAL_INCLUDE_FALLBACK_SUMMARY'] = '1'
    # Build catalog to alternate path
    res = subprocess.run([sys.executable, str(SCRIPT), '--output', str(TEMP_OUT)], capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    data = json.loads(TEMP_OUT.read_text(encoding='utf-8'))
    themes = data.get('themes', [])
    assert themes, 'No themes generated'
    # Pick a theme that should clearly match a mapping rule (e.g., contains "Treasure")
    mapped = [t for t in themes if 'Treasure' in t.get('theme','')]
    if mapped:
        desc = mapped[0].get('description','')
        assert 'Treasure tokens' in desc or 'Treasure token' in desc
    # Clean up
    try:
        TEMP_OUT.unlink()
    except Exception:
        pass
