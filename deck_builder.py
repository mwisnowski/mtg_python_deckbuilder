from __future__ import annotations

import logging
import inquirer.prompt # type: ignore
import keyboard # type: ignore
import math
import numpy as np
import pandas as pd # type: ignore
import pprint # type: ignore
import random
import time

from functools import lru_cache
from fuzzywuzzy import process # type: ignore

from settings import basic_lands, card_types, csv_directory, multiple_copy_cards
from setup import determine_commanders

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

"""
Basic deck builder, primarily intended for building Kindred decks.
Logic for other themes (such as Spellslinger or Wheels), is added.
I plan to also implement having it recommend a commander or themes.

Currently, the script will ask questions to determine number of 
creatures, lands, interaction, ramp, etc... then add cards and 
adjust from there.

Land spread will ideally be handled based on pips and some adjustment
is planned based on mana curve and ramp added.
"""

def new_line(num_lines: int = 1) -> None:
    """Print specified number of newlines for formatting output.

    Args:
        num_lines (int): Number of newlines to print. Defaults to 1.

    Returns:
        None
    """
    if num_lines < 0:
        raise ValueError("Number of lines cannot be negative")
    print('\n' * num_lines)

class DeckBuilder:

    def __init__(self):
        self.card_library = pd.DataFrame()
        self.card_library['Card Name'] = pd.Series(dtype='str')
        self.card_library['Card Type'] = pd.Series(dtype='str')
        self.card_library['Mana Cost'] = pd.Series(dtype='str')
        self.card_library['Mana Value'] = pd.Series(dtype='int')
        self.card_library['Commander'] = pd.Series(dtype='bool')
        
        self.set_max_deck_price = False
        self.set_max_card_price = False
        self.card_prices = {} if use_scrython else None
        
    def pause_with_message(self, message="Press Enter to continue..."):
        """Helper function to pause execution with a message."""
        print(f"\n{message}")
        input()
        
    def validate_text(self, result: str) -> bool:
        """Validate text input is not empty.
        
        Args:
            result (str): Text input to validate
        
        Returns:
            bool: True if text is not empty after stripping whitespace
        """
        return bool(result and result.strip())
    
    def validate_number(self, result: str) -> float | None:
        """Validate and convert string input to float.
        
        Args:
            result (str): Number input to validate
        
        Returns:
            float | None: Converted float value or None if invalid
        """
        try:
            return float(result)
        except (ValueError, TypeError):
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
            if card_price is not None and isinstance(card_price, (int, float)):
                try:
                    self.card_prices[card_name] = card_price
                    return float(card_price)
                except ValueError:
                    logging.error(f"Invalid price format for '{card_name}': {card_price}")
                    return 0.0
            return 0.0
        except (scrython.foundation.ScryfallError, scrython.foundation.ScryfallRequestError) as e:
            logging.error(f"Scryfall API error for '{card_name}': {e}")
            return 0.0
        except TimeoutError:
            logging.error(f"Request timed out while fetching price for '{card_name}'")
            return 0.0
        except Exception as e:
            logging.error(f"Unexpected error fetching price for '{card_name}': {e}")
            return 0.0
        
    def determine_commander(self):
        # Setup dataframe
        try:
            df = pd.read_csv('csv_files/commander_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        except FileNotFoundError:
            determine_commanders()
            df = pd.read_csv('csv_files/commander_cards.csv', converters={'themeTags': pd.eval, 'creatureTypes': pd.eval})
        # Determine the commander of the deck
        # Set frames that have nothing for color identity to be 'COLORLESS' instead
        df['colorIdentity'] = df['colorIdentity'].fillna('COLORLESS')
        df['colors'] = df['colors'].fillna('COLORLESS')
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
                    fuzzy_card_choice = self.questionnaire('Choice', choices_list=fuzzy_card_choices)
                    if isinstance(fuzzy_card_choice, tuple):
                        fuzzy_card_choice = fuzzy_card_choice[0]
                    if fuzzy_card_choice != 'Neither':
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
                    logging.info(f"Commander selected: {self.commander}")
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
        self.commander_mana_value = int(df.at[0, 'manaValue'])

        # Set color identity
        try:
            self.color_identity = df.at[0, 'colorIdentity']
            if pd.isna(self.color_identity):
                self.color_identity = 'COLORLESS'
            self.color_identity_full = ''
            self.determine_color_identity()
        except Exception as e:
            logging.error(f"Failed to set color identity: {e}")
            raise ValueError("Could not determine color identity") from e

        # Set creature colors
        if pd.notna(df.at[0, 'colors']) and df.at[0, 'colors'].strip():
            self.colors = [color.strip() for color in df.at[0, 'colors'].split(',') if color.strip()]
            if not self.colors:
                self.colors = ['COLORLESS']
        else:
            self.colors = ['COLORLESS']

        # Set creature types
        self.creature_types = str(df.at[0, 'creatureTypes'])

        # Set deck theme tags
        self.commander_tags = list(df.at[0, 'themeTags'])

        self.determine_themes()
        

        self.commander_dict = {
            'Commander Name': self.commander,
            'Mana Cost': self.commander_mana_cost,
            'Mana Value': self.commander_mana_value,
            'Color Identity': self.color_identity_full,
            'Colors': self.colors,
            'Type': self.commander_type,
            'Creature Types': self.creature_types,
            'Text': self.commander_text,
            'Power': self.commander_power,
            'Toughness': self.commander_toughness,
            'Themes': self.themes
        }
        self.add_card(self.commander, self.commander_type, self.commander_mana_cost, self.commander_mana_value, True)

        # Begin Building the Deck
        self.setup_dataframes()
        self.determine_ideals()
        self.add_lands()
        self.add_creatures()
        self.add_ramp()
        self.add_interaction()
        self.add_card_advantage()
        self.add_board_wipes()
        if len(self.card_library) < 100:
            self.fill_out_deck()
        self.card_library.to_csv(f'{csv_directory}/test_deck_presort.csv', index=False)
        self.organize_library()
        self.card_library.to_csv(f'{csv_directory}/test_deck_preconcat.csv', index=False)
        print(f'Creature cards (including commander): {self.creature_cards}')
        print(f'Planeswalker cards: {self.planeswalker_cards}')
        print(f'Battle cards: {self.battle_cards}')
        print(f'Instant cards: {self.instant_cards}')
        print(f'Sorcery cards: {self.sorcery_cards}')
        print(f'Artifact cards: {self.artifact_cards}')
        print(f'Enchantment cards: {self.enchantment_cards}')
        print(f'Land cards cards: {self.land_cards}')
        print(f'Number of cards in Library: {len(self.card_library)}')
        self.get_cmc()
        self.count_pips()
        self.concatenate_duplicates()
        self.organize_library()
        self.sort_library()
        self.commander_to_top()
        self.card_library.to_csv(f'{csv_directory}/test_deck_done.csv', index=False)
        self.full_df.to_csv(f'{csv_directory}/test_all_after_done.csv', index=False)
    
    def determine_color_identity(self):
        # Determine the color identity for later
        # Mono color
        if self.color_identity == 'COLORLESS':
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
        elif self.color_identity == 'R, U':
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
            self.color_identity_options = ['B', 'U', 'W', 'B, U', 'B, W', 'U, W', 'B, U, W']
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
        
        self.land_df = self.full_df[self.full_df['type'].str.contains('Land')].copy()
        self.land_df.sort_values(by='edhrecRank', inplace=True)
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
        
        self.full_df = self.full_df[~self.full_df['type'].str.contains('Land')]
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
        
        self.noncreature_df = self.full_df[~self.full_df['type'].str.contains('Creature')].copy()
        self.noncreature_df.sort_values(by='edhrecRank', inplace=True)
        self.noncreature_df.to_csv(f'{csv_directory}/test_noncreatures.csv', index=False)
        
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
    
    def determine_themes(self):
        themes = self.commander_tags
        print('Your commander deck will likely have a number of viable themes, but you\'ll want to narrow it down for focus.\n'
                'This will go through the process of choosing up to three themes for the deck.\n')
        while True:
            # Choose a primary theme
            print('Choose a primary theme for your commander deck.\n'
                'This will be the "focus" of the deck, in a kindred deck this will typically be a creature type for example.')
            choice = self.questionnaire('Choice', choices_list=themes)
            self.primary_theme = choice
            weights_default = {
                'primary': 1.0,
                'secondary': 0.0,
                'tertiary': 0.0,
                'hidden': 0.0
                }
            weights = weights_default
            themes.remove(choice)
            themes.append('Stop Here')

            secondary_theme_chosen = False
            tertiary_theme_chosen = False
            self.hidden_theme = False
            print(weights)

            while not secondary_theme_chosen:
                # Secondary theme
                print('Choose a secondary theme for your commander deck.\n'
                    'This will typically be a secondary focus, like card draw for Spellslinger, or +1/+1 counters for Aggro.')
                choice = self.questionnaire('Choice', choices_list=themes)
                while True:
                    if choice == 'Stop Here':
                        print('You\'ve only selected one theme, are you sure you want to stop?\n')
                        confirm_done = self.questionnaire('Confirm', False)
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
                        weights = weights_default # primary = 1.0, secondary = 0.0, tertiary = 0.0
                        self.secondary_theme = choice
                        themes.remove(choice)
                        secondary_theme_chosen = True
                        # Set weights for primary/secondary themes
                        if 'Kindred' in self.primary_theme and 'Kindred' not in self.secondary_theme:
                            weights['primary'] -= 0.25 # 0.75
                            weights['secondary'] += 0.25 # 0.25
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme:
                            weights['primary'] -= 0.45 # 0.55
                            weights['secondary'] += 0.45 # 0.45
                        else:
                            weights['primary'] -= 0.4 # 0.6
                            weights['secondary'] += 0.4 # 0.4
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        break

            while not tertiary_theme_chosen:
                # Tertiary theme
                print('Choose a tertiary theme for your commander deck.\n'
                    'This will typically be a tertiary focus, or just something else to do that your commander is good at.')
                choice = self.questionnaire('Choice', choices_list=themes)
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
                        weights = weights_default # primary = 1.0, secondary = 0.0, tertiary = 0.0
                        self.tertiary_theme = choice
                        tertiary_theme_chosen = True
                        
                        # Set weights for themes:
                        if 'Kindred' in self.primary_theme and 'Kindred' not in self.secondary_theme and 'Kindred' not in self.tertiary_theme:
                            weights['primary'] -= 0.3 # 0.7
                            weights['secondary'] += 0.2 # 0.2
                            weights['tertiary'] += 0.1 # 0.1
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme and 'Kindred' not in self.tertiary_theme:
                            weights['primary'] -= 0.45 # 0.55
                            weights['secondary'] += 0.35 # 0.35
                            weights['tertiary'] += 0.1 # 0.1
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme and 'Kindred' in self.tertiary_theme:
                            weights['primary'] -= 0.5 # 0.5
                            weights['secondary'] += 0.3 # 0.3
                            weights['tertiary'] += 0.2 # 0.2
                        else:
                            weights['primary'] -= 0.6 # 0.4
                            weights['secondary'] += 0.3 # 0.3
                            weights['tertiary'] += 0.3 # 0.3
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        break
            
            self.themes = [self.primary_theme]
            if not self.secondary_theme:
                pass
            else:
                self.themes.append(self.secondary_theme)
            if not self.tertiary_theme:
                pass
            else:
                self.themes.append(self.tertiary_theme)
                
            print(self.themes)
            print(self.colors)
            """
            Setting 'Hidden' themes for multiple-copy cards, such as 'Hare Apparent' or 'Shadowborn Apostle'.
            These are themes that will be prompted for under specific conditions, such as a matching Kindred theme or a matching color combination and Spellslinger theme for example.
            Typically a hidden theme won't come up, but if it does, it will take priority with theme weights to ensure a decent number of the specialty cards are added.
            """
            # Setting hidden theme for Kindred-specific themes
            hidden_themes = ['Advisor Kindred', 'Demon Kindred', 'Dwarf Kindred', 'Rabbit Kindred', 'Rat Kindred', 'Wraith Kindred']
            theme_cards = ['Persistent Petitioners', 'Shadowborn Apostle', 'Seven Dwarves', 'Hare Apparent', ['Rat Colony', 'Relentless Rats'], 'Nazgûl']
            color = ['B', 'B', 'R', 'W', 'B', 'B']
            for i in range(min(len(hidden_themes), len(theme_cards), len(color))):
                if (hidden_themes[i] in self.themes
                    and hidden_themes[i] != 'Rat Kindred'
                    and color[i] in self.colors):
                    print(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i]} deck?')
                    choice = self.questionnaire('Confirm', False)
                    if choice:
                        self.hidden_theme = theme_cards[i]
                        self.themes.append(self.hidden_theme)
                        weights['primary'] = weights['primary'] / 3 # 0.3
                        weights['secondary'] = weights['secondary'] / 3 # 0.2
                        weights['tertiary'] = weights['tertiary'] / 3 # 0.1
                        weights['hidden'] = 1.0 - weights['primary'] - weights['secondary'] - weights['tertiary']
                        print(weights)
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        self.hidden_weight = weights['hidden']
                    else:
                        continue
                    
                elif (hidden_themes[i] in self.themes
                      and hidden_themes[i] == 'Rat Kindred'
                      and color[i] in self.colors):
                    print(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i][0]} or {theme_cards[i][1]} deck?')
                    choice = self.questionnaire('Confirm', False)
                    if choice:
                        print('Which one?')
                        choice = self.questionnaire('Choice', choices_list=theme_cards[i])
                        if choice:
                            self.hidden_theme = choice
                            self.themes.append(self.hidden_theme)
                            weights['primary'] = weights['primary'] / 3 # 0.3
                            weights['secondary'] = weights['secondary'] / 3 # 0.2
                            weights['tertiary'] = weights['tertiary'] / 3 # 0.1
                            weights['hidden'] = 1.0 - weights['primary'] - weights['secondary'] - weights['tertiary']
                            self.primary_weight = weights['primary']
                            self.secondary_weight = weights['secondary']
                            self.tertiary_weight = weights['tertiary']
                            self.hidden_weight = weights['hidden']
                    else:
                        continue
            
            # Setting the hidden theme for non-Kindred themes
            hidden_themes = ['Little Fellas', 'Mill', 'Spellslinger', 'Spells Matter', 'Spellslinger', 'Spells Matter',]
            theme_cards = ['Hare Apparent', 'Persistent Petitions', 'Dragon\'s Approach', 'Dragon\'s Approach', 'Slime Against Humanity', 'Slime Against Humanity']
            color = ['W', 'B', 'R', 'R', 'G', 'G']
            for i in range(min(len(hidden_themes), len(theme_cards), len(color))):
                if (hidden_themes[i] in self.themes
                    and color[i] in self.colors):
                    print(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i]} deck?')
                    choice = self.questionnaire('Confirm', False)
                    if choice:
                        self.hidden_theme = theme_cards[i]
                        self.themes.append(self.hidden_theme)
                        weights['primary'] = weights['primary'] / 3 # 0.3
                        weights['secondary'] = weights['secondary'] / 3 # 0.2
                        weights['tertiary'] = weights['tertiary'] / 3 # 0.1
                        weights['hidden'] = 1.0 - weights['primary'] - weights['secondary'] - weights['tertiary']
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        self.hidden_weight = weights['hidden']
                    else:
                        continue
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
                self.max_deck_price = float(self.questionnaire('Number', 400))
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
                answer = float(self.questionnaire('Number', 20))
                self.max_card_price = answer
                self.card_library['Card Price'] = pd.Series(dtype='float')
                new_line()
            else:
                self.set_max_card_price = False
                new_line()
        
        # Determine ramp
        print('How many pieces of ramp would you like to include?\n'
              'This includes mana rocks, mana dorks, and land ramp spells.\n'
              'A good baseline is 8-12 pieces, scaling up with higher average CMC\n'
              'Default: 8')
        answer = self.questionnaire('Number', 8)
        self.ideal_ramp = int(answer)
        self.free_slots -= self.ideal_ramp
        new_line()
        
        # Determine ideal land count
        print('How many total lands would you like to include?\n'
              'Before ramp is considered, 38-40 lands is typical for most decks.\n'
              "For landfall decks, consider starting at 40 lands before ramp.\n"
              'As a guideline, each mana source from ramp can reduce land count by ~1.\n'
              'Default: 35')
        answer = self.questionnaire('Number', 35)
        self.ideal_land_count = int(answer)
        self.free_slots -= self.ideal_land_count
        new_line()
        
        # Determine minimum basics to have
        print('How many basic lands would you like to have at minimum?\n'
              'This can vary widely depending on your commander, colors in color identity, and what you want to do.\n'
              'Some decks may be fine with as low as 10, others may want 25.\n'
              'Default: 20')
        answer = self.questionnaire('Number', 20)
        self.min_basics = int(answer)
        new_line()
        
        # Determine ideal creature count
        print('How many creatures would you like to include?\n'
              'Something like 25-30 would be a good starting point.\n'
              "If you're going for a kindred theme, going past 30 is likely normal.\n"
              "Also be sure to take into account token generation, but remember you'll want enough to stay safe\n"
              'Default: 25')
        answer = self.questionnaire('Number', 25)
        self.ideal_creature_count = int(answer)
        self.free_slots -= self.ideal_creature_count
        new_line()
        
        # Determine spot/targetted removal
        print('How many spot removal pieces would you like to include?\n'
              'A good starting point is about 8-12 pieces of spot removal.\n'
              'Counterspells can be considered proactive removal and protection.\n'
              'If you\'re going spellslinger, more would be a good idea as you might have less cretaures.\n'
              'Default: 10')
        answer = self.questionnaire('Number', 10)
        self.ideal_removal = int(answer)
        self.free_slots -= self.ideal_removal
        new_line()

        # Determine board wipes
        print('How many board wipes would you like to include?\n'
              'Somewhere around 2-3 is good to help eliminate threats, but also prevent the game from running long\n.'
              'This can include damaging wipes like "Blasphemous Act" or toughness reduction like "Meathook Massacre".\n'
              'Default: 2')
        answer = self.questionnaire('Number', 2)
        self.ideal_wipes = int(answer)
        self.free_slots -= self.ideal_wipes
        new_line()
        
        # Determine card advantage
        print('How many pieces of card advantage would you like to include?\n'
              '10 pieces of card advantage is good, up to 14 is better.\n'
              'Try to have a majority of it be non-conditional, and only have a couple of "Rhystic Study" style effects.\n'
              'Default: 10')
        answer = self.questionnaire('Number', 10)
        self.ideal_card_advantage = int(answer)
        self.free_slots -= self.ideal_card_advantage
        new_line()
        
        # Determine how many protection spells
        print('How many protection spells would you like to include?\n'
              'This can be individual protection, board protection, fogs, or similar effects.\n'
              'Things that grant indestructible, hexproof, phase out, or even just counterspells.\n'
              'It\'s recommended to have 5 to 15, depending on your commander and preferred strategy.\n'
              'Default: 8')
        answer = self.questionnaire('Number', 8)
        self.ideal_protection = int(answer)
        self.free_slots -= self.ideal_protection
        new_line()
        
        print(f'Free slots that aren\'t part of the ideals: {self.free_slots}')
        print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')
    
    def add_card(self, card: str, card_type: str, mana_cost: str, mana_value: int, is_commander: bool = False) -> None:
        """Add a card to the deck library with price checking if enabled.
        
        Args:
            card (str): Name of the card to add
            card_type (str): Type of the card (e.g., 'Creature', 'Instant')
            mana_cost (str): Mana cost string representation
            mana_value (int): Converted mana cost/mana value
            is_commander (bool, optional): Whether this card is the commander. Defaults to False.
        
        Returns:
            None
        
        Raises:
            ValueError: If card price exceeds maximum allowed price when price checking is enabled
        """
        multiple_copies = basic_lands + multiple_copy_cards

        # Skip if card already exists and isn't allowed multiple copies
        if card in pd.Series(self.card_library['Card Name']).values and card not in multiple_copies:
            return

        # Handle price checking
        card_price = 0.0
        if use_scrython and self.set_max_card_price:
            card_price = self.card_prices.get(card) or self.price_check(card) or 0.0

            # Skip if card is too expensive
            if card_price > self.max_card_price * 1.1:
                logging.info(f"Skipping {card} - price {card_price} exceeds maximum")
                return

        # Create card entry
        card_entry = [card, card_type, mana_cost, mana_value, is_commander]
        if use_scrython and self.set_max_card_price:
            card_entry.append(card_price)

        # Add to library
        self.card_library.loc[len(self.card_library)] = card_entry

        # Update deck cost if tracking
        if self.set_max_deck_price:
            self.deck_cost += card_price

        logging.debug(f"Added {card} to deck library")
    
    def organize_library(self):
        # Initialize counters dictionary dynamically from card_types
        card_counters = {card_type: 0 for card_type in card_types}

        # Count cards by type
        for card_type in card_types:
            type_df = self.card_library[self.card_library['Card Type'].apply(lambda x: card_type in x)]
            card_counters[card_type] = len(type_df)

        # Assign counts to instance variables
        self.artifact_cards = card_counters['Artifact']
        self.battle_cards = card_counters['Battle']
        self.creature_cards = card_counters['Creature']
        self.enchantment_cards = card_counters['Enchantment']
        self.instant_cards = card_counters['Instant']
        self.theme_cards = card_counters['Kindred']
        self.land_cards = card_counters['Land']
        self.planeswalker_cards = card_counters['Planeswalker']
        self.sorcery_cards = card_counters['Sorcery']
    
    def sort_library(self):
        self.card_library['Sort Order'] = pd.Series(dtype='str')
        for index, row in self.card_library.iterrows():
            for card_type in card_types:
                if card_type in row['Card Type']:
                    if row['Sort Order'] == 'Creature':
                        continue
                    if row['Sort Order'] != 'Creature':
                        self.card_library.loc[index, 'Sort Order'] = card_type

        custom_order = ['Planeswalker', 'Battle', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land']
        self.card_library['Sort Order'] = pd.Categorical(
            self.card_library['Sort Order'], 
            categories=custom_order, 
            ordered=True
        )
        self.card_library = (self.card_library
            .sort_values(by=['Sort Order', 'Card Name'], ascending=[True, True])
            .drop(columns=['Sort Order'])
            .reset_index(drop=True)
        )

    def commander_to_top(self):
        """Move commander card to the top of the library."""
        try:
            # Extract commander row
            commander_row = self.card_library[self.card_library['Commander']].copy()
            if commander_row.empty:
                logging.warning("No commander found in library")
                return
            
            # Remove commander from main library
            self.card_library = self.card_library[~self.card_library['Commander']]
            
            # Concatenate with commander at top
            self.card_library = pd.concat([commander_row, self.card_library], ignore_index=True)
            self.card_library = self.card_library.drop(columns=['Commander'])
            
            logging.info(f"Successfully moved commander '{commander_row['Card Name'].iloc[0]}' to top")
        except Exception as e:
            logging.error(f"Error moving commander to top: {e}")
            
    def concatenate_duplicates(self):
        """Handle duplicate cards in the library while maintaining data integrity."""
        duplicate_lists = basic_lands + multiple_copy_cards
        
        # Create a count column for duplicates
        self.card_library['Card Count'] = 1
        
        for duplicate in duplicate_lists:
            mask = self.card_library['Card Name'] == duplicate
            count = mask.sum()
            
            if count > 0:
                logging.info(f'Found {count} copies of {duplicate}')
                
                # Keep first occurrence with updated count
                first_idx = mask.idxmax()
                self.card_library.loc[first_idx, 'Card Count'] = count
                
                # Drop other occurrences
                self.card_library = self.card_library.drop(
                    self.card_library[mask & (self.card_library.index != first_idx)].index
                )
        
        # Update card names with counts where applicable
        mask = self.card_library['Card Count'] > 1
        self.card_library.loc[mask, 'Card Name'] = (
            self.card_library.loc[mask, 'Card Name'] + 
            ' x ' + 
            self.card_library.loc[mask, 'Card Count'].astype(str)
        )
        
        # Clean up
        self.card_library = self.card_library.drop(columns=['Card Count'])
        self.card_library = self.card_library.reset_index(drop=True)
    def drop_card(self, dataframe: pd.DataFrame, index: int) -> None:
        """Safely drop a card from the dataframe by index.
        
        Args:
            dataframe: DataFrame to modify
            index: Index to drop
        """
        try:
            dataframe.drop(index, inplace=True)
        except KeyError:
            logging.warning(f"Attempted to drop non-existent index {index}")
    def add_lands(self):
        """
        Begin the process to add lands, the number will depend on ideal land count, ramp,
        and if any utility lands may be helpful.
        By default, ({self.ideal_land_count} - 5) basic lands will be added, distributed
        across the commander color identity. These will be removed for utility lands, 
        multi-color producing lands, fetches, and any MDFCs added later.
        """
        self.total_basics = 0
        self.add_basics()
        self.check_basics()
        self.add_standard_non_basics()
        self.add_fetches()
        if 'Kindred' in ' '.join(self.themes):
            self.add_kindred_lands()
        if len(self.colors) >= 2:
            self.add_dual_lands()
        if len(self.colors) >= 3:
            self.add_triple_lands()
        
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
        while self.land_cards > int(self.ideal_land_count):
            print(f'Num land cards: {self.land_cards}\n'
                  f'Ideal num land cards {self.ideal_land_count}')
            self.remove_basic()
            self.organize_library()
        
        print(f'Total lands: {self.land_cards}')
    
    def add_basics(self):
        base_basics = self.ideal_land_count - 10  # Reserve 10 slots for non-basic lands
        basics_per_color = base_basics // len(self.colors)
        remaining_basics = base_basics % len(self.colors)
        
        color_to_basic = {
            'W': 'Plains',
            'U': 'Island', 
            'B': 'Swamp',
            'R': 'Mountain',
            'G': 'Forest',
            'COLORLESS': 'Wastes'
        }
        
        if 'Snow' in self.commander_tags:
            color_to_basic = {
            'W': 'Snow-Covered Plains',
            'U': 'Snow-Covered Island', 
            'B': 'Snow-Covered Swamp',
            'R': 'Snow-Covered Mountain',
            'G': 'Snow-Covered Forest',
            'COLORLESS': 'Snow-Covered Wastes'
            }
        
        print(f'Adding {base_basics} basic lands distributed across {len(self.colors)} colors')
        
        # Add equal distribution first
        for color in self.colors:
            basic = color_to_basic.get(color)
            if basic:
                for _ in range(basics_per_color):
                    self.add_card(basic, 'Basic Land', None, 0)
        
        # Distribute remaining basics based on color requirements
        if remaining_basics > 0:
            for color in self.colors[:remaining_basics]:
                basic = color_to_basic.get(color)
                if basic:
                    self.add_card(basic, 'Basic Land', None, 0)
        
        lands_to_remove = []
        for key in color_to_basic:
            basic = color_to_basic.get(key)
            lands_to_remove.append(basic)
            
        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)

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
                self.add_card(card, 'Land', None, 0)
            else:
                pass
        
        lands_to_remove = self.staples
        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
    
    def add_fetches(self):
        # Determine how many fetches in total
        print('How many fetch lands would you like to include?\n'
              'For most decks you\'ll likely be good with 3 or 4, just enough to thin the deck and help ensure the color availability.\n'
              'If you\'re doing Landfall, more fetches would be recommended just to get as many Landfall triggers per turn.')
        answer = self.questionnaire('Number', 2)
        MAX_ATTEMPTS = 50  # Maximum attempts to prevent infinite loops
        attempt_count = 0
        desired_fetches = int(answer)
        chosen_fetches = []
        
        generic_fetches = [
            'Evolving Wilds', 'Terramorphic Expanse', 'Shire Terrace', 
            'Escape Tunnel', 'Promising Vein', 'Myriad Landscape', 
            'Fabled Passage', 'Terminal Moraine'
        ]
        fetches = generic_fetches.copy()
        lands_to_remove = generic_fetches.copy()
        
        # Adding in expensive fetches
        if (use_scrython and self.set_max_card_price):
            if self.price_check('Prismatic Vista') <= self.max_card_price * 1.1:
                lands_to_remove.append('Prismatic Vista')
                fetches.append('Prismatic Vista')
            else:
                lands_to_remove.append('Prismatic Vista')
                pass
        else:
            lands_to_remove.append('Prismatic Vista')
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
                if fetch not in lands_to_remove:
                    lands_to_remove.extend(fetch)
        for color in color_to_fetch:
            fetch = color_to_fetch.get(color)
            if fetch not in fetches:
                fetches.extend(fetch)
                if fetch not in lands_to_remove:
                    lands_to_remove.extend(fetch)
        
        # Randomly choose fetches up to the desired number
        while len(chosen_fetches) < desired_fetches + 3 and attempt_count < MAX_ATTEMPTS:
            if not fetches:  # If we run out of fetches to choose from
                break
                
            fetch_choice = random.choice(fetches)
            if use_scrython and self.set_max_card_price:
                if self.price_check(fetch_choice) <= self.max_card_price * 1.1:
                    chosen_fetches.append(fetch_choice)
                    fetches.remove(fetch_choice)
            else:
                chosen_fetches.append(fetch_choice)
                fetches.remove(fetch_choice)
                
            attempt_count += 1

        # Select final fetches to add
        fetches_to_add = []
        available_fetches = chosen_fetches[:desired_fetches]
        for fetch in available_fetches:
            if fetch not in fetches_to_add:
                fetches_to_add.append(fetch)

        if attempt_count >= MAX_ATTEMPTS:
            logging.warning(f"Reached maximum attempts ({MAX_ATTEMPTS}) while selecting fetch lands")

        for card in fetches_to_add:
            self.add_card(card, 'Land', None, 0)
            
        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
    
    def add_kindred_lands(self):
        print('Adding lands that care about the commander having a Kindred theme.')
        print('Adding general Kindred lands.')

        def create_land(name: str, land_type: str) -> dict:
            """Helper function to create land card dictionaries"""
            return {
                'name': name,
                'type': land_type,
                'manaCost': None,
                'manaValue': 0
            }
        
        kindred_lands = [
            create_land('Path of Ancestry', 'Land'),
            create_land('Three Tree City', 'Legendary Land'),
            create_land('Cavern of Souls', 'Land')
        ]

        for theme in self.themes:
            if 'Kindred' in theme:
                kindred = theme.replace(' Kindred', '')
                print(f'Adding any {kindred}-specific lands.')
                for _, row in self.land_df.iterrows():
                    card = {
                        'name': row['name'],
                        'type': row['type'],
                        'manaCost': row['manaCost'],
                        'manaValue': row['manaValue']
                    }
                    if pd.isna(row['text']):
                        continue
                    if pd.isna(row['type']):
                        continue
                    if (kindred in row['text']) or (kindred in row['type']):
                        kindred_lands.append(card)

        lands_to_remove = []
        for card in kindred_lands:
            self.add_card(card['name'], card['type'], 
                        card['manaCost'], card['manaValue'])
            lands_to_remove.append(card['name'])

        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
    
    def add_dual_lands(self):
        # Determine dual-color lands available 
        
        # Determine if using the dual-type lands
        print('Would you like to include Dual-type lands (i.e. lands that count as both a Plains and a Swamp for example)?')
        choice = self.questionnaire('Confirm', True)
        color_filter = []
        color_dict = {
            'azorius': 'Plains Island',
            'dimir': 'Island Swamp',
            'rakdos': 'Swamp Mountain',
            'gruul': 'Mountain Forest',
            'selesnya': 'Forest Plains',
            'orzhov': 'Plains Swamp',
            'golgari': 'Swamp Forest',
            'simic': 'Forest Island',
            'izzet': 'Island Mountain',
            'boros': 'Mountain Plains'
        }
        
        if choice:
            for key in color_dict:
                if key in self.files_to_load:
                    color_filter.extend([f'Land — {color_dict[key]}', f'Snow Land — {color_dict[key]}'])
            
            dual_df = self.land_df[self.land_df['type'].isin(color_filter)].copy()
            
            # Convert to list of card dictionaries
            card_pool = []
            for _, row in dual_df.iterrows():
                card = {
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue']
                }
                card_pool.append(card)
            
            lands_to_remove = []
            for card in card_pool:
                self.add_card(card['name'], card['type'], 
                            card['manaCost'], card['manaValue'])
                lands_to_remove.append(card['name'])

            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
            
            print(f'Added {len(card_pool)} Dual-type land cards.')
            
        if not choice:
            print('Skipping adding Dual-type land cards.')
    
    def add_triple_lands(self):
        # Determine if using Triome lands
        print('Would you like to include triome lands (i.e. lands that count as a Mountain, Forest, and Plains for example)?')
        choice = self.questionnaire('Confirm', True)
        
        color_filter = []
        color_dict = {
            'bant': 'Forest Plains Island',
            'esper': 'Plains Island Swamp',
            'grixis': 'Island Swamp Mountain',
            'jund': 'Swamp Mountain Forest',
            'naya': 'Mountain Forest Plains',
            'mardu': 'Mountain Plains Swamp',
            'abzan': 'Plains Swamp Forest',
            'sultai': 'Swamp Forest Island',
            'temur': 'Forest Island Mountain',
            'jeska': 'Island Mountain Plains'
        }
        
        if choice:
            for key in color_dict:
                if key in self.files_to_load:
                    color_filter.extend([f'Land — {color_dict[key]}'])
            
            triome_df = self.land_df[self.land_df['type'].isin(color_filter)].copy()
        
            # Convert to list of card dictionaries
            card_pool = []
            for _, row in triome_df.iterrows():
                card = {
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue']
                }
                card_pool.append(card)
            
            lands_to_remove = []
            for card in card_pool:
                self.add_card(card['name'], card['type'], 
                            card['manaCost'], card['manaValue'])
                lands_to_remove.append(card['name'])

            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
            
            print(f'Added {len(card_pool)} Triome land cards.')
            
        if not choice:
            print('Skipping adding Triome land cards.')
    
    def add_misc_lands(self):
        print('Adding additional misc. lands to the deck that fit the color identity.')
        # Add other remaining lands that match color identity

        logging.info('Grabbing lands in your commander\'s color identity that aren\'t already in the deck.')
        # Create a copy of land DataFrame and limit rows if needed for performance
        land_df_misc = self.land_df.copy()
        land_df_misc = land_df_misc.head(100) if len(land_df_misc) > 100 else land_df_misc
        logging.debug(f"Land DataFrame contents:\n{land_df_misc}")

        card_pool = []
        for _, row in land_df_misc.iterrows():
            card = {
                'name': row['name'],
                'type': row['type'],
                'manaCost': row['manaCost'],
                'manaValue': row['manaValue']
            }
            if card['name'] not in self.card_library['Card Name'].values:
                card_pool.append(card)
        # Add cards to the deck library
        cards_to_add = []

        while len(cards_to_add) < random.randint(5, 15):
            card = random.choice(card_pool)
            card_pool.remove(card)
            
            # Check price constraints if enabled
            if use_scrython and self.set_max_card_price:
                price = self.price_check(card['name'])
                if price > self.max_card_price * 1.1:
                    continue
            # Add card if not already in library
            if (card['name'] not in self.card_library['Card Name'].values):
                cards_to_add.append(card)
        
        # Add selected cards to library
        lands_to_remove = []
        for card in cards_to_add:
            self.add_card(card['name'], card['type'], 
                         card['manaCost'], card['manaValue'])
            lands_to_remove.append(card['name'])

        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)

        print(f'Added {len(cards_to_add)} land cards.')
                
    def check_basics(self):
        """Check and display counts of each basic land type."""
        basic_lands = {
            'Plains': 0,
            'Island': 0, 
            'Swamp': 0,
            'Mountain': 0,
            'Forest': 0,
            'Snow-Covered Plains': 0,
            'Snow-Covered Island': 0,
            'Snow-Covered Swamp': 0,
            'Snow-Covered Mountain': 0,
            'Snow-Covered Forest': 0
        }
        
        self.total_basics = 0
        for land in basic_lands:
            count = len(self.card_library[self.card_library['Card Name'] == land])
            basic_lands[land] = count
            self.total_basics += count
        
        print("\nBasic Land Counts:")
        for land, count in basic_lands.items():
            if count > 0:
                print(f"{land}: {count}")
        print(f"Total basic lands: {self.total_basics}\n")
   
    def remove_basic(self):
        """
        Remove a basic land while maintaining color balance.
        Attempts to remove from colors with more basics first.
        """
        logging.info('Land count over ideal count, removing a basic land.')

        # Map colors to basic land names
        color_to_basic = {
            'W': 'Plains',
            'U': 'Island',
            'B': 'Swamp',
            'R': 'Mountain',
            'G': 'Forest'
        }

        # Count basics of each type
        basic_counts = {}
        for color in self.colors:
            basic = color_to_basic.get(color)
            if basic:
                count = len(self.card_library[self.card_library['Card Name'] == basic])
                if count > 0:
                    basic_counts[basic] = count

        if not basic_counts:
            logging.warning("No basic lands found to remove")
            return
        sum_basics = sum(basic_counts.values())

        # Try to remove from color with most basics
        basic_land = max(basic_counts.items(), key=lambda x: x[1])[0]
        if sum_basics > self.min_basics:
            try:
                logging.info(f'Attempting to remove {basic_land}')
                condition = self.card_library['Card Name'] == basic_land
                index_to_drop = self.card_library[condition].index[0]

                self.card_library = self.card_library.drop(index_to_drop)
                self.card_library = self.card_library.reset_index(drop=True)

                logging.info(f'{basic_land} removed successfully')
                self.check_basics()

            except (IndexError, KeyError) as e:
                logging.error(f"Error removing {basic_land}: {e}")
                # Iterative approach instead of recursion
                while basic_counts:
                    basic_counts.pop(basic_land, None)
                    if not basic_counts:
                        logging.error("Failed to remove any basic land")
                        break
                    
                    basic_land = max(basic_counts.items(), key=lambda x: x[1])[0]
                    try:
                        condition = self.card_library['Card Name'] == basic_land
                        index_to_drop = self.card_library[condition].index[0]
                        self.card_library = self.card_library.drop(index_to_drop)
                        self.card_library = self.card_library.reset_index(drop=True)
                        logging.info(f'{basic_land} removed successfully')
                        self.check_basics()
                        break
                    except (IndexError, KeyError):
                        continue
        else:
            print(f'Not enough basic lands to keep the minimum of {self.min_basics}.')
            self.remove_land()
    
    def remove_land(self):
        """Remove a random non-basic, non-staple land from the deck."""
        print('Removing a random nonbasic land.')

        # Define basic lands including snow-covered variants
        basic_lands = [
            'Plains', 'Island', 'Swamp', 'Mountain', 'Forest',
            'Snow-Covered Plains', 'Snow-Covered Island', 'Snow-Covered Swamp',
            'Snow-Covered Mountain', 'Snow-Covered Forest'
        ]

        try:
            # Filter for non-basic, non-staple lands
            library_filter = self.card_library[
                (self.card_library['Card Type'].str.contains('Land')) & 
                (~self.card_library['Card Name'].isin(basic_lands + self.staples))
            ].copy()

            if len(library_filter) == 0:
                print("No suitable non-basic lands found to remove.")
                return

            # Select random land to remove
            card_index = np.random.choice(library_filter.index)
            card_name = self.card_library.loc[card_index, 'Card Name']

            print(f"Removing {card_name}")
            self.card_library.drop(card_index, inplace=True)
            self.card_library.reset_index(drop=True, inplace=True)
            print("Card removed successfully.")

        except Exception as e:
            logging.error(f"Error removing land: {e}")
            print("Failed to remove land card.")
    
    def count_pips(self):
        """Count and display the number of colored mana symbols in casting costs."""
        print('Analyzing color pip distribution...')
        
        pip_counts = {
            'W': 0, 'U': 0, 'B': 0, 'R': 0, 'G': 0
        }
        
        for cost in self.card_library['Mana Cost'].dropna():
            for color in pip_counts:
                pip_counts[color] += cost.count(color)
        
        total_pips = sum(pip_counts.values())
        if total_pips == 0:
            print("No colored mana symbols found in casting costs.")
            return
        
        print("\nColor Pip Distribution:")
        for color, count in pip_counts.items():
            if count > 0:
                percentage = (count / total_pips) * 100
                print(f"{color}: {count} pips ({percentage:.1f}%)")
        print(f"Total colored pips: {total_pips}\n")
        
    def get_cmc(self):
        """Calculate average converted mana cost of non-land cards."""
        logging.info('Calculating average mana value of non-land cards.')
        
        try:
            # Filter non-land cards
            non_land = self.card_library[
                ~self.card_library['Card Type'].str.contains('Land')
            ].copy()
            
            if non_land.empty:
                logging.warning("No non-land cards found")
                self.cmc = 0.0
            else:
                total_cmc = non_land['Mana Value'].sum()
                self.cmc = round(total_cmc / len(non_land), 2)
            
            self.commander_dict.update({'CMC': float(self.cmc)})
            logging.info(f"Average CMC: {self.cmc}")
            
        except Exception as e:
            logging.error(f"Error calculating CMC: {e}")
            self.cmc = 0.0
    
    def weight_by_theme(self, tag, ideal=1, weight=1):
        # First grab the first 50/30/20 cards that match each theme
        """Add cards with specific tag up to ideal_value count"""
        ideal_value = math.ceil(ideal * weight * 0.9)
        print(f'Finding {ideal_value} cards with the "{tag}" tag...')
        if 'Kindred' in tag:
            tags = [tag, 'Kindred Support']
        else:
            tags = [tag]
        # Filter cards with the given tag
        tag_df = self.creature_df.copy()
        tag_df.sort_values(by='edhrecRank', inplace=True)
        tag_df = tag_df[tag_df['themeTags'].apply(lambda x: any(tag in x for tag in tags))]
        # Take top cards based on ideal value
        pool_size = int(ideal_value * random.randint(15, 20) /10)
        tag_df = tag_df.head(pool_size)
        print(tag_df)
        
        # Convert to list of card dictionaries
        card_pool = [
            {
                'name': row['name'],
                'type': row['type'],
                'manaCost': row['manaCost'],
                'manaValue': row['manaValue']
            }
            for _, row in tag_df.iterrows()
        ]

        # Randomly select cards up to ideal value
        cards_to_add = []
        while len(cards_to_add) < ideal_value and card_pool:
            card = random.choice(card_pool)
            card_pool.remove(card)
            
            # Check price constraints if enabled
            if use_scrython and self.set_max_card_price:
                price = self.price_check(card['name'])
                if price > self.max_card_price * 1.1:
                    continue
                    
            # Add card if not already in library
            
            if card['name'] in multiple_copy_cards:
                if card['name'] == 'Nazgûl':
                    for _ in range(9):
                        cards_to_add.append(card)
                elif card['name'] == 'Seven Dwarves':
                    for _ in range(7):
                        cards_to_add.append(card)
                else:
                    num_to_add = ideal_value - len(cards_to_add)
                    for _ in range(num_to_add):
                        cards_to_add.append(card)
            
            elif (card['name'] not in multiple_copy_cards
                  and card['name'] not in self.card_library['Card Name'].values):
                cards_to_add.append(card)
                
            elif (card['name'] not in multiple_copy_cards
                  and card['name'] in self.card_library['Card Name'].values):
                print(f"{card['name']} already in Library, skipping it.")
                continue
        
        # Add selected cards to library
        for card in cards_to_add:
            self.add_card(card['name'], card['type'], 
                         card['manaCost'], card['manaValue'])
        
        card_pool_names = [item['name'] for item in card_pool]
        self.full_df = self.full_df[~self.full_df['name'].isin(card_pool_names)]
        self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(card_pool_names)]
        print(f'Added {len(cards_to_add)} {tag} cards')
        #tag_df.to_csv(f'{csv_directory}/test_{tag}.csv', index=False)
    
    def add_by_tags(self, tag, ideal_value=1):
        """Add cards with specific tag up to ideal_value count"""
        print(f'Finding {ideal_value} cards with the "{tag}" tag...')

        # Filter cards with the given tag
        skip_creatures = self.creature_cards > self.ideal_creature_count * 1.1
        if skip_creatures:
            tag_df = self.noncreature_df.copy()
        else:
            tag_df = self.full_df.copy()
        tag_df.sort_values(by='edhrecRank', inplace=True)
        tag_df = tag_df[tag_df['themeTags'].apply(lambda x: tag in x)]
        # Take top cards based on ideal value
        pool_size = int(ideal_value * random.randint(2, 3))
        tag_df = tag_df.head(pool_size)

        # Convert to list of card dictionaries
        card_pool = [
            {
                'name': row['name'],
                'type': row['type'],
                'manaCost': row['manaCost'],
                'manaValue': row['manaValue']
            }
            for _, row in tag_df.iterrows()
        ]

        # Randomly select cards up to ideal value
        cards_to_add = []
        while len(cards_to_add) < ideal_value and card_pool:
            card = random.choice(card_pool)
            card_pool.remove(card)

            # Check price constraints if enabled
            if use_scrython and self.set_max_card_price:
                price = self.price_check(card['name'])
                if price > self.max_card_price * 1.1:
                    continue

            # Add card if not already in library
            if card['name'] not in self.card_library['Card Name'].values:
                if 'Creature' in card['type'] and skip_creatures:
                    continue
                else:
                    if 'Creature' in card['type']:
                        self.creature_cards += 1
                        skip_creatures = self.creature_cards > self.ideal_creature_count * 1.1
                    cards_to_add.append(card)

        # Add selected cards to library
        for card in cards_to_add:
            if len(self.card_library) < 100:
                self.add_card(card['name'], card['type'], 
                            card['manaCost'], card['manaValue'])
            else:
                continue

        card_pool_names = [item['name'] for item in card_pool]
        self.full_df = self.full_df[~self.full_df['name'].isin(card_pool_names)]
        self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(card_pool_names)]
        print(f'Added {len(cards_to_add)} {tag} cards')
        #tag_df.to_csv(f'{csv_directory}/test_{tag}.csv', index=False)
        
    def add_creatures(self):
        """
        Add creatures to the deck based on themes and weights.
        
        This method processes the primary, secondary, and tertiary themes to add
        creatures proportionally according to their weights. The total number of
        creatures added will approximate the ideal_creature_count.
        
        Themes are processed in order of importance (primary -> secondary -> tertiary)
        with error handling to ensure the deck building process continues even if
        a particular theme encounters issues.
        """
        print(f'Adding creatures to deck based on the ideal creature count of {self.ideal_creature_count}...')
        
        try:
            if self.hidden_theme:
                print(f'Processing Hidden theme: {self.hidden_theme}')
                self.weight_by_theme(self.hidden_theme, self.ideal_creature_count, self.hidden_weight)
 
            print(f'Processing primary theme: {self.primary_theme}')
            self.weight_by_theme(self.primary_theme, self.ideal_creature_count, self.primary_weight)
            
            if self.secondary_theme:
                print(f'Processing secondary theme: {self.secondary_theme}')
                self.weight_by_theme(self.secondary_theme, self.ideal_creature_count, self.secondary_weight)
            
            if self.tertiary_theme:
                print(f'Processing tertiary theme: {self.tertiary_theme}')
                self.weight_by_theme(self.tertiary_theme, self.ideal_creature_count, self.tertiary_weight)
                
        except Exception as e:
            logging.error(f"Error while adding creatures: {e}")
        finally:
            self.organize_library()
            print(f'Creature addition complete. Total creatures (including commander): {self.creature_cards}')
    
    def add_ramp(self):
        self.add_by_tags('Mana Rock', math.ceil(self.ideal_ramp / 4))
        self.add_by_tags('Mana Dork', math.ceil(self.ideal_ramp / 3))
        self.add_by_tags('Ramp', math.ceil(self.ideal_ramp / 2))
    
    def add_interaction(self):
        self.add_by_tags('Removal', self.ideal_removal)
        self.add_by_tags('Protection', self.ideal_protection)
        
    def add_board_wipes(self):
        self.add_by_tags('Board Wipes', self.ideal_wipes)
        
    def add_card_advantage(self):
        self.add_by_tags('Conditional Draw', math.ceil(self.ideal_card_advantage * 0.2))
        self.add_by_tags('Unconditional Draw', math.ceil(self.ideal_card_advantage * 0.8))
    
    def fill_out_deck(self):
        """Fill out the deck to 100 cards with theme-appropriate cards."""
        print('Filling out the Library to 100 with cards fitting the themes.')
        
        cards_needed = 100 - len(self.card_library)
        if cards_needed <= 0:
            return
        
        logging.info(f"Need to add {cards_needed} more cards")
        MAX_ATTEMPTS = max(20, cards_needed * 2)  # Scale attempts with cards needed
        attempts = 0
        
        while len(self.card_library) < 100 and attempts < MAX_ATTEMPTS:
            initial_count = len(self.card_library)
            remaining = 100 - len(self.card_library)
            
            # Adjust weights based on remaining cards needed
            weight_multiplier = remaining / cards_needed
            
            if self.tertiary_theme:
                self.add_by_tags(self.tertiary_theme, 
                    math.ceil(self.tertiary_weight * 3 * weight_multiplier))
            if self.secondary_theme:
                self.add_by_tags(self.secondary_theme, 
                    math.ceil(self.secondary_weight * weight_multiplier))
            self.add_by_tags(self.primary_theme, 
                math.ceil(self.primary_weight * weight_multiplier))
            
            if len(self.card_library) == initial_count:
                attempts += 1
                if attempts % 5 == 0:  # Log progress every 5 failed attempts
                    logging.warning(f"Made {attempts} attempts, still need {100 - len(self.card_library)} cards")
            
        final_count = len(self.card_library)
        if final_count < 100:
            logging.warning(f"Could not reach 100 cards after {attempts} attempts. Current count: {final_count}")
            print(f"\nWARNING: Deck is incomplete with {final_count} cards. Manual additions may be needed.")
        else:
            logging.info(f"Successfully filled deck to {final_count} cards in {attempts} attempts")

def main():
    """Main entry point for deck builder application."""
    build_deck = DeckBuilder()
    build_deck.determine_commander()
    pprint.pprint(build_deck.commander_dict, sort_dicts=False)

if __name__ == '__main__':
    main()

#pprint.pprint(build_deck.card_library['Card Name'], sort_dicts = False)