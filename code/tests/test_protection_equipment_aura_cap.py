"""Tests for the Protection step's Equipment/Aura cap.

EDHREC over-indexes on Equipment for "protection" picks, but most Equipment/Auras
can't grant protection the turn they're cast (they need to be equipped/enchanted
separately first). `add_protection()` caps how many Equipment- or Aura-typed cards
count toward the protection target so non-equipment/aura protection spells still
get a chance to fill the rest of the target.
"""

import pandas as pd

from deck_builder import builder_constants as bc
from deck_builder.builder import DeckBuilder


def _make_builder(target: int = 8):
    builder = DeckBuilder(headless=True, output_func=lambda *a, **k: None, input_func=lambda *a, **k: "")
    builder.files_to_load = ['dummy']
    builder.color_identity = ['W']
    builder.card_library = {}
    builder.selected_tags = []
    builder.show_diagnostics = False
    builder.ideal_counts = {'protection': target}
    builder.set_seed(42)
    return builder


def test_add_protection_caps_equipment_and_auras():
    builder = _make_builder(target=8)

    equip_aura_rows = [
        {
            'name': f'Equip Protector {i}',
            'type': 'Artifact — Equipment',
            'manaCost': '{2}',
            'manaValue': 2,
            'themeTags': ['Protection'],
            'metadataTags': [],
            'edhrecRank': i,
        }
        for i in range(1, 7)
    ] + [
        {
            'name': f'Aura Protector {i}',
            'type': 'Enchantment — Aura',
            'manaCost': '{1}{W}',
            'manaValue': 2,
            'themeTags': ['Protection'],
            'metadataTags': [],
            'edhrecRank': 10 + i,
        }
        for i in range(1, 4)
    ]
    other_rows = [
        {
            'name': f'Protection Spell {i}',
            'type': 'Instant',
            'manaCost': '{W}',
            'manaValue': 1,
            'themeTags': ['Protection'],
            'metadataTags': [],
            'edhrecRank': 20 + i,
        }
        for i in range(1, 10)
    ]

    builder._combined_cards_df = pd.DataFrame(equip_aura_rows + other_rows)

    builder.add_protection()

    added_names = set(builder.card_library.keys())
    equip_aura_added = sum(
        1 for n in added_names if n.startswith('Equip Protector') or n.startswith('Aura Protector')
    )
    other_added = sum(1 for n in added_names if n.startswith('Protection Spell'))

    # Cap enforced: never more than the max, never fewer than the min (plenty of
    # equip/aura candidates were supplied so the cap should always be reached).
    assert bc.PROTECTION_EQUIPMENT_AURA_CAP_MIN <= equip_aura_added <= bc.PROTECTION_EQUIPMENT_AURA_CAP_MAX
    # Fewer than all supplied equip/aura candidates were used, proving the cap kicked in.
    assert equip_aura_added < len(equip_aura_rows)
    # Non-equipment/aura protection spells filled the remainder of the target.
    assert other_added == len(added_names) - equip_aura_added
    assert other_added > 0
