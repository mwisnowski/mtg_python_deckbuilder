"""Metrics aggregation for theme preview service.

Extracted from `theme_preview.py` (Phase 2 refactor) to isolate
metrics/state reporting from orchestration & caching logic. This allows
future experimentation with alternative cache backends / eviction without
coupling metrics concerns.

Public API:
    record_build_duration(ms: float)
    record_role_counts(role_counts: dict[str,int])
    record_curated_sampled(curated: int, sampled: int)
    record_per_theme(slug: str, build_ms: float, curated: int, sampled: int)
    record_request(hit: bool, error: bool = False, client_error: bool = False)
    record_per_theme_error(slug: str)
    preview_metrics() -> dict

The consuming orchestrator remains responsible for calling these hooks.
"""
from __future__ import annotations

from typing import Any, Dict, List
import os

# Global counters (mirrors previous names for backward compatibility where tests may introspect)
_PREVIEW_BUILD_MS_TOTAL = 0.0
_PREVIEW_BUILD_COUNT = 0
_BUILD_DURATIONS: List[float] = []
_ROLE_GLOBAL_COUNTS: dict[str, int] = {}
_CURATED_GLOBAL = 0
_SAMPLED_GLOBAL = 0
_PREVIEW_PER_THEME: dict[str, Dict[str, Any]] = {}
_PREVIEW_PER_THEME_REQUESTS: dict[str, int] = {}
_PREVIEW_PER_THEME_ERRORS: dict[str, int] = {}
_PREVIEW_REQUESTS = 0
_PREVIEW_CACHE_HITS = 0
_PREVIEW_ERROR_COUNT = 0
_PREVIEW_REQUEST_ERROR_COUNT = 0
_EVICTION_TOTAL = 0
_EVICTION_BY_REASON: dict[str, int] = {}
_EVICTION_LAST: dict[str, Any] | None = None
_SPLASH_OFF_COLOR_TOTAL = 0
_SPLASH_PREVIEWS_WITH_PENALTY = 0
_SPLASH_PENALTY_CARD_EVENTS = 0
_REDIS_GET_ATTEMPTS = 0
_REDIS_GET_HITS = 0
_REDIS_GET_ERRORS = 0
_REDIS_STORE_ATTEMPTS = 0
_REDIS_STORE_ERRORS = 0

def record_redis_get(hit: bool, error: bool = False):
    global _REDIS_GET_ATTEMPTS, _REDIS_GET_HITS, _REDIS_GET_ERRORS
    _REDIS_GET_ATTEMPTS += 1
    if hit:
        _REDIS_GET_HITS += 1
    if error:
        _REDIS_GET_ERRORS += 1

def record_redis_store(error: bool = False):
    global _REDIS_STORE_ATTEMPTS, _REDIS_STORE_ERRORS
    _REDIS_STORE_ATTEMPTS += 1
    if error:
        _REDIS_STORE_ERRORS += 1

# External state accessors (injected via set functions) to avoid import cycle
_ttl_seconds_fn = None
_recent_hit_window_fn = None
_cache_len_fn = None
_last_bust_at_fn = None
_curated_synergy_loaded_fn = None
_curated_synergy_size_fn = None

def configure_external_access(
    ttl_seconds_fn,
    recent_hit_window_fn,
    cache_len_fn,
    last_bust_at_fn,
    curated_synergy_loaded_fn,
    curated_synergy_size_fn,
):
    global _ttl_seconds_fn, _recent_hit_window_fn, _cache_len_fn, _last_bust_at_fn, _curated_synergy_loaded_fn, _curated_synergy_size_fn
    _ttl_seconds_fn = ttl_seconds_fn
    _recent_hit_window_fn = recent_hit_window_fn
    _cache_len_fn = cache_len_fn
    _last_bust_at_fn = last_bust_at_fn
    _curated_synergy_loaded_fn = curated_synergy_loaded_fn
    _curated_synergy_size_fn = curated_synergy_size_fn

def record_build_duration(ms: float) -> None:
    global _PREVIEW_BUILD_MS_TOTAL, _PREVIEW_BUILD_COUNT
    _PREVIEW_BUILD_MS_TOTAL += ms
    _PREVIEW_BUILD_COUNT += 1
    _BUILD_DURATIONS.append(ms)

def record_role_counts(role_counts: Dict[str, int]) -> None:
    for r, c in role_counts.items():
        _ROLE_GLOBAL_COUNTS[r] = _ROLE_GLOBAL_COUNTS.get(r, 0) + c

def record_curated_sampled(curated: int, sampled: int) -> None:
    global _CURATED_GLOBAL, _SAMPLED_GLOBAL
    _CURATED_GLOBAL += curated
    _SAMPLED_GLOBAL += sampled

