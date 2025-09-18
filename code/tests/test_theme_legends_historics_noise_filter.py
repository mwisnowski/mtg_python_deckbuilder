"""Tests for suppression of noisy Legends/Historics synergies.

Phase B build should remove Legends Matter / Historics Matter from every theme's synergy
list except:
 - Legends Matter may list Historics Matter
 - Historics Matter may list Legends Matter
No other theme should include either.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
OUTPUT_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'


def _build_catalog():
    # Build with no limit
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), '--limit', '0'], capture_output=True, text=True)
    assert result.returncode == 0, f"build_theme_catalog failed: {result.stderr or result.stdout}"
    assert OUTPUT_JSON.exists(), 'theme_list.json not emitted'
    return json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))


def test_legends_historics_noise_filtered():
    data = _build_catalog()
    legends_entry = None
    historics_entry = None
    for t in data['themes']:
        if t['theme'] == 'Legends Matter':
            legends_entry = t
        elif t['theme'] == 'Historics Matter':
            historics_entry = t
        else:
            assert 'Legends Matter' not in t['synergies'], f"Noise synergy 'Legends Matter' leaked into {t['theme']}"  # noqa: E501
            assert 'Historics Matter' not in t['synergies'], f"Noise synergy 'Historics Matter' leaked into {t['theme']}"  # noqa: E501
    # Mutual allowance
    if legends_entry:
        assert 'Historics Matter' in legends_entry['synergies'], 'Legends Matter should keep Historics Matter'
    if historics_entry:
        assert 'Legends Matter' in historics_entry['synergies'], 'Historics Matter should keep Legends Matter'
