"""Profile helper for multi-theme commander filtering.

Run within the project virtual environment:

    python code/scripts/profile_multi_theme_filter.py --iterations 500

Outputs aggregate timing for combination and synergy fallback scenarios.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from deck_builder.random_entrypoint import _ensure_theme_tag_cache, _filter_multi, _load_commanders_df  # noqa: E402


def _sample_combinations(tags: List[str], iterations: int) -> List[Tuple[str | None, str | None, str | None]]:
    import random

    combos: List[Tuple[str | None, str | None, str | None]] = []
    if not tags:
        return combos
    for _ in range(iterations):
        primary = random.choice(tags)
        secondary = random.choice(tags) if random.random() < 0.45 else None
        tertiary = random.choice(tags) if random.random() < 0.25 else None
        combos.append((primary, secondary, tertiary))
    return combos


def _collect_tag_pool(df: pd.DataFrame) -> List[str]:
    tag_pool: set[str] = set()
    for tags in df.get("_ltags", []):  # type: ignore[assignment]
        if not tags:
            continue
        for token in tags:
            tag_pool.add(token)
    return sorted(tag_pool)


def _summarize(values: List[float]) -> Dict[str, float]:
    mean_ms = statistics.mean(values) * 1000
    if len(values) >= 20:
        p95_ms = statistics.quantiles(values, n=20)[18] * 1000
    else:
        p95_ms = max(values) * 1000 if values else 0.0
    return {
        "mean_ms": round(mean_ms, 6),
        "p95_ms": round(p95_ms, 6),
        "samples": len(values),
    }


def run_profile(iterations: int, seed: int | None = None) -> Dict[str, Any]:
    if iterations <= 0:
        raise ValueError("Iterations must be a positive integer")

    df = _load_commanders_df()
    df = _ensure_theme_tag_cache(df)
    tag_pool = _collect_tag_pool(df)
    if not tag_pool:
        raise RuntimeError("No theme tags available in dataset; ensure commander catalog is populated")

    combos = _sample_combinations(tag_pool, iterations)
    if not combos:
        raise RuntimeError("Failed to generate theme combinations for profiling")

    timings: List[float] = []
    synergy_timings: List[float] = []

    for primary, secondary, tertiary in combos:
        start = time.perf_counter()
        _filter_multi(df, primary, secondary, tertiary)
        timings.append(time.perf_counter() - start)

        improbable_primary = f"{primary or 'aggro'}_unlikely_value"
        start_synergy = time.perf_counter()
        _filter_multi(df, improbable_primary, secondary, tertiary)
        synergy_timings.append(time.perf_counter() - start_synergy)

    return {
        "iterations": iterations,
        "seed": seed,
        "cascade": _summarize(timings),
        "synergy": _summarize(synergy_timings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile multi-theme filtering performance")
    parser.add_argument("--iterations", type=int, default=400, help="Number of random theme combinations to evaluate")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for repeatability")
    parser.add_argument("--json", type=Path, help="Optional path to write the raw metrics as JSON")
    args = parser.parse_args()

    if args.seed is not None:
        import random

        random.seed(args.seed)

    results = run_profile(args.iterations, args.seed)

    def _print(label: str, stats: Dict[str, float]) -> None:
        mean_ms = stats.get("mean_ms", 0.0)
        p95_ms = stats.get("p95_ms", 0.0)
        samples = stats.get("samples", 0)
        print(f"{label}: mean={mean_ms:.4f}ms p95={p95_ms:.4f}ms (n={samples})")

    _print("AND-combo cascade", results.get("cascade", {}))
    _print("Synergy fallback", results.get("synergy", {}))

    if args.json:
        payload = {
            "iterations": results.get("iterations"),
            "seed": results.get("seed"),
            "cascade": results.get("cascade"),
            "synergy": results.get("synergy"),
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
