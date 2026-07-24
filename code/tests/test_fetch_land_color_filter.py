"""Tests for color/theme-aware land filtering in the misc-lands step (Roadmap 31, Milestone 3).

Covers:
- `fetch_land_allowed_for_colors()` helper (mono-color hit/miss, multicolor
  partial overlap, colorless commander, universal-tag always-true cases).
- `kindred_land_allowed_for_deck()` helper (named-tribe kindred lands like
  Seraph Sanctuary/'Angel Kindred' are only relevant to a deck that actually
  selected that tribe as a theme).
- Regression: the misc-lands step (`add_misc_utility_lands`) must not offer a
  non-curated, fetch-shaped land whose only searchable basic type is outside
  the commander's color identity, nor a named-tribe kindred land whose tribe
  the deck didn't select.
"""

import pandas as pd

from deck_builder import builder_utils as bu
from deck_builder.builder import DeckBuilder


def test_fetch_land_allowed_no_fetch_tags():
    # Not a fetch land at all -> not this function's concern, returns True
    assert bu.fetch_land_allowed_for_colors(['Ramp'], ['R']) is True


def test_fetch_land_allowed_mono_color_hit():
    assert bu.fetch_land_allowed_for_colors(['Mountain Fetch'], ['R']) is True


def test_fetch_land_allowed_mono_color_miss():
    assert bu.fetch_land_allowed_for_colors(['Plains Fetch', 'Island Fetch'], ['R']) is False


def test_fetch_land_allowed_multicolor_partial_overlap():
    # Bant deck (G/W/U), fetch only finds a W/B pair -> allowed since W overlaps
    assert bu.fetch_land_allowed_for_colors(['Plains Fetch', 'Swamp Fetch'], ['G', 'W', 'U']) is True


def test_fetch_land_allowed_colorless_commander():
    assert bu.fetch_land_allowed_for_colors(['Mountain Fetch'], []) is False
    assert bu.fetch_land_allowed_for_colors(['Any Basic Fetch'], []) is True


def test_fetch_land_allowed_universal_tags():
    for tag in ('Any Basic Fetch', 'Land Fetch', 'Gate Fetch'):
        assert bu.fetch_land_allowed_for_colors([tag], ['R']) is True
        assert bu.fetch_land_allowed_for_colors([tag], []) is True


def test_fetch_land_allowed_handles_ndarray_and_nan():
    import numpy as np
    assert bu.fetch_land_allowed_for_colors(np.array(['Plains Fetch']), ['R']) is False
    assert bu.fetch_land_allowed_for_colors(np.array(['Plains Fetch']), ['W']) is True
    assert bu.fetch_land_allowed_for_colors(float('nan'), ['R']) is True
    assert bu.fetch_land_allowed_for_colors(None, ['R']) is True


def test_kindred_land_allowed_no_kindred_tags():
    # Not a named-tribe kindred land -> not this function's concern, True
    assert bu.kindred_land_allowed_for_deck(['Lands Matter'], ['goblin kindred']) is True


def test_kindred_land_allowed_matching_tribe():
    assert bu.kindred_land_allowed_for_deck(['Angel Kindred', 'Lifegain'], ['angel kindred']) is True


def test_kindred_land_allowed_mismatched_tribe():
    assert bu.kindred_land_allowed_for_deck(['Angel Kindred', 'Lifegain'], ['goblin kindred']) is False
    assert bu.kindred_land_allowed_for_deck(['Angel Kindred'], []) is False


def test_kindred_land_allowed_handles_ndarray_and_nan():
    import numpy as np
    assert bu.kindred_land_allowed_for_deck(np.array(['Angel Kindred']), ['angel kindred']) is True
    assert bu.kindred_land_allowed_for_deck(np.array(['Angel Kindred']), ['goblin kindred']) is False
    assert bu.kindred_land_allowed_for_deck(float('nan'), []) is True
    assert bu.kindred_land_allowed_for_deck(None, []) is True


def test_misc_lands_step_excludes_offcolor_noncurated_fetch():
    """A Panorama/New-Capenna-style fetch (not in COLOR_TO_FETCH_LANDS) that
    can only find W/B basics must not be offered to a mono-red deck's misc
    land pool."""
    builder = DeckBuilder(headless=True, output_func=lambda *a, **k: None, input_func=lambda *a, **k: "")
    builder.files_to_load = ['dummy']
    builder.color_identity = ['R']
    builder.card_library = {}
    builder.selected_tags = []
    builder.show_diagnostics = False
    builder.ideal_counts = {'lands': 35, 'basic_lands': 20}
    builder._combined_cards_df = pd.DataFrame([
        {
            'name': 'Oncolor Panorama Land',
            'type': 'Land',
            'text': 'Test fetch land',
            'themeTags': ['Panorama Land', 'Lands Matter'],
            'metadataTags': ['Mountain Fetch'],
            'edhrecRank': 1,
        },
        {
            'name': 'Offcolor Panorama Land',
            'type': 'Land',
            'text': 'Test fetch land',
            'themeTags': ['Panorama Land', 'Lands Matter'],
            'metadataTags': ['Plains Fetch', 'Swamp Fetch'],
            'edhrecRank': 2,
        },
        {
            'name': 'Offtheme Kindred Land',
            'type': 'Land',
            'text': 'Whenever an Angel you control enters, you gain 1 life.',
            'themeTags': ['Angel Kindred', 'Lifegain'],
            'metadataTags': [],
            'edhrecRank': 3,
        },
    ] + [
        # Filler candidates ranked worse than the three above so the EDHREC
        # top% trimming step (which randomly keeps 75-100% of the pool)
        # never has a chance to drop a target candidate.
        {
            'name': f'Filler Land {i}',
            'type': 'Land',
            'text': 'Tap: add {C}.',
            'themeTags': [],
            'metadataTags': [],
            'edhrecRank': 100 + i,
        }
        for i in range(8)
    ])

    # Request enough lands that every surviving (non-offcolor, on-theme)
    # candidate gets selected, so the assertions aren't at the mercy of
    # weighted-random sampling among equal-weight candidates.
    builder.add_misc_utility_lands(requested_count=20)

    assert 'Offcolor Panorama Land' not in builder.card_library
    assert 'Offtheme Kindred Land' not in builder.card_library
    assert 'Oncolor Panorama Land' in builder.card_library


def test_misc_lands_step_keeps_ontheme_kindred_land():
    """The same named-tribe kindred land must survive when the deck actually
    selected that tribe as a theme (e.g. an Angel Kindred deck)."""
    builder = DeckBuilder(headless=True, output_func=lambda *a, **k: None, input_func=lambda *a, **k: "")
    builder.files_to_load = ['dummy']
    builder.color_identity = ['W']
    builder.card_library = {}
    builder.selected_tags = ['Angel Kindred']
    builder.show_diagnostics = False
    builder.ideal_counts = {'lands': 35, 'basic_lands': 20}
    builder._combined_cards_df = pd.DataFrame([
        {
            'name': 'Ontheme Kindred Land',
            'type': 'Land',
            'text': 'Whenever an Angel you control enters, you gain 1 life.',
            'themeTags': ['Angel Kindred', 'Lifegain'],
            'metadataTags': [],
            'edhrecRank': 1,
        },
    ] + [
        {
            'name': f'Filler Land {i}',
            'type': 'Land',
            'text': 'Tap: add {C}.',
            'themeTags': [],
            'metadataTags': [],
            'edhrecRank': 100 + i,
        }
        for i in range(8)
    ])

    builder.add_misc_utility_lands(requested_count=20)

    assert 'Ontheme Kindred Land' in builder.card_library
