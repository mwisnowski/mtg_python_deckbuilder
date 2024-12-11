from __future__ import annotations

import pandas as pd # type: ignore
import requests # type: ignore
import inquirer.prompt # type: ignore

from settings import banned_cards

colors = ['colorless', 'white', 'blue', 'black', 'green', 'red',
          'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
          'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
          'bant', 'esper', 'grixis', 'jund', 'naya',
          'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
          'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg']
color_abrv = ['Colorless', 'W', 'U', 'B', 'G', 'R',
              'U, W', 'B, W', 'G, W', 'R, W', 'B, U',
              'G, U', 'R, U', 'B, G', 'B, R', 'G, R',
              'G, U, W', 'B, U, W', 'B, R, U', 'B, G, R', 'G, R, W',
              'B, G, W', 'R, U, W', 'B, R, W', 'B, G, U', 'G, R, U',
              'B, G, R, W', 'B, G, R, U', 'G, R, U, W', 'B, G, U, W',
              'B, R, U, W', 'B, G, R, U, W']

def filter_by_color(df, column_name, value, new_csv_name):
    # Filter dataframe
    filtered_df = df[df[column_name] == value]
    """
    Save the filtered dataframe to a new csv file, and narrow down/rearranges the columns it
    keeps to increase readability/trim some extra data.
    Additionally attempts to remove as many duplicates (including cards with reversible prints,
    as well as taking out Arena-only cards.
    """
    filtered_df.sort_values('name')
    filtered_df = filtered_df.loc[filtered_df['layout'] != 'reversible_card'] 
    filtered_df = filtered_df[filtered_df['availability'].str.contains('paper')]
    filtered_df = filtered_df.loc[filtered_df['promoTypes'] != 'playtest']
    filtered_df = filtered_df.loc[filtered_df['securityStamp'] != 'heart']
    filtered_df = filtered_df.loc[filtered_df['securityStamp'] != 'acorn']
    
    card_types = ['Plane —', 'Conspiracy', 'Vanguard', 'Scheme', 'Phenomena', 'Stickers', 'Attraction']
    for card_type in card_types:
        filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type)]
    filtered_df['faceName'] = filtered_df['faceName'].fillna(filtered_df['name'])
    filtered_df.drop_duplicates(subset='faceName', keep='first', inplace=True)
    columns_to_keep = ['name', 'faceName','edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'text', 'power', 'toughness']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.sort_values(by='name', key=lambda col: col.str.lower(), inplace=True)
    filtered_df.to_csv(new_csv_name, index=False)
    
def determine_legendary():
    print('Generating legendary_cards.csv, containing all Legendary Creatures elligible to be commanders.')
    # Filter dataframe
    while True:
        try:
            with open('csv_files/cards.csv', 'r', encoding='utf-8'):
                break
        except FileNotFoundError:
            initial_setup()
        
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    legendary_options = ['Legendary Creature', 'Legendary Artifact Creature', 'Legendary Enchantment Creature']
    filtered_df = df[df['type'].str.contains('|'.join(legendary_options))]
    """
    Save the filtered dataframe to a new csv file, and narrow down/rearranges the columns it
    keeps to increase readability/trim some extra data.
    Additionally attempts to remove as many duplicates (including cards with reversible prints,
    as well as taking out Arena-only cards.
    """
    filtered_df.sort_values('name')
    filtered_df = filtered_df.loc[filtered_df['layout'] != 'reversible_card'] 
    filtered_df = filtered_df[filtered_df['availability'].str.contains('paper')]
    filtered_df = filtered_df.loc[filtered_df['promoTypes'] != 'playtest']
    filtered_df = filtered_df.loc[filtered_df['securityStamp'] != 'heart']
    filtered_df = filtered_df.loc[filtered_df['securityStamp'] != 'acorn']
    
    card_types = ['Plane —', 'Conspiracy', 'Vanguard', 'Scheme', 'Phenomena', 'Stickers', 'Attraction']
    for card_type in card_types:
        filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type)]
    filtered_df['faceName'] = filtered_df['faceName'].fillna(filtered_df['name'])
    filtered_df.drop_duplicates(subset='faceName', keep='first', inplace=True)
    columns_to_keep = ['name', 'faceName','edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'text', 'power', 'toughness']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.sort_values(by='name', key=lambda col: col.str.lower(), inplace=True)
    filtered_df.to_csv('csv_files/legendary_cards.csv', index=False)
    print('legendary_cards.csv file generated.')

def initial_setup():
    print('Checking for cards.csv file.\n')
    while True:
        try:
            with open('csv_files/cards.csv', 'r', encoding='utf-8'):
                print('cards.csv exists.')
                break
        except FileNotFoundError:
            # If the cards.csv file does not exist or can't be found, pull it from mtgjson.com
            print('cards.csv not found, downloading from mtgjson')
            url = 'https://mtgjson.com/api/v5/csv/cards.csv'
            r = requests.get(url)
            with open('csv_files/cards.csv', 'wb') as outputfile:
                outputfile.write(r.content)
    
    # Load cards.csv file into pandas dataframe so it can be further broken down
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    
    # Set frames that have nothing for color identity to be 'Colorless' instead
    df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
    
    # Check for and create missing, individual color identity sorted CSVs
    print('Checking for color identity sorted files.\n')
    
    # For loop to iterate through the colors
    for i in range(len(colors), len(color_abrv)):
        print(f'Checking for {colors[i]}_cards.csv.')
        try:
            with open(f'csv_files/{colors[i]}_cards.csv', 'r', encoding='utf-8'):
                print(f'{colors[i]}_cards.csv exists.\n')
        except FileNotFoundError:
            print(f'{colors[i]}_cards.csv not found, creating one.\n')
            filter_by_color(df, 'colorIdentity', color_abrv[i], f'csv_files/{colors[i]}_cards.csv')
    
    # Once by-color lists have been made, Determine legendary creatures
    determine_legendary()
    
    # Once Legendary creatures are determined, generate staple lists
    # generate_staple_lists()
    
def regenerate_csvs():
    """
    Pull the original cards.csv file and remake the {color}_cards.csv files.
    This is useful if a new set has since come out to ensure the databases are up-to-date
    """
    print('Downloading cards.csv from mtgjson')
    url = 'https://mtgjson.com/api/v5/csv/cards.csv'
    r = requests.get(url)
    with open('csv_files/cards.csv', 'wb') as outputfile:
        outputfile.write(r.content)
    # Load cards.csv file into pandas dataframe so it can be further broken down
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    
    # Set frames that have nothing for color identity to be 'Colorless' instead
    df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
    
    # Color identity sorted cards
    print('Regenerating color identity sorted files.\n')
    
    # For loop to iterate through the colors
    for i in range(min(len(colors), len(color_abrv))):
        print(f'Regenerating {colors[i]}_cards.csv.')
        filter_by_color(df, 'colorIdentity', color_abrv[i], f'csv_files/{colors[i]}_cards.csv')
        print(f'A new {colors[i]}_cards.csv file has been made.\n')

    # Once files are regenerated, create a new legendary list
    determine_legendary()

def generate_staple_lists():    
    for color in colors:
        staples = []
        print(f'Checking for {color} staples file.')
        try:
            with open(f'staples/{color}.txt', 'r') as file:
                staples = file.read().split('\n')
                del staples[-1]
                print(f'{color.capitalize()} staples:')
                print('\n'.join(staples), '\n')
                
        except FileNotFoundError:
            print(f'{color.capitalize()} staples file not found.')
            print(f'Generating {color} staples list.')
            df = pd.read_csv(f'csv_files/{color}_cards.csv')
            df['edhrecRank'] = pd.to_numeric(df['edhrecRank'], downcast='integer', errors='coerce')
            df = df.dropna(subset=['edhrecRank'])
            df['edhrecRank'] = df['edhrecRank'].astype(int)
            columns_to_keep = ['name', 'edhrecRank', 'type']
            df = df[columns_to_keep]
            df.sort_values(by='edhrecRank', key=lambda col: col, inplace=True)
            i = 1
            y = 0
            while len(staples) < 20 and y < len(df):
                for index, row in df.iterrows():
                    if row['edhrecRank'] == i:
                        if 'Land' not in row['type'] and row['name'] not in banned_cards:
                            staples.append(row['name'])
                i += 1
                y += 1
            with open(f'staples/{color}.txt', 'w') as f:
                for items in staples:
                    f.write('%s\n' %items)

def add_tags():
    pass
                    
def setup():
    while True:
        print('Which setup  operation would you like to perform?\n'
              'If this is your first time setting up, do the initial setup.\n'
              'If you\'ve done the basic setup before, you can regenerate the CSV files\n')
        
        choice = 'Menu'
        while choice == 'Menu':
            question = [
                inquirer.List('menu',
                              choices=['Initial Setup', 'Regenerate CSV Files', 'Back'],
                              carousel=True)
            ]
            answer = inquirer.prompt(question)
            choice = answer['menu']
        
        # Run through initial setup
        while choice == 'Initial Setup':
            initial_setup()
            break
        
        # Regenerate CSV files
        while choice == 'Regenerate CSV Files':
            regenerate_csvs()
            break    
            # Go back
        while choice == 'Back':
            break
        break

#setup()