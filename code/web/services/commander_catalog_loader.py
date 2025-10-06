"""Commander catalog loader and normalization helpers for the web UI.

Responsibilities
================
- Read and normalize `commander_cards.csv` (shared with the deck builder).
- Produce deterministic commander records with rich metadata (slug, colors,
  partner/background flags, theme tags, Scryfall image URLs).
- Cache the parsed catalog and invalidate on file timestamp changes.

The loader operates without pandas to keep the web layer light-weight and to
simplify unit testing. It honors the `CSV_FILES_DIR` environment variable via
`path_util.csv_dir()` just like the CLI builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple
import ast
import csv
import os
import re
from urllib.parse import quote

from path_util import csv_dir
from deck_builder.partner_background_utils import analyze_partner_background

__all__ = [
    "CommanderRecord",
    "CommanderCatalog",
    "load_commander_catalog",
    "clear_commander_catalog_cache",
    "find_commander_record",
    "normalized_restricted_labels",
    "shared_restricted_partner_label",
]


_COLOR_ALIAS = {
    "W": "W",
    "WHITE": "W",
    "U": "U",
    "BLUE": "U",
    "B": "B",
    "BLACK": "B",
    "R": "R",
    "RED": "R",
    "G": "G",
    "GREEN": "G",
    "C": "C",
    "COLORLESS": "C",
}
_WUBRG_ORDER: Tuple[str, ...] = ("W", "U", "B", "R", "G")
_SCYRFALL_BASE = "https://api.scryfall.com/cards/named?format=image"
_THEME_ESCAPE_PATTERN = re.compile(r"\\([+/\\-])")


@dataclass(frozen=True, slots=True)
class CommanderRecord:
    """Normalized commander row."""

    name: str
    face_name: str
    display_name: str
    slug: str
    color_identity: Tuple[str, ...]
    color_identity_key: str
    is_colorless: bool
    colors: Tuple[str, ...]
    mana_cost: str
    mana_value: Optional[float]
    type_line: str
    creature_types: Tuple[str, ...]
    oracle_text: str
    power: Optional[str]
    toughness: Optional[str]
    keywords: Tuple[str, ...]
    themes: Tuple[str, ...]
    theme_tokens: Tuple[str, ...]
    edhrec_rank: Optional[int]
    layout: str
    side: Optional[str]
    image_small_url: str
    image_normal_url: str
    partner_with: Tuple[str, ...]
    has_plain_partner: bool
    is_partner: bool
    supports_backgrounds: bool
    is_background: bool
    is_doctor: bool
    is_doctors_companion: bool
    restricted_partner_labels: Tuple[str, ...]
    search_haystack: str


@dataclass(frozen=True, slots=True)
class CommanderCatalog:
    """Cached commander catalog with lookup helpers."""

    source_path: Path
    etag: str
    mtime_ns: int
    size: int
    entries: Tuple[CommanderRecord, ...]
    by_slug: Mapping[str, CommanderRecord]

    def get(self, slug: str) -> Optional[CommanderRecord]:
        return self.by_slug.get(slug)


_CACHE: Dict[str, CommanderCatalog] = {}


def normalized_restricted_labels(record: CommanderRecord | object) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    raw_labels = getattr(record, "restricted_partner_labels", ()) or ()
    for label in raw_labels:
        text = str(label or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in labels:
            continue
        labels[key] = text
    return labels


def shared_restricted_partner_label(
    primary: CommanderRecord | object,
    candidate: CommanderRecord | object,
) -> Optional[str]:
    primary_labels = normalized_restricted_labels(primary)
    if not primary_labels:
        return None
    candidate_labels = normalized_restricted_labels(candidate)
    if not candidate_labels:
        return None
    for key, display in candidate_labels.items():
        if key in primary_labels:
            return display
    return None


def clear_commander_catalog_cache() -> None:
    """Clear the in-memory commander catalog cache (testing/support)."""

    _CACHE.clear()


def load_commander_catalog(
    source_path: str | os.PathLike[str] | None = None,
    *,
    force_reload: bool = False,
) -> CommanderCatalog:
    """Load (and cache) the commander catalog.

    Args:
        source_path: Optional path to override the default csv (mostly for tests).
        force_reload: When True, bypass cache even if the file is unchanged.
    """

    csv_path = _resolve_commander_path(source_path)
    key = str(csv_path)

    if not force_reload:
        cached = _CACHE.get(key)
        if cached and _is_cache_valid(csv_path, cached):
            return cached

    catalog = _build_catalog(csv_path)
    _CACHE[key] = catalog
    return catalog


def find_commander_record(name: str | None) -> CommanderRecord | None:
    """Return the first commander record matching the provided name.

    Matching is case-insensitive and considers display name, face name, raw name,
    and slug variants. Returns ``None`` when the commander cannot be located.
    """

    text = _clean_str(name)
    if not text:
        return None
    lowered = text.casefold()
    slug = _slugify(text)
    try:
        catalog = load_commander_catalog()
    except Exception:
        return None
    for record in catalog.entries:
        for candidate in (record.display_name, record.face_name, record.name):
            if candidate and candidate.casefold() == lowered:
                return record
        if record.slug == slug:
            return record
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _resolve_commander_path(source_path: str | os.PathLike[str] | None) -> Path:
    if source_path is not None:
        return Path(source_path).resolve()
    return (Path(csv_dir()) / "commander_cards.csv").resolve()


def _is_cache_valid(path: Path, cached: CommanderCatalog) -> bool:
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return False
    mtime_ns = getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000))
    if mtime_ns != cached.mtime_ns:
        return False
    return stat_result.st_size == cached.size


def _build_catalog(path: Path) -> CommanderCatalog:
    if not path.exists():
        raise FileNotFoundError(f"Commander CSV not found at {path}")

    entries: List[CommanderRecord] = []
    used_slugs: set[str] = set()

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Commander CSV missing header row")

        for index, row in enumerate(reader):
            try:
                record = _row_to_record(row, used_slugs)
            except Exception:
                continue
            entries.append(record)
            used_slugs.add(record.slug)

    stat_result = path.stat()
    mtime_ns = getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000))
    etag = f"{stat_result.st_size}-{mtime_ns}-{len(entries)}"
    frozen_entries = tuple(entries)
    by_slug = {record.slug: record for record in frozen_entries}
    return CommanderCatalog(
        source_path=path,
        etag=etag,
        mtime_ns=mtime_ns,
        size=stat_result.st_size,
        entries=frozen_entries,
        by_slug=by_slug,
    )


def _row_to_record(row: Mapping[str, object], used_slugs: Iterable[str]) -> CommanderRecord:
    name = _clean_str(row.get("name")) or "Unknown Commander"
    face_name = _clean_str(row.get("faceName"))
    display_name = face_name or name

    base_slug = _slugify(display_name)
    side = _clean_str(row.get("side"))
    if side and side.lower() not in {"", "a"}:
        candidate = f"{base_slug}-{side.lower()}"
    else:
        candidate = base_slug
    slug = _dedupe_slug(candidate, used_slugs)

    color_identity, is_colorless = _parse_color_identity(row.get("colorIdentity"))
    colors, _ = _parse_color_identity(row.get("colors"))
    mana_cost = _clean_str(row.get("manaCost"))
    mana_value = _parse_float(row.get("manaValue"))
    type_line = _clean_str(row.get("type"))
    creature_types = tuple(_parse_literal_list(row.get("creatureTypes")))
    oracle_text = _clean_multiline(row.get("text"))
    power = _clean_str(row.get("power")) or None
    toughness = _clean_str(row.get("toughness")) or None
    keywords = tuple(_split_to_list(row.get("keywords")))
    raw_themes = _parse_literal_list(row.get("themeTags"))
    themes = tuple(filter(None, (_clean_theme_label(theme) for theme in raw_themes)))
    theme_tokens = tuple(dict.fromkeys(t.lower() for t in themes if t))
    edhrec_rank = _parse_int(row.get("edhrecRank"))
    layout = _clean_str(row.get("layout")) or "normal"
    detection = analyze_partner_background(type_line, oracle_text, raw_themes)
    partner_with = detection.partner_with
    if not partner_with:
        partner_with = tuple(_parse_literal_list(row.get("partnerWith")))
    has_plain_partner = detection.has_plain_partner
    is_partner = detection.has_partner
    supports_backgrounds = detection.choose_background
    is_background = detection.is_background
    is_doctor = detection.is_doctor
    is_doctors_companion = detection.is_doctors_companion
    restricted_partner_labels = tuple(detection.restricted_partner_labels)

    image_small_url = _build_scryfall_url(display_name, "small")
    image_normal_url = _build_scryfall_url(display_name, "normal")
    search_haystack = _build_haystack(display_name, type_line, themes, creature_types, keywords, oracle_text)

    color_identity_key = "".join(color_identity) if color_identity else "C"

    return CommanderRecord(
        name=name,
        face_name=face_name,
        display_name=display_name,
        slug=slug,
        color_identity=color_identity,
        color_identity_key=color_identity_key,
        is_colorless=is_colorless,
        colors=colors,
        mana_cost=mana_cost,
        mana_value=mana_value,
        type_line=type_line,
        creature_types=creature_types,
        oracle_text=oracle_text,
        power=power,
        toughness=toughness,
        keywords=keywords,
        themes=themes,
        theme_tokens=theme_tokens,
        edhrec_rank=edhrec_rank,
        layout=layout,
        side=side or None,
        image_small_url=image_small_url,
        image_normal_url=image_normal_url,
        partner_with=partner_with,
    has_plain_partner=has_plain_partner,
        is_partner=is_partner,
        supports_backgrounds=supports_backgrounds,
        is_background=is_background,
        is_doctor=is_doctor,
        is_doctors_companion=is_doctors_companion,
        restricted_partner_labels=restricted_partner_labels,
        search_haystack=search_haystack,
    )


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_multiline(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if "\\r\\n" in text or "\\n" in text or "\\r" in text:
        text = (
            text.replace("\\r\\n", "\n")
            .replace("\\r", "\n")
            .replace("\\n", "\n")
        )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _parse_float(value: object) -> Optional[float]:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> Optional[int]:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_literal_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return [str(v).strip() for v in parsed if str(v).strip()]
    except Exception:
        pass
    parts = [part.strip() for part in text.replace(";", ",").split(",")]
    return [part for part in parts if part]


def _clean_theme_label(value: str) -> str:
    text = _clean_str(value)
    if not text:
        return ""
    text = text.replace("\ufeff", "")
    return _THEME_ESCAPE_PATTERN.sub(r"\1", text)


def _split_to_list(value: object) -> List[str]:
    text = _clean_str(value)
    if not text:
        return []
    parts = [part.strip() for part in text.split(",")]
    return [part for part in parts if part]

def _parse_color_identity(value: object) -> Tuple[Tuple[str, ...], bool]:
    text = _clean_str(value)
    if not text:
        return tuple(), True
    tokens = re.split(r"[\s,&/]+", text)
    colors: List[str] = []
    colorless_flag = False
    for token in tokens:
        if not token:
            continue
        mapped = _COLOR_ALIAS.get(token.upper())
        if mapped is None:
            continue
        if mapped == "C":
            colorless_flag = True
        else:
            if mapped not in colors:
                colors.append(mapped)
    ordered = tuple(color for color in _WUBRG_ORDER if color in colors)
    if ordered:
        return ordered, False
    return tuple(), True if colorless_flag or text.upper() in {"C", "COLORLESS"} else False


def _slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = normalized.replace("+", " plus ")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "commander"


def _dedupe_slug(initial: str, existing: Iterable[str]) -> str:
    base = initial or "commander"
    if base not in existing:
        return base
    counter = 2
    while f"{base}-{counter}" in existing:
        counter += 1
    return f"{base}-{counter}"


def _build_scryfall_url(name: str, version: str) -> str:
    encoded = quote(name, safe="")
    return f"{_SCYRFALL_BASE}&version={version}&exact={encoded}"


def _build_haystack(
    display_name: str,
    type_line: str,
    themes: Tuple[str, ...],
    creature_types: Tuple[str, ...],
    keywords: Tuple[str, ...],
    oracle_text: str,
) -> str:
    tokens: List[str] = []
    tokens.append(display_name.lower())
    if type_line:
        tokens.append(type_line.lower())
    if themes:
        tokens.extend(theme.lower() for theme in themes)
    if creature_types:
        tokens.extend(t.lower() for t in creature_types)
    if keywords:
        tokens.extend(k.lower() for k in keywords)
    if oracle_text:
        tokens.append(oracle_text.lower())
    return "|".join(t for t in tokens if t)
