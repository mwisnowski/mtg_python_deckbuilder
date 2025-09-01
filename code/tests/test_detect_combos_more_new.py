from __future__ import annotations

from deck_builder.combos import detect_combos


def test_detect_more_new_pairs():
    names = [
        "Godo, Bandit Warlord",
        "Helm of the Host",
        "Narset, Parter of Veils",
        "Windfall",
        "Grand Architect",
        "Pili-Pala",
    ]
    combos = detect_combos(names, combos_path="config/card_lists/combos.json")
    pairs = {(c.a, c.b) for c in combos}
    assert ("Godo, Bandit Warlord", "Helm of the Host") in pairs
    assert ("Narset, Parter of Veils", "Windfall") in pairs
    assert ("Grand Architect", "Pili-Pala") in pairs
