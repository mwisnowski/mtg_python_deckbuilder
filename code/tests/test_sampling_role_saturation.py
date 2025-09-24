from code.web.services import sampling


def test_role_saturation_penalty_applies(monkeypatch):
    # Construct a minimal fake pool via monkeypatching card_index.get_tag_pool
    # We'll generate many payoff-tagged cards to trigger saturation.
    cards = []
    for i in range(30):
        cards.append({
            "name": f"Payoff{i}",
            "color_identity": "G",
            "tags": ["testtheme"],  # ensures payoff
            "mana_cost": "1G",
            "rarity": "common",
            "color_identity_list": ["G"],
            "pip_colors": ["G"],
        })

    def fake_pool(tag: str):
        assert tag == "testtheme"
        return cards

    # Patch symbols where they are used (imported into sampling module)
    monkeypatch.setattr("code.web.services.sampling.get_tag_pool", lambda tag: fake_pool(tag))
    monkeypatch.setattr("code.web.services.sampling.maybe_build_index", lambda: None)
    monkeypatch.setattr("code.web.services.sampling.lookup_commander", lambda name: None)

    chosen = sampling.sample_real_cards_for_theme(
        theme="testtheme",
        limit=12,
        colors_filter=None,
        synergies=["testtheme"],
        commander=None,
    )
    # Ensure we have more than half flagged as payoff in initial classification
    payoff_scores = [c["score"] for c in chosen if c["roles"][0] == "payoff"]
    assert payoff_scores, "Expected payoff cards present"
    # Saturation penalty should have been applied to at least one (score reduced by 0.4 increments) once cap exceeded.
    # We detect presence by existence of reason substring.
    penalized = [c for c in chosen if any(r.startswith("role_saturation_penalty") for r in c.get("reasons", []))]
    assert penalized, "Expected at least one card to receive role_saturation_penalty"
