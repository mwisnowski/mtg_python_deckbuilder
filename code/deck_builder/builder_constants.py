from typing import Dict, List, Final, Tuple, Union, Callable, Any as _Any
from settings import CARD_DATA_COLUMNS as CSV_REQUIRED_COLUMNS  # unified
from path_util import csv_dir

__all__ = [
    'CSV_REQUIRED_COLUMNS'
]
import ast

# Commander selection configuration
# Format string for displaying duplicate cards in deck lists
FUZZY_MATCH_THRESHOLD: Final[int] = 90  # Threshold for fuzzy name matching
MAX_FUZZY_CHOICES: Final[int] = 5  # Maximum number of fuzzy match choices

# Commander-related constants
DUPLICATE_CARD_FORMAT: Final[str] = '{card_name} x {count}'
COMMANDER_CSV_PATH: Final[str] = f"{csv_dir()}/commander_cards.csv"
DECK_DIRECTORY = '../deck_files'
COMMANDER_CONVERTERS: Final[Dict[str, str]] = {
    'themeTags': ast.literal_eval,
    'creatureTypes': ast.literal_eval,
    'roleTags': ast.literal_eval,
}  # CSV loading converters
COMMANDER_POWER_DEFAULT: Final[int] = 0
COMMANDER_TOUGHNESS_DEFAULT: Final[int] = 0
COMMANDER_MANA_VALUE_DEFAULT: Final[int] = 0
COMMANDER_TYPE_DEFAULT: Final[str] = ''
COMMANDER_TEXT_DEFAULT: Final[str] = ''
COMMANDER_MANA_COST_DEFAULT: Final[str] = ''
COMMANDER_COLOR_IDENTITY_DEFAULT: Final[str] = ''
COMMANDER_COLORS_DEFAULT: Final[List[str]] = []
COMMANDER_CREATURE_TYPES_DEFAULT: Final[str] = ''
COMMANDER_TAGS_DEFAULT: Final[List[str]] = []
COMMANDER_THEMES_DEFAULT: Final[List[str]] = []

# Reporting / summaries
TAG_SUMMARY_MIN_COUNT: Final[int] = 3  # Minimum unique-card count for a tag to appear in tag summary output
TAG_SUMMARY_ALWAYS_SHOW_SUBSTRS: Final[List[str]] = [
    'board wipe',   # ensure board wipes always shown even if below threshold
    'mass removal'  # common alternate phrasing
]

CARD_TYPES = ['Artifact','Creature', 'Enchantment', 'Instant', 'Land', 'Planeswalker', 'Sorcery',
              'Kindred', 'Dungeon', 'Battle']

# Basic mana colors
MANA_COLORS: Final[List[str]] = ['W', 'U', 'B', 'R', 'G']

# Mana pip patterns for each color
MANA_PIP_PATTERNS: Final[Dict[str, str]] = {
    color: f'{{{color}}}' for color in MANA_COLORS
}

MONO_COLOR_MAP: Final[Dict[str, Tuple[str, List[str]]]] = {
    'COLORLESS': ('Colorless', ['colorless']),
    'W': ('White', ['colorless', 'white']),
    'U': ('Blue', ['colorless', 'blue']),
    'B': ('Black', ['colorless', 'black']),
    'R': ('Red', ['colorless', 'red']),
    'G': ('Green', ['colorless', 'green'])
}

DUAL_COLOR_MAP: Final[Dict[str, Tuple[str, List[str], List[str]]]] = {
    'B, G': ('Golgari: Black/Green', ['B', 'G', 'B, G'], ['colorless', 'black', 'green', 'golgari']),
    'B, R': ('Rakdos: Black/Red', ['B', 'R', 'B, R'], ['colorless', 'black', 'red', 'rakdos']),
    'B, U': ('Dimir: Black/Blue', ['B', 'U', 'B, U'], ['colorless', 'black', 'blue', 'dimir']),
    'B, W': ('Orzhov: Black/White', ['B', 'W', 'B, W'], ['colorless', 'black', 'white', 'orzhov']),
    'G, R': ('Gruul: Green/Red', ['G', 'R', 'G, R'], ['colorless', 'green', 'red', 'gruul']),
    'G, U': ('Simic: Green/Blue', ['G', 'U', 'G, U'], ['colorless', 'green', 'blue', 'simic']),
    'G, W': ('Selesnya: Green/White', ['G', 'W', 'G, W'], ['colorless', 'green', 'white', 'selesnya']),
    'R, U': ('Izzet: Blue/Red', ['U', 'R', 'U, R'], ['colorless', 'blue', 'red', 'izzet']),
    'U, W': ('Azorius: Blue/White', ['U', 'W', 'U, W'], ['colorless', 'blue', 'white', 'azorius']),
    'R, W': ('Boros: Red/White', ['R', 'W', 'R, W'], ['colorless', 'red', 'white', 'boros'])
}

