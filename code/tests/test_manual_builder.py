"""Manual Deck Builder tests (Roadmap 25).

Milestone 1: mode="manual" must skip the auto-build pipeline entirely and
redirect to the manual builder view instead.

Milestone 2: the pool grid must be filtered to the commander's color
identity, while over-budget cards stay visible (budget is a client-side
flag only, matching the auto-builder's own step 5 behavior).
"""
from __future__ import annotations

import importlib

import pandas as pd
from starlette.testclient import TestClient


def _empty_pool_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["name", "colorIdentity", "type", "manaValue", "themeTags", "edhrecRank", "isNew"])


def test_mode_manual_skips_pipeline(monkeypatch):
    # Import code.web.app first: it's the module that fully wires up the
    # (pre-existing) circular import between app.py and the route modules.
    app_module = importlib.import_module("code.web.app")
    build_newflow = importlib.import_module("code.web.routes.build_newflow")
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    # Avoid the setup-prompt early-return and heavy color-identity lookup so
    # this test only depends on real commander validation (orch.commander_select).
    monkeypatch.setattr(build_newflow, "_is_setup_ready", lambda: True)
    monkeypatch.setattr(build_newflow, "_is_setup_stale", lambda: False)
    monkeypatch.setattr(
        manual_builder_service, "resolve_color_identity", lambda *a, **k: ["R", "G"]
    )
    # Pool data isn't under test here; avoid touching the real all_cards.parquet.
    monkeypatch.setattr(manual_builder_service, "get_card_pool", lambda sess: _empty_pool_df())

    pipeline_started = {"value": False}

    def _fake_start_ctx(sess):
        pipeline_started["value"] = True
        return {}

    monkeypatch.setattr(build_newflow, "start_ctx_from_session", _fake_start_ctx)

    client = TestClient(app_module.app)
    client.get("/build")  # establish session cookie

    resp = client.post(
        "/build/new",
        data={
            "commander": "Inti, Seneschal of the Sun",
            "bracket": 3,
            "mode": "manual",
        },
    )

    assert resp.status_code == 200
    assert resp.headers.get("hx-redirect", "").startswith("/decks/manual/")
    assert pipeline_started["value"] is False

    sid = client.cookies.get("sid")
    resp2 = client.get(f"/decks/manual/{sid}")
    assert resp2.status_code == 200
    assert "Inti, Seneschal of the Sun" in resp2.text


def test_pool_filtered_to_color_identity_and_budget_visible(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    df = pd.DataFrame([
        {"name": "Rampant Growth", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Ramp"], "edhrecRank": 500.0, "isNew": False},
        {"name": "Lightning Bolt", "colorIdentity": "R", "type": "Instant", "manaValue": 1.0,
         "themeTags": ["Removal"], "edhrecRank": 100.0, "isNew": False},
        {"name": "Doom Blade", "colorIdentity": "B", "type": "Instant", "manaValue": 2.0,
         "themeTags": ["Removal"], "edhrecRank": 200.0, "isNew": False},
        {"name": "Expensive Rock", "colorIdentity": "", "type": "Artifact", "manaValue": 3.0,
         "themeTags": ["Ramp"], "edhrecRank": 50.0, "isNew": False},
    ])

    class _FakeLoader:
        def load(self):
            return df

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)

    sess = {
        "color_identity": ["R", "G"],
        "commander": "Some Commander",
        "budget_config": {"total": 50.0, "card_ceiling": 2.0},
    }
    result = manual_builder_service.query_pool(sess)
    names = {c["name"] for c in result["cards"]}

    assert "Doom Blade" not in names  # off-color (B) excluded from an RG commander's pool
    assert "Rampant Growth" in names
    assert "Lightning Bolt" in names
    # Over-budget cards stay in the pool; budget is flagged client-side only.
    assert "Expensive Rock" in names


def test_pool_excludes_off_color_fetch_lands(monkeypatch):
    """Fetch lands have no colorIdentity pips, so the plain color-identity
    subset check alone always lets them through. A W/G deck shouldn't see
    Polluted Delta (Island/Swamp) even though it's technically colorless.
    """
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    df = pd.DataFrame([
        {"name": "Polluted Delta", "colorIdentity": "", "type": "Land", "manaValue": 0.0,
         "themeTags": [], "metadataTags": ["Island Fetch", "Swamp Fetch"], "edhrecRank": 10.0, "isNew": False},
        {"name": "Windswept Heath", "colorIdentity": "", "type": "Land", "manaValue": 0.0,
         "themeTags": [], "metadataTags": ["Plains Fetch", "Forest Fetch"], "edhrecRank": 20.0, "isNew": False},
        {"name": "Evolving Wilds", "colorIdentity": "", "type": "Land", "manaValue": 0.0,
         "themeTags": [], "metadataTags": ["Any Basic Fetch"], "edhrecRank": 30.0, "isNew": False},
    ])

    class _FakeLoader:
        def load(self):
            return df

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)

    sess = {"color_identity": ["W", "G"], "commander": "Some Commander"}
    pool = manual_builder_service.get_card_pool(sess)
    names = set(pool["name"].astype(str))

    assert "Polluted Delta" not in names  # fetches Island/Swamp, neither in W/G
    assert "Windswept Heath" in names     # fetches Plains/Forest, matches W/G
    assert "Evolving Wilds" in names      # universal fetch, always allowed


