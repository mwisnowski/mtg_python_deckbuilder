"""MTG Python Deckbuilder setup module.

This module provides the main setup functionality for the MTG Python Deckbuilder
application. It handles initial setup tasks such as downloading card data,
creating color-filtered card lists, and generating commander-eligible card lists.

Key Features:
    - Initial setup and configuration
    - Card data download and processing
    - Color-based card filtering
    - Commander card list generation
    - CSV file management and validation

The module works in conjunction with setup_utils.py for utility functions and
exceptions.py for error handling.
"""

from __future__ import annotations

# Standard library imports
from enum import Enum
import os
from typing import List, Dict, Any

# Third-party imports (optional)
try:
    import inquirer  # type: ignore
except Exception:
    inquirer = None  # Fallback to simple input-based menu when unavailable
import pandas as pd

# Local imports
import logging_util
from settings import CSV_DIRECTORY
from .setup_constants import BANNED_CARDS, SETUP_COLORS, COLOR_ABRV, MTGJSON_API_URL
from .setup_utils import (
    download_cards_csv,
    filter_dataframe,
    process_legendary_cards,
    check_csv_exists,
    save_color_filtered_csvs,
)
from exceptions import (
    CSVFileNotFoundError,
    CommanderValidationError,
    MTGJSONDownloadError
)

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# Create CSV directory if it doesn't exist
if not os.path.exists(CSV_DIRECTORY):
    os.makedirs(CSV_DIRECTORY)

## Note: using shared check_csv_exists from setup_utils to avoid duplication

def initial_setup() -> None:
    """Perform initial setup by downloading card data and creating filtered CSV files.
    
    Downloads the latest card data from MTGJSON if needed, creates color-filtered CSV files,
    and generates commander-eligible cards list. Uses utility functions from setup_utils.py
    for file operations and data processing.
    
    Raises:
        CSVFileNotFoundError: If required CSV files cannot be found
        MTGJSONDownloadError: If card data download fails
        DataFrameProcessingError: If data processing fails
        ColorFilterError: If color filtering fails
    """
    logger.info('Checking for cards.csv file')
    
    try:
        cards_file = f'{CSV_DIRECTORY}/cards.csv'
        try:
            with open(cards_file, 'r', encoding='utf-8'):
                logger.info('cards.csv exists')
        except FileNotFoundError:
            logger.info('cards.csv not found, downloading from mtgjson')
            download_cards_csv(MTGJSON_API_URL, cards_file)
        
        df = pd.read_csv(cards_file, low_memory=False)
        
        logger.info('Checking for color identity sorted files')
        # Generate color-identity filtered CSVs in one pass
        save_color_filtered_csvs(df, CSV_DIRECTORY)
        
        # Generate commander list
        determine_commanders()

    except Exception as e:
        logger.error(f'Error during initial setup: {str(e)}')
        raise

## Removed local filter_by_color in favor of setup_utils.save_color_filtered_csvs

def determine_commanders() -> None:
    """Generate commander_cards.csv containing all cards eligible to be commanders.
    
    This function processes the card database to identify and validate commander-eligible cards,
    applying comprehensive validation steps and filtering criteria.
    
    Raises:
        CSVFileNotFoundError: If cards.csv is missing and cannot be downloaded
        MTGJSONDownloadError: If downloading cards data fails
        CommanderValidationError: If commander validation fails
        DataFrameProcessingError: If data processing operations fail
    """
    logger.info('Starting commander card generation process')
    
    try:
        # Check for cards.csv with progress tracking
        cards_file = f'{CSV_DIRECTORY}/cards.csv'
        if not check_csv_exists(cards_file):
            logger.info('cards.csv not found, initiating download')
            download_cards_csv(MTGJSON_API_URL, cards_file)
        else:
            logger.info('cards.csv found, proceeding with processing')
        
        # Load and process cards data
        logger.info('Loading card data from CSV')
        df = pd.read_csv(cards_file, low_memory=False)
        
        # Process legendary cards with validation
        logger.info('Processing and validating legendary cards')
        try:
            filtered_df = process_legendary_cards(df)
        except CommanderValidationError as e:
            logger.error(f'Commander validation failed: {str(e)}')
            raise
        
        # Apply standard filters
        logger.info('Applying standard card filters')
        filtered_df = filter_dataframe(filtered_df, BANNED_CARDS)
        
        # Save commander cards
        logger.info('Saving validated commander cards')
        filtered_df.to_csv(f'{CSV_DIRECTORY}/commander_cards.csv', index=False)
        
        logger.info('Commander card generation completed successfully')
        
    except (CSVFileNotFoundError, MTGJSONDownloadError) as e:
        logger.error(f'File operation error: {str(e)}')
        raise
    except CommanderValidationError as e:
        logger.error(f'Commander validation error: {str(e)}')
        raise
    except Exception as e:
        logger.error(f'Unexpected error during commander generation: {str(e)}')
        raise
    
