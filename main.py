from __future__ import annotations

# Standard library imports
import sys
import logging
from pathlib import Path
from typing import NoReturn, Optional

# Third-party imports
import inquirer.prompt # type: ignore

# Local imports
import setup
import card_info
import tagger

"""Command-line interface for the MTG Python Deckbuilder application.

This module provides the main menu and user interaction functionality for the
MTG Python Deckbuilder. It handles menu display, user input processing, and
routing to different application features like setup, deck building, card info
lookup and CSV file tagging.
"""
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
MAIN_TAG = 'Tag CSV Files'
MENU_QUIT = 'Quit'

MENU_CHOICES = [MENU_SETUP, MENU_BUILD_DECK, MENU_CARD_INFO, MAIN_TAG, MENU_QUIT]
def get_menu_choice() -> Optional[str]:
    """Display the main menu and get user choice.

    Presents a menu of options to the user using inquirer and returns their selection.
    Handles potential errors from inquirer gracefully.
    
    Returns:
        Optional[str]: The selected menu option or None if cancelled/error occurs

    Example:
        >>> choice = get_menu_choice()
        >>> if choice == MENU_SETUP:
        ...     setup.setup()
    """
    question = [
        inquirer.List('menu',
                      choices=MENU_CHOICES,
                      carousel=True)
    ]
    try:
        answer = inquirer.prompt(question) # type: ignore
        return answer['menu'] if answer else None
    except (KeyError, TypeError) as e:
        logging.error(f"Error getting menu choice: {e}")
        return None
def handle_card_info() -> None:
    """Handle the card info menu option with proper error handling.

    Provides an interface for looking up card information repeatedly until the user
    chooses to stop. Handles potential errors from card info lookup and user input.

    Returns:
        None

    Example:
        >>> handle_card_info()
        Enter card name: Lightning Bolt
        [Card info displayed]
        Would you like to look up another card? [y/N]: n
    """
    try:
        while True:
            card_info.get_card_info()
            question = [
                inquirer.Confirm('continue',
                                message='Would you like to look up another card?')
            ]
            try:
                answer = inquirer.prompt(question) # type: ignore
                if not answer or not answer['continue']:
                    break
            except (KeyError, TypeError) as e:
                logging.error(f"Error in card info continuation prompt: {e}")
                break
    except Exception as e:
        logging.error(f"Error in card info handling: {e}")
def run_menu() -> NoReturn:
    """Main menu loop with improved error handling and logging.

    Provides the main application loop that displays the menu and handles user selections.
    Creates required directories, processes menu choices, and handles errors gracefully.
    Never returns normally - exits via sys.exit().

    Returns:
        NoReturn: Function never returns normally

    Raises:
        SystemExit: When user selects Quit option

    Example:
        >>> run_menu()
        What would you like to do?
        1. Setup
        2. Build a Deck
        3. Get Card Info
        4. Tag CSV Files
        5. Quit
    """
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
                    tagger.run_tagging()
                case 'Build a Deck':
                    logging.info("Deck building not yet implemented")
                    print('Deck building not yet implemented')
                case 'Get Card Info':
                    handle_card_info()
                case 'Tag CSV Files':
                    tagger.run_tagging()
                case 'Quit':
                    logging.info("Exiting application")
                    sys.exit(0)
                case _:
                    logging.warning(f"Invalid menu choice: {choice}")

        except Exception as e:
            logging.error(f"Unexpected error in main menu: {e}")
if __name__ == "__main__":
    run_menu()