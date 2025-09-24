"""Scoring & sampling configuration constants (Phase 2 extraction).

Centralizes knobs used by the sampling pipeline so future tuning (or
experimentation via environment variables) can occur without editing the
core algorithm code.

Public constants (import into sampling.py and tests):
    COMMANDER_COLOR_FILTER_STRICT
    COMMANDER_OVERLAP_BONUS
    COMMANDER_THEME_MATCH_BONUS
    SPLASH_OFF_COLOR_PENALTY
    ROLE_BASE_WEIGHTS
    ROLE_SATURATION_PENALTY

Helper functions:
    rarity_weight_base()  -> dict[str, float]
        Returns per-rarity base weights (reads env each call to preserve
        existing test expectations that patch env before invoking sampling).
"""
from __future__ import annotations

import os
from typing import Dict, Tuple, Optional

# Commander related bonuses (identical defaults to previous inline values)
COMMANDER_COLOR_FILTER_STRICT = True
COMMANDER_OVERLAP_BONUS = 1.8
COMMANDER_THEME_MATCH_BONUS = 0.9

# Penalties / bonuses
SPLASH_OFF_COLOR_PENALTY = -0.3
# Adaptive splash penalty feature flag & scaling factors.
# When SPLASH_ADAPTIVE=1 the effective penalty becomes:
#   base_penalty * splash_adaptive_scale(color_count)
# Where color_count is the number of distinct commander colors (1-5).
# Default scale keeps existing behavior at 1-3 colors, softens at 4, much lighter at 5.
SPLASH_ADAPTIVE_ENABLED = os.getenv("SPLASH_ADAPTIVE", "0") == "1"
_DEFAULT_SPLASH_SCALE = "1:1.0,2:1.0,3:1.0,4:0.6,5:0.35"
def parse_splash_adaptive_scale() -> Dict[int, float]:  # dynamic to allow test env changes
    spec = os.getenv("SPLASH_ADAPTIVE_SCALE", _DEFAULT_SPLASH_SCALE)
    mapping: Dict[int, float] = {}
    for part in spec.split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        k_s, v_s = part.split(':', 1)
        try:
            k = int(k_s)
            v = float(v_s)
            if 1 <= k <= 5 and v > 0:
                mapping[k] = v
        except Exception:
            continue
    # Ensure all 1-5 present; fallback to 1.0 if unspecified
    for i in range(1, 6):
        mapping.setdefault(i, 1.0)
    return mapping
ROLE_SATURATION_PENALTY = -0.4

# Base role weights applied inside score calculation
ROLE_BASE_WEIGHTS: Dict[str, float] = {
    "payoff": 2.5,
    "enabler": 2.0,
    "support": 1.5,
    "wildcard": 0.9,
}

# Rarity base weights (diminishing duplicate influence applied in sampling pipeline)
# Read from env at call time to allow tests to modify.

def rarity_weight_base() -> Dict[str, float]:  # dynamic to allow env override per test
    return {
        "mythic": float(os.getenv("RARITY_W_MYTHIC", "1.2")),
        "rare": float(os.getenv("RARITY_W_RARE", "0.9")),
        "uncommon": float(os.getenv("RARITY_W_UNCOMMON", "0.65")),
        "common": float(os.getenv("RARITY_W_COMMON", "0.4")),
    }

__all__ = [
    "COMMANDER_COLOR_FILTER_STRICT",
    "COMMANDER_OVERLAP_BONUS",
    "COMMANDER_THEME_MATCH_BONUS",
    "SPLASH_OFF_COLOR_PENALTY",
    "SPLASH_ADAPTIVE_ENABLED",
    "parse_splash_adaptive_scale",
    "ROLE_BASE_WEIGHTS",
    "ROLE_SATURATION_PENALTY",
    "rarity_weight_base",
    "parse_rarity_diversity_targets",
    "RARITY_DIVERSITY_OVER_PENALTY",
]


# Extended rarity diversity (optional) ---------------------------------------
# Env var RARITY_DIVERSITY_TARGETS pattern e.g. "mythic:0-1,rare:0-2,uncommon:0-4,common:0-6"
# Parsed into mapping rarity -> (min,max). Only max is enforced currently (penalty applied
# when overflow occurs); min reserved for potential future boosting logic.

RARITY_DIVERSITY_OVER_PENALTY = float(os.getenv("RARITY_DIVERSITY_OVER_PENALTY", "-0.5"))

def parse_rarity_diversity_targets() -> Optional[Dict[str, Tuple[int, int]]]:
    spec = os.getenv("RARITY_DIVERSITY_TARGETS")
    if not spec:
        return None
    targets: Dict[str, Tuple[int, int]] = {}
    for part in spec.split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        name, rng = part.split(':', 1)
        name = name.strip().lower()
        if '-' not in rng:
            continue
        lo_s, hi_s = rng.split('-', 1)
        try:
            lo = int(lo_s)
            hi = int(hi_s)
            if lo < 0 or hi < lo:
                continue
            targets[name] = (lo, hi)
        except Exception:
            continue
    return targets or None