def record_per_theme(slug: str, build_ms: float, curated: int, sampled: int) -> None:
    data = _PREVIEW_PER_THEME.setdefault(slug, {"total_ms": 0.0, "builds": 0, "durations": [], "curated": 0, "sampled": 0})
    data["total_ms"] += build_ms
    data["builds"] += 1
    durs = data["durations"]
    durs.append(build_ms)
    if len(durs) > 100:
        del durs[0: len(durs) - 100]
    data["curated"] += curated
    data["sampled"] += sampled

def record_request(hit: bool, error: bool = False, client_error: bool = False) -> None:
    global _PREVIEW_REQUESTS, _PREVIEW_CACHE_HITS, _PREVIEW_ERROR_COUNT, _PREVIEW_REQUEST_ERROR_COUNT
    _PREVIEW_REQUESTS += 1
    if hit:
        _PREVIEW_CACHE_HITS += 1
    if error:
        _PREVIEW_ERROR_COUNT += 1
    if client_error:
        _PREVIEW_REQUEST_ERROR_COUNT += 1

def record_per_theme_error(slug: str) -> None:
    _PREVIEW_PER_THEME_ERRORS[slug] = _PREVIEW_PER_THEME_ERRORS.get(slug, 0) + 1

def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1

def preview_metrics() -> Dict[str, Any]:
    ttl_seconds = _ttl_seconds_fn() if _ttl_seconds_fn else 0
    recent_window = _recent_hit_window_fn() if _recent_hit_window_fn else 0
    cache_len = _cache_len_fn() if _cache_len_fn else 0
    last_bust = _last_bust_at_fn() if _last_bust_at_fn else None
    avg_ms = (_PREVIEW_BUILD_MS_TOTAL / _PREVIEW_BUILD_COUNT) if _PREVIEW_BUILD_COUNT else 0.0
    durations_list = sorted(list(_BUILD_DURATIONS))
    p95 = _percentile(durations_list, 0.95)
    # Role distribution aggregate
    total_roles = sum(_ROLE_GLOBAL_COUNTS.values()) or 1
    target = {"payoff": 0.4, "enabler+support": 0.4, "wildcard": 0.2}
    actual_enabler_support = (_ROLE_GLOBAL_COUNTS.get("enabler", 0) + _ROLE_GLOBAL_COUNTS.get("support", 0)) / total_roles
    role_distribution = {
        "payoff": {
            "count": _ROLE_GLOBAL_COUNTS.get("payoff", 0),
            "actual_pct": round((_ROLE_GLOBAL_COUNTS.get("payoff", 0) / total_roles) * 100, 2),
            "target_pct": target["payoff"] * 100,
        },
        "enabler_support": {
            "count": _ROLE_GLOBAL_COUNTS.get("enabler", 0) + _ROLE_GLOBAL_COUNTS.get("support", 0),
            "actual_pct": round(actual_enabler_support * 100, 2),
            "target_pct": target["enabler+support"] * 100,
        },
        "wildcard": {
            "count": _ROLE_GLOBAL_COUNTS.get("wildcard", 0),
            "actual_pct": round((_ROLE_GLOBAL_COUNTS.get("wildcard", 0) / total_roles) * 100, 2),
            "target_pct": target["wildcard"] * 100,
        },
    }
    editorial_coverage_pct = round((_CURATED_GLOBAL / max(1, (_CURATED_GLOBAL + _SAMPLED_GLOBAL))) * 100, 2)
    per_theme_stats: Dict[str, Any] = {}
    for slug, data in list(_PREVIEW_PER_THEME.items())[:50]:
        durs = list(data.get("durations", []))
        sd = sorted(durs)
        p50 = _percentile(sd, 0.50)
        p95_local = _percentile(sd, 0.95)
        per_theme_stats[slug] = {
            "avg_ms": round(data["total_ms"] / max(1, data["builds"]), 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95_local, 2),
            "builds": data["builds"],
            "avg_curated_pct": round((data["curated"] / max(1, (data["curated"] + data["sampled"])) ) * 100, 2),
            "requests": _PREVIEW_PER_THEME_REQUESTS.get(slug, 0),
            "curated_total": data.get("curated", 0),
            "sampled_total": data.get("sampled", 0),
        }
    error_rate = 0.0
    total_req = _PREVIEW_REQUESTS or 0
    if total_req:
        error_rate = round((_PREVIEW_ERROR_COUNT / total_req) * 100, 2)
    try:
        enforce_threshold = float(os.getenv("EXAMPLE_ENFORCE_THRESHOLD", "90"))
    except Exception:  # pragma: no cover
        enforce_threshold = 90.0
    example_enforcement_active = editorial_coverage_pct >= enforce_threshold
    curated_synergy_loaded = _curated_synergy_loaded_fn() if _curated_synergy_loaded_fn else False
    curated_synergy_size = _curated_synergy_size_fn() if _curated_synergy_size_fn else 0
    return {
        "preview_requests": _PREVIEW_REQUESTS,
        "preview_cache_hits": _PREVIEW_CACHE_HITS,
        "preview_cache_entries": cache_len,
        "preview_cache_evictions": _EVICTION_TOTAL,
        "preview_cache_evictions_by_reason": dict(_EVICTION_BY_REASON),
        "preview_cache_eviction_last": _EVICTION_LAST,
        "preview_avg_build_ms": round(avg_ms, 2),
        "preview_p95_build_ms": round(p95, 2),
        "preview_error_rate_pct": error_rate,
        "preview_client_fetch_errors": _PREVIEW_REQUEST_ERROR_COUNT,
        "preview_ttl_seconds": ttl_seconds,
        "preview_ttl_adaptive": True,
        "preview_ttl_window": recent_window,
        "preview_last_bust_at": last_bust,
        "role_distribution": role_distribution,
        "editorial_curated_vs_sampled_pct": editorial_coverage_pct,
        "example_enforcement_active": example_enforcement_active,
        "example_enforce_threshold_pct": enforce_threshold,
        "editorial_curated_total": _CURATED_GLOBAL,
        "editorial_sampled_total": _SAMPLED_GLOBAL,
        "per_theme": per_theme_stats,
        "per_theme_errors": dict(list(_PREVIEW_PER_THEME_ERRORS.items())[:50]),
        "curated_synergy_matrix_loaded": curated_synergy_loaded,
        "curated_synergy_matrix_size": curated_synergy_size,
        "splash_off_color_total_cards": _SPLASH_OFF_COLOR_TOTAL,
        "splash_previews_with_penalty": _SPLASH_PREVIEWS_WITH_PENALTY,
        "splash_penalty_reason_events": _SPLASH_PENALTY_CARD_EVENTS,
        "redis_get_attempts": _REDIS_GET_ATTEMPTS,
        "redis_get_hits": _REDIS_GET_HITS,
        "redis_get_errors": _REDIS_GET_ERRORS,
        "redis_store_attempts": _REDIS_STORE_ATTEMPTS,
        "redis_store_errors": _REDIS_STORE_ERRORS,
    }

