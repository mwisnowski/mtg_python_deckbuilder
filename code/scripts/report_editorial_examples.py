"""Report status of example_commanders coverage across theme YAML catalog.

Outputs counts for:
 - zero example themes
 - themes with 1-4 examples (below minimum threshold)
 - themes meeting or exceeding threshold (default 5)
Excludes deprecated alias placeholder files (identified via notes field).
"""
from __future__ import annotations
from pathlib import Path
from typing import List
import os

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'


def main(threshold: int = 5) -> int:  # pragma: no cover - simple IO script
    if yaml is None:
        print('PyYAML not installed')
        return 1
    zero: List[str] = []
    under: List[str] = []
    ok: List[str] = []
    for p in CATALOG_DIR.glob('*.yml'):
        try:
            data = yaml.safe_load(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict) or not data.get('display_name'):
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        ex = data.get('example_commanders') or []
        if not isinstance(ex, list):
            continue
        c = len(ex)
        name = data['display_name']
        if c == 0:
            zero.append(name)
        elif c < threshold:
            under.append(f"{name} ({c})")
        else:
            ok.append(name)
    print(f"THRESHOLD {threshold}")
    print(f"Zero-example themes: {len(zero)}")
    print(f"Below-threshold themes (1-{threshold-1}): {len(under)}")
    print(f"Meeting/exceeding threshold: {len(ok)}")
    print("Sample under-threshold:", sorted(under)[:30])
    return 0


if __name__ == '__main__':  # pragma: no cover
    t = int(os.environ.get('EDITORIAL_MIN_EXAMPLES', '5') or '5')
    raise SystemExit(main(t))
