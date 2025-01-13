from __future__ import annotations

import pandas as pd # type: ignore
import requests # type: ignore
import inquirer.prompt # type: ignore
import logging

from settings import banned_cards, csv_directory, SETUP_COLORS, COLOR_ABRV, MTGJSON_API_URL
from setup_utils import download_cards_csv, filter_dataframe, process_legendary_cards

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    
    for card in banned_cards:
        filtered_df = filtered_df[~filtered_df['name'].str.contains(card)]
    
    card_types = ['Plane —', 'Conspiracy', 'Vanguard', 'Scheme', 'Phenomenon', 'Stickers', 'Attraction', 'Hero', 'Contraption']
    for card_type in card_types:
        filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type)]
    filtered_df['faceName'] = filtered_df['faceName'].fillna(filtered_df['name'])
    filtered_df.drop_duplicates(subset='faceName', keep='first', inplace=True)
    columns_to_keep = ['name', 'faceName','edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'layout', 'text', 'power', 'toughness', 'keywords', 'side']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.sort_values(by=['name', 'side'], key=lambda col: col.str.lower(), inplace=True)
        
    
    filtered_df.to_csv(new_csv_name, index=False)

def determine_commanders():
    print('Generating commander_cards.csv, containing all cards elligible to be commanders.')
    try:
        # Check for cards.csv
        cards_file = f'{csv_directory}/cards.csv'
        try:
            with open(cards_file, 'r', encoding='utf-8'):
                print('cards.csv exists.')
        except FileNotFoundError:
            print('cards.csv not found, downloading from mtgjson')
            download_cards_csv(MTGJSON_API_URL, cards_file)
            
        # Load and process cards data
        df = pd.read_csv(cards_file, low_memory=False)
        df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
        
        # Process legendary cards
        filtered_df = process_legendary_cards(df)
        
        # Apply standard filters
        filtered_df = filter_dataframe(filtered_df, banned_cards)
        
        # Save commander cards
        filtered_df.to_csv(f'{csv_directory}/commander_cards.csv', index=False)
        print('commander_cards.csv file generated.')
        
    except Exception as e:
        print(f'Error generating commander cards: {str(e)}')
        raise
    
def initial_setup():
    """Perform initial setup by downloading card data and creating filtered CSV files.
    
    This function:
    1. Downloads the latest card data from MTGJSON if needed
    2. Creates color-filtered CSV files
    3. Generates commander-eligible cards list
    
    Uses utility functions from setup_utils.py for file operations and data processing.
    Implements proper error handling for file operations and data processing.
    """
    logger.info('Checking for cards.csv file')
    
    try:
        cards_file = f'{csv_directory}/cards.csv'
        try:
            with open(cards_file, 'r', encoding='utf-8'):
                logger.info('cards.csv exists')
        except FileNotFoundError:
            logger.info('cards.csv not found, downloading from mtgjson')
            download_cards_csv(MTGJSON_API_URL, cards_file)

        df = pd.read_csv(cards_file, low_memory=False)
        df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')

        logger.info('Checking for color identity sorted files')
        
        for i in range(min(len(SETUP_COLORS), len(COLOR_ABRV))):
            logger.info(f'Checking for {SETUP_COLORS[i]}_cards.csv')
            try:
                with open(f'{csv_directory}/{SETUP_COLORS[i]}_cards.csv', 'r', encoding='utf-8'):
                    logger.info(f'{SETUP_COLORS[i]}_cards.csv exists')
            except FileNotFoundError:
                logger.info(f'{SETUP_COLORS[i]}_cards.csv not found, creating one')
                filter_by_color(df, 'colorIdentity', COLOR_ABRV[i], f'{csv_directory}/{SETUP_COLORS[i]}_cards.csv')

        # Generate commander list
        determine_commanders()

    except Exception as e:
        logger.error(f'Error during initial setup: {str(e)}')
        raise
    
def regenerate_csvs_all():
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
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)#, converters={'printings': pd.eval})
    
    # Set frames that have nothing for color identity to be 'Colorless' instead
    df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
    
    rows_to_drop = []
    non_legel_sets = ['PHTR', 'PH17', 'PH18' ,'PH19', 'PH20', 'PH21', 'UGL', 'UND', 'UNH', 'UST',]
    for index, row in df.iterrows():
        for illegal_set in non_legel_sets:
            if illegal_set in row['printings']:
                rows_to_drop.append(index)
    df = df.drop(rows_to_drop)
    
    # Color identity sorted cards
    print('Regenerating color identity sorted files.\n')
    
    # For loop to iterate through the colors
    for i in range(min(len(SETUP_COLORS), len(COLOR_ABRV))):
        print(f'Regenerating {SETUP_COLORS[i]}_cards.csv.')
        filter_by_color(df, 'colorIdentity', COLOR_ABRV[i], f'csv_files/{SETUP_COLORS[i]}_cards.csv')
        print(f'A new {SETUP_COLORS[i]}_cards.csv file has been made.\n')

    # Once files are regenerated, create a new legendary list
    determine_commanders()

def regenerate_csv_by_color(color):
    """
    Pull the original cards.csv file and remake the {color}_cards.csv files
    """
    # Determine the color_abv to use
    COLOR_ABRV_index = SETUP_COLORS.index(color)
    color_abv = COLOR_ABRV[COLOR_ABRV_index]
    print('Downloading cards.csv from mtgjson')
    url = 'https://mtgjson.com/api/v5/csv/cards.csv'
    r = requests.get(url)
    with open(f'{csv_directory}/cards.csv', 'wb') as outputfile:
        outputfile.write(r.content)
    # Load cards.csv file into pandas dataframe so it can be further broken down
    df = pd.read_csv(f'{csv_directory}/cards.csv', low_memory=False)
    
    # Set frames that have nothing for color identity to be 'Colorless' instead
    df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
    
    # Color identity sorted cards
    print(f'Regenerating {color}_cards.csv file.\n')
    
    # Regenerate the file
    print(f'Regenerating {color}_cards.csv.')
    filter_by_color(df, 'colorIdentity', color_abv, f'{csv_directory}/{color}_cards.csv')
    print(f'A new {color}_cards.csv file has been made.\n')

    # Once files are regenerated, create a new legendary list
    determine_commanders()

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
            regenerate_csvs_all()
            break    
            # Go back
        while choice == 'Back':
            break
        break

initial_setup()