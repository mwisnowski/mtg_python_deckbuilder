from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import time
import pandas as pd
import yaml

from deck_builder import builder_constants as bc
from random_util import get_random, generate_seed

_THEME_STATS_CACHE: Dict[str, Any] | None = None
_THEME_STATS_CACHE_TS: float = 0.0
_THEME_STATS_TTL_S = 60.0
_RANDOM_THEME_POOL_CACHE: Dict[str, Any] | None = None
_RANDOM_THEME_POOL_TS: float = 0.0
_RANDOM_THEME_POOL_TTL_S = 60.0

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MANUAL_EXCLUSIONS_PATH = _PROJECT_ROOT / "config" / "random_theme_exclusions.yml"
_MANUAL_EXCLUSIONS_CACHE: Dict[str, Dict[str, Any]] | None = None
_MANUAL_EXCLUSIONS_META: List[Dict[str, Any]] | None = None
_MANUAL_EXCLUSIONS_MTIME: float = 0.0

_TAG_INDEX_TELEMETRY: Dict[str, Any] = {
    "builds": 0,
    "last_build_ts": 0.0,
    "token_count": 0,
    "lookups": 0,
    "hits": 0,
    "misses": 0,
    "substring_checks": 0,
    "substring_hits": 0,
}

_KINDRED_KEYWORDS: tuple[str, ...] = (
    "kindred",
    "tribal",
    "tribe",
    "clan",
    "family",
    "pack",
)
_GLOBAL_THEME_KEYWORDS: tuple[str, ...] = (
    "goodstuff",
    "good stuff",
    "all colors",
    "omnicolor",
)
_GLOBAL_THEME_PATTERNS: tuple[tuple[str, str], ...] = (
    ("legend", "matter"),
    ("legendary", "matter"),
    ("historic", "matter"),
)

_OVERREPRESENTED_SHARE_THRESHOLD: float = 0.30  # 30% of the commander catalog


def _sanitize_manual_category(value: Any) -> str:
    try:
        text = str(value).strip().lower()
    except Exception:
        text = "manual"
    return text.replace(" ", "_") or "manual"


def _load_manual_theme_exclusions(refresh: bool = False) -> tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    global _MANUAL_EXCLUSIONS_CACHE, _MANUAL_EXCLUSIONS_META, _MANUAL_EXCLUSIONS_MTIME

    path = _MANUAL_EXCLUSIONS_PATH
    if not path.exists():
        _MANUAL_EXCLUSIONS_CACHE = {}
        _MANUAL_EXCLUSIONS_META = []
        _MANUAL_EXCLUSIONS_MTIME = 0.0
        return {}, []

    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0

    if (
        not refresh
        and _MANUAL_EXCLUSIONS_CACHE is not None
        and _MANUAL_EXCLUSIONS_META is not None
        and _MANUAL_EXCLUSIONS_MTIME == mtime
    ):
        return dict(_MANUAL_EXCLUSIONS_CACHE), list(_MANUAL_EXCLUSIONS_META)

    try:
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw_data = None
    except Exception:
        raw_data = None

    groups = []
    if isinstance(raw_data, dict):
        manual = raw_data.get("manual_exclusions")
        if isinstance(manual, list):
            groups = manual
    elif isinstance(raw_data, list):
        groups = raw_data

    manual_map: Dict[str, Dict[str, Any]] = {}
    manual_meta: List[Dict[str, Any]] = []

    for group in groups:
        if not isinstance(group, dict):
            continue
        tokens = group.get("tokens")
        if not isinstance(tokens, (list, tuple)):
            continue
        category = _sanitize_manual_category(group.get("category"))
        summary = str(group.get("summary", "")).strip()
        notes_raw = group.get("notes")
        notes = str(notes_raw).strip() if notes_raw is not None else ""
        display_tokens: List[str] = []
        for token in tokens:
            try:
                display = str(token).strip()
            except Exception:
                continue
            if not display:
                continue
            norm = display.lower()
            manual_map[norm] = {
                "display": display,
                "category": category,
                "summary": summary,
                "notes": notes,
            }
            display_tokens.append(display)
        if display_tokens:
            manual_meta.append(
                {
                    "category": category,
                    "summary": summary,
                    "notes": notes,
                    "tokens": display_tokens,
                }
            )

    _MANUAL_EXCLUSIONS_CACHE = manual_map
    _MANUAL_EXCLUSIONS_META = manual_meta
    _MANUAL_EXCLUSIONS_MTIME = mtime
    return dict(manual_map), list(manual_meta)


def _record_index_build(token_count: int) -> None:
    _TAG_INDEX_TELEMETRY["builds"] = int(_TAG_INDEX_TELEMETRY.get("builds", 0) or 0) + 1
    _TAG_INDEX_TELEMETRY["last_build_ts"] = time.time()
    _TAG_INDEX_TELEMETRY["token_count"] = int(max(0, token_count))


def _record_index_lookup(token: Optional[str], hit: bool, *, substring: bool = False) -> None:
    _TAG_INDEX_TELEMETRY["lookups"] = int(_TAG_INDEX_TELEMETRY.get("lookups", 0) or 0) + 1
    key = "hits" if hit else "misses"
    _TAG_INDEX_TELEMETRY[key] = int(_TAG_INDEX_TELEMETRY.get(key, 0) or 0) + 1
    if substring:
        _TAG_INDEX_TELEMETRY["substring_checks"] = int(_TAG_INDEX_TELEMETRY.get("substring_checks", 0) or 0) + 1
        if hit:
            _TAG_INDEX_TELEMETRY["substring_hits"] = int(_TAG_INDEX_TELEMETRY.get("substring_hits", 0) or 0) + 1


