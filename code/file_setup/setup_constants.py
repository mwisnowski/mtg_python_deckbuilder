from typing import Dict, List
from settings import (
    SETUP_COLORS,
    COLOR_ABRV,
    CARD_DATA_COLUMNS as COLUMN_ORDER,  # backward compatible alias
    CARD_DATA_COLUMNS as TAGGED_COLUMN_ORDER,
)

__all__ = [
    'SETUP_COLORS', 'COLOR_ABRV', 'COLUMN_ORDER', 'TAGGED_COLUMN_ORDER',
    'BANNED_CARDS', 'MTGJSON_API_URL', 'LEGENDARY_OPTIONS', 'NON_LEGAL_SETS',
    'CARD_TYPES_TO_EXCLUDE', 'CSV_PROCESSING_COLUMNS', 'SORT_CONFIG',
    'FILTER_CONFIG'
]

# Banned cards consolidated here (remains specific to setup concerns)
BANNED_CARDS: List[str] = [
    # Commander banned list
    'Ancestral Recall', 'Balance', 'Biorhythm', 'Black Lotus',
    'Chaos Orb', 'Channel', 'Dockside Extortionist',
    'Emrakul, the Aeons Torn',
    'Erayo, Soratami Ascendant', 'Falling Star', 'Fastbond',
    'Flash', 'Golos, Tireless Pilgrim',
    'Griselbrand', 'Hullbreacher', 'Iona, Shield of Emeria',
    'Karakas', 'Jeweled Lotus', 'Leovold, Emissary of Trest',
    'Library of Alexandria', 'Limited Resources', 'Lutri, the Spellchaser',
    'Mana Crypt', 'Mox Emerald', 'Mox Jet', 'Mox Pearl', 'Mox Ruby',
    'Mox Sapphire', 'Nadu, Winged Wisdom',
    'Paradox Engine', 'Primeval Titan', 'Prophet of Kruphix',
    'Recurring Nightmare', 'Rofellos, Llanowar Emissary', 'Shahrazad',
    'Sundering Titan', 'Sylvan Primordial',
    'Time Vault', 'Time Walk', 'Tinker', 'Tolarian Academy',
    'Trade Secrets', 'Upheaval', "Yawgmoth's Bargain",
    # Problematic / culturally sensitive or banned in other formats
    'Invoke Prejudice', 'Cleanse', 'Stone-Throwing Devils', 'Pradesh Gypsies',
    'Jihad', 'Imprison', 'Crusade',
    # Cards of the Hero type (non creature)
    "The Protector", "The Hunter", "The Savant", "The Explorer",
    "The Philosopher", "The Harvester", "The Tyrant", "The Vanquisher",
    "The Avenger", "The Slayer", "The Warmonger", "The Destined",
    "The Warrior", "The General", "The Provider", "The Champion",
    # Hero Equipment
    "Spear of the General", "Lash of the Tyrant", "Bow of the Hunter",
    "Cloak of the Philosopher", "Axe of the Warmonger"
]

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

# COLUMN_ORDER and TAGGED_COLUMN_ORDER now sourced from settings via CARD_DATA_COLUMNS