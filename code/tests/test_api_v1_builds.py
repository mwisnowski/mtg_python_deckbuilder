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


def test_create_build_uses_per_user_deck_dir(client, auth_headers, monkeypatch):
    """Regression: builds must export into deck_files/{user_id}/, not the shared root
    (see decks.py's _deck_dir), so GET /api/v1/decks/{filename} can find them."""
    import code.web.routes.api_v1.builds as builds_route
    from code.web.services.user_db import verify_api_key

    seen_kwargs: dict = {}

    def _capturing_start_build_ctx(**kwargs):
        seen_kwargs.update(kwargs)
        return {"stages": [0], "idx": 0}

    monkeypatch.setattr(builds_route.orch, "start_build_ctx", _capturing_start_build_ctx)
    monkeypatch.setattr(builds_route.orch, "ideal_defaults", lambda: {})
    monkeypatch.setattr(builds_route.orch, "bracket_options", lambda: [{"level": 1}])

    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"}, headers=auth_headers)
    assert resp.status_code == 202

    token = auth_headers["Authorization"].split(" ", 1)[1]
    user = verify_api_key(token)
    expected_suffix = str(builds_route._deck_dir(str(user["id"])))
    assert seen_kwargs["deck_dir"] == expected_suffix
    assert seen_kwargs["deck_dir"] != "deck_files"


def _fake_guided_orchestrator(monkeypatch, *, stage_count: int = 2):
    """Like _fake_orchestrator, but run_stage never batches -- each call advances
    exactly one stage and returns added_cards, matching guided-mode semantics."""
    import code.web.routes.api_v1.builds as builds_route

    class _FakeBuilder:
        def __init__(self):
            self.card_library = {
                "Sol Ring": {"Count": 1, "Role": "ramp", "SubRole": "", "TriggerTag": ""},
            }
            self._combined_cards_df = None
            self.commander_name = "Test Commander"

    def _fake_start_build_ctx(**kwargs):
        return {"stages": list(range(stage_count)), "idx": 0, "builder": _FakeBuilder(), "locks": set(), "alts_exclude": set()}

    def _fake_run_stage(ctx, *args, **kwargs):
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
        return {
            "done": False,
            "idx": ctx["idx"],
            "total": len(ctx["stages"]),
            "label": "Stage",
            "added_cards": [{"name": "Sol Ring", "count": 1, "role": "ramp"}],
        }

    monkeypatch.setattr(builds_route.orch, "start_build_ctx", _fake_start_build_ctx)
    monkeypatch.setattr(builds_route.orch, "run_stage", _fake_run_stage)
    monkeypatch.setattr(builds_route.orch, "ideal_defaults", lambda: {})
    monkeypatch.setattr(builds_route.orch, "bracket_options", lambda: [{"level": 1}])


def test_guided_build_advance_flow(client, auth_headers, monkeypatch):
    _fake_guided_orchestrator(monkeypatch, stage_count=2)

    resp = client.post(
        "/api/v1/builds", json={"commander": "Test Commander", "mode": "guided"}, headers=auth_headers
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "ready"
    assert data["mode"] == "guided"
    build_id = data["build_id"]

    # Guided builds start in "ready" state; nothing runs until /advance is called.
    resp = client.get(f"/api/v1/builds/{build_id}", headers=auth_headers)
    assert resp.json()["data"]["status"] == "ready"

    resp = client.post(f"/api/v1/builds/{build_id}/advance", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is False
    assert data["added_cards"][0]["name"] == "Sol Ring"

    resp = client.post(f"/api/v1/builds/{build_id}/advance", headers=auth_headers)
    data = resp.json()["data"]
    assert data["done"] is True

    resp = client.get(f"/api/v1/builds/{build_id}/deck", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["summary"]["type_breakdown"]["total"] == 100


def test_guided_build_advance_rejects_auto_mode(client, auth_headers, monkeypatch):
    _fake_orchestrator(monkeypatch)
    resp = client.post("/api/v1/builds", json={"commander": "Test Commander"}, headers=auth_headers)
    build_id = resp.json()["data"]["build_id"]

    resp = client.post(f"/api/v1/builds/{build_id}/advance", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "BUILD_NOT_FOUND"


def test_guided_build_replace_and_alternatives(client, auth_headers, monkeypatch):
    _fake_guided_orchestrator(monkeypatch, stage_count=1)

    resp = client.post(
        "/api/v1/builds", json={"commander": "Test Commander", "mode": "guided"}, headers=auth_headers
    )
    build_id = resp.json()["data"]["build_id"]

    resp = client.get(
        f"/api/v1/builds/{build_id}/alternatives", params={"card": "Sol Ring"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]

    resp = client.post(
        f"/api/v1/builds/{build_id}/replace",
        json={"old_name": "Sol Ring", "new_name": "Arcane Signet"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["old_name"] == "Sol Ring"
    assert data["new_name"] == "Arcane Signet"

    resp = client.post(
        f"/api/v1/builds/{build_id}/replace",
        json={"old_name": "Not In Deck", "new_name": "Whatever"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "CARD_NOT_IN_DECK"


def test_guided_build_remove_card_and_undo(client, auth_headers, monkeypatch):
    _fake_guided_orchestrator(monkeypatch, stage_count=1)

    resp = client.post(
        "/api/v1/builds", json={"commander": "Test Commander", "mode": "guided"}, headers=auth_headers
    )
    build_id = resp.json()["data"]["build_id"]

    resp = client.post(
        f"/api/v1/builds/{build_id}/remove-card", json={"name": "Sol Ring"}, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["removed"] is True
    assert data["name"] == "Sol Ring"

    resp = client.post(
        f"/api/v1/builds/{build_id}/remove-card", json={"name": "Not In Deck"}, headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "CARD_NOT_IN_DECK"

    resp = client.post(f"/api/v1/builds/{build_id}/remove-card/undo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["restored"] is True
    assert data["name"] == "Sol Ring"
    assert data["count"] == 1

    # Nothing left to undo now.
    resp = client.post(f"/api/v1/builds/{build_id}/remove-card/undo", headers=auth_headers)
    assert resp.json()["data"]["restored"] is False


def test_guided_build_rerun_stage(client, auth_headers, monkeypatch):
    _fake_guided_orchestrator(monkeypatch, stage_count=2)

    resp = client.post(
        "/api/v1/builds", json={"commander": "Test Commander", "mode": "guided"}, headers=auth_headers
    )
    build_id = resp.json()["data"]["build_id"]

    resp = client.post(f"/api/v1/builds/{build_id}/rerun", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is False
    assert data["added_cards"][0]["name"] == "Sol Ring"


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
