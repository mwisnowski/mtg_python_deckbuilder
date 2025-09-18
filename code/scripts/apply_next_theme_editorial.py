"""Apply example_cards / example_commanders to the next theme missing them.

Usage:
  python code/scripts/apply_next_theme_editorial.py

Repeating invocation will fill themes one at a time (skips deprecated alias placeholders).
Options:
  --force  overwrite existing lists for that theme
  --top / --top-commanders size knobs forwarded to suggestion generator
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import yaml  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def find_next_missing():
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        notes = data.get('notes', '')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        # Completion rule: a theme is considered "missing" only if a key itself is absent.
        # We intentionally allow empty lists (e.g., obscure themes with no clear commanders)
        # so we don't get stuck repeatedly selecting the same file.
        if ('example_cards' not in data) or ('example_commanders' not in data):
            return data.get('display_name'), path.name
    return None, None


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description='Apply editorial examples to next missing theme')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--top', type=int, default=8)
    ap.add_argument('--top-commanders', type=int, default=5)
    args = ap.parse_args()
    theme, fname = find_next_missing()
    if not theme:
        print('All themes already have example_cards & example_commanders (or no YAML).')
        return
    print(f"Next missing theme: {theme} ({fname})")
    cmd = [
        sys.executable,
        str(ROOT / 'code' / 'scripts' / 'generate_theme_editorial_suggestions.py'),
        '--themes', theme,
        '--apply', '--limit-yaml', '1',
        '--top', str(args.top), '--top-commanders', str(args.top_commanders)
    ]
    if args.force:
        cmd.append('--force')
    print('Running:', ' '.join(cmd))
    subprocess.run(cmd, check=False)
    # Post-pass: if we managed to add example_cards but no commanders were inferred, stamp an empty list
    # so subsequent runs proceed to the next theme instead of re-processing this one forever.
    if fname:
        target = CATALOG_DIR / fname
        try:
            data = yaml.safe_load(target.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'example_cards' in data and 'example_commanders' not in data:
                data['example_commanders'] = []
                target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
                print(f"[post] added empty example_commanders list to {fname} (no suggestions available)")
        except Exception as e:  # pragma: no cover
            print(f"[post-warn] failed to add placeholder commanders for {fname}: {e}")


if __name__ == '__main__':
    main()
