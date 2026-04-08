"""Tests for UpgradeSuggestionsService — M1 & M2."""
from __future__ import annotations

import datetime
import json
from unittest.mock import patch

import pandas as pd
import pytest

from code.web.services.upgrade_suggestions_service import (
    DeckCard,
    SwapCandidate,
    UpgradeCandidate,
    UpgradeSuggestionsService,
)

TODAY = datetime.date(2026, 4, 6)
_MODULE = "code.web.services.upgrade_suggestions_service"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_bulk(tmp_path, cards: list[dict]) -> str:
    """Write a minimal scryfall-style bulk JSON and return its path."""
    lines = ["["]
    for c in cards:
        lines.append(f"  {json.dumps(c)},")
    lines.append("]")
    p = tmp_path / "scryfall_bulk_data.json"
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def _write_parquet(tmp_path, rows: list[dict]) -> str:
    """Write a minimal parquet file and return its path."""
    df = pd.DataFrame(rows)
    p = tmp_path / "all_cards.parquet"
    df.to_parquet(str(p))
    return str(p)


def _expansion(name, set_code, set_name, released_at) -> dict:
    return {
        "name": name,
        "set": set_code,
        "set_name": set_name,
        "released_at": released_at,
        "set_type": "expansion",
        "reprint": False,
    }


def _card_row(name, color_identity, mana_value, theme_tags, printings, is_new=True, edhrec=100.0) -> dict:
    return {
        "name": name,
        "faceName": None,
        "colorIdentity": color_identity,
        "manaValue": mana_value,
        "themeTags": theme_tags,
        "printings": printings,
        "isNew": is_new,
        "edhrecRank": edhrec,
    }


# ---------------------------------------------------------------------------
# resolve_new_card_window
# ---------------------------------------------------------------------------

