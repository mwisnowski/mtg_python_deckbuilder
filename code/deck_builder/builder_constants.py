from typing import Dict, List, Final, Tuple, Union, Callable
from settings import CARD_DATA_COLUMNS as CSV_REQUIRED_COLUMNS  # unified

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
COMMANDER_CSV_PATH: Final[str] = 'csv_files/commander_cards.csv'
DECK_DIRECTORY = '../deck_files'
COMMANDER_CONVERTERS: Final[Dict[str, str]] = {'themeTags': ast.literal_eval, 'creatureTypes': ast.literal_eval}  # CSV loading converters
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

# Kindred land constants
KINDRED_STAPLE_LANDS: Final[List[Dict[str, str]]] = [
    {
        'name': 'Path of Ancestry',
        'type': 'Land'
    },
    {
        'name': 'Three Tree City',
        'type': 'Legendary Land'
    },
    {'name': 'Cavern of Souls', 'type': 'Land'}
]

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
PROTECTED_LANDS: Final[List[str]] = BASIC_LANDS + [land['name'] for land in KINDRED_STAPLE_LANDS]

# Other defaults
DEFAULT_CREATURE_COUNT: Final[int] = 35  # Default number of creatures
DEFAULT_REMOVAL_COUNT: Final[int] = 10  # Default number of spot removal spells
DEFAULT_WIPES_COUNT: Final[int] = 2  # Default number of board wipes

DEFAULT_CARD_ADVANTAGE_COUNT: Final[int] = 10  # Default number of card advantage pieces
DEFAULT_PROTECTION_COUNT: Final[int] = 8  # Default number of protection spells

# Deck composition prompts
DECK_COMPOSITION_PROMPTS: Final[Dict[str, str]] = {
    'ramp': 'Enter desired number of ramp pieces (default: 8):',
    'lands': 'Enter desired number of total lands (default: 35):',
    'basic_lands': 'Enter minimum number of basic lands (default: 15):',
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