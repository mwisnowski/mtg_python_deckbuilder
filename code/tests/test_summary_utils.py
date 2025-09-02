from __future__ import annotations

from code.web.services.summary_utils import summary_ctx


def test_summary_ctx_empty_summary():
    ctx = summary_ctx(summary=None, commander="Test Commander", tags=["Aggro"])
    assert isinstance(ctx, dict)
    assert ctx.get("owned_set") is not None
    assert isinstance(ctx.get("combos"), list)
    assert isinstance(ctx.get("synergies"), list)
    assert ctx.get("versions") == {}
    assert ctx.get("commander") == "Test Commander"
    assert ctx.get("tags") == ["Aggro"]


def test_summary_ctx_with_summary_basic():
    # Minimal fake summary structure sufficient for detect_for_summary to accept
    summary = {
        "type_breakdown": {"counts": {}, "order": [], "cards": {}, "total": 0},
        "pip_distribution": {"counts": {}, "weights": {}},
        "mana_generation": {},
        "mana_curve": {"total_spells": 0},
        "colors": [],
    }
    ctx = summary_ctx(summary=summary, commander="Cmdr", tags=["Spells"])
    assert "owned_set" in ctx and isinstance(ctx["owned_set"], set)
    assert "game_changers" in ctx
    assert "combos" in ctx and isinstance(ctx["combos"], list)
    assert "synergies" in ctx and isinstance(ctx["synergies"], list)
    assert "versions" in ctx and isinstance(ctx["versions"], dict)
