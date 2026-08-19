"""Tests for the Rulebreaker commander mechanic (Roadmap 35, Milestones 1-2)."""
from types import SimpleNamespace

import pandas as pd

from deck_builder import builder_utils as bu
from deck_builder.builder_constants import RULEBREAKER_ARCHETYPES
from deck_builder.rulebreaker_rules import RULE_TYPE_PREDICATES, card_pool_exception
from tagging.tagger import tag_for_rulebreakers


def _cards_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


class DummyBuilder:
    def __init__(self, commander_name=None, combined_commander=None):
        self.commander_name = commander_name
        if combined_commander is not None:
            self.combined_commander = combined_commander


def test_tag_for_rulebreakers_applies_marker_tag():
    df = _cards_df([
        {'name': 'Maular, the Next Evolution'},
        {'name': 'Sol Ring'},
    ])
    tag_for_rulebreakers(df, 'g')
    maular_tags = df.loc[df['name'] == 'Maular, the Next Evolution', 'themeTags'].iloc[0]
    sol_ring_tags = df.loc[df['name'] == 'Sol Ring', 'themeTags'].iloc[0]
    assert maular_tags == ['Rulebreaker: Maular, the Next Evolution']
    assert sol_ring_tags == []


def test_detect_active_rulebreakers_primary_match():
    b = DummyBuilder(commander_name='Whtz, the Bibliophile')
    results = bu.detect_active_rulebreakers(b)
    assert [r['id'] for r in results] == ['whtz_the_bibliophile']
    assert results[0]['no_max_deck_size'] is True


def test_detect_active_rulebreakers_no_match():
    b = DummyBuilder(commander_name='Sol Ring')
    assert bu.detect_active_rulebreakers(b) == []


def test_detect_active_rulebreakers_partner_pair():
    combined = type('Combined', (), {'secondary_name': 'Tolabow, Loch Rascal'})()
    b = DummyBuilder(commander_name='Maular, the Next Evolution', combined_commander=combined)
    ids = {r['id'] for r in bu.detect_active_rulebreakers(b)}
    assert ids == {'maular_next_evolution', 'tolabow_loch_rascal'}


def test_rule_type_cmc_any_color_predicate():
    predicate = RULE_TYPE_PREDICATES['type_cmc_any_color']
    params = {'types': ['Creature'], 'mv_min': 7}
    big_creature = {'type': 'Creature — Dragon', 'manaValue': 7}
    small_creature = {'type': 'Creature — Elf', 'manaValue': 2}
    non_creature = {'type': 'Sorcery', 'manaValue': 8}
    assert predicate(big_creature, params) is True
    assert predicate(small_creature, params) is False
    assert predicate(non_creature, params) is False


def test_rule_any_land_and_no_max_deck_size_predicates():
    assert RULE_TYPE_PREDICATES['any_land']({'type': 'Land'}, {}) is True
    assert RULE_TYPE_PREDICATES['any_land']({'type': 'Creature — Otter'}, {}) is False
    # no_max_deck_size never contributes a card-pool match
    assert RULE_TYPE_PREDICATES['no_max_deck_size']({'type': 'Creature'}, {}) is False


# --- Milestone 3 integration tests -----------------------------------------
# These exercise the exact functions setup_dataframes()/the land phases call
# (card_pool_exception, resolve_basic_lands_scope) against the real
# RULEBREAKER_ARCHETYPES entries, rather than a full CSV-backed DeckBuilder
# build (per the roadmap's Milestone 3 Testing Plan scenarios).

def test_maular_card_pool_exception_allows_big_offcolor_creature_only():
    meta = RULEBREAKER_ARCHETYPES['maular_next_evolution']
    active = [meta]
    big_black_creature = {'type': 'Creature — Zombie', 'manaValue': 7, 'colorIdentity': ['B']}
    small_black_creature = {'type': 'Creature — Zombie', 'manaValue': 3, 'colorIdentity': ['B']}
    assert card_pool_exception(big_black_creature, active) is True
    assert card_pool_exception(small_black_creature, active) is False
    # Maular's basic_lands_scope is 'any': all 5 basics stay eligible.
    assert bu.resolve_basic_lands_scope(SimpleNamespace(active_rulebreakers=active)) == 'any'


def test_tolabow_card_pool_exception_offcolor_instant_only_with_extra_color():
    meta = RULEBREAKER_ARCHETYPES['tolabow_loch_rascal']
    active = [meta]
    offcolor_instant = {'type': 'Instant', 'colorIdentity': ['R']}
    offcolor_creature = {'type': 'Creature — Goblin', 'colorIdentity': ['R']}
    assert card_pool_exception(offcolor_instant, active, extra_color='R') is True
    assert card_pool_exception(offcolor_creature, active, extra_color='R') is False
    # No extra color chosen: the off-color instant is no longer legal either.
    assert card_pool_exception(offcolor_instant, active, extra_color=None) is False
    # Tolabow's basic_lands_scope is 'any': all 5 basics stay eligible.
    assert bu.resolve_basic_lands_scope(SimpleNamespace(active_rulebreakers=active)) == 'any'


def test_whtz_card_pool_exception_never_bypasses_strict_color_identity():
    meta = RULEBREAKER_ARCHETYPES['whtz_the_bibliophile']
    active = [meta]
    offcolor_creature = {'type': 'Creature — Dragon', 'manaValue': 5, 'colorIdentity': ['B']}
    offcolor_land = {'type': 'Land', 'colorIdentity': []}
    # no_max_deck_size only affects deck size, never the card-pool filter.
    assert card_pool_exception(offcolor_creature, active) is False
    assert card_pool_exception(offcolor_land, active) is False
    assert bu.resolve_basic_lands_scope(SimpleNamespace(active_rulebreakers=active)) == 'strict'


def test_grizzlegom_card_pool_exception_allows_offcolor_nonbasic_land():
    meta = RULEBREAKER_ARCHETYPES['grizzlegom_hurloon_hero']
    active = [meta]
    offcolor_utility_land = {'type': 'Land', 'colorIdentity': ['U']}
    offcolor_creature = {'type': 'Creature — Sphinx', 'colorIdentity': ['U']}
    assert card_pool_exception(offcolor_utility_land, active) is True
    assert card_pool_exception(offcolor_creature, active) is False
    # Grizzlegom's basic_lands_scope is 'any_land': the superset scope.
    assert bu.resolve_basic_lands_scope(SimpleNamespace(active_rulebreakers=active)) == 'any_land'
