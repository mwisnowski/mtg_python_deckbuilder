from __future__ import annotations

import inquirer.prompt # type: ignore
import sys

from pathlib import Path

import setup
import card_info

Path('csv_files').mkdir(parents=True, exist_ok=True)
Path('staples').mkdir(parents=True, exist_ok=True)

while True:
    print('What would you like to do?')
    choice = 'Menu'
    while choice == 'Menu':
        question = [
            inquirer.List('menu',
                          choices=['Setup', 'Build a Deck', 'Get Card Info', 'Quit'],
                          carousel=True)
        ]
        try:
            answer = inquirer.prompt(question)
            if answer is None:
                print("Operation cancelled. Returning to menu...")
                choice = 'Menu'
                continue
            choice = answer['menu']
        except (KeyError, TypeError):
            print("Invalid input. Please try again.")
            choice = 'Menu'

    # Run through initial setup
    while choice == 'Setup':
        setup.setup()
        choice = 'Menu'
        

    # Make a new deck
    while choice == 'Build a Deck':
        print('Deck building not yet implemented')
        choice = 'Menu'
        

    # Get a cards info
    while choice == 'Get Card Info':
        card_info.get_card_info()
        question  = [
            inquirer.Confirm('continue',
                             message='Would you like to look up another card?'
                             )
        ]
        try:
            answer = inquirer.prompt(question)
            if answer is None:
                print("Operation cancelled. Returning to menu...")
                choice = 'Menu'
                continue
            new_card = answer['continue']
            if new_card:
                choice = 'Get Card Info'  # Fixed == to = for assignment
        except (KeyError, TypeError):
            print("Invalid input. Returning to menu...")
            choice = 'Menu'

    # Quit
    while choice == 'Quit':
        sys.exit()
        