TRI_COLOR_MAP: Final[Dict[str, Tuple[str, List[str], List[str]]]] = {
    'B, G, U': ('Sultai: Black/Blue/Green', ['B', 'G', 'U', 'B, G', 'B, U', 'G, U', 'B, G, U'],
                ['colorless', 'black', 'blue', 'green', 'dimir', 'golgari', 'simic', 'sultai']),
    'B, G, R': ('Jund: Black/Red/Green', ['B', 'G', 'R', 'B, G', 'B, R', 'G, R', 'B, G, R'],
                ['colorless', 'black', 'green', 'red', 'golgari', 'rakdos', 'gruul', 'jund']),
    'B, G, W': ('Abzan: Black/Green/White', ['B', 'G', 'W', 'B, G', 'B, W', 'G, W', 'B, G, W'],
                ['colorless', 'black', 'green', 'white', 'golgari', 'orzhov', 'selesnya', 'abzan']),
    'B, R, U': ('Grixis: Black/Blue/Red', ['B', 'R', 'U', 'B, R', 'B, U', 'R, U', 'B, R, U'],
                ['colorless', 'black', 'blue', 'red', 'dimir', 'rakdos', 'izzet', 'grixis']),
    'B, R, W': ('Mardu: Black/Red/White', ['B', 'R', 'W', 'B, R', 'B, W', 'R, W', 'B, R, W'],
                ['colorless', 'black', 'red', 'white', 'rakdos', 'orzhov', 'boros', 'mardu']),
    'B, U, W': ('Esper: Black/Blue/White', ['B', 'U', 'W', 'B, U', 'B, W', 'U, W', 'B, U, W'],
                ['colorless', 'black', 'blue', 'white', 'dimir', 'orzhov', 'azorius', 'esper']),
    'G, R, U': ('Temur: Blue/Green/Red', ['G', 'R', 'U', 'G, R', 'G, U', 'R, U', 'G, R, U'],
                ['colorless', 'green', 'red', 'blue', 'simic', 'izzet', 'gruul', 'temur']),
    'G, R, W': ('Naya: Green/Red/White', ['G', 'R', 'W', 'G, R', 'G, W', 'R, W', 'G, R, W'],
                ['colorless', 'green', 'red', 'white', 'gruul', 'selesnya', 'boros', 'naya']),
    'G, U, W': ('Bant: Blue/Green/White', ['G', 'U', 'W', 'G, U', 'G, W', 'U, W', 'G, U, W'],
                ['colorless', 'green', 'blue', 'white', 'simic', 'azorius', 'selesnya', 'bant']),
    'R, U, W': ('Jeskai: Blue/Red/White', ['R', 'U', 'W', 'R, U', 'U, W', 'R, W', 'R, U, W'],
                ['colorless', 'blue', 'red', 'white', 'izzet', 'azorius', 'boros', 'jeskai'])
}

OTHER_COLOR_MAP: Final[Dict[str, Tuple[str, List[str], List[str]]]] = {
    'B, G, R, U': ('Glint: Black/Blue/Green/Red',
                   ['B', 'G', 'R', 'U', 'B, G', 'B, R', 'B, U', 'G, R', 'G, U', 'R, U', 'B, G, R',
                    'B, G, U', 'B, R, U', 'G, R, U', 'B, G, R, U'],
                   ['colorless', 'black', 'blue', 'green', 'red', 'golgari', 'rakdos', 'dimir',
                    'gruul', 'simic', 'izzet', 'jund', 'sultai', 'grixis', 'temur', 'glint']),
    'B, G, R, W': ('Dune: Black/Green/Red/White',
                   ['B', 'G', 'R', 'W', 'B, G', 'B, R', 'B, W', 'G, R', 'G, W', 'R, W', 'B, G, R',
                    'B, G, W', 'B, R, W', 'G, R, W', 'B, G, R, W'],
                   ['colorless', 'black', 'green', 'red', 'white', 'golgari', 'rakdos', 'orzhov',
                    'gruul', 'selesnya', 'boros', 'jund', 'abzan', 'mardu', 'naya', 'dune']),
    'B, G, U, W': ('Witch: Black/Blue/Green/White',
                   ['B', 'G', 'U', 'W', 'B, G', 'B, U', 'B, W', 'G, U', 'G, W', 'U, W', 'B, G, U',
                    'B, G, W', 'B, U, W', 'G, U, W', 'B, G, U, W'],
                   ['colorless', 'black', 'blue', 'green', 'white', 'golgari', 'dimir', 'orzhov',
                    'simic', 'selesnya', 'azorius', 'sultai', 'abzan', 'esper', 'bant', 'witch']),
    'B, R, U, W': ('Yore: Black/Blue/Red/White',
                   ['B', 'R', 'U', 'W', 'B, R', 'B, U', 'B, W', 'R, U', 'R, W', 'U, W', 'B, R, U',
                    'B, R, W', 'B, U, W', 'R, U, W', 'B, R, U, W'],
                   ['colorless', 'black', 'blue', 'red', 'white', 'rakdos', 'dimir', 'orzhov',
                    'izzet', 'boros', 'azorius', 'grixis', 'mardu', 'esper', 'jeskai', 'yore']),
    'G, R, U, W': ('Ink: Blue/Green/Red/White',
                   ['G', 'R', 'U', 'W', 'G, R', 'G, U', 'G, W', 'R, U', 'R, W', 'U, W', 'G, R, U',
                    'G, R, W', 'G, U, W', 'R, U, W', 'G, R, U, W'],
                   ['colorless', 'blue', 'green', 'red', 'white', 'gruul', 'simic', 'selesnya',
                    'izzet', 'boros', 'azorius', 'temur', 'naya', 'bant', 'jeskai', 'ink']),
    'B, G, R, U, W': ('WUBRG: All colors',
                      ['B', 'G', 'R', 'U', 'W', 'B, G', 'B, R', 'B, U', 'B, W', 'G, R', 'G, U',
                       'G, W', 'R, U', 'R, W', 'U, W', 'B, G, R', 'B, G, U', 'B, G, W', 'B, R, U',
                       'B, R, W', 'B, U, W', 'G, R, U', 'G, R, W', 'G, U, W', 'R, U, W',
                       'B, G, R, U', 'B, G, R, W', 'B, G, U, W', 'B, R, U, W', 'G, R, U, W',
                       'B, G, R, U, W'],
                      ['colorless', 'black', 'green', 'red', 'blue', 'white', 'golgari', 'rakdos',
                       'dimir', 'orzhov', 'gruul', 'simic', 'selesnya', 'izzet', 'boros', 'azorius',
                       'jund', 'sultai', 'abzan', 'grixis', 'mardu', 'esper', 'temur', 'naya',
                       'bant', 'jeskai', 'glint', 'dune', 'witch', 'yore', 'ink', 'wubrg'])
}

# Card category validation rules
CREATURE_VALIDATION_RULES: Final[Dict[str, Dict[str, Union[str, int, float, bool]]]] = {
    'power': {'type': ('str', 'int', 'float'), 'required': True},
    'toughness': {'type': ('str', 'int', 'float'), 'required': True},
    'creatureTypes': {'type': 'list', 'required': True}
}

SPELL_VALIDATION_RULES: Final[Dict[str, Dict[str, Union[str, int, float, bool]]]] = {
    'manaCost': {'type': 'str', 'required': True},
    'text': {'type': 'str', 'required': True}
}

