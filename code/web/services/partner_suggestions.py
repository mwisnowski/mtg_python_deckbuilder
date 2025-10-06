"""Partner suggestion dataset loader and scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Optional, Sequence

from code.logging_util import get_logger

from deck_builder.combined_commander import CombinedCommander, PartnerMode, build_combined_commander
from deck_builder.suggestions import (
    PartnerSuggestionContext,
    ScoreResult,
    is_noise_theme,
    score_partner_candidate,
)
from deck_builder.color_identity_utils import canon_color_code, color_label_from_code
from deck_builder.partner_selection import normalize_lookup_name
from exceptions import CommanderPartnerError


LOGGER = get_logger(__name__)

_COLOR_NAME_MAP = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}

_MODE_DISPLAY = {
    PartnerMode.PARTNER.value: "Partner",
    PartnerMode.PARTNER_WITH.value: "Partner With",
    PartnerMode.BACKGROUND.value: "Choose a Background",
    PartnerMode.DOCTOR_COMPANION.value: "Doctor & Companion",
}

_NOTE_LABELS = {
    "partner_with_match": "Canonical Partner With pair",
    "background_compatible": "Ideal background match",
    "doctor_companion_match": "Doctor ↔ Companion pairing",
    "shared_partner_keyword": "Both commanders have Partner",
    "restricted_label_match": "Restricted partner label matches",
    "observed_pairing": "Popular pairing in exported decks",
}


def _to_tuple(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return tuple()
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return tuple(result)


def _normalize(value: str | None) -> str:
    return normalize_lookup_name(value)


def _color_code(identity: Iterable[str]) -> str:
    code = canon_color_code(tuple(identity))
    return code or "C"


def _color_label(identity: Iterable[str]) -> str:
    return color_label_from_code(_color_code(identity))


def _mode_label(mode: PartnerMode | str | None) -> str:
    if isinstance(mode, PartnerMode):
        return _MODE_DISPLAY.get(mode.value, mode.value)
    if isinstance(mode, str):
        return _MODE_DISPLAY.get(mode, mode.title())
    return "Partner Mechanics"


@dataclass(frozen=True)
class CommanderEntry:
    """Commander metadata extracted from the partner synergy dataset."""

    key: str
    name: str
    display_name: str
    payload: Mapping[str, Any]
    partner_payload: Mapping[str, Any]
    color_identity: tuple[str, ...]
    themes: tuple[str, ...]
    role_tags: tuple[str, ...]

    def to_source(self) -> SimpleNamespace:
        partner = self.partner_payload
        partner_with = _to_tuple(partner.get("partner_with"))
        supports_backgrounds = bool(partner.get("supports_backgrounds") or partner.get("choose_background"))
        is_partner = bool(partner.get("has_partner") or partner.get("has_plain_partner"))
        is_background = bool(partner.get("is_background"))
        is_doctor = bool(partner.get("is_doctor"))
        is_companion = bool(partner.get("is_doctors_companion"))
        restricted_labels = _to_tuple(partner.get("restricted_partner_labels"))
        return SimpleNamespace(
            name=self.name,
            display_name=self.display_name,
            color_identity=self.color_identity,
            colors=self.color_identity,
            themes=self.themes,
            theme_tags=self.themes,
            raw_tags=self.themes,
            partner_with=partner_with,
            supports_backgrounds=supports_backgrounds,
            is_partner=is_partner,
            is_background=is_background,
            is_doctor=is_doctor,
            is_doctors_companion=is_companion,
            restricted_partner_labels=restricted_labels,
            oracle_text="",
            type_line="",
        )

    @property
    def canonical(self) -> str:
        return self.key


@dataclass(frozen=True)
class PartnerSuggestionResult:
    """Structured partner suggestions grouped by mode."""

    commander: str
    display_name: str
    canonical: str
    metadata: Mapping[str, Any]
    by_mode: Mapping[str, list[dict[str, Any]]]
    total: int

    def flatten(
        self,
        partner_names: Iterable[str],
        background_names: Iterable[str],
        *,
        visible_limit: int = 3,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        partner_allowed = {_normalize(name) for name in partner_names if name}
        background_allowed = {_normalize(name) for name in background_names if name}
        ordered_modes = [
            PartnerMode.PARTNER_WITH.value,
            PartnerMode.PARTNER.value,
            PartnerMode.DOCTOR_COMPANION.value,
            PartnerMode.BACKGROUND.value,
        ]
        visible: list[dict[str, Any]] = []
        hidden: list[dict[str, Any]] = []
        for mode_key in ordered_modes:
            suggestions = self.by_mode.get(mode_key, [])
            for suggestion in suggestions:
                name_key = _normalize(suggestion.get("name"))
                if mode_key == PartnerMode.BACKGROUND.value:
                    if name_key not in background_allowed:
                        continue
                else:
                    if name_key not in partner_allowed:
                        continue
                target = visible if len(visible) < visible_limit else hidden
                target.append(suggestion)
        return visible, hidden


class PartnerSuggestionDataset:
    """Cached partner synergy dataset accessor."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._payload: Optional[dict[str, Any]] = None
        self._metadata: dict[str, Any] = {}
        self._entries: dict[str, CommanderEntry] = {}
        self._lookup: dict[str, CommanderEntry] = {}
        self._pairing_counts: dict[tuple[str, str, str], int] = {}
        self._context: PartnerSuggestionContext = PartnerSuggestionContext()
        self._mtime_ns: int = -1

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    @property
    def context(self) -> PartnerSuggestionContext:
        return self._context

    def ensure_loaded(self, *, force: bool = False) -> None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        stat = self.path.stat()
        if not force and self._payload is not None and stat.st_mtime_ns == self._mtime_ns:
            return
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        if not isinstance(raw, dict):
            raise ValueError("partner synergy dataset is not a JSON object")

        commanders = raw.get("commanders") or {}
        if not isinstance(commanders, Mapping):
            raise ValueError("commanders section missing in partner synergy dataset")

        entries: dict[str, CommanderEntry] = {}
        lookup: dict[str, CommanderEntry] = {}
        for key, payload in commanders.items():
            if not isinstance(payload, Mapping):
                continue
            display = str(payload.get("display_name") or payload.get("name") or key or "").strip()
            if not display:
                continue
            name = str(payload.get("name") or display)
            partner_payload = payload.get("partner") or {}
            if not isinstance(partner_payload, Mapping):
                partner_payload = {}
            color_identity = _to_tuple(payload.get("color_identity"))
            themes = tuple(
                theme for theme in _to_tuple(payload.get("themes")) if not is_noise_theme(theme)
            )
            role_tags = _to_tuple(payload.get("role_tags"))
            entry = CommanderEntry(
                key=str(key),
                name=name,
                display_name=display,
                payload=payload,
                partner_payload=partner_payload,
                color_identity=color_identity,
                themes=themes,
                role_tags=role_tags,
            )
            entries[entry.canonical] = entry
            aliases = {
                _normalize(entry.canonical),
                _normalize(entry.display_name),
                _normalize(entry.name),
            }
            for alias in aliases:
                if alias and alias not in lookup:
                    lookup[alias] = entry

        pairings: dict[tuple[str, str, str], int] = {}
        pairing_block = raw.get("pairings") or {}
        records = pairing_block.get("records") if isinstance(pairing_block, Mapping) else None
        if isinstance(records, Sequence):
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                mode = str(record.get("mode") or "unknown").strip().replace("-", "_")
                primary_key = _normalize(record.get("primary_canonical") or record.get("primary"))
                secondary_key = _normalize(record.get("secondary_canonical") or record.get("secondary"))
                if not mode or not primary_key or not secondary_key:
                    continue
                try:
                    count = int(record.get("count", 0))
                except Exception:
                    count = 0
                if count <= 0:
                    continue
                pairings[(mode, primary_key, secondary_key)] = count
                pairings[(mode, secondary_key, primary_key)] = count

        self._payload = raw
        self._metadata = dict(raw.get("metadata") or {})
        self._entries = entries
        self._lookup = lookup
        self._pairing_counts = pairings
        self._context = PartnerSuggestionContext.from_dataset(raw)
        self._mtime_ns = stat.st_mtime_ns

    def lookup(self, name: str) -> Optional[CommanderEntry]:
        key = _normalize(name)
        if not key:
            return None
        entry = self._lookup.get(key)
        if entry is not None:
            return entry
        return self._entries.get(key)

    def entries(self) -> Iterable[CommanderEntry]:
        return self._entries.values()

    def pairing_count(self, mode: PartnerMode, primary: CommanderEntry, secondary: CommanderEntry) -> int:
        return int(self._pairing_counts.get((mode.value, primary.canonical, secondary.canonical), 0))

    def build_combined(
        self,
        primary: CommanderEntry,
        candidate: CommanderEntry,
        mode: PartnerMode,
    ) -> CombinedCommander:
        primary_src = primary.to_source()
        candidate_src = candidate.to_source()
        return build_combined_commander(primary_src, candidate_src, mode)


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_PATH = (ROOT_DIR / "config" / "analytics" / "partner_synergy.json").resolve()
_DATASET_ENV_VAR = "PARTNER_SUGGESTIONS_DATASET"

