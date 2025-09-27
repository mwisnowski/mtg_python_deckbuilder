"""CI helper: run a warm-pass benchmark candidate (single pass over all themes)
then compare against the committed warm baseline with threshold enforcement.

Intended usage (example):
  python -m code.scripts.preview_perf_ci_check --url http://localhost:8080 \
      --baseline logs/perf/theme_preview_warm_baseline.json --p95-threshold 5

Exit codes:
  0 success (within threshold)
  2 regression (p95 delta > threshold)
  3 setup / usage error

Notes:
- Uses --all --passes 1 to create a fresh candidate snapshot that approximates
  a warmed steady-state (server should have background refresh / typical load).
- If you prefer multi-pass then warm-only selection, adjust logic accordingly.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Preview performance CI regression gate")
    ap.add_argument("--url", default="http://localhost:8080", help="Base URL of running web service")
    ap.add_argument("--baseline", type=Path, required=True, help="Path to committed warm baseline JSON")
    ap.add_argument("--p95-threshold", type=float, default=5.0, help="Max allowed p95 regression percent (default: %(default)s)")
    ap.add_argument("--candidate-output", type=Path, default=Path("logs/perf/theme_preview_ci_candidate.json"), help="Where to write candidate benchmark JSON")
    ap.add_argument("--multi-pass", action="store_true", help="Run a 2-pass all-themes benchmark and compare warm pass only (optional enhancement)")
    args = ap.parse_args(argv)

    if not args.baseline.exists():
        print(json.dumps({"event":"ci_perf_error","message":"Baseline not found","path":str(args.baseline)}))
        return 3

    # Run candidate single-pass all-themes benchmark (no extra warm cycles to keep CI fast)
    # If multi-pass requested, run two passes over all themes so second pass represents warmed steady-state.
    passes = "2" if args.multi_pass else "1"
    bench_cmd = [sys.executable, "-m", "code.scripts.preview_perf_benchmark", "--url", args.url, "--all", "--passes", passes, "--output", str(args.candidate_output)]
    bench_proc = run(bench_cmd)
    if bench_proc.returncode != 0:
        print(json.dumps({"event":"ci_perf_error","stage":"benchmark","code":bench_proc.returncode,"stderr":bench_proc.stderr}))
        return 3
    print(bench_proc.stdout)

    if not args.candidate_output.exists():
        print(json.dumps({"event":"ci_perf_error","message":"Candidate output missing"}))
        return 3

    compare_cmd = [
        sys.executable,
        "-m","code.scripts.preview_perf_compare",
        "--baseline", str(args.baseline),
        "--candidate", str(args.candidate_output),
        "--warm-only",
        "--p95-threshold", str(args.p95_threshold),
    ]
    cmp_proc = run(compare_cmd)
    print(cmp_proc.stdout)
    if cmp_proc.returncode == 2:
        # Already printed JSON with failure status
        return 2
    if cmp_proc.returncode != 0:
        print(json.dumps({"event":"ci_perf_error","stage":"compare","code":cmp_proc.returncode,"stderr":cmp_proc.stderr}))
        return 3
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