LAND_VALIDATION_RULES: Final[Dict[str, Dict[str, Union[str, int, float, bool]]]] = {
    'type': {'type': ('str', 'object'), 'required': True},
    'text': {'type': ('str', 'object'), 'required': False}
}

# Price checking configuration
DEFAULT_PRICE_DELAY: Final[float] = 0.1  # Delay between price checks in seconds
MAX_PRICE_CHECK_ATTEMPTS: Final[int] = 3  # Maximum attempts for price checking
PRICE_CACHE_SIZE: Final[int] = 128  # Size of price check LRU cache
PRICE_CHECK_TIMEOUT: Final[int] = 30  # Timeout for price check requests in seconds
PRICE_TOLERANCE_MULTIPLIER: Final[float] = 1.1  # Multiplier for price tolerance
DEFAULT_MAX_CARD_PRICE: Final[float] = 20.0  # Default maximum price per card

# Deck composition defaults
DEFAULT_RAMP_COUNT: Final[int] = 8  # Default number of ramp pieces
DEFAULT_LAND_COUNT: Final[int] = 35  # Default total land count
DEFAULT_BASIC_LAND_COUNT: Final[int] = 15  # Default minimum basic lands
DEFAULT_NON_BASIC_LAND_SLOTS: Final[int] = 10  # Default number of non-basic land slots to reserve
DEFAULT_BASICS_PER_COLOR: Final[int] = 5  # Default number of basic lands to add per color

# Miscellaneous land configuration
MISC_LAND_MIN_COUNT: Final[int] = 5  # Minimum number of miscellaneous lands to add
MISC_LAND_MAX_COUNT: Final[int] = 10  # Maximum number of miscellaneous lands to add
MISC_LAND_POOL_SIZE: Final[int] = 100  # Maximum size of initial land pool to select from
MISC_LAND_TOP_POOL_SIZE: Final[int] = 30  # For utility step: sample from top N by EDHREC rank
MISC_LAND_COLOR_FIX_PRIORITY_WEIGHT: Final[int] = 2  # Weight multiplier for color-fixing candidates
MISC_LAND_USE_FULL_POOL: Final[bool] = True  # If True, ignore TOP_POOL_SIZE and use entire remaining land pool for misc step
MISC_LAND_EDHREC_KEEP_PERCENT: Final[float] = 0.80  # Legacy single-value fallback if min/max not set
# When both min & max are defined (0<min<=max<=1), Step 7 will roll a random % in [min,max]
# using the builder RNG to keep that share of top EDHREC-ranked candidates, injecting variety.
MISC_LAND_EDHREC_KEEP_PERCENT_MIN: Final[float] = 0.75
MISC_LAND_EDHREC_KEEP_PERCENT_MAX: Final[float] = 1.00

# Theme-based misc land weighting (applied after all reductions)
MISC_LAND_THEME_MATCH_ENABLED: Final[bool] = True
MISC_LAND_THEME_MATCH_BASE: Final[float] = 1.4          # Multiplier if at least one theme tag matches
MISC_LAND_THEME_MATCH_PER_EXTRA: Final[float] = 0.15    # Additional multiplier increment per extra matching tag beyond first
MISC_LAND_THEME_MATCH_CAP: Final[float] = 2.0           # Maximum total multiplier cap for theme boosting

# Mono-color extra rainbow filtering (text-based)
MONO_COLOR_EXCLUDE_RAINBOW_TEXT: Final[bool] = True  # If True, exclude lands whose rules text implies any-color mana in mono decks (beyond explicit list)
MONO_COLOR_RAINBOW_TEXT_EXTRA: Final[List[str]] = [  # Additional substrings (lowercased) checked besides ANY_COLOR_MANA_PHRASES
    'add one mana of any type',
    'choose a color',
    'add one mana of any color',
    'add one mana of any color that a gate',
    'add one mana of any color among',  # e.g., Plaza of Harmony style variants (kept list overrides)
]

# Mono-color misc land exclusion (utility/rainbow) logic
# Lands in this list will be excluded from the Step 7 misc/utility selection pool
# when the deck is mono-colored UNLESS they appear in MONO_COLOR_MISC_LAND_KEEP_ALWAYS
# or are detected as kindred lands (see KINDRED_* constants below).
MONO_COLOR_MISC_LAND_EXCLUDE: Final[List[str]] = [
    'Command Tower',
    'Mana Confluence',
    'City of Brass',
    'Grand Coliseum',
    'Tarnished Citadel',
    'Gemstone Mine',
    'Aether Hub',
    'Spire of Industry',
    'Exotic Orchard',
    'Reflecting Pool',
    'Plaza of Harmony',
    'Pillar of the Paruns',
    'Cascading Cataracts',
    'Crystal Quarry',
    'The World Tree',
    # Thriving cycle – functionally useless / invalid in strict mono-color builds
    'Thriving Bluff',
    'Thriving Grove',
    'Thriving Isle',
    'Thriving Heath',
    'Thriving Moor'
]

# Mono-color always-keep exceptions (never excluded by the above rule)
MONO_COLOR_MISC_LAND_KEEP_ALWAYS: Final[List[str]] = [
    'Forbidden Orchard',
    'Plaza of Heroes',
    'Path of Ancestry',
    'Lotus Field',
    'Lotus Vale'
]

## Kindred / creature-type / legend-supporting lands (single unified list)
# Consolidates former KINDRED_STAPLE_LANDS + KINDRED_MISC_LAND_NAMES + Plaza of Heroes
# Order is not semantically important; kept readable.
KINDRED_LAND_NAMES: Final[List[str]] = [
    'Path of Ancestry',
    'Three Tree City',
    'Cavern of Souls',
    'Unclaimed Territory',
    'Secluded Courtyard',
    'Plaza of Heroes'
]

# Default fetch land count & cap
FETCH_LAND_DEFAULT_COUNT: Final[int] = 3  # Default number of fetch lands to include
FETCH_LAND_MAX_CAP: Final[int] = 7  # Absolute maximum fetch lands allowed in final manabase

