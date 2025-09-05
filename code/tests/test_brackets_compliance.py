from __future__ import annotations

from deck_builder.brackets_compliance import evaluate_deck


def _mk_card(tags: list[str] | None = None):
    return {
        "Card Name": "X",
        "Card Type": "Sorcery",
        "Tags": list(tags or []),
        "Count": 1,
    }


def test_exhibition_fails_on_game_changer():
    deck = {
        "Sol Ring": _mk_card(["Bracket:GameChanger"]),
        "Cultivate": _mk_card([]),
    }
    rep = evaluate_deck(deck, commander_name=None, bracket="exhibition")
    assert rep["level"] == 1
    assert rep["categories"]["game_changers"]["status"] == "FAIL"
    assert rep["overall"] == "FAIL"


def test_core_allows_some_extra_turns_but_fails_over_limit():
    deck = {
        f"Time Warp {i}": _mk_card(["Bracket:ExtraTurn"]) for i in range(1, 5)
    }
    rep = evaluate_deck(deck, commander_name=None, bracket="core")
    assert rep["level"] == 2
    assert rep["categories"]["extra_turns"]["limit"] == 3
    assert rep["categories"]["extra_turns"]["count"] == 4
    assert rep["categories"]["extra_turns"]["status"] == "FAIL"
    assert rep["overall"] == "FAIL"


def test_two_card_combination_detection_respects_cheap_early():
    deck = {
        "Thassa's Oracle": _mk_card([]),
        "Demonic Consultation": _mk_card([]),
        "Isochron Scepter": _mk_card([]),
        "Dramatic Reversal": _mk_card([]),
    }
    # Exhibition should fail due to presence of a cheap/early pair
    rep1 = evaluate_deck(deck, commander_name=None, bracket="exhibition")
    assert rep1["categories"]["two_card_combos"]["count"] >= 1
    assert rep1["categories"]["two_card_combos"]["status"] == "FAIL"

    # Optimized has no limit
    rep2 = evaluate_deck(deck, commander_name=None, bracket="optimized")
    assert rep2["categories"]["two_card_combos"]["limit"] is None
    assert rep2["overall"] == "PASS"


def test_warn_thresholds_in_yaml_are_applied():
    # Exhibition: tutors_nonland_warn=1 -> WARN when a single tutor present (hard limit 3)
    deck1 = {
        # Use a non-"Game Changer" tutor to avoid hard fail in Exhibition
        "Solve the Equation": _mk_card(["Bracket:TutorNonland"]),
        "Cultivate": _mk_card([]),
    }
    rep1 = evaluate_deck(deck1, commander_name=None, bracket="exhibition")
    assert rep1["level"] == 1
    assert rep1["categories"]["tutors_nonland"]["status"] == "WARN"
    assert rep1["overall"] == "WARN"

    # Core: extra_turns_warn=1 -> WARN at 1, PASS at 0, FAIL above hard limit 3
    deck2 = {
        "Time Warp": _mk_card(["Bracket:ExtraTurn"]),
        "Explore": _mk_card([]),
    }
    rep2 = evaluate_deck(deck2, commander_name=None, bracket="core")
    assert rep2["level"] == 2
    assert rep2["categories"]["extra_turns"]["limit"] == 3
    assert rep2["categories"]["extra_turns"]["status"] in {"WARN", "PASS"}
    # With two extra turns, still <= limit, but should at least WARN
    deck3 = {
        "Time Warp": _mk_card(["Bracket:ExtraTurn"]),
        "Temporal Manipulation": _mk_card(["Bracket:ExtraTurn"]),
    }
    rep3 = evaluate_deck(deck3, commander_name=None, bracket="core")
    assert rep3["categories"]["extra_turns"]["status"] == "WARN"
