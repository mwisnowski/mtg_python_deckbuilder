from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_diagnostics_combos_endpoint(tmp_path: Path, monkeypatch):
    # Enable diagnostics
    monkeypatch.setenv("SHOW_DIAGNOSTICS", "1")

    # Lazy import app after env set
    import importlib
    import code.web.app as app_module
    importlib.reload(app_module)

    client = TestClient(app_module.app)

    cpath = tmp_path / "config/card_lists/combos.json"
    spath = tmp_path / "config/card_lists/synergies.json"
    _write_json(
        cpath,
        {
            "list_version": "0.1.0",
            "pairs": [
                {"a": "Thassa's Oracle", "b": "Demonic Consultation", "cheap_early": True, "setup_dependent": False}
            ],
        },
    )
    _write_json(
        spath,
        {
            "list_version": "0.1.0",
            "pairs": [{"a": "Grave Pact", "b": "Phyrexian Altar"}],
        },
    )

    payload = {
        "names": ["Thassa’s Oracle", "Demonic Consultation", "Grave Pact", "Phyrexian Altar"],
        "combos_path": str(cpath),
        "synergies_path": str(spath),
    }
    resp = client.post("/diagnostics/combos", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["counts"]["combos"] == 1
    assert data["counts"]["synergies"] == 1
    assert data["versions"]["combos"] == "0.1.0"
    # Ensure flags are present from payload
    c = data["combos"][0]
    assert c.get("cheap_early") is True
    assert c.get("setup_dependent") is False