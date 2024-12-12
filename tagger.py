from __future__ import annotations

#import inquirer.prompt # type: ignore
import keyboard # type: ignore
import pandas as pd # type: ignore
#import pprint # type: ignore
#import random

#from fuzzywuzzy import fuzz, process # type: ignore

import settings
import setup

colors = ['colorless', 'white', 'blue', 'black', 'green', 'red',
          'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
          'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
          'bant', 'esper', 'grixis', 'jund', 'naya',
          'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
          'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg',
          'legendary']
num_to_search = ['a', 'one', '1', 'two', '2', 'three', '3', 'four','4', 'five', '5',
                 'six', '6', 'seven', '7', 'eight', '8', 'nine', '9', 'ten', '10',
                 'x','one or more']
triggered = ['when', 'whenever', 'at']
artifact_tokens = ['Blood', 'Clue', 'Food', 'Gold', 'Incubator',
                   'Junk','Map','Powerstone', 'Treasure']
enchantment_tokens = ['Cursed Role', 'Monster Role', 'Royal Role', 'Sorcerer Role',
                      'Virtuous Role', 'Wicked Role', 'Young Hero Role', 'Shard']
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

csv_directory = 'csv_files'

karnstruct = '0/0 colorless Construct'

def pluralize(word):
    if word.endswith('y'):
        return word[:-1] + 'ies'
    elif word.endswith(('s', 'sh', 'ch', 'x', 'z')):
        return word + 'es'
    elif word.endswith(('f')):
        return word[:-1] + 'ves'
    else:
        return word + 's'

def sort_list(list_to_sort):
    if isinstance(list_to_sort, list):
        print(list_to_sort)
        list_to_sort = sorted(list_to_sort)
        print(list_to_sort)
        return list_to_sort
    else:
        return list_to_sort
    
# Determine any non-creature cards that have creature types mentioned
def kindred_tagging():
    for color in colors:
        print(f'Settings creature type tags on {color}_cards.csv.\n')
        # Setup dataframe
        try:
            df = pd.read_csv(f'csv_files/{color}_cards.csv')
        except FileNotFoundError:
            setup.regenerate_csvs()
        df['creatureTypes'] = [[] for _ in range(len(df))]
        
        # Set creature types
        print(f'Checking for and setting creature types in {color}_cards.csv')
        for index, row in df.iterrows():
            if 'Creature' in row['type']:
                kindred_tags = []
                creature_types = row['type']
                split_types = creature_types.split()
                for creature_type in split_types:
                    if creature_type not in settings.non_creature_types:
                        if creature_type not in kindred_tags:
                            kindred_tags.append(creature_type)
                            df.at[index, 'creatureTypes'] = kindred_tags
        print(f'Creature types set in {color}_cards.csv.\n')
                        
        # Set outlaws
        print(f'Checking for and setting Outlaw types in {color}_cards.csv')
        outlaws = ['Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock']
        for index, row in df.iterrows():
            if 'Creature' in row['type']:
                kindred_tags = row['creatureTypes']
                creature_types = kindred_tags
                for creature_type in creature_types:
                    if creature_type in outlaws:
                        if 'Outlaw' not in kindred_tags:
                            kindred_tags.append('Outlaw')
                            df.at[index, 'creatureTypes'] = kindred_tags
        print(f'Outlaw types set in {color}_cards.csv.\n')

        # Check for creature types in text (i.e. how 'Voja, Jaws of the Conclave' cares about Elves)
        print(f'Checking for and setting creature types found in the text of cards in {color}_cards.csv')
        for index, row in df.iterrows():
            
            """if pd.isna(row['creatureTypes']):
                row['creatureTypes'] = []"""
            kindred_tags = row['creatureTypes']
            if pd.isna(row['text']):
                continue
            for creature_type in settings.creature_types:
                if ('Elite Inquisitor' in row['name']
                    or 'Breaker of Armies' in row['name']
                    or 'Cleopatra, Exiled Pharaoh' in row['name']
                    or 'Nath\'s Buffoon' in row['name']):
                    continue
                if creature_type in row['name']:
                    continue
                if pluralize(f'{creature_type}') in row['name']:
                    continue
                if creature_type in row['text']:
                    if creature_type not in row['name']:
                        if creature_type not in kindred_tags:
                            kindred_tags.append(creature_type)
                            if creature_type in outlaws:
                                kindred_tags.append(creature_type)
                            df.at[index, 'creatureTypes'] = kindred_tags
                if pluralize(f'{creature_type}') in row['text']:
                    if pluralize(f'{creature_type}') not in row['name']:
                        if creature_type not in kindred_tags:
                            kindred_tags.append(creature_type)
                            if creature_type in outlaws:
                                kindred_tags.append(creature_type)
                            df.at[index, 'creatureTypes'] = kindred_tags
        print(f'Creature types from text set in {color}_cards.csv.\n')
        
        # Overwrite file with creature type tags
        columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords']
        df = df[columns_to_keep]
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Creature types tagged on {color}_cards.csv.\n')

def setup_tags():
    # Create a blank column for theme/effect tags
    # This will setup a basis for future tagging to automate deck building
    for color in colors:
        print(f'Creating theme/effect tag column for {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv')
        df['themeTags'] = [[] for _ in range(len(df))]
        columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags']
        df = df[columns_to_keep]
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Theme/effect tag column created on {color}_cards.csv.\n')
    
