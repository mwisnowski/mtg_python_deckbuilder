"""Tests for the public API's deck-build endpoints (Roadmap 28, Milestone 3).

Mocks `orch.start_build_ctx`/`orch.run_stage` (per the existing convention in
test_build_utils_ctx.py) to avoid the full commander-data integration; the
build engine itself is already covered elsewhere. Focus here is on the
API's routing, auth, background execution, and store lifecycle.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    yield


@pytest.fixture()
def client(_isolated_db):
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    from code.web.services.user_db import create_user, create_api_key

    user = create_user("henry", "henry@example.com", "pw")
    key_plain, _ = create_api_key(user["id"])
    return {"Authorization": f"Bearer {key_plain}"}


def _fake_orchestrator(monkeypatch, *, stage_count: int = 2, fail: bool = False):
    """Patch code.web.routes.api_v1.builds.orch with a fake single-stage engine."""
    import code.web.routes.api_v1.builds as builds_route

    def _fake_start_build_ctx(**kwargs):
        return {"stages": list(range(stage_count)), "idx": 0}

    def _fake_run_stage(ctx, *args, **kwargs):
        if fail:
            raise RuntimeError("boom")
        ctx["idx"] += 1
        if ctx["idx"] >= len(ctx["stages"]):
            return {
                "done": True,
                "idx": ctx["idx"],
                "total": len(ctx["stages"]),
                "label": "Complete",
                "csv_path": "deck_files/Test.csv",
                "txt_path": "deck_files/Test.txt",
                "summary": {"type_breakdown": {"total": 100}},
                "compliance": {"overall": "PASS"},
            }
        return {"done": False, "idx": ctx["idx"], "total": len(ctx["stages"]), "label": "Stage"}

    monkeypatch.setattr(builds_route.orch, "start_build_ctx", _fake_start_build_ctx)
    monkeypatch.setattr(builds_route.orch, "run_stage", _fake_run_stage)
    monkeypatch.setattr(builds_route.orch, "ideal_defaults", lambda: {})
    monkeypatch.setattr(builds_route.orch, "bracket_options", lambda: [{"level": 1}])


def _poll_until_done(client, headers, build_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/v1/builds/{build_id}", headers=headers)
        data = resp.json()["data"]
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.05)
    raise AssertionError("build did not finish in time")


def test_create_build_requires_auth(client):
    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"})
    assert resp.status_code == 401


def test_create_build_requires_commander(client, auth_headers, monkeypatch):
    _fake_orchestrator(monkeypatch)
    resp = client.post("/api/v1/builds", json={"commander": "  "}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_COMMANDER"


def test_full_build_lifecycle(client, auth_headers, monkeypatch):
    _fake_orchestrator(monkeypatch)

    resp = client.post(
        "/api/v1/builds", json={"commander": "Test Commander", "themes": ["Aggro"]}, headers=auth_headers
    )
    assert resp.status_code == 202
    build_id = resp.json()["data"]["build_id"]
    assert resp.json()["data"]["status"] == "queued"

    data = _poll_until_done(client, auth_headers, build_id)
    assert data["status"] == "done"
    assert data["progress_pct"] == 100

    resp = client.get(f"/api/v1/builds/{build_id}/deck", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["summary"]["type_breakdown"]["total"] == 100
    assert result["compliance"]["overall"] == "PASS"

    resp = client.delete(f"/api/v1/builds/{build_id}", headers=auth_headers)
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/builds/{build_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_build_failure_reported(client, auth_headers, monkeypatch):
    _fake_orchestrator(monkeypatch, fail=True)

    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"}, headers=auth_headers)
    build_id = resp.json()["data"]["build_id"]

    data = _poll_until_done(client, auth_headers, build_id)
    assert data["status"] == "error"
    assert "boom" in data["error"]

    resp = client.get(f"/api/v1/builds/{build_id}/deck", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "BUILD_FAILED"


def test_deck_not_ready_before_done(client, auth_headers, monkeypatch):
    import threading
    import code.web.routes.api_v1.builds as builds_route

    gate = threading.Event()

    def _fake_start_build_ctx(**kwargs):
        return {"stages": [0], "idx": 0}

    def _fake_run_stage(ctx, *args, **kwargs):
        gate.wait(timeout=5)  # held open until the test releases it
        ctx["idx"] += 1
        return {"done": True, "idx": 1, "total": 1, "label": "Complete", "summary": {}, "compliance": {}}

    monkeypatch.setattr(builds_route.orch, "start_build_ctx", _fake_start_build_ctx)
    monkeypatch.setattr(builds_route.orch, "run_stage", _fake_run_stage)
    monkeypatch.setattr(builds_route.orch, "ideal_defaults", lambda: {})
    monkeypatch.setattr(builds_route.orch, "bracket_options", lambda: [{"level": 1}])

    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"}, headers=auth_headers)
    build_id = resp.json()["data"]["build_id"]

    try:
        resp = client.get(f"/api/v1/builds/{build_id}/deck", headers=auth_headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUILD_NOT_READY"
    finally:
        gate.set()


def test_build_not_visible_to_other_user(client, auth_headers, monkeypatch):
    from code.web.services.user_db import create_user, create_api_key

    _fake_orchestrator(monkeypatch)
    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"}, headers=auth_headers)
    build_id = resp.json()["data"]["build_id"]

    other_user = create_user("iris", "iris@example.com", "pw")
    other_key, _ = create_api_key(other_user["id"])
    other_headers = {"Authorization": f"Bearer {other_key}"}

    resp = client.get(f"/api/v1/builds/{build_id}", headers=other_headers)
    assert resp.status_code == 404
