"""Partner suggestion scoring helpers.

This module provides a scoring helper that ranks potential partner/background
pairings for a selected primary commander. It consumes the normalized metadata
emitted by ``build_partner_suggestions.py`` (themes, role tags, partner flags,
and pairing telemetry) and blends several weighted components:

* Shared theme overlap (normalized Jaccard/role-aware) – baseline synergy.
* Theme adjacency (deck export co-occurrence + curated overrides).
* Color compatibility (prefers compact color changes).
* Mechanic affinity (Partner With, Doctor/Companion, Background matches).
* Penalties (illegal configurations, missing tags, restricted conflicts).

Weights are mode-specific so future tuning can adjust emphasis without
rewriting the algorithm. The public ``score_partner_candidate`` helper returns
both the aggregate score and a component breakdown for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Mapping, MutableMapping, Sequence

from .combined_commander import PartnerMode

__all__ = [
    "PartnerSuggestionContext",
    "ScoreWeights",
    "ScoreResult",
    "MODE_WEIGHTS",
    "score_partner_candidate",
    "is_noise_theme",
]


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_token(value: str | None) -> str:
    return _clean_str(value).casefold()


def _commander_name(payload: Mapping[str, object]) -> str:
    name = _clean_str(payload.get("display_name")) or _clean_str(payload.get("name"))
    return name or "Unknown Commander"


def _commander_key(payload: Mapping[str, object]) -> str:
    return _normalize_token(_commander_name(payload))


def _sequence(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if raw is None:
        return tuple()
    if isinstance(raw, (list, tuple)):
        return tuple(_clean_str(item) for item in raw if _clean_str(item))
    return tuple(filter(None, (_clean_str(raw),)))


_EXCLUDED_THEME_TOKENS = {
    "legends matter",
    "historics matter",
    "partner",
    "partner - survivors",
}


def _theme_should_be_excluded(theme: str) -> bool:
    token = _normalize_token(theme)
    if not token:
        return False
    if token in _EXCLUDED_THEME_TOKENS:
        return True
    return "kindred" in token


def is_noise_theme(theme: str | None) -> bool:
    """Return True when the provided theme is considered too generic/noisy.

    The partner suggestion UI should suppress these themes from overlap summaries to
    keep recommendations focused on distinctive archetypes.
    """

    if theme is None:
        return False
    return _theme_should_be_excluded(theme)


def _theme_sequence(payload: Mapping[str, object], key: str = "themes") -> tuple[str, ...]:
    return tuple(
        theme
        for theme in _sequence(payload, key)
        if not _theme_should_be_excluded(theme)
    )


def _normalize_string_set(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    collected: list[str] = []
    for value in values:
        token = _clean_str(value)
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        collected.append(token)
    return tuple(collected)


@dataclass(frozen=True)
class ScoreWeights:
    """Weight multipliers for each scoring component."""

    overlap: float
    synergy: float
    color: float
    affinity: float
    penalty: float


@dataclass(frozen=True)
class ScoreResult:
    """Result returned by :func:`score_partner_candidate`."""

    score: float
    mode: PartnerMode
    components: Mapping[str, float]
    notes: tuple[str, ...]
    weights: ScoreWeights


class PartnerSuggestionContext:
    """Container for suggestion dataset fragments used during scoring."""

    def __init__(
        self,
        *,
        theme_cooccurrence: Mapping[str, Mapping[str, int]] | None = None,
        pairing_counts: Mapping[tuple[str, str, str], int] | None = None,
        curated_synergy: Mapping[tuple[str, str], float] | None = None,
    ) -> None:
        self._theme_cooccurrence: Dict[str, Dict[str, float]] = {}
        self._pairing_counts: Dict[tuple[str, str, str], float] = {}
        self._curated_synergy: Dict[tuple[str, str], float] = {}

        max_co = 0
        if theme_cooccurrence:
            for theme, neighbors in theme_cooccurrence.items():
                theme_key = _normalize_token(theme)
                if not theme_key:
                    continue
                store: Dict[str, float] = {}
                for other, count in neighbors.items():
                    other_key = _normalize_token(other)
                    if not other_key:
                        continue
                    value = float(count or 0)
                    if value <= 0:
                        continue
                    store[other_key] = value
                    max_co = max(max_co, value)
                if store:
                    self._theme_cooccurrence[theme_key] = store
        self._theme_co_max = max(max_co, 1.0)

        max_pair = 0
        if pairing_counts:
            for key, count in pairing_counts.items():
                if not isinstance(key, tuple) or len(key) != 3:
                    continue
                mode, primary, secondary = key
                norm_key = (
                    _normalize_token(mode),
                    _normalize_token(primary),
                    _normalize_token(secondary),
                )
                value = float(count or 0)
                if value <= 0:
                    continue
                self._pairing_counts[norm_key] = value
                # Store symmetric entry to simplify lookups.
                symmetric = (
                    _normalize_token(mode),
                    _normalize_token(secondary),
                    _normalize_token(primary),
                )
                self._pairing_counts[symmetric] = value
                max_pair = max(max_pair, value)
        self._pairing_max = max(max_pair, 1.0)

        if curated_synergy:
            for key, value in curated_synergy.items():
                if not isinstance(key, tuple) or len(key) != 2:
                    continue
                primary, secondary = key
                normalized = (
                    _normalize_token(primary),
                    _normalize_token(secondary),
                )
                if value is None:
                    continue
                magnitude = max(0.0, float(value))
                if magnitude <= 0:
                    continue
                self._curated_synergy[normalized] = min(1.0, magnitude)
                self._curated_synergy[(normalized[1], normalized[0])] = min(1.0, magnitude)

    @classmethod
    def from_dataset(cls, payload: Mapping[str, object] | None) -> "PartnerSuggestionContext":
        if not payload:
            return cls()

        themes_raw = payload.get("themes")
        theme_cooccurrence: Dict[str, Dict[str, int]] = {}
        if isinstance(themes_raw, Mapping):
            for theme_key, entry in themes_raw.items():
                co = entry.get("co_occurrence") if isinstance(entry, Mapping) else None
                if not isinstance(co, Mapping):
                    continue
                inner: Dict[str, int] = {}
                for other, info in co.items():
                    if isinstance(info, Mapping):
                        count = info.get("count")
                    else:
                        count = info
                    try:
                        inner[str(other)] = int(count)
                    except Exception:
                        continue
                theme_cooccurrence[str(theme_key)] = inner

        pairings = payload.get("pairings")
        pairing_counts: Dict[tuple[str, str, str], int] = {}
        if isinstance(pairings, Mapping):
            records = pairings.get("records")
            if isinstance(records, Sequence):
                for entry in records:
                    if not isinstance(entry, Mapping):
                        continue
                    mode = str(entry.get("mode", "unknown"))
                    primary = str(entry.get("primary_canonical") or entry.get("primary") or "")
                    secondary = str(entry.get("secondary_canonical") or entry.get("secondary") or "")
                    if not primary or not secondary:
                        continue
                    try:
                        count = int(entry.get("count", 0))
                    except Exception:
                        continue
                    pairing_counts[(mode, primary, secondary)] = count

        curated = payload.get("curated_overrides")
        curated_synergy: Dict[tuple[str, str], float] = {}
        if isinstance(curated, Mapping):
            entries = curated.get("entries")
            if isinstance(entries, Mapping):
                for raw_key, raw_value in entries.items():
                    if not isinstance(raw_key, str):
                        continue
                    parts = [part.strip() for part in raw_key.split("::") if part.strip()]
                    if len(parts) != 2:
                        continue
                    try:
                        magnitude = float(raw_value)
                    except Exception:
                        continue
                    curated_synergy[(parts[0], parts[1])] = magnitude

        return cls(
            theme_cooccurrence=theme_cooccurrence,
            pairing_counts=pairing_counts,
            curated_synergy=curated_synergy,
        )

    @lru_cache(maxsize=256)
    def theme_synergy(self, theme_a: str, theme_b: str) -> float:
        key_a = _normalize_token(theme_a)
        key_b = _normalize_token(theme_b)
        if not key_a or not key_b or key_a == key_b:
            return 0.0
        co = self._theme_cooccurrence.get(key_a, {})
        value = co.get(key_b, 0.0)
        normalized = value / self._theme_co_max
        curated = self._curated_synergy.get((key_a, key_b), 0.0)
        return max(0.0, min(1.0, max(normalized, curated)))

    @lru_cache(maxsize=128)
    def pairing_strength(self, mode: PartnerMode, primary: str, secondary: str) -> float:
        key = (
            mode.value,
            _normalize_token(primary),
            _normalize_token(secondary),
        )
        value = self._pairing_counts.get(key, 0.0)
        return max(0.0, min(1.0, value / self._pairing_max))


DEFAULT_WEIGHTS = ScoreWeights(
    overlap=0.45,
    synergy=0.25,
    color=0.15,
    affinity=0.10,
    penalty=0.20,
)


MODE_WEIGHTS: Mapping[PartnerMode, ScoreWeights] = {
    PartnerMode.PARTNER: DEFAULT_WEIGHTS,
    PartnerMode.PARTNER_WITH: ScoreWeights(overlap=0.40, synergy=0.20, color=0.10, affinity=0.20, penalty=0.25),
    PartnerMode.BACKGROUND: ScoreWeights(overlap=0.50, synergy=0.30, color=0.10, affinity=0.10, penalty=0.25),
    PartnerMode.DOCTOR_COMPANION: ScoreWeights(overlap=0.30, synergy=0.20, color=0.10, affinity=0.30, penalty=0.25),
    PartnerMode.NONE: DEFAULT_WEIGHTS,
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def score_partner_candidate(
    primary: Mapping[str, object],
    candidate: Mapping[str, object],
    *,
    mode: PartnerMode | str | None = None,
    context: PartnerSuggestionContext | None = None,
) -> ScoreResult:
    """Score a partner/background candidate for the provided primary.

    Args:
        primary: Commander metadata dictionary (as produced by the dataset).
        candidate: Potential partner/background metadata dictionary.
        mode: Desired partner mode (auto-detected when omitted).
        context: Optional suggestion context providing theme/pairing statistics.

    Returns:
        ScoreResult with aggregate score ``0.0`` – ``1.0`` and component details.
    """

    mode = _resolve_mode(primary, candidate, mode)
    weights = MODE_WEIGHTS.get(mode, DEFAULT_WEIGHTS)
    ctx = context or PartnerSuggestionContext()

    overlap = _theme_overlap(primary, candidate)
    synergy = _theme_synergy(primary, candidate, ctx)
    color_value = _color_compatibility(primary, candidate)
    affinity, affinity_notes, affinity_penalties = _mechanic_affinity(primary, candidate, mode, ctx)
    penalty_value, penalty_notes = _collect_penalties(primary, candidate, mode, affinity_penalties)

    positive_total = weights.overlap + weights.synergy + weights.color + weights.affinity
    positive_total = positive_total or 1.0
    blended = (
        weights.overlap * overlap
        + weights.synergy * synergy
        + weights.color * color_value
        + weights.affinity * affinity
    ) / positive_total

    adjusted = blended - weights.penalty * penalty_value
    final_score = _clamp(adjusted)

    notes = tuple(note for note in (*affinity_notes, *penalty_notes) if note)
    components = {
        "overlap": overlap,
        "synergy": synergy,
        "color": color_value,
        "affinity": affinity,
        "penalty": penalty_value,
    }

    return ScoreResult(
        score=final_score,
        mode=mode,
        components=components,
        notes=notes,
        weights=weights,
    )


def _resolve_mode(
    primary: Mapping[str, object],
    candidate: Mapping[str, object],
    provided: PartnerMode | str | None,
) -> PartnerMode:
    if isinstance(provided, PartnerMode):
        return provided
    if isinstance(provided, str) and provided:
        normalized = provided.replace("-", "_").strip().casefold()
        for mode in PartnerMode:
            if mode.value == normalized:
                return mode

    partner_meta_primary = _partner_meta(primary)
    partner_meta_candidate = _partner_meta(candidate)
    candidate_name = _commander_name(candidate)

    if partner_meta_candidate.get("is_background"):
        return PartnerMode.BACKGROUND
    partner_with = {
        _normalize_token(name)
        for name in partner_meta_primary.get("partner_with", [])
    }
    if partner_with and _normalize_token(candidate_name) in partner_with:
        return PartnerMode.PARTNER_WITH
    if partner_meta_primary.get("is_doctor") and partner_meta_candidate.get("is_doctors_companion"):
        return PartnerMode.DOCTOR_COMPANION
    if partner_meta_primary.get("is_doctors_companion") and partner_meta_candidate.get("is_doctor"):
        return PartnerMode.DOCTOR_COMPANION
    if partner_meta_primary.get("has_partner") and partner_meta_candidate.get("has_partner"):
        return PartnerMode.PARTNER
    if partner_meta_candidate.get("supports_backgrounds") and partner_meta_primary.get("is_background"):
        return PartnerMode.BACKGROUND
    if partner_meta_candidate.get("has_partner"):
        return PartnerMode.PARTNER
    return PartnerMode.PARTNER


def _partner_meta(payload: Mapping[str, object]) -> MutableMapping[str, object]:
    meta = payload.get("partner")
    if isinstance(meta, Mapping):
        return dict(meta)
    return {}


def _theme_overlap(primary: Mapping[str, object], candidate: Mapping[str, object]) -> float:
    theme_primary = {
        _normalize_token(theme)
        for theme in _theme_sequence(primary)
    }
    theme_candidate = {
        _normalize_token(theme)
        for theme in _theme_sequence(candidate)
    }
    theme_primary.discard("")
    theme_candidate.discard("")

    role_primary = {
        _normalize_token(tag)
        for tag in _sequence(primary, "role_tags")
    }
    role_candidate = {
        _normalize_token(tag)
        for tag in _sequence(candidate, "role_tags")
    }
    role_primary.discard("")
    role_candidate.discard("")

    # Base Jaccard over theme tags.
    union = theme_primary | theme_candidate
    if not union:
        base = 0.0
    else:
        base = len(theme_primary & theme_candidate) / len(union)

    # Role-aware bonus (weighted at 30% of overlap component).
    role_union = role_primary | role_candidate
    if not role_union:
        role_score = 0.0
    else:
        role_score = len(role_primary & role_candidate) / len(role_union)

    combined = 0.7 * base + 0.3 * role_score
    return _clamp(combined)


def _theme_synergy(
    primary: Mapping[str, object],
    candidate: Mapping[str, object],
    context: PartnerSuggestionContext,
) -> float:
    themes_primary = _theme_sequence(primary)
    themes_candidate = _theme_sequence(candidate)
    if not themes_primary or not themes_candidate:
        return 0.0

    total = 0.0
    weight = 0
    for theme_a in themes_primary:
        for theme_b in themes_candidate:
            value = context.theme_synergy(theme_a, theme_b)
            if value <= 0:
                continue
            total += value
            weight += 1

    if weight == 0:
        return 0.0

    average = total / weight

    # Observed pairing signal augments synergy.
    primary_name = _commander_name(primary)
    candidate_name = _commander_name(candidate)
    observed_partner = context.pairing_strength(PartnerMode.PARTNER, primary_name, candidate_name)
    observed_background = context.pairing_strength(PartnerMode.BACKGROUND, primary_name, candidate_name)
    observed_doctor = context.pairing_strength(PartnerMode.DOCTOR_COMPANION, primary_name, candidate_name)
    observed_any = max(observed_partner, observed_background, observed_doctor)

    return _clamp(max(average, observed_any))


def _color_compatibility(primary: Mapping[str, object], candidate: Mapping[str, object]) -> float:
    primary_colors = {
        _clean_str(color).upper()
        for color in _sequence(primary, "color_identity")
    }
    candidate_colors = {
        _clean_str(color).upper()
        for color in _sequence(candidate, "color_identity")
    }

    if not candidate_colors:
        # Colorless partners still provide value when primary is colored.
        return 0.6 if primary_colors else 0.0

    overlap = primary_colors & candidate_colors
    union = primary_colors | candidate_colors
    overlap_ratio = len(overlap) / max(len(candidate_colors), 1)

    added_colors = len(union) - len(primary_colors)
    if added_colors <= 0:
        delta = 1.0
    elif added_colors == 1:
        delta = 0.75
    elif added_colors == 2:
        delta = 0.45
    else:
        delta = 0.20

    colorless_bonus = 0.1 if candidate_colors == {"C"} else 0.0

    blended = 0.6 * overlap_ratio + 0.4 * delta + colorless_bonus
    return _clamp(blended)


def _mechanic_affinity(
    primary: Mapping[str, object],
    candidate: Mapping[str, object],
    mode: PartnerMode,
    context: PartnerSuggestionContext,
) -> tuple[float, list[str], list[tuple[str, float]]]:
    primary_meta = _partner_meta(primary)
    candidate_meta = _partner_meta(candidate)
    primary_name = _commander_name(primary)
    candidate_name = _commander_name(candidate)

    notes: list[str] = []
    penalties: list[tuple[str, float]] = []
    score = 0.0

    if mode is PartnerMode.PARTNER_WITH:
        partner_with = {
            _normalize_token(name)
            for name in primary_meta.get("partner_with", [])
        }
        if partner_with and _normalize_token(candidate_name) in partner_with:
            score = 1.0
            notes.append("partner_with_match")
        else:
            penalties.append(("missing_partner_with_link", 0.9))

    elif mode is PartnerMode.BACKGROUND:
        if candidate_meta.get("is_background") and primary_meta.get("supports_backgrounds"):
            score = 0.9
            notes.append("background_compatible")
        else:
            if not candidate_meta.get("is_background"):
                penalties.append(("candidate_not_background", 1.0))
            if not primary_meta.get("supports_backgrounds"):
                penalties.append(("primary_cannot_use_background", 1.0))

    elif mode is PartnerMode.DOCTOR_COMPANION:
        primary_is_doctor = bool(primary_meta.get("is_doctor"))
        primary_is_companion = bool(primary_meta.get("is_doctors_companion"))
        candidate_is_doctor = bool(candidate_meta.get("is_doctor"))
        candidate_is_companion = bool(candidate_meta.get("is_doctors_companion"))

        if primary_is_doctor and candidate_is_companion:
            score = 1.0
            notes.append("doctor_companion_match")
        elif primary_is_companion and candidate_is_doctor:
            score = 1.0
            notes.append("doctor_companion_match")
        else:
            penalties.append(("doctor_pairing_illegal", 1.0))

    else:  # Partner-style default
        if primary_meta.get("has_partner") and candidate_meta.get("has_partner"):
            score = 0.6
            notes.append("shared_partner_keyword")
        else:
            penalties.append(("missing_partner_keyword", 1.0))

        primary_labels = {
            _normalize_token(label)
            for label in _sequence(primary_meta, "restricted_partner_labels")
        }
        candidate_labels = {
            _normalize_token(label)
            for label in _sequence(candidate_meta, "restricted_partner_labels")
        }
        shared_labels = primary_labels & candidate_labels
        if primary_labels or candidate_labels:
            if shared_labels:
                score = max(score, 0.85)
                notes.append("restricted_label_match")
            else:
                penalties.append(("restricted_label_mismatch", 0.7))

    observed = context.pairing_strength(mode, primary_name, candidate_name)
    if observed > 0:
        score = max(score, observed)
        notes.append("observed_pairing")

    return _clamp(score), notes, penalties


def _collect_penalties(
    primary: Mapping[str, object],
    candidate: Mapping[str, object],
    mode: PartnerMode,
    extra: Iterable[tuple[str, float]],
) -> tuple[float, list[str]]:
    penalties: list[tuple[str, float]] = list(extra)

    themes_primary_raw = _sequence(primary, "themes")
    themes_candidate_raw = _sequence(candidate, "themes")
    themes_primary = _theme_sequence(primary)
    themes_candidate = _theme_sequence(candidate)
    if (not themes_primary or not themes_candidate) and (not themes_primary_raw or not themes_candidate_raw):
        penalties.append(("missing_theme_metadata", 0.5))

    if mode is PartnerMode.PARTNER_WITH:
        partner_with = {
            _normalize_token(name)
            for name in _sequence(primary.get("partner", {}), "partner_with")
        }
        if not partner_with:
            penalties.append(("primary_missing_partner_with", 0.7))

    colors_candidate = set(_sequence(candidate, "color_identity"))
    if len(colors_candidate) >= 4:
        penalties.append(("candidate_color_spread", 0.25))

    total = 0.0
    reasons: list[str] = []
    for reason, magnitude in penalties:
        if magnitude <= 0:
            continue
        total += magnitude
        reasons.append(reason)

    return _clamp(total), reasons
