from __future__ import annotations

#import os
import inquirer.prompt # type: ignore
import pandas as pd # type: ignore
import requests # type: ignore
#import scrython # type: ignore
import sys

from pathlib import Path

import setup
import card_info

Path('csv_files').mkdir(parents=True, exist_ok=True)
Path('staples').mkdir(parents=True, exist_ok=True)

while True:
    choice = 'Menu'
    while choice == 'Menu':
        question = [
            inquirer.List('menu',
                          message='What would you like to do?',
                          choices=['Initial Setup', 'Regenerate Card CSVs', 'Setup Staples', 'Build a Deck', 'Get Card Info', 'Quit'],
                          carousel=True)
        ]
        answer = inquirer.prompt(question)
        choice = answer['menu']
    
    # Run through initial setup
    while choice == 'Initial Setup':
        setup.initial_setup()
        choice = 'Menu'
        break
    
    # Run through csv regeneration
    while choice == 'Regenerate Card CSVs':
        setup.regenerate_csvs()
        choice = 'Menu'
        break
    
    # Setup staples
    while choice == 'Setup Staples':
        setup.generate_staple_lists()
        choice = 'Menu'
        break
    
    # Make a new deck
    while choice == 'Build a Deck':
        print('Deck building not yet implemented')
        choice = 'Menu'
        break
    
    # Get a cards info
    while choice == 'Get Card Info':
        card_info.get_card_info()
        question  = [
            inquirer.Confirm('continue',
                             message='Would you like to look up another card?'
                             )
            ]
        answer = inquirer.prompt(question) 
        new_card = answer['continue']
        if new_card:
            choice == 'Get Card Info'
        else:
            choice = 'Menu'
            break
    
    # Quit
    while choice == 'Quit':
        sys.exit()