# Default dual land (two-color nonbasic) total target
DUAL_LAND_DEFAULT_COUNT: Final[int] = 4  # Heuristic total; actual added may be less based on colors/capacity

# Default triple land (three-color typed) total target (kept low; usually only 1-2 high quality available)
TRIPLE_LAND_DEFAULT_COUNT: Final[int] = 2  # User preference: add only one or two

# Maximum acceptable ETB tapped land counts per power bracket (1-5)
TAPPED_LAND_MAX_THRESHOLDS: Final[Dict[int,int]] = {
    1: 14,  # Exhibition
    2: 12,  # Core / Precon
    3: 10,  # Upgraded
    4: 8,   # Optimized
    5: 6,   # cEDH (fast mana expectations)
}

# Minimum penalty score to consider swapping (higher scores swapped first); kept for tuning
TAPPED_LAND_SWAP_MIN_PENALTY: Final[int] = 6

# Basic land floor ratio (ceil of ratio * configured basic count)
BASIC_FLOOR_FACTOR: Final[float] = 0.9

# Shared textual heuristics / keyword lists
BASIC_LAND_TYPE_KEYWORDS: Final[List[str]] = ['plains','island','swamp','mountain','forest']
ANY_COLOR_MANA_PHRASES: Final[List[str]] = [
    'add one mana of any color',
    'add one mana of any colour'
]
TAPPED_LAND_PHRASE: Final[str] = 'enters the battlefield tapped'
SHOCK_LIKE_PHRASE: Final[str] = 'you may pay 2 life'
CONDITIONAL_UNTAP_KEYWORDS: Final[List[str]] = [
    'unless you control',
    'if you control',
    'as long as you control'
]
COLORED_MANA_SYMBOLS: Final[List[str]] = ['{w}','{u}','{b}','{r}','{g}']


# Basic Lands
BASIC_LANDS = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

# Basic land mappings
COLOR_TO_BASIC_LAND: Final[Dict[str, str]] = {
    'W': 'Plains',
    'U': 'Island', 
    'B': 'Swamp',
    'R': 'Mountain',
    'G': 'Forest',
    'C': 'Wastes'
}

# Dual land type mappings
DUAL_LAND_TYPE_MAP: Final[Dict[str, str]] = {
    'azorius': 'Plains Island',
    'dimir': 'Island Swamp',
    'rakdos': 'Swamp Mountain',
    'gruul': 'Mountain Forest',
    'selesnya': 'Forest Plains',
    'orzhov': 'Plains Swamp',
    'golgari': 'Swamp Forest',
    'simic': 'Forest Island',
    'izzet': 'Island Mountain',
    'boros': 'Mountain Plains'
}

# Triple land type mappings
TRIPLE_LAND_TYPE_MAP: Final[Dict[str, str]] = {
    'bant': 'Forest Plains Island',
    'esper': 'Plains Island Swamp',
    'grixis': 'Island Swamp Mountain',
    'jund': 'Swamp Mountain Forest',
    'naya': 'Mountain Forest Plains',
    'mardu': 'Mountain Plains Swamp',
    'abzan': 'Plains Swamp Forest',
    'sultai': 'Swamp Forest Island',
    'temur': 'Forest Island Mountain',
    'jeskai': 'Island Mountain Plains'
}

# Default preference for including dual lands
DEFAULT_DUAL_LAND_ENABLED: Final[bool] = True

# Default preference for including triple lands
DEFAULT_TRIPLE_LAND_ENABLED: Final[bool] = True

SNOW_COVERED_BASIC_LANDS: Final[Dict[str, str]] = {
    'W': 'Snow-Covered Plains',
    'U': 'Snow-Covered Island',
    'B': 'Snow-Covered Swamp',
    'G': 'Snow-Covered Forest'
}

SNOW_BASIC_LAND_MAPPING: Final[Dict[str, str]] = {
    'W': 'Snow-Covered Plains',
    'U': 'Snow-Covered Island', 
    'B': 'Snow-Covered Swamp',
    'R': 'Snow-Covered Mountain',
    'G': 'Snow-Covered Forest',
    'C': 'Wastes'  # Note: No snow-covered version exists for Wastes
}

# Generic fetch lands list
GENERIC_FETCH_LANDS: Final[List[str]] = [
    'Evolving Wilds',
    'Terramorphic Expanse',
    'Shire Terrace',
    'Escape Tunnel',
    'Promising Vein',
    'Myriad Landscape',
    'Fabled Passage',
    'Terminal Moraine',
    'Prismatic Vista'
]

## Backwards compatibility: expose prior names as derived values
KINDRED_STAPLE_LANDS: Final[List[Dict[str, str]]] = [
    {'name': n, 'type': 'Land'} for n in KINDRED_LAND_NAMES
]
KINDRED_ALL_LAND_NAMES: Final[List[str]] = list(KINDRED_LAND_NAMES)

# Color-specific fetch land mappings
COLOR_TO_FETCH_LANDS: Final[Dict[str, List[str]]] = {
    'W': [
        'Flooded Strand',
        'Windswept Heath', 
        'Marsh Flats',
        'Arid Mesa',
        'Brokers Hideout',
        'Obscura Storefront',
        'Cabaretti Courtyard'
    ],
    'U': [
        'Flooded Strand',
        'Polluted Delta',
        'Scalding Tarn', 
        'Misty Rainforest',
        'Brokers Hideout',
        'Obscura Storefront',
        'Maestros Theater'
    ],
    'B': [
        'Polluted Delta',
        'Bloodstained Mire',
        'Marsh Flats',
        'Verdant Catacombs',
        'Obscura Storefront',
        'Maestros Theater',
        'Riveteers Overlook'
    ],
    'R': [
        'Bloodstained Mire',
        'Wooded Foothills',
        'Scalding Tarn',
        'Arid Mesa',
        'Maestros Theater',
        'Riveteers Overlook',
        'Cabaretti Courtyard'
    ],
    'G': [
        'Wooded Foothills',
        'Windswept Heath',
        'Verdant Catacombs',
        'Misty Rainforest',
        'Brokers Hideout',
        'Riveteers Overlook',
        'Cabaretti Courtyard'
    ]
}

