"""Card index construction & lookup (extracted from sampling / theme_preview).

Phase A refactor: Provides a thin API for building and querying the in-memory
card index keyed by tag/theme. Future enhancements may introduce a persistent
cache layer or precomputed artifact.

M4: Updated to load from all_cards.parquet instead of CSV shards.

Public API:
  maybe_build_index() -> None
  get_tag_pool(tag: str) -> list[dict]
  lookup_commander(name: str) -> dict | None

The index is rebuilt lazily when the Parquet file mtime changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# M4: No longer need CSV file glob, we load from Parquet
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


def maybe_build_index() -> None:
    """Rebuild the index if the Parquet file mtime changed.

    M4: Loads from all_cards.parquet instead of CSV files.
    """
    global _CARD_INDEX, _CARD_INDEX_MTIME
    
    try:
        from path_util import get_processed_cards_path
        from deck_builder import builder_utils as bu
        
        parquet_path = Path(get_processed_cards_path())
        if not parquet_path.exists():
            return
            
        latest = parquet_path.stat().st_mtime
        if _CARD_INDEX and _CARD_INDEX_MTIME and latest <= _CARD_INDEX_MTIME:
            return
        
        # Load from Parquet
        df = bu._load_all_cards_parquet()
        if df.empty or THEME_TAGS_COL not in df.columns:
            return
        
        new_index: Dict[str, List[Dict[str, Any]]] = {}
        
        for _, row in df.iterrows():
            name = row.get(NAME_COL) or row.get("faceName") or ""
            tags = row.get(THEME_TAGS_COL)
            
            # Handle tags (already a list after our conversion in builder_utils)
            if not tags or not isinstance(tags, list):
                continue
                
            color_id = str(row.get(COLOR_IDENTITY_COL) or "").strip()
            mana_cost = str(row.get(MANA_COST_COL) or "").strip()
            rarity = _normalize_rarity(str(row.get(RARITY_COL) or ""))
            
            for tg in tags:
                if not tg:
                    continue
                new_index.setdefault(tg, []).append({
                    "name": name,
                    "color_identity": color_id,
                    "tags": tags,
                    "mana_cost": mana_cost,
                    "rarity": rarity,
                    "color_identity_list": [c.strip() for c in color_id.split(',') if c.strip()],
                    "pip_colors": [c for c in mana_cost if c in {"W","U","B","R","G"}],
                })
        
        _CARD_INDEX = new_index
        _CARD_INDEX_MTIME = latest
    except Exception:
        # Defensive: if anything fails, leave index unchanged
        pass

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
