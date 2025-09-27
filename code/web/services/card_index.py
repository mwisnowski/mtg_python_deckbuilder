"""Card index construction & lookup (extracted from sampling / theme_preview).

Phase A refactor: Provides a thin API for building and querying the in-memory
card index keyed by tag/theme. Future enhancements may introduce a persistent
cache layer or precomputed artifact.

Public API:
  maybe_build_index() -> None
  get_tag_pool(tag: str) -> list[dict]
  lookup_commander(name: str) -> dict | None

The index is rebuilt lazily when any of the CSV shard files change mtime.
"""
from __future__ import annotations

from pathlib import Path
import csv
import os
from typing import Any, Dict, List, Optional

CARD_FILES_GLOB = [
    Path("csv_files/blue_cards.csv"),
    Path("csv_files/white_cards.csv"),
    Path("csv_files/black_cards.csv"),
    Path("csv_files/red_cards.csv"),
    Path("csv_files/green_cards.csv"),
    Path("csv_files/colorless_cards.csv"),
    Path("csv_files/cards.csv"),  # fallback large file last
]

THEME_TAGS_COL = "themeTags"
NAME_COL = "name"
COLOR_IDENTITY_COL = "colorIdentity"
MANA_COST_COL = "manaCost"
RARITY_COL = "rarity"

_CARD_INDEX: Dict[str, List[Dict[str, Any]]] = {}
_CARD_INDEX_MTIME: float | None = None

_RARITY_NORM = {
    "mythic rare": "mythic",
    "mythic": "mythic",
    "m": "mythic",
    "rare": "rare",
    "r": "rare",
    "uncommon": "uncommon",
    "u": "uncommon",
    "common": "common",
    "c": "common",
}

def _normalize_rarity(raw: str) -> str:
    r = (raw or "").strip().lower()
    return _RARITY_NORM.get(r, r)

def _resolve_card_files() -> List[Path]:
    """Return base card file list + any extra test files supplied via env.

    Environment variable: CARD_INDEX_EXTRA_CSV can contain a comma or semicolon
    separated list of additional CSV paths (used by tests to inject synthetic
    edge cases without polluting production shards).
    """
    files: List[Path] = list(CARD_FILES_GLOB)
    extra = os.getenv("CARD_INDEX_EXTRA_CSV")
    if extra:
        for part in extra.replace(";", ",").split(","):
            p = part.strip()
            if not p:
                continue
            path_obj = Path(p)
            # Include even if missing; maybe created later in test before build
            files.append(path_obj)
    return files


def maybe_build_index() -> None:
    """Rebuild the index if any card CSV mtime changed.

    Incorporates any extra CSVs specified via CARD_INDEX_EXTRA_CSV.
    """
    global _CARD_INDEX, _CARD_INDEX_MTIME
    latest = 0.0
    card_files = _resolve_card_files()
    for p in card_files:
        if p.exists():
            mt = p.stat().st_mtime
            if mt > latest:
                latest = mt
    if _CARD_INDEX and _CARD_INDEX_MTIME and latest <= _CARD_INDEX_MTIME:
        return
    new_index: Dict[str, List[Dict[str, Any]]] = {}
    for p in card_files:
        if not p.exists():
            continue
        try:
            with p.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames or THEME_TAGS_COL not in reader.fieldnames:
                    continue
                for row in reader:
                    name = row.get(NAME_COL) or row.get("faceName") or ""
                    tags_raw = row.get(THEME_TAGS_COL) or ""
                    tags = [t.strip(" '[]") for t in tags_raw.split(',') if t.strip()] if tags_raw else []
                    if not tags:
                        continue
                    color_id = (row.get(COLOR_IDENTITY_COL) or "").strip()
                    mana_cost = (row.get(MANA_COST_COL) or "").strip()
                    rarity = _normalize_rarity(row.get(RARITY_COL) or "")
                    for tg in tags:
                        if not tg:
                            continue
                        new_index.setdefault(tg, []).append({
                            "name": name,
                            "color_identity": color_id,
                            "tags": tags,
                            "mana_cost": mana_cost,
                            "rarity": rarity,
                            "color_identity_list": list(color_id) if color_id else [],
                            "pip_colors": [c for c in mana_cost if c in {"W","U","B","R","G"}],
                        })
        except Exception:
            continue
    _CARD_INDEX = new_index
    _CARD_INDEX_MTIME = latest

def get_tag_pool(tag: str) -> List[Dict[str, Any]]:
    return _CARD_INDEX.get(tag, [])

def lookup_commander(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    needle = name.lower().strip()
    for tag_cards in _CARD_INDEX.values():
        for c in tag_cards:
            if c.get("name", "").lower() == needle:
                return c
    return None
