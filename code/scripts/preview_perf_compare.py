"""Compare two preview benchmark JSON result files and emit delta stats.

Usage:
  python -m code.scripts.preview_perf_compare --baseline logs/perf/theme_preview_baseline_all_pass1_20250923.json --candidate logs/perf/new_run.json

Outputs JSON with percentage deltas for p50/p90/p95/avg (positive = regression/slower).
If multi-pass structures are present (combined & passes_results) those are included.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def load(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Multi-pass result may store stats under combined
    if "combined" in data:
        core = data["combined"].copy()
        # Inject representative fields for uniform comparison
        core["p50_ms"] = core.get("p50_ms") or data.get("p50_ms")
        core["p90_ms"] = core.get("p90_ms") or data.get("p90_ms")
        core["p95_ms"] = core.get("p95_ms") or data.get("p95_ms")
        core["avg_ms"] = core.get("avg_ms") or data.get("avg_ms")
        data["_core_stats"] = core
    else:
        data["_core_stats"] = {
            k: data.get(k) for k in ("p50_ms", "p90_ms", "p95_ms", "avg_ms", "count")
        }
    return data


def pct_delta(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return round(((new - old) / old) * 100.0, 2)


def compare(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    b = baseline["_core_stats"]
    c = candidate["_core_stats"]
    result = {"baseline_count": b.get("count"), "candidate_count": c.get("count")}
    for k in ("p50_ms", "p90_ms", "p95_ms", "avg_ms"):
        if b.get(k) is not None and c.get(k) is not None:
            result[k] = {
                "baseline": b[k],
                "candidate": c[k],
                "delta_pct": pct_delta(c[k], b[k]),
            }
    # If both have per-pass details include first and last pass p95/p50
    if "passes_results" in baseline and "passes_results" in candidate:
        result["passes"] = {
            "baseline": {
                "cold_p95": baseline.get("cold_pass_p95_ms"),
                "warm_p95": baseline.get("warm_pass_p95_ms"),
                "cold_p50": baseline.get("cold_pass_p50_ms"),
                "warm_p50": baseline.get("warm_pass_p50_ms"),
            },
            "candidate": {
                "cold_p95": candidate.get("cold_pass_p95_ms"),
                "warm_p95": candidate.get("warm_pass_p95_ms"),
                "cold_p50": candidate.get("cold_pass_p50_ms"),
                "warm_p50": candidate.get("warm_pass_p50_ms"),
            },
        }
    return result


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Compare two preview benchmark JSON result files")
    ap.add_argument("--baseline", required=True, type=Path, help="Baseline JSON path")
    ap.add_argument("--candidate", required=True, type=Path, help="Candidate JSON path")
    ap.add_argument("--p95-threshold", type=float, default=None, help="Fail (exit 2) if p95 regression exceeds this percent (positive delta)")
    ap.add_argument("--warm-only", action="store_true", help="When both results have passes, compare warm pass p95/p50 instead of combined/core")
    args = ap.parse_args(argv)
    if not args.baseline.exists():
        raise SystemExit(f"Baseline not found: {args.baseline}")
    if not args.candidate.exists():
        raise SystemExit(f"Candidate not found: {args.candidate}")
    baseline = load(args.baseline)
    candidate = load(args.candidate)
    # If warm-only requested and both have warm pass stats, override _core_stats before compare
    if args.warm_only and "warm_pass_p95_ms" in baseline and "warm_pass_p95_ms" in candidate:
        baseline["_core_stats"] = {
            "p50_ms": baseline.get("warm_pass_p50_ms"),
            "p90_ms": baseline.get("_core_stats", {}).get("p90_ms"),  # p90 not tracked per-pass; retain combined
            "p95_ms": baseline.get("warm_pass_p95_ms"),
            "avg_ms": baseline.get("_core_stats", {}).get("avg_ms"),
            "count": baseline.get("_core_stats", {}).get("count"),
        }
        candidate["_core_stats"] = {
            "p50_ms": candidate.get("warm_pass_p50_ms"),
            "p90_ms": candidate.get("_core_stats", {}).get("p90_ms"),
            "p95_ms": candidate.get("warm_pass_p95_ms"),
            "avg_ms": candidate.get("_core_stats", {}).get("avg_ms"),
            "count": candidate.get("_core_stats", {}).get("count"),
        }
    cmp = compare(baseline, candidate)
    payload = {"event": "preview_perf_compare", **cmp}
    if args.p95_threshold is not None and "p95_ms" in cmp:
        delta = cmp["p95_ms"]["delta_pct"]
        payload["threshold"] = {"p95_threshold": args.p95_threshold, "p95_delta_pct": delta}
        if delta is not None and delta > args.p95_threshold:
            payload["result"] = "fail"
            print(json.dumps(payload, indent=2))  # noqa: T201
            return 2
        payload["result"] = "pass"
    print(json.dumps(payload, indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(__import__('sys').argv[1:]))
