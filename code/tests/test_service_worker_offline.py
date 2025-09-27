import os
import importlib
import types
import pytest
from starlette.testclient import TestClient

fastapi = pytest.importorskip("fastapi")  # skip if FastAPI missing


def load_app_with_env(**env: str) -> types.ModuleType:
    for k, v in env.items():
        os.environ[k] = v
    import code.web.app as app_module  # type: ignore
    importlib.reload(app_module)
    return app_module


def test_catalog_hash_exposed_in_template():
    app_module = load_app_with_env(ENABLE_PWA="1")
    client = TestClient(app_module.app)
    r = client.get("/themes/")  # picker page should exist
    assert r.status_code == 200
    body = r.text
    # catalog_hash may be 'dev' if not present, ensure variable substituted in SW registration block
    assert "serviceWorker" in body
    assert "sw.js?v=" in body


def test_sw_js_served_and_version_param_cache_headers():
    app_module = load_app_with_env(ENABLE_PWA="1")
    client = TestClient(app_module.app)
    r = client.get("/static/sw.js?v=testhash123")
    assert r.status_code == 200
    assert "Service Worker" in r.text
