"""Command-line interface for the MTG Python Deckbuilder application.

This module provides the main menu and user interaction functionality for the
MTG Python Deckbuilder. It handles menu display, user input processing, and
routing to different application features like setup, deck building, card info
lookup and CSV file tagging.
"""
from __future__ import annotations

# Standard library imports
import sys
import logging
import os
from pathlib import Path
from typing import NoReturn, Optional

# Third-party imports
import inquirer.prompt

# Local imports
import deck_builder
import setup
import tagger

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Logging configuration
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'main.log')
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO

# Create formatters and handlers
formatter = logging.Formatter(LOG_FORMAT)

# File handler
file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
file_handler.setFormatter(formatter)

# Stream handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Menu constants
MENU_SETUP = 'Setup'
MAIN_TAG = 'Tag CSV Files'
MENU_BUILD_DECK = 'Build a Deck'
MENU_QUIT = 'Quit'

MENU_CHOICES = [MENU_SETUP, MAIN_TAG, MENU_BUILD_DECK, MENU_QUIT]
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
        answer = inquirer.prompt(question)
        return answer['menu'] if answer else None
    except (KeyError, TypeError) as e:
        logger.error(f"Error getting menu choice: {e}")
        return None

def run_menu() -> NoReturn:
    """Main menu loop with improved error handling and logger.

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
    logger.info("Starting MTG Python Deckbuilder")
    Path('csv_files').mkdir(parents=True, exist_ok=True)
    Path('deck_files').mkdir(parents=True, exist_ok=True)
    Path('logs').mkdir(parents=True, exist_ok=True)

    while True:
        try:
            print('What would you like to do?')
            choice = get_menu_choice()

            if choice is None:
                logger.info("Menu operation cancelled")
                continue

            logger.info(f"User selected: {choice}")

            match choice:
                case 'Setup':
                    setup.setup()
                case 'Tag CSV Files':
                    tagger.run_tagging()
                case 'Build a Deck':
                    deck_builder.main()
                case 'Quit':
                    logger.info("Exiting application")
                    sys.exit(0)
                case _:
                    logger.warning(f"Invalid menu choice: {choice}")

        except Exception as e:
            logger.error(f"Unexpected error in main menu: {e}")

if __name__ == "__main__":
    run_menu()