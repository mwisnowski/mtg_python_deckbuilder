banned_cards = ['Ancestral Recall', 'Balance', 'Biorhythm', 'Black Lotus',
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
                'Trade Secrets', 'Upheaval', 'Yawgmoth\'s Bargain']

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

theme_tags = ['+1/+1 counter', 'one or more counters', 'tokens', 'gain life', 'one or more creature tokens',
              'creature token', 'treasure', 'create token', 'draw a card', 'flash', 'choose a creature type',
              'play land', 'artifact you control enters', 'enchantment you control enters', 'poison counter',
              'from graveyard', 'mana value', 'from exile', 'mana of any color', 'attacks', 'total power',
              'greater than starting life', 'lose life', 'whenever you sacrifice', 'creature dying',
              'creature enters', 'creature leaves', 'creature dies', 'put into graveyard', 'sacrifice',
              'sacricifice creature', 'sacrifice artifact', 'sacrifice another creature', '-1/-1 counter',
              'control get +1/+1', 'control dies', 'experience counter', 'triggered ability', 'token']

board_wipe_tags = ['destroy all', 'destroy each', 'return all', 'return each', 'deals damage to each',
                   'exile all', 'exile each', 'creatures get -X/-X', 'sacrifices all', 'sacrifices each',
                   'sacrifices the rest']
targetted_removal_tags = ['exile target', 'destroy target', 'return target', 'shuffles target', 'you control',
                          'deals damage to target','loses all abilities']