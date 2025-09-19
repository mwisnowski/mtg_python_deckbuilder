"""Remove legacy placeholder 'Anchor' example_commanders entries.

Rules:
 - If all entries are placeholders (endwith ' Anchor'), list is cleared to []
 - If mixed, remove only the placeholder entries
 - Prints summary of modifications; dry-run by default unless --apply
 - Exits 0 on success
"""
from __future__ import annotations
from pathlib import Path
import argparse
import re

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def main(apply: bool) -> int:  # pragma: no cover
    if yaml is None:
        print('PyYAML not installed')
        return 1
    modified = 0
    pattern = re.compile(r" Anchor( [A-Z])?$")
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        ex = data.get('example_commanders')
        if not isinstance(ex, list) or not ex:
            continue
        placeholders = [e for e in ex if isinstance(e, str) and pattern.search(e)]
        if not placeholders:
            continue
        real = [e for e in ex if isinstance(e, str) and not pattern.search(e)]
        new_list = real if real else []  # all placeholders removed if no real
        if new_list != ex:
            modified += 1
            print(f"[purge] {path.name}: {len(ex)} -> {len(new_list)} (removed {len(ex)-len(new_list)} placeholders)")
            if apply:
                data['example_commanders'] = new_list
                path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print(f"[purge] modified {modified} files")
    return 0


if __name__ == '__main__':  # pragma: no cover
    ap = argparse.ArgumentParser(description='Purge legacy placeholder Anchor entries from example_commanders')
    ap.add_argument('--apply', action='store_true', help='Write changes (default dry run)')
    args = ap.parse_args()
    raise SystemExit(main(args.apply))