_ENV_OVERRIDE = os.getenv(_DATASET_ENV_VAR)
_DATASET_PATH: Path = Path(_ENV_OVERRIDE).expanduser().resolve() if _ENV_OVERRIDE else DEFAULT_DATASET_PATH
_DATASET_CACHE: Optional[PartnerSuggestionDataset] = None
_DATASET_LOCK = Lock()
_DATASET_REFRESH_ATTEMPTED = False


def configure_dataset_path(path: str | Path | None) -> None:
    """Override the dataset path (primarily for tests)."""

    global _DATASET_PATH, _DATASET_CACHE
    if path is None:
        _DATASET_PATH = DEFAULT_DATASET_PATH
        os.environ.pop(_DATASET_ENV_VAR, None)
    else:
        resolved = Path(path).expanduser().resolve()
        _DATASET_PATH = resolved
        os.environ[_DATASET_ENV_VAR] = str(resolved)
    _DATASET_CACHE = None


def load_dataset(*, force: bool = False, refresh: bool = False) -> Optional[PartnerSuggestionDataset]:
    """Return the cached dataset, reloading if needed.

    Args:
        force: When True, bypass the in-memory cache and reload the dataset from disk.
        refresh: When True, attempt to regenerate the dataset before loading. This
            resets the "already tried" guard so manual refresh actions can retry
            regeneration after an earlier failure.
    """

    global _DATASET_CACHE, _DATASET_REFRESH_ATTEMPTED
    with _DATASET_LOCK:
        if refresh:
            _DATASET_REFRESH_ATTEMPTED = False
            _DATASET_CACHE = None

        dataset = _DATASET_CACHE
        if dataset is None or force or refresh:
            dataset = PartnerSuggestionDataset(_DATASET_PATH)
        try:
            dataset.ensure_loaded(force=force or refresh or dataset is not _DATASET_CACHE)
        except FileNotFoundError:
            LOGGER.debug("partner suggestions dataset missing at %s", _DATASET_PATH)
            # Attempt to materialize the dataset automatically when using the default path.
            allow_auto_refresh = (
                _DATASET_PATH == DEFAULT_DATASET_PATH
                and (refresh or not _DATASET_REFRESH_ATTEMPTED)
            )
            if allow_auto_refresh:
                _DATASET_REFRESH_ATTEMPTED = True
                try:
                    from .orchestrator import _maybe_refresh_partner_synergy  # type: ignore

                    _maybe_refresh_partner_synergy(None, force=True)
                except Exception as refresh_exc:  # pragma: no cover - best-effort
                    LOGGER.debug(
                        "partner suggestions auto-refresh failed: %s",
                        refresh_exc,
                        exc_info=True,
                    )
                try:
                    dataset.ensure_loaded(force=True)
                except FileNotFoundError:
                    LOGGER.debug(
                        "partner suggestions dataset still missing after auto-refresh",
                        exc_info=True,
                    )
                    if refresh:
                        _DATASET_REFRESH_ATTEMPTED = False
                    _DATASET_CACHE = None
                    return None
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.warning("partner suggestions dataset failed after auto-refresh", exc_info=exc)
                    if refresh:
                        _DATASET_REFRESH_ATTEMPTED = False
                    _DATASET_CACHE = None
                    return None
            else:
                _DATASET_CACHE = None
                return None
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("partner suggestions dataset failed to load", exc_info=exc)
            _DATASET_CACHE = None
            return None
        _DATASET_CACHE = dataset
        return dataset


