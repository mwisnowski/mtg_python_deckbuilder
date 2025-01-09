from __future__ import annotations

from enum import Enum
import pandas as pd # type: ignore
import inquirer # type: ignore
import logging
from tqdm import tqdm

from settings import CSV_DIRECTORY, COLORS, COLOR_ABBREVIATIONS
import setup_utility

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('setup.log', mode='w')
    ]
)

class SetupOption(Enum):
    """Enum for setup menu options."""
    INITIAL_SETUP = 'Initial Setup'
    REGENERATE_CSV = 'Regenerate CSV Files'
    BACK = 'Back'

def initial_setup(force_update: bool = False) -> bool:
    """Perform initial setup by downloading and processing card data.
    
    This function handles the initial setup process by:
    1. Downloading the latest cards.csv if needed
    2. Processing the card data into color-specific files
    3. Generating commander-specific files
    
    Args:
        force_update: If True, update files regardless of age
    
    Returns:
        bool: True if setup completed successfully
    
    Raises:
        Exception: If setup fails
    """
    try:
        logging.info('Starting initial setup process')
        
        # Download cards.csv if needed or forced
        if force_update or setup_utility.file_needs_update(f'{CSV_DIRECTORY}/cards.csv'):
            setup_utility.download_cards_csv()
        
        # Load and process cards DataFrame
        logging.info('Loading and processing cards data')
        df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)
        df = setup_utility.process_card_dataframe(df)
        
        # Validate DataFrame structure
        setup_utility.validate_card_dataframe(df)
        
        # Generate color-specific files
        logging.info('Generating color-specific files')
        for i in tqdm(range(min(len(COLORS), len(COLOR_ABBREVIATIONS))), desc='Processing colors'):
            color_file = f'{CSV_DIRECTORY}/{COLORS[i]}_cards.csv'
            if force_update or setup_utility.file_needs_update(color_file):
                logging.info(f'Processing {COLORS[i]} cards')
                setup_utility.filter_card_dataframe(
                    df,
                    'colorIdentity',
                    COLOR_ABBREVIATIONS[i],
                    color_file
                )
        
        # Generate commander file
        logging.info('Generating commander data')
        determine_commanders()
        
        logging.info('Initial setup completed successfully')
        return True
        
    except Exception as e:
        logging.error(f'Error during initial setup: {e}')
        raise

def regenerate_csvs_all() -> None:
    """
    Pull the original cards.csv file and remake the {color}_cards.csv files.
    This is useful if a new set has come out to ensure the databases are up-to-date.
    
    Uses utility functions from setup_utility to handle DataFrame operations and filtering.
    """
    try:
        # Download latest cards.csv
        setup_utility.download_cards_csv()
        
        # Load and process cards DataFrame
        df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)
        df = setup_utility.process_card_dataframe(df)
        
        # Filter banned cards and illegal types
        df = setup_utility.filter_banned_cards(df)
        df = setup_utility.filter_card_types(df)
        
        # Generate color identity sorted files
        logging.info('Regenerating color identity sorted files.')
        
        for i in range(min(len(COLORS), len(COLOR_ABBREVIATIONS))):
            logging.info(f'Regenerating {COLORS[i]}_cards.csv')
            filter_by_color(df, 'colorIdentity', COLOR_ABBREVIATIONS[i], f'{CSV_DIRECTORY}/{COLORS[i]}_cards.csv')
            logging.info(f'Generated {COLORS[i]}_cards.csv')
        
        # Regenerate commander list
        determine_commanders()
        logging.info('CSV regeneration completed successfully')
        
    except Exception as e:
        logging.error(f'Error regenerating CSVs: {e}')
        raise

