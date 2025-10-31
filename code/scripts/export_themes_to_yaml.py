"""Phase A: Export existing generated theme_list.json into per-theme YAML files.

Generates one YAML file per theme under config/themes/catalog/<slug>.yml

Slug rules:
- Lowercase
- Alphanumerics kept
- Spaces and consecutive separators -> single hyphen
- '+' replaced with 'plus'
- '/' replaced with '-'
- Other punctuation removed
- Collapse multiple hyphens

YAML schema (initial minimal):
  id: <slug>
  display_name: <theme>
  curated_synergies: [ ... ]           # (only curated portion, best-effort guess)
  enforced_synergies: [ ... ]          # (if present in whitelist enforced_synergies or auto-inferred cluster)
  primary_color: Optional TitleCase
  secondary_color: Optional TitleCase
  notes: ''                            # placeholder for editorial additions

We treat current synergy list (capped) as partially curated; we attempt to recover curated vs inferred by re-running
`derive_synergies_for_tags` from extract_themes (imported) to see which curated anchors apply.

Safety: Does NOT overwrite an existing file unless --force provided.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set

import yaml  # type: ignore

# Reuse logic from extract_themes by importing derive_synergies_for_tags
import sys
SCRIPT_ROOT = Path(__file__).resolve().parent
CODE_ROOT = SCRIPT_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))
from scripts.extract_themes import derive_synergies_for_tags

ROOT = Path(__file__).resolve().parents[2]
THEME_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'
WHITELIST_YML = ROOT / 'config' / 'themes' / 'theme_whitelist.yml'


def load_theme_json() -> Dict:
    if not THEME_JSON.exists():
        raise SystemExit(f"theme_list.json not found at {THEME_JSON}. Run extract_themes.py first.")
    return json.loads(THEME_JSON.read_text(encoding='utf-8'))


def load_whitelist() -> Dict:
    if not WHITELIST_YML.exists():
        return {}
    try:
        return yaml.safe_load(WHITELIST_YML.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = s.replace('+', 'plus')
    s = s.replace('/', '-')
    # Replace spaces & underscores with hyphen
    s = re.sub(r'[\s_]+', '-', s)
    # Remove disallowed chars (keep alnum and hyphen)
    s = re.sub(r'[^a-z0-9-]', '', s)
    # Collapse multiple hyphens
    s = re.sub(r'-{2,}', '-', s)
    return s.strip('-')


def recover_curated_synergies(all_themes: Set[str], theme: str) -> List[str]:
    # Recompute curated mapping and return the curated list if present
    curated_map = derive_synergies_for_tags(all_themes)
    return curated_map.get(theme, [])


def main():
    parser = argparse.ArgumentParser(description='Export per-theme YAML catalog files (Phase A).')
    parser.add_argument('--force', action='store_true', help='Overwrite existing YAML files if present.')
    parser.add_argument('--limit', type=int, default=0, help='Limit export to first N themes (debug).')
    args = parser.parse_args()

    data = load_theme_json()
    themes = data.get('themes', [])
    whitelist = load_whitelist()
    enforced_cfg = whitelist.get('enforced_synergies', {}) if isinstance(whitelist.get('enforced_synergies', {}), dict) else {}

    all_theme_names: Set[str] = {t.get('theme') for t in themes if isinstance(t, dict) and t.get('theme')}

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    exported = 0
    for entry in themes:
        theme_name = entry.get('theme')
        if not theme_name:
            continue
        if args.limit and exported >= args.limit:
            break
        slug = slugify(theme_name)
        path = CATALOG_DIR / f'{slug}.yml'
        if path.exists() and not args.force:
            continue
        synergy_list = entry.get('synergies', []) or []
        # Attempt to separate curated portion (only for themes in curated mapping)
        curated_synergies = recover_curated_synergies(all_theme_names, theme_name)
        enforced_synergies = enforced_cfg.get(theme_name, [])
        # Keep order: curated -> enforced -> inferred. synergy_list already reflects that ordering from generation.
        # Filter curated to those present in current synergy_list to avoid stale entries.
        curated_synergies = [s for s in curated_synergies if s in synergy_list]
        # Remove enforced from curated to avoid duplication across buckets
        curated_synergies_clean = [s for s in curated_synergies if s not in enforced_synergies]
        # Inferred = remaining items in synergy_list not in curated or enforced
        curated_set = set(curated_synergies_clean)
        enforced_set = set(enforced_synergies)
        inferred_synergies = [s for s in synergy_list if s not in curated_set and s not in enforced_set]

        example_cards_value = entry.get('example_cards', [])
        example_commanders_value = entry.get('example_commanders', [])
        
        doc = {
            'id': slug,
            'display_name': theme_name,
            'synergies': synergy_list,  # full capped list (ordered)
            'curated_synergies': curated_synergies_clean,
            'enforced_synergies': enforced_synergies,
            'inferred_synergies': inferred_synergies,
            'primary_color': entry.get('primary_color'),
            'secondary_color': entry.get('secondary_color'),
            'example_cards': example_cards_value,
            'example_commanders': example_commanders_value,
            'synergy_example_cards': entry.get('synergy_example_cards', []),
            'synergy_commanders': entry.get('synergy_commanders', []),
            'deck_archetype': entry.get('deck_archetype'),
            'popularity_hint': entry.get('popularity_hint'),
            'popularity_bucket': entry.get('popularity_bucket'),
            'editorial_quality': entry.get('editorial_quality'),
            'description': entry.get('description'),
            'notes': ''
        }
        # Drop None/empty keys for cleanliness
        if doc['primary_color'] is None:
            doc.pop('primary_color')
        if doc.get('secondary_color') is None:
            doc.pop('secondary_color')
        if not doc.get('example_cards'):
            doc.pop('example_cards')
        if not doc.get('example_commanders'):
            doc.pop('example_commanders')
        if not doc.get('synergy_example_cards'):
            doc.pop('synergy_example_cards')
        if not doc.get('synergy_commanders'):
            doc.pop('synergy_commanders')
        if doc.get('deck_archetype') is None:
            doc.pop('deck_archetype')
        if doc.get('popularity_hint') is None:
            doc.pop('popularity_hint')
        if doc.get('popularity_bucket') is None:
            doc.pop('popularity_bucket')
        if doc.get('editorial_quality') is None:
            doc.pop('editorial_quality')
        if doc.get('description') is None:
            doc.pop('description')
        with path.open('w', encoding='utf-8') as f:
            yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)
        exported += 1

    print(f"Exported {exported} theme YAML files to {CATALOG_DIR}")


if __name__ == '__main__':
    main()
