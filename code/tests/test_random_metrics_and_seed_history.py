from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_metrics_and_seed_history(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("RANDOM_TELEMETRY", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    import code.web.app as app_module

    # Reset in-memory telemetry so assertions are deterministic
    app_module.RANDOM_TELEMETRY = True
    app_module.RATE_LIMIT_ENABLED = False
    for bucket in app_module._RANDOM_METRICS.values():
        for key in bucket:
            bucket[key] = 0
    for key in list(app_module._RANDOM_USAGE_METRICS.keys()):
        app_module._RANDOM_USAGE_METRICS[key] = 0
    for key in list(app_module._RANDOM_FALLBACK_METRICS.keys()):
        app_module._RANDOM_FALLBACK_METRICS[key] = 0
    app_module._RANDOM_FALLBACK_REASONS.clear()
    app_module._RL_COUNTS.clear()

    prev_ms = app_module.RANDOM_REROLL_THROTTLE_MS
    prev_seconds = app_module._REROLL_THROTTLE_SECONDS
    app_module.RANDOM_REROLL_THROTTLE_MS = 0
    app_module._REROLL_THROTTLE_SECONDS = 0.0

    try:
        with TestClient(app_module.app) as client:
            # Build + reroll to generate metrics and seed history
            r1 = client.post("/api/random_full_build", json={"seed": 9090, "primary_theme": "Aggro"})
            assert r1.status_code == 200, r1.text
            r2 = client.post("/api/random_reroll", json={"seed": 9090})
            assert r2.status_code == 200, r2.text

            # Metrics
            m = client.get("/status/random_metrics")
            assert m.status_code == 200, m.text
            mj = m.json()
            assert mj.get("ok") is True
            metrics = mj.get("metrics") or {}
            assert "full_build" in metrics and "reroll" in metrics

            usage = mj.get("usage") or {}
            modes = usage.get("modes") or {}
            fallbacks = usage.get("fallbacks") or {}
            assert set(modes.keys()) >= {"theme", "reroll", "surprise", "reroll_same_commander"}
            assert modes.get("theme", 0) >= 2
            assert "none" in fallbacks
            assert isinstance(usage.get("fallback_reasons"), dict)

            # Seed history
            sh = client.get("/api/random/seeds")
            assert sh.status_code == 200
            sj = sh.json()
            seeds = sj.get("seeds") or []
            assert any(s == 9090 for s in seeds) and sj.get("last") in seeds
    finally:
        app_module.RANDOM_REROLL_THROTTLE_MS = prev_ms
        app_module._REROLL_THROTTLE_SECONDS = prev_seconds
