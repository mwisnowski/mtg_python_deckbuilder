"""Constants and configuration settings for the MTG Python Deckbuilder.

This module contains all the constant values and configuration settings used throughout
the application for card filtering, processing, and analysis. Constants are organized
into logical sections with clear documentation.

All constants are properly typed according to PEP 484 standards to ensure type safety
and enable static type checking with mypy.
"""

from typing import Dict, List, Optional

artifact_tokens: List[str] = ['Blood', 'Clue', 'Food', 'Gold', 'Incubator',
                'Junk','Map','Powerstone', 'Treasure']

banned_cards = [# in commander
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

basic_lands = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']
basic_lands = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

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

DOMAIN_PATTERNS = {
    'keyword': ['domain'],
    'text': ['basic land types among lands you control']
}

LANDFALL_PATTERNS = {
    'keyword': ['landfall'],
    'triggers': [
        'whenever a land enters the battlefield under your control',
        'when a land enters the battlefield under your control'
    ]
}

LANDWALK_PATTERNS = {
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

LAND_TYPES = [
    # Basic lands
    'Plains', 'Island', 'Swamp', 'Mountain', 'Forest',
    # Special lands 
    'Cave', 'Desert', 'Gate', 'Lair', 'Locus', 'Mine',
    'Power-Plant', 'Sphere', 'Tower', 'Urza\'s'
]

LANDS_MATTER_SPECIFIC_CARDS = [
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
TOPDECK_TEXT_PATTERNS = [
    'from the top',
    'look at the top',
    'reveal the top', 
    'scries',
    'surveils',
    'top of your library',
    'you scry',
    'you surveil'
]

TOPDECK_KEYWORDS = [
    'Miracle',
    'Scry',
    'Surveil'
]

TOPDECK_SPECIFIC_CARDS = [
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

TOPDECK_EXCLUSION_PATTERNS = [
    'from the top of target player\'s library',
    'from the top of their library',
    'look at the top card of target player\'s library',
    'reveal the top card of target player\'s library'
]

# Constants for stax functionality

# Constants for aristocrats functionality
ARISTOCRAT_TEXT_PATTERNS = [
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

ARISTOCRAT_SPECIFIC_CARDS = [
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

ARISTOCRAT_EXCLUSION_PATTERNS = [
    'blocking enchanted',
    'blocking it',
    'blocked by',
    'end the turn',
    'from your graveyard',
    'from your hand',
    'from your library',
    'into your hand'
]
STAX_TEXT_PATTERNS = [
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

STAX_SPECIFIC_CARDS = [
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

STAX_EXCLUSION_PATTERNS = [
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
REMOVAL_TEXT_PATTERNS = [
    'destroy target',
    'destroys target',
    'exile target',
    'exiles target',
    'sacrifices target',
    'return target.*to.*hand',
    'returns target.*to.*hand'
]

REMOVAL_SPECIFIC_CARDS = [] # type: list

REMOVAL_EXCLUSION_PATTERNS = [] # type: list

REMOVAL_KEYWORDS = [] # type: list

# Constants for counterspell functionality
COUNTERSPELL_TEXT_PATTERNS = [
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

COUNTERSPELL_SPECIFIC_CARDS = [
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

COUNTERSPELL_EXCLUSION_PATTERNS = [
    'counter on',
    'counter from',
    'remove a counter',
    'move a counter',
    'distribute counter',
    'proliferate'
]

# Constants for theft functionality
THEFT_TEXT_PATTERNS = [
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

THEFT_SPECIFIC_CARDS = [
    'Adarkar Valkyrie',
    'Captain N\'gathrod',
    'Hostage Taker',
    'Siphon Insight',
    'Thief of Sanity',
    'Xanathar, Guild Kingpin',
    'Zara, Renegade Recruiter'
]

# Constants for big mana functionality
BIG_MANA_TEXT_PATTERNS = [
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

BIG_MANA_SPECIFIC_CARDS = [
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

BIG_MANA_KEYWORDS = [
    'Cascade',
    'Convoke',
    'Discover',
    'Emerge',
    'Improvise',
    'Surge'
]

# Constants for board wipe effects
BOARD_WIPE_TEXT_PATTERNS = {
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

BOARD_WIPE_SPECIFIC_CARDS = [
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

BOARD_WIPE_EXCLUSION_PATTERNS = [
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


card_types = ['Artifact','Creature', 'Enchantment', 'Instant', 'Land', 'Planeswalker', 'Sorcery',
              'Kindred', 'Dungeon', 'Battle']

# Mapping of card types to their corresponding theme tags
TYPE_TAG_MAPPING = {
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

csv_directory = 'csv_files'

colors = ['colorless', 'white', 'blue', 'black', 'red', 'green',
                'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
                'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
                'bant', 'esper', 'grixis', 'jund', 'naya',
                'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
                'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg',
                'commander']

counter_types = [r'\+0/\+1', r'\+0/\+2', r'\+1/\+0', r'\+1/\+2', r'\+2/\+0', r'\+2/\+2',
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

creature_types = ['Advisor', 'Aetherborn', 'Alien', 'Ally', 'Angel', 'Antelope', 'Ape', 'Archer', 'Archon', 'Armadillo',
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

enchantment_tokens = ['Cursed Role', 'Monster Role', 'Royal Role', 'Sorcerer Role',
                'Virtuous Role', 'Wicked Role', 'Young Hero Role', 'Shard']

multiple_copy_cards = ['Dragon\'s Approach', 'Hare Apparent', 'Nazgûl', 'Persistent Petitioners',
                       'Rat Colony', 'Relentless Rats', 'Seven Dwarves', 'Shadowborn Apostle',
                       'Slime Against Humanity', 'Templar Knight']

non_creature_types = ['Legendary', 'Creature', 'Enchantment', 'Artifact',
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

num_to_search = ['a', 'an', 'one', '1', 'two', '2', 'three', '3', 'four','4', 'five', '5',
                'six', '6', 'seven', '7', 'eight', '8', 'nine', '9', 'ten', '10',
                'x','one or more']

theme_tags = ['+1/+1 counter', 'one or more counters', 'token', 'gain life', 'one or more creature tokens',
                'creature token', 'treasure', 'create token', 'draw a card', 'flash', 'choose a creature type',
                'play land', 'artifact you control enters', 'enchantment you control enters', 'poison counter',
                'from graveyard', 'mana value', 'from exile', 'mana of any color', 'attacks', 'total power',
                'greater than starting life', 'lose life', 'whenever you sacrifice', 'creature dying',
                'creature enters', 'creature leaves', 'creature dies', 'put into graveyard', 'sacrifice',
                'sacrifice creature', 'sacrifice artifact', 'sacrifice another creature', '-1/-1 counter',
                'control get +1/+1', 'control dies', 'experience counter', 'triggered ability', 'token',
                'commit a crime']

targetted_removal_tags = ['exile target', 'destroy target', 'return target', 'shuffles target', 'you control',
                'deals damage to target', 'loses all abilities']

triggers = ['when', 'whenever', 'at']

# Constants for draw-related functionality
DRAW_RELATED_TAGS = [
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
DRAW_EXCLUSION_PATTERNS = [
    'annihilator',  # Eldrazi mechanic that can match 'draw' patterns
    'ravenous',     # Keyword that can match 'draw' patterns
]

# Constants for DataFrame validation and processing
REQUIRED_COLUMNS: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

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

COLUMN_ORDER = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

# Constants for type detection and processing
OUTLAW_TYPES = ['Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock']
TYPE_DETECTION_BATCH_SIZE = 1000

# Aura-related constants
AURA_SPECIFIC_CARDS = [
    'Ardenn, Intrepid Archaeologist',   # Aura movement
    'Calix, Guided By Fate',            # Create duplicate Auras
    'Gilwain, Casting Director',        # Creates role tokens
    'Ivy, Gleeful Spellthief',          # Copies spells that have single target
    'Killian, Ink Duelist',             # Targetted spell cost reduction
]
# Equipment-related constants
EQUIPMENT_EXCLUSIONS = [
    'Bruenor Battlehammer',         # Equipment cost reduction
    'Nazahn, Revered Bladesmith',   # Equipment tutor
    'Stonehewer Giant',             # Equipment tutor
]

EQUIPMENT_SPECIFIC_CARDS = [
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

EQUIPMENT_RELATED_TAGS = [
    'Equipment',           # Base equipment tag
    'Equipment Matters',   # Cards that care about equipment
    'Voltron',             # Commander-focused equipment strategy
    'Artifacts Matter',    # Equipment are artifacts
    'Warriors Matter',     # Common equipment tribal synergy
    'Knights Matter'       # Common equipment tribal synergy
]

EQUIPMENT_TEXT_PATTERNS = [
    'attach',           # Equipment attachment
    'equip',            # Equipment keyword
    'equipped',         # Equipment state
    'equipment',        # Equipment type
    'unattach',         # Equipment removal
    'unequip',          # Equipment removal
]
TYPE_DETECTION_BATCH_SIZE = 1000

# Constants for Voltron strategy
VOLTRON_COMMANDER_CARDS = [
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

VOLTRON_PATTERNS = [
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

# Constants for setup and CSV processing
MTGJSON_API_URL = 'https://mtgjson.com/api/v5/csv/cards.csv'

LEGENDARY_OPTIONS = [
    'Legendary Creature',
    'Legendary Artifact',
    'Legendary Artifact Creature', 
    'Legendary Enchantment Creature',
    'Legendary Planeswalker'
]

NON_LEGAL_SETS = [
    'PHTR', 'PH17', 'PH18', 'PH19', 'PH20', 'PH21',
    'UGL', 'UND', 'UNH', 'UST'
]

CARD_TYPES_TO_EXCLUDE = [
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
CSV_PROCESSING_COLUMNS = [
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

SETUP_COLORS = ['colorless', 'white', 'blue', 'black', 'green', 'red',
          'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
          'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
          'bant', 'esper', 'grixis', 'jund', 'naya',
          'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
          'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg']

COLOR_ABRV = ['Colorless', 'W', 'U', 'B', 'G', 'R',
              'U, W', 'B, W', 'G, W', 'R, W', 'B, U',
              'G, U', 'R, U', 'B, G', 'B, R', 'G, R',
              'G, U, W', 'B, U, W', 'B, R, U', 'B, G, R', 'G, R, W',
              'B, G, W', 'R, U, W', 'B, R, W', 'B, G, U', 'G, R, U',
              'B, G, R, W', 'B, G, R, U', 'G, R, U, W', 'B, G, U, W',
              'B, R, U, W', 'B, G, R, U, W']

# Configuration for handling null/NA values in DataFrame columns
FILL_NA_COLUMNS: Dict[str, Optional[str]] = {
    'colorIdentity': 'Colorless',  # Default color identity for cards without one
    'faceName': None  # Use card's name column value when face name is not available
}
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