def test_pool_dedupes_double_faced_card_rows(monkeypatch):
    """A DFC/split card is stored as one row per face sharing the same
    `name`; the pool should show it once, with themeTags merged from both
    faces."""
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    df = pd.DataFrame([
        {"name": "Blazing Firesinger // Seething Song", "colorIdentity": "R", "type": "Creature - Human",
         "manaValue": 3.0, "themeTags": ["Aggro"], "edhrecRank": 400.0, "isNew": False, "side": "a"},
        {"name": "Blazing Firesinger // Seething Song", "colorIdentity": "R", "type": "Sorcery",
         "manaValue": 2.0, "themeTags": ["Ritual"], "edhrecRank": 400.0, "isNew": False, "side": "b"},
    ])

    class _FakeLoader:
        def load(self):
            return df

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)

    sess = {"color_identity": ["R"], "commander": "Some Commander"}
    pool = manual_builder_service.get_card_pool(sess)
    matches = pool[pool["name"] == "Blazing Firesinger // Seething Song"]

    assert len(matches) == 1
    assert set(matches.iloc[0]["_tags"]) == {"Aggro", "Ritual"}


def _sample_deck_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"name": "Rampant Growth", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Ramp"], "edhrecRank": 500.0, "isNew": False},
        {"name": "Nature's Lore", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Ramp"], "edhrecRank": 300.0, "isNew": False},
        {"name": "Lightning Bolt", "colorIdentity": "R", "type": "Instant", "manaValue": 1.0,
         "themeTags": ["Removal"], "edhrecRank": 100.0, "isNew": False},
        {"name": "Some Beater", "colorIdentity": "R", "type": "Creature - Giant", "manaValue": 4.0,
         "themeTags": [], "edhrecRank": 600.0, "isNew": False},
        {"name": "Forest", "colorIdentity": "", "type": "Basic Land - Forest", "manaValue": 0.0,
         "themeTags": [], "edhrecRank": 1.0, "isNew": False},
    ])


def _manual_sess(monkeypatch, manual_builder_service, df: pd.DataFrame) -> dict:
    class _FakeLoader:
        def load(self):
            return df

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)
    return {
        "color_identity": ["R", "G"],
        "commander": "Some Commander",
        "deck_cards": [],
    }