__all__ = [
    "record_build_duration",
    "record_role_counts",
    "record_curated_sampled",
    "record_per_theme",
    "record_request",
    "record_per_theme_request",
    "record_per_theme_error",
    "record_eviction",
    "preview_metrics",
    "configure_external_access",
    "record_splash_analytics",
    "record_redis_get",
    "record_redis_store",
]

def record_per_theme_request(slug: str) -> None:
    """Increment request counter for a specific theme (cache hit or miss).

    This was previously in the monolith; extracted to keep per-theme request
    counts consistent with new metrics module ownership.
    """
    _PREVIEW_PER_THEME_REQUESTS[slug] = _PREVIEW_PER_THEME_REQUESTS.get(slug, 0) + 1

def record_eviction(meta: Dict[str, Any]) -> None:
    """Record a cache eviction event.

    meta expected keys: reason, hit_count, age_ms, build_cost_ms, protection_score, cache_limit,
    size_before, size_after.
    """
    global _EVICTION_TOTAL, _EVICTION_LAST
    _EVICTION_TOTAL += 1
    reason = meta.get("reason", "unknown")
    _EVICTION_BY_REASON[reason] = _EVICTION_BY_REASON.get(reason, 0) + 1
    _EVICTION_LAST = meta
    # Optional structured log
    try:  # pragma: no cover
        if (os.getenv("WEB_THEME_PREVIEW_LOG") or "").lower() in {"1","true","yes","on"}:
            import json as _json
            print(_json.dumps({"event": "theme_preview_cache_evict", **meta}, separators=(",",":")))  # noqa: T201
    except Exception:
        pass

def record_splash_analytics(off_color_card_count: int, penalty_reason_events: int) -> None:
    """Record splash off-color analytics for a single preview build.

    off_color_card_count: number of sampled cards marked with _splash_off_color flag.
    penalty_reason_events: count of 'splash_off_color_penalty' reason entries encountered.
    """
    global _SPLASH_OFF_COLOR_TOTAL, _SPLASH_PREVIEWS_WITH_PENALTY, _SPLASH_PENALTY_CARD_EVENTS
    if off_color_card_count > 0:
        _SPLASH_PREVIEWS_WITH_PENALTY += 1
        _SPLASH_OFF_COLOR_TOTAL += off_color_card_count
    if penalty_reason_events > 0:
        _SPLASH_PENALTY_CARD_EVENTS += penalty_reason_events
