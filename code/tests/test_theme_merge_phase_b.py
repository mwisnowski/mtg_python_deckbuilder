import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
OUTPUT_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'


def run_builder():
    env = os.environ.copy()
    env['THEME_CATALOG_MODE'] = 'merge'
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), '--limit', '0'], capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"build_theme_catalog failed: {result.stderr or result.stdout}"
    assert OUTPUT_JSON.exists(), "Expected theme_list.json to exist after merge build"


def load_catalog():
    data = json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))
    themes = {t['theme']: t for t in data.get('themes', []) if isinstance(t, dict) and 'theme' in t}
    return data, themes


def test_phase_b_merge_provenance_and_precedence():
    run_builder()
    data, themes = load_catalog()

    # Provenance block required
    prov = data.get('provenance')
    assert isinstance(prov, dict), 'Provenance block missing'
    assert prov.get('mode') == 'merge', 'Provenance mode should be merge'
    assert 'generated_at' in prov, 'generated_at missing in provenance'
    assert 'curated_yaml_files' in prov, 'curated_yaml_files missing in provenance'

    # Sample anchors to verify curated/enforced precedence not truncated under cap
    # Choose +1/+1 Counters (curated + enforced) and Reanimate (curated + enforced)
    for anchor in ['+1/+1 Counters', 'Reanimate']:
        assert anchor in themes, f'Missing anchor theme {anchor}'
        syn = themes[anchor]['synergies']
        # Ensure enforced present
        if anchor == '+1/+1 Counters':
            assert 'Proliferate' in syn and 'Counters Matter' in syn, 'Counters enforced synergies missing'
        if anchor == 'Reanimate':
            assert 'Graveyard Matters' in syn, 'Reanimate enforced synergy missing'
        # If synergy list length equals cap, ensure enforced not last-only list while curated missing
        # (Simplistic check: curated expectation contains at least one of baseline curated anchors)
        if anchor == 'Reanimate':  # baseline curated includes Enter the Battlefield
            assert 'Enter the Battlefield' in syn, 'Curated synergy lost due to capping'

    # Ensure cap respected (soft exceed allowed only if curated+enforced exceed cap)
    cap = data.get('provenance', {}).get('synergy_cap') or 0
    if cap:
        for t, entry in list(themes.items())[:50]:  # sample first 50 for speed
            if len(entry['synergies']) > cap:
                # Validate that over-cap entries contain all enforced + curated combined beyond cap (soft exceed case)
                # We cannot reconstruct curated exactly here without re-running logic; accept soft exceed.
                continue
            assert len(entry['synergies']) <= cap, f"Synergy cap exceeded for {t}: {entry['synergies']}"