def test_add_card_updates_session(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    result = manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    assert result["status"] == "added"
    assert sess["deck_cards"] == ["Rampant Growth"]


def test_remove_card_updates_session(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")

    result = manual_builder_service.remove_card_from_deck(sess, "Rampant Growth")
    assert result["status"] == "removed"
    assert sess["deck_cards"] == []


def test_resolve_color_identity_parses_comma_separated_string(monkeypatch):
    """colorIdentity in commander_cards.csv is stored like \"G, W\" (comma +
    space separated); resolving it must split on comma, not iterate chars.
    """
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    df = pd.DataFrame([{"name": "Some Commander", "colorIdentity": "G, W"}])

    class _FakeBuilder:
        def __init__(self, *a, **k):
            pass

        def load_commander_data(self):
            return df

    monkeypatch.setattr(manual_builder_service, "DeckBuilder", _FakeBuilder)

    result = manual_builder_service.resolve_color_identity("Some Commander")
    assert result == ["G", "W"]


def test_save_manual_deck_writes_full_type_breakdown(monkeypatch, tmp_path):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    sess["deck_cards"] = ["Rampant Growth", "Lightning Bolt", "Forest"]

    manual_builder_service.save_manual_deck(sess, str(tmp_path))

    import json
    summary_path = next(tmp_path.glob("*.summary.json"))
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    tb = payload["summary"]["type_breakdown"]
    assert tb["counts"]["Sorcery"] == 1
    assert tb["counts"]["Instant"] == 1
    assert tb["counts"]["Land"] == 1
    assert "Rampant Growth" in {c["name"] for c in tb["cards"]["Sorcery"]}
    assert payload["summary"]["mana_curve"]["1"] == 1  # Lightning Bolt (mv 1)


def test_duplicate_blocked(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    result = manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    assert result["status"] == "duplicate"
    assert sess["deck_cards"] == ["Rampant Growth"]


def test_land_multiples_allowed(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    manual_builder_service.add_card_to_deck(sess, "Forest")
    result = manual_builder_service.add_card_to_deck(sess, "Forest")
    assert result["status"] == "added"
    assert sess["deck_cards"] == ["Forest", "Forest"]


def test_hover_suggestions_exclude_in_deck(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    manual_builder_service.get_card_pool(sess)  # populate the pool cache like a real request would
    sess["deck_cards"] = ["Nature's Lore"]

    suggestions = manual_builder_service.hover_suggestions(sess, "Rampant Growth")
    names = {s["name"] for s in suggestions}
    assert "Nature's Lore" not in names  # already in the deck
    assert "Rampant Growth" not in names  # excludes itself
    assert all(s["in_pool"] for s in suggestions)


def test_role_bar_counts_correct(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    manual_builder_service.add_card_to_deck(sess, "Nature's Lore")
    manual_builder_service.add_card_to_deck(sess, "Lightning Bolt")

    data = manual_builder_service.role_bar_data(sess)
    ramp_pill = next(p for p in data["pills"] if p["role"] == "Ramp")
    removal_pill = next(p for p in data["pills"] if p["role"] == "Removal")
    assert ramp_pill["actual"] == 2
    assert removal_pill["actual"] == 1


def test_deck_panel_groups_by_type_and_shows_role_labels(monkeypatch):
    """Deck panel groups mirror the finished-deck summary's type order
    (Instant before Sorcery before Land), and each card is tagged with its
    matched theme(s) plus every ideal role its tags satisfy."""
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    sess["tags"] = ["Ramp"]
    manual_builder_service.add_card_to_deck(sess, "Lightning Bolt")
    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    manual_builder_service.add_card_to_deck(sess, "Forest")

    data = manual_builder_service.deck_panel_data(sess)
    role_labels = [g["role"] for g in data["groups"]]
    assert role_labels == ["Instants", "Sorceries", "Lands"]  # not alphabetical, not raw type-line order

    sorcery_group = next(g for g in data["groups"] if g["role"] == "Sorceries")
    rampant_growth = next(c for c in sorcery_group["cards"] if c["name"] == "Rampant Growth")
    assert set(rampant_growth["roles"]) == {"Ramp"}  # matched theme tag AND ideal role collapse to one label here


def test_save_writes_file(monkeypatch, tmp_path):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    manual_builder_service.add_card_to_deck(sess, "Forest")

    csv_name, txt_name, summary_name = manual_builder_service.save_manual_deck(sess, str(tmp_path))

    assert (tmp_path / csv_name).exists()
    assert (tmp_path / txt_name).exists()
    assert (tmp_path / summary_name).exists()

    import json
    summary = json.loads((tmp_path / summary_name).read_text(encoding="utf-8"))
    assert summary["meta"]["source"] == "manual"
    csv_text = (tmp_path / csv_name).read_text(encoding="utf-8")
    assert "Rampant Growth" in csv_text
    assert "Forest" in csv_text


def test_pool_excludes_bracket_banned_and_tags_capped(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    sess["bracket"] = 1

    monkeypatch.setattr(
        manual_builder_service, "banned_category_names",
        lambda bracket: {"game_changers": {"lightning bolt"}},
    )
    monkeypatch.setattr(
        manual_builder_service, "capped_category_names",
        lambda bracket: {"tutors_nonland": {"rampant growth"}},
    )

    result = manual_builder_service.query_pool(sess)
    by_name = {c["name"]: c for c in result["cards"]}
    assert "Lightning Bolt" not in by_name  # fully banned category is hard-filtered
    assert "Tutor" in by_name["Rampant Growth"]["bracket_tags"]  # capped category is badged, not filtered


def test_add_card_blocked_when_bracket_banned(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    monkeypatch.setattr(
        manual_builder_service, "banned_category_names",
        lambda bracket: {"game_changers": {"lightning bolt"}},
    )

    result = manual_builder_service.add_card_to_deck(sess, "Lightning Bolt")
    assert result["status"] == "bracket_banned"
    assert sess["deck_cards"] == []


def test_manual_compliance_report_shapes_pills(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    sess["deck_cards"] = ["Lightning Bolt"]

    fake_report = {
        "overall": "WARN",
        "categories": {
            "game_changers": {"count": 1, "limit": 0, "status": "FAIL", "flagged": ["Lightning Bolt"]},
            "extra_turns": {"count": 0, "limit": 3, "status": "PASS", "flagged": []},
            "mass_land_denial": {"count": 0, "limit": 0, "status": "PASS", "flagged": []},
            "tutors_nonland": {"count": 0, "limit": 3, "status": "PASS", "flagged": []},
            "two_card_combos": {"count": 0, "limit": None, "status": "PASS", "flagged": []},
        },
    }
    monkeypatch.setattr(manual_builder_service, "evaluate_deck", lambda *a, **k: fake_report)

    report = manual_builder_service.manual_compliance_report(sess)
    assert report["bracket_overall"] == "WARN"
    gc_pill = next(p for p in report["bracket_pills"] if p["key"] == "game_changers")
    assert gc_pill["status"] == "red"
    assert "Lightning Bolt" in report["bracket_notes"][0]


def test_load_deck_for_edit_and_save_in_place(monkeypatch, tmp_path):
    import json

    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    csv_path = tmp_path / "test_deck.csv"
    csv_path.write_text(
        "Name,Count\nSome Commander,1\nRampant Growth,1\nForest,5\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "test_deck.summary.json"
    summary_path.write_text(json.dumps({
        "meta": {
            "commander": "Some Commander",
            "color_identity": ["R", "G"],
            "tags": ["Ramp"],
            "bracket": 3,
            "source": "manual",
        },
        "summary": {},
    }), encoding="utf-8")

    sess: dict = {}
    manual_builder_service.load_deck_for_edit(sess, str(csv_path))

    assert sess["mode"] == "manual"
    assert sess["commander"] == "Some Commander"
    assert sess["bracket"] == 3
    assert sess["edit_source_path"] == str(csv_path)
    assert sorted(sess["deck_cards"]) == sorted(["Rampant Growth"] + ["Forest"] * 5)

    _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    csv_name, txt_name, summary_name = manual_builder_service.save_manual_deck(sess, str(tmp_path))

    assert csv_name == "test_deck.csv"  # overwritten in place, not a new dated filename
    updated_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert updated_summary["meta"]["source"] == "manual"
    assert "last_edited" in updated_summary["meta"]
    assert (tmp_path / "test_deck_compliance.json").exists()


def test_pool_hides_added_card_and_restores_on_remove(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    manual_builder_service.add_card_to_deck(sess, "Rampant Growth")
    names = {c["name"] for c in manual_builder_service.query_pool(sess)["cards"]}
    assert "Rampant Growth" not in names

    manual_builder_service.remove_card_from_deck(sess, "Rampant Growth")
    names = {c["name"] for c in manual_builder_service.query_pool(sess)["cards"]}
    assert "Rampant Growth" in names


def test_pool_keeps_basic_lands_and_multicopy_cards_visible(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    manual_builder_service.add_card_to_deck(sess, "Forest")
    names = {c["name"] for c in manual_builder_service.query_pool(sess)["cards"]}
    assert "Forest" in names  # unlimited-copy exception stays visible


def test_add_land_package_splits_basics_and_adds_staples(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())
    sess["ideals"] = {"basic_lands": 10}
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))

    result = manual_builder_service.add_land_package(sess)

    assert result["count"] == len(sess["deck_cards"])
    forests = sess["deck_cards"].count("Forest")
    mountains = sess["deck_cards"].count("Mountain")
    assert forests + mountains == 10
    assert abs(forests - mountains) <= 1
    assert "Reliquary Tower" in sess["deck_cards"]  # always-include staple
    assert "Command Tower" in sess["deck_cards"]  # multi-color staple


def test_categorize_pool_buckets_by_type(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    categories = manual_builder_service.categorize_pool(sess)

    creature_names = {c["name"] for c in categories["creatures"]["cards"]}
    sorcery_names = {c["name"] for c in categories["sorceries"]["cards"]}
    instant_names = {c["name"] for c in categories["instants"]["cards"]}
    land_names = {c["name"] for c in categories["lands"]["cards"]}
    assert creature_names == {"Some Beater"}
    assert sorcery_names == {"Rampant Growth", "Nature's Lore"}
    assert instant_names == {"Lightning Bolt"}
    assert land_names == {"Forest"}
    # "on_brand" is a cross-cutting highlight, so it isn't restricted by type.
    assert categories["on_brand"]["capped"] is True


def test_categorize_pool_role_categories_are_cross_cutting(monkeypatch):
    """Ramp/Removal/etc. categories surface role-tagged cards regardless of
    theme, and independent of (in addition to) their type bucket."""
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))
    sess = _manual_sess(monkeypatch, manual_builder_service, _sample_deck_df())

    categories = manual_builder_service.categorize_pool(sess)

    ramp_names = {c["name"] for c in categories["ramp"]["cards"]}
    removal_names = {c["name"] for c in categories["removal"]["cards"]}
    assert ramp_names == {"Rampant Growth", "Nature's Lore"}
    assert removal_names == {"Lightning Bolt"}
    # Lightning Bolt still shows in its type bucket too (cross-cutting, not exclusive).
    assert "Lightning Bolt" in {c["name"] for c in categories["instants"]["cards"]}


def test_related_synergy_uses_commanders_unselected_themes(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    df = pd.DataFrame([
        {"name": "Direct Match", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Discard Matters"], "edhrecRank": 100.0, "isNew": False},
        {"name": "Other Theme Card", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Exile Matters"], "edhrecRank": 200.0, "isNew": False},
        {"name": "Unrelated Card", "colorIdentity": "G", "type": "Sorcery", "manaValue": 2.0,
         "themeTags": ["Lifegain"], "edhrecRank": 300.0, "isNew": False},
    ])
    sess = _manual_sess(monkeypatch, manual_builder_service, df)
    sess["tags"] = ["Discard Matters"]  # user-selected theme
    monkeypatch.setattr(
        manual_builder_service, "_commander_tags_and_power",
        lambda name: (["Discard Matters", "Exile Matters", "Spellslinger"], 0),
    )

    result = manual_builder_service.query_category(sess, "related_synergy")
    names = {c["name"] for c in result["cards"]}

    assert names == {"Other Theme Card"}  # commander's OTHER (unselected) theme, no direct match


def test_query_category_caps_at_50_cards(monkeypatch):
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))
    rows = [
        {"name": f"Creature {i}", "colorIdentity": "G", "type": "Creature - Bear", "manaValue": 2.0,
         "themeTags": [], "edhrecRank": float(i), "isNew": False}
        for i in range(60)
    ]
    sess = _manual_sess(monkeypatch, manual_builder_service, pd.DataFrame(rows))

    result = manual_builder_service.query_category(sess, "creatures", per_page=20)

    assert result["total"] == 50
    assert result["total_pages"] == 3
    last_page = manual_builder_service.query_category(sess, "creatures", page=3, per_page=20)
    assert len(last_page["cards"]) == 10


def test_tag_badges_highlight_deck_theme_and_role_separately(monkeypatch):
    # Mirrors the "Conspiracy Theorist" case: a card tagged with both a
    # deck-selected theme and a role-defining tag should surface both,
    # not just the role.
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))
    df = pd.DataFrame([
        {"name": "Conspiracy Theorist", "colorIdentity": "U", "type": "Creature - Human Wizard",
         "manaValue": 2.0, "themeTags": ["Discard Matters", "Card Draw"], "edhrecRank": 1000.0, "isNew": False},
    ])
    sess = _manual_sess(monkeypatch, manual_builder_service, df)
    sess["color_identity"] = ["U"]
    sess["tags"] = ["Discard Matters"]

    result = manual_builder_service.query_pool(sess)
    card = result["cards"][0]

    assert card["role"] == "Card Draw"
    badges = {b["name"]: b["kind"] for b in card["tag_badges"]}
    assert badges["Discard Matters"] == "deck_theme"
    assert badges["Card Draw"] == "role"


def test_pool_printing_and_foil_routes(monkeypatch):
    app_module = importlib.import_module("code.web.app")
    build_newflow = importlib.import_module("code.web.routes.build_newflow")
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")
    api_module = importlib.import_module("code.web.routes.api")

    monkeypatch.setattr(build_newflow, "_is_setup_ready", lambda: True)
    monkeypatch.setattr(build_newflow, "_is_setup_stale", lambda: False)
    monkeypatch.setattr(manual_builder_service, "resolve_color_identity", lambda *a, **k: ["R", "G"])
    monkeypatch.setattr(manual_builder_service, "get_card_pool", lambda sess: _empty_pool_df())
    monkeypatch.setattr(build_newflow, "start_ctx_from_session", lambda sess: {})
    monkeypatch.setattr(
        api_module._image_cache, "get_printings",
        lambda name: [{"scryfall_id": "abc123", "set": "znr", "set_name": "Zendikar Rising",
                        "collector_number": "1", "released_at": "2020-01-01", "finishes": ["nonfoil"]}],
    )

    client = TestClient(app_module.app)
    client.get("/build")
    client.post("/build/new", data={"commander": "Inti, Seneschal of the Sun", "bracket": 3, "mode": "manual"})
    sid = client.cookies.get("sid")

    resp = client.get(f"/decks/manual/{sid}/printing-picker", params={"name": "Rampant Growth", "idx": "creatures-0"})
    assert resp.status_code == 200
    assert "printing-picker-grid" in resp.text

    resp = client.post(
        f"/decks/manual/{sid}/printing",
        data={"name": "Rampant Growth", "scryfall_id": "abc123", "idx": "creatures-0"},
    )
    assert resp.status_code == 200
    assert "pool-img-creatures-0" in resp.text
    assert "printing=abc123" in resp.text

    resp = client.post(
        f"/decks/manual/{sid}/foil",
        data={"name": "Rampant Growth", "idx": "creatures-0", "foil": "1"},
    )
    assert resp.status_code == 200
    assert "active" in resp.text


def test_manual_builder_view_renders_pool_card_tile(monkeypatch):
    app_module = importlib.import_module("code.web.app")
    build_newflow = importlib.import_module("code.web.routes.build_newflow")
    manual_builder_service = importlib.import_module("code.web.services.manual_builder_service")

    monkeypatch.setattr(build_newflow, "_is_setup_ready", lambda: True)
    monkeypatch.setattr(build_newflow, "_is_setup_stale", lambda: False)
    monkeypatch.setattr(manual_builder_service, "resolve_color_identity", lambda *a, **k: ["R", "G"])
    monkeypatch.setattr(manual_builder_service, "_commander_tags_and_power", lambda name: ([], 0))
    monkeypatch.setattr(build_newflow, "start_ctx_from_session", lambda sess: {})

    class _FakeLoader:
        def load(self):
            return _sample_deck_df()

    monkeypatch.setattr(manual_builder_service, "AllCardsLoader", _FakeLoader)

    client = TestClient(app_module.app)
    client.get("/build")
    client.post("/build/new", data={"commander": "Inti, Seneschal of the Sun", "bracket": 3, "mode": "manual"})
    sid = client.cookies.get("sid")

    resp = client.get(f"/decks/manual/{sid}")
    assert resp.status_code == 200
    assert 'id="pool-img-' in resp.text
    assert "Choose Printing" in resp.text or "&#128444;" in resp.text

