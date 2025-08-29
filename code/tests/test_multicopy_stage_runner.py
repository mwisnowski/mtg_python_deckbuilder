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
    b._web_multi_copy = selection  # type: ignore[attr-defined]
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