def test_resolve_window_excludes_future_sets(tmp_path):
    bulk = _write_bulk(tmp_path, [
        _expansion("Card A", "AAA", "Set A", "2026-03-01"),
        _expansion("Card B", "BBB", "Set B", "2026-12-01"),  # future
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    codes, cutoff, label = svc.resolve_new_card_window(today=TODAY)
    assert "BBB" not in codes
    assert "AAA" in codes


def test_resolve_window_returns_last_3_expansion_dates(tmp_path):
    bulk = _write_bulk(tmp_path, [
        _expansion("Card A", "AAA", "Set A", "2026-03-01"),
        _expansion("Card B", "BBB", "Set B", "2026-01-01"),
        _expansion("Card C", "CCC", "Set C", "2025-11-01"),
        _expansion("Card D", "DDD", "Set D", "2025-09-01"),  # 4th — excluded
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    codes, cutoff, label = svc.resolve_new_card_window(today=TODAY)
    assert "AAA" in codes
    assert "BBB" in codes
    assert "CCC" in codes
    assert "DDD" not in codes
    assert len(codes) == 3


def test_resolve_window_rolling_cutoff_uses_window_months(tmp_path):
    bulk = _write_bulk(tmp_path, [])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk, window_months=6)
    _, cutoff, _ = svc.resolve_new_card_window(today=TODAY)
    expected = TODAY - datetime.timedelta(days=6 * 30)
    assert cutoff == expected


def test_resolve_window_label_contains_set_codes(tmp_path):
    bulk = _write_bulk(tmp_path, [
        _expansion("Card A", "AAA", "Set A", "2026-03-01"),
        _expansion("Card B", "BBB", "Set B", "2026-01-01"),
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    codes, _, label = svc.resolve_new_card_window(today=TODAY)
    for sc in codes:
        assert sc in label


def test_resolve_window_empty_bulk_returns_rolling_label(tmp_path):
    bulk = _write_bulk(tmp_path, [])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk, window_months=3)
    codes, _, label = svc.resolve_new_card_window(today=TODAY)
    assert codes == []
    assert "Rolling" in label


# ---------------------------------------------------------------------------
# get_new_card_pool
# ---------------------------------------------------------------------------

@pytest.fixture
def pool_svc(tmp_path):
    """Service pre-populated with bulk meta + test parquet."""
    bulk = _write_bulk(tmp_path, [
        _expansion("New Red Card", "AAA", "Set A", "2026-03-01"),
        _expansion("New Green Card", "AAA", "Set A", "2026-03-01"),
        _expansion("New Colorless Card", "AAA", "Set A", "2026-03-01"),
    ])
    parquet = _write_parquet(tmp_path, [
        _card_row("New Red Card",      "R",  3.0, "Burn, Damage", "AAA", edhrec=100.0),
        _card_row("New Green Card",    "G",  2.0, "Ramp",         "AAA", edhrec=50.0),
        _card_row("New Colorless Card","",   1.0, "",             "AAA", edhrec=200.0),
        _card_row("Old Card",          "R",  2.0, "Burn",         "OLD", is_new=False, edhrec=10.0),
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet):
        yield svc


def test_get_new_card_pool_excludes_old_cards(pool_svc):
    results = pool_svc.get_new_card_pool(["R", "G"], today=TODAY)
    names = [c.name for c in results]
    assert "Old Card" not in names


def test_get_new_card_pool_color_filter_excludes_off_color(pool_svc):
    results = pool_svc.get_new_card_pool(["G"], today=TODAY)
    names = [c.name for c in results]
    assert "New Green Card" in names
    assert "New Red Card" not in names


def test_get_new_card_pool_colorless_always_included(pool_svc):
    results = pool_svc.get_new_card_pool(["G"], today=TODAY)
    names = [c.name for c in results]
    assert "New Colorless Card" in names


def test_get_new_card_pool_returns_upgrade_candidates(pool_svc):
    results = pool_svc.get_new_card_pool(["R", "G"], today=TODAY)
    assert len(results) >= 1
    for c in results:
        assert isinstance(c, UpgradeCandidate)
        assert c.is_new_card is True
        assert c.set_code == "AAA"
        assert c.set_name == "Set A"
        assert c.released_at == "2026-03-01"


def test_get_new_card_pool_roles_and_cmc_populated(pool_svc):
    results = pool_svc.get_new_card_pool(["R"], today=TODAY)
    red = next(c for c in results if c.name == "New Red Card")
    assert "Burn" in red.roles
    assert "Damage" in red.roles
    assert red.cmc == 3.0


def test_get_new_card_pool_missing_parquet_returns_empty(tmp_path):
    bulk = _write_bulk(tmp_path, [])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    with patch(f"{_MODULE}.get_processed_cards_path", return_value="/nonexistent/all_cards.parquet"):
        results = svc.get_new_card_pool(["R"], today=TODAY)
    assert results == []


def test_get_new_card_pool_future_set_metadata_excluded(tmp_path):
    """Cards whose set_meta released_at is in the future are skipped."""
    bulk = _write_bulk(tmp_path, [
        _expansion("Future Card", "FUT", "Future Set", "2026-12-01"),
    ])
    parquet = _write_parquet(tmp_path, [
        _card_row("Future Card", "R", 2.0, "", "FUT", is_new=True),
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet):
        results = svc.get_new_card_pool(["R"], today=TODAY)
    assert results == []


@pytest.fixture
def themed_pool_svc(tmp_path):
    """Service with cards that have distinct themes, for testing theme filtering."""
    bulk = _write_bulk(tmp_path, [
        _expansion("Theme Card", "AAA", "Set A", "2026-03-01"),
    ])
    parquet = _write_parquet(tmp_path, [
        _card_row("Exile Card",  "W", 2.0, "Exile Matters", "AAA", edhrec=10.0),
        _card_row("Ramp Card",   "G", 2.0, "Ramp",          "AAA", edhrec=20.0),
        _card_row("Off-Theme",   "W", 3.0, "Voltron",       "AAA", edhrec=30.0),
        _card_row("No-Tag Card", "W", 1.0, "",              "AAA", edhrec=40.0),
    ])
    svc = UpgradeSuggestionsService(bulk_data_path=bulk)
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet):
        yield svc


def test_get_new_card_pool_theme_filter_includes_deck_theme(themed_pool_svc):
    """Card matching a deck theme is included."""
    results = themed_pool_svc.get_new_card_pool(["W", "G"], deck_themes=["Exile Matters"], today=TODAY)
    names = [c.name for c in results]
    assert "Exile Card" in names


def test_get_new_card_pool_theme_filter_includes_default_ideal_role(themed_pool_svc):
    """Card matching a default ideal role (Ramp) is included even if not in deck_themes."""
    results = themed_pool_svc.get_new_card_pool(["W", "G"], deck_themes=["Exile Matters"], today=TODAY)
    names = [c.name for c in results]
    assert "Ramp Card" in names


def test_get_new_card_pool_theme_filter_excludes_off_theme(themed_pool_svc):
    """Cards with tags unrelated to deck themes and ideal roles are excluded."""
    results = themed_pool_svc.get_new_card_pool(["W", "G"], deck_themes=["Exile Matters"], today=TODAY)
    names = [c.name for c in results]
    assert "Off-Theme" not in names
    assert "No-Tag Card" not in names


def test_get_new_card_pool_no_filter_when_deck_themes_none(themed_pool_svc):
    """deck_themes=None (default) disables theme filtering — all color-matching cards returned."""
    results = themed_pool_svc.get_new_card_pool(["W", "G"], today=TODAY)
    assert len(results) == 4


# ---------------------------------------------------------------------------
# M2: score_swap_candidates
# ---------------------------------------------------------------------------

def _svc_plain(tmp_path) -> UpgradeSuggestionsService:
    bulk = _write_bulk(tmp_path, [])
    return UpgradeSuggestionsService(bulk_data_path=bulk)


def _suggestion(roles: list[str], cmc: float = 3.0) -> UpgradeCandidate:
    return UpgradeCandidate(
        name="New Ramp Spell", roles=roles, cmc=cmc,
        set_code="AAA", set_name="Set A", released_at="2026-03-01",
    )


def _deck_card(name: str, roles: list[str], cmc: float = 2.0,
               is_commander=False, is_locked=False, card_type="Instant") -> DeckCard:
    return DeckCard(name=name, roles=roles, cmc=cmc,
                    is_commander=is_commander, is_locked=is_locked, card_type=card_type)


def test_score_returns_swap_candidates(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [_deck_card("Ramp Rock", ["Ramp"], cmc=2.0)]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    assert len(result) == 1
    assert isinstance(result[0], SwapCandidate)


def test_score_commander_excluded(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("The Commander", ["Ramp"], cmc=5.0, is_commander=True),
        _deck_card("Ramp Rock", ["Ramp"], cmc=2.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    names = [c.name for c in result]
    assert "The Commander" not in names
    assert "Ramp Rock" in names


def test_score_locked_excluded(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Locked Staple", ["Ramp"], cmc=3.0, is_locked=True),
        _deck_card("Ramp Rock", ["Ramp"], cmc=2.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    names = [c.name for c in result]
    assert "Locked Staple" not in names


def test_score_role_overlap_ranks_higher(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("On-Role Card", ["Ramp"], cmc=2.0),
        _deck_card("Off-Role Card", ["Draw"], cmc=5.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    # On-role card should outscore the off-role card despite lower CMC
    assert result[0].name == "On-Role Card"


def test_score_fallback_fills_to_top_n(tmp_path):
    """With only 1 role-matched card, fallback fills remaining slots."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Role Match", ["Ramp"], cmc=3.0),
        _deck_card("Filler A", ["Draw"], cmc=4.0),
        _deck_card("Filler B", ["Removal"], cmc=5.0),
        _deck_card("Filler C", ["Tokens"], cmc=2.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck, top_n=3)
    assert len(result) == 3
    assert result[0].name == "Role Match"  # role-matched first


def test_score_fallback_skips_lands(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Forest", [], cmc=0.0, card_type="Basic Land"),
        _deck_card("Filler", ["Draw"], cmc=3.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck, top_n=2)
    names = [c.name for c in result]
    assert "Forest" not in names


def test_score_empty_deck_returns_empty(tmp_path):
    svc = _svc_plain(tmp_path)
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), [])
    assert result == []


def test_score_fewer_than_top_n_swappable_no_crash(tmp_path):
    """Deck with only 2 swappable cards returns 2, not error."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Card A", ["Ramp"], cmc=2.0),
        _deck_card("Card B", ["Draw"], cmc=3.0),
    ]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck, top_n=3)
    assert len(result) == 2


def test_score_reason_contains_role_name(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [_deck_card("Ramp Rock", ["Ramp"], cmc=2.0)]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    assert "Ramp" in result[0].reason


def test_score_high_cmc_mentioned_in_reason(tmp_path):
    svc = _svc_plain(tmp_path)
    deck = [_deck_card("Expensive Card", ["Ramp"], cmc=5.0)]
    result = svc.score_swap_candidates(_suggestion(["Ramp"]), deck)
    # Expensive single-role card costs more than the replacement (CMC 3) —
    # new scoring says "saves N mana" for same-role cuts.
    reason = result[0].reason.lower()
    assert "mana" in reason or "ramp" in reason


def test_score_single_role_higher_cmc_ranks_above_lower_cmc(tmp_path):
    """Single-role suggestion: a same-role deck card at higher CMC should outscore
    a same-role card at lower CMC (cutting expensive redundancy is better)."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Cheap Ramp", ["Ramp"], cmc=1.0),   # lower CMC than suggestion
        _deck_card("Pricey Ramp", ["Ramp"], cmc=5.0),  # higher CMC than suggestion
    ]
    suggestion = _suggestion(["Ramp"])  # CMC 3.0
    result = svc.score_swap_candidates(suggestion, deck, top_n=2)
    assert result[0].name == "Pricey Ramp"
    assert "saves" in result[0].reason.lower() or "mana" in result[0].reason.lower()


def test_score_multi_role_direct_upgrade_wins(tmp_path):
    """Multi-role suggestion: a deck card that already covers ALL same roles at
    a higher CMC should rank as Option B (direct upgrade)."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Clunky Dual", ["Ramp", "Card Draw"], cmc=6.0),  # all roles, higher CMC
        _deck_card("Single Role", ["Ramp"], cmc=4.0),                # partial overlap
    ]
    suggestion = _suggestion(["Ramp", "Card Draw"])  # CMC 3.0
    result = svc.score_swap_candidates(suggestion, deck, top_n=2)
    assert result[0].name == "Clunky Dual"
    assert "direct upgrade" in result[0].reason.lower()


def test_score_multi_role_option_a_consolidation(tmp_path):
    """Multi-role suggestion: a single-role deck card at >= suggestion_cmc * 0.75
    should be scored via Option A (consolidation)."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Fair Ramp", ["Ramp"], cmc=3.0),       # 1 role, CMC = suggestion*1.0
        _deck_card("Cheap Ramp", ["Ramp"], cmc=1.0),      # 1 role, CMC < threshold
    ]
    suggestion = _suggestion(["Ramp", "Card Draw"])  # CMC 3.0; threshold = 2.25
    result = svc.score_swap_candidates(suggestion, deck, top_n=2)
    # Fair Ramp (CMC 3 >= 2.25) should be Option A, Cheap Ramp (CMC 1 < 2.25) partial
    assert result[0].name == "Fair Ramp"
    reason = result[0].reason.lower()
    assert "upgrade" in reason or "role" in reason


def test_score_dfc_deck_card_scores_lower_as_swap_target(tmp_path):
    """A double-faced deck card should score lower as a swap target than an equivalent
    non-DFC at the same CMC, because it provides more value than its CMC suggests."""
    svc = _svc_plain(tmp_path)
    deck = [
        _deck_card("Saga // Flip Side", ["Airbend"], cmc=5.0),  # DFC same-role
        _deck_card("Plain Ramp Spell", ["Airbend"], cmc=5.0),   # non-DFC same-role
    ]
    suggestion = _suggestion(["Airbend"])  # CMC 3.0
    result = svc.score_swap_candidates(suggestion, deck, top_n=2)
    # Plain Ramp Spell should score higher (DFC is harder to justify cutting)
    assert result[0].name == "Plain Ramp Spell"
    assert "double-faced" in result[1].reason


# ===========================================================================
# M3: get_general_suggestions
# ===========================================================================

def _gen_svc(tmp_path, rows: list[dict]) -> UpgradeSuggestionsService:
    """Build a service with the given parquet rows, no bulk data needed."""
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "no_bulk.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        return svc


def _gen_row(
    name: str,
    color_identity: str = "G",
    theme_tags: str = "Ramp",
    edhrec_rank: float = 1000.0,
    is_new: bool = False,
    usd: float = 1.0,
) -> dict:
    return {
        "name": name,
        "colorIdentity": color_identity,
        "themeTags": theme_tags,
        "edhrecRank": edhrec_rank,
        "manaValue": 3.0,
        "isNew": is_new,
        "printings": "ma1",
        "faceName": None,
        "price": usd,
    }


def test_general_excludes_cards_already_in_deck(tmp_path):
    rows = [_gen_row("Sol Ring"), _gen_row("Cultivate")]
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        result = svc.get_general_suggestions(
            deck_card_names={"Sol Ring"},
            color_identity=["G"],
            themes=["Ramp"],
            role_counts={},
        )
    names = [c.name for cards in result.values() for c in cards]
    assert "Sol Ring" not in names
    assert "Cultivate" in names


def test_general_excludes_new_cards(tmp_path):
    rows = [_gen_row("New Card", is_new=True), _gen_row("Old Card")]
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        result = svc.get_general_suggestions(
            deck_card_names=set(),
            color_identity=["G"],
            themes=[],
            role_counts={},
        )
    names = [c.name for cards in result.values() for c in cards]
    assert "New Card" not in names
    assert "Old Card" in names


def test_general_role_gap_boosts_under_represented(tmp_path):
    """Card filling an under-represented role should score ahead of one that fills a saturated role."""
    rows = [
        _gen_row("Gap Filler", theme_tags="Card Draw", edhrec_rank=1000.0),
        _gen_row("Saturated Filler", theme_tags="Ramp", edhrec_rank=1000.0),
    ]
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    # "Card Draw" under-represented (1 card); "Ramp" saturated (10 cards)
    # No deck themes passed → theme_match=0 for both; tie-break is role_gap_bonus.
    role_counts = {"Ramp": 10, "Card Draw": 1}
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        result = svc.get_general_suggestions(
            deck_card_names=set(),
            color_identity=["G"],
            themes=[],  # No themes → theme_match=0 for both; role gap dominates
            role_counts=role_counts,
        )
    cards = [c for bucket in result.values() for c in bucket]
    names = [c.name for c in cards]
    assert names.index("Gap Filler") < names.index("Saturated Filler")


def test_general_no_budget_single_tier(tmp_path):
    rows = [_gen_row("Card A"), _gen_row("Card B")]
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        result = svc.get_general_suggestions(
            deck_card_names=set(),
            color_identity=["G"],
            themes=[],
            role_counts={},
        )
    assert list(result.keys()) == ["General Upgrades"]


def test_general_budget_tier_bucketing(tmp_path):
    rows = [
        _gen_row("Cheap Card", usd=0.50),
        _gen_row("Pricey Card", usd=3.00),
        _gen_row("Expensive Card", usd=7.00),
        _gen_row("Too Expensive", usd=25.00),
    ]
    parquet_path = _write_parquet(tmp_path, rows)
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=parquet_path):
        result = svc.get_general_suggestions(
            deck_card_names=set(),
            color_identity=["G"],
            themes=[],
            role_counts={},
            budget_per_card=2.0,
        )
    within = {c.name for c in result.get("Within Budget", [])}
    slight = {c.name for c in result.get("Slightly Out of Budget", [])}
    out = {c.name for c in result.get("Out of Budget", [])}
    assert "Cheap Card" in within
    assert "Pricey Card" in slight
    assert "Expensive Card" in out
    assert "Too Expensive" not in within | slight | out


def test_general_missing_parquet_returns_empty(tmp_path):
    svc = UpgradeSuggestionsService(bulk_data_path=str(tmp_path / "x.json"))
    with patch(f"{_MODULE}.get_processed_cards_path", return_value=str(tmp_path / "missing.parquet")):
        result = svc.get_general_suggestions(
            deck_card_names=set(),
            color_identity=["G"],
            themes=[],
            role_counts={},
        )
    assert result == {}
