import sys
from pathlib import Path

from fastapi.testclient import TestClient

from code.web import app as web_app  # type: ignore
from code.web.app import app  # type: ignore

# Ensure project root on sys.path for absolute imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_client() -> TestClient:
    return TestClient(app)


def test_theme_stats_requires_diagnostics_flag(monkeypatch):
    monkeypatch.setattr(web_app, "SHOW_DIAGNOSTICS", False)
    client = _make_client()
    resp = client.get("/status/random_theme_stats")
    assert resp.status_code == 404


def test_theme_stats_payload_includes_core_fields(monkeypatch):
    monkeypatch.setattr(web_app, "SHOW_DIAGNOSTICS", True)
    client = _make_client()
    resp = client.get("/status/random_theme_stats")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is True
    stats = payload.get("stats") or {}
    assert "commanders" in stats
    assert "unique_tokens" in stats
    assert "total_assignments" in stats
    assert isinstance(stats.get("top_tokens"), list)