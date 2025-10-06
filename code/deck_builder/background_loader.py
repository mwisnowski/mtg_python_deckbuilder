"""Loader for background cards derived from `background_cards.csv`."""
from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Mapping, Tuple

from code.logging_util import get_logger
from deck_builder.partner_background_utils import analyze_partner_background
from path_util import csv_dir

LOGGER = get_logger(__name__)

BACKGROUND_FILENAME = "background_cards.csv"


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
    """Load and cache background card data."""

    resolved = _resolve_background_path(source_path)
    try:
        stat = resolved.stat()
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        size = stat.st_size
    except FileNotFoundError:
        raise FileNotFoundError(f"Background CSV not found at {resolved}") from None

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

    with path.open("r", encoding="utf-8", newline="") as handle:
        first_line = handle.readline()
        version = "unknown"
        if first_line.startswith("#"):
            version = _parse_version(first_line)
        else:
            handle.seek(0)
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return tuple(), version
        entries = _rows_to_cards(reader)

    frozen = tuple(entries)
    return frozen, version


def _resolve_background_path(override: str | Path | None) -> Path:
    if override:
        return Path(override).resolve()
    return (Path(csv_dir()) / BACKGROUND_FILENAME).resolve()


def _parse_version(line: str) -> str:
    tokens = line.lstrip("# ").strip().split()
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key == "version":
            return value
    return "unknown"


def _rows_to_cards(reader: csv.DictReader) -> list[BackgroundCard]:
    entries: list[BackgroundCard] = []
    seen: set[str] = set()
    for raw in reader:
        if not raw:
            continue
        card = _row_to_card(raw)
        if card is None:
            continue
        key = card.display_name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(card)
    entries.sort(key=lambda card: card.display_name)
    return entries


def _row_to_card(row: Mapping[str, str]) -> BackgroundCard | None:
    name = _clean_str(row.get("name"))
    face_name = _clean_str(row.get("faceName")) or None
    display = face_name or name
    if not display:
        return None

    type_line = _clean_str(row.get("type"))
    oracle_text = _clean_multiline(row.get("text"))
    raw_theme_tags = tuple(_parse_literal_list(row.get("themeTags")))
    detection = analyze_partner_background(type_line, oracle_text, raw_theme_tags)
    if not detection.is_background:
        return None

    return BackgroundCard(
        name=name,
        face_name=face_name,
        display_name=display,
        slug=_slugify(display),
        color_identity=_parse_color_list(row.get("colorIdentity")),
        colors=_parse_color_list(row.get("colors")),
        mana_cost=_clean_str(row.get("manaCost")),
        mana_value=_parse_float(row.get("manaValue")),
        type_line=type_line,
        oracle_text=oracle_text,
        keywords=tuple(_split_list(row.get("keywords"))),
        theme_tags=tuple(tag for tag in raw_theme_tags if tag),
        raw_theme_tags=raw_theme_tags,
        edhrec_rank=_parse_int(row.get("edhrecRank")),
        layout=_clean_str(row.get("layout")) or "normal",
        side=_clean_str(row.get("side")) or None,
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
    if isinstance(value, (list, tuple, set)):
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
    text = _clean_str(value)
    if not text:
        return []
    parts = [part.strip() for part in text.split(",")]
    return [part for part in parts if part]


def _parse_color_list(value: object) -> Tuple[str, ...]:
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