# Staple land conditions mapping
STAPLE_LAND_CONDITIONS: Final[Dict[str, Callable[[List[str], List[str], int], bool]]] = {
    'Reliquary Tower': lambda commander_tags, colors, commander_power: True,  # Always include
    'Ash Barrens': lambda commander_tags, colors, commander_power: 'Landfall' not in commander_tags,
    'Command Tower': lambda commander_tags, colors, commander_power: len(colors) > 1,
    'Exotic Orchard': lambda commander_tags, colors, commander_power: len(colors) > 1,
    'War Room': lambda commander_tags, colors, commander_power: len(colors) <= 2,
    'Rogue\'s Passage': lambda commander_tags, colors, commander_power: commander_power >= 5
}

# Constants for land removal functionality
LAND_REMOVAL_MAX_ATTEMPTS: Final[int] = 3

# Protected lands that cannot be removed during land removal process
PROTECTED_LANDS: Final[List[str]] = BASIC_LANDS + KINDRED_LAND_NAMES

# Other defaults
DEFAULT_CREATURE_COUNT: Final[int] = 25  # Default number of creatures
DEFAULT_REMOVAL_COUNT: Final[int] = 10  # Default number of spot removal spells
DEFAULT_WIPES_COUNT: Final[int] = 2  # Default number of board wipes

DEFAULT_CARD_ADVANTAGE_COUNT: Final[int] = 10  # Default number of card advantage pieces
DEFAULT_PROTECTION_COUNT: Final[int] = 8  # Default number of protection spells

# Deck composition prompts
DECK_COMPOSITION_PROMPTS: Final[Dict[str, str]] = {
    'ramp': 'Enter desired number of ramp pieces (default: 8):',
    'lands': 'Enter desired number of total lands (default: 35):',
    'basic_lands': 'Enter minimum number of basic lands (default: 15):',
    'fetch_lands': 'Enter desired number of fetch lands (default: 3):',
    'creatures': 'Enter desired number of creatures (default: 25):',
    'removal': 'Enter desired number of spot removal spells (default: 10):',
    'wipes': 'Enter desired number of board wipes (default: 2):',
    'card_advantage': 'Enter desired number of card advantage pieces (default: 10):',
    'protection': 'Enter desired number of protection spells (default: 8):',
    'max_deck_price': 'Enter maximum total deck price in dollars (default: 400.0):',
    'max_card_price': 'Enter maximum price per card in dollars (default: 20.0):'
}
DEFAULT_MAX_DECK_PRICE: Final[float] = 400.0  # Default maximum total deck price
BATCH_PRICE_CHECK_SIZE: Final[int] = 50  # Number of cards to check prices for in one batch
# Constants for input validation

# Type aliases
CardName = str
CardType = str
ThemeTag = str
ColorIdentity = str
ColorList = List[str]
ColorInfo = Tuple[str, List[str], List[str]]

INPUT_VALIDATION = {
    'max_attempts': 3,
    'default_text_message': 'Please enter a valid text response.',
    'default_number_message': 'Please enter a valid number.',
    'default_confirm_message': 'Please enter Y/N or Yes/No.',
    'default_choice_message': 'Please select a valid option from the list.'
}

QUESTION_TYPES = [
    'Text',
    'Number', 
    'Confirm',
    'Choice'
]

# Constants for theme weight management and selection
# Multiplier for initial card pool size during theme-based selection
THEME_POOL_SIZE_MULTIPLIER: Final[float] = 2.0

# Bonus multiplier for cards that match multiple deck themes
THEME_PRIORITY_BONUS: Final[float] = 1.2

# Safety multiplier to avoid overshooting target counts
THEME_WEIGHT_MULTIPLIER: Final[float] = 0.9

THEME_WEIGHTS_DEFAULT: Final[Dict[str, float]] = {
    'primary': 1.0,
    'secondary': 0.6,
    'tertiary': 0.2,
    'hidden': 0.0
}

WEIGHT_ADJUSTMENT_FACTORS: Final[Dict[str, float]] = {
    'kindred_primary': 1.4,    # Boost for Kindred themes as primary
    'kindred_secondary': 1.3,  # Boost for Kindred themes as secondary
    'kindred_tertiary': 1.2,   # Boost for Kindred themes as tertiary
    'theme_synergy': 1.2       # Boost for themes that work well together
}

DEFAULT_THEME_TAGS = [
    'Aggro', 'Aristocrats', 'Artifacts Matter', 'Big Mana', 'Blink',
    'Board Wipes', 'Burn', 'Cantrips', 'Card Draw', 'Clones',
    'Combat Matters', 'Control', 'Counters Matter', 'Energy',
    'Enter the Battlefield', 'Equipment', 'Exile Matters', 'Infect',
    'Interaction', 'Lands Matter', 'Leave the Battlefield', 'Legends Matter',
    'Life Matters', 'Mill', 'Monarch', 'Protection', 'Ramp', 'Reanimate',
    'Removal', 'Sacrifice Matters', 'Spellslinger', 'Stax', 'Super Friends',
    'Theft', 'Token Creation', 'Tokens Matter', 'Voltron', 'X Spells'
]

# CSV processing configuration 
CSV_READ_TIMEOUT: Final[int] = 30  # Timeout in seconds for CSV read operations
CSV_PROCESSING_BATCH_SIZE: Final[int] = 1000  # Number of rows to process in each batch

# CSV validation configuration
CSV_VALIDATION_RULES: Final[Dict[str, Dict[str, Union[str, int, float]]]] = {
    'name': {'type': ('str', 'object'), 'required': True, 'unique': True},
    'edhrecRank': {'type': ('str', 'int', 'float', 'object'), 'min': 0, 'max': 100000},
    'manaValue': {'type': ('str', 'int', 'float', 'object'), 'min': 0, 'max': 20},
    'power': {'type': ('str', 'int', 'float', 'object'), 'pattern': r'^[\d*+-]+$'},
    'toughness': {'type': ('str', 'int', 'float', 'object'), 'pattern': r'^[\d*+-]+$'}
}

