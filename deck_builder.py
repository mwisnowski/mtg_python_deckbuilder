from __future__ import annotations

import inquirer.prompt # type: ignore
import keyboard # type: ignore
import pandas as pd # type: ignore
import pprint # type: ignore
import random

from fuzzywuzzy import fuzz, process # type: ignore

from settings import csv_directory
from setup import determine_commanders, set_lands


pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 20)

"""def pluralize_list(singular_list):
    engine = inflect.engine()
    plural_list = [engine.plural(creature_type) for creature_type in singular_list]
    return plural_list

singular_words = settings.creature_types
plural_words = pluralize_list(singular_words)
creature_type_list = settings.creature_types + plural_words"""
#print(plural_words)

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
        self.color_identity = ''
        self.colors = []
        self.creature_types = []
        self.commander_tags = []
        self.commander_df = pd.DataFrame()
        
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
        
        # Creatures
        self.creature_cards = []
        
        # Instants
        self.instant_cards = []
        
        # Sorceries
        self.sorcery_cards = []
        
        # Artifacts
        self.artifact_cards = []
        
        # Enchantments
        self.enchantment_cards = []
        
        # Planeswalkers
        self.planeswalker_cards = []
        
        # Battles
        self.battle_cards = []
        
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
            question = [
                inquirer.Text(
                    'card_prompt',
                    message=''
                )
            ]
            answer = inquirer.prompt(question)
            card_choice = answer['card_prompt']
            
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
                    question = [
                        inquirer.List('choices',
                                    choices=fuzzy_card_choices,
                                    carousel=True)
                    ]
                    answer = inquirer.prompt(question)
                    fuzzy_card_choice = answer['choices']
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
                    self.commander = self.commander_df.at[0, 'name']
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
        print(self.color_identity)
        self.color_identity_full = ''
        self.determine_color_identity()
        
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
        self.determine_ideals()
        self.add_lands()
        
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
        
        # Thri-color
        elif self.color_identity == 'B, G, U':
            self.color_identity_full = 'Sultai: Black/Blue/Green'
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'dimir', 'golgari', 'simic', 'sultai']
            pass
        elif self.color_identity == 'B, G, R':
            self.color_identity_full = 'Jund: Black/Green/Red'
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'golgari', 'rakdos', 'gruul', 'jund']
            pass
        elif self.color_identity == 'B, G, W':
            self.color_identity_full = 'Abzan: Black/Green/White'
            self.files_to_load = ['colorless', 'black', 'green', 'white', 'golgari', 'orzhov', 'selesnya', 'abzan']
            pass
        elif self.color_identity == 'B, R, U':
            self.color_identity_full = 'Grixis: Black/Blue/Red'
            self.files_to_load = ['colorless', 'black', 'blue', 'red', 'dimir', 'rakdos', 'izzet', 'grixis']
            pass
        elif self.color_identity == 'B, R, W':
            self.color_identity_full = 'Mardu: Black/Red/White'
            self.files_to_load = ['colorless', 'black', 'red', 'white', 'rakdos', 'orzhov', 'boros', 'mardu']
            pass
        elif self.color_identity == 'B, U, W':
            self.color_identity_full = 'Esper: Black/Blue/White'
            self.files_to_load = ['colorless', 'black', 'blue', 'white', 'dimir', 'orzhov', 'azorius', 'esper']
            pass
        elif self.color_identity == 'G, R, U':
            self.color_identity_full = 'Temur: Blue/Green/Red'
            self.files_to_load = ['colorless', 'green', 'red', 'blue', 'simir', 'izzet', 'gruul', 'temur']
            pass
        elif self.color_identity == 'G, R, W':
            self.color_identity_full = 'Naya: Green/Red/White'
            self.files_to_load = ['colorless', 'green', 'red', 'white', 'gruul', 'selesnya', 'boros', 'naya']
            pass
        elif self.color_identity == 'G, U, W':
            self.color_identity_full = 'Bant: Blue/Green/White'
            self.files_to_load = ['colorless', 'green', 'blue', 'white', 'simir', 'azorius', 'selesnya', 'bant']
            pass
        elif self.color_identity == 'U, R, W':
            self.color_identity_full = 'Jeskai: Blue/Red/White'
            self.files_to_load = ['colorless', 'blue', 'red', 'white', 'izzet', 'azorius', 'boros', 'jeskai']
            pass
        
        # Quad-color
        elif self.color_identity == 'B, G, R, U':
            self.color_identity_full = 'Glint: Black/Blue/Green/Red'
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'red', 'golgari', 'rakdos', 'dimir', 'gruul',
                                  'simic', 'izzet', 'jund', 'sultai', 'grixis', 'temur', 'glint']
            pass
        elif self.color_identity == 'B, G, R, W':
            self.color_identity_full = 'Dune: Black/Green/Red/White'
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'white', 'golgari', 'rakdos', 'orzhov', 'gruul',
                                  'selesnya', 'boros', 'jund', 'abzan', 'mardu', 'naya', 'dune']
            pass
        elif self.color_identity == 'B, G, U, W':
            self.color_identity_full = 'Witch: Black/Blue/Green/White'
            self.files_to_load = ['colorless', 'black', 'blue', 'green', 'white', 'golgari', 'dimir', 'orzhov', 'simic',
                                  'selesnya', 'azorius', 'sultai', 'abzan', 'esper', 'bant', 'glint']
            pass
        elif self.color_identity == 'B, R, U, W':
            self.color_identity_full = 'Yore: Black/Blue/Red/White'
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
            self.files_to_load = ['colorless', 'black', 'green', 'red', 'blue', 'white', 'golgari', 'rakdos',' dimir',
                                  'orzhov', 'gruul', 'simic', 'selesnya', 'izzet', 'boros', 'azorius', 'jund', 'sultai', 'abzan',
                                  'grixis', 'mardu', 'esper', 'temur', 'naya', 'bant', 'jeska', 'glint', 'dune','witch', 'yore',
                                  'ink']
    
    def determine_themes(self):
        themes = self.commander_tags
        print('Your commander deck will likely have a number of viable themes, but you\'ll want to narrow it down for focus.\n'
                'This will go through the process of choosing up to three themes for the deck.')
        while True:
            # Choose a primary theme
            print('Choose a primary theme for your commander deck.\n'
                'This will be the "focus" of the deck, in a kindred deck this will typically be a creature type for example.\n')
            question = [
                inquirer.List('theme',
                            choices=themes,
                            carousel=True)
            ]
            answer = inquirer.prompt(question)
            choice = answer['theme']
            self.primary_theme = choice
            themes.remove(choice)
            themes.append('Stop Here')
            
            secondary_theme_chosen = False
            tertiary_theme_chosen = False
            
            while not secondary_theme_chosen:
                # Secondary theme
                print('Choose a secondary theme for your commander deck.\n'
                    'This will typically be a secondary focus, like card draw for Spellslinger, or +1/+1 counters for Aggro.')
                question = [
                    inquirer.List('theme',
                                choices=themes,
                                carousel=True)
                ]
                answer = inquirer.prompt(question)
                choice = answer['theme']
                while True:
                    if choice == 'Stop Here':
                        print('You\'ve only selected one theme, are you sure you want to stop?')
                        confirm_themes = [
                            inquirer.Confirm(
                                'done',
                            )
                        ]
                        answer = inquirer.prompt(confirm_themes)
                        confirm_done = answer['done']
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
                        break
            
            while not tertiary_theme_chosen:
                # Tertiary theme
                print('Choose a secondary theme for your commander deck.\n'
                    'This will typically be a tertiary focus, or just something else to do that your commander is good at.')
                question = [
                    inquirer.List('theme',
                                choices=themes,
                                carousel=True)
                ]
                answer = inquirer.prompt(question)
                choice = answer['theme']
                while True:
                    if choice == 'Stop Here':
                        print('You\'ve only selected two themes, are you sure you want to stop?')
                        confirm_themes = [
                            inquirer.Confirm(
                                'done',
                            )
                        ]
                        answer = inquirer.prompt(confirm_themes)
                        confirm_done = answer['done']
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
                        break
            break
        
    def determine_ideals(self):
        # "Free" slots that can be used for anything that isn't the ideals
        self.free_slots = 99
        
        # Determine ideal land count
        print('How many lands would you like to include?\n'
              'Before ramp is taken into account, 38-40 would be "normal" for a deck. I personally use 35.\n'
              'Broadly speaking, for every mana produced per 3 mana spent on ramp could reduce land count by 1.\n'
              'If you\'re playing landfall, probably consider 40 as baseline before ramp.')
        question = [
            inquirer.Text(
                'land_prompt',
                default='35'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_land_count = int(answer['land_prompt'])
        self.free_slots -= self.ideal_land_count
        
        # Determine ideal creature count
        print('How many creatures would you like to include?\n'
              'Something like 25-30 would be a good starting point.\n'
              'If you\'re going for a kindred theme, going past 30 is likely normal.\n'
              'Also be sure to take into account token generation, but remember you\'ll want enough to stay safe')
        question = [
            inquirer.Text(
                'creature_prompt',
                default='25'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_creature_count = int(answer['creature_prompt'])
        self.free_slots -= self.ideal_creature_count
        
        # Determine spot/targetted removal
        print('How many spot removal pieces would you like to include?\n'
              'A good starting point is about 8-12 pieces of spot removal.\n'
              'Counterspells can be consisdered proactive removal and protection.\n'
              'If you\'re going spellslinger, more would be a good idea as you might have less cretaures.')
        question = [
            inquirer.Text(
                'removal_prompt',
                default='10'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_removal = int(answer['removal_prompt'])
        self.free_slots -= self.ideal_removal
        
        # Determine board wipes
        print('How many board wipesyou like to include?\n'
              'Somewhere around 2-3 is good to help eliminate threats, but also prevent the game from running long\n.'
              'This can include damaging wipes like \'Blasphemous Act\' or toughness reduction like \'Meathook Massacre\'.')
        question = [
            inquirer.Text(
                'board_wipe_prompt',
                default='2'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_wipes = int(answer['board_wipe_prompt'])
        self.free_slots -= self.ideal_wipes
        
        # Determine card advantage
        print('How many pieces of card advantage would you like to include?\n'
              '10 pieces of card advantage is good, up to 14 is better.\n'
              'Try to have a majority of it be non-conditional, and only have a couple of \'Rhystic Study\' style effects.')
        question = [
            inquirer.Text(
                'draw_prompt',
                default='10'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_card_advantage = int(answer['draw_prompt'])
        self.free_slots -= self.ideal_card_advantage
        
        # Determine ramp
        print('How many pieces of ramp would you like to include?\n'
              'You\'re gonna want a decent amount of ramp, both getting lands or mana rocks/dorks.\n'
              'A good baseline is 8-12, scaling up with average CMC.')
        question = [
            inquirer.Text(
                'ramp_prompt',
                default='8'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_ramp = int(answer['ramp_prompt'])
        self.free_slots -= self.ideal_ramp
        
        # Determine how many protection spells
        print('How protection spells would you like to include?\n'
              'This can be individual protection, board protection, fogs, or similar effects.\n'
              'Things that grant indestructible, hexproof, phase out, or event just counterspells.\n'
              'This can be a widely variable ideal count, and can be as low as 5, and up past 15,\n'
              'it depends on your commander and how important your wincons are.')
        question = [
            inquirer.Text(
                'protection_prompt',
                default='8'
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_protection = int(answer['protection_prompt'])
        self.free_slots -= self.ideal_protection
        
        print(f'Free slots that aren\'t part of the ideals: {self.free_slots}')
        print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')
    
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
        self.land_df = pd.read_csv(f'{csv_directory}/land_cards.csv')
        # Begin the process to add lands, the number will depend on ideal land count, ramp,
        # and if any utility lands may be helpful.
        # By default, ({self.ideal_land_count} - 5) basic lands will be added, distributed
        # across the commander color identity. These will be removed for utility lands, 
        # multi-color producing lands, fetches, and any MDFCs added later
        self.land_count = 0
        self.add_basics()
        self.add_standard_non_basics()
        self.add_fetches()
        if 'Kindred' in ' '.join(self.themes):
            self.add_kindred_lands()
        
        if len(self.colors) >= 2:
            self.add_dual_lands()
        
        if len(self.colors) >= 3:
            pass
        
        self.add_misc_lands()
        
        rows_to_drop = []
        for index, row in self.land_df.iterrows():
            for land in self.land_cards:
                if land in row['name']:
                    rows_to_drop.append(index)
        self.land_df = self.land_df.drop(rows_to_drop)
        self.land_df.to_csv(f'{csv_directory}/test_lands.csv', index=False)
        
        # If over ideal land count, remove random basics until ideal land count
        while self.land_count > self.ideal_land_count:
            self.remove_basic()
        
        #if self.land_cards < self.ideal_land_count:
        #    pass
        basic_lands = ['Plains', 'Island', 'Swamp', 'Forest', 'Mountain']
        total_basics = 0
        for basic_land in basic_lands:
            num_basics = 0
            if basic_land in self.land_cards:
                while basic_land in self.land_cards:
                    num_basics += 1
                    self.land_cards.remove(basic_land)
                self.land_cards.append(f'{basic_land} x {num_basics}')
                total_basics += num_basics
        print(*self.land_cards, sep='\n')
        print(f'Total lands: {self.land_count}')
        print(total_basics)
    
    def add_basics(self):
        self.land_count = 0
        print(f'Adding {self.ideal_land_count - 5} basic lands.')
        for color in self.colors:
            if color == 'W':
                basic = 'Plains'
            elif color == 'U':
                basic = 'Island'
            elif color == 'B':
                basic = 'Swamp',
            elif color == 'R':
                basic = 'Mountain'
            elif color == 'G':
                basic = 'Forest'
            """if color =='':
                basic = 'Wastes'"""
            num_basics = self.ideal_land_count - 5
            for _ in range(num_basics // len(self.colors)):
                self.land_cards.append(basic)
                self.land_count += 1
    
    def add_standard_non_basics(self):
        # Add lands that are good in most any commander deck
        print('Adding "standard" non-basics')
        self.land_cards.append('Reliquary Tower')
        self.land_count += 1
        if 'Landfall' not in self.commander_tags:
            self.land_cards.append('Ash Barrens')
            self.land_count += 1
        if len(self.colors) > 1:
            # Adding command Tower
            self.land_cards.append('Command Tower')
            self.land_count += 1
            
            # Adding Exotic Orchard
            self.land_cards.append('Exotic Orchard')
            self.land_count += 1
            
        if len(self.colors) <= 2:
            self.land_cards.append('War Room')
            self.land_count += 1
        if self.commander_power >= 5:
            self.land_cards.append('Rogue\'s Passage')
            self.land_count += 1
        
    def add_fetches(self):
        # Determine how many fetches in total
        print('How many fetch lands would you like to include?\n'
              'For most decks you\'ll likely be good with 3 or 4, just enough to thin the deck and help ensure the color availability.\n'
              'If you\'re doing Landfall, more fetches would be recommended just to get as many Landfall triggers per turn.')
        question = [
            inquirer.Text(
                'fetch_prompt',
                default='5'
                )
            ]
        answer = inquirer.prompt(question)
        desired_fetches = int(answer['fetch_prompt'])
        chosen_fetches = []
        
        generic_fetches = ['Evolving Wilds', 'Terramorphic Expanse', 'Shire Terrace', 'Escape Tunnel', 'Promising Vein','Myriad Landscape', 'Fabled Passage', 'Terminal Moraine']
        fetches = generic_fetches
        
        # Adding in life fetches
        print('Would you like to include the pricier fetch-lands (i.e. Prismatic Vista or the Onslaught/Zendikar fetches)?')
        question = [
            inquirer.Confirm(
                            'yes',
                            )
                        ]
        answer = inquirer.prompt(question)
        choice = answer['yes']
        if choice:
            fetches.append('Prismatic Vista')
            if 'W' in self.colors:
                white_fetches = ['Flooded Strand', 'Windswept Heath', 'Marsh Flats', 'Arid Mesa'] 
                for fetch in white_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
                
            if 'U' in self.colors:
                blue_fetches = ['Flooded Strand', 'Polluted Delta', 'Scalding Tarn', 'Misty Rainforest']
                for fetch in blue_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
                
            if 'B' in self.colors:
                black_fetches = ['Polluted Delta', 'Bloodstained Mire', 'Marsh Flats', 'Verdant Catacombs']
                for fetch in black_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
            
            if 'R' in self.colors:
                red_fetches = ['Bloodstained Mire', 'Wooded Foothills', 'Scalding Tarn', 'Arid Mesa']
                for fetch in red_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
                    
            if 'G' in self.colors:
                green_fetches = ['Wooded Foothills', 'Windswept Heath', 'Verdant Catacombs', 'Misty Rainforest']
                for fetch in green_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
        
        # Adding in New Capenna Fetches
        print('Would you like to include the cheaper, New Capenna fetches?')
        question = [
            inquirer.Confirm(
                            'yes',
                            )
                        ]
        answer = inquirer.prompt(question)
        choice = answer['yes']
        if choice:
            if 'W' in self.colors:
                white_fetches = ['Brokers Hideout', 'Obscura Storefront', 'Cabaretti Courtyard']
                for fetch in white_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
            if 'U' in self.colors:
                blue_fetches = ['Brokers Hideout', 'Obscura Storefront', 'Maestros Theater']
                for fetch in blue_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
                
            if 'B' in self.colors:
                black_fetches = ['Obscura Storefront', 'Maestros Theater', 'Riveteers Overlook']
                for fetch in black_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
            
            if 'R' in self.colors:
                red_fetches = ['Maestros Theater', 'Riveteers Overlook', 'Cabaretti Courtyard']
                for fetch in red_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
                    
            if 'G' in self.colors:
                green_fetches = ['Brokers Hideout', 'Riveteers Overlook', 'Cabaretti Courtyard']
                for fetch in green_fetches:
                    if fetch not in fetches:
                        fetches.append(fetch)
        
        fetches_chosen = False
        # Randomly choose fetches up to the desired number
        while not fetches_chosen:
            while len(chosen_fetches) < desired_fetches + 3:
                fetch_choice = random.choice(fetches)
                if fetch_choice not in chosen_fetches:
                    chosen_fetches.append(fetch_choice)
        
            print('These are the fetch lands that have been found for you:')
            print(chosen_fetches)
            print('Do they look good for you?')
            question = [
                inquirer.Confirm(
                                'yes',
                                )
                            ]
            answer = inquirer.prompt(question)
            choice = answer['yes']
            if not choice:
                print('Reselecting fetches to use.')
                chosen_fetches = []
            
            else:
                fetches_to_add = []
                while len(fetches_to_add) < desired_fetches:
                    print(f'Please choose {desired_fetches} of them to add to your deck.')
                    question = [
                        inquirer.List('theme',
                                    choices=chosen_fetches,
                                    carousel=True)
                    ]
                    answer = inquirer.prompt(question)
                    choice = answer['theme']
                    fetches_to_add.append(choice)
                    chosen_fetches.remove(choice)
                fetches_chosen = True
                break
            break
        for fetch in fetches_to_add:
            if fetch not in self.land_cards:
                self.land_cards.append(fetch)
                self.land_count += 1
            
    def add_kindred_lands(self):
        print('Adding lands that care about the commander having a Kindred theme.')
        print('Adding general Kindred lands.')
        kindred_lands = ['Path of Ancestry']
        
        print('Would you like to include the pricier Kindred lands (i.e. Cavern of Souls and Three Tree City)?')
        question = [
            inquirer.Confirm(
                            'yes',
                            )
                        ]
        answer = inquirer.prompt(question)
        choice = answer['yes']
        if choice:
            kindred_lands.extend(['Three Tree City', 'Cavern of Souls'])

        for land in kindred_lands:
            if land not in self.land_cards:
                self.land_cards.append(land)
                self.land_count += 1
    
    def add_dual_lands(self):
        # Determine dual-color lands available 
        dual_options = []
        if ('W' in self.colors and 'U' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Plains Island' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('W' in self.colors and 'B' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Plains Swamp' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('U' in self.colors and 'B' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Island Swamp' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('G' in self.colors and 'B' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Forest Swamp' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('B' in self.colors and 'R' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Swamp Mountain' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('G' in self.colors and 'U' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Forest Island' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('R' in self.colors and 'G' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Mountain Forest' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('U' in self.colors and 'R' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Island Mountain' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('G' in self.colors and 'W' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Forest Plains' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        if ('R' in self.colors and 'W' in self.colors):
            for index, row in self.land_df.iterrows():
                if 'Land — Mountain Plains' == row['type']:
                    dual_options.append(row['name'])
                    self.land_df = self.land_df.drop(index)
        
        # Determine if using the dual-type lands
        print('Would you like to include dual-type lands (i.e. lands that count as both a Plains and a Swamp for example)?')
        question = [
            inquirer.Confirm(
                            'yes',
                            )
                        ]
        answer = inquirer.prompt(question)
        choice = answer['yes']
        
        
        # Add the Duals to a list
        while choice:
            # Include OG duals
            print('Would you like to include the OG dual lands (i.e. Tundra or Plateau)?')
            og_question = [
                inquirer.Confirm(
                    'no',
                )
            ]
            og_answer = inquirer.prompt(og_question)
            include_ogs = og_answer['no']
            og_duals = ['Tundra', 'Underground Sea', 'Badlands', 'Taiga', 'Savannah', 'Scrubland', 'Volcanic Island', 'Bayou', 'Plateau', 'Tropical Island']
            if not include_ogs:
                for land in og_duals:
                    if land in dual_options:
                        dual_options.remove(land)
            print('Here\'s all the dual-type lands in your commander\'s color identity:')
            print(*dual_options, sep='\n')
            print('\n')
            for land in dual_options:
                if land not in self.land_cards:
                    self.land_cards.append(land)
                    self.land_count += 1
            break
    
    def add_misc_lands(self):
        
        print(self.color_identity)
        rows_to_drop = []
        for index, row in self.land_df.iterrows():
            if row['colorIdentity'] not in self.color_identity_options:
                rows_to_drop.append(index)
                
        filtered_lands_df = self.land_df.drop(rows_to_drop)
        filtered_lands_df = filtered_lands_df.head(35)
        print(filtered_lands_df[['name']])
        
    
    def remove_basic(self):
        basic_lands = []
        for color in self.colors:
            if color == 'W':
                basic = 'Plains'
            elif color == 'U':
                basic = 'Island'
            elif color == 'B':
                basic = 'Swamp',
            elif color == 'R':
                basic = 'Mountain'
            elif color == 'G':
                basic = 'Forest'
            if basic not in basic_lands:
                basic_lands.append(basic)
                
        basic_land = random.choice(basic_lands)
        #print(basic_land)
        self.land_cards.remove(basic_land)
        self.land_count -= 1
        
    def add_creatures(self):
        # Begin the process to add creatures, the number added will depend on what the 
        # deck plan is, the commander, creature types, etc...
        print(f'Adding the creatures to deck, a baseline based on the ideal creature count of {self.ideal_creature_count} will be used.')

build_deck = DeckBuilder()
build_deck.determine_commander()
"""print(f'Commander: {build_deck.commander}')
print(f'Color Identity: {build_deck.color_identity}')
print(f'Commander Colors: {build_deck.colors}')
print(f'Commander Creature Types: {build_deck.creature_types}')
print(f'Commander Primary Theme: {build_deck.primary_theme}')
if not build_deck.secondary_theme:
    pass
else:    
    print(f'Commander Secondary Theme: {build_deck.secondary_theme}')
if not build_deck.tertiary_theme:
    pass
else:
    print(f'Commander Tertiary Theme: {build_deck.tertiary_theme}')"""
pprint.pprint(build_deck.commander_dict, sort_dicts = False)
#build_deck.determine_commander()
#build_deck.ideal_land_count = 35
#build_deck.add_lands()