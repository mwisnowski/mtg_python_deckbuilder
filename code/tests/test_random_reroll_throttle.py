from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def throttle_client(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    import code.web.app as app_module

    # Ensure feature flags and globals reflect the test configuration
    app_module.RANDOM_MODES = True
    app_module.RANDOM_UI = True
    app_module.RATE_LIMIT_ENABLED = False

    # Keep existing values so we can restore after the test
    prev_ms = app_module.RANDOM_REROLL_THROTTLE_MS
    prev_seconds = app_module._REROLL_THROTTLE_SECONDS

    app_module.RANDOM_REROLL_THROTTLE_MS = 50
    app_module._REROLL_THROTTLE_SECONDS = 0.05

    app_module._RL_COUNTS.clear()

    with TestClient(app_module.app) as client:
        yield client, app_module

    # Restore globals for other tests
    app_module.RANDOM_REROLL_THROTTLE_MS = prev_ms
    app_module._REROLL_THROTTLE_SECONDS = prev_seconds
    app_module._RL_COUNTS.clear()


def test_random_reroll_session_throttle(throttle_client):
    client, app_module = throttle_client

    # First reroll succeeds and seeds the session timestamp
    first = client.post("/api/random_reroll", json={"seed": 5000})
    assert first.status_code == 200, first.text
    assert "sid" in client.cookies

    # Immediate follow-up should hit the throttle guard
    second = client.post("/api/random_reroll", json={"seed": 5001})
    assert second.status_code == 429
    retry_after = second.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 1

    # After waiting slightly longer than the throttle window, requests succeed again
    time.sleep(0.06)
    third = client.post("/api/random_reroll", json={"seed": 5002})
    assert third.status_code == 200, third.text
    assert int(third.json().get("seed")) >= 5002

    # Telemetry shouldn't record fallback for the throttle rejection
    metrics_snapshot = app_module._RANDOM_METRICS.get("reroll")
    assert metrics_snapshot is not None
    assert metrics_snapshot.get("error", 0) == 0