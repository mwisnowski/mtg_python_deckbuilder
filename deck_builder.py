from __future__ import annotations

import logging
import inquirer.prompt # type: ignore
import keyboard # type: ignore
import numpy as np
import pandas as pd # type: ignore
import pprint # type: ignore
import random
import time

from functools import lru_cache
from fuzzywuzzy import process # type: ignore

from settings import basic_lands, card_types, csv_directory, multiple_copy_cards
from setup import determine_commanders, set_lands

try:
    import scrython # type: ignore
    use_scrython = True
except ImportError:
    scrython = None
    use_scrython = False
    logging.warning("Scrython is not installed. Some pricing features will be unavailable.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 50)

# Basic deck builder, initial plan will just be for kindred support.
# Would like to add logic for other themes, as well as automatically go
# through the commander and find suitable themes.

# Will have it ask questions to determine number of creatures, lands,
# interaction, ramp, etc... then adjust from there. 
# Land spread will ideally be handled based on pips and some adjustment
# is planned based on mana curve and ramp added

# Later plans to have card price taken into account will be added. Lands

def new_line():
    print('\n')

class DeckBuilder:
    def __init__(self):
        self.card_library = pd.DataFrame()
        self.card_library['Card Name'] = pd.Series(dtype='str')
        self.card_library['Card Type'] = pd.Series(dtype='str')
        self.card_library['Mana Cost'] = pd.Series(dtype='str')
        self.card_library['Mana Value'] = pd.Series(dtype='int')
        
        self.set_max_deck_price = False
        self.set_max_card_price = False
        self.card_prices = {} if use_scrython else None
        
        self.artifact_cards = 0
        self.battle_cards = 0
        self.creature_cards = 0
        self.enchantment_cards = 0
        self.instant_cards = 0
        self.kindred_cards = 0
        self.land_cards = 0
        self.planeswalker_cards = 0
        self.sorcery_cards = 0
        
    def validate_text(self, result):
        return bool(result and result.strip())
    
    def validate_number(self, result):
        try:
            return float(result)
        except ValueError:
            return None
            
    def validate_confirm(self, result):
        return bool(result)
        
    def questionnaire(self, question_type, default_value='', choices_list=[]):
        MAX_ATTEMPTS = 3
        
        if question_type == 'Text':
            question = [inquirer.Text('text')]
            result = inquirer.prompt(question)['text']
            while not result.strip():
                question = [
                    inquirer.Text('text', message='Input cannot be empty')
                ]
                result = inquirer.prompt(question)['text']
            return result
            
        elif question_type == 'Number':
            attempts = 0
            question = [
                inquirer.Text('number', default=default_value)
            ]
            result = inquirer.prompt(question)['number']
            
            while attempts < MAX_ATTEMPTS:
                try:
                    result = float(result)
                    break
                except ValueError:
                    attempts += 1
                    if attempts < MAX_ATTEMPTS:
                        question = [
                            inquirer.Text('number', 
                                message='Input must be a valid number',
                                default=default_value)
                        ]
                        result = inquirer.prompt(question)['number']
                    else:
                        logging.error("Maximum input attempts reached for Number type.")
                        raise ValueError("Invalid number input.")
            return result
            
        elif question_type == 'Confirm':
            question = [
                inquirer.Confirm('confirm', default=default_value)
            ]
            result = inquirer.prompt(question)['confirm']
            return self.validate_confirm(result)
            
        elif question_type == 'Choice':
            question = [
                inquirer.List('selection',
                    choices=choices_list,
                    carousel=True)
            ]
            result = inquirer.prompt(question)['selection']
            return result
            
        raise ValueError(f"Unsupported question type: {question_type}")
    
    @lru_cache(maxsize=128)
    def price_check(self, card_name):
        try:
            time.sleep(0.1)
            card = scrython.cards.Named(fuzzy=card_name)
            card_price = card.prices('usd')
            if card_price is not None and isinstance(card_price, (int, float, str)):
                try:
                    self.card_prices[card_name] = card_price
                    return float(card_price)
                except ValueError:
                    print(f"Invalid price format for '{card_name}': {card_price}")
            return 0.0
        except Exception as e:
            print(f"Error fetching price for '{card_name}': {e}")
            return 0.0

    def determine_commander(self):
        # Setup dataframe
        try:
            df = pd.read_csv('csv_files/commander_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            determine_commanders()
            df = pd.read_csv('csv_files/commander_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        # Determine the commander of the deck
        # Set frames that have nothing for color identity to be 'Colorless' instead
        df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
        df['colors'] = df['colors'].fillna('Colorless')
        commander_chosen = False
        while not commander_chosen:
            print('Enter a card name to be your commander, note that at this time only cards that have the \'Creature\' type may be chosen')
            card_choice = self.questionnaire('Text', '')
            
            # Logic to find the card in the commander_cards csv, then display it's information
            # If the card can't be found, or doesn't have enough of a match score, display a 
            # list to choose from
            print(card_choice)
            fuzzy_chosen = False
            while not fuzzy_chosen:
                match, score, something = process.extractOne(card_choice, df['name'])
                if score >= 90:
                    fuzzy_card_choice = match
                    print(fuzzy_card_choice)
                    fuzzy_chosen = True
                else:
                    print('Multiple options found, which is correct?')
                    fuzzy_card_choices = process.extract(card_choice, df['name'], limit=5)
                    fuzzy_card_choices.append('Neither')
                    print(fuzzy_card_choices)
                    fuzzy_card_choice = self.questionnaire('Choice', inq_choices=fuzzy_card_choices)
                    if fuzzy_card_choice != 'Neither':
                        fuzzy_card_choice = fuzzy_card_choice[0]
                        print(fuzzy_card_choice)
                        fuzzy_chosen = True
                        
                    else:
                        break
                    
                        
                filtered_df = df[df['name'] == fuzzy_card_choice]
                df_dict = filtered_df.to_dict('list')
                print('Is this the card you chose?')
                pprint.pprint(df_dict, sort_dicts=False)
                self.commander_df = pd.DataFrame(df_dict)
                
                # Confirm if card entered was correct
                commander_confirmed = self.questionnaire('Confirm', True)
                # If correct, set it as the commander
                if commander_confirmed:
                    commander_chosen = True
                    self.commander_info = df_dict
                    self.commander = self.commander_df.at[0, 'name']
                    self.price_check(self.commander)
                    break
                    #print(self.commander)
                else:
                    commander_chosen = False
                            

        # Send commander info to setup commander, including extracting info on colors, color identity,
        # creature types, and other information, like keywords, abilities, etc...
        self.commander_setup()
                
    def commander_setup(self):
        # Load commander info into a dataframe
        df = self.commander_df
        
        # Set type line
        self.commander_type = str(df.at[0, 'type'])
        
        # Set text line
        self.commander_text = str(df.at[0, 'text'])
        
        # Set Power
        self.commander_power = int(df.at[0, 'power'])
        
        # Set Toughness
        self.commander_toughness = int(df.at[0, 'toughness'])
        
        # Set Mana Cost
        self.commander_mana_cost = str(df.at[0, 'manaCost'])
        
        # Set color identity
        self.color_identity = df.at[0, 'colorIdentity']
        self.color_identity_full = ''
        self.determine_color_identity()
        self.setup_dataframes()
        
        # Set creature colors
        self.colors = df.at[0, 'colors'].split(', ')
        
        # Set creature types
        self.creature_types = str(df.at[0, 'creatureTypes'])
        
        # Set deck theme tags
        self.commander_tags = list(df.at[0, 'themeTags'])
        
        self.determine_themes()
        self.themes = [self.primary_theme]
        if not self.secondary_theme:
            pass
        else:
            self.themes.append(self.secondary_theme)
        if not self.tertiary_theme:
            pass
        else:
            self.themes.append(self.tertiary_theme)
        
        self.commander_dict = {
            'Commander Name': self.commander,
            'Mana Cost': self.commander_mana_cost,
            'Color Identity': self.color_identity_full,
            'Colors': self.colors,
            'Type': self.commander_type,
            'Creature Types': self.creature_types,
            'Text': self.commander_text,
            'Power': self.commander_power,
            'Toughness': self.commander_toughness,
            'Themes': self.themes
        }

        # Begin Building the Deck
        self.add_card(self.commander, self.commander_type)
        self.determine_ideals()
        self.add_lands()
        self.add_ramp()
        self.add_interaction()
        self.add_card_advantage()
        self.add_board_wipes()
        self.add_creatures()
        self.card_library.to_csv(f'{csv_directory}/test_deck_presort.csv', index=False)
        self.organize_library()
        self.concatenate_duplicates()
        self.card_library.to_csv(f'{csv_directory}/test_deck_done.csv', index=False)
        self.full_df.to_csv(f'{csv_directory}/test_all_after_done.csv', index=False)
        
    def determine_color_identity(self):
        # Determine the color identity for later
        # Mono color
        if self.color_identity == 'Colorless':
            self.color_identity_full = 'Colorless'
            self.files_to_load = ['colorless']
            pass
        elif self.color_identity == 'B':
            self.color_identity_full = 'Black'
            self.files_to_load = ['colorless', 'black']
            pass
        elif self.color_identity == 'G':
            self.color_identity_full = 'Green'
            self.files_to_load = ['colorless', 'green']
            pass
        elif self.color_identity == 'R':
            self.color_identity_full = 'Red'
            self.files_to_load = ['colorless', 'red']
        elif self.color_identity == 'U':
            self.color_identity_full = 'Blue'
            self.files_to_load = ['colorless', 'blue']
            pass
            pass
        elif self.color_identity == 'W':
            self.color_identity_full = 'White'
            self.files_to_load = ['colorless', 'white']
            pass
        
        # Two-color
        elif self.color_identity == 'B, G':
            self.color_identity_full = 'Golgari: Black/Green'
            self.color_identity_options = ['B', 'G', 'B, G']
            self.files_to_load = ['colorless', 'black', 'green', 'golgari']
            pass
        elif self.color_identity == 'B, R':
            self.color_identity_full = 'Rakdos: Black/Red'
            self.color_identity_options = ['B', 'R', 'B, R']
            self.files_to_load = ['colorless', 'black', 'red', 'rakdos']
            pass
        elif self.color_identity == 'B, U':
            self.color_identity_full = 'Dimir: Black/Blue'
            self.color_identity_options = ['B', 'U', 'B, U']
            self.files_to_load = ['colorless', 'black', 'blue', 'dimir']
            pass
        elif self.color_identity == 'B, W':
            self.color_identity_full = 'Orzhov: Black/White'
            self.color_identity_options = ['B', 'W', 'B, W']
            self.files_to_load = ['colorless', 'black', 'white', 'orzhov']
            pass
        elif self.color_identity == 'G, R':
            self.color_identity_full = 'Gruul: Green/Red'
            self.color_identity_options = ['G', 'R', 'G, R']
            self.files_to_load = ['colorless', 'green', 'red', 'gruul']
            pass
        elif self.color_identity == 'G, U':
            self.color_identity_full = 'Simic: Green/Blue'
            self.color_identity_options = ['G', 'U', 'G, U']
            self.files_to_load = ['colorless', 'green', 'blue', 'simic']
            pass
        elif self.color_identity == 'G, W':
            self.color_identity_full = 'Selesnya: Green/White'
            self.color_identity_options = ['G', 'W', 'G, W']
            self.files_to_load = ['colorless', 'green', 'white', 'selesnya']
            pass
        elif self.color_identity == 'U, R':
            self.color_identity_full = 'Izzet Blue/Red'
            self.color_identity_options = ['U', 'R', 'U, R']
            self.files_to_load = ['colorless', 'blue', 'red', 'azorius']
            pass
        elif self.color_identity == 'U, W':
            self.color_identity_full = 'Azorius: Blue/White'
            self.color_identity_options = ['U', 'W', 'U, W']
            self.files_to_load = ['colorless', 'blue', 'white', 'azorius']
            pass
        elif self.color_identity == 'R, W':
            self.color_identity_full = 'Boros: Red/White'
            self.color_identity_options = ['R', 'W', 'R, W']
            self.files_to_load = ['colorless', 'red', 'white', 'boros']
            pass
        
        # Tri-color
        elif self.color_identity == 'B, G, U':
            self.color_identity_full = 'Sultai: Black/Blue/Green'
            self.color_identity_options = ['B', 'G', 'U', 'B, G', 'B, U', 'G, U', 'B, G, U']
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'dimir', 'golgari', 'simic', 'sultai']
            pass
        elif self.color_identity == 'B, G, R':
            self.color_identity_full = 'Jund: Black/Green/Red'
            self.color_identity_options = ['B', 'G', 'R', 'B, G', 'B, R', 'G, R', 'B, G, R']
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'golgari', 'rakdos', 'gruul', 'jund']
            pass
        elif self.color_identity == 'B, G, W':
            self.color_identity_full = 'Abzan: Black/Green/White'
            self.color_identity_options = ['B', 'G', 'W', 'B, G', 'B, W', 'G, W', 'B, G, W']
            self.files_to_load = ['colorless', 'black', 'green', 'white', 'golgari', 'orzhov', 'selesnya', 'abzan']
            pass
        elif self.color_identity == 'B, R, U':
            self.color_identity_full = 'Grixis: Black/Blue/Red'
            self.color_identity_options = ['B', 'R', 'U', 'B, R', 'B, U', 'R, U', 'B, R, U']
            self.files_to_load = ['colorless', 'black', 'blue', 'red', 'dimir', 'rakdos', 'izzet', 'grixis']
            pass
        elif self.color_identity == 'B, R, W':
            self.color_identity_full = 'Mardu: Black/Red/White'
            self.color_identity_options = ['B', 'R', 'W', 'B, R', 'B, W', 'R, W', 'B, R, W']
            self.files_to_load = ['colorless', 'black', 'red', 'white', 'rakdos', 'orzhov', 'boros', 'mardu']
            pass
        elif self.color_identity == 'B, U, W':
            self.color_identity_full = 'Esper: Black/Blue/White'
            self.color_identity_options = ['B', 'U', 'W', 'B, R', 'B, W', 'R, W', 'B, R, W']
            self.files_to_load = ['colorless', 'black', 'blue', 'white', 'dimir', 'orzhov', 'azorius', 'esper']
            pass
        elif self.color_identity == 'G, R, U':
            self.color_identity_full = 'Temur: Blue/Green/Red'
            self.color_identity_options = ['G', 'R', 'U', 'G, R', 'G, U', 'R, U', 'G, R, U']
            self.files_to_load = ['colorless', 'green', 'red', 'blue', 'simic', 'izzet', 'gruul', 'temur']
            pass
        elif self.color_identity == 'G, R, W':
            self.color_identity_full = 'Naya: Green/Red/White'
            self.color_identity_options = ['G', 'R', 'W', 'G, R', 'G, W', 'R, W', 'G, R, W']
            self.files_to_load = ['colorless', 'green', 'red', 'white', 'gruul', 'selesnya', 'boros', 'naya']
            pass
        elif self.color_identity == 'G, U, W':
            self.color_identity_full = 'Bant: Blue/Green/White'
            self.color_identity_options = ['G', 'U', 'W', 'G, U', 'G, W', 'U, W', 'G, U, W']
            self.files_to_load = ['colorless', 'green', 'blue', 'white', 'simic', 'azorius', 'selesnya', 'bant']
            pass
        elif self.color_identity == 'U, R, W':
            self.color_identity_full = 'Jeskai: Blue/Red/White'
            self.color_identity_options = ['U', 'R', 'W', 'U, R', 'U, W', 'R, W', 'U, R, W']
            self.files_to_load = ['colorless', 'blue', 'red', 'white', 'izzet', 'azorius', 'boros', 'jeskai']
            pass
        
        # Quad-color
        elif self.color_identity == 'B, G, R, U':
            self.color_identity_full = 'Glint: Black/Blue/Green/Red'
            self.color_identity_options = ['B', 'G', 'R', 'U', 'B, G', 'B, R', 'B, U', 'G, R', 'G, U', 'R, U', 'B, G, R', 'B, G, U', 'B, R, U', 'G, R, U' , 'B, G, R, U']
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'red', 'golgari', 'rakdos', 'dimir', 'gruul',
                                  'simic', 'izzet', 'jund', 'sultai', 'grixis', 'temur', 'glint']
            pass
        elif self.color_identity == 'B, G, R, W':
            self.color_identity_full = 'Dune: Black/Green/Red/White'
            self.color_identity_options = ['B', 'G', 'R', 'W', 'B, G', 'B, R', 'B, W', 'G, R', 'G, W', 'R, W',
                                           'B, G, R', 'B, G, W', 'B, R, W', 'G, R, W' , 'B, G, R, W']
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'white', 'golgari', 'rakdos', 'orzhov', 'gruul',
                                  'selesnya', 'boros', 'jund', 'abzan', 'mardu', 'naya', 'dune']
            pass
        elif self.color_identity == 'B, G, U, W':
            self.color_identity_full = 'Witch: Black/Blue/Green/White'
            self.color_identity_options = ['B', 'G', 'U', 'W', 'B, G', 'B, U', 'B, W', 'G, U', 'G, W', 'U, W',
                                           'B, G, U', 'B, G, W', 'B, U, W', 'G, U, W' , 'B, G, U, W']
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'white', 'golgari', 'dimir', 'orzhov', 'simic',
                                  'selesnya', 'azorius', 'sultai', 'abzan', 'esper', 'bant', 'glint']
            pass
        elif self.color_identity == 'B, R, U, W':
            self.color_identity_full = 'Yore: Black/Blue/Red/White'
            self.color_identity_options = ['B', 'R', 'U', 'W', 'B, R', 'B, U', 'B, W', 'R, U', 'R, W', 'U, W',
                                           'B, R, U', 'B, R, W', 'B, U, W', 'R, U, W' , 'B, R, U, W']
            self.files_to_load = ['colorless', 'black', 'blue', 'red', 'white', 'rakdos', 'dimir', 'orzhov', 'izzet',
                                  'boros', 'azorius', 'grixis', 'mardu', 'esper', 'mardu', 'glint']
            pass
        elif self.color_identity == 'G, R, U, W':
            self.color_identity_full = 'Ink: Blue/Green/Red/White'
            self.color_identity_options = ['G', 'R', 'U', 'W', 'G, R', 'G, U', 'G, W', 'R, U', 'R, W', 'U, W',
                                           'G, R, U', 'G, R, W', 'G, U, W', 'R, U, W', 'G, R, U, W']
            self.files_to_load = ['colorless', 'blue', 'green', 'red', 'white', 'gruul', 'simic', 'selesnya', 'izzet',
                                  'boros', 'azorius', 'temur', 'naya', 'bant', 'jeskai', 'glint']
            pass
        elif self.color_identity == 'B, G, R, U, W':
            self.color_identity_full = 'WUBRG: All colors'
            self.color_identity_options = ['B', 'G', 'R', 'U', 'W', 'B, G', 'B, R', 'B, U', 'B, W', 'G, R', 'G, U', 'G, W',
                                           'R, U', 'R, W', 'U, W', 'B, G, R', 'B, G, U', 'B, G, W', 'B, R, U', 'B, R, W',
                                           'B, U, W', 'G, R, U', 'G, R, W', 'B, U ,W', 'R, U, W', 'B, G, R, U', 'B, G, R, W',
                                           'B, G, U, W', 'B, R, U, W', 'G, R, U, W', 'B, G, R, U, W']
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'blue', 'white', 'golgari', 'rakdos',' dimir',
                                  'orzhov', 'gruul', 'simic', 'selesnya', 'izzet', 'boros', 'azorius', 'jund', 'sultai', 'abzan',
                                  'grixis', 'mardu', 'esper', 'temur', 'naya', 'bant', 'jeska', 'glint', 'dune','witch', 'yore',
                                  'ink']
    
    def setup_dataframes(self):
        all_df = []
        for file in self.files_to_load:
            df = pd.read_csv(f'{csv_directory}/{file}_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
            all_df.append(df)
        self.full_df = pd.concat(all_df,ignore_index=True)
        self.full_df.sort_values(by='edhrecRank', inplace=True)
        self.full_df.to_csv(f'{csv_directory}/test_all.csv', index=False)
        
        self.artifact_df = self.full_df[self.full_df['type'].str.contains('Artifact')].copy()
        self.artifact_df.sort_values(by='edhrecRank', inplace=True)
        self.artifact_df.to_csv(f'{csv_directory}/test_artifacts.csv', index=False)
        
        self.battle_df = self.full_df[self.full_df['type'].str.contains('Battle')].copy()
        self.battle_df.sort_values(by='edhrecRank', inplace=True)
        self.battle_df.to_csv(f'{csv_directory}/test_battles.csv', index=False)
        
        self.creature_df = self.full_df[self.full_df['type'].str.contains('Creature')].copy()
        self.creature_df.sort_values(by='edhrecRank', inplace=True)
        self.creature_df.to_csv(f'{csv_directory}/test_creatures.csv', index=False)
        
        self.enchantment_df = self.full_df[self.full_df['type'].str.contains('Enchantment')].copy()
        self.enchantment_df.sort_values(by='edhrecRank', inplace=True)
        self.enchantment_df.to_csv(f'{csv_directory}/test_enchantments.csv', index=False)
        
        self.instant_df = self.full_df[self.full_df['type'].str.contains('Instant')].copy()
        self.instant_df.sort_values(by='edhrecRank', inplace=True)
        self.instant_df.to_csv(f'{csv_directory}/test_instants.csv', index=False)
        
        self.planeswalker_df = self.full_df[self.full_df['type'].str.contains('Planeswalker')].copy()
        self.planeswalker_df.sort_values(by='edhrecRank', inplace=True)
        self.planeswalker_df.to_csv(f'{csv_directory}/test_planeswalkers.csv', index=False)
        
        self.sorcery_df = self.full_df[self.full_df['type'].str.contains('Sorcery')].copy()
        self.sorcery_df.sort_values(by='edhrecRank', inplace=True)
        self.sorcery_df.to_csv(f'{csv_directory}/test_sorcerys.csv', index=False)
        
        self.land_df = self.full_df[self.full_df['type'].str.contains('Land')].copy()
        self.land_df.sort_values(by='edhrecRank', inplace=True)
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
        
    def determine_themes(self):
        themes = self.commander_tags
        print('Your commander deck will likely have a number of viable themes, but you\'ll want to narrow it down for focus.\n'
                'This will go through the process of choosing up to three themes for the deck.\n')
        while True:
            # Choose a primary theme
            print('Choose a primary theme for your commander deck.\n'
                'This will be the "focus" of the deck, in a kindred deck this will typically be a creature type for example.')
            choice = self.questionnaire('Choice', inq_choices=themes)
            self.primary_theme = choice
            self.primary_weight = 0.9
            self.weights = []
            self.weights.extend([self.primary_weight])
                        
            themes.remove(choice)
            themes.append('Stop Here')
            
            secondary_theme_chosen = False
            tertiary_theme_chosen = False
            
            while not secondary_theme_chosen:
                # Secondary theme
                print('Choose a secondary theme for your commander deck.\n'
                    'This will typically be a secondary focus, like card draw for Spellslinger, or +1/+1 counters for Aggro.')
                choice = self.questionnaire('Choice', inq_choices=themes)
                while True:
                    if choice == 'Stop Here':
                        print('You\'ve only selected one theme, are you sure you want to stop?\n')
                        confirm_done = self.questionnaire('Confirm', 'False')
                        if confirm_done:
                            secondary_theme_chosen = True
                            self.secondary_theme = False
                            tertiary_theme_chosen = True
                            self.tertiary_theme = False
                            themes.remove(choice)
                            break
                        else:
                            pass

                    else:
                        self.secondary_theme = choice
                        themes.remove(choice)
                        secondary_theme_chosen = True
                        self.primary_weight = 0.5
                        self.secondary_weight = 0.4
                        self.weights = []
                        self.weights.extend([self.primary_weight, self.secondary_weight])
                        break
            
            while not tertiary_theme_chosen:
                # Tertiary theme
                print('Choose a tertiary theme for your commander deck.\n'
                    'This will typically be a tertiary focus, or just something else to do that your commander is good at.')
                choice = self.questionnaire('Choice', inq_choices=themes)
                while True:
                    if choice == 'Stop Here':
                        print('You\'ve only selected two themes, are you sure you want to stop?\n')
                        confirm_done = self.questionnaire('Confirm', False)
                        if confirm_done:
                            tertiary_theme_chosen = True
                            self.tertiary_theme = False
                            themes.remove(choice)
                            break
                        else:
                            pass

                    else:
                        self.tertiary_theme = choice
                        tertiary_theme_chosen = True
                        self.primary_weight = 0.4
                        self.secondary_weight = 0.3
                        self.tertiary_weight = 0.2
                        self.weights = []
                        self.weights.extend([self.primary_weight, self.secondary_weight, self.tertiary_weight])
                        break
            break
        
    def determine_ideals(self):
        # "Free" slots that can be used for anything that isn't the ideals
        self.free_slots = 99
        
        if use_scrython:
            print('Would you like to set an intended max price of the deck?\n'
                  'There will be some leeway of ~10%, with a couple alternative options provided.')
            choice = self.questionnaire('Confirm', False)
            if choice:
                self.set_max_deck_price = True
                self.deck_cost = 0.0
                print('What would you like the max price to be?')
                self.max_deck_price = float(self.questionnaire('Number', '400'))
                new_line()
            else:
                self.set_max_deck_price = False
                new_line()
            
            print('Would you like to set a max price per card?\n'
                  'There will be some leeway of ~10% when choosing cards and you can choose to keep it or not.')
            choice = self.questionnaire('Confirm', False)
            if choice:
                self.set_max_card_price = True
                print('What would you like the max price to be?')
                answer = float(self.questionnaire('Number', '20'))
                self.max_card_price = answer
                self.card_library['Card Price'] = pd.Series(dtype='float')
                new_line()
            else:
                self.set_max_card_price = False
                new_line()
        
        # Determine ramp
        print('How many pieces of ramp would you like to include?\n'
              'You\'re gonna want a decent amount of ramp, both getting lands or mana rocks/dorks.\n'
              'A good baseline is 8-12, scaling up with average CMC.')
        answer = self.questionnaire('Number', '8')
        self.ideal_ramp = int(answer)
        self.free_slots -= self.ideal_ramp
        new_line()
        
        # Determine ideal land count
        print('How many lands would you like to include?\n'
              'Before ramp is taken into account, 38-40 would be "normal" for a deck. I personally use 35.\n'
              'Broadly speaking, for every mana produced per 3 mana spent on ramp could reduce land count by 1.\n'
              'If you\'re playing landfall, probably consider 40 as baseline before ramp.')
        answer = self.questionnaire('Number', '35')
        self.ideal_land_count = int(answer)
        self.free_slots -= self.ideal_land_count
        new_line()
        
        # Determine minimum basics to have
        print('How many basic lands would you like to have at minimum?\n'
              'This can vary widely depending on your commander, colors in color identity, and what you want to do.\n'
              'Some decks may be fine with as low as 10, others may want 25.')
        answer = self.questionnaire('Number', '20')
        self.min_basics = int(answer)
        new_line()
        
        # Determine ideal creature count
        print('How many creatures would you like to include?\n'
              'Something like 25-30 would be a good starting point.\n'
              'If you\'re going for a kindred theme, going past 30 is likely normal.\n'
              'Also be sure to take into account token generation, but remember you\'ll want enough to stay safe')
        answer = self.questionnaire('Number', '25')
        self.ideal_creature_count = int(answer)
        self.free_slots -= self.ideal_creature_count
        new_line()
        
        # Determine spot/targetted removal
        print('How many spot removal pieces would you like to include?\n'
              'A good starting point is about 8-12 pieces of spot removal.\n'
              'Counterspells can be consisdered proactive removal and protection.\n'
              'If you\'re going spellslinger, more would be a good idea as you might have less cretaures.')
        answer = self.questionnaire('Number', '10')
        self.ideal_removal = int(answer)
        self.free_slots -= self.ideal_removal
        new_line()

        # Determine board wipes
        print('How many board wipes would you like to include?\n'
              'Somewhere around 2-3 is good to help eliminate threats, but also prevent the game from running long\n.'
              'This can include damaging wipes like \'Blasphemous Act\' or toughness reduction like \'Meathook Massacre\'.')
        answer = self.questionnaire('Number', '2')
        self.ideal_wipes = int(answer)
        self.free_slots -= self.ideal_wipes
        new_line()
        
        # Determine card advantage
        print('How many pieces of card advantage would you like to include?\n'
              '10 pieces of card advantage is good, up to 14 is better.\n'
              'Try to have a majority of it be non-conditional, and only have a couple of \'Rhystic Study\' style effects.')
        answer = self.questionnaire('Number', '10')
        self.ideal_card_advantage = int(answer)
        self.free_slots -= self.ideal_card_advantage
        new_line()
        
        # Determine how many protection spells
        print('How protection spells would you like to include?\n'
              'This can be individual protection, board protection, fogs, or similar effects.\n'
              'Things that grant indestructible, hexproof, phase out, or event just counterspells.\n'
              'This can be a widely variable ideal count, and can be as low as 5, and up past 15,\n'
              'it depends on your commander and how important your wincons are.')
        answer = self.questionnaire('Number', '8')
        self.ideal_protection = int(answer)
        self.free_slots -= self.ideal_protection
        new_line()
        
        print(f'Free slots that aren\'t part of the ideals: {self.free_slots}')
        print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')
    
    def add_card(self, card, card_type, mana_cost, mana_value):
        multiple_copies = basic_lands + multiple_copy_cards
        if card not in pd.Series(self.card_library['Card Name']).values and card not in multiple_copies:
            if use_scrython and self.set_max_card_price:
                if card in self.card_prices:
                    card_price = self.card_prices.get(card)
                else:
                    card_price = self.price_check(card)
                if card_price is None:
                    card_price = 0.0
                self.card_library.loc[len(self.card_library)] = [card, card_type, mana_cost, mana_value, card_price]
                if self.set_max_deck_price:
                    self.deck_cost += card_price
            else:
                self.card_library.loc[len(self.card_library)] = [card, card_type, mana_cost, mana_value]
        elif card in multiple_copies:
            if use_scrython and self.set_max_card_price:
                if card in self.card_prices:
                    card_price = self.card_prices.get(card)
                else:
                    card_price = self.price_check(card)
                if card_price is None:
                    card_price = 0.0
                self.card_library.loc[len(self.card_library)] = [card, card_type, mana_cost, mana_value, card_price]
                if self.set_max_deck_price:
                    self.deck_cost += card_price
            else:
                self.card_library.loc[len(self.card_library)] = [card, card_type, mana_cost, mana_value]
    
    def organize_library(self):
        for card_type in card_types:
            num_cards = len(self.card_library['Card Type'].str.contains(card_type))
            if 'Artifact' in card_type:
                self.artifact_cards += num_cards
            if 'Battle' in card_type:
                self.battle_cards += num_cards
            if 'Creature' in card_type:
                self.creature_cards += num_cards
            if 'Enchantment' in card_type:
                self.enchantment_cards += num_cards
            if 'Instant' in card_type:
                self.instant_cards += num_cards
            if 'Kindred' in card_type:
                self.kindred_cards += num_cards
            if 'Land' in card_type:
                self.land_cards += num_cards
            if 'Planeswalker' in card_type:
                self.planeswalker_cards += num_cards
            if 'Sorcery' in card_type:
                self.sorcery_cards += num_cards
        
    def concatenate_duplicates(self):
        duplicate_lists = basic_lands + multiple_copy_cards
        self.total_duplicates = 0
        self.total_duplicates += len(self.card_library[self.card_library['Card Name'].isin(duplicate_lists)])
        for duplicate in duplicate_lists:
            num_duplicates = len(self.card_library[self.card_library['Card Name'] == duplicate])
            self.card_library = self.card_library.drop_duplicates(subset=['Card Name'], keep='first')
            self.card_library.loc[self.card_library['Card Name'] == duplicate, 'Card Name'] = f'{duplicate} x {num_duplicates}'
            self.card_library = self.card_library.reset_index(drop=True)
    
    def drop_card(self, dataframe, index):
        try:
            dataframe.drop(index, inplace=True)
        except KeyError:
            pass # Index already dropped or does not exist
    
    def add_lands(self):
        while True:
            try:
                with open(f'{csv_directory}/land_cards.csv', 'r', encoding='utf-8') as f:
                    print('land_cards.csv found.')
                    f.close()
                break
            except FileNotFoundError:
                print('land_cards.csv not found, regenerating it.')
                set_lands()
        # Begin the process to add lands, the number will depend on ideal land count, ramp,
        # and if any utility lands may be helpful.
        # By default, ({self.ideal_land_count} - 5) basic lands will be added, distributed
        # across the commander color identity. These will be removed for utility lands, 
        # multi-color producing lands, fetches, and any MDFCs added later
        self.land_count = 0
        self.total_basics = 0
        self.add_basics()
        self.check_basics()
        self.add_standard_non_basics()
        self.add_fetches()
        if 'Kindred' in ' '.join(self.themes):
            self.add_kindred_lands()
        if len(self.colors) >= 2:
            self.add_dual_lands()
        #if len(self.colors) >= 3:
        #    pass
        
        self.add_misc_lands()
        
        for index, row in self.land_df.iterrows():
            for land in self.card_library:
                if land in row['name']:
                    self.drop_card(self.land_df, index)
        
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
        
        # If over ideal land count, remove random basics until ideal land count
        self.check_basics()
        print('Checking total land count to ensure it\'s within ideal count.\n\n')
        self.organize_library()
        while self.land_cards > self.ideal_land_count:
            self.remove_basic()
        
        #if self.card_library < self.ideal_land_count:
        #    pass
        print(f'Total lands: {self.land_cards}')
        #print(self.total_basics)
    
    def add_basics(self):
        self.land_count = 0
        base_basics = self.ideal_land_count - 5  # Reserve 5 slots for utility lands
        basics_per_color = base_basics // len(self.colors)
        remaining_basics = base_basics % len(self.colors)
        
        color_to_basic = {
            'W': 'Plains',
            'U': 'Island', 
            'B': 'Swamp',
            'R': 'Mountain',
            'G': 'Forest'
        }
        
        if 'Snow' in self.commander_tags:
            color_to_basic = {
            'W': 'Snow-Covered Plains',
            'U': 'Snow-Covered Island', 
            'B': 'Snow-Covered Swamp',
            'R': 'Snow-Covered Mountain',
            'G': 'Snow-Covered Forest'
            }
        
        print(f'Adding {base_basics} basic lands distributed across {len(self.colors)} colors')
        
        # Add equal distribution first
        for color in self.colors:
            basic = color_to_basic.get(color)
            if basic:
                for _ in range(basics_per_color):
                    self.add_card(basic, 'Basic Land', '-', 0)
        
        # Distribute remaining basics based on color requirements
        if remaining_basics > 0:
            for color in self.colors[:remaining_basics]:
                basic = color_to_basic.get(color)
                if basic:
                    self.add_card(basic, 'Basic Land', '-', 0)

    def add_standard_non_basics(self):
        # Add lands that are good in most any commander deck
        print('Adding "standard" non-basics')
        self.staples = ['Reliquary Tower']
        if 'Landfall' not in self.commander_tags:
            self.staples.append('Ash Barrens')
        if len(self.colors) > 1:
            # Adding command Tower
            self.staples.append('Command Tower')
            
            # Adding Exotic Orchard
            self.staples.append('Exotic Orchard')
            
        if len(self.colors) <= 2:
            self.staples.append('War Room')
            
        if self.commander_power >= 5:
            self.staples.append('Rogue\'s Passage')
        
        for card in self.staples:
            if card not in self.card_library:
                self.add_card(card, 'Land', '-', 0)
            else:
                pass
                   
        
        lands_to_remove = self.staples
        for index, row in self.land_df.iterrows():
            if row['name'] in lands_to_remove:
                self.drop_card(self.land_df, index)
        
    def add_fetches(self):
        # Determine how many fetches in total
        print('How many fetch lands would you like to include?\n'
              'For most decks you\'ll likely be good with 3 or 4, just enough to thin the deck and help ensure the color availability.\n'
              'If you\'re doing Landfall, more fetches would be recommended just to get as many Landfall triggers per turn.')
        answer = self.questionnaire('Number', '2')
        
        desired_fetches = int(answer)
        chosen_fetches = []
        
        generic_fetches = ['Evolving Wilds', 'Terramorphic Expanse', 'Shire Terrace', 'Escape Tunnel', 'Promising Vein','Myriad Landscape', 'Fabled Passage', 'Terminal Moraine']
        fetches = generic_fetches
        fetches_to_remove = generic_fetches
        
        # Adding in expensive fetches
        if (use_scrython and self.set_max_card_price):
            if self.price_check('Prismatic Vista') <= self.max_card_price * (random.randint(100, 110) / 100):
                fetches_to_remove.append('Prismatic Vista')
                fetches.append('Prismatic Vista')
            else:
                fetches_to_remove.append('Prismatic Vista')
                pass
        else:
            fetches_to_remove.append('Prismatic Vista')
            fetches.append('Prismatic Vista')
        
        color_to_fetch = {
            'W': ['Flooded Strand', 'Windswept Heath', 'Marsh Flats', 'Arid Mesa', 'Brokers Hideout', 'Obscura Storefront', 'Cabaretti Courtyard'],
            'U': ['Flooded Strand', 'Polluted Delta', 'Scalding Tarn', 'Misty Rainforest', 'Brokers Hideout', 'Obscura Storefront', 'Maestros Theater'], 
            'B': ['Polluted Delta', 'Bloodstained Mire', 'Marsh Flats', 'Verdant Catacombs', 'Obscura Storefront', 'Maestros Theater', 'Riveteers Overlook'],
            'R': ['Bloodstained Mire', 'Wooded Foothills', 'Scalding Tarn', 'Arid Mesa', 'Maestros Theater', 'Riveteers Overlook', 'Cabaretti Courtyard'],
            'G': ['Wooded Foothills', 'Windswept Heath', 'Verdant Catacombs', 'Misty Rainforest', 'Brokers Hideout', 'Riveteers Overlook', 'Cabaretti Courtyard']
        }
        
        for color in self.colors:
            fetch = color_to_fetch.get(color)
            if fetch not in fetches:
                fetches.extend(fetch)
                if fetch not in fetches_to_remove:
                    fetches_to_remove.extend(fetch)
        
        fetches_chosen = False
        # Randomly choose fetches up to the desired number
        while not fetches_chosen:
            while len(chosen_fetches) < desired_fetches + 3:
                fetch_choice = random.choice(fetches)
                if use_scrython and self.set_max_card_price:
                    if self.price_check(fetch_choice) <= self.max_card_price * (random.randint(100, 110) / 100):
                        chosen_fetches.append(fetch_choice)
                        fetches.remove(fetch_choice)
                else:
                    chosen_fetches.append(fetch_choice)
                    fetches.remove(fetch_choice)

            fetches_to_add = []
            while len(fetches_to_add) < desired_fetches:
                card = random.choice(fetches)
                if card not in fetches_to_add:
                    fetches_to_add.append(card)
            fetches_chosen = True
        
        for card in fetches_to_add:
            self.add_card(card, 'Land', '-', 0)
            
        
        # Remove Fetches from land_df
        for index, row in self.land_df.iterrows():
            if row['name'] in fetches_to_remove:
                self.drop_card(self.land_df, index)
            
    def add_kindred_lands(self):
        print('Adding lands that care about the commander having a Kindred theme.')
        print('Adding general Kindred lands.')
        kindred_lands = {'Path of Ancestry': 'Land'}
        lands_to_remove = list(kindred_lands.keys())
        if (use_scrython and self.set_max_card_price):
            for land in ['Three Tree City', 'Cavern of Souls']:
                if float(self.price_check(land)) <= self.max_card_price * (random.randint(100, 110) / 100):
                    kindred_lands[land] = 'Land'
                    lands_to_remove
                else:
                    lands_to_remove.append(land)
        print('Adding any kindred-specific lands.')
        for theme in self.themes:
            if 'Kindred' in theme:
                kindred = theme.replace(' Kindred', '')
                for index, row in self.land_df.iterrows():
                    if (kindred in row['text']) or (kindred in row['type']):
                        if use_scrython and self.set_max_card_price:
                            if self.price_check(row['name']) <= self.max_card_price * (random.randint(100, 110) / 100):
                                kindred_lands[row['name']] = row['type']
                                self.drop_card(self.land_df, index)
                            else:
                                self.drop_card(self.land_df, index)
                        else:
                            kindred_lands[row['name']] = row['type']
                            self.drop_card(self.land_df, index)
        
        for card in kindred_lands:
            if card not in self.card_library:
                self.add_card(card, kindred_lands[card], '-', 0)
                
        for index, row in self.land_df.iterrows():
            if row['name'] in lands_to_remove:
                self.drop_card(self.land_df, index)
    
    def add_dual_lands(self):
        # Determine dual-color lands available 
        
        # Determine if using the dual-type lands
        print('Would you like to include dual-type lands (i.e. lands that count as both a Plains and a Swamp for example)?')
        choice = self.questionnaire('Confirm', True)
        
        dual_options = []
        for index, row in self.land_df.iterrows():
            # Azorius Duals
            if ('W' in self.colors and 'U' in self.colors):
                if ('Land — Plains Island' == row['type']
                    or 'Snow Land — Plains Island' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Orzohv Duals
            if ('W' in self.colors and 'B' in self.colors):
                if ('Land — Plains Swamp' == row['type']
                    or 'Snow Land — Plains Swamp' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Dimir Duals
            if ('U' in self.colors and 'B' in self.colors):
                if ('Land — Island Swamp' == row['type']
                    or 'Snow Land — Island Swamp' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Golgari Duals
            if ('G' in self.colors and 'B' in self.colors):
                if ('Land — Forest Swamp' == row['type']
                    or 'Snow Land — Forest Swamp' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Rakdos Duals
            if ('B' in self.colors and 'R' in self.colors):
                if ('Land — Swamp Mountain' == row['type']
                    or 'Snow Land — Swamp Mountain' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Simic Duals
            if ('G' in self.colors and 'U' in self.colors):
                if ('Land — Forest Island' == row['type']
                    or 'Snow Land — Forest Island' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Gruul Duals
            if ('R' in self.colors and 'G' in self.colors):
                if ('Land — Mountain Forest' == row['type']
                    or 'Snow Land — Mountain Forest' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Izzet Duals
            if ('U' in self.colors and 'R' in self.colors):
                if ('Land — Island Mountain' == row['type']
                    or 'Snow Land — Island Mountain' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Selesnya Duals
            if ('G' in self.colors and 'W' in self.colors):
                if ('Land — Forest Plains' == row['type']
                    or 'Snow Land — Forest Plains' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
            
            # Boros Duals
            if ('R' in self.colors and 'W' in self.colors):
                if ('Land — Mountain Plains' == row['type']
                    or 'Snow Land — Mountain Plains' == row['type']
                    ):
                    self.drop_card(self.land_df, index)
                    if (use_scrython and self.set_max_card_price):
                        if float(self.price_check(row['name'])) <= self.max_card_price * (random.randint(100, 110) / 100):
                            dual_options.append(row['name'])
                        else:
                            continue
                    else:
                        dual_options.append(row['name'])
        
        # Add the Duals to a list
        while choice:
            print('Here\'s all the dual-type lands in your commander\'s color identity:')
            print(*dual_options, sep='\n')
            print('\n')
            for card in dual_options:
                if card not in self.card_library:
                    if 'Snow Land' in card:
                        self.add_card(card, 'Snow Land', '-', 0)
                    else:
                        self.add_card(card, 'Land', '-', 0)
            break
    
    def add_misc_lands(self):
        print('Adding additional misc. lands to the deck that fit the color identity.')
        # Add other remaining lands that match color identity
        
        # Take the first 100 matches based on EDHRec popularity
        print('Grabbing the first 100 lands in your commander\'s color identity that aren\'t already in the deck.')
        self.land_df = self.land_df.head(100)
        
        lands_to_add = []
        land_choices = {}
        
        for index, row in self.land_df.iterrows():
            if row['name'] not in land_choices:
                if row['name'] not in self.card_library:
                    land_choices.update({self.land_df.at[index, 'name']: self.land_df.at[index, 'type']})
        
        # Randomly grab 15 lands
        lands_chosen = False
        # Randomly choose fetches up to the desired number
        print('Randomly choosing between 5-15 other lands to add.')
        while not lands_chosen:
            while len(lands_to_add) < random.randint(5, 15):
                land_choice = random.choice(list(land_choices.keys()))
                if land_choice not in lands_to_add:
                    lands_to_add.append(land_choice)
            break
        
        for card in lands_to_add:
            if card not in self.card_library:
                self.add_card(card, 'Land', '-', 0)
            else:
                pass
                
    def check_basics(self):
        basic_lands = ['Plains', 'Island', 'Swamp', 'Forest', 'Mountain']
        self.total_basics = 0
        self.total_basics += len(self.card_library[self.card_library['Card Name'].isin(basic_lands)])
        print(f'Number of basic lands: {self.total_basics}')
    
    def concatenate_basics(self):
        basic_lands = ['Plains', 'Island', 'Swamp', 'Forest', 'Mountain']
        self.total_basics = 0
        self.total_basics += len(self.card_library[self.card_library['Card Name'].isin(basic_lands)])
        for basic_land in basic_lands:
            num_basics = len(self.card_library[self.card_library['Card Name'] == basic_land])
            self.card_library.loc[self.card_library['Card Name'] == basic_land, 'Card Name'] = f'{basic_land} x {num_basics}'
        self.card_library = self.card_library.drop_duplicates(subset=['Card Name'], keep='first')
        self.card_library = self.card_library.reset_index(drop=True)
    
    def remove_basic(self):
        print('Land count over ideal count, removing a basic land.')
        basic_lands = []
        for color in self.colors:
            if color == 'W':
                basic = 'Plains'
            elif color == 'U':
                basic = 'Island'
            elif color == 'B':
                basic = 'Swamp'
            elif color == 'R':
                basic = 'Mountain'
            elif color == 'G':
                basic = 'Forest'
            if basic not in basic_lands:
                basic_lands.append(basic)

        basic_land = random.choice(basic_lands)
        try:
            print(f'Removing a {basic_land}')
            condition = self.card_library['Card Name'] == basic_land
            index_to_drop = self.card_library[condition].index[0]
            self.card_library = self.card_library.drop(index_to_drop)
            self.card_library = self.card_library.reset_index(drop=True)
            self.land_cards -= 1
            print(f'{basic_land} removed.')
            self.check_basics()
        except ValueError:
            basic_lands.remove(basic_land)
            basic_land = basic_lands[0]
            print(f'Removing a {basic_land}')
            condition = self.card_library['Card Name'] == basic_land
            index_to_drop = self.card_library[condition].index[0]
            self.card_library = self.card_library.drop(index_to_drop)
            self.card_library = self.card_library.reset_index(drop=True)
            self.land_cards -= 1
            print(f'{basic_land} removed.')
            self.check_basics()
        except IndexError:
            basic_lands.remove(basic_land)
            basic_land = basic_lands[0]
            print(f'Removing a {basic_land}')
            condition = self.card_library['Card Name'] == basic_land
            index_to_drop = self.card_library[condition].index[0]
            self.card_library = self.card_library.drop(index_to_drop)
            self.card_library = self.card_library.reset_index(drop=True)
            self.land_cards -= 1
            print(f'{basic_land} removed.')
            self.check_basics()
        while self.total_basics < self.min_basics:
            print(f'After removing a {basic_land}, there aren\'t enough basic lands to meet the ideals. Removing a nonbasic land.')
            basic_land = random.choice(basic_lands)
            self.remove_land()
            print(f'Adding a {basic_land} back in.')
            self.add_card(basic_land, 'Basic Land', '-', 0)
            self.check_basics()

    def remove_land(self):
        print('Removing a random nonbasic land.')
        basic_lands = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest',
                       'Snow-Covered Plains', 'Snow-Covered Island', 'Snow-Covered Swamp',
                       'Snow-Covered Mountain', 'Snow-Covered Forest']
        library_filter = self.card_library[self.card_library['Card Type'].str.contains('Land')]
        library_filter = library_filter[~library_filter['Card Name'].isin((basic_lands + self.staples))]
        card = np.random.choice(library_filter.index, 1, replace=False)
        print(library_filter.loc[card, 'Card Name'].to_string(index=False))
        #condition = self.card_library['Card Name'] == card
        #index_to_drop = self.card_library[condition].index[0]
        #self.card_library = self.card_library.drop(index_to_drop)
        self.card_library = self.card_library.drop(card)
        self.card_library = self.card_library.reset_index(drop=True)
        print(f"{library_filter.loc[card, 'Card Name'].to_string(index=False)} removed.")

    def weight_by_theme(self, dataframe, ideal_value):
        # First grab the first 50/30/20 cards that match each theme
        print(f'Grabbing the first {int(50 * self.primary_weight * 2)} cards that fit the {self.primary_theme} tag')
        #if 'Kindred' in self.primary_theme:
            #pass
        self.primary_card_df = dataframe.copy()
        for index, row in self.primary_card_df.iterrows():
            if self.primary_theme not in row['themeTags']:
                self.drop_card(self.primary_card_df, index)
        
        self.primary_card_df = self.primary_card_df.head(int(50 * self.primary_weight * 2))
        
        if self.secondary_theme:
            #if 'Kindred' in self.secondary_theme:
                #pass
            print(f'Grabbing the first {int(30 * self.primary_weight * 2)} cards that fit the {self.secondary_theme} tag')
            self.secondary_card_df = dataframe.copy()
            for index, row in self.secondary_card_df.iterrows():
                if self.secondary_theme not in row['themeTags']:
                    self.drop_card(self.secondary_card_df, index)
            
            self.secondary_card_df = self.secondary_card_df.head(int(30 * self.primary_weight * 2))
        
        if self.tertiary_theme:
            #if 'Kindred' in self.secondary_theme:
                #pass
            print(f'Grabbing the first {int(20 * self.primary_weight * 2)} cards that fit the {self.tertiary_theme} tag')
            self.tertiary_card_df = dataframe.copy()
            for index, row in self.tertiary_card_df.iterrows():
                if self.tertiary_theme not in row['themeTags']:
                    self.drop_card(self.tertiary_card_df, index)
            
            self.tertiary_card_df = self.tertiary_card_df.head(int(20 * self.primary_weight * 2))
        
        # then created random dfs that contain a weighted number of results
        primary_cards_to_add = {}
        primary_card_choices = {}
        secondary_cards_to_add = {}
        secondary_card_choices = {}
        tertiary_cards_to_add = {}
        tertiary_card_choices = {}
        
        for index, row in self.primary_card_df.iterrows():
            if row['name'] not in primary_card_choices:
                if row['name'] not in self.card_library:
                    primary_card_choices.update({self.primary_card_df.at[index, 'name']: self.primary_card_df.at[index, 'type']})
        if self.secondary_theme:
            for index, row in self.secondary_card_df.iterrows():
                if row['name'] not in secondary_card_choices:
                    if row['name'] not in self.card_library:
                        secondary_card_choices.update({self.secondary_card_df.at[index, 'name']: self.secondary_card_df.at[index, 'type']})
        if self.tertiary_theme:
            for index, row in self.tertiary_card_df.iterrows():
                if row['name'] not in tertiary_card_choices:
                    if row['name'] not in self.card_library:
                        tertiary_card_choices.update({self.tertiary_card_df.at[index, 'name']: self.tertiary_card_df.at[index, 'type']})
        
        # Randomly choose matches up to a random number between 1.5 and 2x the ideal value multiplied by the theme weight
        cards_chosen = False
        print('Randomly choosing a weighted number of cards to add.')
        while not cards_chosen:
            while (len(primary_cards_to_add) < int(ideal_value * self.primary_weight) and (len(primary_card_choices) > 0)):
                print(primary_card_choices)
                card_choice = random.choice(list(primary_card_choices.keys()))
                primary_card_choices.pop(card_choice, None)
                if card_choice not in primary_cards_to_add:
                    index = self.primary_card_df[self.primary_card_df['name'] == card_choice].index[0]
                    primary_cards_to_add.update({self.primary_card_df.loc[index, 'name']: self.primary_card_df.at[index, 'type']})
                    
            if self.secondary_theme:
                while (len(secondary_cards_to_add) < int(ideal_value * self.secondary_weight) and (len(secondary_card_choices) > 0)):
                    print(secondary_card_choices)
                    card_choice = random.choice(list(secondary_card_choices.keys()))
                    if card_choice not in secondary_cards_to_add:
                        index = self.secondary_card_df[self.secondary_card_df['name'] == card_choice].index[0]
                        secondary_cards_to_add.update({self.secondary_card_df.loc[index, 'name']: self.secondary_card_df.at[index, 'type']})
            if self.tertiary_theme:
                while (len(tertiary_cards_to_add) < int(ideal_value * self.tertiary_weight) and (len(tertiary_card_choices) > 0)):
                    print(tertiary_card_choices)
                    card_choice = random.choice(list(tertiary_card_choices.keys()))
                    if card_choice not in tertiary_cards_to_add:
                        index = self.tertiary_card_df[self.tertiary_card_df['name'] == card_choice].index[0]
                        tertiary_cards_to_add.update({self.tertiary_card_df.loc[index, 'name']: self.tertiary_card_df.at[index, 'type']})
            cards_chosen = True
        
        card_options = {**primary_cards_to_add, **secondary_cards_to_add, **tertiary_cards_to_add}
        
        cards_to_add = pd.DataFrame(columns=[0, 1])
        while (((len(cards_to_add) < ideal_value) and (len(card_options) > 0))):
            random_card = random.choice(list(card_options.items()))
            if random_card[0] in multiple_copy_cards:
                if random_card[0] == 'Nazgûl':
                    for _ in range(9):
                        cards_to_add.loc[len(cards_to_add)] = random_card
                elif random_card[0] == 'Seven Dwarves':
                    for _ in range(7):
                        cards_to_add.loc[len(cards_to_add)] = random_card
                else:
                    num_to_add = ideal_value - len(cards_to_add)
                    random_num_to_add = random.randint((num_to_add - 15), num_to_add)
                    for _ in range(random_num_to_add):
                        cards_to_add.loc[len(cards_to_add)] = random_card
            else:
                if random_card not in cards_to_add:
                    cards_to_add.loc[len(cards_to_add)] = random_card
        cards_to_add.rename(columns={0: 'Card Name'}, inplace=True)
        cards_to_add.rename(columns={1: 'Card Type'}, inplace=True)
            
        for index, row in cards_to_add.iterrows():
            if row['Card Name'] in multiple_copy_cards:
                if use_scrython and self.set_max_card_price:
                    if self.price_check(row['Card Name']) <= self.max_card_price * (random.randint(100, 110) / 100):
                        self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
                    else:
                        pass
                else:
                        self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
                        print(self.card_library.tail(2))
                        keyboard.wait('space')
            elif row['Card Name'] not in multiple_copy_cards:
                if row['Card Name'] not in self.card_library:
                    if use_scrython and self.set_max_card_price:
                        if self.price_check(row['Card Name']) <= self.max_card_price * (random.randint(100, 110) / 100):
                            self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
                        else:
                            pass
                    
                    else:
                            self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
                else:
                    pass
    
    def add_by_tags(self, tag, ideal_value=1):
        print(f'Grabbing the first {int(ideal_value * 3)} - {int(ideal_value * 4)} cards with the "{tag}" tag.')
        self.tag_df = self.full_df.copy()
        self.tag_df.sort_values(by='edhrecRank', inplace=True)
        
        for index, row in self.tag_df.iterrows():
            if tag not in row['themeTags']:
                self.drop_card(self.tag_df, index)
        
        self.tag_df = self.tag_df.head(int(ideal_value * random.randint(20, 30) / 10))
        
        tag_cards_to_add = self.tag_df.copy()
        tag_cards_to_add.drop(tag_cards_to_add.index, inplace=True)
        tag_card_choices = tag_cards_to_add.copy()
        print(tag_card_choices)
        for index, row in self.tag_df.iterrows():
            if row['name'] in tag_card_choices['name']:
                continue
            else:
                tag_card_choices.loc[len(tag_card_choices)] = row
        
        print(f'Randomly grabbing {self.ideal_ramp} {tag} cards.')
        cards_chosen = False
        while not cards_chosen:
            while (len(tag_cards_to_add) < ideal_value * 2) and (len(tag_card_choices) > 0):
                card = np.random.choice(tag_card_choices.index, 1, replace=False)
                if tag_card_choices.loc[card, 'name'].to_string(index=False) in tag_cards_to_add['name']:
                    continue
                else:
                    tag_cards_to_add = pd.concat([tag_cards_to_add, tag_card_choices.loc[card]], ignore_index=True)
                tag_card_choices = tag_card_choices.drop(card)
                tag_card_choices = tag_card_choices.reset_index(drop=True)
            cards_chosen = True
        card_options = {**tag_cards_to_add}
        
        cards_to_add = pd.DataFrame(columns=[0, 1])
        while (((len(cards_to_add) < ideal_value) and (len(card_options) > 0))):
            random_card = random.choice(list(card_options.keys()))
            random_card_value = card_options[random_card]
            for index, row in cards_to_add.iterrows():
                if row[0] == random_card:
                    continue
                else:
                    cards_to_add.loc[len(cards_to_add)] = [random_card, random_card_value]
        cards_to_add.rename(columns={0: 'Card Name'}, inplace=True)
        cards_to_add.rename(columns={1: 'Card Type'}, inplace=True)
        for index, row in cards_to_add.iterrows():
            if row['Card Name'] not in self.card_library:
                if use_scrython and self.set_max_card_price:
                    if self.price_check(row['Card Name']) <= self.max_card_price * (random.randint(100, 110) / 100):
                        self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
                    else:
                        pass
                
                else:
                        self.add_card(row['Card Name'], row['Card Type'], row['Mana Cost'], row['Mana Value'])
            else:
                pass
        self.tag_df.to_csv(f'{csv_directory}/test_{tag}.csv', index=False)
        
    def add_creatures(self):
        # Begin the process to add creatures, the number added will depend on what the 
        # deck plan is, the commander, creature types, etc...
        print(f'Adding creatures to deck, a baseline based on the ideal creature count of {self.ideal_creature_count} will be used.')
        self.weight_by_theme(self.creature_df, self.ideal_creature_count)
        
    def add_ramp(self):
        self.add_by_tags('Ramp', self.ideal_ramp)
    
    def add_interaction(self):
        self.add_by_tags('Removal', self.ideal_removal)
        self.add_by_tags('Protection', self.ideal_protection)
        
    def add_board_wipes(self):
        self.add_by_tags('Board Wipes', self.ideal_wipes)
        
    def add_card_advantage(self):
        self.add_by_tags('Card Draw', self.ideal_card_advantage)
        

build_deck = DeckBuilder()
build_deck.determine_commander()
pprint.pprint(build_deck.commander_dict, sort_dicts = False)
pprint.pprint(build_deck.card_library, sort_dicts = False)