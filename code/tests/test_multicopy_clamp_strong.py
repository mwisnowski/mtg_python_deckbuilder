import importlib


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
    # Preseed 95 cards in the library
    b.card_library = {"Filler": {"Count": 95, "Role": "Test", "SubRole": "", "AddedBy": "Test"}}
    # Set a multi-copy selection that would exceed 100 by 15
    b._web_multi_copy = {  # type: ignore[attr-defined]
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
    # Clamp assertions
    assert int(res.get("clamped_overflow") or 0) == 15
    assert int(res.get("total_cards") or 0) == 100
    added = res.get("added_cards") or []
    # Only the Petitioners row should be present, and it should show 5 added
    assert len(added) == 1
    row = added[0]
    assert row.get("name") == "Persistent Petitioners"
    assert int(row.get("count") or 0) == 5
    # Ensure the preseeded 95 remain
    lib = ctx["builder"].card_library
    assert lib.get("Filler", {}).get("Count") == 95
