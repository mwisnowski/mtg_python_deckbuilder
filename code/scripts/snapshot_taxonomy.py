"""Snapshot the current power bracket taxonomy to a dated JSON artifact.

Outputs a JSON file under logs/taxonomy_snapshots/ named
  taxonomy_<YYYYMMDD>_<HHMMSS>.json
containing:
  {
    "generated_at": ISO8601,
    "hash": sha256 hex of canonical payload (excluding this top-level wrapper),
    "brackets": [ {level,name,short_desc,long_desc,limits} ... ]
  }

If a snapshot with identical hash already exists today, creation is skipped
unless --force provided.

Usage (from repo root):
  python -m code.scripts.snapshot_taxonomy
  python -m code.scripts.snapshot_taxonomy --force

Intended to provide an auditable evolution trail for taxonomy adjustments
before we implement taxonomy-aware sampling changes.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from code.deck_builder.phases.phase0_core import BRACKET_DEFINITIONS

SNAP_DIR = Path("logs/taxonomy_snapshots")
SNAP_DIR.mkdir(parents=True, exist_ok=True)


def _canonical_brackets():
    return [
        {
            "level": b.level,
            "name": b.name,
            "short_desc": b.short_desc,
            "long_desc": b.long_desc,
            "limits": b.limits,
        }
        for b in sorted(BRACKET_DEFINITIONS, key=lambda x: x.level)
    ]


def compute_hash(brackets) -> str:
    # Canonical JSON with sorted keys for repeatable hash
    payload = json.dumps(brackets, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_existing_hashes() -> Dict[str, Path]:
    existing = {}
    for p in SNAP_DIR.glob("taxonomy_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            h = data.get("hash")
            if h:
                existing[h] = p
        except Exception:
            continue
    return existing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Write new snapshot even if identical hash exists today")
    args = ap.parse_args()

    brackets = _canonical_brackets()
    h = compute_hash(brackets)
    existing = find_existing_hashes()
    if h in existing and not args.force:
        print(f"Snapshot identical (hash={h[:12]}...) exists: {existing[h].name}; skipping.")
        return 0

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = SNAP_DIR / f"taxonomy_{ts}.json"
    wrapper: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "hash": h,
        "brackets": brackets,
    }
    out.write_text(json.dumps(wrapper, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote taxonomy snapshot {out} (hash={h[:12]}...)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
