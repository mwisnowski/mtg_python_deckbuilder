"""CLI utility: snapshot preview metrics and emit summary/top slow themes.

Usage (from repo root virtualenv):
  python -m code.scripts.preview_metrics_snapshot --limit 10 --output logs/preview_metrics_snapshot.json

Fetches /themes/metrics (requires WEB_THEME_PICKER_DIAGNOSTICS=1) and writes a compact JSON plus
human-readable summary to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000/themes/metrics"


def fetch_metrics(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 (local trusted)
        data = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(data)  # type: ignore[return-value]
    except json.JSONDecodeError as e:  # pragma: no cover - unlikely if server OK
        raise SystemExit(f"Invalid JSON from metrics endpoint: {e}\nRaw: {data[:400]}")


def summarize(metrics: Dict[str, Any], top_n: int) -> Dict[str, Any]:
    preview = (metrics.get("preview") or {}) if isinstance(metrics, dict) else {}
    per_theme = preview.get("per_theme") or {}
    # Compute top slow themes by avg_ms
    items = []
    for slug, info in per_theme.items():
        if not isinstance(info, dict):
            continue
        avg = info.get("avg_ms")
        if isinstance(avg, (int, float)):
            items.append((slug, float(avg), info))
    items.sort(key=lambda x: x[1], reverse=True)
    top = items[:top_n]
    return {
        "preview_requests": preview.get("preview_requests"),
        "preview_cache_hits": preview.get("preview_cache_hits"),
        "preview_avg_build_ms": preview.get("preview_avg_build_ms"),
        "preview_p95_build_ms": preview.get("preview_p95_build_ms"),
        "preview_ttl_seconds": preview.get("preview_ttl_seconds"),
        "editorial_curated_vs_sampled_pct": preview.get("editorial_curated_vs_sampled_pct"),
        "top_slowest": [
            {
                "slug": slug,
                "avg_ms": avg,
                "p95_ms": info.get("p95_ms"),
                "builds": info.get("builds"),
                "requests": info.get("requests"),
                "avg_curated_pct": info.get("avg_curated_pct"),
            }
            for slug, avg, info in top
        ],
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Snapshot preview metrics")
    ap.add_argument("--url", default=DEFAULT_URL, help="Metrics endpoint URL (default: %(default)s)")
    ap.add_argument("--limit", type=int, default=10, help="Top N slow themes to include (default: %(default)s)")
    ap.add_argument("--output", type=Path, help="Optional output JSON file for snapshot")
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout summary (still writes file if --output)")
    args = ap.parse_args(argv)

    try:
        raw = fetch_metrics(args.url)
    except urllib.error.URLError as e:
        print(f"ERROR: Failed fetching metrics endpoint: {e}", file=sys.stderr)
        return 2

    summary = summarize(raw, args.limit)
    snapshot = {
        "captured_at": int(time.time()),
        "source": args.url,
        "summary": summary,
    }

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as e:  # pragma: no cover
            print(f"ERROR: writing snapshot file failed: {e}", file=sys.stderr)
            return 3

    if not args.quiet:
        print("Preview Metrics Snapshot:")
        print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
