"""Ad-hoc performance benchmark for theme preview build latency (Phase A validation).

Runs warm-up plus measured request loops against several theme slugs and prints
aggregate latency stats (p50/p90/p95, cache hit ratio evolution). Intended to
establish or validate that refactor did not introduce >5% p95 regression.

Usage (ensure server running locally – commonly :8080 in docker compose):
    python -m code.scripts.preview_perf_benchmark --themes 8 --loops 40 \
            --url http://localhost:8080 --warm 1 --limit 12

Theme slug discovery hierarchy (when --theme not provided):
    1. Try /themes/index.json (legacy / planned static index)
    2. Fallback to /themes/api/themes (current API) and take the first N ids
The discovered slugs are sorted deterministically then truncated to N.

NOTE: This is intentionally minimal (no external deps). For stable comparisons
run with identical parameters pre/post-change and commit the JSON output under
logs/perf/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any, Dict, List
import urllib.request
import urllib.error
import sys
from pathlib import Path


def _fetch_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 local dev
        data = resp.read().decode("utf-8", "replace")
    return json.loads(data)  # type: ignore[return-value]


def select_theme_slugs(base_url: str, count: int) -> List[str]:
    """Discover theme slugs for benchmarking.

    Attempts legacy static index first, then falls back to live API listing.
    """
    errors: List[str] = []
    slugs: List[str] = []
    # Attempt 1: legacy /themes/index.json
    try:
        idx = _fetch_json(f"{base_url.rstrip('/')}/themes/index.json")
        entries = idx.get("themes") or []
        for it in entries:
            if not isinstance(it, dict):
                continue
            slug = it.get("slug") or it.get("id") or it.get("theme_id")
            if isinstance(slug, str):
                slugs.append(slug)
    except Exception as e:  # pragma: no cover - network variability
        errors.append(f"index.json failed: {e}")

    if not slugs:
        # Attempt 2: live API listing
        try:
            listing = _fetch_json(f"{base_url.rstrip('/')}/themes/api/themes")
            items = listing.get("items") or []
            for it in items:
                if not isinstance(it, dict):
                    continue
                tid = it.get("id") or it.get("slug") or it.get("theme_id")
                if isinstance(tid, str):
                    slugs.append(tid)
        except Exception as e:  # pragma: no cover - network variability
            errors.append(f"api/themes failed: {e}")

    slugs = sorted(set(slugs))[:count]
    if not slugs:
        raise SystemExit("No theme slugs discovered; cannot benchmark (" + "; ".join(errors) + ")")
    return slugs


def fetch_all_theme_slugs(base_url: str, page_limit: int = 200) -> List[str]:
    """Fetch all theme slugs via paginated /themes/api/themes endpoint.

    Uses maximum page size (200) and iterates using offset until no next page.
    Returns deterministic sorted unique list of slugs.
    """
    slugs: List[str] = []
    offset = 0
    seen: set[str] = set()
    while True:
        try:
            url = f"{base_url.rstrip('/')}/themes/api/themes?limit={page_limit}&offset={offset}"
            data = _fetch_json(url)
        except Exception as e:  # pragma: no cover - network variability
            raise SystemExit(f"Failed fetching themes page offset={offset}: {e}")
        items = data.get("items") or []
        for it in items:
            if not isinstance(it, dict):
                continue
            tid = it.get("id") or it.get("slug") or it.get("theme_id")
            if isinstance(tid, str) and tid not in seen:
                seen.add(tid)
                slugs.append(tid)
        next_offset = data.get("next_offset")
        if not next_offset or next_offset == offset:
            break
        offset = int(next_offset)
    return sorted(slugs)


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    k = (len(sv) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sv) - 1)
    if f == c:
        return sv[f]
    d0 = sv[f] * (c - k)
    d1 = sv[c] * (k - f)
    return d0 + d1


def run_loop(base_url: str, slugs: List[str], loops: int, limit: int, warm: bool, path_template: str) -> Dict[str, Any]:
    latencies: List[float] = []
    per_slug_counts = {s: 0 for s in slugs}
    t_start = time.time()
    for i in range(loops):
        slug = slugs[i % len(slugs)]
        # path_template may contain {slug} and {limit}
        try:
            rel = path_template.format(slug=slug, limit=limit)
        except Exception:
            rel = f"/themes/api/theme/{slug}/preview?limit={limit}"
        if not rel.startswith('/'):
            rel = '/' + rel
        url = f"{base_url.rstrip('/')}{rel}"
        t0 = time.time()
        try:
            _fetch_json(url)
        except Exception as e:
            print(json.dumps({"event": "perf_benchmark_error", "slug": slug, "error": str(e)}))  # noqa: T201
            continue
        ms = (time.time() - t0) * 1000.0
        latencies.append(ms)
        per_slug_counts[slug] += 1
    elapsed = time.time() - t_start
    return {
        "warm": warm,
        "loops": loops,
        "slugs": slugs,
        "per_slug_requests": per_slug_counts,
        "elapsed_s": round(elapsed, 3),
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p90_ms": round(percentile(latencies, 0.90), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "count": len(latencies),
        "_latencies": latencies,  # internal (removed in final result unless explicitly retained)
    }


def _stats_from_latencies(latencies: List[float]) -> Dict[str, Any]:
    if not latencies:
        return {"count": 0, "p50_ms": 0.0, "p90_ms": 0.0, "p95_ms": 0.0, "avg_ms": 0.0}
    return {
        "count": len(latencies),
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p90_ms": round(percentile(latencies, 0.90), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "avg_ms": round(statistics.mean(latencies), 2),
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Theme preview performance benchmark")
    ap.add_argument("--url", default="http://localhost:8000", help="Base server URL (default: %(default)s)")
    ap.add_argument("--themes", type=int, default=6, help="Number of theme slugs to exercise (default: %(default)s)")
    ap.add_argument("--loops", type=int, default=60, help="Total request iterations (default: %(default)s)")
    ap.add_argument("--limit", type=int, default=12, help="Preview size (default: %(default)s)")
    ap.add_argument("--path-template", default="/themes/api/theme/{slug}/preview?limit={limit}", help="Format string for preview request path (default: %(default)s)")
    ap.add_argument("--theme", action="append", dest="explicit_theme", help="Explicit theme slug(s); overrides automatic selection")
    ap.add_argument("--warm", type=int, default=1, help="Number of warm-up loops (full cycles over selected slugs) (default: %(default)s)")
    ap.add_argument("--output", type=Path, help="Optional JSON output path (committed under logs/perf)")
    ap.add_argument("--all", action="store_true", help="Exercise ALL themes (ignores --themes; loops auto-set to passes*total_slugs unless --loops-explicit)")
    ap.add_argument("--passes", type=int, default=1, help="When using --all, number of passes over the full theme set (default: %(default)s)")
    # Hidden flag to detect if user explicitly set --loops (argparse has no direct support, so use sentinel technique)
    # We keep original --loops for backwards compatibility; when --all we recompute unless user passed --loops-explicit
    ap.add_argument("--loops-explicit", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--extract-warm-baseline", type=Path, help="If multi-pass (--all --passes >1), write a warm-only baseline JSON (final pass stats) to this path")
    args = ap.parse_args(argv)

    try:
        if args.explicit_theme:
            slugs = args.explicit_theme
        elif args.all:
            slugs = fetch_all_theme_slugs(args.url)
        else:
            slugs = select_theme_slugs(args.url, args.themes)
    except SystemExit as e:  # pragma: no cover - dependency on live server
        print(str(e), file=sys.stderr)
        return 2

    mode = "all" if args.all else "subset"
    total_slugs = len(slugs)
    if args.all and not args.loops_explicit:
        # Derive loops = passes * total_slugs
        args.loops = max(1, args.passes) * total_slugs

    print(json.dumps({  # noqa: T201
        "event": "preview_perf_start",
        "mode": mode,
        "total_slugs": total_slugs,
        "planned_loops": args.loops,
        "passes": args.passes if args.all else None,
    }))

    # Execution paths:
    # 1. Standard subset or single-pass all: warm cycles -> single measured run
    # 2. Multi-pass all mode (--all --passes >1): iterate passes capturing per-pass stats (no separate warm loops)
    if args.all and args.passes > 1:
        pass_results: List[Dict[str, Any]] = []
        combined_latencies: List[float] = []
        t0_all = time.time()
        for p in range(1, args.passes + 1):
            r = run_loop(args.url, slugs, len(slugs), args.limit, warm=(p == 1), path_template=args.path_template)
            lat = r.pop("_latencies", [])
            combined_latencies.extend(lat)
            pass_result = {
                "pass": p,
                "warm": r["warm"],
                "elapsed_s": r["elapsed_s"],
                "p50_ms": r["p50_ms"],
                "p90_ms": r["p90_ms"],
                "p95_ms": r["p95_ms"],
                "avg_ms": r["avg_ms"],
                "count": r["count"],
            }
            pass_results.append(pass_result)
        total_elapsed = round(time.time() - t0_all, 3)
        aggregate = _stats_from_latencies(combined_latencies)
        result = {
            "mode": mode,
            "total_slugs": total_slugs,
            "passes": args.passes,
            "slugs": slugs,
            "combined": {
                **aggregate,
                "elapsed_s": total_elapsed,
            },
            "passes_results": pass_results,
            "cold_pass_p95_ms": pass_results[0]["p95_ms"],
            "warm_pass_p95_ms": pass_results[-1]["p95_ms"],
            "cold_pass_p50_ms": pass_results[0]["p50_ms"],
            "warm_pass_p50_ms": pass_results[-1]["p50_ms"],
        }
        print(json.dumps({"event": "preview_perf_result", **result}, indent=2))  # noqa: T201
        # Optional warm baseline extraction (final pass only; represents warmed steady-state)
        if args.extract_warm_baseline:
            try:
                wb = pass_results[-1]
                warm_obj = {
                    "event": "preview_perf_warm_baseline",
                    "mode": mode,
                    "total_slugs": total_slugs,
                    "warm_baseline": True,
                    "source_pass": wb["pass"],
                    "p50_ms": wb["p50_ms"],
                    "p90_ms": wb["p90_ms"],
                    "p95_ms": wb["p95_ms"],
                    "avg_ms": wb["avg_ms"],
                    "count": wb["count"],
                    "slugs": slugs,
                }
                args.extract_warm_baseline.parent.mkdir(parents=True, exist_ok=True)
                args.extract_warm_baseline.write_text(json.dumps(warm_obj, indent=2, sort_keys=True), encoding="utf-8")
                print(json.dumps({  # noqa: T201
                    "event": "preview_perf_warm_baseline_written",
                    "path": str(args.extract_warm_baseline),
                    "p95_ms": wb["p95_ms"],
                }))
            except Exception as e:  # pragma: no cover
                print(json.dumps({"event": "preview_perf_warm_baseline_error", "error": str(e)}))  # noqa: T201
    else:
        # Warm-up loops first (if requested)
        for w in range(args.warm):
            run_loop(args.url, slugs, len(slugs), args.limit, warm=True, path_template=args.path_template)
        result = run_loop(args.url, slugs, args.loops, args.limit, warm=False, path_template=args.path_template)
        result.pop("_latencies", None)
        result["slugs"] = slugs
        result["mode"] = mode
        result["total_slugs"] = total_slugs
        if args.all:
            result["passes"] = args.passes
        print(json.dumps({"event": "preview_perf_result", **result}, indent=2))  # noqa: T201

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Ensure we write the final result object (multi-pass already prepared above)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as e:  # pragma: no cover
            print(f"ERROR: failed writing output file: {e}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
