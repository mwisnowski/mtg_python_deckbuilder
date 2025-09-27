"""Pad example_commanders lists up to a minimum threshold.

Use after running `autofill_min_examples.py` which guarantees every theme has at least
one (typically three) placeholder examples. This script promotes coverage from
the 1..(min-1) state to the configured minimum (default 5) so that
`lint_theme_editorial.py --enforce-min-examples` will pass.

Rules / heuristics:
 - Skip deprecated alias placeholder YAMLs (notes contains 'Deprecated alias file')
 - Skip themes already meeting/exceeding the threshold
 - Do NOT modify themes whose existing examples contain any non-placeholder entries
   (heuristic: placeholder entries end with ' Anchor') unless `--force-mixed` is set.
 - Generate additional placeholder names by:
     1. Unused synergies beyond the first two ("<Synergy> Anchor")
     2. If still short, append generic numbered anchors based on display name:
        "<Display> Anchor B", "<Display> Anchor C", etc.
 - Preserve existing editorial_quality; if absent, set to 'draft'.

This keeps placeholder noise obvious while allowing CI enforcement gating.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import string

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def is_placeholder(entry: str) -> bool:
    return entry.endswith(' Anchor')


def build_extra_placeholders(display: str, synergies: list[str], existing: list[str], need: int) -> list[str]:
    out: list[str] = []
    used = set(existing)
    # 1. Additional synergies not already used
    for syn in synergies[2:]:  # first two were used by autofill
        cand = f"{syn} Anchor"
        if cand not in used and syn != display:
            out.append(cand)
            if len(out) >= need:
                return out
    # 2. Generic letter suffixes
    suffix_iter = list(string.ascii_uppercase[1:])  # start from 'B'
    for s in suffix_iter:
        cand = f"{display} Anchor {s}"
        if cand not in used:
            out.append(cand)
            if len(out) >= need:
                break
    return out


def pad(min_examples: int, force_mixed: bool) -> int:  # pragma: no cover (IO heavy)
    if yaml is None:
        print('PyYAML not installed; cannot pad')
        return 1
    modified = 0
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict) or not data.get('display_name'):
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        examples = data.get('example_commanders') or []
        if not isinstance(examples, list):
            continue
        if len(examples) >= min_examples:
            continue
        # Heuristic: only pure placeholder sets unless forced
        if not force_mixed and any(not is_placeholder(e) for e in examples):
            continue
        display = data['display_name']
        synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
        need = min_examples - len(examples)
        new_entries = build_extra_placeholders(display, synergies, examples, need)
        if not new_entries:
            continue
        data['example_commanders'] = examples + new_entries
        if not data.get('editorial_quality'):
            data['editorial_quality'] = 'draft'
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
        modified += 1
        print(f"[pad] padded {path.name} (+{len(new_entries)}) -> {len(examples)+len(new_entries)} examples")
    print(f"[pad] modified {modified} files")
    return 0


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description='Pad placeholder example_commanders up to minimum threshold')
    ap.add_argument('--min', type=int, default=5, help='Minimum examples target (default 5)')
    ap.add_argument('--force-mixed', action='store_true', help='Pad even if list contains non-placeholder entries')
    args = ap.parse_args()
    raise SystemExit(pad(args.min, args.force_mixed))


if __name__ == '__main__':  # pragma: no cover
    main()
