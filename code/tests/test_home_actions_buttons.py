import os
import importlib
import types
from starlette.testclient import TestClient


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
        "RANDOM_UI",
    ):
        os.environ.pop(key, None)
    for k, v in env.items():
        os.environ[k] = v
    import code.web.app as app_module  # type: ignore
    importlib.reload(app_module)
    return app_module


def test_home_actions_show_all_enabled_buttons():
    app_module = load_app_with_env(
        SHOW_LOGS="1",
        SHOW_DIAGNOSTICS="1",
        SHOW_SETUP="1",
        SHOW_COMMANDERS="1",
        RANDOM_UI="1",
    )
    client = TestClient(app_module.app)
    response = client.get("/")
    body = response.text
    assert 'href="/setup"' in body
    assert 'href="/commanders"' in body
    assert 'href="/random"' in body
    assert 'href="/diagnostics"' in body
    assert 'href="/logs"' in body


def test_home_actions_hides_disabled_sections():
    app_module = load_app_with_env(
        SHOW_LOGS="0",
        SHOW_DIAGNOSTICS="0",
        SHOW_SETUP="0",
        SHOW_COMMANDERS="0",
        RANDOM_UI="0",
    )
    client = TestClient(app_module.app)
    response = client.get("/")
    body = response.text
    assert 'href="/setup"' not in body
    assert 'href="/commanders"' not in body
    assert 'href="/random"' not in body
    assert 'href="/diagnostics"' not in body
    assert 'href="/logs"' not in body
