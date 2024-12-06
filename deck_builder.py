from __future__ import annotations

import inquirer.prompt # type: ignore
import pandas as pd # type: ignore
import pprint # type: ignore
import random

from fuzzywuzzy import fuzz, process, utils # type: ignore
from IPython.display import display

import settings

from setup import determine_legendary

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 5)

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
        self.info_tags = []
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
            try:
                df = pd.read_csv('csv_files/legendary_cards.csv')
            except FileNotFoundError:
                determine_legendary()
                df = pd.read_csv('csv_files/legendary_cards.csv')
            fuzzy_card_choice = process.extractOne(card_choice, df['name'], scorer=fuzz.ratio)
            fuzzy_card_choice = fuzzy_card_choice[0]
            filtered_df = df[df['name'] == fuzzy_card_choice]
            columns_to_keep = ['name', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'keywords', 'power', 'toughness', 'text']
            filtered_df = filtered_df[columns_to_keep]
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
                #print(self.commander)
            else:
                commander_chosen = False

        # Send commander info to setup commander, including extracting info on colors, color identity,
        # creature types, and other information, like keywords, abilities, etc...
        self.commander_setup()
                
    def commander_setup(self):
        # Load commander info into a dataframe
        df = self.commander_df
        self.commander_keywords = df.at[0, 'keywords']
        self.commander_power = int(df.at[0, 'power'])
        self.commander_toughness = int(df.at[0, 'toughness'])
        self.commander_mana_cost = df.at[0, 'manaCost']
        
        # Run the color setup
        self.set_color_identity(df)
        
        # Run the creature type setup
        self.set_creature_types(df)
        
        # Setup deck theme tags
        self.setup_deck_tags(df)
    
    def set_color_identity(self, df):
        # Set color identity
        self.color_identity = df.at[0, 'colorIdentity'].split(', ')
        # Set creature colors
        self.colors = df.at[0, 'colors'].split(', ')
    
    def set_creature_types(self, df):
        # Set creature types
        types = df.at[0, 'type']
        print(types)
        split_types = types.split()
        for type in split_types:
            if type not in settings.non_creature_types:
                self.creature_types.append(type)
                
    def setup_deck_tags(self, df):
        # Determine card tags, such as counters theme
        """keywords = df.at[0, 'keywords'].split()
        for keyword in keywords:
            settings.theme_tags.append(keyword.lower())
        print(settings.theme_tags)"""
        
        self.check_tags(df.at[0, 'text'], settings.theme_tags)
        #print(card_tags)
        
    def check_tags(self, string, word_list, threshold=80):
        card_tags = []
        for word in word_list:
            #print(word)
            if word == '+1/+1 counter' or word == '-1/-1 counter':
                threshold += 20
            if fuzz.partial_ratio(string.lower(), word.lower()) >= threshold:
                card_tags.append(word)
                #return True
        #return False
        self.commander_tags = card_tags
        
    def determine_ideals(self):
        # "Free" slots that can be used for anything that isn't the ideals
        self.free_slots = 99
        
        # Determine ideal land count
        print('How many lands would you like to include?\n'
              'Before ramp is taken into account, 38-40 would be "normal" for a deck.\n'
              'Broadly speaking, for every mana produced per 3 mana spent on ramp could reduce land count by 1.\n'
              'If you\'re playing landfall, probably consider 40 as baseline before ramp.')
        question = [
            inquirer.Text(
                'land_prompt',
                message=''
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
                message=''
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
                message=''
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
                message=''
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
                message=''
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
                message=''
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
                message=''
                )
            ]
        answer = inquirer.prompt(question)
        self.ideal_protection = int(answer['protection_prompt'])
        self.free_slots -= self.ideal_protection
        
        print(f'Free slots that aren\'t part of the ideals: {self.free_slots}')
        print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')
    
    def add_lands(self):
        # Begin the process to add lands, the number will depend on ideal land count, ramp,
        # and if any utility lands may be helpful.
        # By default, ({self.ideal_land_count} - 5) basic lands will be added, distributed
        # across the commander color identity. These will be removed for utility lands, 
        # multi-color producing lands, fetches, and any MDFCs added later
        print(f'Adding {self.ideal_land_count} - 5 basic lands.')
        for color in self.color_identity:
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
            for _ in range(num_basics // len(self.color_identity)):
                self.land_cards.append(basic)
        #print(self.land_cards)
        
        # Add lands that are good in most any commander deck
        print('Adding \'standard\' non-basics')
        self.land_cards.append('Reliquary Tower')
        if 'landfall' not in self.commander_tags:
            self.land_cards.append('Ash Barrens')
        if len(self.color_identity) > 1:
            self.land_cards.append('Command Tower')
            self.land_cards.append('Exotic Orchard')
            self.land_cards.append('Evolving Wilds')
        if len(self.color_identity) <= 2:
            self.land_cards.append('War Room')
        if self.commander_power >= 5:
            self.land_cards.append('Rogue\'s Passage')
        
        # If over ideal land count, remove random basics until ideal land count
        while len(self.land_cards) > self.ideal_land_count:
                self.remove_basic()
        
        #if self.land_cards < self.ideal_land_count:
        #    pass
        print(*self.land_cards, sep='\n')
        print(len(self.land_cards))
            
    def remove_basic(self):
        basic_lands = []
        for color in self.color_identity:
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
        
    def add_creatures(self):
        # Begin the process to add creatures, the number added will depend on what the 
        # deck plan is, the commander, creature types, etc...
        print(f'Adding the creatures to deck, a baseline based on the ideal creature count of {self.ideal_creature_count} will be used.')

build_deck = DeckBuilder()
"""build_deck.determine_commander()
print(f'Commander: {build_deck.commander}')
print(f'Color Identity: {build_deck.color_identity}')
print(f'Commander Colors: {build_deck.colors}')
print(f'Commander Creature Types: {build_deck.creature_types}')
print(f'Commander tags: {build_deck.commander_tags}')"""
build_deck.determine_commander()
build_deck.ideal_land_count = 35
build_deck.add_lands()