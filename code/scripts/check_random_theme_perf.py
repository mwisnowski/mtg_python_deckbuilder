"""Opt-in guard that compares multi-theme filter performance to a stored baseline.

Run inside the project virtual environment:

    python -m code.scripts.check_random_theme_perf --baseline config/random_theme_perf_baseline.json

The script executes the same profiling loop as `profile_multi_theme_filter` and fails
if the observed mean or p95 timings regress more than the allowed threshold.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = PROJECT_ROOT / "config" / "random_theme_perf_baseline.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from code.scripts.profile_multi_theme_filter import run_profile  # type: ignore  # noqa: E402


def _load_baseline(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def _extract(metric: Dict[str, Any], key: str) -> float:
    try:
        value = float(metric.get(key, 0.0))
    except Exception:
        value = 0.0
    return value


def _check_section(name: str, actual: Dict[str, Any], baseline: Dict[str, Any], threshold: float) -> Tuple[bool, str]:
    a_mean = _extract(actual, "mean_ms")
    b_mean = _extract(baseline, "mean_ms")
    a_p95 = _extract(actual, "p95_ms")
    b_p95 = _extract(baseline, "p95_ms")

    allowed_mean = b_mean * (1.0 + threshold)
    allowed_p95 = b_p95 * (1.0 + threshold)

    mean_ok = a_mean <= allowed_mean or b_mean == 0.0
    p95_ok = a_p95 <= allowed_p95 or b_p95 == 0.0

    status = mean_ok and p95_ok

    def _format_row(label: str, actual_val: float, baseline_val: float, allowed_val: float, ok: bool) -> str:
        trend = ((actual_val - baseline_val) / baseline_val * 100.0) if baseline_val else 0.0
        trend_str = f"{trend:+.1f}%" if baseline_val else "n/a"
        limit_str = f"≤ {allowed_val:.3f}ms" if baseline_val else "n/a"
        return f"    {label:<6} actual={actual_val:.3f}ms baseline={baseline_val:.3f}ms ({trend_str}), limit {limit_str} -> {'OK' if ok else 'FAIL'}"

    rows = [f"Section: {name}"]
    rows.append(_format_row("mean", a_mean, b_mean, allowed_mean, mean_ok))
    rows.append(_format_row("p95", a_p95, b_p95, allowed_p95, p95_ok))
    return status, "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check multi-theme filtering performance against a baseline")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="Baseline JSON file (default: config/random_theme_perf_baseline.json)")
    parser.add_argument("--iterations", type=int, default=400, help="Number of iterations to sample (default: 400)")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducibility")
    parser.add_argument("--threshold", type=float, default=0.15, help="Allowed regression threshold as a fraction (default: 0.15 = 15%)")
    parser.add_argument("--update-baseline", action="store_true", help="Overwrite the baseline file with the newly collected metrics")
    args = parser.parse_args(argv)

    baseline_path = args.baseline if args.baseline else DEFAULT_BASELINE
    if args.update_baseline and not baseline_path.parent.exists():
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.update_baseline:
        baseline = _load_baseline(baseline_path)
    else:
        baseline = {}

    results = run_profile(args.iterations, args.seed)

    cascade_status, cascade_report = _check_section("cascade", results.get("cascade", {}), baseline.get("cascade", {}), args.threshold)
    synergy_status, synergy_report = _check_section("synergy", results.get("synergy", {}), baseline.get("synergy", {}), args.threshold)

    print("Iterations:", results.get("iterations"))
    print("Seed:", results.get("seed"))
    print(cascade_report)
    print(synergy_report)

    overall_ok = cascade_status and synergy_status

    if args.update_baseline:
        payload = {
            "iterations": results.get("iterations"),
            "seed": results.get("seed"),
            "cascade": results.get("cascade"),
            "synergy": results.get("synergy"),
        }
        baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline updated → {baseline_path}")
        return 0

    if not overall_ok:
        print(f"FAIL: performance regressions exceeded {args.threshold * 100:.1f}% threshold", file=sys.stderr)
        return 1

    print("PASS: performance within allowed threshold")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
