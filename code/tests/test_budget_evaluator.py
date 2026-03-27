"""Tests for BudgetEvaluatorService - deck cost evaluation and alternatives."""
from __future__ import annotations

from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from code.web.services.budget_evaluator import BudgetEvaluatorService
from code.web.services.price_service import PriceService


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_price_service(prices: Dict[str, Optional[float]]) -> PriceService:
    """Return a PriceService stub that returns predefined prices."""
    svc = MagicMock(spec=PriceService)
    svc.get_price.side_effect = lambda name, region="usd", foil=False: prices.get(name)
    svc.get_prices_batch.side_effect = lambda names, region="usd", foil=False: {
        n: prices.get(n) for n in names
    }
    return svc


# Shared price table: {card_name: price}
KNOWN_PRICES: Dict[str, Optional[float]] = {
    "Sol Ring": 2.00,
    "Mana Crypt": 150.00,
    "Lightning Bolt": 0.25,
    "Arcane Signet": 1.50,
    "Fellwar Stone": 1.00,
    "Command Tower": 0.30,
    "Swamp": 0.10,
    "Island": 0.10,
    "Craterhoof Behemoth": 30.00,
    "Vampiric Tutor": 25.00,
    "No Price Card": None,
}


@pytest.fixture
def price_svc():
    return _make_price_service(KNOWN_PRICES)


@pytest.fixture
def evaluator(price_svc):
    return BudgetEvaluatorService(price_service=price_svc)


# ---------------------------------------------------------------------------
# Tests: evaluate_deck — basic cases
# ---------------------------------------------------------------------------

def test_evaluate_under_budget(evaluator):
    deck = ["Sol Ring", "Arcane Signet", "Command Tower"]
    # 2.00 + 1.50 + 0.30 = 3.80 < 10.00
    report = evaluator.evaluate_deck(deck, budget_total=10.0)
    assert report["budget_status"] == "under"
    assert report["total_price"] == pytest.approx(3.80)
    assert report["overage"] == 0.0


def test_evaluate_soft_exceeded(evaluator):
    deck = ["Sol Ring", "Mana Crypt", "Lightning Bolt"]
    # 2.00 + 150.00 + 0.25 = 152.25 > 100.00
    report = evaluator.evaluate_deck(deck, budget_total=100.0, mode="soft")
    assert report["budget_status"] == "soft_exceeded"
    assert report["overage"] == pytest.approx(52.25)


def test_evaluate_hard_exceeded(evaluator):
    deck = ["Sol Ring", "Mana Crypt"]
    report = evaluator.evaluate_deck(deck, budget_total=50.0, mode="hard")
    assert report["budget_status"] == "hard_exceeded"


def test_evaluate_empty_deck(evaluator):
    report = evaluator.evaluate_deck([], budget_total=100.0)
    assert report["total_price"] == 0.0
    assert report["budget_status"] == "under"
    assert report["overage"] == 0.0


# ---------------------------------------------------------------------------
# Tests: card_ceiling enforcement
# ---------------------------------------------------------------------------

def test_card_ceiling_flags_expensive_card(evaluator):
    deck = ["Sol Ring", "Mana Crypt", "Command Tower"]
    report = evaluator.evaluate_deck(deck, budget_total=500.0, card_ceiling=10.0)
    flagged = [e["card"] for e in report["over_budget_cards"]]
    assert "Mana Crypt" in flagged
    assert "Sol Ring" not in flagged
    assert "Command Tower" not in flagged


def test_card_ceiling_not_triggered_under_cap(evaluator):
    deck = ["Sol Ring", "Arcane Signet"]
    report = evaluator.evaluate_deck(deck, budget_total=500.0, card_ceiling=5.0)
    assert report["over_budget_cards"] == []


# ---------------------------------------------------------------------------
# Tests: include_cards are exempt from over_budget flagging
# ---------------------------------------------------------------------------

