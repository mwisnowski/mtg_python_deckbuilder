"""Augment per-theme YAML files with derived metadata from theme_list.json.

This post-processing step keeps editorial-facing YAML files aligned with the
merged catalog output by adding (when missing):
  - description (auto-generated or curated from catalog)
  - popularity_bucket
  - popularity_hint (if present in catalog and absent in YAML)
  - deck_archetype (defensive backfill; normally curator-supplied)

Non-goals:
  - Do NOT overwrite existing curated values.
  - Do NOT remove fields.
  - Do NOT inject example_commanders/example_cards (those are managed by
    suggestion + padding scripts run earlier in the enrichment pipeline).

Safety:
  - Skips deprecated alias placeholder YAMLs (notes contains 'Deprecated alias file')
  - Emits a concise summary of modifications

Usage:
  python code/scripts/augment_theme_yaml_from_catalog.py

Exit codes:
  0 on success (even if 0 files modified)
  1 on fatal I/O or parse issues preventing processing
"""
from __future__ import annotations

from pathlib import Path
import json
import sys
from typing import Dict, Any
from datetime import datetime as _dt

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'
THEME_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'


def load_catalog() -> Dict[str, Dict[str, Any]]:
    if not THEME_JSON.exists():
        raise FileNotFoundError(f"theme_list.json missing at {THEME_JSON}")
    try:
        data = json.loads(THEME_JSON.read_text(encoding='utf-8') or '{}')
    except Exception as e:
        raise RuntimeError(f"Failed parsing theme_list.json: {e}")
    themes = data.get('themes') or []
    out: Dict[str, Dict[str, Any]] = {}
    for t in themes:
        if isinstance(t, dict) and t.get('theme'):
            out[str(t['theme'])] = t
    return out


def augment() -> int:  # pragma: no cover (IO heavy)
    if yaml is None:
        print('PyYAML not installed; cannot augment')
        return 1
    try:
        catalog_map = load_catalog()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    if not CATALOG_DIR.exists():
        print('Catalog directory missing; nothing to augment')
        return 0
    modified = 0
    scanned = 0
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        name = str(data.get('display_name') or '').strip()
        if not name:
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        scanned += 1
        cat_entry = catalog_map.get(name)
        if not cat_entry:
            continue  # theme absent from catalog (possibly filtered) – skip
        before = dict(data)
        # description
        if 'description' not in data and 'description' in cat_entry and cat_entry['description']:
            data['description'] = cat_entry['description']
        # popularity bucket
        if 'popularity_bucket' not in data and cat_entry.get('popularity_bucket'):
            data['popularity_bucket'] = cat_entry['popularity_bucket']
        # popularity hint
        if 'popularity_hint' not in data and cat_entry.get('popularity_hint'):
            data['popularity_hint'] = cat_entry['popularity_hint']
        # deck_archetype defensive fill
        if 'deck_archetype' not in data and cat_entry.get('deck_archetype'):
            data['deck_archetype'] = cat_entry['deck_archetype']
        # Per-theme metadata_info enrichment marker
        # Do not overwrite existing metadata_info if curator already defined/migrated it
        if 'metadata_info' not in data:
            data['metadata_info'] = {
                'augmented_at': _dt.now().isoformat(timespec='seconds'),
                'augmented_fields': [k for k in ('description','popularity_bucket','popularity_hint','deck_archetype') if k in data and k not in before]
            }
        else:
            # Append augmentation timestamp non-destructively
            if isinstance(data.get('metadata_info'), dict):
                mi = data['metadata_info']
                if 'augmented_at' not in mi:
                    mi['augmented_at'] = _dt.now().isoformat(timespec='seconds')
        if data != before:
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
            modified += 1
    print(f"[augment] scanned={scanned} modified={modified}")
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(augment())