# (CSV_REQUIRED_COLUMNS imported from settings to avoid duplication)

# DataFrame processing configuration
BATCH_SIZE: Final[int] = 1000  # Number of records to process at once
DATAFRAME_BATCH_SIZE: Final[int] = 500  # Batch size for DataFrame operations
TRANSFORM_BATCH_SIZE: Final[int] = 250  # Batch size for data transformations
CSV_DOWNLOAD_TIMEOUT: Final[int] = 30  # Timeout in seconds for CSV downloads
PROGRESS_UPDATE_INTERVAL: Final[int] = 100  # Number of records between progress updates

# DataFrame operation timeouts
DATAFRAME_READ_TIMEOUT: Final[int] = 30  # Timeout for DataFrame read operations
DATAFRAME_WRITE_TIMEOUT: Final[int] = 30  # Timeout for DataFrame write operations
DATAFRAME_TRANSFORM_TIMEOUT: Final[int] = 45  # Timeout for DataFrame transformations
DATAFRAME_VALIDATION_TIMEOUT: Final[int] = 20  # Timeout for DataFrame validation

# Required DataFrame columns
DATAFRAME_REQUIRED_COLUMNS: Final[List[str]] = [
    'name', 'type', 'colorIdentity', 'manaValue', 'text',
    'edhrecRank', 'themeTags', 'keywords'
]

# DataFrame validation rules
DATAFRAME_VALIDATION_RULES: Final[Dict[str, Dict[str, Union[str, int, float, bool]]]] = {
    'name': {'type': ('str', 'object'), 'required': True, 'unique': True},
    'edhrecRank': {'type': ('str', 'int', 'float', 'object'), 'min': 0, 'max': 100000},
    'manaValue': {'type': ('str', 'int', 'float', 'object'), 'min': 0, 'max': 20},
    'power': {'type': ('str', 'int', 'float', 'object'), 'pattern': r'^[\d*+-]+$'},
    'toughness': {'type': ('str', 'int', 'float', 'object'), 'pattern': r'^[\d*+-]+$'},
    'colorIdentity': {'type': ('str', 'object'), 'required': True},
    'text': {'type': ('str', 'object'), 'required': False}
}

# Card type sorting order for organizing libraries
# This constant defines the order in which different card types should be sorted
# when organizing a deck library. The order is designed to group cards logically,
# starting with Planeswalkers and ending with Lands.
CARD_TYPE_SORT_ORDER: Final[List[str]] = [
    'Planeswalker', 'Battle', 'Creature', 'Instant', 'Sorcery',
    'Artifact', 'Enchantment', 'Land'
]

# Game changer cards, used to help determine bracket
GAME_CHANGERS: Final[List[str]] = [
    'Ad Nauseum', 'Ancient Tomb', 'Aura Shards', 'Bolas\'s Citadel', 'Braids, Cabal Minion',
    'Chrome Mox', 'Coalition Victory', 'Consecrated Sphinx', 'Crop Rotation', 'Cyclonic Rift',
    'Deflecting Swat', 'Demonic Tutor', 'Drannith Magistrate', 'Enlightened Tutor', 'Expropriate',
    'Field of the Dead', 'Fierce Guardianship', 'Food Chain', 'Force of Will', 'Gaea\'s Cradle',
    'Gamble', 'Gifts Ungiven', 'Glacial Chasm', 'Grand Arbiter Augustin IV', 'Grim Monolith', 'Humility',
    'Imperial Seal', 'Intuition', 'Jeska\'s Will', 'Jin-Gitaxias, Core Augur', 'Kinnan, Bonder Prodigy',
    'Lion\'s Eye Diamond', 'Mana Vault', 'Mishra\'s Workshop', 'Mox Diamond', 'Mystical Tutor',
    'Narset, Parter of Veils', 'Natural Order', 'Necropotence', 'Notion Thief', 'Opposition Agent',
    'Orcish Bowmasters', 'Panoptic Mirror', 'Rhystic Study', 'Seedborn Muse', 'Serra\'s Sanctum',
    'Smother Tithe', 'Survival of the Fittest', 'Sway of the Stars', 'Teferi\'s Protection',
    'Tergrid, God of Fright', 'Thassa\'s Oracle', 'The One Ring', 'The Tabernacle at Pendrell Vale',
    'Underworld Breach', 'Urza, Lord High Artificer', 'Vampiric Tutor', 'Vorinclex, Voice of Hunger',
    'Winota, Joiner of Forces', 'Worldly Tutor', 'Yuriko, the Tiger\'s Shadow'
]

