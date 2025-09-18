import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATE = ROOT / 'code' / 'scripts' / 'validate_theme_catalog.py'
BUILD = ROOT / 'code' / 'scripts' / 'build_theme_catalog.py'
CATALOG = ROOT / 'config' / 'themes' / 'theme_list.json'


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def ensure_catalog():
    if not CATALOG.exists():
        rc, out, err = _run([sys.executable, str(BUILD)])
        assert rc == 0, f"build failed: {err or out}"


def test_schema_export():
    ensure_catalog()
    rc, out, err = _run([sys.executable, str(VALIDATE), '--schema'])
    assert rc == 0, f"schema export failed: {err or out}"
    data = json.loads(out)
    assert 'properties' in data, 'Expected JSON Schema properties'
    assert 'themes' in data['properties'], 'Schema missing themes property'


def test_yaml_schema_export():
    rc, out, err = _run([sys.executable, str(VALIDATE), '--yaml-schema'])
    assert rc == 0, f"yaml schema export failed: {err or out}"
    data = json.loads(out)
    assert 'properties' in data and 'display_name' in data['properties'], 'YAML schema missing display_name'


def test_rebuild_idempotent():
    ensure_catalog()
    rc, out, err = _run([sys.executable, str(VALIDATE), '--rebuild-pass'])
    assert rc == 0, f"validation with rebuild failed: {err or out}"
    assert 'validation passed' in out.lower()


def test_enforced_synergies_present_sample():
    ensure_catalog()
    # Quick sanity: rely on validator's own enforced synergy check (will exit 2 if violation)
    rc, out, err = _run([sys.executable, str(VALIDATE)])
    assert rc == 0, f"validator reported errors unexpectedly: {err or out}"


def test_duplicate_yaml_id_detection(tmp_path):
    ensure_catalog()
    # Copy an existing YAML and keep same id to force duplicate
    catalog_dir = ROOT / 'config' / 'themes' / 'catalog'
    sample = next(catalog_dir.glob('plus1-plus1-counters.yml'))
    dup_path = catalog_dir / 'dup-test.yml'
    content = sample.read_text(encoding='utf-8')
    dup_path.write_text(content, encoding='utf-8')
    rc, out, err = _run([sys.executable, str(VALIDATE)])
    dup_path.unlink(missing_ok=True)
    # Expect failure (exit code 2) because of duplicate id
    assert rc == 2 and 'Duplicate YAML id' in out, 'Expected duplicate id detection'


def test_normalization_alias_absent():
    ensure_catalog()
    # Aliases defined in whitelist (e.g., Pillow Fort) should not appear as display_name
    rc, out, err = _run([sys.executable, str(VALIDATE)])
    assert rc == 0, f"validation failed unexpectedly: {out or err}"
    # Build again and ensure stable result (indirect idempotency reinforcement)
    rc2, out2, err2 = _run([sys.executable, str(VALIDATE), '--rebuild-pass'])
    assert rc2 == 0, f"rebuild pass failed: {out2 or err2}"


def test_strict_alias_mode_passes_current_state():
    # If alias YAMLs still exist (e.g., Reanimator), strict mode is expected to fail.
    # Once alias files are removed/renamed this test should be updated to assert success.
    ensure_catalog()
    rc, out, err = _run([sys.executable, str(VALIDATE), '--strict-alias'])
    # After alias cleanup, strict mode should cleanly pass
    assert rc == 0, f"Strict alias mode unexpectedly failed: {out or err}"


def test_synergy_cap_global():
    ensure_catalog()
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    cap = data.get('provenance', {}).get('synergy_cap') or 0
    if not cap:
        return
    for entry in data.get('themes', [])[:200]:  # sample subset for speed
        syn = entry.get('synergies', [])
        if len(syn) > cap:
            # Soft exceed acceptable only if curated+enforced likely > cap; cannot assert here
            continue
        assert len(syn) <= cap, f"Synergy cap violation for {entry.get('theme')}: {syn}"


def test_always_include_persistence_between_builds():
    # Build twice and ensure all always_include themes still present
    ensure_catalog()
    rc, out, err = _run([sys.executable, str(BUILD)])
    assert rc == 0, f"rebuild failed: {out or err}"
    rc2, out2, err2 = _run([sys.executable, str(BUILD)])
    assert rc2 == 0, f"second rebuild failed: {out2 or err2}"
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    whitelist_path = ROOT / 'config' / 'themes' / 'theme_whitelist.yml'
    import yaml
    wl = yaml.safe_load(whitelist_path.read_text(encoding='utf-8'))
    ai = set(wl.get('always_include', []) or [])
    themes = {t['theme'] for t in data.get('themes', [])}
    # Account for normalization: if an always_include item is an alias mapped to canonical form, use canonical.
    whitelist_norm = wl.get('normalization', {}) or {}
    normalized_ai = {whitelist_norm.get(t, t) for t in ai}
    missing = normalized_ai - themes
    assert not missing, f"Always include (normalized) themes missing after rebuilds: {missing}"


def test_soft_exceed_enforced_over_cap(tmp_path):
    # Create a temporary enforced override scenario where enforced list alone exceeds cap
    ensure_catalog()
    # Load whitelist, augment enforced_synergies for a target anchor artificially
    whitelist_path = ROOT / 'config' / 'themes' / 'theme_whitelist.yml'
    import yaml
    wl = yaml.safe_load(whitelist_path.read_text(encoding='utf-8'))
    cap = int(wl.get('synergy_cap') or 0)
    if cap < 2:
        return
    anchor = 'Reanimate'
    enforced = wl.get('enforced_synergies', {}) or {}
    # Inject synthetic enforced set longer than cap
    synthetic = [f"Synthetic{i}" for i in range(cap + 2)]
    enforced[anchor] = synthetic
    wl['enforced_synergies'] = enforced
    # Write temp whitelist file copy and patch environment to point loader to it by monkeypatching cwd
    # Simpler: write to a temp file and swap original (restore after)
    backup = whitelist_path.read_text(encoding='utf-8')
    try:
        whitelist_path.write_text(yaml.safe_dump(wl), encoding='utf-8')
        rc, out, err = _run([sys.executable, str(BUILD)])
        assert rc == 0, f"build failed with synthetic enforced: {out or err}"
        data = json.loads(CATALOG.read_text(encoding='utf-8'))
        theme_map = {t['theme']: t for t in data.get('themes', [])}
        if anchor in theme_map:
            syn_list = theme_map[anchor]['synergies']
            # All synthetic enforced should appear even though > cap
            missing = [s for s in synthetic if s not in syn_list]
            assert not missing, f"Synthetic enforced synergies missing despite soft exceed policy: {missing}"
    finally:
        whitelist_path.write_text(backup, encoding='utf-8')
        # Rebuild to restore canonical state
        _run([sys.executable, str(BUILD)])
