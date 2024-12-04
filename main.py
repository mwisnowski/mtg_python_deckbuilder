from __future__ import annotations

#import os
import requests # type: ignore
import pandas as pd # type: ignore
#import scrython # type: ignore

def filter_by_color(df, column_name, value, new_csv_name):
    # Filter dataframe
    filtered_df = df[df[column_name] == value]
    # Save the filtered dataframe to a new csv file
    columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.drop_duplicates(subset='name', inplace=True)
    filtered_df.to_csv(new_csv_name, index=False)

def initial_setup():
    # Check if the overall cards.csv file exists
    print('Checking if setup was previously finished.')
    while True:
        try:
            with open('setup_done.txt', 'r') as setup:
                setup.close()
                print('Setup is done.')
                break
        except FileNotFoundError:
            print('Checking for cards.csv file.')
            while True:
                try:
                    with open('csv_files/cards.csv', 'r', encoding='utf-8'):
                        print('cards.csv exists.')
                        break
                except FileNotFoundError:
                    print('cards.csv not found, downloading from mtgjson')
                    url = 'https://mtgjson.com/api/v5/csv/cards.csv'
                    r = requests.get(url)
                    with open('csv_files/cards.csv', 'wb') as outputfile:
                        outputfile.write(r.content)
            df = pd.read_csv('cards.csv', dtype='unicode')
            df['colorIdentity'] = df['colorIdentity'].fillna('None')

            print('Checking for color identity sorted files.')
            print('Checking for colorless_cards.csv.')
            while True:
                try:
                    with open('csv_files/colorless_cards.csv', 'r', encoding='utf-8'):
                        print('colorless_cards.csv exists.')
                        break
                except FileNotFoundError:
                    print('colorless_cards.csv not found, creating it.')
                    filter_by_color(df, 'colorIdentity', 'None', 'csv_files/colorless_cards.csv')
            print('Checking for mono-color card lists.')
            while True:
                print('Checking for white_cards.csv.')
                while True:
                    try:
                        with open('csv_files/white_cards.csv', 'r', encoding='utf-8'):
                            print('white_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('white_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'W', 'csv_files/white_cards.csv')
                print('Checking for blue_cards.csv.')
                while True:
                    try:
                        with open('csv_files/blue_cards.csv', 'r', encoding='utf-8'):
                            print('blue_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('blue_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'U', 'csv_files/blue_cards.csv')
                print('Checking for black_cards.csv.')
                while True:
                    try:
                        with open('csv_files/black_cards.csv', 'r', encoding='utf-8'):
                            print('black_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('black_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B', 'csv_files/black_cards.csv')
                print('Checking for red_cards.csv.')
                while True:
                    try:
                        with open('csv_files/red_cards.csv', 'r', encoding='utf-8'):
                            print('red_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('red_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'R', 'csv_files/red_cards.csv')
                print('Checking for green_cards.csv.')
                while True:
                    try:
                        with open('csv_files/green_cards.csv', 'r', encoding='utf-8'):
                            print('green_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('green_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G', 'csv_files/green_cards.csv')
                break
            print('Checking for color-pair lists')
            while True:
                print('Checking for azorius_cards.csv.')
                while True:
                    try:
                        with open('csv_files/azorius_cards.csv', 'r', encoding='utf-8'):
                            print('azorius_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('azorius_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'U, W', 'csv_files/azorius_cards.csv')
                print('Checking for orzhov_cards.csv.')
                while True:
                    try:
                        with open('csv_files/orzhov_cards.csv', 'r', encoding='utf-8'):
                            print('orzhov_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('orzhov_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, W', 'csv_files/orzhov_cards.csv')
                print('Checking for boros_cards.csv.')
                while True:
                    try:
                        with open('csv_files/boros_cards.csv', 'r', encoding='utf-8'):
                            print('boros_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('boros_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'R, W', 'csv_files/boros_cards.csv')
                print('Checking for selesnya_cards.csv.')
                while True:
                    try:
                        with open('csv_files/selesnya_cards.csv', 'r', encoding='utf-8'):
                            print('selesnya_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('selesnya_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, W', 'csv_files/selesnya_cards.csv')
                print('Checking for dimir_cards.csv.')
                while True:
                    try:
                        with open('csv_files/dimir_cards.csv', 'r', encoding='utf-8'):
                            print('dimir_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('dimir_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, U', 'csv_files/dimir_cards.csv')
                print('Checking for izzet_cards.csv.')
                while True:
                    try:
                        with open('csv_files/izzet_cards.csv', 'r', encoding='utf-8'):
                            print('izzet_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('izzet_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'R, U', 'csv_files/izzet_cards.csv')
                print('Checking for simic_cards.csv.')
                while True:
                    try:
                        with open('csv_files/simic_cards.csv', 'r', encoding='utf-8'):
                            print('simic_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('simic_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, U', 'csv_files/simic_cards.csv')
                print('Checking for rakdos_cards.csv.')
                while True:
                    try:
                        with open('csv_files/rakdos_cards.csv', 'r', encoding='utf-8'):
                            print('rakdos_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('rakdos_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, R', 'csv_files/rakdos_cards.csv')
                print('Checking for golgari_cards.csv.')
                while True:
                    try:
                        with open('csv_files/golgari_cards.csv', 'r', encoding='utf-8'):
                            print('golgari_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('golgari_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G', 'csv_files/golgari_cards.csv')
                print('Checking for gruul_cards.csv.')
                while True:
                    try:
                        with open('csv_files/gruul_cards.csv', 'r', encoding='utf-8'):
                            print('gruul_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('gruul_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, R', 'csv_files/gruul_cards.csv')
                break
            print('Checking for three-color sets.')
            while True:
                print('Checking for bant_cards.csv.')
                while True:
                    try:
                        with open('csv_files/bant_cards.csv', 'r', encoding='utf-8'):
                            print('bant_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('bant_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, U, W', 'csv_files/bant_cards.csv')
                print('Checking for esper_cards.csv.')
                while True:
                    try:
                        with open('csv_files/esper_cards.csv', 'r', encoding='utf-8'):
                            print('esper_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('esper_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, U, W', 'csv_files/esper_cards.csv')
                print('Checking for grixis_cards.csv.')
                while True:
                    try:
                        with open('csv_files/grixis_cards.csv', 'r', encoding='utf-8'):
                            print('grixis_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('grixis_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, R, U', 'csv_files/grixis_cards.csv')
                print('Checking for jund_cards.csv.')
                while True:
                    try:
                        with open('csv_files/jund_cards.csv', 'r', encoding='utf-8'):
                            print('jund_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('jund_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G, R', 'csv_files/jund_cards.csv')
                print('Checking for naya_cards.csv.')
                while True:
                    try:
                        with open('csv_files/naya_cards.csv', 'r', encoding='utf-8'):
                            print('naya_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('naya_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, R, W', 'csv_files/naya_cards.csv')
                print('Checking for abzan_cards.csv.')
                while True:
                    try:
                        with open('csv_files/abzan_cards.csv', 'r', encoding='utf-8'):
                            print('abzan_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('abzan_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G, W', 'csv_files/abzan_cards.csv')
                print('Checking for jeskai_cards.csv.')
                while True:
                    try:
                        with open('csv_files/jeskai_cards.csv', 'r', encoding='utf-8'):
                            print('jeskai_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('jeskai_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'R, U, W', 'csv_files/jeskai_cards.csv')
                print('Checking for sultai_cards.csv.')
                while True:
                    try:
                        with open('csv_files/sultai_cards.csv', 'r', encoding='utf-8'):
                            print('sultai_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('sultai_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, U, G', 'csv_files/sultai_cards.csv')
                print('Checking for temur_cards.csv.')
                while True:
                    try:
                        with open('csv_files/temur_cards.csv', 'r', encoding='utf-8'):
                            print('temur_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('temur_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, R, U', 'csv_files/temur_cards.csv')
                break
            print('Checking for four color sets.')
            while True:
                print('Checking for dune_cards.csv.')
                while True:
                    try:
                        with open('csv_files/dune_cards.csv', 'r', encoding='utf-8'):
                            print('dune_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('dune_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G, R, W', 'csv_files/dune_cards.csv')
                print('Checking for glint_cards.csv.')
                while True:
                    try:
                        with open('csv_files/glint_cards.csv', 'r', encoding='utf-8'):
                            print('glint_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('glint_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G, R, U', 'csv_files/glint_cards.csv')
                print('Checking for ink_cards.csv.')
                while True:
                    try:
                        with open('csv_files/ink_cards.csv', 'r', encoding='utf-8'):
                            print('ink_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('ink_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'G, R, U, W', 'csv_files/ink_cards.csv')
                print('Checking for witch_cards.csv.')
                while True:
                    try:
                        with open('csv_files/witch_cards.csv', 'r', encoding='utf-8'):
                            print('witch_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('witch_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, G, U, W', 'csv_files/witch_cards.csv')
                print('Checking for yore_cards.csv.')
                while True:
                    try:
                        with open('csv_files/yore_cards.csv', 'r', encoding='utf-8'):
                            print('yore_cards.csv exists.')
                            break
                    except FileNotFoundError:
                        print('yore_cards.csv not found, creating it.')
                        filter_by_color(df, 'colorIdentity', 'B, R, U, W', 'csv_files/yore_cards.csv')
                break
            print('Checking for wubrg_cards.csv.')
            while True:
                try:
                    with open('csv_files/wubrg_cards.csv', 'r', encoding='utf-8'):
                        print('wubrg_cards.csv exists.')
                        break
                except FileNotFoundError:
                    print('wubrg_cards.csv not found, creating it.')
                    filter_by_color(df, 'colorIdentity', 'B, G, R, U, W', 'csv_files/wubrg_cards.csv')
            print('Creating setup_done.txt file')
            with open('setup_done.txt', 'w') as f:
                f.write('Setup is done')
                f.close()
    
#df = pd.read_csv('cards.csv')

#
initial_setup()