def _shared_restriction_label(primary: CommanderEntry, candidate: CommanderEntry) -> Optional[str]:
    primary_labels = set(_to_tuple(primary.partner_payload.get("restricted_partner_labels")))
    candidate_labels = set(_to_tuple(candidate.partner_payload.get("restricted_partner_labels")))
    shared = primary_labels & candidate_labels
    if not shared:
        return None
    return sorted(shared, key=str.casefold)[0]


def _color_delta(primary: CommanderEntry, combined: CombinedCommander) -> dict[str, list[str]]:
    primary_colors = {color.upper() for color in primary.color_identity}
    combined_colors = {color.upper() for color in combined.color_identity or ()}
    added = [
        _COLOR_NAME_MAP.get(color, color)
        for color in sorted(combined_colors - primary_colors)
    ]
    removed = [
        _COLOR_NAME_MAP.get(color, color)
        for color in sorted(primary_colors - combined_colors)
    ]
    return {
        "added": added,
        "removed": removed,
    }


def _reason_summary(
    result: ScoreResult,
    shared_themes: Sequence[str],
    pairing_count: int,
    color_delta: Mapping[str, Sequence[str]],
) -> tuple[str, list[str]]:
    parts: list[str] = []
    details: list[str] = []
    score_percent = int(round(max(0.0, min(1.0, result.score)) * 100))
    parts.append(f"{score_percent}% match")
    if shared_themes:
        label = ", ".join(shared_themes[:2])
        parts.append(f"Shared themes: {label}")
    if pairing_count > 0:
        parts.append(f"Seen in {pairing_count} decks")
    for note in result.notes:
        label = _NOTE_LABELS.get(note)
        if label and label not in details:
            details.append(label)
    if not details and pairing_count > 0:
        details.append(f"Observed together {pairing_count} time(s)")
    added = color_delta.get("added") or []
    if added:
        details.append("Adds " + ", ".join(added))
    overlap_component = float(result.components.get("overlap", 0.0))
    if overlap_component >= 0.35 and len(parts) < 3:
        percent = int(round(overlap_component * 100))
        details.append(f"Theme overlap {percent}%")
    summary = " • ".join(parts[:3])
    return summary, details


