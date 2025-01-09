from __future__ import annotations

import inquirer.prompt # type: ignore
import sys
import logging
from pathlib import Path
from typing import NoReturn, Optional

import setup
import card_info

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('main.log', mode='w')
    ]
)

# Menu constants
MENU_SETUP = 'Setup'
MENU_BUILD_DECK = 'Build a Deck'
MENU_CARD_INFO = 'Get Card Info'
MENU_QUIT = 'Quit'

MENU_CHOICES = [MENU_SETUP, MENU_BUILD_DECK, MENU_CARD_INFO, MENU_QUIT]
def get_menu_choice() -> Optional[str]:
    """Display the main menu and get user choice.

    Returns:
        Optional[str]: The selected menu option or None if cancelled
    """
    question = [
        inquirer.List('menu',
                      choices=MENU_CHOICES,
                      carousel=True)
    ]
    try:
        answer = inquirer.prompt(question)
        return answer['menu'] if answer else None
    except (KeyError, TypeError) as e:
        logging.error(f"Error getting menu choice: {e}")
        return None

def handle_card_info() -> None:
    """Handle the card info menu option with proper error handling."""
    try:
        while True:
            card_info.get_card_info()
            question = [
                inquirer.Confirm('continue',
                                message='Would you like to look up another card?')
            ]
            try:
                answer = inquirer.prompt(question)
                if not answer or not answer['continue']:
                    break
            except (KeyError, TypeError) as e:
                logging.error(f"Error in card info continuation prompt: {e}")
                break
    except Exception as e:
        logging.error(f"Error in card info handling: {e}")

def run_menu() -> NoReturn:
    """Main menu loop with improved error handling and logging."""
    logging.info("Starting MTG Python Deckbuilder")
    Path('csv_files').mkdir(parents=True, exist_ok=True)

    while True:
        try:
            print('What would you like to do?')
            choice = get_menu_choice()

            if choice is None:
                logging.info("Menu operation cancelled")
                continue

            logging.info(f"User selected: {choice}")

            match choice:
                case 'Setup':
                    setup.setup()
                case 'Build a Deck':
                    logging.info("Deck building not yet implemented")
                    print('Deck building not yet implemented')
                case 'Get Card Info':
                    handle_card_info()
                case 'Quit':
                    logging.info("Exiting application")
                    sys.exit(0)
                case _:
                    logging.warning(f"Invalid menu choice: {choice}")

        except Exception as e:
            logging.error(f"Unexpected error in main menu: {e}")

if __name__ == "__main__":
    run_menu()