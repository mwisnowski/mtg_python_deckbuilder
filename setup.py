from __future__ import annotations

import pandas as pd # type: ignore
import requests # type: ignore

from settings import banned_cards

staple_lists = ['Colorless', 'White', 'Blue', 'Black']
colorless_staples = [] # type: ignore
white_staples = [] # type: ignore
blue_staples = [] # type: ignore
black_staples = [] # type: ignore  

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
    filtered_df = filtered_df[filtered_df['layout'].str.contains('reversible_card') == False]
    filtered_df = filtered_df[filtered_df['availability'].str.contains('arena') == False]
    filtered_df.drop_duplicates(subset='name', keep='first', inplace=True)
    columns_to_keep = ['name', 'edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'text', 'power', 'toughness']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.sort_values(by='name', key=lambda col: col.str.lower(), inplace=True)
    filtered_df.to_csv(new_csv_name, index=False)
    
def determine_legendary():
    # Filter dataframe
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
    filtered_df = filtered_df[filtered_df['layout'].str.contains('reversible_card') == False]
    filtered_df = filtered_df[filtered_df['availability'].str.contains('arena') == False]
    filtered_df.drop_duplicates(subset='name', keep='first', inplace=True)
    columns_to_keep = ['name', 'edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'text', 'power', 'toughness']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.sort_values(by='name', key=lambda col: col.str.lower(), inplace=True)
    filtered_df.to_csv('csv_files/legendary_cards.csv', index=False)

def initial_setup():
    # Check if the overall cards.csv file exists
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
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    df['colorIdentity'] = df['colorIdentity'].fillna('None')

    # Checking for and creating individual color identity sorted csvs
    print('Checking for color identity sorted files.\n')
    
    # Colorless
    print('Checking for colorless_cards.csv.\n')
    while True:
        try:
            with open('csv_files/colorless_cards.csv', 'r', encoding='utf-8'):
                print('colorless_cards.csv exists.\n')
                break
        except FileNotFoundError:
            print('colorless_cards.csv not found, creating it.\n')
            filter_by_color(df, 'colorIdentity', 'None', 'csv_files/colorless_cards.csv')
    print('Checking for mono-color card lists.\n')
    while True:
        print('Checking for white_cards.csv.')
        while True:
            try:
                with open('csv_files/white_cards.csv', 'r', encoding='utf-8'):
                    print('white_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('white_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'W', 'csv_files/white_cards.csv')
        print('Checking for blue_cards.csv.')
        while True:
            try:
                with open('csv_files/blue_cards.csv', 'r', encoding='utf-8'):
                    print('blue_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('blue_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'U', 'csv_files/blue_cards.csv')
        print('Checking for black_cards.csv.')
        while True:
            try:
                with open('csv_files/black_cards.csv', 'r', encoding='utf-8'):
                    print('black_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('black_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B', 'csv_files/black_cards.csv')
        print('Checking for red_cards.csv.')
        while True:
            try:
                with open('csv_files/red_cards.csv', 'r', encoding='utf-8'):
                    print('red_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('red_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'R', 'csv_files/red_cards.csv')
        print('Checking for green_cards.csv.')
        while True:
            try:
                with open('csv_files/green_cards.csv', 'r', encoding='utf-8'):
                    print('green_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('green_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G', 'csv_files/green_cards.csv')
        break
    print('Checking for color-pair lists.\n')
    while True:
        print('Checking for azorius_cards.csv.')
        while True:
            try:
                with open('csv_files/azorius_cards.csv', 'r', encoding='utf-8'):
                    print('azorius_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('azorius_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'U, W', 'csv_files/azorius_cards.csv')
        print('Checking for orzhov_cards.csv.')
        while True:
            try:
                with open('csv_files/orzhov_cards.csv', 'r', encoding='utf-8'):
                    print('orzhov_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('orzhov_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, W', 'csv_files/orzhov_cards.csv')
        print('Checking for boros_cards.csv.')
        while True:
            try:
                with open('csv_files/boros_cards.csv', 'r', encoding='utf-8'):
                    print('boros_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('boros_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'R, W', 'csv_files/boros_cards.csv')
        print('Checking for selesnya_cards.csv.')
        while True:
            try:
                with open('csv_files/selesnya_cards.csv', 'r', encoding='utf-8'):
                    print('selesnya_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('selesnya_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, W', 'csv_files/selesnya_cards.csv')
        print('Checking for dimir_cards.csv.')
        while True:
            try:
                with open('csv_files/dimir_cards.csv', 'r', encoding='utf-8'):
                    print('dimir_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('dimir_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, U', 'csv_files/dimir_cards.csv')
        print('Checking for izzet_cards.csv.')
        while True:
            try:
                with open('csv_files/izzet_cards.csv', 'r', encoding='utf-8'):
                    print('izzet_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('izzet_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'R, U', 'csv_files/izzet_cards.csv')
        print('Checking for simic_cards.csv.')
        while True:
            try:
                with open('csv_files/simic_cards.csv', 'r', encoding='utf-8'):
                    print('simic_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('simic_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, U', 'csv_files/simic_cards.csv')
        print('Checking for rakdos_cards.csv.')
        while True:
            try:
                with open('csv_files/rakdos_cards.csv', 'r', encoding='utf-8'):
                    print('rakdos_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('rakdos_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, R', 'csv_files/rakdos_cards.csv')
        print('Checking for golgari_cards.csv.')
        while True:
            try:
                with open('csv_files/golgari_cards.csv', 'r', encoding='utf-8'):
                    print('golgari_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('golgari_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G', 'csv_files/golgari_cards.csv')
        print('Checking for gruul_cards.csv.')
        while True:
            try:
                with open('csv_files/gruul_cards.csv', 'r', encoding='utf-8'):
                    print('gruul_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('gruul_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, R', 'csv_files/gruul_cards.csv')
        break
    print('Checking for three-color sets.\n')
    while True:
        print('Checking for bant_cards.csv.')
        while True:
            try:
                with open('csv_files/bant_cards.csv', 'r', encoding='utf-8'):
                    print('bant_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('bant_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, U, W', 'csv_files/bant_cards.csv')
        print('Checking for esper_cards.csv.')
        while True:
            try:
                with open('csv_files/esper_cards.csv', 'r', encoding='utf-8'):
                    print('esper_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('esper_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, U, W', 'csv_files/esper_cards.csv')
        print('Checking for grixis_cards.csv.')
        while True:
            try:
                with open('csv_files/grixis_cards.csv', 'r', encoding='utf-8'):
                    print('grixis_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('grixis_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, R, U', 'csv_files/grixis_cards.csv')
        print('Checking for jund_cards.csv.')
        while True:
            try:
                with open('csv_files/jund_cards.csv', 'r', encoding='utf-8'):
                    print('jund_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('jund_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, R', 'csv_files/jund_cards.csv')
        print('Checking for naya_cards.csv.')
        while True:
            try:
                with open('csv_files/naya_cards.csv', 'r', encoding='utf-8'):
                    print('naya_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('naya_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, R, W', 'csv_files/naya_cards.csv')
        print('Checking for abzan_cards.csv.')
        while True:
            try:
                with open('csv_files/abzan_cards.csv', 'r', encoding='utf-8'):
                    print('abzan_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('abzan_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, W', 'csv_files/abzan_cards.csv')
        print('Checking for jeskai_cards.csv.')
        while True:
            try:
                with open('csv_files/jeskai_cards.csv', 'r', encoding='utf-8'):
                    print('jeskai_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('jeskai_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'R, U, W', 'csv_files/jeskai_cards.csv')
        print('Checking for mardu_cards.csv.')
        while True:
            try:
                with open('csv_files/mardu_cards.csv', 'r', encoding='utf-8'):
                    print('mardu_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('mardu_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, R, W', 'csv_files/mardu_cards.csv')
        print('Checking for sultai_cards.csv.')
        while True:
            try:
                with open('csv_files/sultai_cards.csv', 'r', encoding='utf-8'):
                    print('sultai_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('sultai_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, U', 'csv_files/sultai_cards.csv')
        print('Checking for temur_cards.csv.')
        while True:
            try:
                with open('csv_files/temur_cards.csv', 'r', encoding='utf-8'):
                    print('temur_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('temur_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, R, U', 'csv_files/temur_cards.csv')
        break
    print('Checking for four color sets.\n')
    while True:
        print('Checking for dune_cards.csv.')
        while True:
            try:
                with open('csv_files/dune_cards.csv', 'r', encoding='utf-8'):
                    print('dune_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('dune_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, R, W', 'csv_files/dune_cards.csv')
        print('Checking for glint_cards.csv.')
        while True:
            try:
                with open('csv_files/glint_cards.csv', 'r', encoding='utf-8'):
                    print('glint_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('glint_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, R, U', 'csv_files/glint_cards.csv')
        print('Checking for ink_cards.csv.')
        while True:
            try:
                with open('csv_files/ink_cards.csv', 'r', encoding='utf-8'):
                    print('ink_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('ink_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'G, R, U, W', 'csv_files/ink_cards.csv')
        print('Checking for witch_cards.csv.')
        while True:
            try:
                with open('csv_files/witch_cards.csv', 'r', encoding='utf-8'):
                    print('witch_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('witch_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, G, U, W', 'csv_files/witch_cards.csv')
        print('Checking for yore_cards.csv.')
        while True:
            try:
                with open('csv_files/yore_cards.csv', 'r', encoding='utf-8'):
                    print('yore_cards.csv exists.\n')
                    break
            except FileNotFoundError:
                print('yore_cards.csv not found, creating it.')
                filter_by_color(df, 'colorIdentity', 'B, R, U, W', 'csv_files/yore_cards.csv')
        break
    print('Checking for wubrg_cards.csv.\n')
    while True:
        try:
            with open('csv_files/wubrg_cards.csv', 'r', encoding='utf-8'):
                print('wubrg_cards.csv exists.\n')
                break
        except FileNotFoundError:
            print('wubrg_cards.csv not found, creating it.')
            filter_by_color(df, 'colorIdentity', 'B, G, R, U, W', 'csv_files/wubrg_cards.csv')
            
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
    df = pd.read_csv('csv_files/cards.csv', low_memory=False)
    df['colorIdentity'] = df['colorIdentity'].fillna('None')
    
    # Color identity sorted cards
    print('Regenerating color identity sorted files.\n')
    print('Regenerating colorless_cards.csv.')
    
    # Colorless
    cards = 'colorless'
    print(f'Regenerating {cards}_cards.csv.')
    filter_by_color(df, 'colorIdentity', 'None', f'csv_files/{cards}_cards.csv')
    print(f'A new {cards}_cards.csv file has been made\n')
    
    # Mono color
    print('Regenerating mono-color card lists.\n')
    while True:
        # White cards
        cards = 'white'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Blue cards
        cards = 'blue'
        print('Regenerating blue_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
            
        # Black cards
        cards = 'black'
        print('Regenerating black_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Red cards
        cards = 'red'
        print('Regenerating red_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'R', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Green cards
        cards = 'green'
        print('Regenerating green_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        break
    
    # Color pairs
    print('Regenerating color-pair lists.\n')
    while True:
        # Azorius cards
        cards = 'azorius'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
            
        # Orzhov cards
        cards = 'orzhov'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
                
        # Boros cards
        cards = 'boros'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'R, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Selesnya
        cards = 'selesnya'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Dimir
        cards = 'dimir'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Izzet
        cards = 'izzet'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'R, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
                
        # Simic
        cards = 'Simic'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Rakdos
        cards = 'rakdos'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, R', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Golgari
        cards = 'golgari'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Gruul
        cards = 'gruul'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, R', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        break
    
    # Color trios
    print('Regenerating three-color sets.\n')
    while True:
        # Bant
        cards = 'Bant'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
            
        # Esper
        cards = 'esper'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Grixis
        cards = 'grixis'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, R, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Jund
        cards = 'jund'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, R', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Naya
        cards = 'naya'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, R, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Abzan
        cards = 'abzan'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Jeskai
        cards = 'jeskai'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'R, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Mardu
        cards = 'mardu'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, R, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Sultai
        cards = 'sultai'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Temur
        cards = 'temur'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, R, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        break
    
    # Four color
    print('Regenerating four color sets.\n')
    while True:
        # Dune
        cards = 'dune'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, R, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Glint
        cards = 'glint'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, R, U', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Ink
        cards = 'ink'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'G, R, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Witch
        cards = 'witch'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, G, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        
        # Yore
        cards = 'yore'
        print(f'Regenerating {cards}_cards.csv.')
        filter_by_color(df, 'colorIdentity', 'B, R, U, W', f'csv_files/{cards}_cards.csv')
        print(f'A new {cards}_cards.csv file has been made\n')
        break
    
    # WUBRG
    cards = 'wubrg'
    print(f'Regenerating {cards}_cards.csv.')
    filter_by_color(df, 'colorIdentity', 'B, G, R, U, W', f'csv_files/{cards}_cards.csv')
    print(f'A new {cards}_cards.csv file has been made\n')
 
def generate_staple_lists():
    colors = ['colorless', 'white', 'blue', 'black', 'green', 'red',
              'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
              'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
              'bant', 'esper', 'grixis', 'jund', 'naya',
              'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
              'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg']
    
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
                    