def add_creatures_to_tags():
    for color in colors:
        print(f'Adding creature types to theme tags in {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            kindred_tags = row['creatureTypes']
            
            
            for kindred_tag in kindred_tags:
                if kindred_tag not in theme_tags:
                    theme_tags.extend([f'{kindred_tag} Kindred'])
        
        # Overwrite file with kindred tags added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Adding creature types to theme tags in {color}_cards.csv.')

def sort_theme_tags():
    for color in colors:
        print(f'Alphabetically sorting theme tags in {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        df['themeTags'] = df['themeTags'].apply(sorted)
        
        columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags']
        df = df[columns_to_keep]
        df.to_csv(f'csv_files/{color}_cards.csv', index=sorted)
        print(f'Theme tags alphabetically sorted in {color}_cards.csv.\n')

def tag_for_sacrifice_to_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for sacrifice to draw cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Basic logic for the cards
            if ('as an additional cost to cast this spell, sacrifice' in row['text'].lower()):
                # Sacrific to draw
                for num in num_to_search:
                    if (f'draw {num} card' in row['text'].lower()):
                        if 'Sacrifice to Draw' not in theme_tags and 'Card Draw' not in theme_tags:
                            theme_tags.extend(['Sacrifice to Draw', 'Card Draw'])
                            df.at[index, 'themeTags'] = theme_tags
            a_or_an = ['a', 'an']
            for which_one in a_or_an:
                if (f'sacrifice {which_one} creature: draw a card' in row['text'].lower()
                    or f'sacrifice {which_one} artifact: draw a card' in row['text'].lower()):
                    kind_of_draw = ['Sacrifice to Draw', 'Card Draw']
                    for which_draw in kind_of_draw:
                        if which_draw not in theme_tags:
                            theme_tags.extend([which_draw])
                            df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with connive tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Sacrifice to draw cards tagged in {color}_cards.csv.\n')

def tag_for_pay_life_to_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for pay life to draw card effects:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Basic logic for the cards
            if ('life: draw' in row['text'].lower()):
                # Sacrific to draw
                for num in num_to_search:
                    if (f'draw {num} card' in row['text'].lower()):
                        kind_of_draw = ['Life to Draw', 'Card Draw']
                        for which_draw in kind_of_draw:
                            if which_draw not in theme_tags:
                                theme_tags.extend([which_draw])
                                df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with connive tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Pay life to draw cards tagged in {color}_cards.csv.\n')

def tag_for_connive():
    for color in colors:
        print(f'Checking {color}_cards.csv for connive cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})

        # Set connive tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            # Logic for Connive cards
            #print('Checking for Connive cards:')
            if ('connive' in row['text'].lower() or 'connives' in row['text'].lower()):
                kind_of_draw = ['Connive', 'Loot', 'Card Draw']
                for which_draw in kind_of_draw:
                    if which_draw not in theme_tags:
                        theme_tags.extend([which_draw])
                        df.at[index, 'themeTags'] = theme_tags

        # Overwrite file with connive tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_cycling():
    for color in colors:
        print(f'Checking {color}_cards.csv for cycling cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set cycling tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
                    
            # Logic for cycling cards
            # print('Checking for Cycling cards.')
            if ('cycling' in row['text'].lower()):
                kind_of_draw = ['cycling','Loot', 'Card Draw']
                for which_draw in kind_of_draw:
                    if which_draw not in theme_tags:
                        theme_tags.extend([which_draw])
                        df.at[index, 'themeTags'] = theme_tags

        # Overwrite file with cycling tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_loot():
    for color in colors:
        print(f'Checking {color}_cards.csv for loot cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Standard loot effects
        print('Checking for standard loot effects.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
                    
            # Looting logic
            if ('Cycling' in theme_tags or 'Connive' in theme_tags or 'blood token' in row['text'].lower()):
                continue
            for num in num_to_search:
                if (f'draw {num} card' in row['text'].lower()):
                    if ('then discard' in row['text'].lower()
                        or 'if you do, discard' in row['text'].lower()
                        or 'discard the rest' in row['text'].lower()
                        or 'for each card drawn this way, discard' in row['text'].lower()):
                        kind_of_draw = ['Loot', 'Card Draw']
                        for which_draw in kind_of_draw:
                            if which_draw not in theme_tags:
                                theme_tags.extend([which_draw])
                                df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with loot tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_imprint():
    for color in colors:
        print(f'Checking {color}_cards.csv for imprint cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Check for imprint effects
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('imprint' in row['text'].lower()):
                if 'Imprint' not in theme_tags:
                    theme_tags.extend(['Imprint'])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with creature type tags
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Impulse cards tagged in {color}_cards.csv.\n')

def tag_for_impulse():
    for color in colors:
        print(f'Checking {color}_cards.csv for impulse cards:')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Check for impulse effects
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            if ('possibility storm' in row['name'].lower()
                or 'ragava, nimble pilferer' in row['name'].lower()
                or 'stolen strategy' in row['name'].lower()
                or 'urabrask, heretic praetor' in row['name'].lower()
                or 'valakut exploration' in row['name'].lower()
                or 'wild wasteland' in row['name'].lower()
                or 'daxos of meletis' in row['name'].lower()
                or 'bloodsoaked insight' in row['name'].lower()
                or 'florian, voldaren scion' in row['name'].lower()
                or 'rakdos, the muscle' in row['name'].lower()):
                if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                    theme_tags.append('Impulse')
                    df.at[index, 'themeTags'] = theme_tags
            if ('raid' not in row['text'].lower()
                or 'planeswalker' not in row['type'].lower()
                or 'deals combat damage' not in row['text'].lower()
                or 'damage to target' not in row['text'].lower()
                or 'damage to each' not in row['text'].lower()
                or 'target opponent\'s hand' not in row['text'].lower()):
                if ('morph' in row['text'].lower()
                    or 'you may look at the top card' in row['text'].lower()
                    or 'opponent\'s library' in row['text'].lower()
                    or 'skip your draw' in row['text'].lower()
                    or 'target opponent' in row['text'].lower()
                    or 'that player\'s' in row['text'].lower()
                    or 'each opponent' in row['text'].lower()):
                    continue
            if ('exile the top'in row['text'].lower()
                or 'exiles the top' in row['text'].lower()
                ):
                if ('may play' in row['text'].lower()
                    or 'may cast' in row['text'].lower()):
                    if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                        theme_tags.append('Impulse')
                        df.at[index, 'themeTags'] = theme_tags
            if ('junk token' in row['text'].lower()):
                if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                    theme_tags.append('Impulse')
                    df.at[index, 'themeTags'] = theme_tags
            
        # Overwrite file with creature type tags 
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Impulse cards tagged in {color}_cards.csv.\n')

def tag_for_conditional_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for conditional card draw effects.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Cycling' in theme_tags
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                ):
                continue
            if ('relic vial' in row['name'].lower()
                or 'vexing bauble' in row['name'].lower()
                or 'whenever you draw a card' in row['text'].lower()
                ):
                continue
            for trigger in triggered:
                if (f'{trigger} an opponent' in row['text'].lower()
                or (f'{trigger} {row['name']} attacks'.lower() in row['text'].lower())
                or f'{trigger} a player' in row['text'].lower()
                or f'{trigger} you' in row['text'].lower()
                or f'{trigger} a creature' in row['text'].lower()
                or f'{trigger} another creature' in row['text'].lower()
                or f'{trigger} one or more creatures' in row['text'].lower()
                or f'{trigger} one or more other creatures' in row['text'].lower()
                or f'{trigger} a permanent' in row['text'].lower()
                or f'{trigger} enchanted player' in row['text'].lower()
                or 'created a token' in row['text'].lower()
                or 'draw a card for each' in row['text'].lower()
                ):
                    for num in num_to_search:
                        if (f'draw {num} card' in row['text'].lower()):
                            kind_of_draw = ['Conditional Draw', 'Card Draw']
                            for which_draw in kind_of_draw:
                                if which_draw not in theme_tags:
                                    theme_tags.extend([which_draw])
                                    df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with Conditional Draw tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Conditional draw cards tagged in {color}_cards.csv.\n')

def tag_for_replacement_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for replacement card draw effects.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Cycling' in theme_tags
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                or 'Conditional Draw' in theme_tags
                ):
                continue
            
            if 'skips that turn instead' in row['text'].lower():
                continue
            
            for trigger in triggered:
                if (f'{trigger} an opponent' in row['text'].lower()
                    or f'{trigger} a player' in row['text'].lower()
                    or f'{trigger} you' in row['text'].lower()
                    or 'if you would' in row['text'].lower()
                    or 'if a player would' in row['text'].lower()
                    or 'if an opponent would' in row['text'].lower()
                    or f'{trigger} the beginning of your draw step' in row['text'].lower()
                    ):
                    if 'instead' in row['text'].lower():
                        for num in num_to_search:
                            if (f'draw {num} card' in row['text'].lower()):
                                kind_of_draw = ['Replacement Draw', 'Card Draw']
                                for which_draw in kind_of_draw:
                                    if which_draw not in theme_tags:
                                        theme_tags.extend([which_draw])
                                        df.at[index, 'themeTags'] = theme_tags
            
            if ('sylvan library' in row['name'].lower()
                ):
                if 'Replacement Draw' not in theme_tags:
                    theme_tags.extend(['Replacement Draw'])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with Conditional Draw tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Replacement draw cards tagged in {color}_cards.csv.\n')
        
def tag_for_card_draw():
    tag_for_connive()
    tag_for_cycling()
    tag_for_loot()
    tag_for_imprint()
    tag_for_impulse()
    tag_for_sacrifice_to_draw()
    tag_for_pay_life_to_draw()
    tag_for_conditional_draw()
    tag_for_replacement_draw()
    
    # Check for any other card draw effects
    for color in colors:
        print(f'Checking {color}_cards.csv for any other unconditional card draw effects.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Cycling' in theme_tags
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                or 'Conditional Draw' in theme_tags
                or 'Replacement Draw' in theme_tags
                ):
                if 'Card Draw' not in theme_tags:
                    theme_tags.extend(['Card Draw'])
                continue
            for num in num_to_search:
                if (f'draw {num} card' in row['text'].lower()):
                    kind_of_draw = ['Unconditional Draw', 'Card Draw']
                    for which_draw in kind_of_draw:
                        if which_draw not in theme_tags:
                            theme_tags.extend([which_draw])
                            df.at[index, 'themeTags'] = theme_tags
            
        
        # Overwrite file with Conditional Draw tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Unonditional draw cards tagged in {color}_cards.csv.\n')

def tag_for_artifact():
    # Iterate through each {color}_cards.csv file to find artifact cards
    # Also check for cards that care about artifacts
    for color in colors:
        print(f'Settings "Artifact" type tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for artifacts
        print(f'Tagging cards in {color}_cards.csv that have the "Artifact" type.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Artifact' in row['type']:
                tag_type = ['Artifact', 'Artifacts Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with artifact tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Cards with the "Artifact" type in {color}_cards.csv have been tagged.\n')

def tag_for_artifact_tokens():
    for color in colors:
        print(f'Settings artifact token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for artifact token creation
        print(f'Tagging cards in {color}_cards.csv that create or modify creation of Artifact tokens and don\'t have Fabricate.')
        print('Checking for non-predefined tokens (i.e. Karnstruct or Servo) generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('lifecraft awakening' in row['name'].lower()
                or 'sandsteppe war riders' in row['name'].lower()
                or 'diabolical salvation' in row['name'].lower()
                ):
                continue
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                if ('artifact token' in row['text'].lower()
                    or 'artifact creature token' in row['text'].lower()
                    or 'copy of target artifact' in row['text'].lower()
                    or 'copy of that artifact' in row['text'].lower()
                    or 'copy of enchanted artifact' in row['text'].lower()
                    or 'construct artifact' in row['text'].lower()
                    or 'bloodforged battle' in row['name'].lower()
                    or 'nexus of becoming' in row['name'].lower()
                    or 'prototype portal' in row['name'].lower()
                    or 'wedding ring' in row['name'].lower()
                    or 'court of vantress' in row['name'].lower()
                    or 'faerie artisans' in row['name'].lower()
                    or 'lenoardo da vinci' in row['name'].lower()
                    or 'march of progress' in row['name'].lower()
                    or 'season of weaving' in row['name'].lower()
                    or 'vaultborn tyrant' in row['name'].lower()
                    or 'feldon of the third path' in row['name'].lower()
                    or 'red sun\'s twilight' in row['name'].lower()
                    or 'osgir, the reconstructor' in row['name'].lower()
                    or 'saheeli, the sun\'s brilliance' in row['name'].lower()
                    or 'shaun, father of synths' in row['name'].lower()
                    or 'elmar, ulvenwald informant' in row['name'].lower()
                    or 'sophia, dogged detective' in row['name'].lower()
                    ):
                    if 'transmutation font' not in row['name'].lower():
                        if 'fabricate' not in row['text'].lower():
                            tag_type = ['Artifact Tokens', 'Artifacts Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are non-predefined token generators have been tagged.\n')
        print('Checking for predefined tokens (i.e. Treassure or Food) generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('create' in row['text'].lower()):
                for artifact_token in artifact_tokens:
                    if (f'{artifact_token.lower()}' in row['text'].lower()):
                        if artifact_token == 'Blood':
                            if (row['name'] == 'Bloodroot Apothecary'):
                                continue
                        if artifact_token == 'Gold':
                            if (row['name'] == 'Goldspan Dragon'
                                or row['name'] == 'The Golden-Gear Colossus'):
                                continue
                        if artifact_token == 'Junk':
                            if (row['name'] == 'Junkyard Genius'):
                                continue
                        tag_type = ['Artifact Tokens', f'{artifact_token} Tokens', 'Artifacts Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are predefined token generators have been tagged.\n')
        print(f'Cards in {color}_cards.csv that create or modify creation of Artifact tokens and don\'t have Fabricate have been tagged.\n')
        # Tag for artifact token creation
        print(f'Tagging cards in {color}_cards.csv have Fabricate.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'fabricate' in row['text'].lower():
                tag_type = ['Artifact Tokens']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that have Fabricate have been tagged.\n')

        # Overwrite file with artifact tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Artifact cards tagged in {color}_cards.csv.\n')

def tag_for_artifacts_matter():
    tag_for_artifact()
    tag_for_artifact_tokens()
    for color in colors:
        print(f'Settings artifact token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for artifacts matter
        print(f'Tagging cards in {color}_cards.csv that care about artifacts.\n')
        print(f'Tagging cards in {color}_cards.csv or reduce spell cost for or depending on number of artifacts.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            for num in num_to_search:
                if (f'artifact spells you cast cost {{{num}}} less to cast' in row['text'].lower()
                    or f'artifact and enchantment spells you cast cost {{{num}}} less to cast' in row['text'].lower()
                    or f'historic spells you cast cost {{{num}}} less to cast' in row['text'].lower()
                    or f'this spell costs {{{num}}} less to cast for each artifact' in row['text'].lower()
                    or f'this spell costs {{{num}}} less to cast for each historic' in row['text'].lower()
                    ):
                    tag_type = ['Artifacts Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            if ('affinity for artifacts' in row['text'].lower()
                or 'improvise' in row['text'].lower()
                or 'artificer class' in row['name'].lower()
                ):
                
                tag_type = ['Artifacts Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that reduce spell cost for or depending on number of artifacts have been tagged.\n')
        
        print(f'Tagging cards in {color}_cards.csv that care about artifacts.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('cast an artifact' in row['text'].lower()
                or 'artifact spells you cast' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an artifact' in row['text'].lower()
                or 'whenever a nontoken artifact' in row['text'].lower()
                or 'whenever another nontoken artifact' in row['text'].lower()
                or 'whenever an artifact' in row['text'].lower()
                or 'prowess' in row['text'].lower()
                or 'whenever one or more artifact' in row['text'].lower()
                or 'artifact creature you control' in row['text'].lower()
                or 'artifact creatures you control' in row['text'].lower()
                or 'artifact you control' in row['text'].lower()
                or 'artifacts you control' in row['text'].lower()
                or 'artifact creature you control' in row['text'].lower()
                or 'artifact creatures you control' in row['text'].lower()
                or 'another target artifact' in row['text'].lower()
                or 'target artifact' in row['text'].lower()
                or 'abilities of artifact' in row['text'].lower()
                or 'ability of artifact' in row['text'].lower()
                or 'copy of any artifact' in row['text'].lower()
                or 'search your library for an artifact' in row['text'].lower()
                or 'artifact spells as though they had flash' in row['text'].lower()
                or 'artifact enters' in row['text'].lower()
                or 'metalcraft' in row['text'].lower()
                or 'number of artifacts' in row['text'].lower()
                or 'number of other artifacts' in row['text'].lower()
                or 'number of tapped artifacts' in row['text'].lower()
                or 'affinity for artifacts' in row['text'].lower()
                or 'all artifact' in row['text'].lower()
                or 'choose an artifact' in row['text'].lower()
                or 'artifact with the highest mana value' in row['text'].lower()
                or 'mana cost among artifact' in row['text'].lower()
                or 'mana value among artifact' in row['text'].lower()
                or 'each artifact' in row['text'].lower()
                or 'number of artifact' in row['text'].lower()
                or 'another artifact' in row['text'].lower()
                or 'are artifacts in addition' in row['text'].lower()
                or 'artifact' in row['text'].lower()
                or 'artifact card' in row['text'].lower()
                ):
                
                tag_type = ['Artifacts Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that care about other artifacts have been tagged.\n')
        
        # Overwrite file with artifacts matter tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Artifact matters cards tagged in {color}_cards.csv.\n')

def tag_equipment():
    # Iterate through each {color}_cards.csv file to find equipment cards
    # Also check for cards that care about equipments
    for color in colors:
        print(f'Settings "Equipment" type tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for equipments
        print(f'Tagging cards in {color}_cards.csv that have the "Equipment" type.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Equipment' in row['type']:
                tag_type = ['Equipment', 'Equipment Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Tag for cares about equipment
        print(f'Tagging cards in {color}_cards.csv that care about equipment.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('equipment' in row['text'].lower()
                or 'equipped' in row['text'].lower()
                or 'modified' in row['text'].lower()
                or 'alexios, deimos of kosmos' in row['name'].lower()
                or 'kosei, penitent warlord' in row['name'].lower()
                ):
                tag_type = ['Equipment Matters', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with equipment tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Cards that care about equipment in {color}_cards.csv have been tagged.\n')

def tag_for_enchantment():
    # Iterate through each {color}_cards.csv file to find enchantment cards
    # Also check for cards that care about enchantments
    for color in colors:
        print(f'Settings "Enchantment" type tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for enchantments
        print(f'Tagging cards in {color}_cards.csv that have the "Enchantment" type.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Enchantment' in row['type']:
                tag_type = ['Enchantment', 'Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with enchantment tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Cards with the "Enchantment" type in {color}_cards.csv have been tagged.\n')

def tag_for_enchantment_tokens():
    for color in colors:
        print(f'Settings enchantment token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for enchantment token creation
        print(f'Tagging cards in {color}_cards.csv that create or modify creation of Enchantment tokens')
        print('Checking for non-predefined token generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                if ('enchantment token' in row['text'].lower()
                    or 'enchantment creature token' in row['text'].lower()
                    or 'copy of target enchantment' in row['text'].lower()
                    or 'copy of that enchantment' in row['text'].lower()
                    or 'copy of enchanted enchantment' in row['text'].lower()
                    or 'court of vantress' in row['name'].lower()
                    or 'felhide spiritbinder' in row['name'].lower()
                    or 'hammer of purphoros' in row['name'].lower()
                    ):
                    tag_type = ['Enchantment Tokens', 'Enchantments Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are non-predefined token generators have been tagged.\n')
        print('Checking for predefined token (i.e. Roles or Shard) generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('create' in row['text'].lower()):
                for enchantment_token in enchantment_tokens:
                    if (f'{enchantment_token.lower()}' in row['text'].lower()):
                        tag_type = ['Enchantment Tokens', f'{enchantment_token} Tokens', 'Enchantments Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are predefined token generators have been tagged.\n')
        print(f'Cards in {color}_cards.csv that create or modify creation of Enchantment tokens have been tagged.\n')
        
        # Overwrite file with enchantment tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Enchantment cards tagged in {color}_cards.csv.\n')

def tag_for_enchantments_matter():
    tag_for_enchantment()
    tag_for_enchantment_tokens()
    for color in colors:
        print(f'Settings enchantment token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for enchantments matter
        print(f'Tagging cards in {color}_cards.csv that care about enchantments.\n')
        print(f'Tagging cards in {color}_cards.csv or reduce spell cost for or depending on number of enchantments.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            for num in num_to_search:
                if (f'artifact and enchantment spells you cast cost {{{num}}} less to cast' in row['text'].lower()
                    or f'artifact and enchantment spells you cast cost {{{num}}} less to cast' in row['text'].lower()
                    or f'this spell costs {{{num}}} less to cast for each enchantment' in row['text'].lower()
                    ):
                    tag_type = ['Enchantments Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that reduce spell cost for or depending on number of enchantments have been tagged.\n')
        print(f'Tagging cards in {color}_cards.csv that care about enchantments.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('luxa river shrine' in row['name']
                ):
                continue
            if ('cast an enchantment' in row['text'].lower()
                or 'enchantment spells you cast' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an enchantment' in row['text'].lower()
                or 'you may cast aura' in row['text'].lower()
                or 'whenever you cast an artifact or enchantment' in row['text'].lower()
                or 'whenever a nontoken enchantment' in row['text'].lower()
                or 'whenever another nontoken enchantment' in row['text'].lower()
                or 'wehenver an enchantment' in row['text'].lower()
                or 'whenever an aura' in row['text'].lower()
                or 'prowess' in row['text'].lower()
                or 'other enchantment' in row['text'].lower()
                or 'whenever one or more enchantment' in row['text'].lower()
                or 'enchantment you control' in row['text'].lower()
                or 'modified creature you control' in row['text'].lower()
                or 'enchantment creature you control' in row['text'].lower()
                or 'enchantment creatures you control' in row['text'].lower()
                or 'enchantments you control' in row['text'].lower()
                or 'enchantment creature you control' in row['text'].lower()
                or 'enchantment creatures you control' in row['text'].lower()
                or 'another target enchantment' in row['text'].lower()
                or 'target enchantment' in row['text'].lower()
                or 'abilities of enchantment' in row['text'].lower()
                or 'ability of enchantment' in row['text'].lower()
                or 'copy of any enchantment' in row['text'].lower()
                or 'search your library for an aura' in row['text'].lower()
                or 'search your library for an enchantment' in row['text'].lower()
                or 'search your library for an artifact or enchantment' in row['text'].lower()
                or 'enchantment spells as though they had flash' in row['text'].lower()
                or 'enchantment enters' in row['text'].lower()
                or 'constellation' in row['text'].lower()
                or 'enchantment' in row['text'].lower()
                or 'eerie' in row['text'].lower()
                or 'shrine' in row['text'].lower()
                or 'bestow' in row['text'].lower()
                or 'number of enchanment' in row['text'].lower()
                or 'all artifact and enchantment' in row['text'].lower()
                or 'all enchantment' in row['text'].lower()
                or 'choose an enchantment' in row['text'].lower()
                or 'enchantment with the highest mana value' in row['text'].lower()
                or 'mana cost among enchantment' in row['text'].lower()
                or 'mana value among enchantment' in row['text'].lower()
                or 'each enchantment' in row['text'].lower()
                or 'number of enchantment' in row['text'].lower()
                or 'another enchantment' in row['text'].lower()
                or 'return an enchantment' in row['text'].lower()
                or 'are enchantments in addition' in row['text'].lower()
                or 'number of aura' in row['text'].lower()
                or 'enchantment card' in row['text'].lower()
                ):
                tag_type = ['Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that care about other enchantments have been tagged.\n')
        
        # Overwrite file with enchantments matter tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'enchantment matters cards tagged in {color}_cards.csv.\n')

def tag_auras():
    # Iterate through each {color}_cards.csv file to find aura cards
    # Also check for cards that care about auras
    for color in colors:
        print(f'Settings "Aura" type tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for auras
        print(f'Tagging cards in {color}_cards.csv that have the "Aura" type.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Aura' in row['type']:
                tag_type = ['Auras', 'Auras Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Tag for cares about aura
        print(f'Tagging cards in {color}_cards.csv that care about auras.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('aura' in row['text'].lower()
                or 'equipped' in row['text'].lower()
                or 'modified' in row['text'].lower()
                or 'enchanted creature' in row['text'].lower()
                or 'ivy, gleeful spellthief' in row['name'].lower()
                or 'zur the enchanter' in row['name'].lower()
                or 'killian, ink duelist' in row['name'].lower()
                or 'sithis, harvest\'s hand' in row['name'].lower()
                or 'tatsunari, toad rider' in row['name'].lower()
                or 'gylwain, casting director' in row['name'].lower()
                or 'calix, guided by fate' in row['name'].lower()
                or 'alexios, deimos of kosmos' in row['name'].lower()
                ):
                tag_type = ['Auras Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with aura tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Cards that care about aura in {color}_cards.csv have been tagged.\n')

def tag_for_tokens():
    for color in colors:
        print(f'Settings token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for enchantment token creation
        print(f'Tagging cards in {color}_cards.csv that create or modify creation of tokens.')
        print('Checking for creature token generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('agatha\'s soul cauldron' in row['name'].lower()
                or 'fabricate' in row['text'].lower()
                or 'modular' in row['text'].lower()
                ):
                continue
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                for tokens in num_to_search:
                    if (f'{tokens}' in row['text']
                        and 'token' in row['text']):
                        if ('creature' in row['text'].lower()):
                            tag_type = ['Creature Tokens', 'Tokens Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are creature token generators have been tagged.\n')
        print('Checking for token creation modifiers.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('staff of the storyteller' in row['name'].lower()
                or 'cloakwood swarmkeeper' in row['name'].lower()
                or 'neyali, sun\'s vanguard' in row['name'].lower()
                ):
                continue
            if ('create one or more' in row['text']
                or 'put one or more' in row['text']
                or 'one or more tokens would enter' in row['text']
                or 'one or more tokens would be created' in row['text']
                or 'one or more tokens would be put' in row['text']
                or 'one or more tokens you control' in row['text']
                or 'one or more creature tokens' in row['text']
                ):
                if ('token' in row['text']):
                    if ('instead' in row['text']
                        or 'plus' in row['text']
                        ):
                        tag_type = ['Tokens', 'Token Modification', 'Tokens Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are token creation modifiers have been tagged.\n')
        # Overwrite file with enchantment tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Enchantment cards tagged in {color}_cards.csv.\n')

        #keyboard.wait('space')

def tag_for_life_matters():
    for color in colors:
        print(f'Settings token tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for enchantment token creation
        print(f'Tagging cards in {color}_cards.csv that gain life or care about life gain.')
        print('Checking for life gain cards.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('whenever you gain life' in row['text'].lower()
                or 'if you would gain life' in row['text'].lower()
                ):
                continue
            if ('food token' in row['text'].lower()):
                tag_type = ['Food Tokens', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                continue
            for life_gained in num_to_search:
                if (f'gain {life_gained} life' in row['text'].lower()
                    or f'gains {life_gained} life' in row['text'].lower()):
                    tag_type = ['Lifegain', 'Life Matters']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags    
            if ('gain life' in row['text'].lower()
                or 'gains life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('lifelink' in row['text'].lower()
                ):
                tag_type = ['Lifelink', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('deals damage' not in row['text'].lower()
                ):
                if ('loses life' in row['text'].lower()):
                    if ('gain that much life' in row['text'].lower()
                    ):
                        tag_type = ['Lifelink', 'Lifegain', 'Life Matters']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
            if ('deals damage, you gain that much life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that gain life or grant lifelink have been tagged.\n')
        
        # Checking for life gain modifiers or trigger on life gain
        print('Checking for life gain modifications or triggers.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('whenever you gain life' in row['text'].lower()
                or 'if you would gain life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Lifegain Triggers', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        print(f'\nCards in {color}_cards.csv that modify life gain or trigger on life gain have been tagged.\n')
        
        # Checking for life loss modifiers or trigger on life loss
        print('Checking for life loss triggers.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('whenever you lose life' in row['text'].lower()
                or 'you would lose life' in row['text'].lower()
                or 'you lost life' in row['text'].lower()
                or 'you\'ve lost life' in row['text'].lower()
                or 'you gained and lost life' in row['text'].lower()
                or 'you gained or lost life' in row['text'].lower()
                or 'you gained and lost life this turn' in row['text'].lower()
                or 'whenever you gain or lose life' in row['text'].lower()
                ):
                print(row['name'])
                tag_type = ['Lifeloss', 'Lifeloss Triggers', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        print(f'\nCards in {color}_cards.csv that modify life gain or trigger on life gain have been tagged.\n')
        
        # Overwrite file with Life tags added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Life Matters cards tagged in {color}_cards.csv.\n')

def tag_for_counters():
    # Iterate through each {color}_cards.csv file to find cards that add counters
    # Also check for cards that care about counters
    for color in colors:
        print(f'Settings "Counters Matter" tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for counters matter
        print(f'Tagging cards in {color}_cards.csv that fit the "Counters Matter" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            if ('proliferate' in row['text'].lower()
                or 'hydra' in row['creatureTypes'].lower()
                or 'one or more counters' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'ozolith' in row['name'].lower()
                or 'proliferate' in row['text'].lower()
                or 'banner of kinship' in row['name'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                or 'damning verdict' in row['name'].lower()
                ):
                tag_type = ['Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('+1/+1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'hydra' in row['creatureTypes'].lower()
                or 'one or more counters' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'shield counter' in row['text'].lower()
                or 'ozolith' in row['name'].lower()
                or 'proliferate' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                or 'damning verdict' in row['name'].lower()
                ):
                tag_type = ['+1/+1 Counters', 'Counters Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if ('-1/-1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'one or more counters' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'damning verdict' in row['name'].lower()
                ):
                tag_type = ['-1/-1 Counters', 'Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            for counter_type in counter_types:
                if f'{counter_type} counter'.lower() in row['text'].lower():
                    tag_type = [f'{counter_type} Counters', 'Counters Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with counters matter tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'"Counters Matter" themed cards in {color}_cards.csv have been tagged.\n')

def tag_for_voltron():
    tag_equipment()
    tag_auras()
    tag_for_counters()
    # Iterate through each {color}_cards.csv file to find voltron cards
    # Also check for cards that care about auras
    for color in colors:
        print(f'Settings "Voltron" tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for voltron
        print(f'Tagging cards in {color}_cards.csv that fit the "Voltron" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Voltron' in row['themeTags']:
                continue
            if ('raised by giants' in row['name'].lower()
                or 'feather, the redeemed' in row['name'].lower()
                or 'narset, enlightened master' in row['name'].lower()
                or 'zurgo helmsmasher' in row['name'].lower()
                or 'rafiq of the many' in row['name'].lower()
                or 'slicer, hired muscle' in row['name'].lower()
                or 'yargle and multani' in row['name'].lower()
                or 'kosei, penitent warlord' in row['name'].lower()
                or 'rograkh, son of rohgahh' in row['name'].lower()
                or 'wilson, refined grizzly' in row['name'].lower()
                or 'skullbriar, the walking grave' in row['name'].lower()
                or 'feather, the redeemed' in row['name'].lower()
                or 'narset, enlightened master' in row['name'].lower()
                or 'zurgo helmsmasher' in row['name'].lower()
                ):
                tag_type = ['Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        # Overwrite file with voltron tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'"Voltron" themed cards in {color}_cards.csv have been tagged.\n')

def tag_for_wheels():
    # Iterate through each {color}_cards.csv file to find wheel cards
    # Also check for cards that care about wheeling
    for color in colors:
        print(f'Settings "Wheels" tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv', converters={'themeTags': pd.eval})
        
        # Tag for voltron
        print(f'Tagging cards in {color}_cards.csv that fit the "Wheels" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('an opponent draws a card' in row['text'].lower()
                or 'whenever you draw a card' in row['text'].lower()
                or 'draws their first second card' in row['text'].lower()
                or 'draws their second second card' in row['text'].lower()
                or 'draw your second card' in row['text'].lower()
                or 'may draw a card' in row['text'].lower()
                or 'you draw a card' in row['text'].lower()
                or 'each card your opponents have drawn' in row['text'].lower()
                or 'each player draws' in row['text'].lower()
                or 'each draw a card' in row['text'].lower()
                or 'draws an additional card' in row['text'].lower()
                or 'draws two additional cards' in row['text'].lower()
                or 'draws a card' in row['text'].lower()
                or 'draw two cards instead' in row['text'].lower()
                or 'draw that many cards' in row['text'].lower()
                or 'discards their hand, then draws' in row['text'].lower()
                or 'draws half that many cards' in row['text'].lower()
                or 'draws cards' in row['text'].lower()
                or 'threshold' in row['text'].lower()
                or 'delirium' in row['text'].lower()
                or 'descended' in row['text'].lower()
                or 'maximum hand size' in row['text'].lower()
                or 'no cards in it, you win the game instead' in row['text'].lower()
                or 'each opponent draws a card' in row['text'].lower()
                or 'has no cards in hand' in row['text'].lower()
                or 'have no cards in hand' in row['text'].lower()
                or 'opponent discards' in row['text'].lower()
                or 'discards that card' in row['text'].lower()
                or 'mills' in row['text'].lower()
                or 'cards you\'ve drawn' in row['text'].lower()
                ):
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            if ('raffine, scheming seer' in row['name'].lower()
                or 'raffine, scheming seer' in row['name'].lower()
                or 'kynaios and tiro of meletis' in row['name'].lower()
                or 'elenda and azor' in row['name'].lower()
                or 'sauron, the dark lord' in row['name'].lower()
                or 'dark deal' in row['name'].lower()
                or 'whispering madness' in row['name'].lower()
                or 'arcane denial' in row['name'].lower()
                or 'glunch, the bestower' in row['name'].lower()
                or 'mr. foxglove' in row['name'].lower()
                or 'kiora the rising tide' in row['name'].lower()
                or 'esper sentinel' in row['name'].lower()
                or 'loran of the third path' in row['name'].lower()
                or 'icewind elemental' in row['name'].lower()
                or 'seizan, perverter of truth' in row['name'].lower()
                or 'twenty-toed toad' in row['name'].lower()
                or 'triskaidekaphile' in row['name'].lower()
                or 'wedding ring' in row['name'].lower()
                or 'bolas\'s citadel' in row['name'].lower()
                or 'the one ring' in row['name'].lower()
                or 'library of leng' in row['name'].lower()
                or 'sensei\'s divining top' in row['name'].lower()
                or 'elixir of immortality' in row['name'].lower()
                or 'waste not' in row['name'].lower()
                or 'forced fruition' in row['name'].lower()
                or 'bloodchief ascension' in row['name'].lower()
                or 'whirlwind of thought' in row['name'].lower()
                ):
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            if 'Card Draw' in row['themeTags']:
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with wheels tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'"Wheels" themed cards in {color}_cards.csv have been tagged.\n')
        
        
"""kindred_tagging()
setup_tags()
tag_for_artifacts_matter()
tag_for_enchantments_matter()
tag_for_card_draw()
tag_for_tokens()
tag_for_life_matters()
tag_for_voltron()"""
#add_creatures_to_tags()
tag_for_wheels()
sort_theme_tags()