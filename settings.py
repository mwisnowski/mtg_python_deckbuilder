artifact_tokens = ['Blood', 'Clue', 'Food', 'Gold', 'Incubator',
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

board_wipe_tags = ['destroy all', 'destroy each', 'return all', 'return each', 'deals damage to each',
                'exile all', 'exile each', 'creatures get -X/-X', 'sacrifices all', 'sacrifices each',
                'sacrifices the rest']

card_types = ['Artifact','Creature', 'Enchantment', 'Instant', 'Land', 'Planeswalker', 'Sorcery',
              'Kindred', 'Dungeon', 'Battle']

csv_directory = 'csv_files'

colors = ['colorless', 'white', 'blue', 'black', 'red', 'green',
                'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
                'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
                'bant', 'esper', 'grixis', 'jund', 'naya',
                'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
                'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg',
                'commander']

counter_types = ['+0/+1', '+0/+2', '+1/+0', '+1/+2', '+2/+0', '+2/+2',
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
                       'Rat Colony','Relentless Rars', 'Seven Dwarves', 'Shadowborn Apostle',
                       'Slime Against Humanity', 'Templar Knights']

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
