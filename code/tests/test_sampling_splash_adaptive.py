from __future__ import annotations

from code.web.services.sampling import sample_real_cards_for_theme

# We'll construct a minimal in-memory index by monkeypatching card_index structures directly
# to avoid needing real CSV files. This keeps the test fast & deterministic.


def test_adaptive_splash_penalty_scaling(monkeypatch):
    # Prepare index
    theme = "__AdaptiveSplashTest__"
    # Commander (4-color) enabling splash path
    commander_name = "Test Commander"
    commander_tags = [theme, "Value", "ETB"]
    commander_entry = {
        "name": commander_name,
        "color_identity": "WUBR",  # 4 colors
        "tags": commander_tags,
        "mana_cost": "WUBR",
        "rarity": "mythic",
        "color_identity_list": list("WUBR"),
        "pip_colors": list("WUBR"),
    }
    pool = [commander_entry]
    def add_card(name: str, color_identity: str, tags: list[str]):
        pool.append({
            "name": name,
            "color_identity": color_identity,
            "tags": tags,
            "mana_cost": "1G",
            "rarity": "uncommon",
            "color_identity_list": list(color_identity),
            "pip_colors": [c for c in "1G" if c in {"W","U","B","R","G"}],
        })
    # On-color payoff (no splash penalty)
    add_card("On Color Card", "WUB", [theme, "ETB"])
    # Off-color splash (adds G)
    add_card("Splash Card", "WUBG", [theme, "ETB", "Synergy"])

    # Monkeypatch lookup_commander to return our commander
    from code.web.services import card_index as ci
    # Patch underlying card_index (for direct calls elsewhere)
    monkeypatch.setattr(ci, "lookup_commander", lambda name: commander_entry if name == commander_name else None)
    monkeypatch.setattr(ci, "maybe_build_index", lambda: None)
    monkeypatch.setattr(ci, "get_tag_pool", lambda tag: pool if tag == theme else [])
    # Also patch symbols imported into sampling at import time
    import code.web.services.sampling as sampling_mod
    monkeypatch.setattr(sampling_mod, "maybe_build_index", lambda: None)
    monkeypatch.setattr(sampling_mod, "get_tag_pool", lambda tag: pool if tag == theme else [])
    monkeypatch.setattr(sampling_mod, "lookup_commander", lambda name: commander_entry if name == commander_name else None)
    monkeypatch.setattr(sampling_mod, "SPLASH_ADAPTIVE_ENABLED", True)
    monkeypatch.setenv("SPLASH_ADAPTIVE", "1")
    monkeypatch.setenv("SPLASH_ADAPTIVE_SCALE", "1:1.0,2:1.0,3:1.0,4:0.5,5:0.25")

    # Invoke sampler (limit large enough to include both cards)
    cards = sample_real_cards_for_theme(theme, 10, None, synergies=[theme, "ETB", "Synergy"], commander=commander_name)
    by_name = {c["name"]: c for c in cards}
    assert "Splash Card" in by_name, cards
    splash_reasons = [r for r in by_name["Splash Card"]["reasons"] if r.startswith("splash_off_color_penalty")]
    assert splash_reasons, by_name["Splash Card"]["reasons"]
    # Adaptive variant reason format: splash_off_color_penalty_adaptive:<color_count>:<value>
    adaptive_reason = next(r for r in splash_reasons if r.startswith("splash_off_color_penalty_adaptive"))
    parts = adaptive_reason.split(":")
    assert parts[1] == "4"  # commander color count
    penalty_value = float(parts[2])
    # With base -0.3 and scale 0.5 expect -0.15 (+/- float rounding)
    assert abs(penalty_value - (-0.3 * 0.5)) < 1e-6