def _get_index_telemetry_snapshot() -> Dict[str, Any]:
    lookups = float(_TAG_INDEX_TELEMETRY.get("lookups", 0) or 0)
    hits = float(_TAG_INDEX_TELEMETRY.get("hits", 0) or 0)
    hit_rate = round(hits / lookups, 6) if lookups else 0.0
    snapshot = {
        "builds": int(_TAG_INDEX_TELEMETRY.get("builds", 0) or 0),
        "token_count": int(_TAG_INDEX_TELEMETRY.get("token_count", 0) or 0),
        "lookups": int(lookups),
        "hits": int(hits),
        "misses": int(_TAG_INDEX_TELEMETRY.get("misses", 0) or 0),
        "hit_rate": hit_rate,
        "substring_checks": int(_TAG_INDEX_TELEMETRY.get("substring_checks", 0) or 0),
        "substring_hits": int(_TAG_INDEX_TELEMETRY.get("substring_hits", 0) or 0),
    }
    last_ts = _TAG_INDEX_TELEMETRY.get("last_build_ts")
    if last_ts:
        try:
            snapshot["last_build_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(last_ts)))
        except Exception:
            pass
    return snapshot


def _is_kindred_token(token: str) -> bool:
    norm = token.strip().lower()
    if not norm:
        return False
    if norm.startswith("tribal ") or norm.endswith(" tribe"):
        return True
    for keyword in _KINDRED_KEYWORDS:
        if keyword in norm:
            return True
    return False


def _is_global_token(token: str) -> bool:
    norm = token.strip().lower()
    if not norm:
        return False
    for keyword in _GLOBAL_THEME_KEYWORDS:
        if keyword in norm:
            return True
    for prefix, suffix in _GLOBAL_THEME_PATTERNS:
        if prefix in norm and suffix in norm:
            return True
    return False


def _build_random_theme_pool(df: pd.DataFrame, *, include_details: bool = False) -> tuple[set[str], Dict[str, Any]]:
    """Build a curated pool of theme tokens eligible for auto-fill assistance."""

    _ensure_theme_tag_cache(df)
    index_map = df.attrs.get("_ltag_index") or {}
    manual_map, manual_meta = _load_manual_theme_exclusions()
    manual_applied: Dict[str, Dict[str, Any]] = {}
    allowed: set[str] = set()
    excluded: Dict[str, list[str]] = {}
    counts: Dict[str, int] = {}
    try:
        total_rows = int(len(df.index))
    except Exception:
        total_rows = 0
    total_rows = max(0, total_rows)
    for token, values in index_map.items():
        reasons: list[str] = []
        count = 0
        try:
            count = int(len(values)) if values is not None else 0
        except Exception:
            count = 0
        counts[token] = count
        if count < 5:
            reasons.append("insufficient_samples")
        if _is_global_token(token):
            reasons.append("global_theme")
        if _is_kindred_token(token):
            reasons.append("kindred_theme")
        if total_rows > 0:
            try:
                share = float(count) / float(total_rows)
            except Exception:
                share = 0.0
            if share >= _OVERREPRESENTED_SHARE_THRESHOLD:
                reasons.append("overrepresented_theme")
        manual_entry = manual_map.get(token)
        if manual_entry:
            category = _sanitize_manual_category(manual_entry.get("category"))
            if category:
                reasons.append(f"manual_category:{category}")
            reasons.append("manual_exclusion")
            manual_applied[token] = {
                "display": manual_entry.get("display", token),
                "category": category,
                "summary": manual_entry.get("summary", ""),
                "notes": manual_entry.get("notes", ""),
            }

        if reasons:
            excluded[token] = reasons
            continue
        allowed.add(token)

    excluded_counts: Dict[str, int] = {}
    excluded_samples: Dict[str, list[str]] = {}
    for token, reasons in excluded.items():
        for reason in reasons:
            excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
            bucket = excluded_samples.setdefault(reason, [])
            if len(bucket) < 8:
                bucket.append(token)

    total_tokens = len(counts)
    try:
        coverage_ratio = float(len(allowed)) / float(total_tokens) if total_tokens else 0.0
    except Exception:
        coverage_ratio = 0.0

    try:
        manual_source = _MANUAL_EXCLUSIONS_PATH.relative_to(_PROJECT_ROOT)
        manual_source_str = str(manual_source)
    except Exception:
        manual_source_str = str(_MANUAL_EXCLUSIONS_PATH)

    metadata: Dict[str, Any] = {
        "pool_size": len(allowed),
        "total_commander_count": total_rows,
        "coverage_ratio": round(float(coverage_ratio), 6),
        "excluded_counts": excluded_counts,
        "excluded_samples": excluded_samples,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rules": {
            "min_commander_tags": 5,
            "excluded_keywords": list(_GLOBAL_THEME_KEYWORDS),
            "excluded_patterns": [" ".join(p) for p in _GLOBAL_THEME_PATTERNS],
            "kindred_keywords": list(_KINDRED_KEYWORDS),
            "overrepresented_share_threshold": _OVERREPRESENTED_SHARE_THRESHOLD,
            "manual_exclusions_source": manual_source_str,
            "manual_exclusions": manual_meta,
            "manual_category_count": len({entry.get("category") for entry in manual_meta}),
        },
    }
    if manual_applied:
        metadata["manual_exclusion_detail"] = manual_applied
        metadata["manual_exclusion_token_count"] = len(manual_applied)
    if include_details:
        metadata["excluded_detail"] = {
            token: list(reasons)
            for token, reasons in excluded.items()
        }
    return allowed, metadata


def _get_random_theme_pool_cached(refresh: bool = False, df: Optional[pd.DataFrame] = None) -> tuple[set[str], Dict[str, Any]]:
    global _RANDOM_THEME_POOL_CACHE, _RANDOM_THEME_POOL_TS

    now = time.time()
    if (
        not refresh
        and _RANDOM_THEME_POOL_CACHE is not None
        and (now - _RANDOM_THEME_POOL_TS) < _RANDOM_THEME_POOL_TTL_S
    ):
        cached_allowed = _RANDOM_THEME_POOL_CACHE.get("allowed", set())
        cached_meta = _RANDOM_THEME_POOL_CACHE.get("metadata", {})
        return set(cached_allowed), dict(cached_meta)

    dataset = df if df is not None else _load_commanders_df()
    allowed, metadata = _build_random_theme_pool(dataset)
    _RANDOM_THEME_POOL_CACHE = {"allowed": set(allowed), "metadata": dict(metadata)}
    _RANDOM_THEME_POOL_TS = now
    return set(allowed), dict(metadata)


def get_random_theme_pool(*, refresh: bool = False) -> Dict[str, Any]:
    """Public helper exposing the curated auto-fill theme pool."""

    allowed, metadata = _get_random_theme_pool_cached(refresh=refresh)
    rules = dict(metadata.get("rules", {}))
    if not rules:
        rules = {
            "min_commander_tags": 5,
            "excluded_keywords": list(_GLOBAL_THEME_KEYWORDS),
            "excluded_patterns": [" ".join(p) for p in _GLOBAL_THEME_PATTERNS],
            "kindred_keywords": list(_KINDRED_KEYWORDS),
            "overrepresented_share_threshold": _OVERREPRESENTED_SHARE_THRESHOLD,
        }
        metadata = dict(metadata)
        metadata["rules"] = dict(rules)
    payload = {
        "allowed_tokens": sorted(allowed),
        "metadata": metadata,
        "rules": rules,
    }
    return payload


def token_allowed_for_random(token: Optional[str]) -> bool:
    if token is None:
        return False
    norm = token.strip().lower()
    if not norm:
        return False
    allowed, _meta = _get_random_theme_pool_cached(refresh=False)
    return norm in allowed


class RandomBuildError(Exception):
    pass


class RandomConstraintsImpossibleError(RandomBuildError):
    def __init__(self, message: str, *, constraints: Optional[Dict[str, Any]] = None, pool_size: Optional[int] = None):
        super().__init__(message)
        self.constraints = constraints or {}
        self.pool_size = int(pool_size or 0)


class RandomThemeNoMatchError(RandomBuildError):
    def __init__(self, message: str, *, diagnostics: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


@dataclass
class RandomBuildResult:
    seed: int
    commander: str
    theme: Optional[str]
    constraints: Optional[Dict[str, Any]]
    # Extended multi-theme support
    primary_theme: Optional[str] = None
    secondary_theme: Optional[str] = None
    tertiary_theme: Optional[str] = None
    resolved_themes: List[str] | None = None  # actual AND-combination used for filtering (case-preserved)
    # Diagnostics / fallback metadata
    theme_fallback: bool = False  # original single-theme fallback (legacy)
    original_theme: Optional[str] = None
    combo_fallback: bool = False  # when we had to drop one or more secondary/tertiary themes
    synergy_fallback: bool = False  # when primary itself had no matches and we broadened based on loose overlap
    fallback_reason: Optional[str] = None
    attempts_tried: int = 0
    timeout_hit: bool = False
    retries_exhausted: bool = False
    display_themes: List[str] | None = None
    auto_fill_secondary_enabled: bool = False
    auto_fill_tertiary_enabled: bool = False
    auto_fill_enabled: bool = False
    auto_fill_applied: bool = False
    auto_filled_themes: List[str] | None = None
    strict_theme_match: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": int(self.seed),
            "commander": self.commander,
            "theme": self.theme,
            "constraints": self.constraints or {},
        }


