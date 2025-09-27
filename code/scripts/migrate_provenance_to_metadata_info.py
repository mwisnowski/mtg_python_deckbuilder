"""One-off migration: rename 'provenance' key to 'metadata_info' in theme YAML files.

Safety characteristics:
 - Skips files already migrated.
 - Creates a side-by-side backup copy with suffix '.pre_meta_migration' on first change.
 - Preserves ordering and other fields; only renames key.
 - Merges existing metadata_info if both present (metadata_info takes precedence).

Usage:
  python code/scripts/migrate_provenance_to_metadata_info.py --apply

Dry run (default) prints summary only.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Dict, Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def migrate_file(path: Path, apply: bool = False) -> bool:
    if yaml is None:
        raise RuntimeError('PyYAML not installed')
    try:
        data: Dict[str, Any] | None = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if 'metadata_info' in data and 'provenance' not in data:
        return False  # already migrated
    if 'provenance' not in data:
        return False  # nothing to do
    prov = data.get('provenance') if isinstance(data.get('provenance'), dict) else {}
    meta_existing = data.get('metadata_info') if isinstance(data.get('metadata_info'), dict) else {}
    merged = {**prov, **meta_existing}  # metadata_info values override provenance on key collision
    data['metadata_info'] = merged
    if 'provenance' in data:
        del data['provenance']
    if apply:
        backup = path.with_suffix(path.suffix + '.pre_meta_migration')
        if not backup.exists():  # only create backup first time
            backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return True


def main():  # pragma: no cover (script)
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Write changes (default dry-run)')
    args = ap.parse_args()
    changed = 0
    total = 0
    for yml in sorted(CATALOG_DIR.glob('*.yml')):
        total += 1
        if migrate_file(yml, apply=args.apply):
            changed += 1
    print(f"[migrate] scanned={total} changed={changed} mode={'apply' if args.apply else 'dry-run'}")
    if not args.apply:
        print('Re-run with --apply to persist changes.')


if __name__ == '__main__':  # pragma: no cover
    main()