def test_include_cards_exempt_from_ceiling(evaluator):
    deck = ["Mana Crypt", "Sol Ring"]
    # Mana Crypt (150) is an include — should NOT appear in over_budget_cards
    report = evaluator.evaluate_deck(
        deck, budget_total=10.0, card_ceiling=10.0, include_cards=["Mana Crypt"]
    )
    flagged = [e["card"] for e in report["over_budget_cards"]]
    assert "Mana Crypt" not in flagged


def test_include_budget_overage_reported(evaluator):
    deck = ["Craterhoof Behemoth", "Lightning Bolt"]
    report = evaluator.evaluate_deck(
        deck, budget_total=50.0, include_cards=["Craterhoof Behemoth"]
    )
    assert report["include_budget_overage"] == pytest.approx(30.00)


def test_include_cards_counted_in_total_price(evaluator):
    deck = ["Mana Crypt", "Sol Ring"]
    report = evaluator.evaluate_deck(deck, budget_total=200.0, include_cards=["Mana Crypt"])
    assert report["total_price"] == pytest.approx(152.00)


# ---------------------------------------------------------------------------
# Tests: missing price handling (legacy_fail_open)
# ---------------------------------------------------------------------------

def test_missing_price_fail_open_skips(evaluator):
    deck = ["Sol Ring", "No Price Card"]
    # No Price Card has no price → treated as 0 in calculation
    report = evaluator.evaluate_deck(deck, budget_total=100.0, legacy_fail_open=True)
    assert "No Price Card" in report["stale_prices"]
    assert report["total_price"] == pytest.approx(2.00)


def test_missing_price_fail_closed_raises(evaluator):
    deck = ["No Price Card"]
    with pytest.raises(ValueError, match="No price data for"):
        evaluator.evaluate_deck(deck, budget_total=100.0, legacy_fail_open=False)


# ---------------------------------------------------------------------------
# Tests: price_breakdown structure
# ---------------------------------------------------------------------------

def test_price_breakdown_contains_all_cards(evaluator):
    deck = ["Sol Ring", "Lightning Bolt", "Swamp"]
    report = evaluator.evaluate_deck(deck, budget_total=100.0)
    names_in_breakdown = [e["card"] for e in report["price_breakdown"]]
    for card in deck:
        assert card in names_in_breakdown


def test_price_breakdown_flags_include(evaluator):
    deck = ["Mana Crypt", "Sol Ring"]
    report = evaluator.evaluate_deck(deck, budget_total=200.0, include_cards=["Mana Crypt"])
    mc_entry = next(e for e in report["price_breakdown"] if e["card"] == "Mana Crypt")
    assert mc_entry["is_include"] is True
    sr_entry = next(e for e in report["price_breakdown"] if e["card"] == "Sol Ring")
    assert sr_entry["is_include"] is False


# ---------------------------------------------------------------------------
# Tests: find_cheaper_alternatives
# ---------------------------------------------------------------------------

def test_cheaper_alternatives_respects_max_price():
    """Alternatives returned must all be ≤ max_price."""
    # Build a card index stub with two alternatives
    candidate_index = {
        "ramp": [
            {"name": "Arcane Signet", "tags": ["ramp"], "color_identity": "", "color_identity_list": [], "mana_cost": "", "rarity": ""},
            {"name": "Cursed Mirror", "tags": ["ramp"], "color_identity": "", "color_identity_list": [], "mana_cost": "", "rarity": ""},
        ]
    }
    prices = {"Arcane Signet": 1.50, "Cursed Mirror": 8.00}

    svc = _make_price_service(prices)
    evaluator = BudgetEvaluatorService(price_service=svc)

    with patch("code.web.services.card_index.get_tag_pool") as mock_pool, \
         patch("code.web.services.card_index.maybe_build_index"):
        mock_pool.side_effect = lambda tag: candidate_index.get(tag, [])
        results = evaluator.find_cheaper_alternatives("Mana Crypt", max_price=5.0, tags=["ramp"])

    # Only Arcane Signet (1.50) should qualify; Cursed Mirror (8.00) exceeds max_price
    names = [r["name"] for r in results]
    assert "Arcane Signet" in names
    assert "Cursed Mirror" not in names


