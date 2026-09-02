"""Tests for Lifedrain text pattern matching (create_lifedrain_text_mask)."""
import pandas as pd

from code.tagging import tag_constants, tag_utils


def _mask_for(texts):
    df = pd.DataFrame({'text': texts})
    return tag_utils.create_text_mask(df, tag_constants.LIFEDRAIN_TEXT_PATTERNS)


def test_lifedrain_matches_literal_same_number_loses_then_gains():
    # Retreat to Hagra
    mask = _mask_for(['Each opponent loses 1 life and you gain 1 life.'])
    assert mask.iloc[0]


def test_lifedrain_matches_blood_artist_wording():
    mask = _mask_for(['Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.'])
    assert mask.iloc[0]


def test_lifedrain_matches_gain_then_loses_order():
    mask = _mask_for(['You gain 3 life and each opponent loses 3 life.'])
    assert mask.iloc[0]


def test_lifedrain_does_not_match_mismatched_numbers():
    mask = _mask_for(['Each opponent loses 2 life and you gain 1 life.'])
    assert not mask.iloc[0]


def test_lifedrain_still_matches_existing_equal_to_wording():
    mask = _mask_for(['Each opponent loses life equal to the number of creatures you control and you gain life equal to the life lost.'])
    assert mask.iloc[0]
