"""Preview cache utilities & adaptive policy (Core Refactor Phase A continued).

This module now owns:
    - In-memory preview cache (OrderedDict)
    - Cache bust helper
    - Adaptive TTL policy & recent hit tracking
    - Background refresh thread orchestration (warming top-K hot themes)

`theme_preview` orchestrator invokes `record_request_hit()` and
`maybe_adapt_ttl()` after each build/cache check, and calls `ensure_bg_thread()`
post-build. Metrics still aggregated in `theme_preview` but TTL state lives
here to prepare for future backend abstraction.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from typing import Any, Dict, Tuple, Callable
import time as _t
import os
import json
import threading
import math

from .preview_metrics import record_eviction

# Phase 2 extraction: adaptive TTL band policy moved into preview_policy
from .preview_policy import (
    compute_ttl_adjustment,
    DEFAULT_TTL_BASE as _POLICY_TTL_BASE,
    DEFAULT_TTL_MIN as _POLICY_TTL_MIN,
    DEFAULT_TTL_MAX as _POLICY_TTL_MAX,
)
from .preview_cache_backend import redis_store

TTL_SECONDS = 600
# Backward-compat variable names retained (tests may reference) mapping to policy constants
_TTL_BASE = _POLICY_TTL_BASE
_TTL_MIN = _POLICY_TTL_MIN
_TTL_MAX = _POLICY_TTL_MAX
_ADAPT_SAMPLE_WINDOW = 120
_ADAPT_INTERVAL_S = 30
_ADAPTATION_ENABLED = (os.getenv("THEME_PREVIEW_ADAPTIVE") or "").lower() in {"1","true","yes","on"}
_RECENT_HITS: "deque[bool]" = deque(maxlen=_ADAPT_SAMPLE_WINDOW)
_LAST_ADAPT_AT: float | None = None

_BG_REFRESH_THREAD_STARTED = False
_BG_REFRESH_INTERVAL_S = int(os.getenv("THEME_PREVIEW_BG_REFRESH_INTERVAL") or 120)
_BG_REFRESH_ENABLED = (os.getenv("THEME_PREVIEW_BG_REFRESH") or "").lower() in {"1","true","yes","on"}
_BG_REFRESH_MIN = 30
_BG_REFRESH_MAX = max(300, _BG_REFRESH_INTERVAL_S * 5)

def record_request_hit(hit: bool) -> None:
    _RECENT_HITS.append(hit)

def recent_hit_window() -> int:
    return len(_RECENT_HITS)

def ttl_seconds() -> int:
    return TTL_SECONDS

def _maybe_adapt_ttl(now: float) -> None:
    """Apply adaptive TTL adjustment using extracted policy.

    Keeps prior guards (sample window, interval) for stability; only the
    banded adjustment math has moved to preview_policy.
    """
    global TTL_SECONDS, _LAST_ADAPT_AT
    if not _ADAPTATION_ENABLED:
        return
    if len(_RECENT_HITS) < max(30, int(_ADAPT_SAMPLE_WINDOW * 0.5)):
        return
    if _LAST_ADAPT_AT and (now - _LAST_ADAPT_AT) < _ADAPT_INTERVAL_S:
        return
    hit_ratio = sum(1 for h in _RECENT_HITS if h) / len(_RECENT_HITS)
    new_ttl = compute_ttl_adjustment(hit_ratio, TTL_SECONDS, _TTL_BASE, _TTL_MIN, _TTL_MAX)
    if new_ttl != TTL_SECONDS:
        TTL_SECONDS = new_ttl
        try:  # pragma: no cover - defensive logging
            print(json.dumps({
                "event": "theme_preview_ttl_adapt",
                "hit_ratio": round(hit_ratio, 3),
                "ttl": TTL_SECONDS,
            }))  # noqa: T201
        except Exception:
            pass
    _LAST_ADAPT_AT = now

def maybe_adapt_ttl() -> None:
    _maybe_adapt_ttl(_t.time())

def _bg_refresh_loop(build_top_slug: Callable[[str], None], get_hot_slugs: Callable[[], list[str]]):  # pragma: no cover
    while True:
        if not _BG_REFRESH_ENABLED:
            return
        try:
            for slug in get_hot_slugs():
                try:
                    build_top_slug(slug)
                except Exception:
                    continue
        except Exception:
            pass
        _t.sleep(_BG_REFRESH_INTERVAL_S)

def ensure_bg_thread(build_top_slug: Callable[[str], None], get_hot_slugs: Callable[[], list[str]]):  # pragma: no cover
    global _BG_REFRESH_THREAD_STARTED
    if _BG_REFRESH_THREAD_STARTED or not _BG_REFRESH_ENABLED:
        return
    try:
        th = threading.Thread(target=_bg_refresh_loop, args=(build_top_slug, get_hot_slugs), name="theme_preview_bg_refresh", daemon=True)
        th.start()
        _BG_REFRESH_THREAD_STARTED = True
    except Exception:
        pass

PREVIEW_CACHE: "OrderedDict[Tuple[str, int, str | None, str | None, str], Dict[str, Any]]" = OrderedDict()
# Cache entry shape (dict) — groundwork for adaptive eviction (Phase 2)
# Keys:
#   payload: preview payload dict
#   _cached_at / cached_at: epoch seconds when stored (TTL reference; _cached_at kept for backward compat)
#   inserted_at: epoch seconds first insertion
#   last_access: epoch seconds of last successful cache hit
#   hit_count: int number of cache hits (excludes initial store)
#   build_cost_ms: float build duration captured at store time (used for cost-based protection)

def register_cache_hit(key: Tuple[str, int, str | None, str | None, str]) -> None:
    entry = PREVIEW_CACHE.get(key)
    if not entry:
        return
    now = _t.time()
    # Initialize metadata if legacy entry present
    if "inserted_at" not in entry:
        entry["inserted_at"] = entry.get("_cached_at", now)
    entry["last_access"] = now
    entry["hit_count"] = int(entry.get("hit_count", 0)) + 1

def store_cache_entry(key: Tuple[str, int, str | None, str | None, str], payload: Dict[str, Any], build_cost_ms: float) -> None:
    now = _t.time()
    PREVIEW_CACHE[key] = {
        "payload": payload,
        "_cached_at": now,  # legacy field name
        "cached_at": now,
        "inserted_at": now,
        "last_access": now,
        "hit_count": 0,
        "build_cost_ms": float(build_cost_ms),
    }
    PREVIEW_CACHE.move_to_end(key)
    # Optional Redis write-through (best-effort)
    try:
        if os.getenv("THEME_PREVIEW_REDIS_URL") and not os.getenv("THEME_PREVIEW_REDIS_DISABLE"):
            redis_store(key, payload, int(TTL_SECONDS), build_cost_ms)
    except Exception:
        pass

# --- Adaptive Eviction Weight & Threshold Resolution (Phase 2 Step 4) --- #
_EVICT_WEIGHTS_CACHE: Dict[str, float] | None = None
_EVICT_THRESH_CACHE: Tuple[float, float, float] | None = None

def _resolve_eviction_weights() -> Dict[str, float]:
    global _EVICT_WEIGHTS_CACHE
    if _EVICT_WEIGHTS_CACHE is not None:
        return _EVICT_WEIGHTS_CACHE
    def _f(env_key: str, default: float) -> float:
        raw = os.getenv(env_key)
        if not raw:
            return default
        try:
            return float(raw)
        except Exception:
            return default
    _EVICT_WEIGHTS_CACHE = {
        "W_HITS": _f("THEME_PREVIEW_EVICT_W_HITS", 3.0),
        "W_RECENCY": _f("THEME_PREVIEW_EVICT_W_RECENCY", 2.0),
        "W_COST": _f("THEME_PREVIEW_EVICT_W_COST", 1.0),
        "W_AGE": _f("THEME_PREVIEW_EVICT_W_AGE", 1.5),
    }
    return _EVICT_WEIGHTS_CACHE

def _resolve_cost_thresholds() -> Tuple[float, float, float]:
    global _EVICT_THRESH_CACHE
    if _EVICT_THRESH_CACHE is not None:
        return _EVICT_THRESH_CACHE
    raw = os.getenv("THEME_PREVIEW_EVICT_COST_THRESHOLDS", "5,15,40")
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    nums: list[float] = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            pass
    while len(nums) < 3:
        # pad with defaults if insufficient
        defaults = [5.0, 15.0, 40.0]
        nums.append(defaults[len(nums)])
    nums = sorted(nums[:3])
    _EVICT_THRESH_CACHE = (nums[0], nums[1], nums[2])
    return _EVICT_THRESH_CACHE

def _cost_bucket(build_cost_ms: float) -> int:
    t1, t2, t3 = _resolve_cost_thresholds()
    if build_cost_ms < t1:
        return 0
    if build_cost_ms < t2:
        return 1
    if build_cost_ms < t3:
        return 2
    return 3

def compute_protection_score(entry: Dict[str, Any], now: float | None = None) -> float:
    """Compute protection score (higher = more protected from eviction).

    Score components:
      - hit_count (log scaled) weighted by W_HITS
      - recency (inverse minutes since last access) weighted by W_RECENCY
      - build cost bucket weighted by W_COST
      - age penalty (minutes since insert) weighted by W_AGE (subtracted)
    """
    if now is None:
        now = _t.time()
    weights = _resolve_eviction_weights()
    inserted = float(entry.get("inserted_at", now))
    last_access = float(entry.get("last_access", inserted))
    hits = int(entry.get("hit_count", 0))
    build_cost_ms = float(entry.get("build_cost_ms", 0.0))
    minutes_since_last = max(0.0, (now - last_access) / 60.0)
    minutes_since_insert = max(0.0, (now - inserted) / 60.0)
    recency_score = 1.0 / (1.0 + minutes_since_last)
    age_score = minutes_since_insert
    cost_b = _cost_bucket(build_cost_ms)
    score = (
        weights["W_HITS"] * math.log(1 + hits)
        + weights["W_RECENCY"] * recency_score
        + weights["W_COST"] * cost_b
        - weights["W_AGE"] * age_score
    )
    return float(score)

# --- Eviction Logic (Phase 2 Step 6) --- #
def _cache_max() -> int:
    try:
        raw = os.getenv("THEME_PREVIEW_CACHE_MAX") or "400"
        v = int(raw)
        if v <= 0:
            raise ValueError
        return v
    except Exception:
        return 400

def evict_if_needed() -> None:
    """Adaptive eviction replacing FIFO.

    Strategy:
      - If size <= limit: no-op
      - If size > 2*limit: emergency overflow path (age-based removal until within limit)
      - Else: remove lowest protection score entry (single) if over limit
    """
    try:
        # Removed previous hard floor (50) to allow test scenarios with small limits.
        # Operational deployments can still set higher env value. Tests rely on low limits
        # (e.g., 5) to exercise eviction deterministically.
        limit = _cache_max()
        size = len(PREVIEW_CACHE)
        if size <= limit:
            return
        now = _t.time()
        # Emergency overflow path
        if size > 2 * limit:
            while len(PREVIEW_CACHE) > limit:
                # Oldest by inserted_at/_cached_at
                oldest_key = min(
                    PREVIEW_CACHE.items(),
                    key=lambda kv: kv[1].get("inserted_at", kv[1].get("_cached_at", 0.0)),
                )[0]
                entry = PREVIEW_CACHE.pop(oldest_key)
                meta = {
                    "hit_count": int(entry.get("hit_count", 0)),
                    "age_ms": int((now - entry.get("inserted_at", now)) * 1000),
                    "build_cost_ms": float(entry.get("build_cost_ms", 0.0)),
                    "protection_score": compute_protection_score(entry, now),
                    "reason": "emergency_overflow",
                    "cache_limit": limit,
                    "size_before": size,
                    "size_after": len(PREVIEW_CACHE),
                }
                record_eviction(meta)
            return
        # Standard single-entry score-based eviction
        lowest_key = None
        lowest_score = None
        for key, entry in PREVIEW_CACHE.items():
            score = compute_protection_score(entry, now)
            if lowest_score is None or score < lowest_score:
                lowest_key = key
                lowest_score = score
        if lowest_key is not None:
            entry = PREVIEW_CACHE.pop(lowest_key)
            meta = {
                "hit_count": int(entry.get("hit_count", 0)),
                "age_ms": int((now - entry.get("inserted_at", now)) * 1000),
                "build_cost_ms": float(entry.get("build_cost_ms", 0.0)),
                "protection_score": float(lowest_score if lowest_score is not None else 0.0),
                "reason": "low_score",
                "cache_limit": limit,
                "size_before": size,
                "size_after": len(PREVIEW_CACHE),
            }
            record_eviction(meta)
    except Exception:
        # Fail quiet; eviction is best-effort
        pass
_PREVIEW_LAST_BUST_AT: float | None = None

def bust_preview_cache(reason: str | None = None) -> None:  # pragma: no cover (trivial)
    global PREVIEW_CACHE, _PREVIEW_LAST_BUST_AT
    try:
        PREVIEW_CACHE.clear()
        _PREVIEW_LAST_BUST_AT = _t.time()
    except Exception:
        pass

def preview_cache_last_bust_at() -> float | None:
    return _PREVIEW_LAST_BUST_AT
