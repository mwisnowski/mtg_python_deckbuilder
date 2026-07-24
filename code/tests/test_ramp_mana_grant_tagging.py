"""Tests for mana-grant/worded-mana Ramp tagging (Roadmap 31, Milestone 5)."""
import pandas as pd

from tagging.tagger import tag_for_ramp


def _ramp_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['themeTags'] = [[] for _ in range(len(df))]
    return df


def _tags_for(df: pd.DataFrame, name: str) -> list[str]:
    return df.loc[df['name'] == name, 'themeTags'].iloc[0]


def test_enchantment_grants_mana_ability_to_other_permanents():
    df = _ramp_df([
        {
            'name': 'A Realm Reborn',
            'type': 'Enchantment',
            'text': "Other permanents you control have \"{T}: Add one mana of any color.\"",
        },
    ])
    tag_for_ramp(df, 'wu')
    assert 'Ramp' in _tags_for(df, 'A Realm Reborn')


def test_worded_non_symbol_mana_amount():
    df = _ramp_df([
        {
            'name': 'Test Mana Burst',
            'type': 'Sorcery',
            'text': 'Add two mana of any one color.',
        },
    ])
    tag_for_ramp(df, 'colorless')
    assert 'Ramp' in _tags_for(df, 'Test Mana Burst')


def test_mana_tax_text_is_not_a_false_positive():
    df = _ramp_df([
        {
            'name': 'Test Mana Tax',
            'type': 'Enchantment',
            'text': "Creatures can't be sacrificed to abilities that produce mana of any color.",
        },
    ])
    tag_for_ramp(df, 'colorless')
    assert 'Ramp' not in _tags_for(df, 'Test Mana Tax')


def test_one_for_one_sacrifice_filter_is_not_ramp():
    """Golden Egg-style filters that spend as much (or more) generic mana than they
    produce don't net a mana gain, so they shouldn't be tagged Ramp."""
    df = _ramp_df([
        {
            'name': 'Test Filter Egg',
            'type': 'Artifact',
            'text': 'When this artifact enters, draw a card.\n{1}, {T}, Sacrifice this artifact: Add '
                    'one mana of any color.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.',
        },
    ])
    tag_for_ramp(df, 'colorless')
    assert 'Ramp' not in _tags_for(df, 'Test Filter Egg')


def test_charge_counter_mana_battery_is_not_ramp():
    df = _ramp_df([
        {
            'name': 'Test Mana Battery',
            'type': 'Artifact',
            'text': '{2}: Put a charge counter on this artifact.\nRemove a charge counter from this '
                    'artifact: Add one mana of any color.',
        },
    ])
    tag_for_ramp(df, 'colorless')
    assert 'Ramp' not in _tags_for(df, 'Test Mana Battery')
