from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from deck_builder.builder import DeckBuilder
from code.web.services.orchestrator import _add_secondary_commander_card


def test_add_secondary_commander_card_injects_partner() -> None:
    builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    partner_name = "Pir, Imaginative Rascal"
    combined = SimpleNamespace(secondary_name=partner_name)
    commander_df = pd.DataFrame(
        [
            {
                "name": partner_name,
                "type": "Legendary Creature — Human",
                "manaCost": "{2}{G}",
                "manaValue": 3,
                "creatureTypes": ["Human", "Ranger"],
                "themeTags": ["+1/+1 Counters"],
            }
        ]
    )

    assert partner_name not in builder.card_library

    _add_secondary_commander_card(builder, commander_df, combined)

    assert partner_name in builder.card_library
    entry = builder.card_library[partner_name]
    assert entry["Commander"] is True
    assert entry["Role"] == "commander"
    assert entry["SubRole"] == "Partner"
