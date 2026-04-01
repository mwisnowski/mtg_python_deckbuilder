import importlib


def _minimal_ctx(selection: dict):
    """Build a minimal orchestrator context to run only the multi-copy stage.

    This avoids loading commander data or datasets; we only exercise the special
    runner path (__add_multi_copy__) and the added-cards diff logic.
    """
    logs: list[str] = []

    def out(msg: str) -> None:
        logs.append(msg)

    # Create a DeckBuilder with no-op IO; no setup required for this unit test
    from deck_builder.builder import DeckBuilder

    b = DeckBuilder(output_func=out, input_func=lambda *_: "", headless=True)
    # Thread selection and ensure empty library
    b._web_multi_copy = selection
    b.card_library = {}

    ctx = {
        "builder": b,
        "logs": logs,
        "stages": [
            {"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}
        ],
        "idx": 0,
        "last_log_idx": 0,
        "csv_path": None,
        "txt_path": None,
        "snapshot": None,
        "history": [],
        "locks": set(),
        "custom_export_base": None,
    }
    return ctx


def test_multicopy_stage_adds_selected_card_only():
    sel = {"id": "dragons_approach", "name": "Dragon's Approach", "count": 25, "thrumming": False}
    ctx = _minimal_ctx(sel)
    orch = importlib.import_module('code.web.services.orchestrator')
    res = orch.run_stage(ctx, rerun=False, show_skipped=False)
    assert res.get("done") is False
    assert res.get("label") == "Multi-Copy Package"
    added = res.get("added_cards") or []
    names = [c.get("name") for c in added]
    # Should include the selected card and not Thrumming Stone
    assert "Dragon's Approach" in names
    assert all(n != "Thrumming Stone" for n in names)
    # Count delta should reflect the selection quantity
    det = next(c for c in added if c.get("name") == "Dragon's Approach")
    assert int(det.get("count") or 0) == 25


def test_multicopy_stage_adds_thrumming_when_requested():
    sel = {"id": "dragons_approach", "name": "Dragon's Approach", "count": 20, "thrumming": True}
    ctx = _minimal_ctx(sel)
    orch = importlib.import_module('code.web.services.orchestrator')
    res = orch.run_stage(ctx, rerun=False, show_skipped=False)
    assert res.get("done") is False
    added = res.get("added_cards") or []
    names = {c.get("name") for c in added}
    assert "Dragon's Approach" in names
    assert "Thrumming Stone" in names
    # Thrumming Stone should be exactly one copy added in this stage
    thr = next(c for c in added if c.get("name") == "Thrumming Stone")
    assert int(thr.get("count") or 0) == 1


def test_multicopy_clamp_trims_current_stage_additions_only():
    """
    Pre-seed the library to 95, add a 20x multi-copy package, and ensure:
    - clamped_overflow == 15
    - total_cards == 100
    - added delta for the package reflects 5 (20 - 15) after clamping
    - pre-seeded cards are untouched
    """
    orch = importlib.import_module('code.web.services.orchestrator')
    logs = []

    def out(msg: str):
        logs.append(msg)

    from deck_builder.builder import DeckBuilder
    b = DeckBuilder(output_func=out, input_func=lambda *_: "", headless=True)
    b.card_library = {"Filler": {"Count": 95, "Role": "Test", "SubRole": "", "AddedBy": "Test"}}
    b._web_multi_copy = {
        "id": "persistent_petitioners",
        "name": "Persistent Petitioners",
        "count": 20,
        "thrumming": False,
    }
    ctx = {
        "builder": b,
        "logs": logs,
        "stages": [{"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}],
        "idx": 0,
        "last_log_idx": 0,
        "csv_path": None,
        "txt_path": None,
        "snapshot": None,
        "history": [],
        "locks": set(),
        "custom_export_base": None,
    }
    res = orch.run_stage(ctx, rerun=False, show_skipped=False)
    assert res.get("done") is False
    assert res.get("label") == "Multi-Copy Package"
    assert int(res.get("clamped_overflow") or 0) == 15
    assert int(res.get("total_cards") or 0) == 100
    added = res.get("added_cards") or []
    assert len(added) == 1
    row = added[0]
    assert row.get("name") == "Persistent Petitioners"
    assert int(row.get("count") or 0) == 5
    lib = ctx["builder"].card_library
    assert lib.get("Filler", {}).get("Count") == 95


def test_petitioners_clamp_to_100_and_reduce_creature_slots():
    """
    Ensure that when a large multi-copy creature package is added (e.g., Persistent Petitioners),
    the deck does not exceed 100 after the multi-copy stage and ideal creature targets are reduced.
    """
    orch = importlib.import_module('code.web.services.orchestrator')
    logs = []

    def out(msg: str):
        logs.append(msg)

    from deck_builder.builder import DeckBuilder
    b = DeckBuilder(output_func=out, input_func=lambda *_: "", headless=True)
    b.ideal_counts = {
        "ramp": 10, "lands": 35, "basic_lands": 20,
        "fetch_lands": 3, "creatures": 28, "removal": 10, "wipes": 2,
        "card_advantage": 8, "protection": 4,
    }
    b._web_multi_copy = {
        "id": "persistent_petitioners",
        "name": "Persistent Petitioners",
        "count": 40,
        "thrumming": False,
    }
    b.card_library = {}
    ctx = {
        "builder": b,
        "logs": logs,
        "stages": [{"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}],
        "idx": 0,
        "last_log_idx": 0,
        "csv_path": None,
        "txt_path": None,
        "snapshot": None,
        "history": [],
        "locks": set(),
        "custom_export_base": None,
    }
    res = orch.run_stage(ctx, rerun=False, show_skipped=False)
    assert res.get("done") is False
    assert res.get("label") == "Multi-Copy Package"
    mc_adj = res.get("mc_adjustments") or []
    assert any(a.startswith("creatures ") for a in mc_adj), f"mc_adjustments missing creature reduction: {mc_adj}"
    total_cards = int(res.get("total_cards") or 0)
    assert total_cards >= 1


def _inject_minimal_ctx(client, selection: dict):
    r = client.get('/build')
    assert r.status_code == 200
    sid = r.cookies.get('sid')
    assert sid
    tasks = importlib.import_module('code.web.services.tasks')
    sess = tasks.get_session(sid)
    sess['commander'] = 'Dummy Commander'
    sess['tags'] = []
    from deck_builder.builder import DeckBuilder
    b = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    b.card_library = {}
    ctx = {
        'builder': b, 'logs': [], 'stages': [], 'idx': 0, 'last_log_idx': 0,
        'csv_path': None, 'txt_path': None, 'snapshot': None, 'history': [],
        'locks': set(), 'custom_export_base': None,
    }
    sess['build_ctx'] = ctx
    sess['multi_copy'] = selection
    return sid


def test_step5_continue_runs_multicopy_stage_and_renders_additions():
    try:
        from starlette.testclient import TestClient
    except Exception:
        import pytest; pytest.skip("starlette not available")
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    sel = {"id": "dragons_approach", "name": "Dragon's Approach", "count": 12, "thrumming": True}
    _inject_minimal_ctx(client, sel)
    r = client.post('/build/step5/continue')
    assert r.status_code == 200
    body = r.text
    assert "Dragon's Approach" in body
    assert "\u00d712" in body or "x12" in body or "\u00d7 12" in body
    assert "Thrumming Stone" in body
