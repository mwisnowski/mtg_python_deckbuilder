"""Autofill minimal example_commanders for themes with zero examples.

Strategy:
 - For each YAML with zero example_commanders, synthesize placeholder entries using top synergies:
     <Theme> Anchor, <First Synergy> Anchor, <Second Synergy> Anchor ... (non-real placeholders)
 - Mark editorial_quality: draft (only if not already set)
 - Skip themes already having >=1 example.
 - Limit number of files modified with --limit (default unlimited) for safety.

These placeholders are intended to be replaced by real curated suggestions later; they simply allow
min-example enforcement to be flipped without blocking on full curation of long-tail themes.
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


def synth_examples(display: str, synergies: list[str]) -> list[str]:
    out = [f"{display} Anchor"]
    for s in synergies[:2]:  # keep it short
        if isinstance(s, str) and s and s != display:
            out.append(f"{s} Anchor")
    return out


def main(limit: int) -> int:  # pragma: no cover
    if yaml is None:
        print('PyYAML not installed; cannot autofill')
        return 1
    updated = 0
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not data.get('display_name'):
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        ex = data.get('example_commanders') or []
        if isinstance(ex, list) and ex:
            continue  # already has examples
        display = data['display_name']
        synergies = data.get('synergies') or []
        examples = synth_examples(display, synergies if isinstance(synergies, list) else [])
        data['example_commanders'] = examples
        if not data.get('editorial_quality'):
            data['editorial_quality'] = 'draft'
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
        updated += 1
        print(f"[autofill] added placeholders to {path.name}")
        if limit and updated >= limit:
            print(f"[autofill] reached limit {limit}")
            break
    print(f"[autofill] updated {updated} files")
    return 0


if __name__ == '__main__':  # pragma: no cover
    ap = argparse.ArgumentParser(description='Autofill placeholder example_commanders for zero-example themes')
    ap.add_argument('--limit', type=int, default=0, help='Limit number of YAML files modified (0 = unlimited)')
    args = ap.parse_args()
    raise SystemExit(main(args.limit))
