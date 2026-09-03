"""Tests for the Roadmap 40 metadataTags: Token Multiplier, Token Modifier: Additive,
Counter Multiplier, and Kindred Support (plus the pool-widening helper that consumes them).
"""
import pandas as pd

from tagging.tagger import tag_for_tokens, tag_for_counter_multipliers, tag_for_kindred_support
from deck_builder import builder_utils as bu


def _df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


def _tags_for(df: pd.DataFrame, name: str) -> list[str]:
    return df.loc[df['name'] == name, 'themeTags'].iloc[0]


def test_token_multiplier_and_additive_split():
    df = _df([
        {
            'name': 'Doubling Season',
            'type': 'Enchantment',
            'text': 'If an effect would create one or more tokens under your control, '
                    'it creates twice that many of those tokens instead.',
        },
        {
            'name': 'Academy Manufactor',
            'type': 'Artifact Creature - Assembly-Worker',
            'text': 'If you would create a Clue, Food, or Treasure token, instead create one of each.',
        },
        {
            'name': 'Divine Visitation',
            'type': 'Enchantment',
            'text': 'If one or more creature tokens would be created under your control, that many 4/4 '
                    'white Angel creature tokens with flying and vigilance are created instead.',
        },
    ])
    tag_for_tokens(df, 'g')

    assert 'Token Multiplier' in _tags_for(df, 'Doubling Season')
    assert 'Token Modifier: Additive' not in _tags_for(df, 'Doubling Season')

    assert 'Token Modifier: Additive' in _tags_for(df, 'Academy Manufactor')
    assert 'Token Multiplier' not in _tags_for(df, 'Academy Manufactor')

    # Full type-substitution ("Changed") cards get neither new tag; they already
    # surface via their own specific creature/token-type tags elsewhere.
    assert 'Token Multiplier' not in _tags_for(df, 'Divine Visitation')
    assert 'Token Modifier: Additive' not in _tags_for(df, 'Divine Visitation')


def test_counter_multiplier_tagging():
    df = _df([
        {
            'name': 'Doubling Season',
            'text': 'If one or more +1/+1 counters would be put on a creature you control, '
                    'twice that many +1/+1 counters are put on it instead.',
        },
        {
            'name': 'Gilder Bairn',
            'text': '{T}: Double the number of each kind of counter on target permanent.',
        },
        {
            'name': 'Some Vanilla Creature',
            'text': 'Vigilance',
        },
    ])
    tag_for_counter_multipliers(df, 'g')

    assert 'Counter Multiplier' in _tags_for(df, 'Doubling Season')
    assert 'Counter Multiplier' in _tags_for(df, 'Gilder Bairn')
    assert 'Counter Multiplier' not in _tags_for(df, 'Some Vanilla Creature')


def test_kindred_support_excludes_hosers_and_utility():
    df = _df([
        {
            'name': 'Adaptive Automaton',
            'text': 'As Adaptive Automaton enters, choose a creature type. Creatures you control of the '
                    'chosen type get +1/+1.',
        },
        {
            'name': 'Engineered Plague',
            'text': 'As Engineered Plague enters, choose a creature type. Creatures of the chosen type '
                    'get -1/-1.',
        },
        {
            'name': 'Imagecrafter',
            'text': "{T}: Target creature becomes the creature type of your choice until end of turn.",
        },
    ])
    tag_for_kindred_support(df, 'wubrg')

    assert 'Kindred Support' in _tags_for(df, 'Adaptive Automaton')
    assert 'Kindred Support' not in _tags_for(df, 'Engineered Plague')
    assert 'Kindred Support' not in _tags_for(df, 'Imagecrafter')


def test_expand_theme_subset_with_metadata_widens_tokens_theme():
    pool_df = pd.DataFrame([
        {'name': 'Cat Warrior', 'metadataTags': []},
        {'name': 'Academy Manufactor', 'metadataTags': ['Token Modifier: Additive']},
        {'name': 'Some Ramp Spell', 'metadataTags': []},
    ])
    subset = pool_df[pool_df['name'] == 'Cat Warrior']

    widened = bu.expand_theme_subset_with_metadata(subset, pool_df, 'cat tokens')
    assert set(widened['name']) == {'Cat Warrior', 'Academy Manufactor'}

    # A non token/counter/kindred theme is returned unchanged.
    unchanged = bu.expand_theme_subset_with_metadata(subset, pool_df, 'ramp')
    assert set(unchanged['name']) == {'Cat Warrior'}


def test_expand_theme_subset_with_metadata_widens_kindred_theme_with_changelings():
    pool_df = pd.DataFrame([
        {'name': 'Plain Otter', 'metadataTags': [], 'themeTags': ['Otter Kindred']},
        {'name': 'Morophon, the Boundless', 'metadataTags': [], 'themeTags': ['Changeling']},
        {'name': 'Adaptive Automaton', 'metadataTags': ['Kindred Support'], 'themeTags': []},
        {'name': 'Some Ramp Spell', 'metadataTags': [], 'themeTags': []},
    ])
    subset = pool_df[pool_df['name'] == 'Plain Otter']

    widened = bu.expand_theme_subset_with_metadata(subset, pool_df, 'otter kindred')
    assert set(widened['name']) == {'Plain Otter', 'Morophon, the Boundless', 'Adaptive Automaton'}

    # A Changeling card shouldn't get every Kindred tag added to its own themeTags;
    # it's the pool widening that includes it, not the card's own tag list.
    assert pool_df.loc[pool_df['name'] == 'Morophon, the Boundless', 'themeTags'].iloc[0] == ['Changeling']
