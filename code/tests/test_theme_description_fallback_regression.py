import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
OUTPUT = ROOT / 'config' / 'themes' / 'theme_list_test_regression.json'


def test_generic_description_regression():
    # Run build with summary enabled directed to temp output
    env = os.environ.copy()
    env['EDITORIAL_INCLUDE_FALLBACK_SUMMARY'] = '1'
    # Avoid writing real catalog file; just produce alternate output
    import subprocess
    import sys
    cmd = [sys.executable, str(SCRIPT), '--output', str(OUTPUT)]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    data = json.loads(OUTPUT.read_text(encoding='utf-8'))
    summary = data.get('description_fallback_summary') or {}
    # Guardrails tightened (second wave). Prior baseline: ~357 generic (309 + 48).
    # New ceiling: <= 365 total generic and <52% share. Future passes should lower further.
    assert summary.get('generic_total', 0) <= 365, summary
    assert summary.get('generic_pct', 100.0) < 52.0, summary
    # Basic shape checks
    assert 'top_generic_by_frequency' in summary
    assert isinstance(summary['top_generic_by_frequency'], list)
    # Clean up temp output file
    try:
        OUTPUT.unlink()
    except Exception:
        pass