def _build_suggestion_payload(
    primary: CommanderEntry,
    candidate: CommanderEntry,
    mode: PartnerMode,
    result: ScoreResult,
    combined: CombinedCommander,
    pairing_count: int,
) -> dict[str, Any]:
    shared_themes = sorted(
        {
            theme
            for theme in primary.themes
            if theme in candidate.themes and not is_noise_theme(theme)
        },
        key=str.casefold,
    )
    color_delta = _color_delta(primary, combined)
    summary, details = _reason_summary(result, shared_themes, pairing_count, color_delta)
    suggestion = {
        "name": candidate.display_name,
        "mode": mode.value,
        "mode_label": _mode_label(mode),
        "score": max(0.0, min(1.0, float(result.score))),
        "score_percent": int(round(max(0.0, min(1.0, float(result.score))) * 100)),
        "score_components": dict(result.components),
        "notes": list(result.notes),
        "shared_themes": shared_themes,
        "candidate_themes": list(candidate.themes),
        "theme_tags": list(combined.theme_tags or ()),
        "summary": summary,
        "reasons": details,
        "pairing_count": pairing_count,
        "color_code": combined.color_code or _color_code(combined.color_identity or ()),
        "color_label": combined.color_label or _color_label(combined.color_identity or ()),
        "color_identity": list(combined.color_identity or ()),
        "candidate_colors": list(candidate.color_identity),
        "primary_colors": list(combined.primary_color_identity or primary.color_identity),
        "secondary_colors": list(combined.secondary_color_identity or candidate.color_identity),
        "color_delta": color_delta,
        "restriction_label": _shared_restriction_label(primary, candidate),
    }
    if combined.secondary_name:
        suggestion["secondary_name"] = combined.secondary_name
    suggestion["preview"] = {
        "primary_name": combined.primary_name,
        "secondary_name": combined.secondary_name,
        "partner_mode": mode.value,
        "partner_mode_label": _mode_label(mode),
        "color_label": suggestion["color_label"],
        "color_code": suggestion["color_code"],
        "theme_tags": list(combined.theme_tags or ()),
        "secondary_role_label": getattr(combined, "secondary_name", None) and (
            "Background" if mode is PartnerMode.BACKGROUND else (
                "Doctor's Companion" if mode is PartnerMode.DOCTOR_COMPANION else "Partner commander"
            )
        ),
    }
    return suggestion


