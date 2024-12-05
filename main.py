from __future__ import annotations

#import os
import inquirer.prompt # type: ignore
import pandas as pd # type: ignore
import requests # type: ignore
#import scrython # type: ignore

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

def filter_by_color(df, column_name, value, new_csv_name):
    # Filter dataframe
    filtered_df = df[df[column_name] == value]
    # Save the filtered dataframe to a new csv file
    columns_to_keep = ['name', 'edhrecRank','colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'text', 'power', 'toughness', 'printings']
    filtered_df = filtered_df[columns_to_keep]
    filtered_df.drop_duplicates(subset='name', inplace=True)
    filtered_df.to_csv(new_csv_name, index=False)

def initial_setup():
    # Check if the overall cards.csv file exists
    print('Checking if setup was previously finished.\n')
    while True:
        try:
            with open('setup_done.txt', 'r'):
                print('Setup is done.\n')
                break
        except FileNotFoundError:
            print('Checking for cards.csv file.\n')
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
            df = pd.read_csv('csv_files/cards.csv')
            df['colorIdentity'] = df['colorIdentity'].fillna('None')

            print('Checking for color identity sorted files.\n')
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
            print('Checking for color-pair lists.\n')
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
            print('Checking for three-color sets.\n')
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
            print('Checking for four color sets.\n')
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
            print('Checking for wubrg_cards.csv.\n')
            while True:
                try:
                    with open('csv_files/wubrg_cards.csv', 'r', encoding='utf-8'):
                        print('wubrg_cards.csv exists.')
                        break
                except FileNotFoundError:
                    print('wubrg_cards.csv not found, creating it.')
                    filter_by_color(df, 'colorIdentity', 'B, G, R, U, W', 'csv_files/wubrg_cards.csv')
            print('Creating setup_done.txt file.\n')
            with open('setup_done.txt', 'w') as f:
                f.write('Setup is done.')
                f.close()
staple_lists = ['Colorless', 'White', 'Blue', 'Black']
colorless_staples = [] # type: ignore
white_staples = [] # type: ignore
blue_staples = [] # type: ignore
black_staples = [] # type: ignore
def make_staples_list():
    # Generate list of staples by color. This is subjective and can be modified as seen fit.
    # At present it's based on top cards from edhrec, using the first 15 or so of each color
    print('Making staple lists.\n')
    print('Colorless staples:')
    global colorless_staples
    colorless_staples = [
        'Sol Ring',
        'Arcane Signet',
        'Fellwar Stone',
        'Skullclamp',
        'Lightning Greaves',
        'Swiftfoot Boots',
        'Thought Vessel',
        'Solemn Simulacrum',
        'Mind Stone',
        'Wayfarer\'s Bauble',
        'Commander\'s Sphere'
        ]
    colorless_staples.sort()
    print(colorless_staples)
    print('White staples:')
    global white_staples
    white_staples = [
        'Swords to Plowshares',
        'Path to Exile',
        'Generous Gift',
        'Smothering Tithe',
        'Esper Sentinel',
        'Teferi\'s Protection',
        'Enlightened Tutor',
        'Farewell',
        'Austere Command',
        'Ghostly Prison',
        'Sun Titan',
        'Flawless Maneuver',
        'Akroma\'s Will',
        'Annointed Procession',
        'Wrath of God'
    ]
    print(white_staples)
    print('Blue staples:')
    global blue_staples
    blue_staples = [
        'Counterspell',
        'Cyclonic Rift',
        'Rhystic Study',
        'Negate',
        'Brainstorm',
        'An Offer You Can\'t Refuse',
        'Arcane Denial',
        'Mystic Remora',
        'Fierce Guardianship',
        'Swan Song',
        'Mana Drain',
        'Mystical Tutor',
        'Windfall',
        'Ponder',
        'Frantic Search',
        'Pongify',
        'Propoganda',
        'Preordain',
        'Opt',
        'Rapid Hybridization'
    ]
    print(blue_staples)
    print('Black staples:')
    global black_staples
    black_staples = [
        'Demonic Tutor',
        'Dark Ritual',
        'Vampiric Tutor',
        'Feed the Swarm',
        'Toxic Deluge',
        'Reanimate',
        'Phyrexian Arena',
        'Blood Artist',
        'Victimize',
        'Deadly Dispute',
        'Deadly Rollick',
        'Black Market Connections',
        'Zulaport Cutthroat',
        'Village Rites',
        'Sign in Blood',
        'Animate Dead',
        'Bolas\'s Citadel',
        'Gray Merchant of Asphodel',
        'Syr Konrad, the Grim',
        'Diabolic Intent'
    ]
    print(black_staples)
    
    return colorless_staples, white_staples, blue_staples, black_staples

def generate_staple_lists():
    # Colorless staples
    global colorless_staples
    print('Colorless staples:')
    while True:
        try:
            with open('staples/colorless.txt', 'r') as file:
                colorless_staples = file.read().split('\n')
                del colorless_staples[-1]
                print('\n'.join(colorless_staples), '\n')
                break
        except FileNotFoundError:
            print('Generating colorless staples list.')
            df = pd.read_csv('csv_files/colorless_cards.csv')
            df['edhrecRank'] = pd.to_numeric(df['edhrecRank'], downcast='integer', errors='coerce')
            df = df.dropna(subset=['edhrecRank'])
            df['edhrecRank'] = df['edhrecRank'].astype(int)
            columns_to_keep = ['name', 'edhrecRank', 'type']
            df = df[columns_to_keep]
            i = 1
            while len(colorless_staples) < 20:
                for index, row in df.iterrows():
                    if row['edhrecRank'] == i:
                        if 'Land' not in row['type'] and row['name'] not in banned_cards:
                            colorless_staples.append(row['name'])
                i += 1
            #print(colorless_staples)
            with open('staples/colorless.txt', 'w') as f:
                for items in colorless_staples:
                    f.write('%s\n' %items)
    # White staples
    print('White staples:')
    global white_staples
    while True:
        try:
            with open('staples/white.txt', 'r') as file:
                white_staples = file.read().split('\n')
                del white_staples[-1]
                print('\n'.join(white_staples), '\n')
                break
        except FileNotFoundError:
            print('Generating white staples list.')
            df = pd.read_csv('csv_files/white_cards.csv')
            df['edhrecRank'] = pd.to_numeric(df['edhrecRank'], downcast='integer', errors='coerce')
            df = df.dropna(subset=['edhrecRank'])
            df['edhrecRank'] = df['edhrecRank'].astype(int)
            columns_to_keep = ['name', 'edhrecRank', 'type']
            df = df[columns_to_keep]
            i = 1
            while len(white_staples) < 20:
                for index, row in df.iterrows():
                    if row['edhrecRank'] == i:
                        if row['name'] not in banned_cards:
                            white_staples.append(row['name'])
                i += 1
            #print(white_staples)
            with open('staples/white.txt', 'w') as f:
                for items in white_staples:
                    f.write('%s\n' %items)
    
    
        
def get_card_info():
    question = [
        inquirer.List(
            'staple_list',
            message='Choose a staple list to check through',
            choices=staple_lists,
            carousel=True
            )
    ]
    answer = inquirer.prompt(question)
    staple_list_choice = answer['staple_list']
    if staple_list_choice == 'Colorless':
        staple = 'colorless'
        question = [
            inquirer.List(
                'card_list',
                message='Choose a card from the list.',
                choices=colorless_staples,
                carousel=True
            )
        ]
        answer = inquirer.prompt(question)
        card_choice = answer['card_list']
    elif staple_list_choice == 'White':
        staple = 'white'
        question = [
            inquirer.List(
                'card_list',
                message='Choose a card from the list.',
                choices=white_staples,
                carousel=True
            )
        ]
        answer = inquirer.prompt(question)
        card_choice = answer['card_list']
    elif staple_list_choice == 'Blue':
        staple = 'blue'
        question = [
            inquirer.List(
                'card_list',
                message='Choose a card from the list.',
                choices=blue_staples,
                carousel=True
            )
        ]
        answer = inquirer.prompt(question)
        card_choice = answer['card_list']
    elif staple_list_choice == 'Black':
        staple = 'black'
        question = [
            inquirer.List(
                'card_list',
                message='Choose a card from the list.',
                choices=black_staples,
                carousel=True
            )
        ]
        answer = inquirer.prompt(question)
        card_choice = answer['card_list']
    df = pd.read_csv(f'csv_files/{staple}_cards.csv')
    filtered_df = df[df['name'] == card_choice]
    columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness', 'text']
    filtered_df = filtered_df[columns_to_keep]
    print(filtered_df)

initial_setup()
#make_staples_list()
generate_staple_lists()
#get_card_info()