from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from deck_builder import builder_utils as bu
from deck_builder.theme_matcher import normalize_theme
from deck_builder.theme_resolution import ThemeResolutionInfo

import logging_util

logger = logging_util.logging.getLogger(__name__)

__all__ = [
    "ThemeTarget",
    "ThemeContext",
    "default_user_theme_weight",
    "build_theme_context",
    "annotate_theme_matches",
    "theme_summary_payload",
]


@dataclass(frozen=True)
class ThemeTarget:
    """Represents a prioritized theme target for selection weighting."""

    role: str
    display: str
    slug: str
    source: str  # "commander" | "user"
    weight: float = 0.0


@dataclass
class ThemeContext:
    """Captured theme aggregation for card selection and diagnostics."""

    ordered_targets: List[ThemeTarget]
    combine_mode: str
    weights: Dict[str, float]
    commander_slugs: List[str]
    user_slugs: List[str]
    resolution: Optional[ThemeResolutionInfo]
    user_theme_weight: float

    def selected_slugs(self) -> List[str]:
        return [target.slug for target in self.ordered_targets if target.slug]

    @property
    def commander_selected(self) -> List[str]:
        return list(self.commander_slugs)

    @property
    def user_selected(self) -> List[str]:
        return list(self.user_slugs)

    @property
    def match_multiplier(self) -> float:
        try:
            value = float(self.user_theme_weight)
        except Exception:
            value = 1.0
        return value if value > 0 else 1.0

    @property
    def match_bonus(self) -> float:
        return max(0.0, self.match_multiplier - 1.0)


def default_user_theme_weight() -> float:
    """Read the default user theme weighting multiplier from the environment."""

    raw = os.getenv("USER_THEME_WEIGHT")
    if raw is None:
        return 1.0
    try:
        value = float(raw)
    except Exception:
        logger.warning("Invalid USER_THEME_WEIGHT=%s; falling back to 1.0", raw)
        return 1.0
    return value if value >= 0 else 0.0


def _normalize_role(role: str) -> str:
    try:
        return str(role).strip().lower()
    except Exception:
        return str(role)


def _normalize_tag(value: str | None) -> str:
    if not value:
        return ""
    try:
        return normalize_theme(value)
    except Exception:
        return str(value).strip().lower()


def _theme_weight_factors(
    commander_targets: Sequence[ThemeTarget],
    user_targets: Sequence[ThemeTarget],
    user_theme_weight: float,
) -> Dict[str, float]:
    """Compute normalized weight allocations for commander and user themes."""

    role_factors = {
        "primary": 1.0,
        "secondary": 0.75,
        "tertiary": 0.5,
    }
    raw_weights: Dict[str, float] = {}
    for target in commander_targets:
        factor = role_factors.get(_normalize_role(target.role), 0.5)
        raw_weights[target.role] = max(0.0, factor)
    user_total = max(0.0, user_theme_weight)
    per_user = (user_total / len(user_targets)) if user_targets else 0.0
    for target in user_targets:
        raw_weights[target.role] = max(0.0, per_user)
    total = sum(raw_weights.values())
    if total <= 0:
        if commander_targets:
            fallback = 1.0 / len(commander_targets)
            for target in commander_targets:
                raw_weights[target.role] = fallback
        elif user_targets:
            fallback = 1.0 / len(user_targets)
            for target in user_targets:
                raw_weights[target.role] = fallback
        else:
            return {}
        total = sum(raw_weights.values())
    return {role: weight / total for role, weight in raw_weights.items()}