def test_cheaper_alternatives_sorted_by_price():
    """Alternatives should be sorted cheapest first."""
    candidates = [
        {"name": "Card A", "tags": ["ramp"], "color_identity": "", "color_identity_list": [], "mana_cost": "", "rarity": ""},
        {"name": "Card B", "tags": ["ramp"], "color_identity": "", "color_identity_list": [], "mana_cost": "", "rarity": ""},
        {"name": "Card C", "tags": ["ramp"], "color_identity": "", "color_identity_list": [], "mana_cost": "", "rarity": ""},
    ]
    prices = {"Card A": 3.00, "Card B": 1.00, "Card C": 2.00}
    svc = _make_price_service(prices)
    evaluator = BudgetEvaluatorService(price_service=svc)

    with patch("code.web.services.card_index.get_tag_pool") as mock_pool, \
         patch("code.web.services.card_index.maybe_build_index"):
        mock_pool.return_value = candidates
        results = evaluator.find_cheaper_alternatives("Mana Crypt", max_price=10.0, tags=["ramp"])

    assert [r["name"] for r in results] == ["Card B", "Card C", "Card A"]


def test_cheaper_alternatives_empty_when_no_tags():
    evaluator = BudgetEvaluatorService(price_service=_make_price_service({}))
    with patch("code.web.services.card_index.maybe_build_index"), \
         patch("code.web.services.card_index._CARD_INDEX", {}):
        results = evaluator.find_cheaper_alternatives("Unknown Card", max_price=10.0)
    assert results == []


def test_cheaper_alternatives_color_identity_filter():
    """Cards outside the commander's color identity must be excluded."""
    candidates = [
        # This card requires White (W) — not in Dimir (U/B)
        {"name": "Swords to Plowshares", "tags": ["removal"], "color_identity": "W", "color_identity_list": ["W"], "mana_cost": "{W}", "rarity": "", "type_line": "Instant"},
        {"name": "Doom Blade", "tags": ["removal"], "color_identity": "B", "color_identity_list": ["B"], "mana_cost": "{1}{B}", "rarity": "", "type_line": "Instant"},
    ]
    prices = {"Swords to Plowshares": 1.00, "Doom Blade": 0.50}
    svc = _make_price_service(prices)
    evaluator = BudgetEvaluatorService(price_service=svc)

    with patch("code.web.services.card_index.get_tag_pool") as mock_pool, \
         patch("code.web.services.card_index.maybe_build_index"):
        mock_pool.return_value = candidates
        results = evaluator.find_cheaper_alternatives(
            "Vampiric Tutor", max_price=5.0,
            color_identity=["U", "B"], tags=["removal"]
        )

    names = [r["name"] for r in results]
    assert "Swords to Plowshares" not in names
    assert "Doom Blade" in names


# ---------------------------------------------------------------------------
# Tests: calculate_tier_ceilings
# ---------------------------------------------------------------------------

def test_tier_ceilings_correct_fractions(evaluator):
    ceilings = evaluator.calculate_tier_ceilings(100.0)
    assert ceilings["S"] == pytest.approx(20.0)
    assert ceilings["M"] == pytest.approx(10.0)
    assert ceilings["L"] == pytest.approx(5.0)


def test_tier_ceilings_zero_budget(evaluator):
    ceilings = evaluator.calculate_tier_ceilings(0.0)
    assert all(v == 0.0 for v in ceilings.values())


# ---------------------------------------------------------------------------
# Tests: validation guards
# ---------------------------------------------------------------------------

def test_negative_budget_raises(evaluator):
    with pytest.raises(Exception):
        evaluator.evaluate_deck(["Sol Ring"], budget_total=-1.0)


