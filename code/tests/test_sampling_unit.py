import os
from code.web.services import sampling
from code.web.services import card_index


def setup_module(module):  # ensure deterministic env weights
    os.environ.setdefault("RARITY_W_MYTHIC", "1.2")


def test_rarity_diminishing():
    # Monkeypatch internal index
    card_index._CARD_INDEX.clear()
    theme = "Test Theme"
    card_index._CARD_INDEX[theme] = [
        {"name": "Mythic One", "tags": [theme], "color_identity": "G", "mana_cost": "G", "rarity": "mythic"},
        {"name": "Mythic Two", "tags": [theme], "color_identity": "G", "mana_cost": "G", "rarity": "mythic"},
    ]
    def no_build():
        return None
    sampling.maybe_build_index = no_build
    cards = sampling.sample_real_cards_for_theme(theme, 2, None, synergies=[theme], commander=None)
    rarity_weights = [r for c in cards for r in c["reasons"] if r.startswith("rarity_weight_calibrated")]
    assert len(rarity_weights) >= 2
    v1 = float(rarity_weights[0].split(":")[-1])
    v2 = float(rarity_weights[1].split(":")[-1])
    assert v1 > v2  # diminishing returns


def test_commander_overlap_monotonic_diminishing():
    cmd_tags = {"A","B","C","D"}
    synergy_set = {"A","B","C","D","E"}
    # Build artificial card tag lists with increasing overlaps
    bonus1 = sampling.commander_overlap_scale(cmd_tags, ["A"], synergy_set)
    bonus2 = sampling.commander_overlap_scale(cmd_tags, ["A","B"], synergy_set)
    bonus3 = sampling.commander_overlap_scale(cmd_tags, ["A","B","C"], synergy_set)
    assert 0 < bonus1 < bonus2 < bonus3
    # Diminishing increments: delta shrinks
    assert (bonus2 - bonus1) > 0
    assert (bonus3 - bonus2) < (bonus2 - bonus1)


def test_splash_off_color_penalty_applied():
    card_index._CARD_INDEX.clear()
    theme = "Splash Theme"
    # Commander W U B R (4 colors)
    commander = {"name": "CommanderTest", "tags": [theme], "color_identity": "WUBR", "mana_cost": "", "rarity": "mythic"}
    # Card with single off-color G (W U B R G)
    splash_card = {"name": "CardSplash", "tags": [theme], "color_identity": "WUBRG", "mana_cost": "G", "rarity": "rare"}
    card_index._CARD_INDEX[theme] = [commander, splash_card]
    sampling.maybe_build_index = lambda: None
    cards = sampling.sample_real_cards_for_theme(theme, 2, None, synergies=[theme], commander="CommanderTest")
    splash = next((c for c in cards if c["name"] == "CardSplash"), None)
    assert splash is not None
    assert any(r.startswith("splash_off_color_penalty") for r in splash["reasons"])


def test_role_saturation_penalty_applies(monkeypatch):
    cards = []
    for i in range(30):
        cards.append({"name": f"Payoff{i}", "color_identity": "G", "tags": ["testtheme"], "mana_cost": "1G", "rarity": "common", "color_identity_list": ["G"], "pip_colors": ["G"]})
    monkeypatch.setattr("code.web.services.sampling.get_tag_pool", lambda tag: cards)
    monkeypatch.setattr("code.web.services.sampling.maybe_build_index", lambda: None)
    monkeypatch.setattr("code.web.services.sampling.lookup_commander", lambda name: None)
    chosen = sampling.sample_real_cards_for_theme(theme="testtheme", limit=12, colors_filter=None, synergies=["testtheme"], commander=None)
    penalized = [c for c in chosen if any(r.startswith("role_saturation_penalty") for r in c.get("reasons", []))]
    assert penalized, "Expected at least one card to receive role_saturation_penalty"


def test_adaptive_splash_penalty_scaling(monkeypatch):
    theme = "__AdaptiveSplashTest__"
    commander_name = "Test Commander"
    commander_tags = [theme, "Value", "ETB"]
    commander_entry = {
        "name": commander_name,
        "color_identity": "WUBR",
        "tags": commander_tags,
        "mana_cost": "WUBR",
        "rarity": "mythic",
        "color_identity_list": list("WUBR"),
        "pip_colors": list("WUBR"),
    }
    pool = [commander_entry]

    def add_card(name: str, color_identity: str, tags: list):
        pool.append({
            "name": name,
            "color_identity": color_identity,
            "tags": tags,
            "mana_cost": "1G",
            "rarity": "uncommon",
            "color_identity_list": list(color_identity),
            "pip_colors": [c for c in "1G" if c in {"W", "U", "B", "R", "G"}],
        })

    add_card("On Color Card", "WUB", [theme, "ETB"])
    add_card("Splash Card", "WUBG", [theme, "ETB", "Synergy"])

    from code.web.services import card_index as ci
    monkeypatch.setattr(ci, "lookup_commander", lambda name: commander_entry if name == commander_name else None)
    monkeypatch.setattr(ci, "maybe_build_index", lambda: None)
    monkeypatch.setattr(ci, "get_tag_pool", lambda tag: pool if tag == theme else [])
    monkeypatch.setattr(sampling, "maybe_build_index", lambda: None)
    monkeypatch.setattr(sampling, "get_tag_pool", lambda tag: pool if tag == theme else [])
    monkeypatch.setattr(sampling, "lookup_commander", lambda name: commander_entry if name == commander_name else None)
    monkeypatch.setattr(sampling, "SPLASH_ADAPTIVE_ENABLED", True)
    monkeypatch.setenv("SPLASH_ADAPTIVE", "1")
    monkeypatch.setenv("SPLASH_ADAPTIVE_SCALE", "1:1.0,2:1.0,3:1.0,4:0.5,5:0.25")

    cards = sampling.sample_real_cards_for_theme(theme, 10, None, synergies=[theme, "ETB", "Synergy"], commander=commander_name)
    by_name = {c["name"]: c for c in cards}
    assert "Splash Card" in by_name, cards
    splash_reasons = [r for r in by_name["Splash Card"]["reasons"] if r.startswith("splash_off_color_penalty")]
    assert splash_reasons, by_name["Splash Card"]["reasons"]
    adaptive_reason = next(r for r in splash_reasons if r.startswith("splash_off_color_penalty_adaptive"))
    parts = adaptive_reason.split(":")
    assert parts[1] == "4"
    penalty_value = float(parts[2])
    assert abs(penalty_value - (-0.3 * 0.5)) < 1e-6