def build_theme_context(builder: Any) -> ThemeContext:
    """Construct theme ordering, weights, and resolution metadata from a builder."""

    commander_targets: List[ThemeTarget] = []
    for role in ("primary", "secondary", "tertiary"):
        tag = getattr(builder, f"{role}_tag", None)
        if not tag:
            continue
        slug = _normalize_tag(tag)
        commander_targets.append(
            ThemeTarget(role=role, display=str(tag), slug=slug, source="commander")
        )

    user_resolved: List[str] = []
    resolution = getattr(builder, "user_theme_resolution", None)
    if resolution is not None and isinstance(resolution, ThemeResolutionInfo):
        user_resolved = list(resolution.resolved)
    else:
        raw_resolved = getattr(builder, "user_theme_resolved", [])
        if isinstance(raw_resolved, (list, tuple)):
            user_resolved = [str(item) for item in raw_resolved if str(item).strip()]
    user_targets: List[ThemeTarget] = []
    for index, theme in enumerate(user_resolved):
        slug = _normalize_tag(theme)
        role = f"user_{index + 1}"
        user_targets.append(
            ThemeTarget(role=role, display=str(theme), slug=slug, source="user")
        )

    combine_mode = str(getattr(builder, "tag_mode", "AND") or "AND").upper()
    user_theme_weight = float(getattr(builder, "user_theme_weight", default_user_theme_weight()))
    weights = _theme_weight_factors(commander_targets, user_targets, user_theme_weight)

    ordered_raw = commander_targets + user_targets
    ordered = [
        ThemeTarget(
            role=target.role,
            display=target.display,
            slug=target.slug,
            source=target.source,
            weight=weights.get(target.role, 0.0),
        )
        for target in ordered_raw
    ]
    commander_slugs = [target.slug for target in ordered if target.source == "commander" and target.slug]
    user_slugs = [target.slug for target in ordered if target.source == "user" and target.slug]

    info = resolution if isinstance(resolution, ThemeResolutionInfo) else None

    # Log once per context creation for diagnostics
    try:
        logger.debug(
            "Theme context constructed: commander=%s user=%s mode=%s weight=%.3f",
            commander_slugs,
            user_slugs,
            combine_mode,
            user_theme_weight,
        )
    except Exception:
        pass

    try:
        for target in ordered:
            if target.source != "user":
                continue
            effective_weight = weights.get(target.role, target.weight)
            logger.info(
                "user_theme_applied theme='%s' slug=%s role=%s weight=%.3f mode=%s multiplier=%.3f",
                target.display,
                target.slug,
                target.role,
                float(effective_weight or 0.0),
                combine_mode,
                float(user_theme_weight or 0.0),
            )
    except Exception:
        pass

    return ThemeContext(
        ordered_targets=ordered,
        combine_mode=combine_mode,
        weights=weights,
        commander_slugs=commander_slugs,
        user_slugs=user_slugs,
        resolution=info,
        user_theme_weight=user_theme_weight,
    )


def annotate_theme_matches(df, context: ThemeContext):
    """Add commander/user match columns to a working dataframe."""

    if df is None or getattr(df, "empty", True):
        return df
    if "_parsedThemeTags" not in df.columns:
        df = df.copy()
        df["_parsedThemeTags"] = df["themeTags"].apply(bu.normalize_tag_cell)
    if "_normTags" not in df.columns:
        df = df.copy()
        df["_normTags"] = df["_parsedThemeTags"]

    commander_set = set(context.commander_slugs)
    user_set = set(context.user_slugs)

    def _match_count(tags: Iterable[str], needles: set[str]) -> int:
        if not tags or not needles:
            return 0
        try:
            return sum(1 for tag in tags if tag in needles)
        except Exception:
            total = 0
            for tag in tags:
                try:
                    if tag in needles:
                        total += 1
                except Exception:
                    continue
            return total

    df["_commanderMatch"] = df["_normTags"].apply(lambda tags: _match_count(tags, commander_set))
    df["_userMatch"] = df["_normTags"].apply(lambda tags: _match_count(tags, user_set))
    df["_multiMatch"] = df["_commanderMatch"] + df["_userMatch"]
    bonus = context.match_bonus
    if bonus > 0:
        df["_matchScore"] = df["_multiMatch"] + (df["_userMatch"] * bonus)
    else:
        df["_matchScore"] = df["_multiMatch"]

    def _collect_hits(tags: Iterable[str]) -> List[str]:
        if not tags:
            return []
        hits: List[str] = []
        seen: set[str] = set()
        for target in context.ordered_targets:
            slug = target.slug
            if not slug or slug in seen:
                continue
            try:
                if slug in tags:
                    hits.append(target.display)
                    seen.add(slug)
            except Exception:
                continue
        return hits

    df["_matchTags"] = df["_normTags"].apply(_collect_hits)
    return df


def theme_summary_payload(context: ThemeContext) -> Dict[str, Any]:
    """Produce a structured payload for UI/JSON exports summarizing themes."""

    info = context.resolution
    requested: List[str] = []
    resolved: List[str] = []
    unresolved: List[str] = []
    matches: List[Dict[str, Any]] = []
    fuzzy: Dict[str, str] = {}
    catalog_version: Optional[str] = None
    if info is not None:
        requested = list(info.requested)
        resolved = list(info.resolved)
        unresolved = [item.get("input", "") for item in info.unresolved]
        matches = list(info.matches)
        fuzzy = dict(info.fuzzy_corrections)
        catalog_version = info.catalog_version
    else:
        resolved = [target.display for target in context.ordered_targets if target.source == "user"]

    return {
        "commanderThemes": [target.display for target in context.ordered_targets if target.source == "commander"],
        "userThemes": [target.display for target in context.ordered_targets if target.source == "user"],
        "requested": requested,
        "resolved": resolved,
        "unresolved": unresolved,
        "matches": matches,
        "fuzzyCorrections": fuzzy,
        "mode": context.combine_mode,
        "weight": context.user_theme_weight,
        "themeCatalogVersion": catalog_version,
    }
