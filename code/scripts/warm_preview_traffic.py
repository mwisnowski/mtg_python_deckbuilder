"""Generate warm preview traffic to populate theme preview cache & metrics.

Usage:
  python -m code.scripts.warm_preview_traffic --count 25 --repeats 2 \
      --base-url http://localhost:8000 --delay 0.05

Requirements:
  - FastAPI server running locally exposing /themes endpoints
  - WEB_THEME_PICKER_DIAGNOSTICS=1 so /themes/metrics is accessible

Strategy:
  1. Fetch /themes/fragment/list?limit=COUNT to obtain HTML table.
  2. Extract theme slugs via regex on data-theme-id attributes.
  3. Issue REPEATS preview fragment requests per slug in order.
  4. Print simple timing / status summary.

This script intentionally uses stdlib only (urllib, re, time) to avoid extra deps.
"""
from __future__ import annotations

import argparse
import re
import time
import urllib.request
import urllib.error
from typing import List

LIST_PATH = "/themes/fragment/list"
PREVIEW_PATH = "/themes/fragment/preview/{slug}"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "warm-preview/1"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 (local trusted)
        return resp.read().decode("utf-8", "replace")


def extract_slugs(html: str, limit: int) -> List[str]:
    slugs = []
    for m in re.finditer(r'data-theme-id="([^"]+)"', html):
        s = m.group(1).strip()
        if s and s not in slugs:
            slugs.append(s)
        if len(slugs) >= limit:
            break
    return slugs


def warm(base_url: str, count: int, repeats: int, delay: float) -> None:
    list_url = f"{base_url}{LIST_PATH}?limit={count}&offset=0"
    print(f"[warm] Fetching list: {list_url}")
    try:
        html = fetch(list_url)
    except urllib.error.URLError as e:  # pragma: no cover
        raise SystemExit(f"Failed fetching list: {e}")
    slugs = extract_slugs(html, count)
    if not slugs:
        raise SystemExit("No theme slugs extracted – cannot warm.")
    print(f"[warm] Extracted {len(slugs)} slugs: {', '.join(slugs[:8])}{'...' if len(slugs)>8 else ''}")
    total_requests = 0
    start = time.time()
    for r in range(repeats):
        print(f"[warm] Pass {r+1}/{repeats}")
        for slug in slugs:
            url = f"{base_url}{PREVIEW_PATH.format(slug=slug)}"
            try:
                fetch(url)
            except Exception as e:  # pragma: no cover
                print(f"  [warn] Failed {slug}: {e}")
            else:
                total_requests += 1
            if delay:
                time.sleep(delay)
    dur = time.time() - start
    print(f"[warm] Completed {total_requests} preview requests in {dur:.2f}s ({total_requests/dur if dur>0 else 0:.1f} rps)")
    print("[warm] Done. Now run metrics snapshot to capture warm p95.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate warm preview traffic")
    ap.add_argument("--base-url", default="http://localhost:8000", help="Base URL (default: %(default)s)")
    ap.add_argument("--count", type=int, default=25, help="Number of distinct theme slugs to warm (default: %(default)s)")
    ap.add_argument("--repeats", type=int, default=2, help="Repeat passes over slugs (default: %(default)s)")
    ap.add_argument("--delay", type=float, default=0.05, help="Delay between requests in seconds (default: %(default)s)")
    args = ap.parse_args(argv)
    warm(args.base_url.rstrip("/"), args.count, args.repeats, args.delay)
    return 0

if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv[1:]))
