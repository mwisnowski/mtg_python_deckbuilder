from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import time
import pandas as pd

from deck_builder import builder_constants as bc
from random_util import get_random, generate_seed


@dataclass
class RandomBuildResult:
    seed: int
    commander: str
    theme: Optional[str]
    constraints: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": int(self.seed),
            "commander": self.commander,
            "theme": self.theme,
            "constraints": self.constraints or {},
        }


def _load_commanders_df() -> pd.DataFrame:
    """Load commander CSV using the same path/converters as the builder.

    Uses bc.COMMANDER_CSV_PATH and bc.COMMANDER_CONVERTERS for consistency.
    """
    return pd.read_csv(bc.COMMANDER_CSV_PATH, converters=getattr(bc, "COMMANDER_CONVERTERS", None))


def _filter_by_theme(df: pd.DataFrame, theme: Optional[str]) -> pd.DataFrame:
    if not theme:
        return df
    t = str(theme).strip().lower()
    try:
        mask = df.get("themeTags").apply(
            lambda tags: any(str(x).strip().lower() == t for x in (tags or []))
        )
        sub = df[mask]
        if len(sub) > 0:
            return sub
    except Exception:
        pass
    return df


def build_random_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
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

    # Load commander pool and apply theme filter (if any)
    df_all = _load_commanders_df()
    df = _filter_by_theme(df_all, theme)
    # Stable ordering then seeded selection for deterministic behavior
    names: List[str] = sorted(df["name"].astype(str).tolist()) if not df.empty else []
    if not names:
        # Fall back to entire pool by name if theme produced nothing
        names = sorted(df_all["name"].astype(str).tolist())
    if not names:
        # Absolute fallback for pathological cases
        names = ["Unknown Commander"]

    # Simple attempt/timeout loop (placeholder for future constraints checks)
    start = time.time()
    pick = None
    for _ in range(attempts):
        if (time.time() - start) > timeout_s:
            break
        idx = rng.randrange(0, len(names))
        candidate = names[idx]
        # For now, accept the first candidate; constraint hooks can be added here.
        pick = candidate
        break
    if pick is None:
        # Timeout/attempts exhausted; choose deterministically based on seed modulo
        pick = names[resolved_seed % len(names)]

    return RandomBuildResult(seed=int(resolved_seed), commander=pick, theme=theme, constraints=constraints or {})


__all__ = [
    "RandomBuildResult",
    "build_random_deck",
]


# Full-build wrapper for deterministic end-to-end builds
@dataclass
class RandomFullBuildResult(RandomBuildResult):
    decklist: List[Dict[str, Any]] | None = None
    diagnostics: Dict[str, Any] | None = None


def build_random_full_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
) -> RandomFullBuildResult:
    """Select a commander deterministically, then run a full deck build via DeckBuilder.

    Returns a compact result including the seed, commander, and a summarized decklist.
    """
    base = build_random_deck(theme=theme, constraints=constraints, seed=seed, attempts=attempts, timeout_s=timeout_s)

    # Run the full headless build with the chosen commander and the same seed
    try:
        from headless_runner import run as _run  # type: ignore
    except Exception as e:
        return RandomFullBuildResult(
            seed=base.seed,
            commander=base.commander,
            theme=base.theme,
            constraints=base.constraints or {},
            decklist=None,
            diagnostics={"error": f"headless runner unavailable: {e}"},
        )

    builder = _run(command_name=base.commander, seed=base.seed)

    # Summarize the decklist from builder.card_library
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

    diags: Dict[str, Any] = {"attempts": 1, "timeout_s": timeout_s}
    return RandomFullBuildResult(
        seed=base.seed,
        commander=base.commander,
        theme=base.theme,
        constraints=base.constraints or {},
        decklist=deck_items,
        diagnostics=diags,
    )

