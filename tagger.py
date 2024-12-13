from __future__ import annotations

import keyboard # type: ignore
import pandas as pd # type: ignore

import settings

from settings import artifact_tokens, csv_directory, colors, counter_types, enchantment_tokens, num_to_search, triggers
from setup import regenerate_csvs_all, regenerate_csv_by_color
from utility import pluralize, sort_list

karnstruct = '0/0 colorless Construct'
  
# Determine any non-creature cards that have creature types mentioned
def kindred_tagging():
    for color in colors:
        print(f'Settings creature type tags on {color}_cards.csv.\n')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv')
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
            
        # Create new blank list column called 'creatureTypes
        df['creatureTypes'] = [[] for _ in range(len(df))]
        
        # Set creature types
        print(f'Checking for and setting creature types in {color}_cards.csv')
        for index, row in df.iterrows():
            if 'Creature' in row['type']:
                kindred_tags = []
                creature_types = row['type']
                split_types = creature_types.split()
                for creature_type in split_types:
                    
                    # If the type is a non-creature type ignore it
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
                        if creature_type == 'Mount':
                            if 'Mountain' in row['text']:
                                continue
                        if creature_type not in kindred_tags:
                            kindred_tags.append(creature_type)
                            if creature_type in outlaws:
                                kindred_tags.append(creature_type)
                            df.at[index, 'creatureTypes'] = kindred_tags
                
                # Tag for pluralized types (i.e. Elves, Wolves, etc...) in textbox
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Creature types tagged on {color}_cards.csv.\n')

def setup_tags():
    # Create a blank column for theme/effect tags
    # This will setup a basis for future tagging to automate deck building
    for color in colors:
        print(f'Creating theme/effect tag column for {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv')
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # # Create new blank list column called 'themeTags
        df['themeTags'] = [[] for _ in range(len(df))]
        
        # Organize it's location
        columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags']
        df = df[columns_to_keep]
        
        # Overwrite original file
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Theme/effect tag column created on {color}_cards.csv.\n')
    
