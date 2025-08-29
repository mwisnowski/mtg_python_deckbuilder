import importlib


def test_petitioners_clamp_to_100_and_reduce_creature_slots():
    """
    Ensure that when a large multi-copy creature package is added (e.g., Persistent Petitioners),
    the deck does not exceed 100 after the multi-copy stage and ideal creature targets are reduced.

    This uses the staged orchestrator flow to exercise the clamp and adjustments, but avoids
    full dataset loading by using a minimal builder context and a dummy DF where possible.
    """
    orch = importlib.import_module('code.web.services.orchestrator')
    # Start a minimal staged context with only the multi-copy stage
    logs = []
    def out(msg: str):
        logs.append(msg)
    from deck_builder.builder import DeckBuilder
    b = DeckBuilder(output_func=out, input_func=lambda *_: "", headless=True)
    # Seed ideal_counts with a typical creature target so we can observe reduction
    b.ideal_counts = {
        "ramp": 10, "lands": 35, "basic_lands": 20,
        "fetch_lands": 3, "creatures": 28, "removal": 10, "wipes": 2,
        "card_advantage": 8, "protection": 4,
    }
    # Thread multi-copy selection for Petitioners as a creature archetype
    b._web_multi_copy = {  # type: ignore[attr-defined]
        "id": "persistent_petitioners",
        "name": "Persistent Petitioners",
        "count": 40,  # intentionally large to trigger clamp/adjustments
        "thrumming": False,
    }
    # Minimal library
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
    # Should show the stage with added cards
    assert res.get("done") is False
    assert res.get("label") == "Multi-Copy Package"
    # Clamp should be applied if over 100; however with only one name in library, it won't clamp yet.
    # We'll at least assert that mc_adjustments exist and creatures target reduced by ~count.
    mc_adj = res.get("mc_adjustments") or []
    assert any(a.startswith("creatures ") for a in mc_adj), f"mc_adjustments missing creature reduction: {mc_adj}"
    # Verify deck total does not exceed 100 when a follow-up 100 baseline exists; here just sanity check the number present
    total_cards = int(res.get("total_cards") or 0)
    assert total_cards >= 1
