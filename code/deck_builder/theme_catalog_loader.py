"""Lightweight loader for the supplemental theme catalog CSV."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Tuple

import logging_util

LOGGER = logging_util.get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = ROOT / "config" / "themes" / "theme_catalog.csv"
JSON_FALLBACK_PATH = ROOT / "config" / "themes" / "theme_list.json"
REQUIRED_COLUMNS = {"theme", "commander_count", "card_count"}


@dataclass(frozen=True)
class ThemeCatalogEntry:
    """Single row from the supplemental theme catalog."""

    theme: str
    commander_count: int
    card_count: int

    @property
    def source_count(self) -> int:
        return self.commander_count + self.card_count


def _resolve_catalog_path(override: str | os.PathLike[str] | None) -> Path:
    if override:
        return Path(override).resolve()
    env_override = os.environ.get("THEME_CATALOG_PATH")
    if env_override:
        return Path(env_override).resolve()
    return DEFAULT_CATALOG_PATH


def _parse_metadata(line: str) -> Tuple[str, dict[str, str]]:
    version = "unknown"
    meta: dict[str, str] = {}
    cleaned = line.lstrip("#").strip()
    if not cleaned:
        return version, meta
    for token in cleaned.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        meta[key] = value
        if key == "version":
            version = value
    return version, meta


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return 0
    return int(text)


def load_theme_catalog(
    catalog_path: str | os.PathLike[str] | None = None,
) -> tuple[list[ThemeCatalogEntry], str]:
    """Load the supplemental theme catalog with memoization.

    Args:
        catalog_path: Optional override path. Defaults to ``config/themes/theme_catalog.csv``
            or the ``THEME_CATALOG_PATH`` environment variable.

    Returns:
        A tuple of ``(entries, version)`` where ``entries`` is a list of
        :class:`ThemeCatalogEntry` and ``version`` is the parsed catalog version.
    """

    resolved = _resolve_catalog_path(catalog_path)
    mtime = 0.0
    try:
        mtime = resolved.stat().st_mtime
    except FileNotFoundError:
        pass
    entries, version = _load_catalog_cached(str(resolved), mtime)
    if entries:
        return list(entries), version
    # Fallback to JSON catalog when CSV export unavailable.
    fallback_entries, fallback_version = _load_json_catalog()
    if fallback_entries:
        return list(fallback_entries), fallback_version
    return list(entries), version


@lru_cache(maxsize=4)
def _load_catalog_cached(path_str: str, mtime: float) -> tuple[tuple[ThemeCatalogEntry, ...], str]:
    path = Path(path_str)
    if not path.exists():
        LOGGER.warning("theme_catalog_missing path=%s", path)
        return tuple(), "unknown"

    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        version = "unknown"
        if first_line.startswith("#"):
            version, _ = _parse_metadata(first_line)
        else:
            handle.seek(0)

        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            LOGGER.info("theme_catalog_loaded size=0 version=%s path=%s", version, path)
            return tuple(), version

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(
                "theme_catalog.csv missing required columns: " + ", ".join(sorted(missing))
            )

        entries: list[ThemeCatalogEntry] = []
        for row in reader:
            if not row:
                continue
            theme = str(row.get("theme", "")).strip()
            if not theme:
                continue
            try:
                commander = _to_int(row.get("commander_count"))
                card = _to_int(row.get("card_count"))
            except ValueError as exc:  # pragma: no cover - defensive, should not happen
                raise ValueError(f"Invalid numeric values in theme catalog for theme '{theme}'") from exc
            entries.append(ThemeCatalogEntry(theme=theme, commander_count=commander, card_count=card))

    LOGGER.info("theme_catalog_loaded size=%s version=%s path=%s", len(entries), version, path)
    return tuple(entries), version


def _load_json_catalog() -> tuple[tuple[ThemeCatalogEntry, ...], str]:
    if not JSON_FALLBACK_PATH.exists():
        return tuple(), "unknown"
    try:
        mtime = JSON_FALLBACK_PATH.stat().st_mtime
    except Exception:  # pragma: no cover - stat failures
        mtime = 0.0
    return _load_json_catalog_cached(str(JSON_FALLBACK_PATH), mtime)


@lru_cache(maxsize=2)
def _load_json_catalog_cached(path_str: str, mtime: float) -> tuple[tuple[ThemeCatalogEntry, ...], str]:
    path = Path(path_str)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - IO edge cases
        LOGGER.warning("theme_catalog_json_read_error path=%s error=%s", path, exc)
        return tuple(), "unknown"
    if not raw_text.strip():
        return tuple(), "unknown"
    try:
        payload = json.loads(raw_text)
    except Exception as exc:  # pragma: no cover - malformed JSON
        LOGGER.warning("theme_catalog_json_parse_error path=%s error=%s", path, exc)
        return tuple(), "unknown"
    themes = _iter_json_themes(payload)
    entries = tuple(themes)
    if not entries:
        return tuple(), "unknown"
    version = _extract_json_version(payload)
    LOGGER.info("theme_catalog_loaded_json size=%s version=%s path=%s", len(entries), version, path)
    return entries, version


def _iter_json_themes(payload: object) -> Iterable[ThemeCatalogEntry]:
    if not isinstance(payload, dict):
        LOGGER.warning("theme_catalog_json_invalid_root type=%s", type(payload).__name__)
        return tuple()
    try:
        from type_definitions_theme_catalog import ThemeCatalog  # pragma: no cover - primary import path
    except ImportError:  # pragma: no cover - fallback when running as package
        from code.type_definitions_theme_catalog import ThemeCatalog

    try:
        catalog = ThemeCatalog.model_validate(payload)
    except Exception as exc:  # pragma: no cover - validation errors
        LOGGER.warning("theme_catalog_json_validate_error error=%s", exc)
        return tuple()

    for theme in catalog.themes:
        commander_count = len(theme.example_commanders or [])
        # Prefer synergy count, fall back to example cards, ensure non-negative.
        inferred_card_count = max(len(theme.synergies or []), len(theme.example_cards or []))
        yield ThemeCatalogEntry(
            theme=theme.theme,
            commander_count=int(commander_count),
            card_count=int(inferred_card_count),
        )


def _extract_json_version(payload: object) -> str:
    if not isinstance(payload, dict):
        return "json"
    meta = payload.get("metadata_info")
    if isinstance(meta, dict):
        version = meta.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    # Fallback to catalog hash if available
    recorded = None
    if isinstance(meta, dict):
        recorded = meta.get("catalog_hash")
    if isinstance(recorded, str) and recorded.strip():
        return recorded.strip()
    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        version = provenance.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    return "json"


__all__ = ["ThemeCatalogEntry", "load_theme_catalog"]
