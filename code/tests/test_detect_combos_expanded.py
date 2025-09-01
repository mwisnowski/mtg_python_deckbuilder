from __future__ import annotations

from deck_builder.combos import detect_combos


def test_detect_expanded_pairs():
    names = [
        "Isochron Scepter",
        "Dramatic Reversal",
        "Basalt Monolith",
        "Rings of Brighthearth",
        "Some Other Card",
    ]
    combos = detect_combos(names, combos_path="config/card_lists/combos.json")
    found = {(c.a, c.b) for c in combos}
    assert ("Isochron Scepter", "Dramatic Reversal") in found
    assert ("Basalt Monolith", "Rings of Brighthearth") in found