def _load_commanders_df() -> pd.DataFrame:
    """Load commanders from Parquet using isCommander boolean flag.

    M4: Migrated from CSV to Parquet loading with boolean filtering.
    """
    from . import builder_utils as bu
    
    # Load all cards from Parquet
    df = bu._load_all_cards_parquet()
    if df.empty:
        return pd.DataFrame()
    
    # Filter to commanders using boolean flag
    commanders_df = bc.get_commanders(df)
    return _ensure_theme_tag_cache(commanders_df)


def _ensure_theme_tag_cache(df: pd.DataFrame) -> pd.DataFrame:
    """Attach a lower-cased theme tag cache column and prebuilt index."""

    if "_ltags" not in df.columns:

        def _normalize_tag_list(raw: Any) -> List[str]:
            result: List[str] = []
            if raw is None:
                return result
            try:
                iterable = list(raw) if isinstance(raw, (list, tuple, set)) else raw
            except Exception:
                iterable = []
            seen: set[str] = set()
            for item in iterable:
                try:
                    token = str(item).strip().lower()
                except Exception:
                    continue
                if not token:
                    continue
                if token in seen:
                    continue
                seen.add(token)
                result.append(token)
            return result

        try:
            df["_ltags"] = df.get("themeTags").apply(_normalize_tag_list)
        except Exception:
            df["_ltags"] = [[] for _ in range(len(df))]

    _ensure_theme_tag_index(df)
    return df


def _ensure_theme_tag_index(df: pd.DataFrame) -> None:
    """Populate a cached mapping of theme tag -> DataFrame index for fast lookups."""

    if "_ltag_index" in df.attrs:
        return

    index_map: Dict[str, List[Any]] = {}
    tags_series = df.get("_ltags")
    if tags_series is None:
        df.attrs["_ltag_index"] = {}
        return

    for idx, tags in tags_series.items():
        if not tags:
            continue
        for token in tags:
            index_map.setdefault(token, []).append(idx)

    built_index = {token: pd.Index(values) for token, values in index_map.items()}
    df.attrs["_ltag_index"] = built_index
    try:
        _record_index_build(len(built_index))
    except Exception:
        pass


def _fallback_display_token(token: str) -> str:
    parts = [segment for segment in token.strip().split() if segment]
    if not parts:
        return token.strip() or token
    return " ".join(piece.capitalize() for piece in parts)


def _resolve_display_tokens(tokens: Iterable[str], *frames: pd.DataFrame) -> List[str]:
    order: List[str] = []
    display_map: Dict[str, Optional[str]] = {}
    for raw in tokens:
        try:
            norm = str(raw).strip().lower()
        except Exception:
            continue
        if not norm or norm in display_map:
            continue
        display_map[norm] = None
        order.append(norm)
    if not order:
        return []

    def _harvest(frame: pd.DataFrame) -> None:
        try:
            tags_series = frame.get("themeTags")
        except Exception:
            tags_series = None
        if not isinstance(tags_series, pd.Series):
            return
        for tags in tags_series:
            if not tags:
                continue
            try:
                iterator = list(tags) if isinstance(tags, (list, tuple, set)) else []
            except Exception:
                iterator = []
            for tag in iterator:
                try:
                    text = str(tag).strip()
                except Exception:
                    continue
                if not text:
                    continue
                key = text.lower()
                if key in display_map and display_map[key] is None:
                    display_map[key] = text
            if all(display_map[k] is not None for k in order):
                return

    for frame in frames:
        if isinstance(frame, pd.DataFrame):
            _harvest(frame)
            if all(display_map[k] is not None for k in order):
                break

    return [display_map.get(norm) or _fallback_display_token(norm) for norm in order]