def get_partner_suggestions(
    commander_name: str,
    *,
    limit_per_mode: int = 5,
    include_modes: Optional[Sequence[PartnerMode]] = None,
    min_score: float = 0.15,
    refresh_dataset: bool = False,
) -> Optional[PartnerSuggestionResult]:
    dataset = load_dataset(force=refresh_dataset, refresh=refresh_dataset)
    if dataset is None:
        return None

    primary_entry = dataset.lookup(commander_name)
    if primary_entry is None:
        return PartnerSuggestionResult(
            commander=commander_name,
            display_name=commander_name,
            canonical=_normalize(commander_name) or commander_name,
            metadata=dataset.metadata,
            by_mode={},
            total=0,
        )

    allowed_modes = set(include_modes) if include_modes else {
        PartnerMode.PARTNER,
        PartnerMode.PARTNER_WITH,
        PartnerMode.BACKGROUND,
        PartnerMode.DOCTOR_COMPANION,
    }
    grouped: dict[str, list[dict[str, Any]]] = {
        PartnerMode.PARTNER.value: [],
        PartnerMode.PARTNER_WITH.value: [],
        PartnerMode.BACKGROUND.value: [],
        PartnerMode.DOCTOR_COMPANION.value: [],
    }

    total = 0
    primary_source = primary_entry.payload
    context = dataset.context

    for candidate_entry in dataset.entries():
        if candidate_entry.canonical == primary_entry.canonical:
            continue
        try:
            result = score_partner_candidate(primary_source, candidate_entry.payload, context=context)
        except Exception:  # pragma: no cover - defensive scoring guard
            continue
        mode = result.mode
        if mode is PartnerMode.NONE or mode not in allowed_modes:
            continue
        if result.score < min_score:
            continue
        try:
            combined = dataset.build_combined(primary_entry, candidate_entry, mode)
        except CommanderPartnerError:
            continue
        except Exception:  # pragma: no cover - defensive
            continue
        pairing_count = dataset.pairing_count(mode, primary_entry, candidate_entry)
        suggestion = _build_suggestion_payload(primary_entry, candidate_entry, mode, result, combined, pairing_count)
        grouped[mode.value].append(suggestion)
        total += 1

    for mode_key, suggestions in grouped.items():
        suggestions.sort(key=lambda item: (-float(item.get("score", 0.0)), item.get("name", "").casefold()))
        if limit_per_mode > 0:
            grouped[mode_key] = suggestions[:limit_per_mode]

    return PartnerSuggestionResult(
        commander=primary_entry.display_name,
        display_name=primary_entry.display_name,
        canonical=primary_entry.canonical,
        metadata=dataset.metadata,
        by_mode=grouped,
        total=sum(len(s) for s in grouped.values()),
    )
