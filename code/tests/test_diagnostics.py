import os
import importlib
import types
import pytest
from starlette.testclient import TestClient

fastapi = pytest.importorskip("fastapi")  # skip tests if FastAPI isn't installed


def load_app_with_env(**env: str) -> types.ModuleType:
    for key in (
        "SHOW_LOGS",
        "SHOW_DIAGNOSTICS",
        "SHOW_SETUP",
        "SHOW_COMMANDERS",
        "ENABLE_THEMES",
        "ENABLE_PWA",
        "ENABLE_PRESETS",
        "APP_VERSION",
        "THEME",
    ):
        os.environ.pop(key, None)
    for k, v in env.items():
        os.environ[k] = v
    import code.web.app as app_module  # type: ignore
    importlib.reload(app_module)
    return app_module


def test_healthz_ok_and_request_id_header():
    app_module = load_app_with_env()
    client = TestClient(app_module.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") in {"ok", "degraded"}
    assert "uptime_seconds" in data
    assert r.headers.get("X-Request-ID")


def test_404_renders_html_when_accept_html():
    app_module = load_app_with_env()
    client = TestClient(app_module.app)
    r = client.get("/this-does-not-exist", headers={"Accept": "text/html"})
    assert r.status_code == 404
    body = r.text.lower()
    assert "page not found" in body
    assert "go home" in body
    assert r.headers.get("X-Request-ID")


def test_htmx_http_exception_returns_json_with_request_id():
    app_module = load_app_with_env(SHOW_DIAGNOSTICS="1")
    client = TestClient(app_module.app)
    r = client.get("/diagnostics/trigger-error", headers={"HX-Request": "true"})
    assert r.status_code == 418
    data = r.json()
    assert data.get("error") is True
    assert data.get("status") == 418
    assert data.get("request_id")
    assert r.headers.get("X-Request-ID")


def test_unhandled_exception_returns_500_json_with_request_id():
    app_module = load_app_with_env(SHOW_DIAGNOSTICS="1")
    # Configure client to not re-raise server exceptions so we can assert the 500 response
    client = TestClient(app_module.app, raise_server_exceptions=False)
    r = client.get("/diagnostics/trigger-error?kind=unhandled", headers={"HX-Request": "true"})
    assert r.status_code == 500
    data = r.json()
    assert data.get("error") is True
    assert data.get("status") == 500
    assert data.get("request_id")
    assert r.headers.get("X-Request-ID")


def test_status_sys_summary_and_flags():
    app_module = load_app_with_env(
        SHOW_LOGS="1",
        SHOW_DIAGNOSTICS="1",
        SHOW_SETUP="1",
        SHOW_COMMANDERS="1",
        ENABLE_THEMES="1",
        ENABLE_PWA="1",
        ENABLE_PRESETS="1",
        APP_VERSION="testver",
        THEME="dark",
    )
    client = TestClient(app_module.app)
    r = client.get("/status/sys")
    assert r.status_code == 200
    data = r.json()
    assert data.get("version") == "testver"
    assert isinstance(data.get("uptime_seconds"), int)
    assert isinstance(data.get("server_time_utc"), str)
    flags = data.get("flags") or {}
    assert flags.get("SHOW_LOGS") is True
    assert flags.get("SHOW_DIAGNOSTICS") is True
    assert flags.get("SHOW_SETUP") is True
    assert flags.get("SHOW_COMMANDERS") is True
    # Theme-related flags
    assert flags.get("ENABLE_THEMES") is True
    assert flags.get("ENABLE_PWA") is True
    assert flags.get("ENABLE_PRESETS") is True
    assert flags.get("DEFAULT_THEME") == "dark"


def test_commanders_nav_hidden_when_flag_disabled():
    app_module = load_app_with_env(SHOW_COMMANDERS="0")
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert '<a href="/commanders"' not in body


def test_commanders_nav_visible_by_default():
    app_module = load_app_with_env()
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert '<a href="/commanders"' in body
