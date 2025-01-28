from typing import Dict, List, Optional, Final, Tuple, Pattern, Union, Callable

BANNED_CARDS: List[str] = [# in commander
                'Ancestral Recall', 'Balance', 'Biorhythm', 'Black Lotus',
                'Braids, Cabal Minion', 'Chaos Orb', 'Coalition Victory',
                'Channel', 'Dockside Extortionist', 'Emrakul, the Aeons Torn',
                'Erayo, Soratami Ascendant', 'Falling Star', 'Fastbond',
                'Flash', 'Gifts Ungiven', 'Golos, Tireless Pilgrim',
                'Griselbrand', 'Hullbreacher', 'Iona, Shield of Emeria',
                'Karakas', 'Jeweled Lotus', 'Leovold, Emissary of Trest',
                'Library of Alexandria', 'Limited Resources', 'Lutri, the Spellchaser',
                'Mana Crypt', 'Mox Emerald', 'Mox Jet', 'Mox Pearl', 'Mox Ruby',
                'Mox Sapphire', 'Nadu, Winged Wisdom', 'Panoptic Mirror',
                'Paradox Engine', 'Primeval Titan', 'Prophet of Kruphix',
                'Recurring Nightmare', 'Rofellos, Llanowar Emissary', 'Shahrazad',
                'Sundering Titan', 'Sway of the Stars', 'Sylvan Primordial',
                'Time Vault', 'Time Walk', 'Tinker', 'Tolarian Academy',
                'Trade Secrets', 'Upheaval', 'Yawgmoth\'s Bargain',
                
                # In constructed
                'Invoke Prejudice', 'Cleanse', 'Stone-Throwing Devils', 'Pradesh Gypsies',
                'Jihad', 'Imprison', 'Crusade'
                ]

SETUP_COLORS: List[str] = ['colorless', 'white', 'blue', 'black', 'green', 'red',
          'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
          'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
          'bant', 'esper', 'grixis', 'jund', 'naya',
          'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
          'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg']

COLOR_ABRV: List[str] = ['Colorless', 'W', 'U', 'B', 'G', 'R',
              'U, W', 'B, W', 'G, W', 'R, W', 'B, U',
              'G, U', 'R, U', 'B, G', 'B, R', 'G, R',
              'G, U, W', 'B, U, W', 'B, R, U', 'B, G, R', 'G, R, W',
              'B, G, W', 'R, U, W', 'B, R, W', 'B, G, U', 'G, R, U',
              'B, G, R, W', 'B, G, R, U', 'G, R, U, W', 'B, G, U, W',
              'B, R, U, W', 'B, G, R, U, W']

# Constants for setup and CSV processing
MTGJSON_API_URL: str = 'https://mtgjson.com/api/v5/csv/cards.csv'

LEGENDARY_OPTIONS: List[str] = [
    'Legendary Creature',
    'Legendary Artifact',
    'Legendary Artifact Creature', 
    'Legendary Enchantment Creature',
    'Legendary Planeswalker'
]

NON_LEGAL_SETS: List[str] = [
    'PHTR', 'PH17', 'PH18', 'PH19', 'PH20', 'PH21',
    'UGL', 'UND', 'UNH', 'UST'
]

CARD_TYPES_TO_EXCLUDE: List[str] = [
    'Plane —',
    'Conspiracy',
    'Vanguard', 
    'Scheme',
    'Phenomenon',
    'Stickers',
    'Attraction',
    'Hero',
    'Contraption'
]

# Columns to keep when processing CSV files
CSV_PROCESSING_COLUMNS: List[str] = [
    'name',        # Card name
    'faceName',    # Name of specific face for multi-faced cards
    'edhrecRank',  # Card's rank on EDHREC
    'colorIdentity',  # Color identity for Commander format
    'colors',      # Actual colors in card's mana cost
    'manaCost',    # Mana cost string
    'manaValue',   # Converted mana cost
    'type',        # Card type line
    'layout',      # Card layout (normal, split, etc)
    'text',        # Card text/rules
    'power',       # Power (for creatures)
    'toughness',   # Toughness (for creatures)
    'keywords',    # Card's keywords
    'side'         # Side identifier for multi-faced cards
]

# Configuration for DataFrame sorting operations
SORT_CONFIG = {
    'columns': ['name', 'side'],  # Columns to sort by
    'case_sensitive': False  # Ignore case when sorting
}

# Configuration for DataFrame filtering operations
FILTER_CONFIG: Dict[str, Dict[str, List[str]]] = {
    'layout': {
        'exclude': ['reversible_card']
    },
    'availability': {
        'require': ['paper']
    },
    'promoTypes': {
        'exclude': ['playtest']
    },
    'securityStamp': {
        'exclude': ['Heart', 'Acorn']
    }
}

COLUMN_ORDER: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

TAGGED_COLUMN_ORDER: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]