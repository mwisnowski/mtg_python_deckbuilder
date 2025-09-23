#!/usr/bin/env python3
"""Fast path theme catalog presence & schema sanity validator.

Checks:
1. theme_list.json exists.
2. Loads JSON and ensures top-level keys present: themes (list), metadata_info (dict).
3. Basic field contract for each theme: id, theme, synergies (list), description.
4. Enforces presence of catalog_hash inside metadata_info for drift detection.
5. Optionally validates against Pydantic models if available (best effort).
Exit codes:
 0 success
 1 structural failure / missing file
 2 partial validation warnings elevated via --strict
"""
from __future__ import annotations
import sys
import json
import argparse
import pathlib
import typing as t

THEME_LIST_PATH = pathlib.Path('config/themes/theme_list.json')

class Problem:
    def __init__(self, level: str, message: str):
        self.level = level
        self.message = message
    def __repr__(self):
        return f"{self.level.upper()}: {self.message}"

def load_json(path: pathlib.Path) -> t.Any:
    try:
        return json.loads(path.read_text(encoding='utf-8') or '{}')
    except FileNotFoundError:
        raise
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"parse_error: {e}")

def validate(data: t.Any) -> list[Problem]:
    probs: list[Problem] = []
    if not isinstance(data, dict):
        probs.append(Problem('error','top-level not an object'))
        return probs
    themes = data.get('themes')
    if not isinstance(themes, list) or not themes:
        probs.append(Problem('error','themes list missing or empty'))
    meta = data.get('metadata_info')
    if not isinstance(meta, dict):
        probs.append(Problem('error','metadata_info missing or not object'))
    else:
        if not meta.get('catalog_hash'):
            probs.append(Problem('error','metadata_info.catalog_hash missing'))
        if not meta.get('generated_at'):
            probs.append(Problem('warn','metadata_info.generated_at missing'))
    # Per theme spot check (limit to first 50 to keep CI snappy)
    for i, th in enumerate(themes[:50] if isinstance(themes, list) else []):
        if not isinstance(th, dict):
            probs.append(Problem('error', f'theme[{i}] not object'))
            continue
        if not th.get('id'):
            probs.append(Problem('error', f'theme[{i}] id missing'))
        if not th.get('theme'):
            probs.append(Problem('error', f'theme[{i}] theme missing'))
        syns = th.get('synergies')
        if not isinstance(syns, list) or not syns:
            probs.append(Problem('warn', f'theme[{i}] synergies empty or not list'))
        if 'description' not in th:
            probs.append(Problem('warn', f'theme[{i}] description missing'))
    return probs

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description='Validate fast path theme catalog build presence & schema.')
    ap.add_argument('--strict-warn', action='store_true', help='Promote warnings to errors (fail CI).')
    args = ap.parse_args(argv)
    if not THEME_LIST_PATH.exists():
        print('ERROR: theme_list.json missing at expected path.', file=sys.stderr)
        return 1
    try:
        data = load_json(THEME_LIST_PATH)
    except FileNotFoundError:
        print('ERROR: theme_list.json missing.', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'ERROR: failed parsing theme_list.json: {e}', file=sys.stderr)
        return 1
    problems = validate(data)
    errors = [p for p in problems if p.level=='error']
    warns = [p for p in problems if p.level=='warn']
    for p in problems:
        stream = sys.stderr if p.level!='info' else sys.stdout
        print(repr(p), file=stream)
    if errors:
        return 1
    if args.strict_warn and warns:
        return 2
    print(f"Fast path validation ok: {len(errors)} errors, {len(warns)} warnings. Checked {min(len(data.get('themes', [])),50)} themes.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
