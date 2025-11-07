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