# ---------------------------------------------------------------------------
# Multi-copy archetype configuration (centralized source of truth)
# ---------------------------------------------------------------------------
# Each entry describes a supported multi-copy archetype eligible for the choose-one flow.
# Fields:
# - id: machine id
# - name: card name
# - color_identity: list[str] of required color letters (subset must be in commander CI)
# - printed_cap: int | None (None means no printed cap)
# - exclusive_group: str | None (at most one from the same group)
# - triggers: { tags_any: list[str], tags_all: list[str] }
# - default_count: int (default 25)
# - rec_window: tuple[int,int] (recommendation window)
# - thrumming_stone_synergy: bool
# - type_hint: 'creature' | 'noncreature'
MULTI_COPY_ARCHETYPES: Final[dict[str, dict[str, _Any]]] = {
    'cid_timeless_artificer': {
        'id': 'cid_timeless_artificer',
        'name': 'Cid, Timeless Artificer',
        'color_identity': ['U','W'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['artificer kindred', 'hero kindred', 'artifacts matter'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'dragons_approach': {
        'id': 'dragons_approach',
        'name': "Dragon's Approach",
        'color_identity': ['R'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['burn','spellslinger','prowess','storm','copy','cascade','impulse draw','treasure','ramp','graveyard','mill','discard','recursion'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'noncreature'
    },
    'hare_apparent': {
        'id': 'hare_apparent',
        'name': 'Hare Apparent',
        'color_identity': ['W'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['rabbit kindred','tokens matter','aggro'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'slime_against_humanity': {
        'id': 'slime_against_humanity',
        'name': 'Slime Against Humanity',
        'color_identity': ['G'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['tokens','tokens matter','go-wide','exile matters','ooze kindred','spells matter','spellslinger','graveyard','mill','discard','recursion','domain','self-mill','delirium','descend'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'noncreature'
    },
    'relentless_rats': {
        'id': 'relentless_rats',
        'name': 'Relentless Rats',
        'color_identity': ['B'],
        'printed_cap': None,
        'exclusive_group': 'rats',
        'triggers': {
            'tags_any': ['rats','swarm','aristocrats','sacrifice','devotion-b','lifedrain','graveyard','recursion'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'rat_colony': {
        'id': 'rat_colony',
        'name': 'Rat Colony',
        'color_identity': ['B'],
        'printed_cap': None,
        'exclusive_group': 'rats',
        'triggers': {
            'tags_any': ['rats','swarm','aristocrats','sacrifice','devotion-b','lifedrain','graveyard','recursion'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'seven_dwarves': {
        'id': 'seven_dwarves',
        'name': 'Seven Dwarves',
        'color_identity': ['R'],
        'printed_cap': 7,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['dwarf kindred','treasure','equipment','tokens','go-wide','tribal'],
            'tags_all': []
        },
        'default_count': 7,
        'rec_window': (7,7),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'persistent_petitioners': {
        'id': 'persistent_petitioners',
        'name': 'Persistent Petitioners',
        'color_identity': ['U'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['mill','advisor kindred','control','defenders','walls','draw-go'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'shadowborn_apostle': {
        'id': 'shadowborn_apostle',
        'name': 'Shadowborn Apostle',
        'color_identity': ['B'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['demon kindred','aristocrats','sacrifice','recursion','lifedrain'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'nazgul': {
        'id': 'nazgul',
        'name': 'Nazgûl',
        'color_identity': ['B'],
        'printed_cap': 9,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['wraith kindred','ring','amass','orc','menace','aristocrats','sacrifice','devotion-b'],
            'tags_all': []
        },
        'default_count': 9,
        'rec_window': (9,9),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'tempest_hawk': {
        'id': 'tempest_hawk',
        'name': 'Tempest Hawk',
        'color_identity': ['W'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['bird kindred','aggro'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
    'templar_knight': {
        'id': 'templar_knight',
        'name': 'Templar Knight',
        'color_identity': ['W'],
        'printed_cap': None,
        'exclusive_group': None,
        'triggers': {
            'tags_any': ['aggro','human kindred','knight kindred','historic matters','artifacts matter'],
            'tags_all': []
        },
        'default_count': 25,
        'rec_window': (20,30),
        'thrumming_stone_synergy': True,
        'type_hint': 'creature'
    },
}

EXCLUSIVE_GROUPS: Final[dict[str, list[str]]] = {
    'rats': ['relentless_rats', 'rat_colony']
}

# Popular and iconic cards for fuzzy matching prioritization
POPULAR_CARDS: Final[set[str]] = {
    # Most played removal spells
    'Lightning Bolt', 'Swords to Plowshares', 'Path to Exile', 'Counterspell',
    'Assassinate', 'Murder', 'Go for the Throat', 'Fatal Push', 'Doom Blade',
    'Naturalize', 'Disenchant', 'Beast Within', 'Chaos Warp', 'Generous Gift',
    'Anguished Unmaking', 'Vindicate', 'Putrefy', 'Terminate', 'Abrupt Decay',
    
    # Board wipes
    'Wrath of God', 'Day of Judgment', 'Damnation', 'Pyroclasm', 'Anger of the Gods',
    'Supreme Verdict', 'Austere Command', 'Cyclonic Rift', 'Toxic Deluge',
    'Blasphemous Act', 'Starstorm', 'Earthquake', 'Hurricane', 'Pernicious Deed',
    
    # Card draw engines
    'Rhystic Study', 'Mystic Remora', 'Phyrexian Arena', 'Necropotence',
    'Sylvan Library', 'Consecrated Sphinx', 'Mulldrifter', 'Divination',
    'Sign in Blood', 'Night\'s Whisper', 'Harmonize', 'Concentrate',
    'Mind Spring', 'Stroke of Genius', 'Blue Sun\'s Zenith', 'Pull from Tomorrow',
    
    # Ramp spells
    'Sol Ring', 'Rampant Growth', 'Cultivate', 'Kodama\'s Reach', 'Farseek',
    'Nature\'s Lore', 'Three Visits', 'Sakura-Tribe Elder', 'Wood Elves',
    'Farhaven Elf', 'Solemn Simulacrum', 'Commander\'s Sphere', 'Arcane Signet',
    'Talisman of Progress', 'Talisman of Dominance', 'Talisman of Indulgence',
    'Talisman of Impulse', 'Talisman of Unity', 'Fellwar Stone', 'Mind Stone',
    'Thought Vessel', 'Worn Powerstone', 'Thran Dynamo', 'Gilded Lotus',
    
    # Tutors
    'Demonic Tutor', 'Vampiric Tutor', 'Mystical Tutor', 'Enlightened Tutor',
    'Worldly Tutor', 'Survival of the Fittest', 'Green Sun\'s Zenith',
    'Chord of Calling', 'Natural Order', 'Idyllic Tutor', 'Steelshaper\'s Gift',
    
    # Protection
    'Counterspell', 'Negate', 'Swan Song', 'Dispel', 'Force of Will',
    'Force of Negation', 'Fierce Guardianship', 'Deflecting Swat',
    'Teferi\'s Protection', 'Heroic Intervention', 'Boros Charm', 'Simic Charm',
    
    # Value creatures
    'Eternal Witness', 'Snapcaster Mage', 'Mulldrifter', 'Acidic Slime',
    'Reclamation Sage', 'Wood Elves', 'Farhaven Elf', 'Solemn Simulacrum',
    'Oracle of Mul Daya', 'Azusa, Lost but Seeking', 'Ramunap Excavator',
    'Courser of Kruphix', 'Titania, Protector of Argoth', 'Avenger of Zendikar',
    
    # Planeswalkers
    'Jace, the Mind Sculptor', 'Liliana of the Veil', 'Elspeth, Sun\'s Champion',
    'Chandra, Torch of Defiance', 'Garruk Wildspeaker', 'Ajani, Mentor of Heroes',
    'Teferi, Hero of Dominaria', 'Vraska, Golgari Queen', 'Domri, Anarch of Bolas',
    
    # Combo pieces
    'Thassa\'s Oracle', 'Laboratory Maniac', 'Jace, Wielder of Mysteries',
    'Demonic Consultation', 'Tainted Pact', 'Ad Nauseam', 'Angel\'s Grace',
    'Underworld Breach', 'Brain Freeze', 'Gaea\'s Cradle', 'Cradle of Vitality',
    
    # Equipment
    'Lightning Greaves', 'Swiftfoot Boots', 'Sword of Fire and Ice',
    'Sword of Light and Shadow', 'Sword of Feast and Famine', 'Umezawa\'s Jitte',
    'Skullclamp', 'Cranial Plating', 'Bonesplitter', 'Loxodon Warhammer',
    
    # Enchantments
    'Rhystic Study', 'Smothering Tithe', 'Phyrexian Arena', 'Sylvan Library',
    'Mystic Remora', 'Necropotence', 'Doubling Season', 'Parallel Lives',
    'Cathars\' Crusade', 'Impact Tremors', 'Purphoros, God of the Forge',
    
    # Artifacts (Commander-legal only)
    'Sol Ring', 'Mana Vault', 'Chrome Mox', 'Mox Diamond',
    'Lotus Petal', 'Lion\'s Eye Diamond', 'Sensei\'s Divining Top',
    'Scroll Rack', 'Aetherflux Reservoir', 'Bolas\'s Citadel', 'The One Ring',
    
    # Lands
    'Command Tower', 'Exotic Orchard', 'Reflecting Pool', 'City of Brass',
    'Mana Confluence', 'Forbidden Orchard', 'Ancient Tomb', 'Reliquary Tower',
    'Bojuka Bog', 'Strip Mine', 'Wasteland', 'Ghost Quarter', 'Tectonic Edge',
    'Maze of Ith', 'Kor Haven', 'Riptide Laboratory', 'Academy Ruins',
    
    # Multicolored staples
    'Lightning Helix', 'Electrolyze', 'Fire // Ice', 'Terminate', 'Putrefy',
    'Vindicate', 'Anguished Unmaking', 'Abrupt Decay', 'Maelstrom Pulse',
    'Sphinx\'s Revelation', 'Cruel Ultimatum', 'Nicol Bolas, Planeswalker',
    
    # Token generators
    'Avenger of Zendikar', 'Hornet Queen', 'Tendershoot Dryad', 'Elspeth, Sun\'s Champion',
    'Secure the Wastes', 'White Sun\'s Zenith', 'Decree of Justice', 'Empty the Warrens',
    'Goblin Rabblemaster', 'Siege-Gang Commander', 'Krenko, Mob Boss',
}

ICONIC_CARDS: Final[set[str]] = {
    # Classic and iconic Magic cards that define the game (Commander-legal only)
    
    # Foundational spells
    'Lightning Bolt', 'Counterspell', 'Swords to Plowshares', 'Dark Ritual',
    'Giant Growth', 'Wrath of God', 'Fireball', 'Control Magic', 'Terror',
    'Disenchant', 'Regrowth', 'Brainstorm', 'Force of Will', 'Wasteland',
    
    # Iconic creatures
    'Tarmogoyf', 'Delver of Secrets', 'Snapcaster Mage', 'Dark Confidant',
    'Psychatog', 'Morphling', 'Shivan Dragon', 'Serra Angel', 'Llanowar Elves',
    'Birds of Paradise', 'Noble Hierarch', 'Deathrite Shaman', 'True-Name Nemesis',
    
    # Game-changing planeswalkers
    'Jace, the Mind Sculptor', 'Liliana of the Veil', 'Elspeth, Knight-Errant',
    'Chandra, Pyromaster', 'Garruk Wildspeaker', 'Ajani Goldmane',
    'Nicol Bolas, Planeswalker', 'Karn Liberated', 'Ugin, the Spirit Dragon',
    
    # Combo enablers and engines
    'Necropotence', 'Yawgmoth\'s Will', 'Show and Tell', 'Natural Order',
    'Survival of the Fittest', 'Earthcraft', 'Squirrel Nest', 'High Tide',
    'Reset', 'Time Spiral', 'Wheel of Fortune', 'Memory Jar', 'Windfall',
    
    # Iconic artifacts
    'Sol Ring', 'Mana Vault', 'Winter Orb', 'Static Orb', 'Sphere of Resistance',
    'Trinisphere', 'Chalice of the Void', 'Null Rod', 'Stony Silence',
    'Crucible of Worlds', 'Sensei\'s Divining Top', 'Scroll Rack', 'Skullclamp',
    
    # Powerful lands
    'Strip Mine', 'Mishra\'s Factory', 'Maze of Ith', 'Gaea\'s Cradle',
    'Serra\'s Sanctum', 'Cabal Coffers', 'Urborg, Tomb of Yawgmoth',
    'Fetchlands', 'Dual Lands', 'Shock Lands', 'Check Lands',
    
    # Magic history and format-defining cards
    'Mana Drain', 'Daze', 'Ponder', 'Preordain', 'Path to Exile',
    'Dig Through Time', 'Treasure Cruise', 'Gitaxian Probe', 'Cabal Therapy',
    'Thoughtseize', 'Hymn to Tourach', 'Chain Lightning', 'Price of Progress',
    'Stoneforge Mystic', 'Bloodbraid Elf', 'Vendilion Clique', 'Cryptic Command',
    
    # Commander format staples
    'Command Tower', 'Rhystic Study', 'Cyclonic Rift', 'Demonic Tutor',
    'Vampiric Tutor', 'Mystical Tutor', 'Enlightened Tutor', 'Worldly Tutor',
    'Eternal Witness', 'Solemn Simulacrum', 'Consecrated Sphinx', 'Avenger of Zendikar',
}
