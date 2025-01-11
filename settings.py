from typing import List, Dict, Union, Final, Tuple, Pattern
import ast

# Commander selection configuration
COMMANDER_CSV_PATH: Final[str] = 'csv_files/commander_cards.csv'
FUZZY_MATCH_THRESHOLD: Final[int] = 90  # Threshold for fuzzy name matching
MAX_FUZZY_CHOICES: Final[int] = 5  # Maximum number of fuzzy match choices
COMMANDER_CONVERTERS: Final[Dict[str, str]] = {'themeTags': ast.literal_eval, 'creatureTypes': ast.literal_eval}  # CSV loading converters

# Commander-related constants
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

# Price checking configuration
DEFAULT_PRICE_DELAY: Final[float] = 0.1  # Delay between price checks in seconds
MAX_PRICE_CHECK_ATTEMPTS: Final[int] = 3  # Maximum attempts for price checking
PRICE_CACHE_SIZE: Final[int] = 128  # Size of price check LRU cache
PRICE_CHECK_TIMEOUT: Final[int] = 30  # Timeout for price check requests in seconds
PRICE_TOLERANCE_MULTIPLIER: Final[float] = 1.1  # Multiplier for price tolerance
DEFAULT_MAX_CARD_PRICE: Final[float] = 20.0  # Default maximum price per card
DEFAULT_MAX_DECK_PRICE: Final[float] = 400.0  # Default maximum total deck price
BATCH_PRICE_CHECK_SIZE: Final[int] = 50  # Number of cards to check prices for in one batch

# Type aliases
CardName = str
CardType = str
ThemeTag = str
ColorIdentity = str
ColorList = List[str]
ColorInfo = Tuple[str, List[str], List[str]]

# Token configuration
artifact_tokens: List[str] = ['Blood', 'Clue', 'Food', 'Gold', 'Incubator',
                'Junk','Map','Powerstone', 'Treasure']

