"""Validate external description mapping file for auto-description system.

Checks:
  - YAML parses
  - Each item has triggers (list[str]) and description (str)
  - No duplicate trigger substrings across entries (first wins; duplicates may cause confusion)
  - Optional mapping_version entry allowed (dict with key mapping_version)
  - Warn if {SYNERGIES} placeholder unused in entries where synergy phrase seems beneficial (heuristic: contains tokens/ counters / treasure / artifact / spell / graveyard / landfall)
Exit code 0 on success, >0 on validation failure.
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import List, Dict

try:
    import yaml  # type: ignore
except Exception:
    print("PyYAML not installed; cannot validate mapping.", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = ROOT / 'config' / 'themes' / 'description_mapping.yml'
PAIRS_PATH = ROOT / 'config' / 'themes' / 'synergy_pairs.yml'
CLUSTERS_PATH = ROOT / 'config' / 'themes' / 'theme_clusters.yml'
CATALOG_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'

SYNERGY_HINT_WORDS = [
    'token', 'treasure', 'clue', 'food', 'blood', 'map', 'incubat', 'powerstone',
    'counter', 'proliferate', '+1/+1', '-1/-1', 'grave', 'reanimate', 'spell', 'landfall',
    'artifact', 'enchant', 'equipment', 'sacrifice'
]

def _load_theme_names():
    if not CATALOG_JSON.exists():
        return set()
    import json
    try:
        data = json.loads(CATALOG_JSON.read_text(encoding='utf-8'))
        return {t.get('theme') for t in data.get('themes', []) if isinstance(t, dict) and t.get('theme')}
    except Exception:
        return set()


def main() -> int:
    if not MAPPING_PATH.exists():
        print(f"Mapping file missing: {MAPPING_PATH}", file=sys.stderr)
        return 1
    raw = yaml.safe_load(MAPPING_PATH.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        print("Top-level YAML structure must be a list (items + optional mapping_version dict).", file=sys.stderr)
        return 1
    seen_triggers: Dict[str, str] = {}
    errors: List[str] = []
    warnings: List[str] = []
    for idx, item in enumerate(raw):
        if isinstance(item, dict) and 'mapping_version' in item:
            continue
        if not isinstance(item, dict):
            errors.append(f"Item {idx} not a dict")
            continue
        triggers = item.get('triggers')
        desc = item.get('description')
        if not isinstance(triggers, list) or not all(isinstance(t, str) and t for t in triggers):
            errors.append(f"Item {idx} has invalid triggers: {triggers}")
            continue
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"Item {idx} missing/empty description")
            continue
        for t in triggers:
            t_lower = t.lower()
            if t_lower in seen_triggers:
                warnings.append(f"Duplicate trigger '{t_lower}' (first declared earlier); consider pruning.")
            else:
                seen_triggers[t_lower] = 'ok'
        # Heuristic synergy placeholder suggestion
        if '{SYNERGIES}' not in desc:
            lower_desc = desc.lower()
            if any(w in lower_desc for w in SYNERGY_HINT_WORDS):
                # Suggest placeholder usage
                warnings.append(f"Item {idx} ('{triggers[0]}') may benefit from {{SYNERGIES}} placeholder.")
    theme_names = _load_theme_names()

    # Synergy pairs validation
    if PAIRS_PATH.exists():
        try:
            pairs_raw = yaml.safe_load(PAIRS_PATH.read_text(encoding='utf-8')) or {}
            pairs = pairs_raw.get('synergy_pairs', {}) if isinstance(pairs_raw, dict) else {}
            if not isinstance(pairs, dict):
                errors.append('synergy_pairs.yml: root.synergy_pairs must be a mapping')
            else:
                for theme, lst in pairs.items():
                    if not isinstance(lst, list):
                        errors.append(f'synergy_pairs.{theme} not list')
                        continue
                    seen_local = set()
                    for s in lst:
                        if s == theme:
                            errors.append(f'{theme} lists itself as synergy')
                        if s in seen_local:
                            errors.append(f'{theme} duplicate curated synergy {s}')
                        seen_local.add(s)
                    if len(lst) > 12:
                        warnings.append(f'{theme} curated synergies >12 ({len(lst)})')
                    if theme_names and theme not in theme_names:
                        warnings.append(f'{theme} not yet in catalog (pending addition)')
        except Exception as e:  # pragma: no cover
            errors.append(f'Failed parsing synergy_pairs.yml: {e}')

    # Cluster validation
    if CLUSTERS_PATH.exists():
        try:
            clusters_raw = yaml.safe_load(CLUSTERS_PATH.read_text(encoding='utf-8')) or {}
            clusters = clusters_raw.get('clusters', []) if isinstance(clusters_raw, dict) else []
            if not isinstance(clusters, list):
                errors.append('theme_clusters.yml: clusters must be a list')
            else:
                seen_ids = set()
                for c in clusters:
                    if not isinstance(c, dict):
                        errors.append('cluster entry not dict')
                        continue
                    cid = c.get('id')
                    if not cid or cid in seen_ids:
                        errors.append(f'cluster id missing/duplicate: {cid}')
                    seen_ids.add(cid)
                    themes = c.get('themes') or []
                    if not isinstance(themes, list) or not themes:
                        errors.append(f'cluster {cid} missing themes list')
                        continue
                    seen_local = set()
                    for t in themes:
                        if t in seen_local:
                            errors.append(f'cluster {cid} duplicate theme {t}')
                        seen_local.add(t)
                        if theme_names and t not in theme_names:
                            warnings.append(f'cluster {cid} theme {t} not in catalog (maybe naming variant)')
        except Exception as e:  # pragma: no cover
            errors.append(f'Failed parsing theme_clusters.yml: {e}')

    if errors:
        print("VALIDATION FAILURES:", file=sys.stderr)
        for e in errors:
            print(f" - {e}", file=sys.stderr)
        return 1
    if warnings:
        print("Validation warnings:")
        for w in warnings:
            print(f" - {w}")
    print(f"Mapping OK. {len(seen_triggers)} unique trigger substrings.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
