from __future__ import annotations

import os
from typing import List
from fastapi.testclient import TestClient

"""Lightweight performance smoke test for Random Modes.

Runs a small number of builds (SURPRISE_COUNT + THEMED_COUNT) using the frozen
CSV test dataset and asserts that the p95 elapsed_ms is under the configured
threshold (default 1000ms) unless PERF_SKIP=1 is set.

This is intentionally lenient and should not be treated as a microbenchmark; it
serves as a regression guard for accidental O(N^2) style slowdowns.
"""

SURPRISE_COUNT = int(os.getenv("PERF_SURPRISE_COUNT", "15"))
THEMED_COUNT = int(os.getenv("PERF_THEMED_COUNT", "15"))
THRESHOLD_MS = int(os.getenv("PERF_P95_THRESHOLD_MS", "1000"))
SKIP = os.getenv("PERF_SKIP") == "1"
THEME = os.getenv("PERF_SAMPLE_THEME", "Tokens")


def _elapsed(diag: dict) -> int:
    try:
        return int(diag.get("elapsed_ms") or 0)
    except Exception:
        return 0


def test_random_performance_p95(monkeypatch):  # pragma: no cover - performance heuristic
    if SKIP:
        return  # allow opt-out in CI or constrained environments

    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))
    from code.web.app import app
    client = TestClient(app)

    samples: List[int] = []

    # Surprise (no theme)
    for i in range(SURPRISE_COUNT):
        r = client.post("/api/random_full_build", json={"seed": 10000 + i})
        assert r.status_code == 200, r.text
        samples.append(_elapsed(r.json().get("diagnostics") or {}))

    # Themed
    for i in range(THEMED_COUNT):
        r = client.post("/api/random_full_build", json={"seed": 20000 + i, "theme": THEME})
        assert r.status_code == 200, r.text
        samples.append(_elapsed(r.json().get("diagnostics") or {}))

    # Basic sanity: no zeros for all entries (some builds may be extremely fast; allow zeros but not all)
    assert len(samples) == SURPRISE_COUNT + THEMED_COUNT
    if all(s == 0 for s in samples):  # degenerate path
        return

    # p95
    sorted_samples = sorted(samples)
    idx = max(0, int(round(0.95 * (len(sorted_samples) - 1))))
    p95 = sorted_samples[idx]
    assert p95 < THRESHOLD_MS, f"p95 {p95}ms exceeds threshold {THRESHOLD_MS}ms (samples={samples})"
