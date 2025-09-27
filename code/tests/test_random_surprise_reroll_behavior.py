from __future__ import annotations

import importlib
import itertools
import os
from typing import Any

from fastapi.testclient import TestClient


def _make_stub_result(seed: int | None, theme: Any, primary: Any, secondary: Any = None, tertiary: Any = None):
    class _Result:
        pass

    res = _Result()
    res.seed = int(seed) if seed is not None else 0
    res.commander = f"Commander-{res.seed}"
    res.decklist = []
    res.theme = theme
    res.primary_theme = primary
    res.secondary_theme = secondary
    res.tertiary_theme = tertiary
    res.resolved_themes = [t for t in [primary, secondary, tertiary] if t]
    res.combo_fallback = True if primary and primary != theme else False
    res.synergy_fallback = False
    res.fallback_reason = "fallback" if res.combo_fallback else None
    res.constraints = {}
    res.diagnostics = {}
    res.summary = None
    res.theme_fallback = bool(res.combo_fallback or res.synergy_fallback)
    res.csv_path = None
    res.txt_path = None
    res.compliance = None
    res.original_theme = theme
    return res


def test_surprise_reuses_requested_theme(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    random_util = importlib.import_module("random_util")
    seed_iter = itertools.count(1000)
    monkeypatch.setattr(random_util, "generate_seed", lambda: next(seed_iter))

    random_entrypoint = importlib.import_module("deck_builder.random_entrypoint")
    build_calls: list[dict[str, Any]] = []

    def fake_build_random_full_deck(*, theme, constraints, seed, attempts, timeout_s, primary_theme, secondary_theme, tertiary_theme):
        build_calls.append({
            "theme": theme,
            "primary": primary_theme,
            "secondary": secondary_theme,
            "tertiary": tertiary_theme,
            "seed": seed,
        })
        return _make_stub_result(seed, theme, "ResolvedTokens")

    monkeypatch.setattr(random_entrypoint, "build_random_full_deck", fake_build_random_full_deck)

    web_app_module = importlib.import_module("code.web.app")
    web_app_module = importlib.reload(web_app_module)

    client = TestClient(web_app_module.app)

    # Initial surprise request with explicit theme
    resp1 = client.post("/hx/random_reroll", json={"mode": "surprise", "primary_theme": "Tokens"})
    assert resp1.status_code == 200
    assert build_calls[0]["primary"] == "Tokens"
    assert build_calls[0]["theme"] == "Tokens"

    # Subsequent surprise request without providing themes should reuse requested input, not resolved fallback
    resp2 = client.post("/hx/random_reroll", json={"mode": "surprise"})
    assert resp2.status_code == 200
    assert len(build_calls) == 2
    assert build_calls[1]["primary"] == "Tokens"
    assert build_calls[1]["theme"] == "Tokens"


def test_reroll_same_commander_uses_resolved_cache(monkeypatch):
    monkeypatch.setenv("RANDOM_MODES", "1")
    monkeypatch.setenv("RANDOM_UI", "1")
    monkeypatch.setenv("CSV_FILES_DIR", os.path.join("csv_files", "testdata"))

    random_util = importlib.import_module("random_util")
    seed_iter = itertools.count(2000)
    monkeypatch.setattr(random_util, "generate_seed", lambda: next(seed_iter))

    random_entrypoint = importlib.import_module("deck_builder.random_entrypoint")
    build_calls: list[dict[str, Any]] = []

    def fake_build_random_full_deck(*, theme, constraints, seed, attempts, timeout_s, primary_theme, secondary_theme, tertiary_theme):
        build_calls.append({
            "theme": theme,
            "primary": primary_theme,
            "seed": seed,
        })
        return _make_stub_result(seed, theme, "ResolvedArtifacts")

    monkeypatch.setattr(random_entrypoint, "build_random_full_deck", fake_build_random_full_deck)

    headless_runner = importlib.import_module("headless_runner")
    locked_runs: list[dict[str, Any]] = []

    class DummyBuilder:
        def __init__(self, commander: str):
            self.commander_name = commander
            self.commander = commander
            self.deck_list_final: list[Any] = []
            self.last_csv_path = None
            self.last_txt_path = None
            self.custom_export_base = None

        def build_deck_summary(self):
            return None

        def export_decklist_csv(self):
            return None

        def export_decklist_text(self, filename: str | None = None):  # pragma: no cover - optional path
            return None

        def compute_and_print_compliance(self, base_stem: str | None = None):  # pragma: no cover - optional path
            return None

    def fake_run(command_name: str, seed: int | None = None):
        locked_runs.append({"commander": command_name, "seed": seed})
        return DummyBuilder(command_name)

    monkeypatch.setattr(headless_runner, "run", fake_run)

    web_app_module = importlib.import_module("code.web.app")
    web_app_module = importlib.reload(web_app_module)
    from code.web.services import tasks

    tasks._SESSIONS.clear()
    client = TestClient(web_app_module.app)

    # Initial surprise build to populate session cache
    resp1 = client.post("/hx/random_reroll", json={"mode": "surprise", "primary_theme": "Artifacts"})
    assert resp1.status_code == 200
    assert build_calls[0]["primary"] == "Artifacts"
    commander_name = f"Commander-{build_calls[0]['seed']}"
    first_seed = build_calls[0]["seed"]

    form_payload = [
        ("mode", "reroll_same_commander"),
        ("commander", commander_name),
        ("seed", str(first_seed)),
        ("primary_theme", "ResolvedArtifacts"),
        ("primary_theme", "UserOverride"),
        ("resolved_themes", "ResolvedArtifacts"),
    ]

    from urllib.parse import urlencode

    encoded = urlencode(form_payload, doseq=True)
    resp2 = client.post(
        "/hx/random_reroll",
        content=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp2.status_code == 200
    assert resp2.request.headers.get("Content-Type") == "application/x-www-form-urlencoded"
    assert len(locked_runs) == 1  # headless runner invoked once
    assert len(build_calls) == 1  # no additional filter build

    # Hidden input should reflect resolved theme, not user override
    assert 'id="current-primary-theme"' in resp2.text
    assert 'value="ResolvedArtifacts"' in resp2.text
    assert "UserOverride" not in resp2.text

    sid = client.cookies.get("sid")
    assert sid
    session = tasks.get_session(sid)
    requested = session.get("random_build", {}).get("requested_themes") or {}
    assert requested.get("primary") == "Artifacts"
