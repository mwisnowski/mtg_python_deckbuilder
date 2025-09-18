"""Validate that Phase B merge build also produces a healthy number of per-theme YAML files.

Rationale: We rely on YAML files for editorial workflows even when using merged catalog mode.
This test ensures the orchestrator or build pipeline hasn't regressed by skipping YAML export.

Threshold heuristic: Expect at least 25 YAML files (themes) which is far below the real count
but above zero / trivial to catch regressions.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def _run_merge_build():
    env = os.environ.copy()
    env['THEME_CATALOG_MODE'] = 'merge'
    # Force rebuild without limiting themes so we measure real output
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), '--limit', '0'], capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"build_theme_catalog failed: {result.stderr or result.stdout}"


def test_yaml_export_count_present():
    _run_merge_build()
    assert CATALOG_DIR.exists(), f"catalog dir missing: {CATALOG_DIR}"
    yaml_files = list(CATALOG_DIR.glob('*.yml'))
    assert yaml_files, 'No YAML files generated under catalog/*.yml'
    # Minimum heuristic threshold – adjust upward if stable count known.
    assert len(yaml_files) >= 25, f"Expected >=25 YAML files, found {len(yaml_files)}"
