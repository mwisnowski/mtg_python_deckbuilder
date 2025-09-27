"""Preview policy module (Phase 2 extraction).

Extracts adaptive TTL band logic so experimentation can occur without
touching core cache data structures. Future extensions will add:
 - Environment-variable overrides for band thresholds & step sizes
 - Adaptive eviction strategy (hit-ratio + recency hybrid)
 - Backend abstraction tuning knobs (e.g., Redis TTL harmonization)

Current exported API is intentionally small/stable:

compute_ttl_adjustment(hit_ratio: float, current_ttl: int,
                       base: int = DEFAULT_TTL_BASE,
                       ttl_min: int = DEFAULT_TTL_MIN,
                       ttl_max: int = DEFAULT_TTL_MAX) -> int
    Given the recent hit ratio (0..1) and current TTL, returns the new TTL
    after applying banded adjustment rules. Never mutates globals; caller
    decides whether to commit the change.

Constants kept here mirror the prior inline values from preview_cache.
They are NOT yet configurable via env to keep behavior unchanged for
existing tests. A follow-up task will add env override + validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

__all__ = [
    "DEFAULT_TTL_BASE",
    "DEFAULT_TTL_MIN",
    "DEFAULT_TTL_MAX",
    "BAND_LOW_CRITICAL",
    "BAND_LOW_MODERATE",
    "BAND_HIGH_GROW",
    "compute_ttl_adjustment",
]

DEFAULT_TTL_BASE = 600
DEFAULT_TTL_MIN = 300
DEFAULT_TTL_MAX = 900

# Default hit ratio band thresholds (exclusive upper bounds for each tier)
_DEFAULT_BAND_LOW_CRITICAL = 0.25   # Severe miss rate – shrink TTL aggressively
_DEFAULT_BAND_LOW_MODERATE = 0.55   # Mild miss bias – converge back toward base
_DEFAULT_BAND_HIGH_GROW = 0.75      # Healthy hit rate – modest growth

# Public band variables (may be overridden via env at import time)
BAND_LOW_CRITICAL = _DEFAULT_BAND_LOW_CRITICAL
BAND_LOW_MODERATE = _DEFAULT_BAND_LOW_MODERATE
BAND_HIGH_GROW = _DEFAULT_BAND_HIGH_GROW

@dataclass(frozen=True)
class AdjustmentSteps:
    low_critical: int = -60
    low_mod_decrease: int = -30
    low_mod_increase: int = 30
    high_grow: int = 60
    high_peak: int = 90  # very high hit ratio

_STEPS = AdjustmentSteps()

# --- Environment Override Support (POLICY Env overrides task) --- #
_ENV_APPLIED = False

def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        v = float(raw)
        if not (0.0 <= v <= 1.0):
            return default
        return v
    except Exception:
        return default

def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default

def _apply_env_overrides() -> None:
    """Idempotently apply environment overrides for bands & step sizes.

    Env vars:
      THEME_PREVIEW_TTL_BASE / _MIN / _MAX (ints)
      THEME_PREVIEW_TTL_BANDS (comma floats: low_critical,low_moderate,high_grow)
      THEME_PREVIEW_TTL_STEPS (comma ints: low_critical,low_mod_dec,low_mod_inc,high_grow,high_peak)
    Invalid / partial specs fall back to defaults. Bands are validated to be
    strictly increasing within (0,1). If validation fails, defaults retained.
    """
    global DEFAULT_TTL_BASE, DEFAULT_TTL_MIN, DEFAULT_TTL_MAX
    global BAND_LOW_CRITICAL, BAND_LOW_MODERATE, BAND_HIGH_GROW, _STEPS, _ENV_APPLIED
    if _ENV_APPLIED:
        return
    DEFAULT_TTL_BASE = _parse_int_env("THEME_PREVIEW_TTL_BASE", DEFAULT_TTL_BASE)
    DEFAULT_TTL_MIN = _parse_int_env("THEME_PREVIEW_TTL_MIN", DEFAULT_TTL_MIN)
    DEFAULT_TTL_MAX = _parse_int_env("THEME_PREVIEW_TTL_MAX", DEFAULT_TTL_MAX)
    # Ensure ordering min <= base <= max
    if DEFAULT_TTL_MIN > DEFAULT_TTL_BASE:
        DEFAULT_TTL_MIN = min(DEFAULT_TTL_MIN, DEFAULT_TTL_BASE)
    if DEFAULT_TTL_BASE > DEFAULT_TTL_MAX:
        DEFAULT_TTL_MAX = max(DEFAULT_TTL_BASE, DEFAULT_TTL_MAX)
    bands_raw = os.getenv("THEME_PREVIEW_TTL_BANDS")
    if bands_raw:
        parts = [p.strip() for p in bands_raw.split(',') if p.strip()]
        vals: list[float] = []
        for p in parts[:3]:
            try:
                vals.append(float(p))
            except Exception:
                pass
        if len(vals) == 3:
            a, b, c = vals
            if 0 < a < b < c < 1:
                BAND_LOW_CRITICAL, BAND_LOW_MODERATE, BAND_HIGH_GROW = a, b, c
    steps_raw = os.getenv("THEME_PREVIEW_TTL_STEPS")
    if steps_raw:
        parts = [p.strip() for p in steps_raw.split(',') if p.strip()]
        ints: list[int] = []
        for p in parts[:5]:
            try:
                ints.append(int(p))
            except Exception:
                pass
        if len(ints) == 5:
            _STEPS = AdjustmentSteps(
                low_critical=ints[0],
                low_mod_decrease=ints[1],
                low_mod_increase=ints[2],
                high_grow=ints[3],
                high_peak=ints[4],
            )
    _ENV_APPLIED = True

# Apply overrides at import time (safe & idempotent)
_apply_env_overrides()

def compute_ttl_adjustment(
    hit_ratio: float,
    current_ttl: int,
    base: int = DEFAULT_TTL_BASE,
    ttl_min: int = DEFAULT_TTL_MIN,
    ttl_max: int = DEFAULT_TTL_MAX,
) -> int:
    """Return a new TTL based on hit ratio & current TTL.

    Logic mirrors the original inline implementation; extracted for clarity.
    """
    new_ttl = current_ttl
    if hit_ratio < BAND_LOW_CRITICAL:
        new_ttl = max(ttl_min, current_ttl + _STEPS.low_critical)
    elif hit_ratio < BAND_LOW_MODERATE:
        if current_ttl > base:
            new_ttl = max(base, current_ttl + _STEPS.low_mod_decrease)
        elif current_ttl < base:
            new_ttl = min(base, current_ttl + _STEPS.low_mod_increase)
        # else already at base – no change
    elif hit_ratio < BAND_HIGH_GROW:
        new_ttl = min(ttl_max, current_ttl + _STEPS.high_grow)
    else:
        new_ttl = min(ttl_max, current_ttl + _STEPS.high_peak)
    return new_ttl
