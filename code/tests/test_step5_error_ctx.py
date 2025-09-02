from __future__ import annotations

from types import SimpleNamespace

from code.web.services.build_utils import step5_error_ctx


class _Req(SimpleNamespace):
    # minimal object to satisfy template context needs
    pass


def test_step5_error_ctx_shape():
    req = _Req()
    sess = {
        "commander": "Atraxa, Praetors' Voice",
        "tags": ["+1/+1 Counters"],
        "bracket": 3,
        "ideals": {"lands": 36},
        "use_owned_only": False,
        "prefer_owned": False,
        "replace_mode": True,
        "locks": ["sol ring"],
    }
    ctx = step5_error_ctx(req, sess, "Boom")
    # Ensure required keys for _step5.html are present with safe defaults
    for k in (
        "request",
        "commander",
        "tags",
        "bracket",
        "values",
        "owned_only",
        "prefer_owned",
        "owned_set",
        "game_changers",
        "replace_mode",
        "prefer_combos",
        "combo_target_count",
        "combo_balance",
        "status",
        "stage_label",
        "log",
        "added_cards",
        "i",
        "n",
        "csv_path",
        "txt_path",
        "summary",
        "show_skipped",
        "total_cards",
        "added_total",
        "skipped",
    ):
        assert k in ctx
    assert ctx["status"] == "Error"
    assert isinstance(ctx["added_cards"], list)
    assert ctx["show_skipped"] is False


def test_step5_error_ctx_respects_flags():
    req = _Req()
    sess = {
        "use_owned_only": True,
        "prefer_owned": True,
        "combo_target_count": 3,
        "combo_balance": "early",
    }
    ctx = step5_error_ctx(req, sess, "Oops", include_name=False, include_locks=False)
    assert "name" not in ctx
    assert "locks" not in ctx
    # Flags should flow through
    assert ctx["owned_only"] is True
    assert ctx["prefer_owned"] is True
    assert ctx["combo_target_count"] == 3
    assert ctx["combo_balance"] == "early"
