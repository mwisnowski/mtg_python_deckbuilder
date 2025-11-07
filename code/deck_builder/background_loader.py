"""Loader for background cards derived from all_cards.parquet."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Tuple

from logging_util import get_logger
from deck_builder.partner_background_utils import analyze_partner_background

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BackgroundCard:
    """Normalized background card entry."""

    name: str
    face_name: str | None
    display_name: str
    slug: str
    color_identity: Tuple[str, ...]
    colors: Tuple[str, ...]
    mana_cost: str
    mana_value: float | None
    type_line: str
    oracle_text: str
    keywords: Tuple[str, ...]
    theme_tags: Tuple[str, ...]
    raw_theme_tags: Tuple[str, ...]
    edhrec_rank: int | None
    layout: str
    side: str | None


@dataclass(frozen=True, slots=True)
class BackgroundCatalog:
    source_path: Path
    etag: str
    mtime_ns: int
    size: int
    version: str
    entries: Tuple[BackgroundCard, ...]
    by_name: Mapping[str, BackgroundCard]

    def get(self, name: str) -> BackgroundCard | None:
        return self.by_name.get(name.lower())


def load_background_cards(
    source_path: str | Path | None = None,
) -> BackgroundCatalog:
    """Load and cache background card data from all_cards.parquet."""

    resolved = _resolve_background_path(source_path)
    try:
        stat = resolved.stat()
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        size = stat.st_size
    except FileNotFoundError:
        raise FileNotFoundError(f"Background data not found at {resolved}") from None

    entries, version = _load_background_cards_cached(str(resolved), mtime_ns)
    etag = f"{size}-{mtime_ns}-{len(entries)}"
    catalog = BackgroundCatalog(
        source_path=resolved,
        etag=etag,
        mtime_ns=mtime_ns,
        size=size,
        version=version,
        entries=entries,
        by_name={card.display_name.lower(): card for card in entries},
    )
    LOGGER.info("background_cards_loaded count=%s version=%s path=%s", len(entries), version, resolved)
    return catalog


@lru_cache(maxsize=4)
def _load_background_cards_cached(path_str: str, mtime_ns: int) -> Tuple[Tuple[BackgroundCard, ...], str]:
    path = Path(path_str)
    if not path.exists():
        return tuple(), "unknown"

    try:
        import pandas as pd
        df = pd.read_parquet(path, engine="pyarrow")
        
        # Filter for background cards
        if 'isBackground' not in df.columns:
            LOGGER.warning("isBackground column not found in %s", path)
            return tuple(), "unknown"
        
        df_backgrounds = df[df['isBackground']].copy()
        
        if len(df_backgrounds) == 0:
            LOGGER.warning("No background cards found in %s", path)
            return tuple(), "unknown"
        
        entries = _rows_to_cards(df_backgrounds)
        version = "parquet"
        
    except Exception as e:
        LOGGER.error("Failed to load backgrounds from %s: %s", path, e)
        return tuple(), "unknown"

    frozen = tuple(entries)
    return frozen, version


def _resolve_background_path(override: str | Path | None) -> Path:
    """Resolve path to all_cards.parquet."""
    if override:
        return Path(override).resolve()
    # Use card_files/processed/all_cards.parquet
    return Path("card_files/processed/all_cards.parquet").resolve()


def _rows_to_cards(df) -> list[BackgroundCard]:
    """Convert DataFrame rows to BackgroundCard objects."""
    entries: list[BackgroundCard] = []
    seen: set[str] = set()
    
    for _, row in df.iterrows():
        if row.empty:
            continue
        card = _row_to_card(row)
        if card is None:
            continue
        key = card.display_name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(card)
    
    entries.sort(key=lambda card: card.display_name)
    return entries


def _row_to_card(row) -> BackgroundCard | None:
    """Convert a DataFrame row to a BackgroundCard."""
    # Helper to safely get values from DataFrame row
    def get_val(key: str):
        try:
            if hasattr(row, key):
                val = getattr(row, key)
                # Handle pandas NA/None
                if val is None or (hasattr(val, '__class__') and 'NA' in val.__class__.__name__):
                    return None
                return val
            return None
        except Exception:
            return None
    
    name = _clean_str(get_val("name"))
    face_name = _clean_str(get_val("faceName")) or None
    display = face_name or name
    if not display:
        return None

    type_line = _clean_str(get_val("type"))
    oracle_text = _clean_multiline(get_val("text"))
    raw_theme_tags = tuple(_parse_literal_list(get_val("themeTags")))
    detection = analyze_partner_background(type_line, oracle_text, raw_theme_tags)
    if not detection.is_background:
        return None

    return BackgroundCard(
        name=name,
        face_name=face_name,
        display_name=display,
        slug=_slugify(display),
        color_identity=_parse_color_list(get_val("colorIdentity")),
        colors=_parse_color_list(get_val("colors")),
        mana_cost=_clean_str(get_val("manaCost")),
        mana_value=_parse_float(get_val("manaValue")),
        type_line=type_line,
        oracle_text=oracle_text,
        keywords=tuple(_split_list(get_val("keywords"))),
        theme_tags=tuple(tag for tag in raw_theme_tags if tag),
        raw_theme_tags=raw_theme_tags,
        edhrec_rank=_parse_int(get_val("edhrecRank")),
        layout=_clean_str(get_val("layout")) or "normal",
        side=_clean_str(get_val("side")) or None,
    )


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_multiline(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines())


def _parse_literal_list(value: object) -> list[str]:
    if value is None:
        return []
    
    # Check if it's a numpy array (from Parquet/pandas)
    is_numpy = False
    try:
        import numpy as np
        is_numpy = isinstance(value, np.ndarray)
    except ImportError:
        pass
    
    # Handle lists, tuples, sets, and numpy arrays
    if isinstance(value, (list, tuple, set)) or is_numpy:
        return [str(item).strip() for item in value if str(item).strip()]
    
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except Exception:
        parsed = None
    if isinstance(parsed, (list, tuple, set)):
        return [str(item).strip() for item in parsed if str(item).strip()]
    parts = [part.strip() for part in text.replace(";", ",").split(",")]
    return [part for part in parts if part]


def _split_list(value: object) -> list[str]:
    # Check if it's a numpy array (from Parquet/pandas)
    is_numpy = False
    try:
        import numpy as np
        is_numpy = isinstance(value, np.ndarray)
    except ImportError:
        pass
    
    if isinstance(value, (list, tuple, set)) or is_numpy:
        return [str(item).strip() for item in value if str(item).strip()]
    
    text = _clean_str(value)
    if not text:
        return []
    parts = [part.strip() for part in text.split(",")]
    return [part for part in parts if part]


def _parse_color_list(value: object) -> Tuple[str, ...]:
    # Check if it's a numpy array (from Parquet/pandas)
    is_numpy = False
    try:
        import numpy as np
        is_numpy = isinstance(value, np.ndarray)
    except ImportError:
        pass
    
    if isinstance(value, (list, tuple, set)) or is_numpy:
        parts = [str(item).strip().upper() for item in value if str(item).strip()]
        return tuple(parts)
    
    text = _clean_str(value)
    if not text:
        return tuple()
    parts = [part.strip().upper() for part in text.split(",")]
    return tuple(part for part in parts if part)


def _parse_float(value: object) -> float | None:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    allowed = [ch if ch.isalnum() else "-" for ch in lowered]
    slug = "".join(allowed)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def clear_background_cards_cache() -> None:
    """Clear the memoized background card cache (testing/support)."""

    _load_background_cards_cached.cache_clear()


__all__ = [
    "BackgroundCard",
    "BackgroundCatalog",
    "clear_background_cards_cache",
    "load_background_cards",
]