def add_creatures_to_tags():
    for color in colors:
        print(f'Adding creature types to theme tags in {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Add kindred_tags to creatureTypes column
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            kindred_tags = row['creatureTypes']
            for kindred_tag in kindred_tags:
                if kindred_tag not in theme_tags:
                    theme_tags.extend([f'{kindred_tag} Kindred'])
        
        # Overwrite file with kindred tags added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Creature types added to theme tags in {color}_cards.csv.')

def tag_for_card_types():
    # Iterate through each {color}_cards.csv file to find artifact cards
    # Also check for cards that care about artifacts
    for color in colors:
        print(f'Settings card type tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        card_types = ['Artifact', 'Creature', 'Enchantment', 'Land', 'Instant', 'Sorcery', 'Planeswalker', 'Battle']
        
        # Tag for artifacts
        for card_type in card_types:
            print(f'Tagging cards in {color}_cards.csv that have the "{card_type}" type.')
            for index, row in df.iterrows():
                theme_tags = row['themeTags']
                if card_type in row['type']:
                    tag_type = [card_type]
                    if card_type in ['Artifact', 'Enchantment', 'Land']:
                        tag_type.append(f'{card_type}s Matter')
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            print(f'Cards with the "{card_type}" type in {color}_cards.csv have been tagged.\n')
        # Overwrite file with artifact tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)

def sort_theme_tags():
    for color in colors:
        print(f'Alphabetically sorting theme tags in {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        df['themeTags'] = df['themeTags'].apply(sorted)
        
        columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags']
        df = df[columns_to_keep]
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=sorted)
        print(f'Theme tags alphabetically sorted in {color}_cards.csv.\n')

# Card draw/advantage
def tag_for_sacrifice_to_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for sacrifice to draw cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
            
            # Cards that say 'sacrifice a' or 'sacrifice an'
            a_or_an = ['a', 'an']
            for which_one in a_or_an:
                if (f'sacrifice {which_one} artifact: draw a card' in row['text'].lower()
                    or f'sacrifice {which_one} creature: draw a card' in row['text'].lower()):
                    kind_of_draw = ['Sacrifice to Draw', 'Card Draw']
                    for which_draw in kind_of_draw:
                        if which_draw not in theme_tags:
                            theme_tags.extend([which_draw])
                            df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with connive tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Sacrifice to draw cards tagged in {color}_cards.csv.\n')

def tag_for_pay_life_to_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for pay life to draw card effects:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Basic logic for the cards
            if ('life: draw' in row['text'].lower()):
                
                # Pay life to draw
                for num in num_to_search:
                    if (f'draw {num} card' in row['text'].lower()):
                        kind_of_draw = ['Life to Draw', 'Card Draw']
                        for which_draw in kind_of_draw:
                            if which_draw not in theme_tags:
                                theme_tags.extend([which_draw])
                                df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with connive tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Pay life to draw cards tagged in {color}_cards.csv.\n')

def tag_for_connive():
    for color in colors:
        print(f'Checking {color}_cards.csv for connive cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)

        # Set connive tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if pd.isna(row['keywords']):
                continue
            
            # Logic for Connive cards
            if ('connive' in row['keywords'].lower()
                
                # In text if not in keywords
                or 'connives' in row['text'].lower()
                or 'connives' in row['text'].lower()
                ):
                kind_of_draw = ['Connive', 'Loot', 'Card Draw']
                for which_draw in kind_of_draw:
                    if which_draw not in theme_tags:
                        theme_tags.extend([which_draw])
                        df.at[index, 'themeTags'] = theme_tags

        # Overwrite file with connive tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_cycling():
    for color in colors:
        print(f'Checking {color}_cards.csv for cycling cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_loot():
    for color in colors:
        print(f'Checking {color}_cards.csv for loot cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
                    if ('discard the rest' in row['text'].lower()
                        or 'for each card drawn this way, discard' in row['text'].lower()
                        or 'if you do, discard' in row['text'].lower()
                        or 'then discard' in row['text'].lower()
                        ):
                        kind_of_draw = ['Loot', 'Card Draw']
                        for which_draw in kind_of_draw:
                            if which_draw not in theme_tags:
                                theme_tags.extend([which_draw])
                                df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with loot tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Loot cards tagged in {color}_cards.csv.\n')

def tag_for_imprint():
    for color in colors:
        print(f'Checking {color}_cards.csv for imprint cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tagging for imprint effects
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('imprint' in row['text'].lower()):
                if 'Imprint' not in theme_tags:
                    theme_tags.extend(['Imprint'])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with creature type tags
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Impulse cards tagged in {color}_cards.csv.\n')

def tag_for_impulse():
    for color in colors:
        print(f'Checking {color}_cards.csv for impulse cards:')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Check for impulse effects
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Tagging cards that should match, but need specific wording
            if (
                'daxos of meletis' in row['name'].lower()
                or 'bloodsoaked insight' in row['name'].lower()
                or 'florian, voldaren scion' in row['name'].lower()
                or 'possibility storm' in row['name'].lower()
                or 'ragava, nimble pilferer' in row['name'].lower()
                or 'rakdos, the muscle' in row['name'].lower()
                or 'stolen strategy' in row['name'].lower()
                or 'urabrask, heretic praetor' in row['name'].lower()
                or 'valakut exploration' in row['name'].lower()
                or 'wild wasteland' in row['name'].lower()
                ):
                if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                    theme_tags.append('Impulse')
                    df.at[index, 'themeTags'] = theme_tags
            
            # Setting exclusions that may result in erroneous matches
            if (
                'damage to each' not in row['text'].lower()
                or 'damage to target' not in row['text'].lower()
                or 'deals combat damage' not in row['text'].lower()
                or 'planeswalker' not in row['type'].lower()
                or 'raid' not in row['text'].lower()
                or 'target opponent\'s hand' not in row['text'].lower()):
                if ('each opponent' in row['text'].lower()
                    or 'morph' in row['text'].lower()
                    or 'opponent\'s library' in row['text'].lower()
                    or 'skip your draw' in row['text'].lower()
                    or 'target opponent' in row['text'].lower()
                    or 'that player\'s' in row['text'].lower()
                    or 'you may look at the top card' in row['text'].lower()
                    ):
                    continue
                
            # Tagging cards that match based on the phrasing of 'exile the top' cards then 'you may {play/cast}'
            if ('exile the top'in row['text'].lower()
                or 'exiles the top' in row['text'].lower()
                ):
                if ('may cast' in row['text'].lower()
                    or 'may play' in row['text'].lower()):
                    if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                        theme_tags.append('Impulse')
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging cards that create junk tokens
            if ('junk token' in row['text'].lower()):
                if ('Impulse' not in theme_tags
                    and 'Imprint' not in theme_tags):
                    theme_tags.append('Impulse')
                    df.at[index, 'themeTags'] = theme_tags
            
        # Overwrite file with creature type tags 
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Impulse cards tagged in {color}_cards.csv.\n')

def tag_for_conditional_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for conditional card draw effects.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Cycling' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                
                # Keywords in text
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                ):
                continue
            
            # Ecluding cards that have erroneous matches
            if ('relic vial' in row['name'].lower()
                or 'vexing bauble' in row['name'].lower()
                or 'whenever you draw a card' in row['text'].lower()
                ):
                continue
            
            # Tagging cards that have when, whenever, at effects
            for trigger in triggers:
                if (f'{trigger} a permanent' in row['text'].lower()
                or f'{trigger} a creature' in row['text'].lower()
                or f'{trigger} a player' in row['text'].lower()
                or f'{trigger} an opponent' in row['text'].lower()
                or f'{trigger} another creature' in row['text'].lower()
                or f'{trigger} enchanted player' in row['text'].lower()
                or f'{trigger} one or more creatures' in row['text'].lower()
                or f'{trigger} one or more other creatures' in row['text'].lower()
                or f'{trigger} you' in row['text'].lower()
                or (f'{trigger} {row['name']} attacks'.lower() in row['text'].lower())
                ):
                    for num in num_to_search:
                        if (f'draw {num} card' in row['text'].lower()):
                            kind_of_draw = ['Conditional Draw', 'Card Draw']
                            for which_draw in kind_of_draw:
                                if which_draw not in theme_tags:
                                    theme_tags.extend([which_draw])
                                    df.at[index, 'themeTags'] = theme_tags
            
            # For other triggers or similar effects
            if ('created a token' in row['text'].lower()
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Conditional draw cards tagged in {color}_cards.csv.\n')

def tag_for_replacement_draw():
    for color in colors:
        print(f'Checking {color}_cards.csv for replacement card draw effects.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Conditional Draw' in theme_tags
                or 'Cycling' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                ):
                continue
            
            if 'skips that turn instead' in row['text'].lower():
                continue
            
            # Tagging for when, whenaver, at replacement draw effects
            for trigger in triggers:
                if (f'{trigger} a player' in row['text'].lower()
                    or f'{trigger} an opponent' in row['text'].lower()
                    or f'{trigger} the beginning of your draw step' in row['text'].lower()
                    or f'{trigger} you' in row['text'].lower()
                    ):
                    if 'instead' in row['text'].lower():
                        for num in num_to_search:
                            if (f'draw {num} card' in row['text'].lower()):
                                kind_of_draw = ['Replacement Draw', 'Card Draw']
                                for which_draw in kind_of_draw:
                                    if which_draw not in theme_tags:
                                        theme_tags.extend([which_draw])
                                        df.at[index, 'themeTags'] = theme_tags
            
            # Other triggers or replacement effects
            if ('if a player would' in row['text'].lower()
                    or 'if an opponent would' in row['text'].lower()
                    or 'if you would' in row['text'].lower()
                    ):
                    if 'instead' in row['text'].lower():
                        for num in num_to_search:
                            if (f'draw {num} card' in row['text'].lower()):
                                kind_of_draw = ['Replacement Draw', 'Card Draw']
                                for which_draw in kind_of_draw:
                                    if which_draw not in theme_tags:
                                        theme_tags.extend([which_draw])
                                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging Sylvan Library
            if ('sylvan library' in row['name'].lower()
                ):
                if 'Replacement Draw' not in theme_tags:
                    theme_tags.extend(['Replacement Draw'])
                    df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with Conditional Draw tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
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
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Set sacrifice to draw tags
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Triggered effects
            if ('Conditional Draw' in theme_tags
                or 'Cycling' in theme_tags
                or 'Imprint' in theme_tags
                or 'Impulse' in theme_tags
                or 'Life to Draw' in theme_tags
                or 'Loot' in theme_tags
                or 'Sacrifice to Draw' in theme_tags
                or 'Replacement Draw' in theme_tags
                or 'annihilator' in row['text'].lower()
                or 'ravenous' in row['text'].lower()
                ):
                if 'Card Draw' not in theme_tags:
                    theme_tags.extend(['Card Draw'])
                continue
            
            # Tagging remaining cards that have draw effects
            for num in num_to_search:
                if (f'draw {num} card' in row['text'].lower()):
                    kind_of_draw = ['Unconditional Draw', 'Card Draw']
                    for which_draw in kind_of_draw:
                        if which_draw not in theme_tags:
                            theme_tags.extend([which_draw])
                            df.at[index, 'themeTags'] = theme_tags
            
        
        # Overwrite file with Conditional Draw tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Unonditional draw cards tagged in {color}_cards.csv.\n')

# Artifacts
def tag_for_artifact():
    # Iterate through each {color}_cards.csv file to find artifact cards
    # Also check for cards that care about artifacts
    for color in colors:
        print(f'Settings "Artifact" type tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Cards with the "Artifact" type in {color}_cards.csv have been tagged.\n')

def tag_for_artifact_tokens():
    for color in colors:
        print(f'Settings artifact token tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for artifact token creation
        print(f'Tagging cards in {color}_cards.csv that create or modify creation of Artifact tokens and don\'t have Fabricate.')
        print('Checking for non-predefined tokens (i.e. Karnstruct or Servo) generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Setting false positive exclusions
            if ('diabolical salvation' in row['name'].lower()
                or 'lifecraft awakening' in row['name'].lower()
                or 'sandsteppe war riders' in row['name'].lower()
                ):
                continue
            
            # Tagging for card that create non-predefined tokens (i.e. Karnstruct or Servo tokens)
            if ('create' in row['text'].lower()
                or 'put' in row['text'].lower()
                ):
                if ('artifact creature token' in row['text'].lower()
                    or 'artifact token' in row['text'].lower()
                    or 'construct artifact' in row['text'].lower()
                    or 'copy of enchanted artifact' in row['text'].lower()
                    or 'copy of target artifact' in row['text'].lower()
                    or 'copy of that artifact' in row['text'].lower()
                    
                    # Specifically named cards
                    or 'bloodforged battle' in row['name'].lower()
                    or 'court of vantress' in row['name'].lower()
                    or 'elmar, ulvenwald informant' in row['name'].lower()
                    or 'faerie artisans' in row['name'].lower()
                    or 'feldon of the third path' in row['name'].lower()
                    or 'lenoardo da vinci' in row['name'].lower()
                    or 'march of progress' in row['name'].lower()
                    or 'nexus of becoming' in row['name'].lower()
                    or 'osgir, the reconstructor' in row['name'].lower()
                    or 'prototype portal' in row['name'].lower()
                    or 'red sun\'s twilight' in row['name'].lower()
                    or 'saheeli, the sun\'s brilliance' in row['name'].lower()
                    or 'season of weaving' in row['name'].lower()
                    or 'shaun, father of synths' in row['name'].lower()
                    or 'sophia, dogged detective' in row['name'].lower()
                    or 'vaultborn tyrant' in row['name'].lower()
                    or 'wedding ring' in row['name'].lower()
                    ):
                    if 'transmutation font' not in row['name'].lower():
                        if 'fabricate' not in row['text'].lower():
                            tag_type = ['Artifact Tokens', 'Artifacts Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are non-predefined token generators have been tagged.\n')
        
        # Tagging cards that create predefined tokens (i.e. Treasure or Food)
        print('Checking for predefined tokens (i.e. Treasure or Food) generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if ('create' in row['text'].lower()):
                for artifact_token in artifact_tokens:
                    if (f'{artifact_token.lower()}' in row['text'].lower()):
                        
                        # Setting exclusions
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
                            
                        # Tagging cards
                        tag_type = ['Artifact Tokens', f'{artifact_token} Tokens', 'Artifacts Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
        print(f'\nCards in {color}_cards.csv that are predefined token generators have been tagged.\n')
        print(f'Cards in {color}_cards.csv that create or modify creation of Artifact tokens and don\'t have Fabricate have been tagged.\n')
        
        # Tag for Fabricate cards
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Artifact cards tagged in {color}_cards.csv.\n')

def tag_for_artifacts_matter():
    #tag_for_artifact()
    tag_for_artifact_tokens()
    for color in colors:
        print(f'Settings artifact token tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for artifacts matter
        print(f'Tagging cards in {color}_cards.csv that care about artifacts.\n')
        print(f'Tagging cards in {color}_cards.csv or reduce spell cost for or depending on number of artifacts.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # General cost reduction, search for any that say reduce by 1 - 10, or X
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
            
            # Affinity, imrpov, or other cost reduction
            if ('affinity for artifacts' in row['text'].lower()
                or 'improvise' in row['text'].lower()
                
                # Specifically named cards
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
            
            # Tagging for triggered abilities, replacement effects, or other
            # effects that care about artifacts (i.e. Metalcraft)
            if ('abilities of artifact' in row['text'].lower()
                or 'ability of artifact' in row['text'].lower()
                or 'affinity for artifacts' in row['text'].lower()
                or 'all artifact' in row['text'].lower()
                or 'another artifact' in row['text'].lower()
                or 'another target artifact' in row['text'].lower()
                or 'are artifacts in addition' in row['text'].lower()
                or 'artifact' in row['text'].lower()
                or 'artifact card' in row['text'].lower()
                or 'artifact creature you control' in row['text'].lower()
                or 'artifact creatures you control' in row['text'].lower()
                or 'artifact enters' in row['text'].lower()
                or 'artifact spells as though they had flash' in row['text'].lower()
                or 'artifact spells you cast' in row['text'].lower()
                or 'artifact with the highest mana value' in row['text'].lower()
                or 'artifact you control' in row['text'].lower()
                or 'artifacts you control' in row['text'].lower()
                or 'cast an artifact' in row['text'].lower()
                or 'choose an artifact' in row['text'].lower()
                or 'copy of any artifact' in row['text'].lower()
                or 'each artifact' in row['text'].lower()
                or 'mana cost among artifact' in row['text'].lower()
                or 'mana value among artifact' in row['text'].lower()
                or 'metalcraft' in row['text'].lower()
                or 'number of artifacts' in row['text'].lower()
                or 'number of other artifacts' in row['text'].lower()
                or 'number of tapped artifacts' in row['text'].lower()
                or 'number of artifact' in row['text'].lower()
                or 'prowess' in row['text'].lower()
                or 'search your library for an artifact' in row['text'].lower()
                or 'target artifact' in row['text'].lower()
                or 'whenever a nontoken artifact' in row['text'].lower()
                or 'whenever an artifact' in row['text'].lower()
                or 'whenever another nontoken artifact' in row['text'].lower()
                or 'whenever one or more artifact' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an artifact' in row['text'].lower()
                ):
                tag_type = ['Artifacts Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that care about other artifacts have been tagged.\n')
        
        # Overwrite file with artifacts matter tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Artifact matters cards tagged in {color}_cards.csv.\n')

def tag_equipment():
    # Iterate through each {color}_cards.csv file to find equipment cards
    # Also check for cards that care about equipments
    for color in colors:
        print(f'Settings "Equipment" type tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
                
                # Specifically named cards
                or 'alexios, deimos of kosmos' in row['name'].lower()
                or 'kosei, penitent warlord' in row['name'].lower()
                ):
                tag_type = ['Equipment Matters', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with equipment tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Cards that care about equipment in {color}_cards.csv have been tagged.\n')

# Enchantments
def tag_for_enchantment():
    # Iterate through each {color}_cards.csv file to find enchantment cards
    # Also check for cards that care about enchantments
    for color in colors:
        print(f'Settings "Enchantment" type tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Cards with the "Enchantment" type in {color}_cards.csv have been tagged.\n')

def tag_for_enchantment_tokens():
    for color in colors:
        print(f'Settings enchantment token tags on {color}_cards.csv.')
        
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
                if ('copy of enchanted enchantment' in row['text'].lower()
                    or 'copy of target enchantment' in row['text'].lower()
                    or 'copy of that enchantment' in row['text'].lower()
                    or 'enchantment creature token' in row['text'].lower()
                    or 'enchantment token' in row['text'].lower()
                    
                    # Specifically named cards 
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
        
        # Tagging for roles and shards
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
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Enchantment cards tagged in {color}_cards.csv.\n')

def tag_for_enchantments_matter():
    #tag_for_enchantment()
    tag_for_enchantment_tokens()
    for color in colors:
        print(f'Settings enchantment token tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for enchantments matter
        print(f'Tagging cards in {color}_cards.csv that care about enchantments.\n')
        print(f'Tagging cards in {color}_cards.csv or reduce spell cost for or depending on number of enchantments.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Tagging for cards that reduce enchantment costs or reduce spell costs based on number of enchantments
            for num in num_to_search:
                if (f'artifact and enchantment spells cost {{{num}}} less to cast' in row['text'].lower()
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
            
            # Excluding false positive
            if ('luxa river shrine' in row['name']
                ):
                continue
            
            # Tagging based on triggered effects or other effects that care about enchantments
            if ('abilities of enchantment' in row['text'].lower()
                or 'ability of enchantment' in row['text'].lower()
                or 'all artifact and enchantment' in row['text'].lower()
                or 'all enchantment' in row['text'].lower()
                or 'another enchantment' in row['text'].lower()
                or 'another target enchantment' in row['text'].lower()
                or 'are enchantments in addition' in row['text'].lower()
                or 'bestow' in row['text'].lower()
                or 'cast an enchantment' in row['text'].lower()
                or 'choose an enchantment' in row['text'].lower()
                or 'constellation' in row['text'].lower()
                or 'copy of any enchantment' in row['text'].lower()
                or 'each enchantment' in row['text'].lower()
                or 'eerie' in row['text'].lower()
                or 'enchantment' in row['text'].lower()
                or 'enchantment card' in row['text'].lower()
                or 'enchantment creature you control' in row['text'].lower()
                or 'enchantment creatures you control' in row['text'].lower()
                or 'enchantment enters' in row['text'].lower()
                or 'enchantment spells as though they had flash' in row['text'].lower()
                or 'enchantment spells you cast' in row['text'].lower()
                or 'enchantment with the highest mana value' in row['text'].lower()
                or 'enchantment you control' in row['text'].lower()
                or 'enchantments you control' in row['text'].lower()
                or 'mana cost among enchantment' in row['text'].lower()
                or 'mana value among enchantment' in row['text'].lower()
                or 'modified creature you control' in row['text'].lower()
                or 'number of aura' in row['text'].lower()
                or 'number of enchantment' in row['text'].lower()
                or 'other enchantment' in row['text'].lower()
                or 'prowess' in row['text'].lower()
                or 'return an enchantment' in row['text'].lower()
                or 'search your library for an artifact or enchantment' in row['text'].lower()
                or 'search your library for an aura' in row['text'].lower()
                or 'search your library for an enchantment' in row['text'].lower()
                or 'shrine' in row['text'].lower()
                or 'target enchantment' in row['text'].lower()
                or 'whenever a nontoken enchantment' in row['text'].lower()
                or 'wehenver an enchantment' in row['text'].lower()
                or 'whenever an aura' in row['text'].lower()
                or 'whenever another nontoken enchantment' in row['text'].lower()
                or 'whenever one or more enchantment' in row['text'].lower()
                or 'whenever you cast a noncreature' in row['text'].lower()
                or 'whenever you cast an artifact or enchantment' in row['text'].lower()
                or 'whenever you cast an enchantment' in row['text'].lower()
                or 'you may cast aura' in row['text'].lower()
                ):
                tag_type = ['Enchantments Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Cards in {color}_cards.csv that care about other enchantments have been tagged.\n')
        
        # Overwrite file with enchantments matter tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'enchantment matters cards tagged in {color}_cards.csv.\n')

def tag_auras():
    # Iterate through each {color}_cards.csv file to find aura cards
    # Also check for cards that care about auras
    for color in colors:
        print(f'Settings "Aura" type tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
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
                or 'enchanted creature' in row['text'].lower()
                or 'modified' in row['text'].lower()
                
                # Specifically named cards
                or 'alexios, deimos of kosmos' in row['name'].lower()
                or 'calix, guided by fate' in row['name'].lower()
                or 'equipped' in row['text'].lower()
                or 'gylwain, casting director' in row['name'].lower()
                or 'ivy, gleeful spellthief' in row['name'].lower()
                or 'killian, ink duelist' in row['name'].lower()
                or 'sithis, harvest\'s hand' in row['name'].lower()
                or 'tatsunari, toad rider' in row['name'].lower()
                or 'zur the enchanter' in row['name'].lower()
                ):
                tag_type = ['Auras Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with aura tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Cards that care about aura in {color}_cards.csv have been tagged.\n')

# Tokens
def tag_for_tokens():
    for color in colors:
        print(f'Settings token tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for other token creation
        print(f'Tagging cards in {color}_cards.csv that create or modify creation of tokens.')
        print('Checking for creature token generators.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Excluding false positives
            if ('fabricate' in row['text'].lower()
                or 'modular' in row['text'].lower()
                
                # Spefically named cards
                or 'agatha\'s soul cauldron' in row['name'].lower()
                ):
                continue
            
            # Tagging cards that create creature tokens
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
            
            # Excluding false positives
            if ('cloakwood swarmkeeper' in row['name'].lower()
                or 'neyali, sun\'s vanguard' in row['name'].lower()
                or 'staff of the storyteller' in row['name'].lower()
                ):
                continue
            
            # Tagging replacement effects (i.e. doublers, create different tokens instead, or additional tokens)
            if ('create one or more' in row['text']
                or 'one or more creature' in row['text']
                or 'one or more tokens would be created' in row['text']
                or 'one or more tokens would be put' in row['text']
                or 'one or more tokens would enter' in row['text']
                or 'one or more tokens you control' in row['text']
                or 'put one or more' in row['text']
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
        
        # Overwrite file with token tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Token cards tagged in {color}_cards.csv.\n')

# Life Matters
def tag_for_life_matters():
    for color in colors:
        print(f'Settings token tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for Life gain cares cards
        print(f'Tagging cards in {color}_cards.csv that gain life or care about life gain.')
        print('Checking for life gain cards.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Excluding replacement effects
            if ('if you would gain life' in row['text'].lower()
                or 'whenever you gain life' in row['text'].lower()
                ):
                continue
            
            # Tagging food token creation
            if ('food token' in row['text'].lower()
                or 'food' in row['type'].lower()):
                tag_type = ['Food Tokens', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
                continue
            
            # Tagging for cards that gain specific amounts of life between 1 - 10 and X
            for life_gained in num_to_search:
                if (f'gain {life_gained} life' in row['text'].lower()
                    or f'gains {life_gained} life' in row['text'].lower()):
                    tag_type = ['Lifegain', 'Life Matters']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                            
            # Tagging for cards that gain life
            if ('gain life' in row['text'].lower()
                or 'gains life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for cards that have or give lifelink
            if ('lifelink' in row['text'].lower()
                ):
                tag_type = ['Lifelink', 'Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for cards that gain life on life loss
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
            
            # Tagging for lifelink-like effects that aren't exactly lifelink
            if ('deals damage, you gain that much life' in row['text'].lower()
                ):
                tag_type = ['Lifegain', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for creature types that commonly care about life gain
            if ('Angel' in row['creatureTypes']
                or 'Bat' in row['creatureTypes']
                or 'Cleric' in row['creatureTypes']
                or 'Vampire' in row['creatureTypes']
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
            
            # Tagging for life gain triggers or modifiers
            if ('if you would gain life' in row['text'].lower()
                or 'whenever you gain life' in row['text'].lower()
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
            if ('Bat' in row['creatureTypes']
                or 'you lost life' in row['text'].lower()
                or 'you gained and lost life' in row['text'].lower()
                or 'you gained or lost life' in row['text'].lower()
                or 'you would lose life' in row['text'].lower()
                or 'you\'ve gained and lost life this turn' in row['text'].lower()
                or 'you\'ve lost life' in row['text'].lower()
                or 'whenever you gain or lose life' in row['text'].lower()
                or 'whenever you lose life' in row['text'].lower()
                ):
                tag_type = ['Lifeloss', 'Lifeloss Triggers', 'Life Matters']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        print(f'\nCards in {color}_cards.csv that modify life gain or trigger on life gain have been tagged.\n')
        
        # Overwrite file with Life tags added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'Life Matters cards tagged in {color}_cards.csv.\n')

# Counters
def tag_for_counters():
    # Iterate through each {color}_cards.csv file to find cards that add counters
    # Also check for cards that care about counters
    for color in colors:
        print(f'Settings "Counters Matter" tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for counters matter
        print(f'Tagging cards in {color}_cards.csv that fit the "Counters Matter" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Tagging for things that care about counters in general
            if ('choose a kind of counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'move a counter' in row['text'].lower()
                or 'one or more counters' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'remove a counter' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                
                # Specifically named cards
                or 'banner of kinship' in row['name'].lower()
                or 'damning verdict' in row['name'].lower()
                or 'ozolith' in row['name'].lower()
                ):
                tag_type = ['Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for specifically +1/+1
            if ('+1/+1 counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'one or more counter' in row['text'].lower()
                or 'one or more +1/+1 counter' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'undying' in row['text'].lower()
                or 'with counters on them' in row['text'].lower()
                
                # Specific creature types
                or 'Hydra' in row['creatureTypes']
                
                # Speficially named cards
                or 'damning verdict' in row['name'].lower()
                or 'ozolith' in row['name'].lower()
                ):
                tag_type = ['+1/+1 Counters', 'Counters Matter', 'Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for specifically -1/-1
            if ('-1/-1 counter' in row['text'].lower()
                or 'if it had counters' in row['text'].lower()
                or 'infect' in row['text'].lower()
                or 'one or more counter' in row['text'].lower()
                or 'one of more -1/-1 counter' in row['text'].lower()
                or 'persist' in row['text'].lower()
                or 'proliferate' in row['text'].lower()
                or 'wither' in row['text'].lower()
                
                # Specifically named cards
                or 'damning verdict' in row['name'].lower()
                ):
                tag_type = ['-1/-1 Counters', 'Counters Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tagging for other counters (i.e. oil, lore, etc...)
            for counter_type in counter_types:
                if f'{counter_type} counter'.lower() in row['text'].lower():
                    tag_type = [f'{counter_type} Counters', 'Counters Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with counters matter tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'"Counters Matter" themed cards in {color}_cards.csv have been tagged.\n')

# Voltron
def tag_for_voltron():
    tag_equipment()
    tag_auras()
    tag_for_counters()
    # Iterate through each {color}_cards.csv file to find voltron cards
    # Also check for cards that care about auras
    for color in colors:
        print(f'Settings "Voltron" tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for voltron
        print(f'Tagging cards in {color}_cards.csv that fit the "Voltron" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if 'Voltron' in row['themeTags']:
                continue
            
            # Tagging for specifically named cards
            if ('feather, the redeemed' in row['name'].lower()
                or 'kosei, penitent warlord' in row['name'].lower()
                or 'narset, enlightened master' in row['name'].lower()
                or 'rafiq of the many' in row['name'].lower()
                or 'raised by giants' in row['name'].lower()
                or 'rograkh, son of rohgahh' in row['name'].lower()
                or 'skullbriar, the walking grave' in row['name'].lower()
                or 'slicer, hired muscle' in row['name'].lower()
                or 'wilson, refined grizzly' in row['name'].lower()
                or 'yargle and multani' in row['name'].lower()
                or 'zurgo helmsmasher' in row['name'].lower()
                ):
                tag_type = ['Voltron']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with voltron tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'"Voltron" themed cards in {color}_cards.csv have been tagged.\n')

# Wheels
def tag_for_wheels():
    # Iterate through each {color}_cards.csv file to find wheel cards
    # Also check for cards that care about wheeling
    for color in colors:
        print(f'Settings "Wheels" tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for voltron
        print(f'Tagging cards in {color}_cards.csv that fit the "Wheels" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Define generalized wheel searches
            if ('an opponent draws a card' in row['text'].lower()
                or 'cards you\'ve drawn' in row['text'].lower()
                or 'delirium' in row['text'].lower()
                or 'descended' in row['text'].lower()
                or 'draw your second card' in row['text'].lower()
                or 'draw that many cards' in row['text'].lower()
                or 'draws an additional card' in row['text'].lower()
                or 'draws a card' in row['text'].lower()
                or 'draws cards' in row['text'].lower()
                or 'draws half that many cards' in row['text'].lower()
                or 'draws their first second card' in row['text'].lower()
                or 'draws their second second card' in row['text'].lower()
                or 'draw two cards instead' in row['text'].lower()
                or 'draws two additional cards' in row['text'].lower()
                or 'discards that card' in row['text'].lower()
                or 'discards their hand, then draws' in row['text'].lower()
                or 'each card your opponents have drawn' in row['text'].lower()
                or 'each draw a card' in row['text'].lower()
                or 'each opponent draws a card' in row['text'].lower()
                or 'each player draws' in row['text'].lower()
                or 'has no cards in hand' in row['text'].lower()
                or 'have no cards in hand' in row['text'].lower()
                or 'may draw a card' in row['text'].lower()
                or 'maximum hand size' in row['text'].lower()
                or 'mills' in row['text'].lower()
                or 'no cards in it, you win the game instead' in row['text'].lower()
                or 'opponent discards' in row['text'].lower()
                or 'threshold' in row['text'].lower()
                or 'you draw a card' in row['text'].lower()
                or 'whenever you draw a card' in row['text'].lower()
                ):
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Define specific cards that care about or could affect wheel, or draw cards
            if ('arcane denial' in row['name'].lower()
                or 'bloodchief ascension' in row['name'].lower()
                or 'bolas\'s citadel' in row['name'].lower()
                or 'dark deal' in row['name'].lower()
                or 'elenda and azor' in row['name'].lower()
                or 'elixir of immortality' in row['name'].lower()
                or 'esper sentinel' in row['name'].lower()
                or 'forced fruition' in row['name'].lower()
                or 'glunch, the bestower' in row['name'].lower()
                or 'icewind elemental' in row['name'].lower()
                or 'kiora the rising tide' in row['name'].lower()
                or 'kynaios and tiro of meletis' in row['name'].lower()
                or 'library of leng' in row['name'].lower()
                or 'loran of the third path' in row['name'].lower()
                or 'mr. foxglove' in row['name'].lower()
                or 'raffine, scheming seer' in row['name'].lower()
                or 'sauron, the dark lord' in row['name'].lower()
                or 'seizan, perverter of truth' in row['name'].lower()
                or 'sensei\'s divining top' in row['name'].lower()
                or 'the one ring' in row['name'].lower()
                or 'triskaidekaphile' in row['name'].lower()
                or 'twenty-toed toad' in row['name'].lower()
                or 'waste not' in row['name'].lower()
                or 'wedding ring' in row['name'].lower()
                or 'whirlwind of thought' in row['name'].lower()
                or 'whispering madness' in row['name'].lower()
                ):
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Add general card draw cards to the wheel tag
            if 'Card Draw' in row['themeTags']:
                tag_type = ['Card Draw', 'Wheels']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        
        # Overwrite file with wheels tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'"Wheels" themed cards in {color}_cards.csv have been tagged.\n')

# Lands matter
def tag_for_lands_matter():
    # Iterate through each {color}_cards.csv file to find lands matter cards
    for color in colors:
        print(f'Settings "Lands Matter" tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        # Tag for voltron
        print(f'Tagging cards in {color}_cards.csv that fit the "Lands Matter" theme.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Do generalized lands matter tags
            if ('copy of any land' in row['text'].lower()
                or 'desert card' in row['text'].lower()
                or 'everything counter' in row['text'].lower()
                or 'flood counter' in row['text'].lower()
                or 'forest dryad' in row['text'].lower()
                or 'forest lands' in row['text'].lower()
                or 'landfall' in row['text'].lower()
                or 'land card' in row['text'].lower()
                or 'land card from your graveyard' in row['text'].lower()
                or 'land card in your graveyard' in row['text'].lower()
                or 'land card is put into your graveyard' in row['text'].lower()
                or 'land cards' in row['text'].lower()
                or 'land cards from your graveyard' in row['text'].lower()
                or 'land cards in your graveyard' in row['text'].lower()
                or 'land cards put into your graveyard' in row['text'].lower()
                or 'land enters' in row['text'].lower()
                or 'lands you control' in row['text'].lower()
                or 'lands from your graveyard' in row['text'].lower()
                or 'nonbasic land type' in row['text'].lower()
                or 'number of lands you control' in row['text'].lower()
                or 'one or more land cards' in row ['text'].lower()
                or 'play a land' in row['text'].lower()
                or 'play an additional land' in row['text'].lower()
                or 'play lands from the top of your library' in row['text'].lower()
                or 'play two additional lands' in row['text'].lower()
                or 'plays a land' in row['text'].lower()
                or 'put a land card' in row['text'].lower()
                or 'return all land cards' in row['text'].lower()
                or 'sacrifice a land' in row['text'].lower()
                or 'search their library for a basic land card' in row['text'].lower()
                or 'search your library for a basic land card' in row['text'].lower()
                or 'search your library for a land card' in row['text'].lower()
                or 'search your library for up to two basic land card' in row['text'].lower()
                or 'target land' in row['text'].lower()
                or 'target land card' in row['text'].lower()
                or 'up to x land card' in row['text'].lower()
                ):
                tag_type = ['Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Add domain tags
            if ('domain' in row['text'].lower()
                ):
                tag_type = ['Domain', 'Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Add Landfall tags
            if ('landfall' in row['text'].lower()
                ):
                tag_type = ['Landfall', 'Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Do specifically card name lands matter tags
            if ('abundance' in row['name'].lower()
                or 'archdruid\'s charm' in row['name'].lower()
                or 'archelos, lagoon mystic' in row['name'].lower()
                or 'catacylsmic prospecting' in row['name'].lower()
                or 'coiling oracle' in row['name'].lower()
                or 'disorienting choice' in row['name'].lower()
                or 'eerie ultimatum' in row['name'].lower()
                or 'gitrog monster' in row['name'].lower()
                or 'mana reflection' in row['name'].lower()
                or 'nahiri\'s lithoforming' in row['name'].lower()
                or 'nine-fingers keene' in row['name'].lower()
                or 'open the way' in row['name'].lower()
                or 'realms uncharted' in row['name'].lower()
                or 'reshape the earth' in row['name'].lower()
                or 'scapeshift' in row['name'].lower()
                or 'yarok, the desecrated' in row['name'].lower()
                or 'wonderscape sage' in row['name'].lower()
                ):
                tag_type = ['Lands Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tag Urza lands
            if ('Land — Urza' in row['type']
                ):
                tag_type = ['Urzatron', 'Lands Matter']    
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Tag Snow lands
            if ('Snow Land' in row['type']
                ):
                tag_type = ['Snow Matters', 'Lands Matter']    
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
            
            # Define land types
            land_types = ['plains', 'island', 'swamp', 'mountain', 'forest', 'wastes',
                          'cave','desert', 'gate', 'lair', 'locus', 'sphere']
            
            # Search for cards that use the specific land types (i.e. fetches, reveal lands, etc...)
            for land_type in land_types:
                if (f'search your library for a {land_type}' in row['text'].lower()
                    or f'search your library for up to two {land_type}' in row['text'].lower()
                    or land_type.capitalize() in row['type']
                    ):
                    if ('azor\'s gateway' in row['name'].lower()
                        ):
                        continue
                    if land_type not in ['plains', 'wastes' 'locus']:
                        tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                    else:
                        tag_type = [f'{land_type.capitalize()} Matter', 'Lands Matter']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
                
                # Tag the cards that don't have types that could be in card names and unrelated
                # to their land type
                if land_type not in ['gate', 'sphere', 'lair', 'locus', 'cave']:
                    if (land_type in row['text'].lower()):
                        if land_type not in ['plains', 'wastes']:
                            tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                        else:
                            tag_type = [f'{land_type.capitalize()} Matter', 'Lands Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
                
                # Tag cards that do have types that could be in card names and unrelated to their
                # land types, with some refined logic to filter better filter out matches
                if land_type in ['gate', 'sphere', 'lair', 'locus', 'cave']:
                    if (f'or more {land_type.capitalize()}s' in row['text']
                        or f'{land_type.capitalize()}s' in row['text']
                        or f'a {land_type.capitalize()}' in row['text']
                        or f'{land_type.capitalize()} you control' in row['text']
                        ):
                        # Exclude specificall named cards
                        if ('Adarkar Wastes' in row['name']
                            or 'Afflicted Deserter'in row['name']
                            or 'Caves of Chaos Adventurer'in row['name']
                            or 'Caves of Koilos' in row['name']
                            or 'Cave People'in row['name']
                            or 'Gates of Istfell' in row['name']
                            or 'Gimli of the Glittering Caves'in row['name']
                            or 'Karplusan Forest' in row['name']
                            or 'Llanowar Wastes' in row['name']
                            or 'Mountain Titan' in row['name']
                            or 'Sea Gate Oracle' in row['name']
                            or 'Sea Gate Restoration'in row['name']
                            or 'Sea Gate Stormcaller'in row['name']
                            or 'Skyshroud Forest' in row['name']
                            or 'Sophina, Spearsage Deserter' in row['name']
                            or 'Swamp Mosquito'in row['name']
                            or 'Watcher of the Spheres' in row['name']
                            ):
                            continue
                        tag_type = [f'{land_type.capitalize()}s Matter', 'Lands Matter']
                        for tag in tag_type:
                            if tag not in theme_tags:
                                theme_tags.extend([tag])
                                df.at[index, 'themeTags'] = theme_tags
            
            # Define landwalk abilities
            land_types = ['plains', 'island', 'swamp', 'mountain', 'forest', 'nonbasic land', 'land']
            for land_type in land_types:
                if (f'{land_type}walk' in row['text'].lower()):
                    tag_type = [f'{land_type.capitalize()}walk']
                    for tag in tag_type:
                        if tag not in theme_tags:
                            theme_tags.extend([tag])
                            df.at[index, 'themeTags'] = theme_tags
            
        # Overwrite file with wheels tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'"Lands Matter" themed cards in {color}_cards.csv have been tagged.\n')

# Spells Matter
def tag_for_spellslinger():
    # Iterate through each {color}_cards.csv file to find spells matter cards
    for color in colors:
        print(f'Settings "Spells Matter" tags on {color}_cards.csv.')
        # Setup dataframe
        try:
            df = pd.read_csv(f'{csv_directory}/{color}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            print(f'{color}_cards.csv not found, regenerating it.')
            regenerate_csv_by_color(color)
        
        df['manaValue'] = df['manaValue'].astype(int)
        # Tag for storm
        print(f'Tagging cards in {color}_cards.csv that have the the storm keyword.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if pd.isna(row['keywords']):
                continue
            
            # Logic for storm cards
            if ('storm' in row['keywords'].lower()
                
                # In text if not in keywords
                or 'has storm' in row['text'].lower()
                or 'have storm' in row['text'].lower()
                ):
                tag_type = ['Storm', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Storm cards tagged in {color}_cards.csv.\n')
            
        # Logic for magecraft
        print(f'Checking {color}_cards.csv for Magecraft cards.')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            if pd.isna(row['keywords']):
                continue
            
            if ('magecraft' in row['keywords'].lower()
                ):
                tag_type = ['Magecraft', 'Spellslinger', 'Spells Matter']
                for tag in tag_type:
                    if tag not in theme_tags:
                        theme_tags.extend([tag])
                        df.at[index, 'themeTags'] = theme_tags
        print(f'Magecraft cards tagged in {color}_cards.csv.\n')
            
        # Logic for Cantrip cards
        print(f'Checking {color}_cards.csv for Cantrip cards.\n'
              'Note: I am considering a cantrip to be a card that has a mana value of 0-2,\n'
              'does some effect, and draws cards.\n'
              'This also includes activated abilities, that when the combined mana value\n'
              'and ability cost are less than 2 mana.\n')
        for index, row in df.iterrows():
            theme_tags = row['themeTags']
            if pd.isna(row['text']):
                continue
            
            # Take out Lands and Equipment
            if ('Land' in row['type']
                or 'Equipment' in row['type']):
                continue
            
            # Remove ones that have specific kewords
            if pd.notna(row['keywords']):
                if ('Channel' in row['keywords']
                    or 'Cycling' in row['keywords']
                    or 'Connive' in row['keywords']
                    or 'Learn' in row['keywords']
                    or 'Ravenous' in row['keywords']
                    ):
                    continue
            
            # Remove cards that loot or have loot effects
            if ('Loot' in row['themeTags']
                ):
                continue
            
            # Exclude specific cards
            if (# Specific cards
                'Archivist of Oghma' == row['name']
                or 'Argothian Enchantress' == row['name']
                or 'Audacity' == row['name']
                or 'Betrayal' == row['name']
                or 'Bequeathal' == row['name']
                or 'Blood Scrivener' == row['name']
                or 'Brigone, Soldier of Meletis' == row['name']
                or 'compost' == row['name']
                or 'Concealing Curtains // Revealing Eye' == row['name']
                or 'Cryptbreaker' == row['name']
                or 'Curiosity' == row['name']
                or 'Curse of Vengenace' == row['name']
                or 'Cryptex' == row['name']
                or 'Dakra Mystic' == row['name']
                or 'Dawn of a New Age' == row['name']
                or 'Dockside Chef' == row['name']
                or 'Dreamcatcher' == row['name']
                or 'Edgewall Innkeeper' == row['name']
                or 'Eidolon of Philosphy' == row['name']
                or 'Evolveld Sleeper' == row['name']
                or 'Femeref Enchantress' == row['name']
                or 'Finneas, Ace Archer' == row['name']
                or 'Flumph' == row['name']
                or 'Folk Hero' == row['name']
                or 'Frodo, Adventurous Hobbit' == row['name']
                or 'Goblin Artisans' == row['name']
                or 'Goldberry, River-Daughter' == row['name']
                or 'Gollum, Scheming Guide' == row['name']
                or 'Hatching Plans' == row['name']
                or 'Ideas Unbound' == row['name']
                or 'Ingenius Prodigy' == row['name']
                or 'Ior Ruin Expedition' == row['name']
                or 'Jace\'s Erasure' == row['name']
                or 'Keeper of the Mind' == row['name']
                or 'Kor Spiritdancer' == row['name']
                or 'Lodestone Bauble' == row['name']
                or 'Puresteel Paladin' == row['name']
                or 'Jeweled Bird' == row['name']
                or 'Mindblade Render' == row['name']
                or 'Multani\'s Presence' == row['name']
                or 'Nahiri\'s Lithoforming' == row['name']
                or 'Ordeal of Thassa' == row['name']
                or 'Pollywog Prodigy' == row['name']
                or 'Priest of Forgotten Gods' == row['name']
                or 'RAvenous Squirrel' == row['name']
                or 'Read the Runes' == row['name']
                or 'Red Death, Shipwrecker' == row['name']
                or 'Roil Cartographer' == row['name']
                or 'Sage of Lat-Nam' == row['name']
                or 'Saprazzan Heir' == row['name']
                or 'Scion of Halaster' == row['name']
                or 'See Beyond' == row['name']
                or 'Selhoff Entomber' == row['name']
                or 'Shielded Aether Thief' == row['name']
                or 'Shore Keeper' == row['name']
                or 'Silverquill Silencer' == row['name']
                or 'Soldevi Sage' == row['name']
                or 'Soldevi Sentry' == row['name']
                or 'Spiritual Focus' == row['name']
                or 'Sram, Senior Edificer' == row['name']
                or 'Staff of the Storyteller' == row['name']
                or 'Stirge' == row['name']
                or 'Sylvan Echoes' == row['name']
                or 'Sythis, Harvest\'s Hand' == row['name']
                or 'Sygg, River Cutthroat' == row['name']
                or 'Tenuous Truce' == row['name']
                or 'Test of Talents' == row['name']
                or 'Thalakos Seer' == row['name']
                or 'Tribute to Horobi // Echo of Death\'s Wail' == row['name']
                or 'Vampire Gourmand' == row['name']
                or 'Vampiric Rites' == row['name']
                or 'Vampirism' == row['name']
                or 'Vessel of Paramnesia' == row['name']
                or 'Witch\'s Cauldron' == row['name']
                or 'Wall of Mulch' == row['name']
                or 'Waste Not' == row['name']
                or 'Well Rested' == row['name']
                
                # Matching text or triggers
                or 'cast from exile, you draw a card' in row['text']
                or 'commit a crime, draw a card' in row['text']
                or 'deals damage to an opponent' in row['text'].lower()
                or 'deals combat damage to a player' in row['text'].lower()
                or 'deals combat damage to a player, you may draw a card' in row['text'].lower()
                or 'deals combat damage to a player, draw a card' in row['text'].lower()
                or 'deals combat damage to an opponent' in row['text'].lower()
                or 'first time this turn, draw' in row['text'].lower()
                or 'Gift a card' in row['text']
                or 'give a gift' in row['text'].lower()
                or 'then draw a card if it has' in row['text']
                or 'target of a spell, draw' in row['text']
                or 'target of a spell you control, draw' in row['text']
                or 'unless that player pays' in row['text']
                
                # Matches relating to skipping draws
                or 'draw step, instead you may skip' in row['text'].lower()
                or 'skip that draw' in row['text'].lower()
                ): 
                continue
            
            
            else:
                if (row['manaValue'] == 0
                or row['manaValue'] == 1
                or row['manaValue'] == 2
                ):
                    if ('draw a card' in row['text'].lower()
                        or 'draw a card.' in row['text'].lower()
                        or 'draw two cards' in row['text'].lower()
                        or 'draw three cards' in row['text'].lower()
                        or 'draw x cards' in row['text'].lower()
                        or 'draws a card' in row['text'].lower()
                        ):
                        if ('enters, draw a card' in row['text']
                            or 'enters, you draw a card' in row['text']
                            or 'enters, you may draw a card' in row['text']
                            
                            # Specific cards
                            or 'Cling to Dust' == row['name']
                            or 'Deduce' == row['name']
                            or 'Everdream' == row['name']
                            or 'Inverted Iceberg' == row['name']
                            or 'Lunar Rejection' == row['name']
                            or 'Open of the Sea' == row['name']
                            or 'Pawpatch Formation' == row['name']
                            or 'Scour All Possibilities' == row['name']
                            or 'Sleight of Hand' == row['name']
                            or 'Think Twice' == row['name']
                            or 'Train of Thought' == row['name']
                            or 'Whispers of the Muse' == row['name']
                            ):
                            tag_type = ['Cantrips', 'Spellslinger', 'Spells Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
                        elif ('{T}: Draw a card' in row['text']
                            or '{T}: Draw' in row['text']
                            or 'another legendary creature, draw a card' in row['text'].lower()
                            or 'artifact or land: draw' in row['text'].lower()
                            or 'Blood token' in row['text']
                            or 'creature you control, draw' in row['text'].lower()
                            or 'creature\'s toughness' in row['text'].lower()
                            or 'Clue' in row['type']
                            or 'dies, draw' in row['text']
                            or 'dies, choose one' in row['text']
                            or 'dies, you draw a card' in row['text']
                            or 'discard' in row['text'].lower()
                            or 'discard a card' in row['text'].lower()
                            or 'discard your hand' in row['text'].lower()
                            or 'each player may draw' in row['text'].lower()
                            or 'each other player' in row['text']
                            or 'each opponent. draw' in row['text'].lower()
                            or 'flip a coin' in row['text']
                            or 'if a player would draw' in row['text'].lower()
                            or 'if an opponent would draw' in row['text'].lower()
                            or 'if you would draw' in row['text'].lower()
                            or 'sacrifice a land: draw' in row['text'].lower()
                            or 'each player may draw' in row['text'].lower()
                            or 'opponent controls, draw' in row['text'].lower()
                            or 'opponent controls, you may draw' in row['text'].lower()
                            or 'or greater, draw a card' in row['text'].lower()
                            or 'this turn, draw a card' in row['text'].lower()
                            or 'turned face up, draw a card' in row['text'].lower()
                            or 'upkeep, each player draws' in row['text'].lower()
                            or 'you countrol: draw a card' in row['text'].lower()
                            or 'you may pay' in row['text']
                            or 'whenever an opponent draws a card' in row['text'].lower()
                            or f'{{1}}, Sacrifice {row['name']}: Draw a card' in row['text']
                            or f'{row['name']} dies' in row['text']
                            or f'{row['name']} dies, draw a card' in row['text']
                            or f'{row['name']} dies, you may draw a card' in row['text']
                            ):
                            continue
                        elif ('{1}' in row['text']
                                or '{2}' in row['text']
                                or '{3}' in row['text']
                                or '{4}' in row['text']
                                or '{5}' in row['text']
                                ):
                                ability_costs = [1, 2, 3]
                                for i in ability_costs:
                                    if (f'{{{i}}}' in row['text']
                                        or f'pay {i} life: draw' in row['text'].lower()
                                        ):
                                        if i + row['manaValue'] >= 3:
                                            continue     
                                        else:
                                            tag_type = ['Cantrips', 'Spellslinger', 'Spells Matter']
                                            for tag in tag_type:
                                                if tag not in theme_tags:
                                                    theme_tags.extend([tag])
                                                    df.at[index, 'themeTags'] = theme_tags
                        else:
                            tag_type = ['Cantrips', 'Spellslinger', 'Spells Matter']
                            for tag in tag_type:
                                if tag not in theme_tags:
                                    theme_tags.extend([tag])
                                    df.at[index, 'themeTags'] = theme_tags
        print(f'\nCantrip cards tagged in {color}_cards.csv.')
        
        # Overwrite file with Spells Matter tag added
        df.to_csv(f'{csv_directory}/{color}_cards.csv', index=False)
        print(f'"Spellslinger" themed cards in {color}_cards.csv have been tagged.\n')
               
#kindred_tagging()
"""setup_tags()
add_creatures_to_tags()
tag_for_card_types()
tag_for_artifacts_matter()
tag_for_enchantments_matter()
tag_for_card_draw()
tag_for_tokens()
tag_for_life_matters()"""
tag_for_voltron()
tag_for_wheels()
tag_for_lands_matter()

tag_for_spellslinger()
sort_theme_tags()