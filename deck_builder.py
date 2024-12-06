from __future__ import annotations

import inquirer.prompt # type: ignore
import pandas as pd # type: ignore
import pprint # type: ignore

from fuzzywuzzy import fuzz, process # type: ignore
from IPython.display import display

# Basic deck builder, initial plan will just be for kindred support.
# Would like to add logic for other themes, as well as automatically go
# through the commander and find suitable themes.

# Will have it ask questions to determine number of creatures, lands,
# interaction, ramp, etc... then adjust from there. 
# Land spread will ideally be handled based on pips and some adjustment
# is planned based on mana curve and ramp added

# Later plans to have card price taken into account will be added. Lands

class DeckBuilder:
    def __init__(self):
        # Commander
        self.commander = ''
        self.commander_info = {}
        
        # Library (99 cards total)
        self.library = []
        
        # Number of cards that do/are what
        self.land_count = 0
        self.creature_count = 0
        self.removal = 0
        self.wipes = 0
        self.card_advantage = 0
        self.ramp = 0
        self.protection = 0
        
        # Ideal number of cards that do/are what
        self.ideal_land_count = 0
        self.ideal_creature_count = 0
        self.ideal_removal = 0
        self.ideal_wipes = 0
        self.ideal_card_advantage = 0
        self.ideal_ramp = 0
        self.ideal_protection = 0
        
        # Cards that are what type
        # Lands
        self.land_cards = []
        self.lands = len(self.land_cards)
        # Creatures
        self.creature_cards = []
        self.creatures = len(self.creature_cards)
        
        # Instants
        self.instant_cards = []
        self.instants = len(self.creature_cards)
        
        # Sorceries
        self.sorcery_cards = []
        self.sorceries = len(self.sorcery_cards)
        
        # Artifacts
        self.artifact_cards = []
        self.artifacts = len(self.artifact_cards)
        
        # Enchantments
        self.enchantment_cards = []
        self.enchantments = len(self.enchantment_cards)
        
        # Planeswalkers
        self.planeswalker_cards = []
        self.planeswalkers = len(self.planeswalker_cards)
        
        # Battles
        self.battle_cards = []
        self.battles = len(self.battle_cards)
        
    def determine_commander(self):
        # Determine the commander of the deck
        commander_chosen = False
        while not commander_chosen:
            print('Enter a card name to be your commander, note that at this time only cards that have the \'Creature\' type may be chosen')
            question = [
                inquirer.Text(
                    'card_prompt',
                    message=''
                )
            ]
            answer = inquirer.prompt(question)
            card_choice = answer['card_prompt']
            
            # Logic to find the card in the legendary_cards csv, then display it's information
            df = pd.read_csv('csv_files/legendary_cards.csv', low_memory=False)
            fuzzy_card_choice = process.extractOne(card_choice, df['name'], scorer=fuzz.ratio)
            fuzzy_card_choice = fuzzy_card_choice[0]
            filtered_df = df[df['name'] == fuzzy_card_choice]
            columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness', 'text']
            filtered_df = filtered_df[columns_to_keep]
            df_dict = filtered_df.to_dict('list')
            print('Is this the card you chose?')
            pprint.pprint(df_dict, sort_dicts=False)
            
            # Confirm if card entered was correct
            correct_commander = [
                inquirer.Confirm(
                    'commander',
                )
            ]
            confirm_commander = inquirer.prompt(correct_commander)
            commander_confirmed = confirm_commander['commander']
            # If correct, set it as the commander
            if commander_confirmed:
                commander_chosen = True
                self.commander_info = df_dict
                first_key = list(self.commander_info.keys())[0]
                self.commander = str(self.commander_info[first_key])
                #print(self.commander)
            else:
                commander_chosen = False
        
    def determine_ideals(self):
        # Determine ideal land count
        question = [
            inquirer.Text
        ]

build_deck = DeckBuilder()
build_deck.determine_commander()
print(build_deck.commander)