def regenerate_csvs_all() -> None:
    """Regenerate all color-filtered CSV files from latest card data.
    
    Downloads fresh card data and recreates all color-filtered CSV files.
    Useful for updating the card database when new sets are released.
    
    Raises:
        MTGJSONDownloadError: If card data download fails
        DataFrameProcessingError: If data processing fails
        ColorFilterError: If color filtering fails
    """
    try:
        logger.info('Downloading latest card data from MTGJSON')
        download_cards_csv(MTGJSON_API_URL, f'{CSV_DIRECTORY}/cards.csv')
        
        logger.info('Loading and processing card data')
        df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)
        
        logger.info('Regenerating color identity sorted files')
        save_color_filtered_csvs(df, CSV_DIRECTORY)
            
        logger.info('Regenerating commander cards')
        determine_commanders()
        
        logger.info('Card database regeneration complete')
        
    except Exception as e:
        logger.error(f'Failed to regenerate card database: {str(e)}')
        raise
    # Once files are regenerated, create a new legendary list (already executed in try)

def regenerate_csv_by_color(color: str) -> None:
    """Regenerate CSV file for a specific color identity.
    
    Args:
        color: Color name to regenerate CSV for (e.g. 'white', 'blue')
        
    Raises:
        ValueError: If color is not valid
        MTGJSONDownloadError: If card data download fails
        DataFrameProcessingError: If data processing fails
        ColorFilterError: If color filtering fails
    """
    try:
        if color not in SETUP_COLORS:
            raise ValueError(f'Invalid color: {color}')

        color_abv = COLOR_ABRV[SETUP_COLORS.index(color)]

        logger.info(f'Downloading latest card data for {color} cards')
        download_cards_csv(MTGJSON_API_URL, f'{CSV_DIRECTORY}/cards.csv')

        logger.info('Loading and processing card data')
        df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)

        logger.info(f'Regenerating {color} cards CSV')
        # Use shared utilities to base-filter once then slice color, honoring bans
        base_df = filter_dataframe(df, BANNED_CARDS)
        base_df[base_df['colorIdentity'] == color_abv].to_csv(
            f'{CSV_DIRECTORY}/{color}_cards.csv', index=False
        )

        logger.info(f'Successfully regenerated {color} cards database')

    except Exception as e:
        logger.error(f'Failed to regenerate {color} cards: {str(e)}')
        raise

class SetupOption(Enum):
    """Enum for setup menu options."""
    INITIAL_SETUP = 'Initial Setup'
    REGENERATE_CSV = 'Regenerate CSV Files'
    BACK = 'Back'

def _display_setup_menu() -> SetupOption:
    """Display the setup menu and return the selected option.
    
    Returns:
        SetupOption: The selected menu option
    """
    if inquirer is not None:
        question: List[Dict[str, Any]] = [
            inquirer.List(
                'menu',
                choices=[option.value for option in SetupOption],
                carousel=True)]
        answer = inquirer.prompt(question)
        return SetupOption(answer['menu'])

    # Simple fallback when inquirer isn't installed (e.g., headless/container)
    options = list(SetupOption)
    print("\nSetup Menu:")
    for idx, opt in enumerate(options, start=1):
        print(f"  {idx}) {opt.value}")
    while True:
        try:
            sel = input("Select an option [1]: ").strip() or "1"
            i = int(sel)
            if 1 <= i <= len(options):
                return options[i - 1]
        except KeyboardInterrupt:
            print("")
            return SetupOption.BACK
        except Exception:
            pass
        print("Invalid selection. Please try again.")

def setup() -> bool:
    """Run the setup process for the MTG Python Deckbuilder.
    
    This function provides a menu-driven interface to:
    1. Perform initial setup by downloading and processing card data
    2. Regenerate CSV files with updated card data
    3. Perform all tagging processes on the color-sorted csv files
    
    The function handles errors gracefully and provides feedback through logging.
    
    Returns:
        bool: True if setup completed successfully, False otherwise
    """
    try:
        print('Which setup operation would you like to perform?\n'
              'If this is your first time setting up, do the initial setup.\n'
              'If you\'ve done the basic setup before, you can regenerate the CSV files\n')
        
        choice = _display_setup_menu()
        
        if choice == SetupOption.INITIAL_SETUP:
            logger.info('Starting initial setup')
            initial_setup()
            logger.info('Initial setup completed successfully')
            return True
            
        elif choice == SetupOption.REGENERATE_CSV:
            logger.info('Starting CSV regeneration')
            regenerate_csvs_all()
            logger.info('CSV regeneration completed successfully')
            return True
            
        elif choice == SetupOption.BACK:
            logger.info('Setup cancelled by user')
            return False
            
    except Exception as e:
        logger.error(f'Error during setup: {e}')
        raise
    
    return False