def _auto_fill_missing_themes(
    df: pd.DataFrame,
    commander: str,
    rng,
    *,
    primary_theme: Optional[str],
    secondary_theme: Optional[str],
    tertiary_theme: Optional[str],
    allowed_pool: set[str],
    fill_secondary: bool,
    fill_tertiary: bool,
) -> tuple[Optional[str], Optional[str], list[str]]:
    """Given a commander, auto-fill secondary/tertiary themes from curated pool."""

    def _norm(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            text = str(value).strip().lower()
        except Exception:
            return None
        return text if text else None

    secondary_result = secondary_theme if secondary_theme else None
    tertiary_result = tertiary_theme if tertiary_theme else None
    auto_filled: list[str] = []

    missing_secondary = bool(fill_secondary) and (secondary_result is None or _norm(secondary_result) is None)
    missing_tertiary = bool(fill_tertiary) and (tertiary_result is None or _norm(tertiary_result) is None)
    if not missing_secondary and not missing_tertiary:
        return secondary_result, tertiary_result, auto_filled

    try:
        subset = df[df["name"].astype(str) == str(commander)]
        if subset.empty:
            return secondary_result, tertiary_result, auto_filled
        row = subset.iloc[0]
        raw_tags = row.get("themeTags", []) or []
    except Exception:
        return secondary_result, tertiary_result, auto_filled

    seen_norms: set[str] = set()
    candidates: list[tuple[str, str]] = []

    primary_norm = _norm(primary_theme)
    secondary_norm = _norm(secondary_result)
    tertiary_norm = _norm(tertiary_result)
    existing_norms = {n for n in (primary_norm, secondary_norm, tertiary_norm) if n}

    for raw in raw_tags:
        try:
            text = str(raw).strip()
        except Exception:
            continue
        if not text:
            continue
        norm = text.lower()
        if norm in seen_norms:
            continue
        seen_norms.add(norm)
        if norm in existing_norms:
            continue
        if norm not in allowed_pool:
            continue
        candidates.append((text, norm))

    if not candidates:
        return secondary_result, tertiary_result, auto_filled

    order = list(range(len(candidates)))
    try:
        rng.shuffle(order)
    except Exception:
        order = list(range(len(candidates)))

    shuffled = [candidates[i] for i in order]
    used_norms = set(existing_norms)

    for text, norm in shuffled:
        if missing_secondary and norm not in used_norms:
            secondary_result = text
            missing_secondary = False
            used_norms.add(norm)
            auto_filled.append(text)
            continue
        if missing_tertiary and norm not in used_norms:
            tertiary_result = text
            missing_tertiary = False
            used_norms.add(norm)
            auto_filled.append(text)
        if not missing_secondary and not missing_tertiary:
            break

    return secondary_result, tertiary_result, auto_filled


def _build_theme_tag_stats(df: pd.DataFrame) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "commanders": 0,
        "with_tags": 0,
        "without_tags": 0,
        "unique_tokens": 0,
        "total_assignments": 0,
        "avg_tokens_per_commander": 0.0,
        "median_tokens_per_commander": 0.0,
        "top_tokens": [],
        "cache_ready": False,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        total_rows = int(len(df.index))
    except Exception:
        total_rows = 0
    stats["commanders"] = total_rows

    try:
        tags_series = df.get("_ltags")
    except Exception:
        tags_series = None

    lengths: list[int] = []
    if tags_series is not None:
        try:
            for item in tags_series.tolist():
                if isinstance(item, list):
                    lengths.append(len(item))
                else:
                    lengths.append(0)
        except Exception:
            lengths = []

    if lengths:
        with_tags = sum(1 for length in lengths if length > 0)
    else:
        with_tags = 0
    stats["with_tags"] = with_tags
    stats["without_tags"] = max(0, total_rows - with_tags)

    index_map = df.attrs.get("_ltag_index") or {}
    stats["cache_ready"] = bool(index_map)

    try:
        unique_tokens = len(index_map)
    except Exception:
        unique_tokens = 0
    stats["unique_tokens"] = unique_tokens

    total_assignments = 0
    if isinstance(index_map, dict):
        try:
            for values in index_map.values():
                try:
                    total_assignments += int(len(values))
                except Exception:
                    continue
        except Exception:
            total_assignments = 0
    stats["total_assignments"] = total_assignments

    avg_tokens = 0.0
    if total_rows > 0:
        try:
            avg_tokens = total_assignments / float(total_rows)
        except Exception:
            avg_tokens = 0.0
    stats["avg_tokens_per_commander"] = round(float(avg_tokens), 3)

    if lengths:
        try:
            sorted_lengths = sorted(lengths)
            mid = len(sorted_lengths) // 2
            if len(sorted_lengths) % 2 == 0:
                median_val = (sorted_lengths[mid - 1] + sorted_lengths[mid]) / 2.0
            else:
                median_val = float(sorted_lengths[mid])
        except Exception:
            median_val = 0.0
        stats["median_tokens_per_commander"] = round(float(median_val), 3)

    top_tokens: list[Dict[str, Any]] = []
    if isinstance(index_map, dict) and index_map:
        try:
            pairs = [
                (token, int(len(idx)))
                for token, idx in index_map.items()
                if idx is not None
            ]
            pairs.sort(key=lambda item: item[1], reverse=True)
            for token, count in pairs[:10]:
                top_tokens.append({"token": token, "count": count})
        except Exception:
            top_tokens = []
    stats["top_tokens"] = top_tokens

    try:
        pool_allowed, pool_meta = _build_random_theme_pool(df)
    except Exception:
        pool_allowed, pool_meta = set(), {}
    rules_meta = pool_meta.get("rules") or {
        "min_commander_tags": 5,
        "excluded_keywords": list(_GLOBAL_THEME_KEYWORDS),
        "excluded_patterns": [" ".join(p) for p in _GLOBAL_THEME_PATTERNS],
        "kindred_keywords": list(_KINDRED_KEYWORDS),
        "overrepresented_share_threshold": _OVERREPRESENTED_SHARE_THRESHOLD,
    }
    stats["random_pool"] = {
        "size": len(pool_allowed),
        "coverage_ratio": pool_meta.get("coverage_ratio"),
        "total_commander_count": pool_meta.get("total_commander_count"),
        "excluded_counts": dict(pool_meta.get("excluded_counts", {})),
        "excluded_samples": {
            reason: list(tokens)
            for reason, tokens in (pool_meta.get("excluded_samples", {}) or {}).items()
        },
        "rules": dict(rules_meta),
        "manual_exclusion_detail": dict(pool_meta.get("manual_exclusion_detail", {})),
        "manual_exclusion_token_count": pool_meta.get("manual_exclusion_token_count", 0),
    }

    try:
        stats["index_telemetry"] = _get_index_telemetry_snapshot()
    except Exception:
        stats["index_telemetry"] = {
            "builds": 0,
            "token_count": 0,
            "lookups": 0,
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "substring_checks": 0,
            "substring_hits": 0,
        }

    return stats


def get_theme_tag_stats(*, refresh: bool = False) -> Dict[str, Any]:
    """Return cached commander theme tag statistics for diagnostics."""

    global _THEME_STATS_CACHE, _THEME_STATS_CACHE_TS

    now = time.time()
    if (
        not refresh
        and _THEME_STATS_CACHE is not None
        and (now - _THEME_STATS_CACHE_TS) < _THEME_STATS_TTL_S
    ):
        return dict(_THEME_STATS_CACHE)

    df = _load_commanders_df()
    df = _ensure_theme_tag_cache(df)
    stats = _build_theme_tag_stats(df)

    _THEME_STATS_CACHE = dict(stats)
    _THEME_STATS_CACHE_TS = now
    return stats


def _normalize_tag(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def _normalize_meta_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_meta_list(values: Optional[Iterable[Optional[str]]]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    if not values:
        return normalized
    for value in values:
        norm = _normalize_meta_value(value)
        if norm:
            lowered = norm.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(lowered)
    return normalized


def _filter_multi(df: pd.DataFrame, primary: Optional[str], secondary: Optional[str], tertiary: Optional[str]) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Return filtered commander dataframe based on ordered fallback strategy.

    Strategy (P = primary, S = secondary, T = tertiary):
      1. If all P,S,T provided → try P&S&T
      2. If no triple match → try P&S
      3. If no P&S → try P&T (treat tertiary as secondary weight-wise)
      4. If no P+{S|T} → try P alone
      5. If P alone empty → attempt loose synergy fallback (any commander whose themeTags share a word with P)
      6. Else full pool fallback (ultimate guard)

    Returns (filtered_df, diagnostics_dict)
    diagnostics_dict keys:
      - resolved_themes: list[str]
      - combo_fallback: bool
      - synergy_fallback: bool
      - fallback_reason: str | None
    """
    diag: Dict[str, Any] = {
        "resolved_themes": None,
        "combo_fallback": False,
        "synergy_fallback": False,
        "fallback_reason": None,
    }
    # Normalize to lowercase for comparison but preserve original for reporting
    p = _normalize_tag(primary)
    s = _normalize_tag(secondary)
    t = _normalize_tag(tertiary)
    # Helper to test AND-combo
    def _get_index_map(current_df: pd.DataFrame) -> Dict[str, pd.Index]:
        _ensure_theme_tag_cache(current_df)
        index_map = current_df.attrs.get("_ltag_index")
        if index_map is None:
            _ensure_theme_tag_index(current_df)
            index_map = current_df.attrs.get("_ltag_index") or {}
        return index_map

    index_map_all = _get_index_map(df)

    def and_filter(req: List[str]) -> pd.DataFrame:
        if not req:
            return df
        req_l = [r.lower() for r in req]
        try:
            matching_indices: Optional[pd.Index] = None
            for token in req_l:
                token_matches = index_map_all.get(token)
                hit = False
                if token_matches is not None:
                    try:
                        hit = len(token_matches) > 0
                    except Exception:
                        hit = False
                try:
                    _record_index_lookup(token, hit)
                except Exception:
                    pass
                if not hit:
                    return df.iloc[0:0]
                matching_indices = token_matches if matching_indices is None else matching_indices.intersection(token_matches)
                if matching_indices is not None and matching_indices.empty:
                    return df.iloc[0:0]
            if matching_indices is None or matching_indices.empty:
                return df.iloc[0:0]
            return df.loc[matching_indices]
        except Exception:
            return df.iloc[0:0]

    # 1. Triple
    if p and s and t:
        triple = and_filter([p, s, t])
        if len(triple) > 0:
            diag["resolved_themes"] = [p, s, t]
            return triple, diag
    # 2. P+S
    if p and s:
        ps = and_filter([p, s])
        if len(ps) > 0:
            if t:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No commanders matched all three themes; using Primary+Secondary"
            diag["resolved_themes"] = [p, s]
            return ps, diag
    # 3. P+T
    if p and t:
        pt = and_filter([p, t])
        if len(pt) > 0:
            if s:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No commanders matched requested combinations; using Primary+Tertiary"
            diag["resolved_themes"] = [p, t]
            return pt, diag
    # 4. P only
    if p:
        p_only = and_filter([p])
        if len(p_only) > 0:
            if s or t:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No multi-theme combination matched; using Primary only"
            diag["resolved_themes"] = [p]
            return p_only, diag
    # 5. Synergy fallback based on primary token overlaps
    if p:
        words = [w.lower() for w in p.replace('-', ' ').split() if w]
        if words:
            try:
                direct_hits = pd.Index([])
                matched_tokens: set[str] = set()
                matched_order: List[str] = []
                for token in words:
                    matches = index_map_all.get(token)
                    hit = False
                    if matches is not None:
                        try:
                            hit = len(matches) > 0
                        except Exception:
                            hit = False
                    try:
                        _record_index_lookup(token, hit)
                    except Exception:
                        pass
                    if hit:
                        if token not in matched_tokens:
                            matched_tokens.add(token)
                            matched_order.append(token)
                        direct_hits = direct_hits.union(matches)

                # If no direct hits, attempt substring matches using cached index keys
                if len(direct_hits) == 0:
                    for word in words:
                        for token_value, matches in index_map_all.items():
                            if word in token_value:
                                hit = False
                                if matches is not None:
                                    try:
                                        hit = len(matches) > 0
                                    except Exception:
                                        hit = False
                                try:
                                    _record_index_lookup(token_value, hit, substring=True)
                                except Exception:
                                    pass
                                if hit:
                                    token_key = str(token_value).strip().lower()
                                    if token_key and token_key not in matched_tokens:
                                        matched_tokens.add(token_key)
                                        matched_order.append(token_key)
                                    direct_hits = direct_hits.union(matches)

                if len(direct_hits) > 0:
                    synergy_df = df.loc[direct_hits]
                    if len(synergy_df) > 0:
                        display_tokens = _resolve_display_tokens(matched_order or words, synergy_df, df)
                        if not display_tokens:
                            display_tokens = [_fallback_display_token(word) for word in words]
                        diag["resolved_themes"] = display_tokens
                        diag["combo_fallback"] = True
                        diag["synergy_fallback"] = True
                        diag["fallback_reason"] = "Primary theme had no direct matches; using synergy overlap"
                        return synergy_df, diag
            except Exception:
                pass
    # 6. Full pool fallback
    diag["resolved_themes"] = []
    diag["combo_fallback"] = True
    diag["synergy_fallback"] = True
    diag["fallback_reason"] = "No theme matches found; using full commander pool"
    return df, diag


def _candidate_ok(candidate: str, constraints: Optional[Dict[str, Any]]) -> bool:
    """Check simple feasibility filters from constraints.

    Supported keys (lightweight, safe defaults):
      - reject_all: bool -> if True, reject every candidate (useful for retries-exhausted tests)
      - reject_names: list[str] -> reject these specific names
    """
    if not constraints:
        return True
    try:
        if constraints.get("reject_all"):
            return False
    except Exception:
        pass
    try:
        rej = constraints.get("reject_names")
        if isinstance(rej, (list, tuple)) and any(str(candidate) == str(x) for x in rej):
            return False
    except Exception:
        pass
    return True


def _check_constraints(candidate_count: int, constraints: Optional[Dict[str, Any]]) -> None:
    if not constraints:
        return
    try:
        req_min = constraints.get("require_min_candidates")
    except Exception:
        req_min = None
    if req_min is None:
        return
    try:
        req_min_int = int(req_min)
    except Exception:
        req_min_int = None
    if req_min_int is not None and candidate_count < req_min_int:
        raise RandomConstraintsImpossibleError(
            f"Not enough candidates to satisfy constraints (have {candidate_count}, require >= {req_min_int})",
            constraints=constraints,
            pool_size=candidate_count,
        )


def build_random_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
    # New multi-theme inputs (theme retained for backward compatibility as primary)
    primary_theme: Optional[str] = None,
    secondary_theme: Optional[str] = None,
    tertiary_theme: Optional[str] = None,
    auto_fill_missing: bool = False,
    auto_fill_secondary: Optional[bool] = None,
    auto_fill_tertiary: Optional[bool] = None,
    strict_theme_match: bool = False,
) -> RandomBuildResult:
    """Thin wrapper for random selection of a commander, deterministic when seeded.

    Contract (initial/minimal):
    - Inputs: optional theme filter, optional constraints dict, seed for determinism,
      attempts (max reroll attempts), timeout_s (wall clock cap).
    - Output: RandomBuildResult with chosen commander and the resolved seed.

    Notes:
    - This does NOT run the full deck builder yet; it focuses on picking a commander
      deterministically for tests and plumbing. Full pipeline can be layered later.
    - Determinism: when `seed` is provided, selection is stable across runs.
    - When `seed` is None, a new high-entropy seed is generated and returned.
    """
    # Resolve seed and RNG
    resolved_seed = int(seed) if isinstance(seed, int) or (isinstance(seed, str) and str(seed).isdigit()) else None
    if resolved_seed is None:
        resolved_seed = generate_seed()
    rng = get_random(resolved_seed)

    # Bounds sanitation
    attempts = max(1, int(attempts or 1))
    try:
        timeout_s = float(timeout_s)
    except Exception:
        timeout_s = 5.0
    timeout_s = max(0.1, timeout_s)

    # Resolve multi-theme inputs
    if primary_theme is None:
        primary_theme = theme  # legacy single theme becomes primary
    df_all = _load_commanders_df()
    df_all = _ensure_theme_tag_cache(df_all)
    df, multi_diag = _filter_multi(df_all, primary_theme, secondary_theme, tertiary_theme)
    strict_flag = bool(strict_theme_match)
    if strict_flag:
        if df.empty:
            raise RandomThemeNoMatchError(
                "No commanders matched the requested themes",
                diagnostics=dict(multi_diag or {}),
            )
        if bool(multi_diag.get("combo_fallback")) or bool(multi_diag.get("synergy_fallback")):
            raise RandomThemeNoMatchError(
                "No commanders matched the requested themes",
                diagnostics=dict(multi_diag or {}),
            )
    used_fallback = False
    original_theme = None
    resolved_before_auto = list(multi_diag.get("resolved_themes") or [])
    if multi_diag.get("combo_fallback") or multi_diag.get("synergy_fallback"):
        # For legacy fields
        used_fallback = bool(multi_diag.get("combo_fallback"))
        original_theme = primary_theme if primary_theme else None
    # Stable ordering then seeded selection for deterministic behavior
    names: List[str] = sorted(df["name"].astype(str).tolist()) if not df.empty else []
    if not names:
        # Fall back to entire pool by name if theme produced nothing
        names = sorted(df_all["name"].astype(str).tolist())
    if not names:
        # Absolute fallback for pathological cases
        names = ["Unknown Commander"]

    # Constraint feasibility check (based on candidate count)
    _check_constraints(len(names), constraints)

    # Simple attempt/timeout loop (placeholder for future constraints checks)
    start = time.time()
    pick = None
    attempts_tried = 0
    timeout_hit = False
    for i in range(attempts):
        if (time.time() - start) > timeout_s:
            timeout_hit = True
            break
        attempts_tried = i + 1
        idx = rng.randrange(0, len(names))
        candidate = names[idx]
        # Accept only if candidate passes simple feasibility filters
        if _candidate_ok(candidate, constraints):
            pick = candidate
            break
        # else continue and try another candidate until attempts/timeout
    retries_exhausted = (pick is None) and (not timeout_hit) and (attempts_tried >= attempts)
    if pick is None:
        # Timeout/attempts exhausted; choose deterministically based on seed modulo
        pick = names[resolved_seed % len(names)]

    display_themes: List[str] = list(multi_diag.get("resolved_themes") or [])
    auto_filled_themes: List[str] = []

    fill_secondary = bool(auto_fill_secondary if auto_fill_secondary is not None else auto_fill_missing)
    fill_tertiary = bool(auto_fill_tertiary if auto_fill_tertiary is not None else auto_fill_missing)
    auto_fill_enabled_flag = bool(fill_secondary or fill_tertiary)

    if auto_fill_enabled_flag and pick:
        try:
            allowed_pool, _pool_meta = _get_random_theme_pool_cached(refresh=False, df=df_all)
        except Exception:
            allowed_pool = set()
        try:
            secondary_new, tertiary_new, filled = _auto_fill_missing_themes(
                df_all,
                pick,
                rng,
                primary_theme=primary_theme,
                secondary_theme=secondary_theme,
                tertiary_theme=tertiary_theme,
                allowed_pool=allowed_pool,
                fill_secondary=fill_secondary,
                fill_tertiary=fill_tertiary,
            )
        except Exception:
            secondary_new, tertiary_new, filled = secondary_theme, tertiary_theme, []
        secondary_theme = secondary_new
        tertiary_theme = tertiary_new
        auto_filled_themes = list(filled or [])

        if auto_filled_themes:
            multi_diag.setdefault("filter_resolved_themes", resolved_before_auto)
            if not display_themes:
                display_themes = [
                    value
                    for value in (primary_theme, secondary_theme, tertiary_theme)
                    if value
                ]
            existing_norms = {
                str(item).strip().lower()
                for item in display_themes
                if isinstance(item, str) and str(item).strip()
            }
            for value in auto_filled_themes:
                try:
                    text = str(value).strip()
                except Exception:
                    continue
                if not text:
                    continue
                key = text.lower()
                if key in existing_norms:
                    continue
                display_themes.append(text)
                existing_norms.add(key)
            multi_diag["resolved_themes"] = list(display_themes)

    if not display_themes:
        display_themes = list(multi_diag.get("resolved_themes") or [])

    multi_diag["auto_fill_secondary_enabled"] = bool(fill_secondary)
    multi_diag["auto_fill_tertiary_enabled"] = bool(fill_tertiary)
    multi_diag["auto_fill_enabled"] = bool(auto_fill_enabled_flag)
    multi_diag["auto_fill_applied"] = bool(auto_filled_themes)
    multi_diag["auto_filled_themes"] = list(auto_filled_themes)
    multi_diag["strict_theme_match"] = strict_flag

    return RandomBuildResult(
        seed=int(resolved_seed),
        commander=pick,
        theme=primary_theme,  # preserve prior contract
        constraints=constraints or {},
        primary_theme=primary_theme,
        secondary_theme=secondary_theme,
        tertiary_theme=tertiary_theme,
        resolved_themes=list(multi_diag.get("resolved_themes") or []),
        display_themes=list(display_themes),
        auto_fill_secondary_enabled=bool(fill_secondary),
        auto_fill_tertiary_enabled=bool(fill_tertiary),
        auto_fill_enabled=bool(auto_fill_enabled_flag),
        auto_fill_applied=bool(auto_filled_themes),
        auto_filled_themes=list(auto_filled_themes or []),
    strict_theme_match=strict_flag,
        combo_fallback=bool(multi_diag.get("combo_fallback")),
        synergy_fallback=bool(multi_diag.get("synergy_fallback")),
        fallback_reason=multi_diag.get("fallback_reason"),
        theme_fallback=bool(used_fallback),
        original_theme=original_theme,
        attempts_tried=int(attempts_tried or (1 if pick else 0)),
        timeout_hit=bool(timeout_hit),
        retries_exhausted=bool(retries_exhausted),
    )


__all__ = [
    "RandomBuildResult",
    "build_random_deck",
    "get_theme_tag_stats",
]


# Full-build wrapper for deterministic end-to-end builds
@dataclass
class RandomFullBuildResult(RandomBuildResult):
    decklist: List[Dict[str, Any]] | None = None
    diagnostics: Dict[str, Any] | None = None
    summary: Dict[str, Any] | None = None
    csv_path: str | None = None
    txt_path: str | None = None
    compliance: Dict[str, Any] | None = None


def build_random_full_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
    *,
    primary_theme: Optional[str] = None,
    secondary_theme: Optional[str] = None,
    tertiary_theme: Optional[str] = None,
    auto_fill_missing: bool = False,
    auto_fill_secondary: Optional[bool] = None,
    auto_fill_tertiary: Optional[bool] = None,
    strict_theme_match: bool = False,
) -> RandomFullBuildResult:
    """Select a commander deterministically, then run a full deck build via DeckBuilder.

    Returns a compact result including the seed, commander, and a summarized decklist.
    """
    t0 = time.time()

    # Align legacy single-theme input with multi-theme fields
    if primary_theme is None and theme is not None:
        primary_theme = theme
    if primary_theme is not None and theme is None:
        theme = primary_theme

    base = build_random_deck(
        theme=theme,
        constraints=constraints,
        seed=seed,
        attempts=attempts,
        timeout_s=timeout_s,
        primary_theme=primary_theme,
        secondary_theme=secondary_theme,
        tertiary_theme=tertiary_theme,
        auto_fill_missing=auto_fill_missing,
        auto_fill_secondary=auto_fill_secondary,
        auto_fill_tertiary=auto_fill_tertiary,
        strict_theme_match=strict_theme_match,
    )

    def _resolve_theme_choices_for_headless(commander_name: str, base_result: RandomBuildResult) -> tuple[int, Optional[int], Optional[int]]:
        """Translate resolved theme names into DeckBuilder menu selections.

        The headless runner expects numeric indices for primary/secondary/tertiary selections
        based on the commander-specific theme menu. We mirror the CLI ordering so the
        automated run picks the same combination that triggered the commander selection.
        """

        try:
            df = _load_commanders_df()
            row = df[df["name"].astype(str) == str(commander_name)]
            if row.empty:
                return 1, None, None
            raw_tags = row.iloc[0].get("themeTags", []) or []
        except Exception:
            return 1, None, None

        cleaned_tags: List[str] = []
        seen_tags: set[str] = set()
        for tag in raw_tags:
            try:
                tag_str = str(tag).strip()
            except Exception:
                continue
            if not tag_str:
                continue
            key = tag_str.lower()
            if key in seen_tags:
                continue
            seen_tags.add(key)
            cleaned_tags.append(tag_str)

        if not cleaned_tags:
            return 1, None, None

        resolved_list: List[str] = []
        for item in (base_result.resolved_themes or [])[:3]:
            try:
                text = str(item).strip()
            except Exception:
                continue
            if text:
                resolved_list.append(text)

        def _norm(value: Optional[str]) -> str:
            return str(value).strip().lower() if isinstance(value, str) else ""

        def _collect_candidates(*values: Optional[str]) -> List[str]:
            collected: List[str] = []
            seen: set[str] = set()
            for val in values:
                if not val:
                    continue
                text = str(val).strip()
                if not text:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(text)
            return collected

        def _match(options: List[str], candidates: List[str]) -> Optional[int]:
            for candidate in candidates:
                cand_norm = candidate.lower()
                for idx, option in enumerate(options, start=1):
                    if option.strip().lower() == cand_norm:
                        return idx
            return None

        primary_candidates = _collect_candidates(
            resolved_list[0] if resolved_list else None,
            base_result.primary_theme,
        )
        primary_idx = _match(cleaned_tags, primary_candidates)
        if primary_idx is None:
            primary_idx = 1

        def _remove_index(options: List[str], idx: Optional[int]) -> List[str]:
            if idx is None:
                return list(options)
            return [opt for position, opt in enumerate(options, start=1) if position != idx]

        remaining_after_primary = _remove_index(cleaned_tags, primary_idx)

        secondary_idx: Optional[int] = None
        tertiary_idx: Optional[int] = None

        if len(resolved_list) >= 2 and remaining_after_primary:
            second_token = resolved_list[1]
            secondary_candidates = _collect_candidates(
                second_token,
                base_result.secondary_theme if _norm(base_result.secondary_theme) == _norm(second_token) else None,
                base_result.tertiary_theme if _norm(base_result.tertiary_theme) == _norm(second_token) else None,
            )
            secondary_idx = _match(remaining_after_primary, secondary_candidates)
            if secondary_idx is not None:
                remaining_after_secondary = _remove_index(remaining_after_primary, secondary_idx)
                if len(resolved_list) >= 3 and remaining_after_secondary:
                    third_token = resolved_list[2]
                    tertiary_candidates = _collect_candidates(
                        third_token,
                        base_result.tertiary_theme if _norm(base_result.tertiary_theme) == _norm(third_token) else None,
                    )
                    tertiary_idx = _match(remaining_after_secondary, tertiary_candidates)
        elif len(resolved_list) >= 3:
            # Multi-theme fallback kept extra tokens but we could not match a secondary;
            # in that case avoid forcing tertiary selection.
            tertiary_idx = None

        return int(primary_idx), int(secondary_idx) if secondary_idx is not None else None, int(tertiary_idx) if tertiary_idx is not None else None

    # Run the full headless build with the chosen commander and the same seed
    primary_choice_idx, secondary_choice_idx, tertiary_choice_idx = _resolve_theme_choices_for_headless(base.commander, base)

    try:
        from headless_runner import run as _run
    except Exception as e:
        return RandomFullBuildResult(
            seed=base.seed,
            commander=base.commander,
            theme=base.theme,
            constraints=base.constraints or {},
            primary_theme=getattr(base, "primary_theme", None),
            secondary_theme=getattr(base, "secondary_theme", None),
            tertiary_theme=getattr(base, "tertiary_theme", None),
            resolved_themes=list(getattr(base, "resolved_themes", []) or []),
            strict_theme_match=bool(getattr(base, "strict_theme_match", False)),
            combo_fallback=bool(getattr(base, "combo_fallback", False)),
            synergy_fallback=bool(getattr(base, "synergy_fallback", False)),
            fallback_reason=getattr(base, "fallback_reason", None),
            display_themes=list(getattr(base, "display_themes", []) or []),
            auto_fill_secondary_enabled=bool(getattr(base, "auto_fill_secondary_enabled", False)),
            auto_fill_tertiary_enabled=bool(getattr(base, "auto_fill_tertiary_enabled", False)),
            auto_fill_enabled=bool(getattr(base, "auto_fill_enabled", False)),
            auto_fill_applied=bool(getattr(base, "auto_fill_applied", False)),
            auto_filled_themes=list(getattr(base, "auto_filled_themes", []) or []),
            decklist=None,
            diagnostics={"error": f"headless runner unavailable: {e}"},
        )

    # Run the full builder once; reuse object for summary + deck extraction
    # Default behavior: suppress the initial internal export so Random build controls artifacts.
    # (If user explicitly sets RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=0 we respect that.)
    try:
        import os as _os
        if _os.getenv('RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT') is None:
            _os.environ['RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT'] = '1'
    except Exception:
        pass
    builder = _run(
        command_name=base.commander,
        seed=base.seed,
        primary_choice=primary_choice_idx,
        secondary_choice=secondary_choice_idx,
        tertiary_choice=tertiary_choice_idx,
    )

    # Build summary (may fail gracefully)
    summary: Dict[str, Any] | None = None
    try:
        if hasattr(builder, 'build_deck_summary'):
            summary = builder.build_deck_summary()
    except Exception:
        summary = None

    primary_theme_clean = _normalize_meta_value(getattr(base, "primary_theme", None))
    secondary_theme_clean = _normalize_meta_value(getattr(base, "secondary_theme", None))
    tertiary_theme_clean = _normalize_meta_value(getattr(base, "tertiary_theme", None))
    resolved_themes_clean = _normalize_meta_list(getattr(base, "resolved_themes", []) or [])
    fallback_reason_clean = _normalize_meta_value(getattr(base, "fallback_reason", None))
    display_themes_clean = _normalize_meta_list(getattr(base, "display_themes", []) or [])
    auto_filled_clean = _normalize_meta_list(getattr(base, "auto_filled_themes", []) or [])

    random_meta_fields = {
        "primary_theme": primary_theme_clean,
        "secondary_theme": secondary_theme_clean,
        "tertiary_theme": tertiary_theme_clean,
        "resolved_themes": resolved_themes_clean,
        "combo_fallback": bool(getattr(base, "combo_fallback", False)),
        "synergy_fallback": bool(getattr(base, "synergy_fallback", False)),
        "fallback_reason": fallback_reason_clean,
        "display_themes": display_themes_clean,
        "auto_fill_secondary_enabled": bool(getattr(base, "auto_fill_secondary_enabled", False)),
        "auto_fill_tertiary_enabled": bool(getattr(base, "auto_fill_tertiary_enabled", False)),
        "auto_fill_enabled": bool(getattr(base, "auto_fill_enabled", False)),
        "auto_fill_applied": bool(getattr(base, "auto_fill_applied", False)),
        "auto_filled_themes": auto_filled_clean,
    }

    if isinstance(summary, dict):
        try:
            existing_meta = summary.get("meta") if isinstance(summary.get("meta"), dict) else {}
        except Exception:
            existing_meta = {}
        merged_meta = dict(existing_meta or {})
        merged_meta.update({k: v for k, v in random_meta_fields.items()})
        summary["meta"] = merged_meta

    def _build_sidecar_meta(csv_path_val: Optional[str], txt_path_val: Optional[str]) -> Dict[str, Any]:
        commander_name = getattr(builder, 'commander_name', '') or getattr(builder, 'commander', '')
        try:
            selected_tags = list(getattr(builder, 'selected_tags', []) or [])
        except Exception:
            selected_tags = []
        if not selected_tags:
            selected_tags = [t for t in [getattr(builder, 'primary_tag', None), getattr(builder, 'secondary_tag', None), getattr(builder, 'tertiary_tag', None)] if t]
        meta_payload: Dict[str, Any] = {
            "commander": commander_name,
            "tags": selected_tags,
            "bracket_level": getattr(builder, 'bracket_level', None),
            "csv": csv_path_val,
            "txt": txt_path_val,
            "random_seed": base.seed,
            "random_theme": base.theme,
            "random_constraints": base.constraints or {},
        }
        meta_payload.update(random_meta_fields)
        # Legacy keys for backward compatibility
        meta_payload.setdefault("random_primary_theme", meta_payload.get("primary_theme"))
        meta_payload.setdefault("random_secondary_theme", meta_payload.get("secondary_theme"))
        meta_payload.setdefault("random_tertiary_theme", meta_payload.get("tertiary_theme"))
        meta_payload.setdefault("random_resolved_themes", meta_payload.get("resolved_themes"))
        meta_payload.setdefault("random_combo_fallback", meta_payload.get("combo_fallback"))
        meta_payload.setdefault("random_synergy_fallback", meta_payload.get("synergy_fallback"))
        meta_payload.setdefault("random_fallback_reason", meta_payload.get("fallback_reason"))
        meta_payload.setdefault("random_display_themes", meta_payload.get("display_themes"))
        meta_payload.setdefault("random_auto_fill_secondary_enabled", meta_payload.get("auto_fill_secondary_enabled"))
        meta_payload.setdefault("random_auto_fill_tertiary_enabled", meta_payload.get("auto_fill_tertiary_enabled"))
        meta_payload.setdefault("random_auto_fill_enabled", meta_payload.get("auto_fill_enabled"))
        meta_payload.setdefault("random_auto_fill_applied", meta_payload.get("auto_fill_applied"))
        meta_payload.setdefault("random_auto_filled_themes", meta_payload.get("auto_filled_themes"))
        try:
            custom_base = getattr(builder, 'custom_export_base', None)
        except Exception:
            custom_base = None
        if isinstance(custom_base, str) and custom_base.strip():
            meta_payload["name"] = custom_base.strip()
        try:
            commander_meta = builder.get_commander_export_metadata()
        except Exception:
            commander_meta = {}
        names = commander_meta.get("commander_names") or []
        if names:
            meta_payload["commander_names"] = names
        combined_payload = commander_meta.get("combined_commander")
        if combined_payload:
            meta_payload["combined_commander"] = combined_payload
        partner_mode = commander_meta.get("partner_mode")
        if partner_mode:
            meta_payload["partner_mode"] = partner_mode
        color_identity = commander_meta.get("color_identity")
        if color_identity:
            meta_payload["color_identity"] = color_identity
        primary_commander = commander_meta.get("primary_commander")
        if primary_commander:
            meta_payload["commander"] = primary_commander
        secondary_commander = commander_meta.get("secondary_commander")
        if secondary_commander:
            meta_payload["secondary_commander"] = secondary_commander
        return meta_payload

    # Attempt to reuse existing export performed inside builder (headless run already exported)
    csv_path: str | None = None
    txt_path: str | None = None
    compliance: Dict[str, Any] | None = None
    try:
        import os as _os
        import json as _json
        csv_path = getattr(builder, 'last_csv_path', None)
        txt_path = getattr(builder, 'last_txt_path', None)
        if csv_path and isinstance(csv_path, str):
            base_path, _ = _os.path.splitext(csv_path)
            # If txt missing but expected, look for sibling
            if (not txt_path or not _os.path.isfile(str(txt_path))) and _os.path.isfile(base_path + '.txt'):
                txt_path = base_path + '.txt'
            # Load existing compliance if present
            comp_path = base_path + '_compliance.json'
            if _os.path.isfile(comp_path):
                try:
                    with open(comp_path, 'r', encoding='utf-8') as _cf:
                        compliance = _json.load(_cf)
                except Exception:
                    compliance = None
            else:
                # Compute compliance if not already saved
                try:
                    if hasattr(builder, 'compute_and_print_compliance'):
                        compliance = builder.compute_and_print_compliance(base_stem=_os.path.basename(base_path))
                except Exception:
                    compliance = None
            # Write summary sidecar if missing
            if summary:
                sidecar = base_path + '.summary.json'
                if not _os.path.isfile(sidecar):
                    meta = _build_sidecar_meta(csv_path, txt_path)
                    try:
                        with open(sidecar, 'w', encoding='utf-8') as f:
                            _json.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
        else:
            # Fallback: export now (rare path if headless build skipped export)
            if hasattr(builder, 'export_decklist_csv'):
                try:
                    # Before exporting, attempt to find an existing same-day base file (non-suffixed) to avoid duplicate export
                    existing_base: str | None = None
                    try:
                        import glob as _glob
                        today = time.strftime('%Y%m%d')
                        # Commander slug approximation: remove non alnum underscores
                        import re as _re
                        cmdr = (getattr(builder, 'commander_name', '') or getattr(builder, 'commander', '') or '')
                        slug = _re.sub(r'[^A-Za-z0-9_]+', '', cmdr) or 'deck'
                        pattern = f"deck_files/{slug}_*_{today}.csv"
                        for path in sorted(_glob.glob(pattern)):
                            base_name = _os.path.basename(path)
                            if '_1.csv' not in base_name:  # prefer original
                                existing_base = path
                                break
                    except Exception:
                        existing_base = None
                    if existing_base and _os.path.isfile(existing_base):
                        csv_path = existing_base
                        base_path, _ = _os.path.splitext(csv_path)
                    else:
                        tmp_csv = builder.export_decklist_csv()
                        stem_base, ext = _os.path.splitext(tmp_csv)
                        if stem_base.endswith('_1'):
                            original = stem_base[:-2] + ext
                            if _os.path.isfile(original):
                                csv_path = original
                            else:
                                csv_path = tmp_csv
                        else:
                            csv_path = tmp_csv
                        base_path, _ = _os.path.splitext(csv_path)
                    if hasattr(builder, 'export_decklist_text'):
                        target_txt = base_path + '.txt'
                        if _os.path.isfile(target_txt):
                            txt_path = target_txt
                        else:
                            tmp_txt = builder.export_decklist_text(filename=_os.path.basename(base_path) + '.txt')
                            if tmp_txt.endswith('_1.txt') and _os.path.isfile(target_txt):
                                txt_path = target_txt
                            else:
                                txt_path = tmp_txt
                    if hasattr(builder, 'compute_and_print_compliance'):
                        compliance = builder.compute_and_print_compliance(base_stem=_os.path.basename(base_path))
                    if summary:
                        sidecar = base_path + '.summary.json'
                        if not _os.path.isfile(sidecar):
                            meta = _build_sidecar_meta(csv_path, txt_path)
                            with open(sidecar, 'w', encoding='utf-8') as f:
                                _json.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
    except Exception:
        pass

    # Extract a simple decklist (name/count)
    deck_items: List[Dict[str, Any]] = []
    try:
        lib = getattr(builder, 'card_library', {}) or {}
        for name, info in lib.items():
            try:
                cnt = int(info.get('Count', 1)) if isinstance(info, dict) else 1
            except Exception:
                cnt = 1
            deck_items.append({"name": str(name), "count": cnt})
        deck_items.sort(key=lambda x: (str(x.get("name", "").lower()), int(x.get("count", 0))))
    except Exception:
        deck_items = []

    elapsed_ms = int((time.time() - t0) * 1000)
    diags: Dict[str, Any] = {
        "attempts": int(getattr(base, "attempts_tried", 1) or 1),
        "timeout_s": float(timeout_s),
        "elapsed_ms": elapsed_ms,
        "fallback": bool(base.theme_fallback),
        "timeout_hit": bool(getattr(base, "timeout_hit", False)),
        "retries_exhausted": bool(getattr(base, "retries_exhausted", False)),
    }
    diags.update(
        {
            "resolved_themes": list(getattr(base, "resolved_themes", []) or []),
            "combo_fallback": bool(getattr(base, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(base, "synergy_fallback", False)),
            "fallback_reason": getattr(base, "fallback_reason", None),
        }
    )

    base_kwargs = {f.name: getattr(base, f.name) for f in fields(RandomBuildResult)}
    base_kwargs.update({
        "decklist": deck_items,
        "diagnostics": diags,
        "summary": summary,
        "csv_path": csv_path,
        "txt_path": txt_path,
        "compliance": compliance,
    })
    return RandomFullBuildResult(**base_kwargs)