banned_cards: List[str] = [# in commander
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

# DataFrame validation configuration
MIN_EDHREC_RANK: int = 0
MAX_EDHREC_RANK: int = 100000
MIN_MANA_VALUE: int = 0
MAX_MANA_VALUE: int = 20

# Constants for lands matter functionality
LANDS_MATTER_PATTERNS: Dict[str, List[str]] = {
    'land_play': [
        'play a land',
        'play an additional land', 
        'play two additional lands',
        'play lands from',
        'put a land card',
        'put a basic land card'
    ],
    'land_search': [
        'search your library for a basic land card',
        'search your library for a land card',
        'search your library for up to two basic land',
        'search their library for a basic land card'
    ],
    'land_state': [
        'land enters',
        'land card is put into your graveyard',
        'number of lands you control',
        'one or more land cards',
        'sacrifice a land',
        'target land'
    ]
}

DOMAIN_PATTERNS: Dict[str, List[str]] = {
    'keyword': ['domain'],
    'text': ['basic land types among lands you control']
}

LANDFALL_PATTERNS: Dict[str, List[str]] = {
    'keyword': ['landfall'],
    'triggers': [
        'whenever a land enters the battlefield under your control',
        'when a land enters the battlefield under your control'
    ]
}

LANDWALK_PATTERNS: Dict[str, List[str]] = {
    'basic': [
        'plainswalker',
        'islandwalk',
        'swampwalk', 
        'mountainwalk',
        'forestwalk'
    ],
    'nonbasic': [
        'nonbasic landwalk',
        'landwalk'
    ]
}

LAND_TYPES: List[str] = [
    # Basic lands
    'Plains', 'Island', 'Swamp', 'Mountain', 'Forest',
    # Special lands 
    'Cave', 'Desert', 'Gate', 'Lair', 'Locus', 'Mine',
    'Power-Plant', 'Sphere', 'Tower', 'Urza\'s'
]

LANDS_MATTER_SPECIFIC_CARDS: List[str] = [
    'Abundance',
    'Archdruid\'s Charm', 
    'Archelos, Lagoon Mystic',
    'Catacylsmic Prospecting',
    'Coiling Oracle',
    'Disorienting Choice', 
    'Eerie Ultimatum',
    'Gitrog Monster',
    'Mana Reflection',
    'Nahiri\'s Lithoforming',
    'Nine-fingers Keene',
    'Open the Way',
    'Realms Uncharted',
    'Reshape the Earth',
    'Scapeshift',
    'Yarok, the Desecrated',
    'Wonderscape Sage'
]

# Constants for topdeck manipulation
TOPDECK_TEXT_PATTERNS: List[str] = [
    'from the top',
    'look at the top',
    'reveal the top', 
    'scries',
    'surveils',
    'top of your library',
    'you scry',
    'you surveil'
]

TOPDECK_KEYWORDS: List[str] = [
    'Miracle',
    'Scry',
    'Surveil'
]

TOPDECK_SPECIFIC_CARDS: List[str] = [
    'Aminatou, the Fateshifter',
    'Brainstorm',
    'Counterbalance',
    'Delver of Secrets',
    'Jace, the Mind Sculptor',
    'Lantern of Insight',
    'Melek, Izzet Paragon',
    'Mystic Forge',
    'Sensei\'s Divining Top',
    'Soothsaying',
    'Temporal Mastery',
    'Vampiric Tutor'
]

TOPDECK_EXCLUSION_PATTERNS: List[str] = [
    'from the top of target player\'s library',
    'from the top of their library',
    'look at the top card of target player\'s library',
    'reveal the top card of target player\'s library'
]


# Constants for aristocrats functionality
ARISTOCRAT_TEXT_PATTERNS: List[str] = [
    'another creature dies',
    'creature dies',
    'creature dying',
    'creature you control dies', 
    'creature you own dies',
    'dies this turn',
    'dies, create',
    'dies, draw',
    'dies, each opponent',
    'dies, exile',
    'dies, put',
    'dies, return',
    'dies, sacrifice',
    'dies, you',
    'has blitz',
    'have blitz',
    'permanents were sacrificed',
    'sacrifice a creature',
    'sacrifice another',
    'sacrifice another creature',
    'sacrifice a nontoken',
    'sacrifice a permanent',
    'sacrifice another nontoken',
    'sacrifice another permanent',
    'sacrifice another token',
    'sacrifices a creature',
    'sacrifices another',
    'sacrifices another creature',
    'sacrifices another nontoken',
    'sacrifices another permanent',
    'sacrifices another token',
    'sacrifices a nontoken',
    'sacrifices a permanent',
    'sacrifices a token',
    'when this creature dies',
    'whenever a food',
    'whenever you sacrifice'
]

ARISTOCRAT_SPECIFIC_CARDS: List[str] = [
    'Ashnod, Flesh Mechanist',
    'Blood Artist',
    'Butcher of Malakir',
    'Chatterfang, Squirrel General',
    'Cruel Celebrant',
    'Dictate of Erebos',
    'Endrek Sahr, Master Breeder',
    'Gisa, Glorious Resurrector',
    'Grave Pact',
    'Grim Haruspex',
    'Judith, the Scourge Diva',
    'Korvold, Fae-Cursed King',
    'Mayhem Devil',
    'Midnight Reaper',
    'Mikaeus, the Unhallowed',
    'Pitiless Plunderer',
    'Poison-Tip Archer',
    'Savra, Queen of the Golgari',
    'Sheoldred, the Apocalypse',
    'Syr Konrad, the Grim',
    'Teysa Karlov',
    'Viscera Seer',
    'Yawgmoth, Thran Physician',
    'Zulaport Cutthroat'
]

ARISTOCRAT_EXCLUSION_PATTERNS: List[str] = [
    'blocking enchanted',
    'blocking it',
    'blocked by',
    'end the turn',
    'from your graveyard',
    'from your hand',
    'from your library',
    'into your hand'
]

# Constants for stax functionality
STAX_TEXT_PATTERNS: List[str] = [
    'an opponent controls'
    'can\'t attack',
    'can\'t be cast', 
    'can\'t be activated',
    'can\'t cast spells',
    'can\'t enter',
    'can\'t search',
    'can\'t untap',
    'don\'t untap',
    'don\'t cause abilities',
    'each other player\'s',
    'each player\'s upkeep',
    'opponent would search',
    'opponents cast cost',
    'opponents can\'t',
    'opponents control',
    'opponents control can\'t',
    'opponents control enter tapped',
    'spells cost {1} more',
    'spells cost {2} more',
    'spells cost {3} more',
    'spells cost {4} more',
    'spells cost {5} more',
    'that player doesn\'t',
    'unless that player pays',
    'you control your opponent',
    'you gain protection'
]

STAX_SPECIFIC_CARDS: List[str] = [
    'Archon of Emeria',
    'Drannith Magistrate',
    'Ethersworn Canonist', 
    'Grand Arbiter Augustin IV',
    'Hokori, Dust Drinker',
    'Kataki, War\'s Wage',
    'Lavinia, Azorius Renegade',
    'Leovold, Emissary of Trest',
    'Magus of the Moon',
    'Narset, Parter of Veils',
    'Opposition Agent',
    'Rule of Law',
    'Sanctum Prelate',
    'Thalia, Guardian of Thraben',
    'Winter Orb'
]

STAX_EXCLUSION_PATTERNS: List[str] = [
    'blocking enchanted',
    'blocking it',
    'blocked by',
    'end the turn',
    'from your graveyard',
    'from your hand',
    'from your library',
    'into your hand'
]

# Constants for removal functionality
REMOVAL_TEXT_PATTERNS: List[str] = [
    'destroy target',
    'destroys target',
    'exile target',
    'exiles target',
    'sacrifices target',
    'return target.*to.*hand',
    'returns target.*to.*hand'
]

REMOVAL_SPECIFIC_CARDS: List[str] = []

REMOVAL_EXCLUSION_PATTERNS: List[str] = []

REMOVAL_KEYWORDS: List[str] = []

# Constants for counterspell functionality
COUNTERSPELL_TEXT_PATTERNS: List[str] = [
    'control counters a',
    'counter target',
    'counter that spell',
    'counter all',
    'counter each',
    'counter the next',
    'counters a spell',
    'counters target',
    'return target spell',
    'exile target spell',
    'counter unless',
    'unless its controller pays'
]

COUNTERSPELL_SPECIFIC_CARDS: List[str] = [
    'Arcane Denial',
    'Counterspell',
    "Dovin's Veto",
    'Force of Will',
    'Mana Drain',
    'Mental Misstep',
    'Mindbreak Trap',
    'Mystic Confluence',
    'Pact of Negation',
    'Swan Song'
]

COUNTERSPELL_EXCLUSION_PATTERNS: List[str] = [
    'counter on',
    'counter from',
    'remove a counter',
    'move a counter',
    'distribute counter',
    'proliferate'
]

# Constants for theft functionality
THEFT_TEXT_PATTERNS: List[str] = [
    'cast a spell you don\'t own',
    'cast but don\'t own',
    'cost to cast this spell, sacrifice',
    'control but don\'t own',
    'exile top of target player\'s library',
    'exile top of each player\'s library',
    'gain control of',
    'target opponent\'s library',
    'that player\'s library',
    'you control enchanted creature'
]

THEFT_SPECIFIC_CARDS: List[str] = [
    'Adarkar Valkyrie',
    'Captain N\'gathrod',
    'Hostage Taker',
    'Siphon Insight',
    'Thief of Sanity',
    'Xanathar, Guild Kingpin',
    'Zara, Renegade Recruiter'
]

# Constants for big mana functionality
BIG_MANA_TEXT_PATTERNS: List[str] = [
    'add {w}{u}{b}{r}{g}',
    'card onto the battlefield',
    'control with power [3-5] or greater',
    'creature with power [3-5] or greater',
    'double the power',
    'from among them onto the battlefield',
    'from among them without paying',
    'hand onto the battlefield',
    'mana, add one mana',
    'mana, it produces twice',
    'mana, it produces three',
    'mana, its controller adds',
    'pay {w}{u}{b}{r}{g}',
    'spell with power 5 or greater',
    'value [5-7] or greater',
    'you may cast it without paying'
]

BIG_MANA_SPECIFIC_CARDS: List[str] = [
    'Akroma\'s Memorial',
    'Apex Devastator',
    'Apex of Power',
    'Brass\'s Bounty',
    'Cabal Coffers',
    'Caged Sun',
    'Doubling Cube',
    'Forsaken Monument',
    'Guardian Project',
    'Mana Reflection',
    'Nyxbloom Ancient',
    'Omniscience',
    'One with the Multiverse',
    'Portal to Phyrexia',
    'Vorinclex, Voice of Hunger'
]

BIG_MANA_KEYWORDS: List[str] = [
    'Cascade',
    'Convoke',
    'Discover',
    'Emerge',
    'Improvise',
    'Surge'
]

# Constants for board wipe effects
BOARD_WIPE_TEXT_PATTERNS: List[str] = {
    'mass_destruction': [
        'destroy all',
        'destroy each',
        'destroy the rest',
        'destroys all',
        'destroys each',
        'destroys the rest'
    ],
    'mass_exile': [
        'exile all',
        'exile each',
        'exile the rest',
        'exiles all',
        'exiles each',
        'exiles the rest'
    ],
    'mass_bounce': [
        'return all',
        'return each',
        'put all creatures',
        'returns all',
        'returns each',
        'puts all creatures'
    ],
    'mass_sacrifice': [
        'sacrifice all',
        'sacrifice each',
        'sacrifice the rest',
        'sacrifices all',
        'sacrifices each',
        'sacrifices the rest'
    ],
    'mass_damage': [
        'deals damage to each',
        'deals damage to all',
        'deals X damage to each',
        'deals X damage to all',
        'deals that much damage to each',
        'deals that much damage to all'
    ]
}

BOARD_WIPE_SPECIFIC_CARDS: List[str] = [
    'Akroma\'s Vengeance',
    'All Is Dust',
    'Austere Command',
    'Blasphemous Act',
    'Cleansing Nova',
    'Cyclonic Rift',
    'Damnation',
    'Day of Judgment',
    'Decree of Pain',
    'Devastation Tide',
    'Evacuation',
    'Extinction Event',
    'Farewell',
    'Hour of Devastation',
    'In Garruk\'s Wake',
    'Living Death',
    'Living End',
    'Merciless Eviction',
    'Nevinyrral\'s Disk',
    'Oblivion Stone',
    'Planar Cleansing',
    'Ravnica at War',
    'Shatter the Sky',
    'Supreme Verdict',
    'Terminus',
    'Time Wipe',
    'Toxic Deluge',
    'Vanquish the Horde',
    'Wrath of God'
]

BOARD_WIPE_EXCLUSION_PATTERNS: List[str] = [
    'blocking enchanted',
    'blocking it',
    'blocked by',
    'end the turn',
    'from your graveyard',
    'from your hand',
    'from your library',
    'into your hand',
    'target player\'s library',
    'that player\'s library'
]

# Card type constants
CARD_TYPES: Final[List[str]] = ['Artifact','Creature', 'Enchantment', 'Instant', 'Land', 'Planeswalker', 'Sorcery',
                        'Kindred', 'Dungeon', 'Battle']

BASIC_LANDS: Final[List[str]] = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

# Color identity constants and mappings
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

# Color identity validation patterns
COLOR_IDENTITY_PATTERNS: Final[Dict[str, str]] = {
    'mono': r'^[WUBRG]$',
    'dual': r'^[WUBRG], [WUBRG]$',
    'tri': r'^[WUBRG], [WUBRG], [WUBRG]$',
    'four': r'^[WUBRG], [WUBRG], [WUBRG], [WUBRG]$',
    'five': r'^[WUBRG], [WUBRG], [WUBRG], [WUBRG], [WUBRG]$'
}

COLORS: Final[List[str]] = ['colorless', 'white', 'blue', 'black', 'red', 'green',
                'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
                'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
                'bant', 'esper', 'grixis', 'jund', 'naya',
                'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
                'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg',
                'commander']
COLOR_ABBREVIATIONS: Final[List[str]] = ['Colorless', 'W', 'U', 'B', 'R', 'G',
                'U, W', 'B, W', 'G, W', 'R, W', 'B, U',
                'G, U', 'R, U', 'B, G', 'B, R', 'G, R',
                'G, U, W', 'B, U, W', 'B, R, U', 'B, G, R', 'G, R, W',
                'B, G, W', 'R, U, W', 'B, R, W', 'B, G, U', 'G, R, U',
                'B, G, R, W', 'B, G, R, U', 'G, R, U, W', 'B, G, U, W',
                'B, R, U, W', 'B, G, R, U, W']

# Mapping of card types to their corresponding theme tags
TYPE_TAG_MAPPING: Dict[str, List[str]] = {
    'Artifact': ['Artifacts Matter'],
    'Battle': ['Battles Matter'],
    #'Creature': [],
    'Enchantment': ['Enchantments Matter'],
    'Equipment': ['Equipment', 'Voltron'],
    'Aura': ['Auras', 'Voltron'],
    'Instant': ['Spells Matter', 'Spellslinger'],
    'Land': ['Lands Matter'],
    'Planeswalker': ['Superfriends'],
    'Sorcery': ['Spells Matter', 'Spellslinger']
}

# File system configuration
# Directory for storing CSV files
CSV_DIRECTORY: Final[str] = 'csv_files'  # Path to CSV storage directory

# Counter types and tokens
counter_types: List[str] = [r'\+0/\+1', r'\+0/\+2', r'\+1/\+0', r'\+1/\+2', r'\+2/\+0', r'\+2/\+2',
                '-0/-1', '-0/-2', '-1/-0', '-1/-2', '-2/-0', '-2/-2',
                'Acorn', 'Aegis', 'Age', 'Aim', 'Arrow', 'Arrowhead','Awakening',
                'Bait', 'Blaze', 'Blessing', 'Blight',' Blood', 'Bloddline',
                'Bloodstain', 'Book', 'Bounty', 'Brain', 'Bribery', 'Brick',
                'Burden', 'Cage', 'Carrion', 'Charge', 'Coin', 'Collection',
                'Component', 'Contested', 'Corruption', 'CRANK!', 'Credit',
                'Croak', 'Corpse', 'Crystal', 'Cube', 'Currency', 'Death',
                'Defense', 'Delay', 'Depletion', 'Descent', 'Despair', 'Devotion',
                'Divinity', 'Doom', 'Dream', 'Duty', 'Echo', 'Egg', 'Elixir',
                'Ember', 'Energy', 'Enlightened', 'Eon', 'Eruption', 'Everything',
                'Experience', 'Eyeball', 'Eyestalk', 'Fade', 'Fate', 'Feather',
                'Feeding', 'Fellowship', 'Fetch', 'Filibuster', 'Finality', 'Flame',
                'Flood', 'Foreshadow', 'Fungus', 'Fury', 'Fuse', 'Gem', 'Ghostform',
                'Glpyh', 'Gold', 'Growth', 'Hack', 'Harmony', 'Hatching', 'Hatchling',
                'Healing', 'Hit', 'Hope',' Hone', 'Hoofprint', 'Hour', 'Hourglass',
                'Hunger', 'Ice', 'Imposter', 'Incarnation', 'Incubation', 'Infection',
                'Influence', 'Ingenuity', 'Intel', 'Intervention', 'Invitation',
                'Isolation', 'Javelin', 'Judgment', 'Keyword', 'Ki', 'Kick',
                'Knickknack', 'Knowledge', 'Landmark', 'Level', 'Loot', 'Lore',
                'Loyalty', 'Luck', 'Magnet', 'Manabond', 'Manifestation', 'Mannequin',
                'Mask', 'Matrix', 'Memory', 'Midway', 'Mine', 'Mining', 'Mire',
                'Music', 'Muster', 'Necrodermis', 'Nest', 'Net', 'Night', 'Oil',
                'Omen', 'Ore', 'Page', 'Pain', 'Palliation', 'Paralyzing', 'Pause',
                'Petal', 'Petrification', 'Phyresis', 'Phylatery', 'Pin', 'Plague',
                'Plot', 'Point', 'Poison', 'Polyp', 'Possession', 'Pressure', 'Prey',
                'Pupa', 'Quest', 'Rad', 'Rejection', 'Reprieve', 'Rev', 'Revival',
                'Ribbon', 'Ritual', 'Rope', 'Rust', 'Scream', 'Scroll', 'Shell',
                'Shield', 'Silver', 'Shred', 'Sleep', 'Sleight', 'Slime', 'Slumber',
                'Soot', 'Soul', 'Spark', 'Spite', 'Spore', 'Stash', 'Storage',
                'Story', 'Strife', 'Study', 'Stun', 'Supply', 'Suspect', 'Takeover',
                'Task', 'Ticket', 'Tide', 'Time', 'Tower', 'Training', 'Trap',
                'Treasure', 'Unity', 'Unlock', 'Valor', 'Velocity', 'Verse',
                'Vitality', 'Void', 'Volatile', 'Vortex', 'Vow', 'Voyage', 'Wage',
                'Winch', 'Wind', 'Wish']

creature_types: List[str] = ['Advisor', 'Aetherborn', 'Alien', 'Ally', 'Angel', 'Antelope', 'Ape', 'Archer', 'Archon', 'Armadillo',
                'Army', 'Artificer', 'Assassin', 'Assembly-Worker', 'Astartes', 'Atog', 'Aurochs', 'Automaton',
                'Avatar', 'Azra', 'Badger', 'Balloon', 'Barbarian', 'Bard', 'Basilisk', 'Bat', 'Bear', 'Beast', 'Beaver',
                'Beeble', 'Beholder', 'Berserker', 'Bird', 'Blinkmoth', 'Boar', 'Brainiac', 'Bringer', 'Brushwagg',
                'C\'tan', 'Camarid', 'Camel', 'Capybara', 'Caribou', 'Carrier', 'Cat', 'Centaur', 'Chicken', 'Child',
                'Chimera', 'Citizen', 'Cleric', 'Clown', 'Cockatrice', 'Construct', 'Coward', 'Coyote', 'Crab', 'Crocodile',
                'Custodes', 'Cyberman', 'Cyclops', 'Dalek', 'Dauthi', 'Demigod', 'Demon', 'Deserter', 'Detective', 'Devil',
                'Dinosaur', 'Djinn', 'Doctor', 'Dog', 'Dragon', 'Drake', 'Dreadnought', 'Drone', 'Druid', 'Dryad', 'Dwarf',
                'Efreet', 'Egg', 'Elder', 'Eldrazi', 'Elemental', 'Elephant', 'Elf', 'Elk', 'Employee', 'Eye', 'Faerie',
                'Ferret', 'Fish', 'Flagbearer', 'Fox', 'Fractal', 'Frog', 'Fungus', 'Gamer', 'Gargoyle', 'Germ', 'Giant',
                'Gith', 'Glimmer', 'Gnoll', 'Gnome', 'Goat', 'Goblin', 'God', 'Golem', 'Gorgon', 'Graveborn', 'Gremlin',
                'Griffin', 'Guest', 'Hag', 'Halfling', 'Hamster', 'Harpy', 'Head', 'Hellion', 'Hero', 'Hippo', 'Hippogriff',
                'Homarid', 'Homunculus', 'Hornet', 'Horror', 'Horse', 'Human', 'Hydra', 'Hyena', 'Illusion', 'Imp',
                'Incarnation', 'Inkling', 'Inquisitor', 'Insect', 'Jackal', 'Jellyfish', 'Juggernaut', 'Kavu', 'Kirin',
                'Kithkin', 'Knight', 'Kobold', 'Kor', 'Kraken', 'Lamia', 'Lammasu', 'Leech', 'Leviathan', 'Lhurgoyf',
                'Licid', 'Lizard', 'Manticore', 'Masticore', 'Mercenary', 'Merfolk', 'Metathran', 'Minion', 'Minotaur',
                'Mite', 'Mole', 'Monger', 'Mongoose', 'Monk', 'Monkey', 'Moonfolk', 'Mount', 'Mouse', 'Mutant', 'Myr',
                'Mystic', 'Naga', 'Nautilus', 'Necron', 'Nephilim', 'Nightmare', 'Nightstalker', 'Ninja', 'Noble', 'Noggle',
                'Nomad', 'Nymph', 'Octopus', 'Ogre', 'Ooze', 'Orb', 'Orc', 'Orgg', 'Otter', 'Ouphe', 'Ox', 'Oyster', 'Pangolin',
                'Peasant', 'Pegasus', 'Pentavite', 'Performer', 'Pest', 'Phelddagrif', 'Phoenix', 'Phyrexian', 'Pilot',
                'Pincher', 'Pirate', 'Plant', 'Porcupine', 'Possum', 'Praetor', 'Primarch', 'Prism', 'Processor', 'Rabbit',
                'Raccoon', 'Ranger', 'Rat', 'Rebel', 'Reflection', 'Reveler', 'Rhino', 'Rigger', 'Robot', 'Rogue', 'Rukh',
                'Sable', 'Salamander', 'Samurai', 'Sand', 'Saproling', 'Satyr', 'Scarecrow', 'Scientist', 'Scion', 'Scorpion',
                'Scout', 'Sculpture', 'Serf', 'Serpent', 'Servo', 'Shade', 'Shaman', 'Shapeshifter', 'Shark', 'Sheep', 'Siren',
                'Skeleton', 'Skunk', 'Slith', 'Sliver', 'Sloth', 'Slug', 'Snail', 'Snake', 'Soldier', 'Soltari', 'Spawn',
                'Specter', 'Spellshaper', 'Sphinx', 'Spider', 'Spike', 'Spirit', 'Splinter', 'Sponge', 'Spy', 'Squid',
                'Squirrel', 'Starfish', 'Surrakar', 'Survivor', 'Synth', 'Teddy', 'Tentacle', 'Tetravite', 'Thalakos',
                'Thopter', 'Thrull', 'Tiefling', 'Time Lord', 'Toy', 'Treefolk', 'Trilobite', 'Triskelavite', 'Troll',
                'Turtle', 'Tyranid', 'Unicorn', 'Urzan', 'Vampire', 'Varmint', 'Vedalken', 'Volver', 'Wall', 'Walrus',
                'Warlock', 'Warrior', 'Wasp', 'Weasel', 'Weird', 'Werewolf', 'Whale', 'Wizard', 'Wolf', 'Wolverine', 'Wombat',
                'Worm', 'Wraith', 'Wurm', 'Yeti', 'Zombie', 'Zubera']

enchantment_tokens: List[str] = ['Cursed Role', 'Monster Role', 'Royal Role', 'Sorcerer Role',
                'Virtuous Role', 'Wicked Role', 'Young Hero Role', 'Shard']

multiple_copy_cards: List[str] = ['Dragon\'s Approach', 'Hare Apparent', 'Nazgûl', 'Persistent Petitioners',
                       'Rat Colony', 'Relentless Rats', 'Seven Dwarves', 'Shadowborn Apostle',
                       'Slime Against Humanity', 'Templar Knight']

non_creature_types: List[str] = ['Legendary', 'Creature', 'Enchantment', 'Artifact',
                'Battle', 'Sorcery', 'Instant', 'Land', '-', '—',
                'Blood', 'Clue', 'Food', 'Gold', 'Incubator',
                'Junk', 'Map', 'Powerstone', 'Treasure',
                'Equipment', 'Fortification', 'vehicle',
                'Bobblehead', 'Attraction', 'Contraption',
                'Siege',
                'Aura', 'Background', 'Saga', 'Role', 'Shard',
                'Cartouche', 'Case', 'Class', 'Curse', 'Rune',
                'Shrine',
                'Plains', 'Island', 'Swamp', 'Forest', 'Mountain',
                'Cave', 'Desert', 'Gate', 'Lair', 'Locus', 'Mine',
                'Power-Plant', 'Sphere', 'Tower', 'Urza\'s']

num_to_search: List[str] = ['a', 'an', 'one', '1', 'two', '2', 'three', '3', 'four','4', 'five', '5',
                'six', '6', 'seven', '7', 'eight', '8', 'nine', '9', 'ten', '10',
                'x','one or more']

theme_tags: List[str] = ['+1/+1 counter', 'one or more counters', 'token', 'gain life', 'one or more creature tokens',
                'creature token', 'treasure', 'create token', 'draw a card', 'flash', 'choose a creature type',
                'play land', 'artifact you control enters', 'enchantment you control enters', 'poison counter',
                'from graveyard', 'mana value', 'from exile', 'mana of any color', 'attacks', 'total power',
                'greater than starting life', 'lose life', 'whenever you sacrifice', 'creature dying',
                'creature enters', 'creature leaves', 'creature dies', 'put into graveyard', 'sacrifice',
                'sacrifice creature', 'sacrifice artifact', 'sacrifice another creature', '-1/-1 counter',
                'control get +1/+1', 'control dies', 'experience counter', 'triggered ability', 'token',
                'commit a crime']

targetted_removal_tags: List[str] = ['exile target', 'destroy target', 'return target', 'shuffles target', 'you control',
                'deals damage to target', 'loses all abilities']

triggers: List[str] = ['when', 'whenever', 'at']

# Constants for draw-related functionality
DRAW_RELATED_TAGS: List[str] = [
    'Card Draw',          # General card draw effects
    'Conditional Draw',   # Draw effects with conditions/triggers
    'Cycling',           # Cycling and similar discard-to-draw effects
    'Life to Draw',      # Draw effects that require paying life
    'Loot',              # Draw + discard effects
    'Replacement Draw',   # Effects that modify or replace draws
    'Sacrifice to Draw', # Draw effects requiring sacrificing permanents
    'Unconditional Draw' # Pure card draw without conditions
]

# Text patterns that exclude cards from being tagged as unconditional draw
DRAW_EXCLUSION_PATTERNS: List[str] = [
    'annihilator',  # Eldrazi mechanic that can match 'draw' patterns
    'ravenous',     # Keyword that can match 'draw' patterns
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

# Column mapping configurations
DATAFRAME_COLUMN_MAPS: Final[Dict[str, Dict[str, str]]] = {
    'creature': {
        'name': 'Card Name',
        'type': 'Card Type',
        'manaCost': 'Mana Cost',
        'manaValue': 'Mana Value',
        'power': 'Power',
        'toughness': 'Toughness'
    },
    'spell': {
        'name': 'Card Name', 
        'type': 'Card Type',
        'manaCost': 'Mana Cost',
        'manaValue': 'Mana Value'
    },
    'land': {
        'name': 'Card Name',
        'type': 'Card Type'
    }
}

# Required DataFrame columns
DATAFRAME_REQUIRED_COLUMNS: Final[List[str]] = [
    'name', 'type', 'colorIdentity', 'manaValue', 'text',
    'edhrecRank', 'themeTags', 'keywords'
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
# Required columns for CSV validation
CSV_REQUIRED_COLUMNS: Final[List[str]] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

# Default values for missing CSV data
CSV_DEFAULT_VALUES: Final[Dict[str, Union[str, int, List[str]]]] = {
    'faceName': '',
    'edhrecRank': 99999,
    'colorIdentity': '',
    'colors': [],
    'manaCost': '',
    'manaValue': 0,
    'type': '',
    'creatureTypes': '',
    'text': '',
    'power': '',
    'toughness': '',
    'keywords': [],
    'themeTags': [],
    'layout': 'normal',
    'side': ''
}
DEFAULT_THEME_TAGS: List[str] = [
    'Aggro', 'Aristocrats', 'Artifacts Matter', 'Big Mana', 'Blink',
    'Board Wipes', 'Burn', 'Cantrips', 'Card Draw', 'Clones',
    'Combat Matters', 'Control', 'Counters Matter', 'Energy',
    'Enter the Battlefield', 'Equipment', 'Exile Matters', 'Infect',
    'Interaction', 'Lands Matter', 'Leave the Battlefield', 'Legends Matter',
    'Life Matters', 'Mill', 'Monarch', 'Protection', 'Ramp', 'Reanimate',
    'Removal', 'Sacrifice Matters', 'Spellslinger', 'Stax', 'Super Friends',
    'Theft', 'Token Creation', 'Tokens Matter', 'Voltron', 'X Spells'
]

COLUMN_ORDER: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'text', 'power', 'toughness',
    'keywords', 'layout', 'side', 'availability', 'promoTypes',
    'securityStamp'
]

PRETAG_COLUMN_ORDER: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'text', 'power', 'toughness',
    'keywords', 'layout', 'side'
]

TAGGED_COLUMN_ORDER: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

EXCLUDED_CARD_TYPES: List[str] = ['Plane —', 'Conspiracy', 'Vanguard', 'Scheme',
                       'Phenomenon', 'Stickers', 'Attraction', 'Hero',
                       'Contraption']

# Constants for type detection and processing
OUTLAW_TYPES: List[str] = ['Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock']
TYPE_DETECTION_BATCH_SIZE: int = 1000

# Aura-related constants
AURA_SPECIFIC_CARDS: List[str] = [
    'Ardenn, Intrepid Archaeologist',   # Aura movement
    'Calix, Guided By Fate',            # Create duplicate Auras
    'Gilwain, Casting Director',        # Creates role tokens
    'Ivy, Gleeful Spellthief',          # Copies spells that have single target
    'Killian, Ink Duelist',             # Targetted spell cost reduction
]

# Equipment-related constants
EQUIPMENT_EXCLUSIONS: List[str] = [
    'Bruenor Battlehammer',         # Equipment cost reduction
    'Nazahn, Revered Bladesmith',   # Equipment tutor
    'Stonehewer Giant',             # Equipment tutor
]

EQUIPMENT_SPECIFIC_CARDS: List[str] = [
    'Ardenn, Intrepid Archaeologist',   # Equipment movement
    'Armory Automaton',                 # Mass equip ability
    'Brass Squire',                     # Free equip ability
    'Danitha Capashen, Paragon',        # Equipment cost reduction
    'Halvar, God of Battle',            # Equipment movement
    'Kemba, Kha Regent',                # Equipment payoff
    'Kosei, Penitent Warlord',          # Wants to be eequipped
    'Puresteel Paladin',                # Equipment draw engine
    'Reyav, Master Smith',              # Equipment combat boost
    'Sram, Senior Edificer',            # Equipment card draw
    'Valduk, Keeper of the Flame'       # Equipment token creation
]

EQUIPMENT_RELATED_TAGS: List[str] = [
    'Equipment',           # Base equipment tag
    'Equipment Matters',   # Cards that care about equipment
    'Voltron',             # Commander-focused equipment strategy
    'Artifacts Matter',    # Equipment are artifacts
    'Warriors Matter',     # Common equipment tribal synergy
    'Knights Matter'       # Common equipment tribal synergy
]

EQUIPMENT_TEXT_PATTERNS: List[str] = [
    'attach',           # Equipment attachment
    'equip',            # Equipment keyword
    'equipped',         # Equipment state
    'equipment',        # Equipment type
    'unattach',         # Equipment removal
    'unequip',          # Equipment removal
]

TYPE_DETECTION_BATCH_SIZE: int = 1000

# Constants for Voltron strategy
VOLTRON_COMMANDER_CARDS: List[str] = [
    'Akiri, Line-Slinger',
    'Ardenn, Intrepid Archaeologist',
    'Bruna, Light of Alabaster',
    'Danitha Capashen, Paragon',
    'Greven, Predator Captain',
    'Halvar, God of Battle',
    'Kaldra Compleat',
    'Kemba, Kha Regent',
    'Light-Paws, Emperor\'s Voice',
    'Nahiri, the Lithomancer',
    'Rafiq of the Many',
    'Reyav, Master Smith',
    'Rograkh, Son of Rohgahh',
    'Sram, Senior Edificer',
    'Syr Gwyn, Hero of Ashvale',
    'Tiana, Ship\'s Caretaker',
    'Uril, the Miststalker',
    'Valduk, Keeper of the Flame',
    'Wyleth, Soul of Steel'
]

VOLTRON_PATTERNS: List[str] = [
    'attach',
    'aura you control',
    'enchant creature',
    'enchanted creature',
    'equipped creature',
    'equipment you control',
    'fortify',
    'living weapon',
    'reconfigure'
]