def test_invalid_mode_raises(evaluator):
    with pytest.raises(Exception):
        evaluator.evaluate_deck(["Sol Ring"], budget_total=100.0, mode="turbo")


def test_negative_ceiling_raises(evaluator):
    with pytest.raises(Exception):
        evaluator.evaluate_deck(["Sol Ring"], budget_total=100.0, card_ceiling=-5.0)


# ---------------------------------------------------------------------------
# Tests: BudgetHardCapExceeded exception
# ---------------------------------------------------------------------------

def test_budget_hard_cap_exception_attributes():
    from code.exceptions import BudgetHardCapExceeded
    exc = BudgetHardCapExceeded(
        total_price=200.0,
        budget_total=150.0,
        over_budget_cards=[{"card": "Mana Crypt", "price": 150.0}],
    )
    assert exc.overage == pytest.approx(50.0)
    assert exc.total_price == 200.0
    assert exc.budget_total == 150.0
    assert len(exc.over_budget_cards) == 1
    assert "BUDGET_HARD_CAP" in exc.code


# ---------------------------------------------------------------------------
# M8: Price chart helpers
# ---------------------------------------------------------------------------

from code.web.services.budget_evaluator import (
    compute_price_category_breakdown,
    compute_price_histogram,
    CATEGORY_ORDER,
)


def test_category_breakdown_basic():
    items = [
        {"card": "Sol Ring",     "price": 2.00,  "tags": ["ramp", "mana rock"]},
        {"card": "Arcane Signet","price": 1.50,  "tags": ["ramp", "mana rock"]},
        {"card": "Swords to Plowshares", "price": 3.00, "tags": ["spot removal", "removal"]},
        {"card": "Forest",       "price": 0.25,  "tags": ["land"]},
    ]
    result = compute_price_category_breakdown(items)
    assert result["totals"]["Ramp"] == pytest.approx(3.50)
    assert result["totals"]["Removal"] == pytest.approx(3.00)
    assert result["totals"]["Land"] == pytest.approx(0.25)
    assert result["total"] == pytest.approx(6.75)
    assert result["order"] == CATEGORY_ORDER


def test_category_breakdown_unmatched_goes_to_other():
    items = [{"card": "Thassa's Oracle", "price": 10.00, "tags": ["combo", "wincon"]}]
    result = compute_price_category_breakdown(items)
    assert result["totals"]["Synergy"] == pytest.approx(10.00)
    # Specifically "combo" hits Synergy, not Other


def test_category_breakdown_no_price_skipped():
    items = [
        {"card": "Card A", "price": None, "tags": ["ramp"]},
        {"card": "Card B", "price": 5.00,  "tags": []},
    ]
    result = compute_price_category_breakdown(items)
    assert result["total"] == pytest.approx(5.00)
    assert result["totals"]["Other"] == pytest.approx(5.00)


def test_histogram_10_bins():
    items = [{"card": f"Card {i}", "price": float(i)} for i in range(1, 21)]
    bins = compute_price_histogram(items)
    assert len(bins) == 10
    assert all("label" in b and "count" in b and "pct" in b and "color" in b for b in bins)
    assert sum(b["count"] for b in bins) == 20


def test_histogram_all_same_price():
    items = [{"card": f"Card {i}", "price": 1.00} for i in range(5)]
    bins = compute_price_histogram(items)
    assert len(bins) == 10
    assert bins[0]["count"] == 5
    assert all(b["count"] == 0 for b in bins[1:])


def test_histogram_fewer_than_2_returns_empty():
    assert compute_price_histogram([]) == []
    assert compute_price_histogram([{"card": "Solo", "price": 5.0}]) == []


def test_histogram_excludes_unpriced_cards():
    items = [
        {"card": "A", "price": 1.0},
        {"card": "B", "price": None},
        {"card": "C", "price": 3.0},
        {"card": "D", "price": 5.0},
    ]
    bins = compute_price_histogram(items)
    assert sum(b["count"] for b in bins) == 3  # B excluded

