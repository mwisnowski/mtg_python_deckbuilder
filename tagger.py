from __future__ import annotations

import inquirer.prompt # type: ignore
import keyboard # type: ignore
import pandas as pd # type: ignore
import pprint # type: ignore
import random

from fuzzywuzzy import fuzz, process # type: ignore

import settings

colors = ['colorless', 'white', 'blue', 'black', 'green', 'red',
          'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
          'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
          'bant', 'esper', 'grixis', 'jund', 'naya',
          'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
          'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg',
          'legendary']
num_cards = ['a', 'two', '2', 'three', '3', 'four',' 4', 'five', '5', 'six', 
             '6', 'seven', '7', 'eight', '8', 'nine', '9', 'ten', '10', 'X']
triggered = ['when', 'whenever', 'at']
artifact_tokens = ['Blood', 'Clue', 'Food', 'Gold', 'Incubator',
                   'Junk','Map','Powerstone', 'Treasure']
enchanment_tokens = ['Cursed Role', 'Monster Role', 'Royal Role','Virtuous Role',
                     'Wicked Role', 'Young Hero Role', 'Shard']

csv_directory = 'csv_files'

karnstruct = '0/0 colorless Construct'

# Determine any non-creature cards that have creature types mentioned
def kindred_tagging():
    for color in colors:
        print(f'Settings creature type tags on {color}_cards.csv.')
        # Setup dataframe
        df = pd.read_csv(f'csv_files/{color}_cards.csv')
        df['creatureType'] = ''
        
        # Set creature types
        for index, row in df.iterrows():
            kindred_tags = []
            if 'Creature' in row['type']:
                creature_types = row['type']
                split_types = creature_types.split()
                for creature_type in split_types:
                    if creature_type not in settings.non_creature_types:
                        kindred_tags.append(creature_type)
                        df.at[index, 'creatureType'] = kindred_tags
                        
        # Set outlaws
        outlaws = ['Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock']
        for index, row in df.iterrows():
            kindred_tags = row['creatureType']
            creature_types = kindred_tags
            for creature_type in creature_types:
                if creature_type in outlaws:
                    kindred_tags.append('Outlaw')
                    df.at[index, 'creatureType'] = kindred_tags
        
        # Overwrite file with creature type tags
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
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Theme/effect tag column created on {color}_cards.csv.\n')
    
    #tag_for_card_draw()

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
                for num in num_cards:
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
                for num in num_cards:
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
            for num in num_cards:
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
                    for num in num_cards:
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
                        for num in num_cards:
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
                theme_tags.extend(['Card Draw'])
                continue
            for num in num_cards:
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
                            print(row['name'])
                            tag_type = ['Artifact Tokens', 'Artifacts Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are non-predefined token generators have been tagged.\n')
        keyboard.wait('space')
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
                        print(row['name'])
                        tag_type = ['Artifact Tokens', f'{artifact_token} Tokens', 'Artifacts Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are predefined token generators have been tagged.\n')
        keyboard.wait('space')
        print(f'Cards in {color}_cards.csv that create or modify creation of Artifact tokens and don\'t have Fabricate have been tagged.\n')
        # Tag for artifact token creation
        print(f'Tagging cards in {color}_cards.csv have Fabricate.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'fabricate' in row['text'].lower():
                print(row['name'])
                tag_type = ['Artifact Tokens']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that have Fabricate have been tagged.\n')

        keyboard.wait('space')
        # Overwrite file with artifact tag added
        df.to_csv(f'csv_files/{color}_cards.csv', index=False)
        print(f'Artifact cards tagged in {color}_cards.csv.\n')
        keyboard.wait('space')

#kindred_tagging()
setup_tags()
#tag_for_artifact()
tag_for_artifact_tokens()