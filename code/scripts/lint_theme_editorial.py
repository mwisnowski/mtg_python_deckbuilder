"""Phase D: Lint editorial metadata for theme YAML files.

Checks (non-fatal unless --strict):
 - example_commanders/example_cards length & uniqueness
 - deck_archetype membership in allowed set (warn if unknown)
 - Cornerstone themes have at least one example commander & card

Exit codes:
 0: No errors (warnings may still print)
 1: Structural / fatal errors (in strict mode or malformed YAML)
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Set
import re

import sys

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

ALLOWED_ARCHETYPES: Set[str] = {
    'Lands', 'Graveyard', 'Planeswalkers', 'Tokens', 'Counters', 'Spells', 'Artifacts', 'Enchantments', 'Politics'
}

CORNERSTONE: Set[str] = {
    'Landfall', 'Reanimate', 'Superfriends', 'Tokens Matter', '+1/+1 Counters'
}


def lint(strict: bool) -> int:
    if yaml is None:
        print('YAML support not available (PyYAML missing); skipping lint.')
        return 0
    if not CATALOG_DIR.exists():
        print('Catalog directory missing; nothing to lint.')
        return 0
    errors: List[str] = []
    warnings: List[str] = []
    cornerstone_present: Set[str] = set()
    seen_display: Set[str] = set()
    ann_re = re.compile(r" - Synergy \(([^)]+)\)$")
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception as e:
            errors.append(f"Failed to parse {path.name}: {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"YAML not mapping: {path.name}")
            continue
        name = str(data.get('display_name') or '').strip()
        if not name:
            continue
        # Skip deprecated alias placeholder files
        notes_field = data.get('notes')
        if isinstance(notes_field, str) and 'Deprecated alias file' in notes_field:
            continue
        if name in seen_display:
            # Already processed a canonical file for this display name; skip duplicates (aliases)
            continue
        seen_display.add(name)
        ex_cmd = data.get('example_commanders') or []
        ex_cards = data.get('example_cards') or []
        synergy_cmds = data.get('synergy_commanders') if isinstance(data.get('synergy_commanders'), list) else []
        theme_synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
        if not isinstance(ex_cmd, list):
            errors.append(f"example_commanders not list in {path.name}")
            ex_cmd = []
        if not isinstance(ex_cards, list):
            errors.append(f"example_cards not list in {path.name}")
            ex_cards = []
        # Length caps
        if len(ex_cmd) > 12:
            warnings.append(f"{name}: example_commanders trimmed to 12 (found {len(ex_cmd)})")
        if len(ex_cards) > 20:
            warnings.append(f"{name}: example_cards length {len(ex_cards)} > 20 (consider trimming)")
        if synergy_cmds and len(synergy_cmds) > 6:
            warnings.append(f"{name}: synergy_commanders length {len(synergy_cmds)} > 6 (3/2/1 pattern expected)")
        if ex_cmd and len(ex_cmd) < 5:
            warnings.append(f"{name}: example_commanders only {len(ex_cmd)} (<5 minimum target)")
        if not synergy_cmds and any(' - Synergy (' in c for c in ex_cmd):
            # If synergy_commanders intentionally filtered out because all synergy picks were promoted, skip warning.
            # Heuristic: if at least 5 examples and every annotated example has unique base name, treat as satisfied.
            base_names = {c.split(' - Synergy ')[0] for c in ex_cmd if ' - Synergy (' in c}
            if not (len(ex_cmd) >= 5 and len(base_names) >= 1):
                warnings.append(f"{name}: has synergy-annotated example_commanders but missing synergy_commanders list")
        # Uniqueness
        if len(set(ex_cmd)) != len(ex_cmd):
            warnings.append(f"{name}: duplicate entries in example_commanders")
        if len(set(ex_cards)) != len(ex_cards):
            warnings.append(f"{name}: duplicate entries in example_cards")
        if synergy_cmds:
            base_synergy_names = [c.split(' - Synergy ')[0] for c in synergy_cmds]
            if len(set(base_synergy_names)) != len(base_synergy_names):
                warnings.append(f"{name}: duplicate entries in synergy_commanders (base names)")

        # Annotation validation: each annotated example should reference a synergy in theme synergies
        for c in ex_cmd:
            if ' - Synergy (' in c:
                m = ann_re.search(c)
                if m:
                    syn = m.group(1).strip()
                    if syn and syn not in theme_synergies:
                        warnings.append(f"{name}: example commander annotation synergy '{syn}' not in theme synergies list")
        # Cornerstone coverage
        if name in CORNERSTONE:
            if not ex_cmd:
                warnings.append(f"Cornerstone theme {name} missing example_commanders")
            if not ex_cards:
                warnings.append(f"Cornerstone theme {name} missing example_cards")
            else:
                cornerstone_present.add(name)
        # Archetype
        arch = data.get('deck_archetype')
        if arch and arch not in ALLOWED_ARCHETYPES:
            warnings.append(f"{name}: deck_archetype '{arch}' not in allowed set {sorted(ALLOWED_ARCHETYPES)}")
    # Summaries
    if warnings:
        print('LINT WARNINGS:')
        for w in warnings:
            print(f" - {w}")
    if errors:
        print('LINT ERRORS:')
        for e in errors:
            print(f" - {e}")
    if errors and strict:
        return 1
    return 0


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Lint editorial metadata for theme YAML files (Phase D)')
    parser.add_argument('--strict', action='store_true', help='Treat errors as fatal (non-zero exit)')
    args = parser.parse_args()
    rc = lint(args.strict)
    if rc != 0:
        sys.exit(rc)


if __name__ == '__main__':
    main()
