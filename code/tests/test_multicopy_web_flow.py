import importlib
import pytest
try:
    from starlette.testclient import TestClient  # type: ignore
except Exception:  # pragma: no cover - optional dep in CI
    TestClient = None  # type: ignore


def _inject_minimal_ctx(client, selection: dict):
    # Touch session to get sid
    r = client.get('/build')
    assert r.status_code == 200
    sid = r.cookies.get('sid')
    assert sid

    tasks = importlib.import_module('code.web.services.tasks')
    sess = tasks.get_session(sid)
    # Minimal commander/tag presence to satisfy route guards
    sess['commander'] = 'Dummy Commander'
    sess['tags'] = []

    # Build a minimal staged context with only the builder object; no stages yet
    from deck_builder.builder import DeckBuilder
    b = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    b.card_library = {}
    ctx = {
        'builder': b,
        'logs': [],
        'stages': [],
        'idx': 0,
        'last_log_idx': 0,
        'csv_path': None,
        'txt_path': None,
        'snapshot': None,
        'history': [],
        'locks': set(),
        'custom_export_base': None,
    }
    sess['build_ctx'] = ctx
    # Persist multi-copy selection so the route injects the stage on continue
    sess['multi_copy'] = selection
    return sid


def test_step5_continue_runs_multicopy_stage_and_renders_additions():
    if TestClient is None:
        pytest.skip("starlette not available")
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    sel = {"id": "dragons_approach", "name": "Dragon's Approach", "count": 12, "thrumming": True}
    _inject_minimal_ctx(client, sel)
    r = client.post('/build/step5/continue')
    assert r.status_code == 200
    body = r.text
    # Should show the stage label and added cards including quantities and Thrumming Stone
    assert "Dragon's Approach" in body
    assert "×12" in body or "x12" in body or "× 12" in body
    assert "Thrumming Stone" in body
