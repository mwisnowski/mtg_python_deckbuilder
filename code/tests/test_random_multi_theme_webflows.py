from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Iterator, List
from urllib.parse import urlencode

import importlib
import pytest
from fastapi.testclient import TestClient

from deck_builder.random_entrypoint import RandomFullBuildResult


def _decode_state_token(token: str) -> Dict[str, Any]:
    pad = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + pad).encode("ascii")).decode("utf-8")
    return json.loads(raw)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    web_app_module = importlib.import_module("code.web.app")
    web_app_module = importlib.reload(web_app_module)
    from code.web.services import tasks

    tasks._SESSIONS.clear()
    with TestClient(web_app_module.app) as test_client:
        yield test_client
    tasks._SESSIONS.clear()


def _make_full_result(seed: int) -> RandomFullBuildResult:
    return RandomFullBuildResult(
        seed=seed,
        commander=f"Commander-{seed}",
        theme="Aggro",
        constraints={},
        primary_theme="Aggro",
        secondary_theme="Tokens",
        tertiary_theme="Equipment",
        resolved_themes=["aggro", "tokens", "equipment"],
        combo_fallback=False,
        synergy_fallback=False,
        fallback_reason=None,
        decklist=[{"name": "Sample Card", "count": 1}],
        diagnostics={"elapsed_ms": 5},
        summary={"meta": {"existing": True}},
        csv_path=None,
        txt_path=None,
        compliance=None,
    )


def test_random_multi_theme_reroll_same_commander_preserves_resolved(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import deck_builder.random_entrypoint as random_entrypoint
    import headless_runner
    from code.web.services import tasks

    build_calls: List[Dict[str, Any]] = []

    def fake_build_random_full_deck(*, theme, constraints, seed, attempts, timeout_s, primary_theme, secondary_theme, tertiary_theme):
        build_calls.append(
            {
                "theme": theme,
                "primary": primary_theme,
                "secondary": secondary_theme,
                "tertiary": tertiary_theme,
                "seed": seed,
            }
        )
        return _make_full_result(int(seed))

    monkeypatch.setattr(random_entrypoint, "build_random_full_deck", fake_build_random_full_deck)

    class DummyBuilder:
        def __init__(self, commander: str, seed: int) -> None:
            self.commander_name = commander
            self.commander = commander
            self.deck_list_final: List[Dict[str, Any]] = []
            self.last_csv_path = None
            self.last_txt_path = None
            self.custom_export_base = commander

        def build_deck_summary(self) -> Dict[str, Any]:
            return {"meta": {"rebuild": True}}

        def export_decklist_csv(self) -> str:
            return "deck_files/placeholder.csv"

        def export_decklist_text(self, filename: str | None = None) -> str:
            return "deck_files/placeholder.txt"

        def compute_and_print_compliance(self, base_stem: str | None = None) -> Dict[str, Any]:
            return {"ok": True}

    reroll_runs: List[Dict[str, Any]] = []

    def fake_run(command_name: str, seed: int | None = None):
        reroll_runs.append({"commander": command_name, "seed": seed})
        return DummyBuilder(command_name, seed or 0)

    monkeypatch.setattr(headless_runner, "run", fake_run)

    tasks._SESSIONS.clear()

    resp1 = client.post(
        "/hx/random_reroll",
        json={
            "mode": "surprise",
            "primary_theme": "Aggro",
            "secondary_theme": "Tokens",
            "tertiary_theme": "Equipment",
            "seed": 1010,
        },
    )
    assert resp1.status_code == 200, resp1.text
    assert build_calls and build_calls[0]["primary"] == "Aggro"
    assert "value=\"aggro||tokens||equipment\"" in resp1.text

    sid = client.cookies.get("sid")
    assert sid
    session = tasks.get_session(sid)
    resolved_list = session.get("random_build", {}).get("resolved_theme_info", {}).get("resolved_list")
    assert resolved_list == ["aggro", "tokens", "equipment"]

    commander = f"Commander-{build_calls[0]['seed']}"
    form_payload = [
        ("mode", "reroll_same_commander"),
        ("commander", commander),
        ("seed", str(build_calls[0]["seed"])),
        ("resolved_themes", "aggro||tokens||equipment"),
    ]
    encoded = urlencode(form_payload, doseq=True)
    resp2 = client.post(
        "/hx/random_reroll",
        content=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp2.status_code == 200, resp2.text
    assert len(build_calls) == 1
    assert reroll_runs and reroll_runs[0]["commander"] == commander
    assert "value=\"aggro||tokens||equipment\"" in resp2.text

    session_after = tasks.get_session(sid)
    resolved_after = session_after.get("random_build", {}).get("resolved_theme_info", {}).get("resolved_list")
    assert resolved_after == ["aggro", "tokens", "equipment"]


def test_random_multi_theme_permalink_roundtrip(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import deck_builder.random_entrypoint as random_entrypoint
    from code.web.services import tasks

    seeds_seen: List[int] = []

    def fake_build_random_full_deck(*, theme, constraints, seed, attempts, timeout_s, primary_theme, secondary_theme, tertiary_theme):
        seeds_seen.append(int(seed))
        return _make_full_result(int(seed))

    monkeypatch.setattr(random_entrypoint, "build_random_full_deck", fake_build_random_full_deck)

    tasks._SESSIONS.clear()

    resp = client.post(
        "/api/random_full_build",
        json={
            "seed": 4242,
            "primary_theme": "Aggro",
            "secondary_theme": "Tokens",
            "tertiary_theme": "Equipment",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["primary_theme"] == "Aggro"
    assert body["secondary_theme"] == "Tokens"
    assert body["tertiary_theme"] == "Equipment"
    assert body["resolved_themes"] == ["aggro", "tokens", "equipment"]
    permalink = body["permalink"]
    assert permalink and permalink.startswith("/build/from?state=")

    visit = client.get(permalink)
    assert visit.status_code == 200

    state_resp = client.get("/build/permalink")
    assert state_resp.status_code == 200, state_resp.text
    state_payload = state_resp.json()
    token = state_payload["permalink"].split("state=", 1)[1]
    decoded = _decode_state_token(token)
    random_section = decoded.get("random") or {}
    assert random_section.get("primary_theme") == "Aggro"
    assert random_section.get("secondary_theme") == "Tokens"
    assert random_section.get("tertiary_theme") == "Equipment"
    assert random_section.get("resolved_themes") == ["aggro", "tokens", "equipment"]
    requested = random_section.get("requested_themes") or {}
    assert requested.get("primary") == "Aggro"
    assert requested.get("secondary") == "Tokens"
    assert requested.get("tertiary") == "Equipment"
    assert seeds_seen == [4242]