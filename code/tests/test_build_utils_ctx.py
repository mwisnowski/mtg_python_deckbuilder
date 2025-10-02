from __future__ import annotations

from code.web.services.build_utils import start_ctx_from_session, owned_set, owned_names


def _fake_session(**kw):
    # Provide minimal session keys used by start_ctx_from_session
    base = {
        "commander": "Cmdr",
        "tags": ["Aggro", "Spells"],
        "bracket": 3,
        "ideals": {"creatures": 25},
        "tag_mode": "AND",
        "use_owned_only": False,
        "prefer_owned": False,
        "locks": [],
        "custom_export_base": "TestDeck",
        "multi_copy": None,
        "prefer_combos": False,
        "combo_target_count": 2,
        "combo_balance": "mix",
        "swap_mdfc_basics": False,
    }
    base.update(kw)
    return base


def test_owned_helpers_do_not_crash():
    # These reflect over the owned store; they should be resilient
    s = owned_set()
    assert isinstance(s, set)
    n = owned_names()
    assert isinstance(n, list)


def test_start_ctx_from_session_minimal(monkeypatch):
    # Avoid integration dependency by faking orchestrator.start_build_ctx
    calls = {}
    def _fake_start_build_ctx(**kwargs):
        calls.update(kwargs)
        return {"builder": object(), "stages": [], "idx": 0, "last_visible_idx": 0}
    import code.web.services.build_utils as bu
    monkeypatch.setattr(bu.orch, "start_build_ctx", _fake_start_build_ctx)

    sess = _fake_session()
    ctx = start_ctx_from_session(sess, set_on_session=False)
    assert isinstance(ctx, dict)
    assert "builder" in ctx
    assert "stages" in ctx
    assert "idx" in ctx
    assert calls.get("swap_mdfc_basics") is False


def test_start_ctx_from_session_sets_on_session(monkeypatch):
    def _fake_start_build_ctx(**kwargs):
        return {"builder": object(), "stages": [], "idx": 0}
    import code.web.services.build_utils as bu
    monkeypatch.setattr(bu.orch, "start_build_ctx", _fake_start_build_ctx)

    sess = _fake_session()
    ctx = start_ctx_from_session(sess, set_on_session=True)
    assert sess.get("build_ctx") == ctx
