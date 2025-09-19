"""Remove placeholder ' Anchor' example_commanders when real examples have been added.

Usage:
  python code/scripts/cleanup_placeholder_examples.py --dry-run
  python code/scripts/cleanup_placeholder_examples.py --apply

Rules:
 - If a theme's example_commanders list contains at least one non-placeholder entry
   AND at least one placeholder (suffix ' Anchor'), strip all placeholder entries.
 - If the list becomes empty (edge case), leave one placeholder (first) to avoid
   violating minimum until regeneration.
 - Report counts of cleaned themes.
"""
from __future__ import annotations
from pathlib import Path
import argparse

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

def is_placeholder(s: str) -> bool:
    return s.endswith(' Anchor')

def main(dry_run: bool) -> int:  # pragma: no cover
    if yaml is None:
        print('PyYAML missing')
        return 1
    cleaned = 0
    for p in sorted(CATALOG_DIR.glob('*.yml')):
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not data.get('display_name'):
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        ex = data.get('example_commanders')
        if not isinstance(ex, list) or not ex:
            continue
        placeholders = [e for e in ex if isinstance(e, str) and is_placeholder(e)]
        real = [e for e in ex if isinstance(e, str) and not is_placeholder(e)]
        if placeholders and real:
            new_list = real if real else placeholders[:1]
            if new_list != ex:
                print(f"[cleanup] {p.name}: removed {len(placeholders)} placeholders -> {len(new_list)} examples")
                cleaned += 1
                if not dry_run:
                    data['example_commanders'] = new_list
                    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print(f"[cleanup] cleaned {cleaned} themes")
    return 0

if __name__ == '__main__':  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    raise SystemExit(main(not args.apply))
