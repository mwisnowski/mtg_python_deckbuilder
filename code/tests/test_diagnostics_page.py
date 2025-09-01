from __future__ import annotations

import importlib
from starlette.testclient import TestClient


def test_diagnostics_page_gated_and_visible(monkeypatch):
    # Ensure disabled first
    monkeypatch.delenv("SHOW_DIAGNOSTICS", raising=False)
    import code.web.app as app_module
    importlib.reload(app_module)
    client = TestClient(app_module.app)
    r = client.get("/diagnostics")
    assert r.status_code == 404

    # Enabled: should render
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")
    importlib.reload(app_module)
    client2 = TestClient(app_module.app)
    r2 = client2.get("/diagnostics")
    assert r2.status_code == 200
    body = r2.text
    assert "Diagnostics" in body
    assert "Combos & Synergies" in body
