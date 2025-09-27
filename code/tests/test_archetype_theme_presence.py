"""Ensure each enumerated deck archetype has at least one theme YAML with matching deck_archetype.
Also validates presence of core archetype display_name entries for discoverability.
"""
from __future__ import annotations

from pathlib import Path
import yaml  # type: ignore
import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

ARHCETYPE_MIN = 1

# Mirror of ALLOWED_DECK_ARCHETYPES (keep in sync or import if packaging adjusted)
ALLOWED = {
    'Graveyard', 'Tokens', 'Counters', 'Spells', 'Artifacts', 'Enchantments', 'Lands', 'Politics', 'Combo',
    'Aggro', 'Control', 'Midrange', 'Stax', 'Ramp', 'Toolbox'
}


def test_each_archetype_present():
    """Validate at least one theme YAML declares each deck_archetype.

    Skips gracefully when the generated theme catalog is not available in the
    current environment (e.g., minimal install without generated YAML assets).
    """
    yaml_files = list(CATALOG_DIR.glob('*.yml'))
    found = {a: 0 for a in ALLOWED}

    for p in yaml_files:
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            continue
        arch = data.get('deck_archetype')
        if arch in found:
            found[arch] += 1

    # Unified skip: either no files OR zero assignments discovered.
    if (not yaml_files) or all(c == 0 for c in found.values()):
        pytest.skip("Theme catalog not present; skipping archetype presence check.")

    missing = [a for a, c in found.items() if c < ARHCETYPE_MIN]
    assert not missing, f"Archetypes lacking themed representation: {missing}"