def regenerate_csv_by_color(color: str) -> None:
    """
    Regenerate a specific color's card CSV file with the latest data.
    
    Args:
        color: The color to regenerate (must be in the COLORS list)
    
    Raises:
        ValueError: If color is not in the valid COLORS list
        Exception: If CSV regeneration fails
    """
    # Validate color input
    if color not in COLORS:
        raise ValueError(f"Invalid color: {color}. Must be one of {COLORS}")
    
    try:
        # Get corresponding color abbreviation
        COLOR_ABBREVIATIONS_index = COLORS.index(color)
        color_abv = COLOR_ABBREVIATIONS[COLOR_ABBREVIATIONS_index]
        
        # Download latest cards.csv
        logging.info(f"Regenerating {color}_cards.csv")
        setup_utility.download_cards_csv()
        
        # Load and process cards DataFrame
        df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)
        
        # Ensure 'availability' column is preserved
        required_columns = ['name', 'faceName', 'edhrecRank', 'colorIdentity', 'COLORS', 
                           'manaCost', 'manaValue', 'type', 'layout', 'text', 'power', 
                           'toughness', 'keywords', 'side', 'availability', 'promoTypes', 
                           'securityStamp']
        
        # Process DataFrame while preserving required columns
        df = setup_utility.process_card_dataframe(df[required_columns])
        # Filter banned cards and illegal types
        df = setup_utility.filter_banned_cards(df)
        df = setup_utility.filter_card_types(df)
        
        # Filter paper-only cards
        df = df[df['availability'].str.contains('paper')]
        
        # Filter and save color-specific cards
        setup_utility.filter_card_dataframe(
            df,
            'colorIdentity',
            color_abv,
            f'{CSV_DIRECTORY}/{color}_cards.csv'
        )
        
        logging.info(f"Successfully regenerated {color}_cards.csv")
        
    except Exception as e:
        logging.error(f"Error regenerating {color}_cards.csv: {e}")
        raise

def filter_by_color(df: pd.DataFrame, column_name: str, value: str, new_csv_name: str) -> None:
    """
    Filter cards by color identity and save to a CSV file.
    
    This function processes a DataFrame of cards, filtering by the specified color identity
    and saving the results to a CSV file. It handles common operations like removing duplicates,
    filtering banned cards, and ensuring only paper cards are included.
    
    Args:
        df: DataFrame containing card data
        column_name: Column to filter on (typically 'colorIdentity')
        value: Color identity value to filter for
        new_csv_name: Path where the filtered CSV should be saved
    """
    try:
        logging.info(f"Filtering cards for {column_name}={value}")
        
        # Process DataFrame with common operations
        df = setup_utility.process_card_dataframe(df)
        
        # Apply filters
        df = setup_utility.filter_banned_cards(df)
        df = setup_utility.filter_card_types(df)
        
        # Filter and save using utility function
        setup_utility.filter_card_dataframe(
            df,
            column_name,
            value,
            new_csv_name
        )
        
        logging.info(f"Successfully created {new_csv_name}")
        
    except Exception as e:
        logging.error(f"Error filtering cards by color: {e}")
        raise

def determine_commanders(force_update: bool = False) -> None:
    """Generate commander_cards.csv containing all cards eligible to be commanders.
    
    Uses utility functions to handle file operations, DataFrame processing,
    and commander-specific filtering logic.
    
    Args:
        force_update: If True, update files regardless of age
    
    Raises:
        Exception: If CSV generation fails
    """
    try:
        logging.info('Generating commander_cards.csv')
        
        commander_file = f'{CSV_DIRECTORY}/commander_cards.csv'
        
        # Check if update is needed
        if force_update or setup_utility.file_needs_update(commander_file):
            logging.info('Updating commander cards data')
            
            # Download and load cards.csv
            setup_utility.download_cards_csv()
            df = pd.read_csv(f'{CSV_DIRECTORY}/cards.csv', low_memory=False)
            
            # Process DataFrame with commander-specific columns
            df = setup_utility.process_card_dataframe(
                df,
                include_commander_cols=True
            )
            
            # Apply commander-specific filtering
            filtered_df = setup_utility.filter_commander_cards(df)
            
            # Save filtered DataFrame
            filtered_df.to_csv(commander_file, index=False)
            
            logging.info('Successfully generated commander_cards.csv')
        else:
            logging.info('Commander cards data is up to date')
        
    except Exception as e:
        logging.error(f'Error generating commander_cards.csv: {e}')
        raise

def _display_setup_menu() -> SetupOption:
    """Display the setup menu and return the selected option.
    
    Returns:
        SetupOption: The selected menu option
    """
    question = [
        inquirer.List('menu',
                      choices=[option.value for option in SetupOption],
                      carousel=True)
    ]
    answer = inquirer.prompt(question)
    return SetupOption(answer['menu'])

def setup() -> bool:
    """Run the setup process for the MTG Python Deckbuilder.
    
    This function provides a menu-driven interface to:
    1. Perform initial setup by downloading and processing card data
    2. Regenerate CSV files with updated card data
    
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
            logging.info('Starting initial setup')
            initial_setup()
            logging.info('Initial setup completed successfully')
            return True
            
        elif choice == SetupOption.REGENERATE_CSV:
            logging.info('Starting CSV regeneration')
            regenerate_csvs_all()
            logging.info('CSV regeneration completed successfully')
            return True
            
        elif choice == SetupOption.BACK:
            logging.info('Setup cancelled by user')
            return False
            
    except Exception as e:
        logging.error(f'Error during setup: {e}')
        raise
    
    return False