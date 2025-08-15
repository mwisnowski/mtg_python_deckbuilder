from __future__ import annotations

import math
import numpy as np
import os
import random
import time
from functools import lru_cache
from typing import Dict, List, Optional, Union

import inquirer.prompt
import keyboard
import pandas as pd
import pprint
from fuzzywuzzy import process
from tqdm import tqdm

from settings import CSV_DIRECTORY, MULTIPLE_COPY_CARDS
from .builder_constants import (
    BASIC_LANDS, CARD_TYPES, DEFAULT_NON_BASIC_LAND_SLOTS,
    COMMANDER_CSV_PATH, FUZZY_MATCH_THRESHOLD, MAX_FUZZY_CHOICES, FETCH_LAND_DEFAULT_COUNT,
    COMMANDER_POWER_DEFAULT, COMMANDER_TOUGHNESS_DEFAULT, COMMANDER_MANA_COST_DEFAULT,
    COMMANDER_MANA_VALUE_DEFAULT, COMMANDER_TYPE_DEFAULT, COMMANDER_TEXT_DEFAULT, 
    THEME_PRIORITY_BONUS, THEME_POOL_SIZE_MULTIPLIER, DECK_DIRECTORY,
    COMMANDER_COLOR_IDENTITY_DEFAULT, COMMANDER_COLORS_DEFAULT, COMMANDER_TAGS_DEFAULT, 
    COMMANDER_THEMES_DEFAULT, COMMANDER_CREATURE_TYPES_DEFAULT, DUAL_LAND_TYPE_MAP,
    CSV_READ_TIMEOUT, CSV_PROCESSING_BATCH_SIZE, CSV_VALIDATION_RULES, CSV_REQUIRED_COLUMNS,
    STAPLE_LAND_CONDITIONS, TRIPLE_LAND_TYPE_MAP, MISC_LAND_MAX_COUNT, MISC_LAND_MIN_COUNT,
    MISC_LAND_POOL_SIZE, LAND_REMOVAL_MAX_ATTEMPTS, PROTECTED_LANDS,
    MANA_COLORS, MANA_PIP_PATTERNS, THEME_WEIGHT_MULTIPLIER
)
from . import builder_utils
from file_setup import setup_utils
from input_handler import InputHandler
from exceptions import (
    BasicLandCountError,
    BasicLandError,
    CommanderMoveError,
    CardTypeCountError,
    CommanderColorError,
    CommanderSelectionError, 
    CommanderValidationError,
    CSVError,
    CSVReadError,
    CSVTimeoutError,
    CSVValidationError,
    DataFrameValidationError,
    DuplicateCardError,
    DeckBuilderError,
    EmptyDataFrameError,
    FetchLandSelectionError,
    FetchLandValidationError,
    IdealDeterminationError,
    LandRemovalError,
    LibraryOrganizationError,
    LibrarySortError,
    PriceAPIError,
    PriceConfigurationError,
    PriceLimitError, 
    PriceTimeoutError,
    PriceValidationError,
    ThemeSelectionError,
    ThemeWeightError,
    StapleLandError,
    ManaPipError,
    ThemeTagError,
    ThemeWeightingError,
    ThemePoolError
)
from type_definitions import (
    CommanderDict,
    CardLibraryDF,
    CommanderDF,
    LandDF,
    ArtifactDF,
    CreatureDF,
    NonCreatureDF,
    PlaneswalkerDF,
    NonPlaneswalkerDF)

import logging_util

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# Try to import scrython and price_checker
try:
    import scrython
    from price_check import PriceChecker
    use_scrython = True
except ImportError:
    scrython = None
    PriceChecker = None
    use_scrython = False
    logger.warning("Scrython is not installed. Price checking features will be unavailable."
                    )

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 50)

def new_line(num_lines: int = 1) -> None:
    """Print specified number of newlines for formatting output.

    Args:
        num_lines (int): Number of newlines to print. Defaults to 1.

    Returns:
        None
    """
    if num_lines < 0:
        raise ValueError("Number of lines cannot be negative")
    print('\n' * num_lines)

class DeckBuilder:

    def __init__(self) -> None:
        """Initialize DeckBuilder with empty dataframes and default attributes."""
        # Initialize dataframes with type hints
        self.card_library: CardLibraryDF = pd.DataFrame({
            'Card Name': pd.Series(dtype='str'),
            'Card Type': pd.Series(dtype='str'), 
            'Mana Cost': pd.Series(dtype='str'),
            'Mana Value': pd.Series(dtype='int'),
            'Creature Types': pd.Series(dtype='object'),
            'Themes': pd.Series(dtype='object'),
            'Commander': pd.Series(dtype='bool'),
        })
        
        # Initialize component dataframes
        self.commander_df: CommanderDF = pd.DataFrame()
        self.land_df: LandDF = pd.DataFrame()
        self.artifact_df: ArtifactDF = pd.DataFrame()
        self.creature_df: CreatureDF = pd.DataFrame()
        self.noncreature_df: NonCreatureDF = pd.DataFrame()
        self.nonplaneswalker_df: NonPlaneswalkerDF = pd.DataFrame()
        # Initialize other attributes with type hints
        self.commander_info: Dict = {}
        self.max_card_price: Optional[float] = None
        self.commander_dict: CommanderDict = {}
        self.commander: str = ''
        self.commander_type: str = ''
        self.commander_text: str = ''
        self.commander_power: int = 0
        self.commander_toughness: int = 0
        self.commander_mana_cost: str = ''
        self.commander_mana_value: int = 0
        self.color_identity: Union[str, List[str]] = ''
        self.color_identity_full: str = ''
        self.colors: List[str] = []
        self.creature_types: str = ''
        self.commander_tags: List[str] = []
        self.themes: List[str] = []
        
        # Initialize handlers
        self.price_checker = PriceChecker() if PriceChecker else None
        self.input_handler = InputHandler()
    
    def pause_with_message(self, message: str = "Press Enter to continue...") -> None:
        """Display a message and wait for user input.
        
        Args:
            message: Message to display before pausing
        """
        """Helper function to pause execution with a message."""
        print(f"\n{message}")
        input()
    
    # Determine and Validate commander
    def determine_commander(self) -> None:
        """Main orchestrator method for commander selection and initialization process.
        
        This method coordinates the commander selection workflow by:
        1. Loading commander data
        2. Facilitating commander selection
        3. Confirming the selection
        4. Initializing commander attributes
        
        Raises:
            CommanderLoadError: If commander data cannot be loaded
            CommanderSelectionError: If commander selection fails
            CommanderValidationError: If commander data is invalid
        """
        logger.info("Starting commander selection process")
        
        try:
            # Load commander data using builder_utils
            df = builder_utils.load_commander_data()
            logger.debug("Commander data loaded successfully")
            
            # Select commander
            commander_name = self._select_commander(df)
            logger.info(f"Commander selected: {commander_name}")
            
            # Confirm selection
            commander_data = self._confirm_commander(df, commander_name)
            logger.info("Commander selection confirmed")
            
            # Initialize commander
            self._initialize_commander(commander_data)
            logger.info("Commander initialization complete")
            
        except DeckBuilderError as e:
            logger.error(f"Commander selection failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in commander selection: {e}")
            raise DeckBuilderError(f"Commander selection failed: {str(e)}")

    def _select_commander(self, df: pd.DataFrame) -> str:
        """Handle the commander selection process including fuzzy matching.
        
        Args:
            df: DataFrame containing commander data
            
        Returns:
            Selected commander name
            
        Raises:
            CommanderSelectionError: If commander selection fails
        """
        while True:
            try:
                card_choice = self.input_handler.questionnaire(
                    'Text',
                    'Enter a card name to be your commander'
                )
                
                # Use builder_utils for fuzzy matching
                match, choices, exact_match = builder_utils.process_fuzzy_matches(card_choice, df)
                
                if exact_match:
                    return match
                
                # Handle multiple matches
                choices.append(('Neither', 0))
                logger.info("Multiple commander matches found")
                
                choice = self.input_handler.questionnaire(
                    'Choice',
                    'Multiple matches found. Please select:',
                    choices_list=[name for name, _ in choices]
                )
                
                if choice != 'Neither':
                    return choice
                    
            except DeckBuilderError as e:
                logger.warning(f"Commander selection attempt failed: {e}")
                continue
                
    def _confirm_commander(self, df: pd.DataFrame, commander_name: str) -> Dict:
        """Confirm commander selection and validate data.
        
        Args:
            df: DataFrame containing commander data
            commander_name: Name of selected commander
            
        Returns:
            Dictionary containing commander data
            
        Raises:
            CommanderValidationError: If commander data is invalid
        """
        try:
            # Validate commander data
            commander_data = builder_utils.validate_commander_selection(df, commander_name)
            
            # Store commander DataFrame
            self.commander_df = pd.DataFrame(commander_data)
            
            # Display commander info
            print('\nSelected Commander:')
            pprint.pprint(commander_data, sort_dicts=False)
            
            # Confirm selection
            if not self.input_handler.questionnaire('Confirm', 'Is this the commander you want?', True):
                raise CommanderSelectionError("Commander selection cancelled by user")
            
            # Check price if enabled
            if self.price_checker:
                self.price_checker.get_card_price(commander_name)
                
            return commander_data
            
        except DeckBuilderError as e:
            logger.error(f"Commander confirmation failed: {e}")
            raise
            
    def _initialize_commander(self, commander_data: Dict) -> None:
        """Initialize commander attributes from validated data.
        
        Args:
            commander_data: Dictionary containing commander information
            
        Raises:
            CommanderValidationError: If required attributes are missing
        """
        try:
            # Store commander info
            self.commander_info = commander_data
            self.commander = commander_data['name'][0]
            
            # Initialize commander attributes
            self.commander_setup()
            logger.debug("Commander attributes initialized successfully")
            
        except Exception as e:
            logger.error(f"Commander initialization failed: {e}")
            raise CommanderValidationError(f"Failed to initialize commander: {str(e)}")

    # Setup Commander
    def commander_setup(self) -> None:
        """Set up commander attributes and initialize deck building.
        
        This method orchestrates the commander setup process by calling specialized
        helper methods to handle different aspects of initialization.
        
        Raises:
            CommanderValidationError: If commander validation fails
            DeckBuilderError: If deck building initialization fails
        """
        try:
            # Initialize commander attributes
            self._initialize_commander_attributes()
            
            # Set up commander components
            self._setup_commander_type_and_text()
            self._setup_commander_stats()
            self._setup_color_identity()
            self._setup_creature_types()
            self._setup_commander_tags()
            
            # Initialize commander dictionary and deck
            self._initialize_commander_dict()
            self._initialize_deck_building()
            
            logger.info("Commander setup completed successfully")
            
        except CommanderValidationError as e:
            logger.error(f"Commander validation failed: {e}")
            raise
        except DeckBuilderError as e:
            logger.error(f"Deck building initialization failed: {e}")
            raise

    def _initialize_commander_attributes(self) -> None:
        """Initialize basic commander attributes with defaults.
        
        Uses settings.py constants for default values.
        """
        self.commander_power = COMMANDER_POWER_DEFAULT
        self.commander_toughness = COMMANDER_TOUGHNESS_DEFAULT
        self.commander_mana_value = COMMANDER_MANA_VALUE_DEFAULT
        self.commander_type = COMMANDER_TYPE_DEFAULT
        self.commander_text = COMMANDER_TEXT_DEFAULT
        self.commander_mana_cost = COMMANDER_MANA_COST_DEFAULT
        self.color_identity = COMMANDER_COLOR_IDENTITY_DEFAULT
        self.colors = COMMANDER_COLORS_DEFAULT.copy()
        self.creature_types = COMMANDER_CREATURE_TYPES_DEFAULT
        self.commander_tags = COMMANDER_TAGS_DEFAULT.copy()
        self.themes = COMMANDER_THEMES_DEFAULT.copy()

    def _setup_commander_type_and_text(self) -> None:
        """Set up and validate commander type line and text.
        
        Raises:
            CommanderTypeError: If type line validation fails
        """
        df = self.commander_df
        type_line = str(df.at[0, 'type'])
        self.commander_type = self.input_handler.validate_commander_type(type_line)
        self.commander_text = str(df.at[0, 'text'])

    def _setup_commander_stats(self) -> None:
        """Set up and validate commander power, toughness, and mana values.
        
        Raises:
            CommanderStatsError: If stats validation fails
        """
        df = self.commander_df
        
        # Validate power and toughness
        self.commander_power = self.input_handler.validate_commander_stats(
            'power', str(df.at[0, 'power']))
        self.commander_toughness = self.input_handler.validate_commander_stats(
            'toughness', str(df.at[0, 'toughness']))
            
        # Set mana cost and value
        self.commander_mana_cost = str(df.at[0, 'manaCost'])
        self.commander_mana_value = self.input_handler.validate_commander_stats(
            'mana value', int(df.at[0, 'manaValue']))

    def _setup_color_identity(self) -> None:
        """Set up and validate commander color identity.
        
        Raises:
            CommanderColorError: If color identity validation fails
        """
        df = self.commander_df
        try:
            color_id = df.at[0, 'colorIdentity']
            if pd.isna(color_id):
                color_id = 'COLORLESS'
            
            self.color_identity = self.input_handler.validate_commander_colors(color_id)
            self.color_identity_full = ''
            self.determine_color_identity()
            print(self.color_identity_full)
            
            # Set colors list
            if pd.notna(df.at[0, 'colors']) and df.at[0, 'colors'].strip():
                self.colors = [color.strip() for color in df.at[0, 'colors'].split(',') if color.strip()]
                if not self.colors:
                    self.colors = ['COLORLESS']
            else:
                self.colors = ['COLORLESS']
                
        except Exception as e:
            raise CommanderColorError(f"Failed to set color identity: {str(e)}")

    def _setup_creature_types(self) -> None:
        """Set up commander creature types."""
        df = self.commander_df
        self.creature_types = str(df.at[0, 'creatureTypes'])

    def _setup_commander_tags(self) -> None:
        """Set up and validate commander theme tags.
        
        Raises:
            CommanderTagError: If tag validation fails
        """
        df = self.commander_df
        tags = list(df.at[0, 'themeTags'])
        self.commander_tags = self.input_handler.validate_commander_tags(tags)
        self.determine_themes()

    def _initialize_commander_dict(self) -> None:
        """Initialize the commander dictionary with validated data."""
        self.commander_dict: CommanderDict = {
            'Commander Name': self.commander,
            'Mana Cost': self.commander_mana_cost,
            'Mana Value': self.commander_mana_value,
            'Color Identity': self.color_identity_full,
            'Colors': self.colors,
            'Type': self.commander_type,
            'Creature Types': self.creature_types,
            'Text': self.commander_text,
            'Power': self.commander_power,
            'Toughness': self.commander_toughness,
            'Themes': self.themes,
            'CMC': 0.0
        }
        self.add_card(self.commander, self.commander_type,
                      self.commander_mana_cost, self.commander_mana_value,
                      self.creature_types, self.commander_tags, True)

    def _initialize_deck_building(self) -> None:
        """Initialize deck building process.
        
        Raises:
            DeckBuilderError: If deck building initialization fails
        """
        try:
            # Set up initial deck structure
            self.setup_dataframes()
            self.determine_ideals()
            
            # Add cards by category
            self.add_lands()
            self.add_creatures()
            self.add_ramp()
            self.add_board_wipes()
            self.add_interaction()
            self.add_card_advantage()
            
            # Fill remaining slots if needed
            if len(self.card_library) < 100:
                self.fill_out_deck()
                
            # Process and organize deck
            self.organize_library()
            
            # Log deck composition
            self._log_deck_composition()
            
            # Finalize deck
            self.get_cmc()
            self.count_pips()
            self.concatenate_duplicates()
            self.organize_library()
            self.sort_library()
            self.commander_to_top()
            
            # Save final deck
            FILE_TIME = time.strftime("%Y%m%d-%H%M%S")
            DECK_FILE = f'{self.commander}_{FILE_TIME}.csv'
            self.card_library.to_csv(f'{DECK_DIRECTORY}/{DECK_FILE}', index=False)
            
        except Exception as e:
            raise DeckBuilderError(f"Failed to initialize deck building: {str(e)}")

    def _log_deck_composition(self) -> None:
        """Log the deck composition statistics."""
        logger.info(f'Creature cards (including commander): {self.creature_cards}')
        logger.info(f'Planeswalker cards: {self.planeswalker_cards}')
        logger.info(f'Battle cards: {self.battle_cards}')
        logger.info(f'Instant cards: {self.instant_cards}')
        logger.info(f'Sorcery cards: {self.sorcery_cards}')
        logger.info(f'Artifact cards: {self.artifact_cards}')
        logger.info(f'Enchantment cards: {self.enchantment_cards}')
        logger.info(f'Land cards cards: {self.land_cards}')
        logger.info(f'Number of cards in Library: {len(self.card_library)}')
    
    # Determine and validate color identity
    def determine_color_identity(self) -> None:
        """Determine the deck's color identity and set related attributes.

        This method orchestrates the color identity determination process by:
        1. Validating the color identity input
        2. Determining the appropriate color combination type
        3. Setting color identity attributes based on the combination

        Raises:
            CommanderColorError: If color identity validation fails
        """
        try:
            # Validate color identity using input handler
            validated_identity = self.input_handler.validate_commander_colors(self.color_identity)
            
            # Determine color combination type and set attributes
            if self._determine_mono_color(validated_identity):
                return
            
            if self._determine_dual_color(validated_identity):
                return
            
            if self._determine_tri_color(validated_identity):
                return
            
            if self._determine_other_color(validated_identity):
                return
            
            # Handle unknown color identity
            logger.warning(f"Unknown color identity: {validated_identity}")
            self.color_identity_full = 'Unknown'
            self.files_to_load = ['colorless']
            
        except CommanderColorError as e:
            logger.error(f"Color identity validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in determine_color_identity: {e}")
            raise CommanderColorError(f"Failed to determine color identity: {str(e)}")

    def _determine_mono_color(self, color_identity: str) -> bool:
        """Handle single color identities.

        Args:
            color_identity: Validated color identity string

        Returns:
            True if color identity was handled, False otherwise
        """
        from settings import MONO_COLOR_MAP
        
        if color_identity in MONO_COLOR_MAP:
            self.color_identity_full, self.files_to_load = MONO_COLOR_MAP[color_identity]
            return True
        return False

    def _determine_dual_color(self, color_identity: str) -> bool:
        """Handle two-color combinations.

        Args:
            color_identity: Validated color identity string

        Returns:
            True if color identity was handled, False otherwise
        """
        from settings import DUAL_COLOR_MAP
        
        if color_identity in DUAL_COLOR_MAP:
            identity_info = DUAL_COLOR_MAP[color_identity]
            self.color_identity_full = identity_info[0]
            self.color_identity_options = identity_info[1]
            self.files_to_load = identity_info[2]
            return True
        return False

    def _determine_tri_color(self, color_identity: str) -> bool:
        """Handle three-color combinations.

        Args:
            color_identity: Validated color identity string

        Returns:
            True if color identity was handled, False otherwise
        """
        from settings import TRI_COLOR_MAP
        
        if color_identity in TRI_COLOR_MAP:
            identity_info = TRI_COLOR_MAP[color_identity]
            self.color_identity_full = identity_info[0]
            self.color_identity_options = identity_info[1]
            self.files_to_load = identity_info[2]
            return True
        return False

    def _determine_other_color(self, color_identity: str) -> bool:
        """Handle four and five color combinations.

        Args:
            color_identity: Validated color identity string

        Returns:
            True if color identity was handled, False otherwise
        """
        from builder_constants import OTHER_COLOR_MAP
        
        if color_identity in OTHER_COLOR_MAP:
            identity_info = OTHER_COLOR_MAP[color_identity]
            self.color_identity_full = identity_info[0]
            self.color_identity_options = identity_info[1]
            self.files_to_load = identity_info[2]
            return True
        return False

    # CSV and dataframe functionality
    def read_csv(self, filename: str, converters: dict | None = None) -> pd.DataFrame:
        """Read and validate CSV file with comprehensive error handling.

        Args:
            filename: Name of the CSV file without extension
            converters: Dictionary of converters for specific columns

        Returns:
            pd.DataFrame: Validated and processed DataFrame

        Raises:
            CSVReadError: If file cannot be read
            CSVValidationError: If data fails validation
            CSVTimeoutError: If read operation times out
            EmptyDataFrameError: If DataFrame is empty
        """
        filepath = f'{CSV_DIRECTORY}/{filename}_cards.csv'
        
        try:
            # Read with timeout
            df = pd.read_csv(
                filepath,
                converters=converters or {'themeTags': pd.eval, 'creatureTypes': pd.eval},
            )
            
            # Check for empty DataFrame
            if df.empty:
                raise EmptyDataFrameError(f"Empty DataFrame from {filename}_cards.csv")
            
            # Validate required columns
            missing_cols = set(CSV_REQUIRED_COLUMNS) - set(df.columns)
            if missing_cols:
                raise CSVValidationError(f"Missing required columns: {missing_cols}")
            
            # Validate data rules
            for col, rules in CSV_VALIDATION_RULES.items():
                if rules.get('required', False) and df[col].isnull().any():
                    raise CSVValidationError(f"Missing required values in column: {col}")
                if 'type' in rules:
                    expected_type = rules['type']
                    actual_type = df[col].dtype.name
                    if expected_type == 'str' and actual_type not in ['object', 'string']:
                        raise CSVValidationError(f"Invalid type for column {col}: expected {expected_type}, got {actual_type}")
                    elif expected_type != 'str' and not actual_type.startswith(expected_type):
                        raise CSVValidationError(f"Invalid type for column {col}: expected {expected_type}, got {actual_type}")
            logger.debug(f"Successfully read and validated {filename}_cards.csv")
            #print(df.columns)
            return df
            
        except pd.errors.EmptyDataError:
            raise EmptyDataFrameError(f"Empty CSV file: {filename}_cards.csv")
            
        except FileNotFoundError as e:
            logger.error(f"File {filename}_cards.csv not found: {e}")
            setup_utils.regenerate_csvs_all()
            return self.read_csv(filename, converters)
            
        except TimeoutError:
            raise CSVTimeoutError(f"Timeout reading {filename}_cards.csv", CSV_READ_TIMEOUT)
            
        except Exception as e:
            logger.error(f"Error reading {filename}_cards.csv: {e}")
            raise CSVReadError(f"Failed to read {filename}_cards.csv: {str(e)}")
    
    def write_csv(self, df: pd.DataFrame, filename: str) -> None:
        """Write DataFrame to CSV with error handling and logger.
        
        Args:
            df: DataFrame to write
            filename: Name of the CSV file without extension
        """
        try:
            filepath = f'{CSV_DIRECTORY}/{filename}.csv'
            df.to_csv(filepath, index=False)
            logger.debug(f"Successfully wrote {filename}.csv")
        except Exception as e:
            logger.error(f"Error writing {filename}.csv: {e}")
    
    def _load_and_combine_data(self) -> pd.DataFrame:
        """Load and combine data from multiple CSV files.

        Returns:
            Combined DataFrame from all source files

        Raises:
            CSVError: If data loading or combining fails
            EmptyDataFrameError: If no valid data is loaded
        """
        logger.info("Loading and combining data from CSV files...")
        all_df = []

        try:
            # Wrap files_to_load with tqdm for progress bar
            for file in tqdm(self.files_to_load, desc="Loading card data files", leave=False):
                df = self.read_csv(file)
                if df.empty:
                    raise EmptyDataFrameError(f"Empty DataFrame from {file}")
                all_df.append(df)
                #print(df.columns)
            return builder_utils.combine_dataframes(all_df)

        except (CSVError, EmptyDataFrameError) as e:
            logger.error(f"Error loading and combining data: {e}")
            raise

    def _split_into_specialized_frames(self, df: pd.DataFrame) -> None:
        """Split combined DataFrame into specialized component frames.

        Args:
            df: Source DataFrame to split

        Raises:
            DataFrameValidationError: If data splitting fails
        """
        try:
            # Extract lands
            self.land_df = df[df['type'].str.contains('Land')].copy()
            self.land_df.sort_values(by='edhrecRank', inplace=True)
            
            # Remove lands from main DataFrame
            df = df[~df['type'].str.contains('Land')]
            df.to_csv(f'{CSV_DIRECTORY}/test_cards.csv', index=False)
            
            # Create specialized frames
            self.artifact_df = df[df['type'].str.contains('Artifact')].copy()
            self.battle_df = df[df['type'].str.contains('Battle')].copy()
            self.creature_df = df[df['type'].str.contains('Creature')].copy()
            self.noncreature_df = df[~df['type'].str.contains('Creature')].copy()
            self.enchantment_df = df[df['type'].str.contains('Enchantment')].copy()
            self.instant_df = df[df['type'].str.contains('Instant')].copy()
            self.planeswalker_df = df[df['type'].str.contains('Planeswalker')].copy()
            self.nonplaneswalker_df = df[~df['type'].str.contains('Planeswalker')].copy()
            self.sorcery_df = df[df['type'].str.contains('Sorcery')].copy()

            self.battle_df.to_csv(f'{CSV_DIRECTORY}/test_battle_cards.csv', index=False)
            
            # Sort all frames
            for frame in [self.artifact_df, self.battle_df, self.creature_df,
                         self.noncreature_df, self.enchantment_df, self.instant_df,
                         self.planeswalker_df, self.sorcery_df]:
                frame.sort_values(by='edhrecRank', inplace=True)
                
        except Exception as e:
            logger.error(f"Error splitting DataFrames: {e}")
            raise DataFrameValidationError("DataFrame splitting failed", {}, {"error": str(e)})

    def _validate_dataframes(self) -> None:
        """Validate all component DataFrames.

        Raises:
            DataFrameValidationError: If validation fails
        """
        try:
            frames_to_validate = {
                'land': self.land_df,
                'artifact': self.artifact_df,
                'battle': self.battle_df,
                'creature': self.creature_df,
                'noncreature': self.noncreature_df,
                'enchantment': self.enchantment_df,
                'instant': self.instant_df,
                'planeswalker': self.planeswalker_df,
                'sorcery': self.sorcery_df
            }
            
            for name, frame in frames_to_validate.items():
                rules = builder_utils.get_validation_rules(name)
                if not builder_utils.validate_dataframe(frame, rules):
                    raise DataFrameValidationError(f"{name} validation failed", rules)
                    
        except Exception as e:
            logger.error(f"DataFrame validation failed: {e}")
            raise

    def _save_intermediate_results(self) -> None:
        """Save intermediate DataFrames for debugging and analysis.

        Raises:
            CSVError: If saving fails
        """
        try:
            frames_to_save = {
                'lands': self.land_df,
                'artifacts': self.artifact_df,
                'battles': self.battle_df,
                'creatures': self.creature_df,
                'noncreatures': self.noncreature_df,
                'enchantments': self.enchantment_df,
                'instants': self.instant_df,
                'planeswalkers': self.planeswalker_df,
                'sorcerys': self.sorcery_df
            }
            
            for name, frame in frames_to_save.items():
                self.write_csv(frame, f'test_{name}')
                
        except Exception as e:
            logger.error(f"Error saving intermediate results: {e}")
            raise CSVError(f"Failed to save intermediate results: {str(e)}")

    def setup_dataframes(self) -> None:
        """Initialize and validate all required DataFrames.
        
        This method orchestrates the DataFrame setup process by:
        1. Loading and combining data from CSV files
        2. Splitting into specialized component frames
        3. Validating all DataFrames
        4. Saving intermediate results
        
        Raises:
            CSVError: If any CSV operations fail
            EmptyDataFrameError: If any required DataFrame is empty
            DataFrameValidationError: If validation fails
        """
        try:
            # Load and combine data
            self.full_df = self._load_and_combine_data()
            self.full_df = self.full_df[~self.full_df['name'].str.contains(self.commander)]
            self.full_df.sort_values(by='edhrecRank', inplace=True)
            self.full_df.to_csv(f'{CSV_DIRECTORY}/test_full_cards.csv', index=False)
            
            # Split into specialized frames
            self._split_into_specialized_frames(self.full_df)
            # Validate all frames
            self._validate_dataframes()
            
            # Save intermediate results
            self._save_intermediate_results()
            
            logger.info("DataFrame setup completed successfully")
            
        except (CSVError, EmptyDataFrameError, DataFrameValidationError) as e:
            logger.error(f"Error in DataFrame setup: {e}")
            raise
    
    # Theme selection
    def determine_themes(self) -> None:
        """Determine and set up themes for the deck building process.
        
        This method handles:
        1. Theme selection (primary, secondary, tertiary)
        2. Theme weight calculations
        3. Hidden theme detection and setup
        
        Raises:
            ThemeSelectionError: If theme selection fails
            ThemeWeightError: If weight calculation fails
        """
        try:
            # Get available themes from commander tags
            themes = self.commander_tags.copy()
            
            # Get available themes from commander tags
            themes = self.commander_tags.copy()
            
            # Initialize theme flags
            self.hidden_theme = False
            self.secondary_theme = False
            self.tertiary_theme = False
            
            # Select primary theme (required)
            self.primary_theme = builder_utils.select_theme(
                themes,
                'Choose a primary theme for your commander deck.\n'
                'This will be the "focus" of the deck, in a kindred deck this will typically be a creature type for example.'
            )
            themes.remove(self.primary_theme)
            
            # Initialize self.weights from settings
            from settings import THEME_WEIGHTS_DEFAULT
            self.weights = THEME_WEIGHTS_DEFAULT.copy()
            # Set initial weights for primary-only case
            self.weights['primary'] = 1.0
            self.weights['secondary'] = 0.0
            self.weights['tertiary'] = 0.0
            self.primary_weight = 1.0
            
            # Select secondary theme if desired
            if themes:
                self.secondary_theme = builder_utils.select_theme(
                    themes,
                    'Choose a secondary theme for your commander deck.\n'
                    'This will typically be a secondary focus, like card draw for Spellslinger, or +1/+1 counters for Aggro.',
                    optional=True
                )
                
                # Check for Stop Here before modifying themes list
                if self.secondary_theme == 'Stop Here':
                    self.secondary_theme = False
                elif self.secondary_theme:
                    themes.remove(self.secondary_theme)
                    self.weights['secondary'] = 0.6
                    self.weights = builder_utils.adjust_theme_weights(
                        self.primary_theme,
                        self.secondary_theme,
                        None,  # No tertiary theme yet
                        self.weights
                    )
                    self.primary_weight = self.weights['primary']
                    self.secondary_weight = self.weights['secondary']
            
            # Select tertiary theme if desired
            if themes and self.secondary_theme and self.secondary_theme != 'Stop Here':
                self.tertiary_theme = builder_utils.select_theme(
                    themes,
                    'Choose a tertiary theme for your commander deck.\n'
                    'This will typically be a tertiary focus, or just something else to do that your commander is good at.',
                    optional=True
                )
                
                # Check for Stop Here before modifying themes list
                if self.tertiary_theme == 'Stop Here':
                    self.tertiary_theme = False
                elif self.tertiary_theme:
                    self.weights['tertiary'] = 0.3
                    self.weights = builder_utils.adjust_theme_weights(
                        self.primary_theme,
                        self.secondary_theme,
                        self.tertiary_theme,
                        self.weights
                    )
                    self.primary_weight = self.weights['primary']
                    self.secondary_weight = self.weights['secondary']
                    self.tertiary_weight = self.weights['tertiary']
            
            # Build final themes list
            self.themes = [self.primary_theme]
            if self.secondary_theme:
                self.themes.append(self.secondary_theme)
            if self.tertiary_theme:
                self.themes.append
            self.determine_hidden_themes()

        except (ThemeSelectionError, ThemeWeightError) as e:
            logger.error(f"Error in theme determination: {e}")
            raise

    def determine_hidden_themes(self) -> None:            
        """
        Setting 'Hidden' themes for multiple-copy cards, such as 'Hare Apparent' or 'Shadowborn Apostle'.
        These are themes that will be prompted for under specific conditions, such as a matching Kindred theme or a matching color combination and Spellslinger theme for example.
        Typically a hidden theme won't come up, but if it does, it will take priority with theme self.weights to ensure a decent number of the specialty cards are added.
        """
        # Setting hidden theme for Kindred-specific themes
        hidden_themes = ['Advisor Kindred', 'Demon Kindred', 'Dwarf Kindred', 'Rabbit Kindred', 'Rat Kindred', 'Wraith Kindred']
        theme_cards = ['Persistent Petitioners', 'Shadowborn Apostle', 'Seven Dwarves', 'Hare Apparent', ['Rat Colony', 'Relentless Rats'], 'Nazgûl']
        color = ['B', 'B', 'R', 'W', 'B', 'B']
        for i in range(min(len(hidden_themes), len(theme_cards), len(color))):
            if (hidden_themes[i] in self.themes
                and hidden_themes[i] != 'Rat Kindred'
                and color[i] in self.colors):
                logger.info(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i]} deck?')
                choice = self.input_handler.questionnaire('Confirm', message='', default_value=False)
                if choice:
                    self.hidden_theme = theme_cards[i]
                    self.themes.append(self.hidden_theme)
                    self.weights['primary'] = round(self.weights['primary'] / 3, 2)
                    self.weights['secondary'] = round(self.weights['secondary'] / 2, 2)
                    self.weights['tertiary'] = self.weights['tertiary'] 
                    self.weights['hidden'] = round(1.0 - self.weights['primary'] - self.weights['secondary'] - self.weights['tertiary'], 2)
                    self.primary_weight = self.weights['primary']
                    self.secondary_weight = self.weights['secondary']
                    self.tertiary_weight = self.weights['tertiary']
                    self.hidden_weight = self.weights['hidden']
                else:
                    continue
                
            elif (hidden_themes[i] in self.themes
                    and hidden_themes[i] == 'Rat Kindred'
                    and color[i] in self.colors):
                logger.info(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i][0]} or {theme_cards[i][1]} deck?')
                choice = self.input_handler.questionnaire('Confirm', message='', default_value=False)
                if choice:
                    print('Which one?')
                    choice = self.input_handler.questionnaire('Choice', choices_list=theme_cards[i], message='')
                    if choice:
                        self.hidden_theme = choice
                        self.themes.append(self.hidden_theme)
                        self.weights['primary'] = round(self.weights['primary'] / 3, 2)
                        self.weights['secondary'] = round(self.weights['secondary'] / 2, 2)
                        self.weights['tertiary'] = self.weights['tertiary'] 
                        self.weights['hidden'] = round(1.0 - self.weights['primary'] - self.weights['secondary'] - self.weights['tertiary'], 2)
                        self.primary_weight = self.weights['primary']
                        self.secondary_weight = self.weights['secondary']
                        self.tertiary_weight = self.weights['tertiary']
                        self.hidden_weight = self.weights['hidden']
                else:
                    continue
        
        # Setting the hidden theme for non-Kindred themes
        hidden_themes = ['Little Fellas', 'Mill', 'Spellslinger', 'Spells Matter', 'Spellslinger', 'Spells Matter',]
        theme_cards = ['Hare Apparent', 'Persistent Petitions', 'Dragon\'s Approach', 'Dragon\'s Approach', 'Slime Against Humanity', 'Slime Against Humanity']
        color = ['W', 'B', 'R', 'R', 'G', 'G']
        for i in range(min(len(hidden_themes), len(theme_cards), len(color))):
            if (hidden_themes[i] in self.themes
                and color[i] in self.colors):
                logger.info(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i]} deck?')
                choice = self.input_handler.questionnaire('Confirm', message='', default_value=False)
                if choice:
                    self.hidden_theme = theme_cards[i]
                    self.themes.append(self.hidden_theme)
                    self.weights['primary'] = round(self.weights['primary'] / 3, 2)
                    self.weights['secondary'] = round(self.weights['secondary'] / 2, 2)
                    self.weights['tertiary'] = self.weights['tertiary'] 
                    self.weights['hidden'] = round(1.0 - self.weights['primary'] - self.weights['secondary'] - self.weights['tertiary'], 2)
                    self.primary_weight = self.weights['primary']
                    self.secondary_weight = self.weights['secondary']
                    self.tertiary_weight = self.weights['tertiary']
                    self.hidden_weight = self.weights['hidden']
                else:
                    continue
    
    # Setting ideals
    def determine_ideals(self):
        """Determine ideal card counts and price settings for the deck.

        This method handles:
        1. Price configuration (if price checking is enabled)
        2. Setting ideal counts for different card types
        3. Calculating remaining free slots

        Raises:
            PriceConfigurationError: If there are issues configuring price settings
            IdealDeterminationError: If there are issues determining ideal counts
        """
        try:
            # Initialize free slots
            self.free_slots = 99

            # Configure price settings if enabled
            if use_scrython:
                try:
                    builder_utils.configure_price_settings(self.price_checker, self.input_handler)
                except ValueError as e:
                    raise PriceConfigurationError(f"Failed to configure price settings: {str(e)}")

            # Get deck composition values
            try:
                composition = builder_utils.get_deck_composition_values(self.input_handler)
            except ValueError as e:
                raise IdealDeterminationError(f"Failed to determine deck composition: {str(e)}")

            # Update class attributes with composition values
            self.ideal_ramp = composition['ramp']
            self.ideal_land_count = composition['lands']
            self.min_basics = composition['basic_lands']
            self.ideal_creature_count = composition['creatures']
            self.ideal_removal = composition['removal']
            self.ideal_wipes = composition['wipes']
            self.ideal_card_advantage = composition['card_advantage']
            self.ideal_protection = composition['protection']

            # Update free slots
            for value in [self.ideal_ramp, self.ideal_land_count, self.ideal_creature_count,
                         self.ideal_removal, self.ideal_wipes, self.ideal_card_advantage,
                         self.ideal_protection]:
                self.free_slots -= value

            print(f'\nFree slots that aren\'t part of the ideals: {self.free_slots}')
            print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')

        except (PriceConfigurationError, IdealDeterminationError) as e:
            logger.error(f"Error in determine_ideals: {e}")
            raise
    
    # Adding card to library
    def add_card(self, card: str, card_type: str, mana_cost: str, mana_value: int, creature_types: list = None, tags: list = None, is_commander: bool = False) -> None:
        """Add a card to the deck library with price checking if enabled.
        Args:
            card (str): Name of the card to add
            card_type (str): Type of the card (e.g., 'Creature', 'Instant')
            mana_cost (str): Mana cost string representation
            mana_value (int): Converted mana cost/mana value
            creature_types (list): List of creature types in the card (if any)
            themes (list): List of themes the card has
            is_commander (bool, optional): Whether this card is the commander. Defaults to False.

        Returns:
            None

        Raises:
            PriceLimitError: If card price exceeds maximum allowed price
            PriceAPIError: If there is an error fetching the price
            PriceTimeoutError: If the price check times out
            PriceValidationError: If the price data is invalid
        """
        multiple_copies = BASIC_LANDS + MULTIPLE_COPY_CARDS

        # Skip if card already exists and isn't allowed multiple copies
        if card in pd.Series(self.card_library['Card Name']).values and card not in multiple_copies:
            return

        # Handle price checking
        card_price = 0.0
        try:
            # Get price and validate
            card_price = self.price_checker.get_card_price(card)
            self.price_checker.validate_card_price(card, card_price)
            self.price_checker.update_deck_price(card_price)
        except (PriceAPIError, PriceTimeoutError, PriceValidationError, PriceLimitError) as e:
            logger.warning(str(e))
            return

        # Create card entry
        card_entry = [card, card_type, mana_cost, mana_value, creature_types, tags, is_commander]

        # Add to library
        self.card_library.loc[len(self.card_library)] = card_entry

        logger.debug(f"Added {card} to deck library")
    
    # Get card counts, sort library, set commander at index 1, and combine duplicates into 1 entry
    def organize_library(self):
        """Organize and count cards in the library by their types.

        This method counts the number of cards for each card type in the library
        and updates the corresponding instance variables. It uses the count_cards_by_type
        helper function from builder_utils for efficient counting.

        The method handles the following card types:
        - Artifacts
        - Battles
        - Creatures
        - Enchantments
        - Instants
        - Kindred (if applicable)
        - Lands
        - Planeswalkers
        - Sorceries

        Raises:
            CardTypeCountError: If there are issues counting cards by type
            LibraryOrganizationError: If library organization fails
        """
        try:
            # Get all card types to count, including Kindred if not already present
            all_types = CARD_TYPES + ['Kindred'] if 'Kindred' not in CARD_TYPES else CARD_TYPES

            # Use helper function to count cards by type
            card_counters = builder_utils.count_cards_by_type(self.card_library, all_types)

            # Update instance variables with counts
            self.artifact_cards = card_counters['Artifact']
            self.battle_cards = card_counters['Battle']
            self.creature_cards = card_counters['Creature']
            self.enchantment_cards = card_counters['Enchantment']
            self.instant_cards = card_counters['Instant']
            self.kindred_cards = card_counters.get('Kindred', 0)
            self.land_cards = card_counters['Land']
            self.planeswalker_cards = card_counters['Planeswalker']
            self.sorcery_cards = card_counters['Sorcery']

            logger.debug(f"Library organized successfully with {len(self.card_library)} total cards")

        except (CardTypeCountError, Exception) as e:
            logger.error(f"Error organizing library: {e}")
            raise LibraryOrganizationError(f"Failed to organize library: {str(e)}")
    
    def sort_library(self) -> None:
        """Sort the card library by card type and name.

        This method sorts the card library first by card type according to the
        CARD_TYPE_SORT_ORDER constant, and then alphabetically by card name.
        It uses the assign_sort_order() helper function to ensure consistent
        type-based sorting across the application.

        The sorting order is:
        1. Card type (Planeswalker -> Battle -> Creature -> Instant -> Sorcery ->
           Artifact -> Enchantment -> Land)
        2. Card name (alphabetically)

        Raises:
            LibrarySortError: If there are issues during the sorting process
        """
        try:
            # Use the assign_sort_order helper function to add sort order
            sorted_library = builder_utils.assign_sort_order(self.card_library)

            # Sort by Sort Order and Card Name
            sorted_library = sorted_library.sort_values(
                by=['Sort Order', 'Card Name'],
                ascending=[True, True]
            )

            # Clean up and reset index
            self.card_library = (
                sorted_library
                .drop(columns=['Sort Order'])
                .reset_index(drop=True)
            )

            logger.debug("Card library sorted successfully")

        except Exception as e:
            logger.error(f"Error sorting library: {e}")
            raise LibrarySortError(
                "Failed to sort card library",
                {"error": str(e)}
            )
            
    def commander_to_top(self) -> None:
        """Move commander card to the top of the library while preserving commander status.
        
        This method identifies the commander card in the library using a boolean mask,
        removes it from its current position, and prepends it to the top of the library.
        The commander's status and attributes are preserved during the move.
        
        Raises:
            CommanderMoveError: If the commander cannot be found in the library or
                               if there are issues with the move operation.
        """
        try:
            # Create boolean mask to identify commander
            commander_mask = self.card_library['Commander']
            
            # Check if commander exists in library
            if not commander_mask.any():
                error_msg = "Commander not found in library"
                logger.warning(error_msg)
                raise CommanderMoveError(error_msg)
            
            # Get commander row and name for logging
            commander_row = self.card_library[commander_mask].copy()
            commander_name = commander_row['Card Name'].iloc[0]
            
            # Remove commander from current position
            self.card_library = self.card_library[~commander_mask]
            
            # Prepend commander to top of library
            self.card_library = pd.concat([commander_row, self.card_library], ignore_index=True)
            
            logger.info(f"Successfully moved commander '{commander_name}' to top of library")
            
        except CommanderMoveError:
            raise
        except Exception as e:
            error_msg = f"Error moving commander to top: {str(e)}"
            logger.error(error_msg)
            raise CommanderMoveError(error_msg)

    def concatenate_duplicates(self):
        """Process duplicate cards in the library using the helper function.

        This method consolidates duplicate cards (like basic lands and special cards
        that can have multiple copies) into single entries with updated counts.
        It uses the process_duplicate_cards helper function from builder_utils.

        Raises:
            DuplicateCardError: If there are issues processing duplicate cards
        """
        try:
            # Get list of cards that can have duplicates
            duplicate_lists = BASIC_LANDS + MULTIPLE_COPY_CARDS

            # Process duplicates using helper function
            self.card_library = builder_utils.process_duplicate_cards(
                self.card_library,
                duplicate_lists
            )

            logger.info("Successfully processed duplicate cards")

        except DuplicateCardError as e:
            logger.error(f"Error processing duplicate cards: {e}")
            raise
    
    # Land Management
    def add_lands(self):
        """
        Add lands to the deck based on ideal count and deck requirements.
        
        The process follows these steps:
        1. Add basic lands distributed by color identity
        2. Add utility/staple lands
        3. Add fetch lands if requested
        4. Add theme-specific lands (e.g., Kindred)
        5. Add multi-color lands based on color count
        6. Add miscellaneous utility lands
        7. Adjust total land count to match ideal count
        """
        MAX_ADJUSTMENT_ATTEMPTS = (self.ideal_land_count - self.min_basics) * 1.5
        self.total_basics = 0
        
        try:
            # Add lands in sequence
            self.add_basics()
            self.check_basics()
            self.add_standard_non_basics()
            self.add_fetches()
            
            # Add theme and color-specific lands
            if any('Kindred' in theme for theme in self.themes):
                self.add_kindred_lands()
            if len(self.colors) >= 2:
                self.add_dual_lands()
            if len(self.colors) >= 3:
                self.add_triple_lands()
            
            self.add_misc_lands()
            
            # Clean up land database
            mask = self.land_df['name'].isin(self.card_library['Card Name'])
            self.land_df = self.land_df[~mask]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            # Adjust to ideal land count
            self.check_basics()
            print()
            logger.info('Adjusting total land count to match ideal count...')
            self.organize_library()
            
            attempts = 0
            while self.land_cards > int(self.ideal_land_count) and attempts < MAX_ADJUSTMENT_ATTEMPTS:
                logger.info(f'Current lands: {self.land_cards}, Target: {self.ideal_land_count}')
                self.remove_basic()
                self.organize_library()
                attempts += 1
            
            if attempts >= MAX_ADJUSTMENT_ATTEMPTS:
                logger.warning(f"Could not reach ideal land count after {MAX_ADJUSTMENT_ATTEMPTS} attempts")
            
            logger.info(f'Final land count: {self.land_cards}')
            
        except Exception as e:
            logger.error(f"Error during land addition: {e}")
            raise
    
    def add_basics(self):
        """Add basic lands to the deck based on color identity and commander tags.

        This method:
        1. Calculates total basics needed based on ideal land count
        2. Gets appropriate basic land mapping (normal or snow-covered)
        3. Distributes basics across colors
        4. Updates the land database

        Raises:
            BasicLandError: If there are issues with basic land addition
            LandDistributionError: If land distribution fails
        """
        try:
            # Calculate total basics needed
            total_basics = self.ideal_land_count - DEFAULT_NON_BASIC_LAND_SLOTS
            if total_basics <= 0:
                raise BasicLandError("Invalid basic land count calculation")

            # Get appropriate basic land mapping
            use_snow = 'Snow' in self.commander_tags
            color_to_basic = builder_utils.get_basic_land_mapping(use_snow)

            # Calculate distribution
            basics_per_color, remaining = builder_utils.calculate_basics_per_color(
                total_basics,
                len(self.colors)
            )

            print()
            logger.info(
                f'Adding {total_basics} basic lands distributed across '
                f'{len(self.colors)} colors'
            )

            # Initialize distribution dictionary
            distribution = {color: basics_per_color for color in self.colors}

            # Distribute remaining basics
            if remaining > 0:
                distribution = builder_utils.distribute_remaining_basics(
                    distribution,
                    remaining,
                    self.colors
                )

            # Add basics according to distribution
            lands_to_remove = []
            for color, count in distribution.items():
                basic = color_to_basic.get(color)
                if basic:
                    for _ in range(count):
                        self.add_card(basic, 'Basic Land', None, 0, is_commander=False)
                    lands_to_remove.append(basic)

            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)

        except Exception as e:
            logger.error(f"Error adding basic lands: {e}")
            raise BasicLandError(f"Failed to add basic lands: {str(e)}")

    def add_standard_non_basics(self):
        """Add staple utility lands to the deck based on predefined conditions and requirements.

        This method processes the STAPLE_LAND_CONDITIONS from settings to add appropriate
        utility lands to the deck. For each potential staple land, it:

        1. Validates the land against deck requirements using:
           - Commander tags
           - Color identity
           - Commander power level
           - Other predefined conditions

        2. Adds validated lands to the deck and tracks them in self.staples

        3. Updates the land database to remove added lands

        The method ensures no duplicate lands are added and maintains proper logging
        of all additions.

        Raises:
            StapleLandError: If there are issues adding staple lands, such as
                            validation failures or database update errors.
        """
        print()
        logger.info('Adding staple non-basic lands')
        self.staples = []

        try:
            for land in STAPLE_LAND_CONDITIONS:
                if builder_utils.validate_staple_land_conditions(
                    land,
                    STAPLE_LAND_CONDITIONS,
                    self.commander_tags,
                    self.colors,
                    self.commander_power
                ):
                    if land not in self.card_library['Card Name'].values:
                        self.add_card(land, 'Land', None, 0)
                        self.staples.append(land)
                        logger.debug(f"Added staple land: {land}")

            self.land_df = builder_utils.process_staple_lands(
                self.staples, self.card_library, self.land_df
            )
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            logger.info(f'Added {len(self.staples)} staple lands:')
            print(*self.staples, sep='\n')
        except Exception as e:
            logger.error(f"Error adding staple lands: {e}")
            raise StapleLandError(f"Failed to add staple lands: {str(e)}")
        
    def add_fetches(self):
        """Add fetch lands to the deck based on user input and deck colors.

        This method handles:
        1. Getting user input for desired number of fetch lands
        2. Validating the input
        3. Getting available fetch lands based on deck colors
        4. Selecting and adding appropriate fetch lands
        5. Updating the land database

        Raises:
            FetchLandValidationError: If fetch land count is invalid
            FetchLandSelectionError: If unable to select required fetch lands
            PriceLimitError: If fetch lands exceed price limits
        """
        try:
            # Get user input for fetch lands
            print()
            logger.info('Adding fetch lands')
            print('How many fetch lands would you like to include?\n'
                  'For most decks you\'ll likely be good with 3 or 4, just enough to thin the deck and help ensure the color availability.\n'
                  'If you\'re doing Landfall, more fetches would be recommended just to get as many Landfall triggers per turn.')
            
            # Get and validate fetch count
            fetch_count = self.input_handler.questionnaire('Number', default_value=FETCH_LAND_DEFAULT_COUNT, message='Default')
            validated_count = builder_utils.validate_fetch_land_count(fetch_count)
            
            # Get available fetch lands based on colors and budget
            max_price = self.max_card_price if hasattr(self, 'max_card_price') else None
            available_fetches = builder_utils.get_available_fetch_lands(
                self.colors,
                self.price_checker if use_scrython else None,
                max_price
            )
            
            # Select fetch lands
            selected_fetches = builder_utils.select_fetch_lands(
                available_fetches,
                validated_count
            )
            
            # Add selected fetch lands to deck
            lands_to_remove = set()
            for fetch in selected_fetches:
                self.add_card(fetch, 'Land', None, 0)
                lands_to_remove.add(fetch)
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(selected_fetches)} fetch lands:')
            print(*selected_fetches, sep='\n')
            
        except (FetchLandValidationError, FetchLandSelectionError, PriceLimitError) as e:
            logger.error(f"Error adding fetch lands: {e}")
            raise
        
    def add_kindred_lands(self):
        """Add Kindred-themed lands to the deck based on commander themes.

        This method handles:
        1. Getting available Kindred lands based on deck themes
        2. Selecting and adding appropriate Kindred lands
        3. Updating the land database

        Raises:
            KindredLandSelectionError: If unable to select required Kindred lands
            PriceLimitError: If Kindred lands exceed price limits
        """
        try:
            print()
            logger.info('Adding Kindred-themed lands')
        
            # Get available Kindred lands based on themes and budget
            max_price = self.max_card_price if hasattr(self, 'max_card_price') else None
            available_lands = builder_utils.get_available_kindred_lands(
                self.land_df,
                self.colors,
                self.commander_tags,
                self.price_checker if use_scrython else None,
                max_price
            )
        
            # Select Kindred lands
            selected_lands = builder_utils.select_kindred_lands(
                available_lands,
                len(available_lands)
            )
            
            # Add selected Kindred lands to deck
            lands_to_remove = set()
            for land in selected_lands:
                self.add_card(land, 'Land', None, 0)
                lands_to_remove.add(land)
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(selected_lands)} Kindred-themed lands:')
            print(*selected_lands, sep='\n')
            
        except Exception as e:
            logger.error(f"Error adding Kindred lands: {e}")
            raise
        
    def add_dual_lands(self):
        """Add dual lands to the deck based on color identity and user preference.

        This method handles the addition of dual lands by:
        1. Validating if dual lands should be added
        2. Getting available dual lands based on deck colors
        3. Selecting appropriate dual lands
        4. Adding selected lands to the deck
        5. Updating the land database

        The process uses helper functions from builder_utils for modular operation.
        """
        try:
            # Check if we should add dual lands
            print()
            print('Would you like to include Dual-type lands (i.e. lands that count as both a Plains and a Swamp for example)?')
            use_duals = self.input_handler.questionnaire('Confirm', message='', default_value=True)
            
            if not use_duals:
                logger.info('Skipping adding Dual-type land cards.')
                return
            
            logger.info('Adding Dual-type lands')
            # Get color pairs by checking DUAL_LAND_TYPE_MAP keys against files_to_load
            color_pairs = []
            for key in DUAL_LAND_TYPE_MAP:
                if key in self.files_to_load:
                    color_pairs.extend([f'Land — {DUAL_LAND_TYPE_MAP[key]}', f'Snow Land — {DUAL_LAND_TYPE_MAP[key]}'])
            
            # Validate dual lands for these color pairs
            if not builder_utils.validate_dual_lands(color_pairs, 'Snow' in self.commander_tags):
                logger.info('No valid dual lands available for this color combination.')
                return
            
            # Get available dual lands
            dual_df = builder_utils.get_available_dual_lands(
                self.land_df,
                color_pairs,
                'Snow' in self.commander_tags
            )
            
            # Select appropriate dual lands
            selected_lands = builder_utils.select_dual_lands(
                dual_df,
                self.price_checker if use_scrython else None,
                self.max_card_price if hasattr(self, 'max_card_price') else None
            )
            
            # Add selected lands to deck
            for land in selected_lands:
                self.add_card(land['name'], land['type'],
                             land['manaCost'], land['manaValue'])
            
            # Update land database
            self.land_df = builder_utils.process_dual_lands(
                selected_lands,
                self.card_library,
                self.land_df
            )
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(selected_lands)} Dual-type land cards:')
            for card in selected_lands:
                print(card['name'])
            
        except Exception as e:
            logger.error(f"Error adding dual lands: {e}")
            raise
    
    def add_triple_lands(self):
        """Add triple lands to the deck based on color identity and user preference.

        This method handles the addition of triple lands by:
        1. Validating if triple lands should be added
        2. Getting available triple lands based on deck colors
        3. Selecting appropriate triple lands
        4. Adding selected lands to the deck
        5. Updating the land database

        The process uses helper functions from builder_utils for modular operation.
        """
        try:
            # Check if we should add triple lands
            print()
            print('Would you like to include triple lands (i.e. lands that count as a Mountain, Forest, and Plains for example)?')
            use_triples = self.input_handler.questionnaire('Confirm', message='', default_value=True)
            
            if not use_triples:
                logger.info('Skipping adding triple lands.')
                return
            
            logger.info('Adding triple lands')
            # Get color triplets by checking TRIPLE_LAND_TYPE_MAP keys against files_to_load
            color_triplets = []
            for key in TRIPLE_LAND_TYPE_MAP:
                if key in self.files_to_load:
                    color_triplets.extend([f'Land — {TRIPLE_LAND_TYPE_MAP[key]}'])
            
            # Validate triple lands for these color triplets
            if not builder_utils.validate_triple_lands(color_triplets, 'Snow' in self.commander_tags):
                logger.info('No valid triple lands available for this color combination.')
                return
            
            # Get available triple lands
            triple_df = builder_utils.get_available_triple_lands(
                self.land_df,
                color_triplets,
                'Snow' in self.commander_tags
            )
            
            # Select appropriate triple lands
            selected_lands = builder_utils.select_triple_lands(
                triple_df,
                self.price_checker if use_scrython else None,
                self.max_card_price if hasattr(self, 'max_card_price') else None
            )
            
            # Add selected lands to deck
            for land in selected_lands:
                self.add_card(land['name'], land['type'],
                             land['manaCost'], land['manaValue'])
            
            # Update land database
            self.land_df = builder_utils.process_triple_lands(
                selected_lands,
                self.card_library,
                self.land_df
            )
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(selected_lands)} triple lands:')
            for card in selected_lands:
                print(card['name'])
            
        except Exception as e:
            logger.error(f"Error adding triple lands: {e}")
            
    def add_misc_lands(self):
        """Add additional utility lands that fit the deck's color identity.

        This method randomly selects a number of miscellaneous utility lands to add to the deck.
        The number of lands is randomly determined between MISC_LAND_MIN_COUNT and MISC_LAND_MAX_COUNT.
        Lands are selected from a filtered pool of the top MISC_LAND_POOL_SIZE lands by EDHREC rank.

        The method handles price constraints if price checking is enabled and updates the land
        database after adding lands to prevent duplicates.

        Raises:
            MiscLandSelectionError: If there are issues selecting appropriate misc lands
        """
        print()
        logger.info('Adding miscellaneous utility lands')
        
        try:
            # Get available misc lands
            available_lands = builder_utils.get_available_misc_lands(
                self.land_df,
                MISC_LAND_POOL_SIZE
            )
            
            if not available_lands:
                logger.warning("No eligible miscellaneous lands found")
                return
            
            # Select random number of lands
            selected_lands = builder_utils.select_misc_lands(
                available_lands,
                MISC_LAND_MIN_COUNT,
                MISC_LAND_MAX_COUNT,
                self.price_checker if use_scrython else None,
                self.max_card_price if hasattr(self, 'max_card_price') else None
            )
            
            # Add selected lands
            lands_to_remove = set()
            for card in selected_lands:
                self.add_card(card['name'], card['type'],
                            card['manaCost'], card['manaValue'])
                lands_to_remove.add(card['name'])
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(selected_lands)} miscellaneous lands:')
            for card in selected_lands:
                print(card['name'])
            
        except Exception as e:
            logger.error(f"Error adding misc lands: {e}")
            raise
        
    def check_basics(self):
        """Check and display counts of each basic land type in the deck.

        This method analyzes the deck's basic land composition by:
        1. Counting each type of basic land (including snow-covered)
        2. Displaying the counts for each basic land type
        3. Calculating and storing the total number of basic lands

        The method uses helper functions from builder_utils for consistent
        counting and display formatting.

        Raises:
            BasicLandCountError: If there are issues counting basic lands

        Note:
            Updates self.total_basics with the sum of all basic lands
        """
        basic_lands = {
            'Plains': 0,
            'Island': 0, 
            'Swamp': 0,
            'Mountain': 0,
            'Forest': 0,
            'Snow-Covered Plains': 0,
            'Snow-Covered Island': 0,
            'Snow-Covered Swamp': 0,
            'Snow-Covered Mountain': 0,
            'Snow-Covered Forest': 0
        }
        
        self.total_basics = 0
        
        try:
            for land in basic_lands:
                count = len(self.card_library[self.card_library['Card Name'] == land])
                basic_lands[land] = count
                self.total_basics += count
            print()
            logger.info("Basic Land Counts:")
            for land, count in basic_lands.items():
                if count > 0:
                    print(f"{land}: {count}")
            logger.info(f"Total basic lands: {self.total_basics}")
        except BasicLandCountError as e:
            logger.error(f"Error counting basic lands: {e}")
            self.total_basics = 0
            raise
   
    def remove_basic(self, max_attempts: int = 3):
        """
        Remove a basic land while maintaining color balance.
        Attempts to remove from colors with more basics first.
        
        Args:
            max_attempts: Maximum number of removal attempts before falling back to non-basics
        """
        print()
        logger.info('Land count over ideal count, removing a basic land.')
        
        color_to_basic = {
            'W': 'Plains', 'U': 'Island', 'B': 'Swamp',
            'R': 'Mountain', 'G': 'Forest'
        }
        
        # Get current basic land counts using vectorized operations
        basic_counts = {
            basic: len(self.card_library[self.card_library['Card Name'] == basic])
            for color, basic in color_to_basic.items()
            if color in self.colors
        }
        
        sum_basics = sum(basic_counts.values())
        attempts = 0
        
        while attempts < max_attempts and sum_basics > self.min_basics:
            if not basic_counts:
                logger.warning("No basic lands found to remove")
                break
                
            basic_land = max(basic_counts.items(), key=lambda x: x[1])[0]
            try:
                # Use boolean indexing for efficiency
                mask = self.card_library['Card Name'] == basic_land
                if not mask.any():
                    basic_counts.pop(basic_land)
                    continue
                    
                index_to_drop = self.card_library[mask].index[0]
                self.card_library = self.card_library.drop(index_to_drop).reset_index(drop=True)
                logger.info(f'{basic_land} removed successfully')
                return
                
            except (IndexError, KeyError) as e:
                logger.error(f"Error removing {basic_land}: {e}")
                basic_counts.pop(basic_land)
            
            attempts += 1
            
        # If we couldn't remove a basic land, try removing a non-basic
        logger.warning("Could not remove basic land, attempting to remove non-basic")
        self.remove_land()
    
    def remove_land(self):
        """Remove a random non-basic, non-staple land from the deck.

        This method attempts to remove a non-protected land from the deck up to
        LAND_REMOVAL_MAX_ATTEMPTS times. It uses helper functions to filter removable
        lands and select a land for removal.

        Raises:
            LandRemovalError: If no removable lands are found or removal fails
        """
        print()
        logger.info('Attempting to remove a non-protected land')
        attempts = 0

        while attempts < LAND_REMOVAL_MAX_ATTEMPTS:
            try:
                # Get removable lands
                removable_lands = builder_utils.filter_removable_lands(self.card_library, PROTECTED_LANDS + self.staples)

                # Select a land for removal
                card_index, card_name = builder_utils.select_land_for_removal(removable_lands)

                # Remove the selected land
                logger.info(f"Removing {card_name}")
                self.card_library.drop(card_index, inplace=True)
                self.card_library.reset_index(drop=True, inplace=True)
                logger.info("Land removed successfully")
                return

            except LandRemovalError as e:
                logger.warning(f"Attempt {attempts + 1} failed: {e}")
                attempts += 1
                continue
            except Exception as e:
                logger.error(f"Unexpected error removing land: {e}")
                raise LandRemovalError(f"Failed to remove land: {str(e)}")

        # If we reach here, we've exceeded max attempts
        raise LandRemovalError(f"Could not find a removable land after {LAND_REMOVAL_MAX_ATTEMPTS} attempts")
    # Count pips and get average CMC
    def count_pips(self):
        """Analyze and display the distribution of colored mana symbols (pips) in card casting costs.

        This method processes the mana costs of all cards in the deck to:
        1. Count the number of colored mana symbols for each color
        2. Calculate the percentage distribution of colors
        3. Log detailed pip distribution information

        The analysis uses helper functions from builder_utils for consistent counting
        and percentage calculations. Results are logged with detailed breakdowns
        of pip counts and distributions.

        Dependencies:
            - MANA_COLORS from settings.py for color iteration
            - builder_utils.count_color_pips() for counting pips
            - builder_utils.calculate_pip_percentages() for distribution calculation

        Returns:
            None

        Raises:
            ManaPipError: If there are issues with:
                - Counting pips for specific colors
                - Calculating pip percentages
                - Unexpected errors during analysis

        Logs:
            - Warning if no colored mana symbols are found
            - Info with detailed pip distribution and percentages
            - Error details if analysis fails
        """
        print()
        logger.info('Analyzing color pip distribution...')
        
        try:
            # Get mana costs from card library
            mana_costs = self.card_library['Mana Cost'].dropna()
            
            # Count pips for each color using helper function
            pip_counts = {}
            for color in MANA_COLORS:
                try:
                    pip_counts[color] = builder_utils.count_color_pips(mana_costs, color)
                except (TypeError, ValueError) as e:
                    raise ManaPipError(
                        f"Error counting {color} pips",
                        {"color": color, "error": str(e)}
                    )
            
            # Calculate percentages using helper function
            try:
                percentages = builder_utils.calculate_pip_percentages(pip_counts)
            except (TypeError, ValueError) as e:
                raise ManaPipError(
                    "Error calculating pip percentages",
                    {"error": str(e)}
                )
            
            # Log detailed pip distribution
            total_pips = sum(pip_counts.values())
            if total_pips == 0:
                logger.warning("No colored mana symbols found in casting costs")
                return
            
            logger.info("Color Pip Distribution:")
            for color in MANA_COLORS:
                count = pip_counts[color]
                if count > 0:
                    percentage = percentages[color]
                    print(f"{color}: {count} pips ({percentage:.1f}%)")
            print()
            logger.info(f"Total colored pips: {total_pips}")
            # Filter out zero percentages
            non_zero_percentages = {color: pct for color, pct in percentages.items() if pct > 0}
            logger.info(f"Distribution ratios: {non_zero_percentages}\n")
            
        except ManaPipError as e:
            logger.error(f"Mana pip analysis failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in pip analysis: {e}")
            raise ManaPipError("Failed to analyze mana pips", {"error": str(e)})
        
    def get_cmc(self):
        """Calculate average converted mana cost of non-land cards."""
        logger.info('Calculating average mana value of non-land cards.')
        
        try:
            # Filter non-land cards
            non_land = self.card_library[
                ~self.card_library['Card Type'].str.contains('Land')
            ].copy()
            
            if non_land.empty:
                logger.warning("No non-land cards found")
                self.cmc = 0.0
            else:
                total_cmc = non_land['Mana Value'].sum()
                self.cmc = round(total_cmc / len(non_land), 2)
            
            self.commander_dict.update({'CMC': float(self.cmc)})
            logger.info(f"Average CMC: {self.cmc}")
            
        except Exception as e:
            logger.error(f"Error calculating CMC: {e}")
            self.cmc = 0.0
    
    def weight_by_theme(self, tag: str, ideal: int = 1, weight: float = 1.0, df: Optional[pd.DataFrame] = None) -> None:
        """Add cards with specific tag up to weighted ideal count.

        Args:
            tag: Theme tag to filter cards by
            ideal: Target number of cards to add
            weight: Theme weight factor (0.0-1.0)
            df: Source DataFrame to filter cards from

        Raises:
            ThemeWeightingError: If weight calculation fails
            ThemePoolError: If card pool is empty or insufficient
        """
        try:
            # Calculate target card count using weight and safety multiplier
            target_count = math.ceil(ideal * weight * THEME_WEIGHT_MULTIPLIER)
            logger.info(f'Finding {target_count} cards with the "{tag}" tag...')

            # Handle Kindred theme special case
            tags = [tag, 'Kindred Support'] if 'Kindred' in tag else [tag]

            # Calculate initial pool size
            pool_size = builder_utils.calculate_weighted_pool_size(target_count, weight)

            # Filter cards by theme
            if df is None:
                raise ThemePoolError(f"No source DataFrame provided for theme {tag}")
            
            tag_df = builder_utils.filter_theme_cards(df, tags, pool_size)
            if tag_df.empty:
                raise ThemePoolError(f"No cards found for theme {tag}")

            # Select cards considering price and duplicates
            selected_cards = builder_utils.select_weighted_cards(
                tag_df,
                target_count,
                self.price_checker if use_scrython else None,
                self.max_card_price if hasattr(self, 'max_card_price') else None
            )

            # Process selected cards
            cards_added = []
            for card in selected_cards:
                # Handle multiple copy cards
                if card['name'] in MULTIPLE_COPY_CARDS:
                    copies = {
                        'Nazgûl': 9,
                        'Seven Dwarves': 7
                    }.get(card['name'], target_count - len(cards_added))
                    
                    for _ in range(copies):
                        cards_added.append(card)
                        
                # Handle regular cards
                elif card['name'] not in self.card_library['Card Name'].values:
                    cards_added.append(card)
                else:
                    logger.warning(f"{card['name']} already in Library, skipping it.")

            # Add selected cards to library
            for card in cards_added:
                self.add_card(
                    card['name'],
                    card['type'],
                    card['manaCost'],
                    card['manaValue'],
                    card.get('creatureTypes'),
                    card['themeTags']
                )

            # Update DataFrames
            used_cards = {card['name'] for card in selected_cards}
            self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(used_cards)]

            logger.info(f'Added {len(cards_added)} {tag} cards')
            for card in cards_added:
                print(card['name'])

        except (ThemeWeightingError, ThemePoolError) as e:
            logger.error(f"Error in weight_by_theme: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in weight_by_theme: {e}")
            raise ThemeWeightingError(f"Failed to process theme {tag}: {str(e)}")
    
    def add_by_tags(self, tag, ideal_value=1, df=None, ignore_existing=False):
        """Add cards with specific tag up to ideal_value count.
        Args:
            tag: The theme tag to filter cards by
            ideal_value: Target number of cards to add
            df: DataFrame containing candidate cards

        Raises:
            ThemeTagError: If there are issues with tag processing or card selection
        """
        try:
            # Count existing cards with target tag
            print()
            if not ignore_existing:
                existing_count = len(self.card_library[self.card_library['Themes'].apply(lambda x: x is not None and tag in x)])
                remaining_slots = max(0, ideal_value - existing_count + 1)
            else:
                existing_count = 0
                remaining_slots = max(0, ideal_value - existing_count + 1)

            if remaining_slots == 0:
                if not ignore_existing:
                    logger.info(f'Already have {existing_count} cards with tag "{tag}" - no additional cards needed')
                    return
                else:
                    logger.info(f'Already have {ideal_value} cards with tag "{tag}" - no additional cards needed')
                    return

            logger.info(f'Finding {remaining_slots} additional cards with the "{tag}" tag...')

            # Filter cards with the given tag
            skip_creatures = self.creature_cards > self.ideal_creature_count * 1.1
            tag_df = df.copy()
            tag_df.sort_values(by='edhrecRank', inplace=True)
            tag_df = tag_df[tag_df['themeTags'].apply(lambda x: x is not None and tag in x)]

            # Calculate initial pool size using THEME_POOL_SIZE_MULTIPLIER
            pool_size = int(remaining_slots * THEME_POOL_SIZE_MULTIPLIER)
            tag_df = tag_df.head(pool_size)

            # Convert to list of card dictionaries with priority scores
            card_pool = []
            for _, row in tag_df.iterrows():
                theme_tags = row['themeTags'] if row['themeTags'] is not None else []
                priority = builder_utils.calculate_theme_priority(theme_tags, self.themes, THEME_PRIORITY_BONUS)
                card_pool.append({
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue'],
                    'creatureTypes': row['creatureTypes'],
                    'themeTags': theme_tags,
                    'priority': priority
                })

            # Sort card pool by priority score
            card_pool.sort(key=lambda x: x['priority'], reverse=True)

            # Select cards up to remaining slots
            cards_to_add = []
            for card in card_pool:
                if len(cards_to_add) >= remaining_slots:
                    break

                # Check price constraints if enabled
                if use_scrython and hasattr(self, 'max_card_price') and self.max_card_price:
                    price = self.price_checker.get_card_price(card['name'])
                    if price > self.max_card_price * 1.1:
                        continue

                # Handle multiple-copy cards
                if card['name'] in MULTIPLE_COPY_CARDS:
                    existing_copies = len(self.card_library[self.card_library['Card Name'] == card['name']])
                    if existing_copies < ideal_value:
                        cards_to_add.append(card)
                    continue

                # Add new cards if not already in library
                if card['name'] not in self.card_library['Card Name'].values:
                    if 'Creature' in card['type'] and skip_creatures:
                        continue
                    else:
                        if 'Creature' in card['type']:
                            self.creature_cards += 1
                            skip_creatures = self.creature_cards > self.ideal_creature_count * 1.1
                        cards_to_add.append(card)

            # Add selected cards to library
            for card in cards_to_add:
                if len(self.card_library) < 100:
                    self.add_card(card['name'], card['type'],
                                card['manaCost'], card['manaValue'],
                                card['creatureTypes'], card['themeTags'])
                else:
                    break

            # Update DataFrames
            card_pool_names = [item['name'] for item in card_pool]
            self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(card_pool_names)]

            logger.info(f'Added {len(cards_to_add)} {tag} cards (total with tag: {existing_count + len(cards_to_add)})')
            for card in cards_to_add:
                print(card['name'])

        except Exception as e:
            raise ThemeTagError(f"Error processing tag '{tag}'", {"error": str(e)})
        
    def add_creatures(self):
        """
        Add creatures to the deck based on themes and weights.
        
        This method processes the primary, secondary, and tertiary themes to add
        creatures proportionally according to their weights. The total number of
        creatures added will approximate the ideal_creature_count.
        
        The method follows this process:
        1. Process hidden theme if present
        2. Process primary theme
        3. Process secondary theme if present
        4. Process tertiary theme if present

        Each theme is weighted according to its importance:
        - Hidden theme: Highest priority if present
        - Primary theme: Main focus
        - Secondary theme: Supporting focus
        - Tertiary theme: Minor focus

        Args:
            None

        Returns:
            None

        Raises:
            ThemeWeightingError: If there are issues with theme weight calculations
            ThemePoolError: If the card pool for a theme is insufficient
            Exception: For any other unexpected errors during creature addition

        Note:
            The method uses error handling to ensure the deck building process
            continues even if a particular theme encounters issues.
        """
        print()
        logger.info(f'Adding creatures to deck based on the ideal creature count of {self.ideal_creature_count}...')
        
        try:
            if self.hidden_theme:
                print()
                logger.info(f'Processing Hidden theme: {self.hidden_theme}')
                self.weight_by_theme(self.hidden_theme, self.ideal_creature_count, self.hidden_weight, self.creature_df)
            
            logger.info(f'Processing primary theme: {self.primary_theme}')
            self.weight_by_theme(self.primary_theme, self.ideal_creature_count, self.primary_weight, self.creature_df)
            
            if self.secondary_theme:
                print()
                logger.info(f'Processing secondary theme: {self.secondary_theme}')
                self.weight_by_theme(self.secondary_theme, self.ideal_creature_count, self.secondary_weight, self.creature_df)
            
            if self.tertiary_theme:
                print()
                logger.info(f'Processing tertiary theme: {self.tertiary_theme}')
                self.weight_by_theme(self.tertiary_theme, self.ideal_creature_count, self.tertiary_weight, self.creature_df)
                
        except Exception as e:
            logger.error(f"Error while adding creatures: {e}")
        finally:
            self.organize_library()
    
    def add_ramp(self):
        """Add ramp cards to the deck based on ideal ramp count.

        This method adds three categories of ramp cards:
        1. Mana rocks (artifacts that produce mana) - ~1/3 of ideal ramp count
        2. Mana dorks (creatures that produce mana) - ~1/4 of ideal ramp count
        3. General ramp spells - remaining portion of ideal ramp count

        The method uses the add_by_tags() helper to add cards from each category
        while respecting the deck's themes and color identity.

        Args:
            None

        Returns:
            None

        Raises:
            ThemeTagError: If there are issues adding cards with ramp-related tags
        """
        try:
            self.add_by_tags('Mana Rock', math.ceil(self.ideal_ramp / 3), self.noncreature_df)
            self.add_by_tags('Mana Dork', math.ceil(self.ideal_ramp / 4), self.creature_df)
            self.add_by_tags('Ramp', self.ideal_ramp, self.noncreature_df)
        except Exception as e:
            logger.error(f"Error while adding Ramp: {e}")
            
    def add_interaction(self):
        """Add interaction cards to the deck for removal and protection.

        This method adds two categories of interaction cards:
        1. Removal spells based on ideal_removal count
        2. Protection spells based on ideal_protection count

        Cards are selected from non-planeswalker cards to ensure appropriate
        interaction types are added.

        Args:
            None

        Returns:
            None

        Raises:
            ThemeTagError: If there are issues adding cards with interaction-related tags
        """
        try:
            self.add_by_tags('Removal', self.ideal_removal, self.nonplaneswalker_df)
            self.add_by_tags('Protection', self.ideal_protection, self.nonplaneswalker_df)
        except Exception as e:
            logger.error(f"Error while adding Interaction: {e}")
        
    def add_board_wipes(self):
        """Add board wipe cards to the deck.

        This method adds board wipe cards based on the ideal_wipes count.
        Board wipes are selected from the full card pool to include all possible
        options across different card types.

        Args:
            None

        Returns:
            None

        Raises:
            ThemeTagError: If there are issues adding cards with the 'Board Wipes' tag
        """
        try:
            self.add_by_tags('Board Wipes', self.ideal_wipes, self.full_df)
        except Exception as e:
            logger.error(f"Error while adding Board Wipes: {e}")
        
    def add_card_advantage(self):
        """Add card advantage effects to the deck.

        This method adds two categories of card draw effects:
        1. Conditional draw effects (20% of ideal_card_advantage)
           - Cards that draw based on specific conditions or triggers
        2. Unconditional draw effects (80% of ideal_card_advantage)
           - Cards that provide straightforward card draw

        Cards are selected from appropriate pools while avoiding planeswalkers
        for unconditional draw effects.

        Args:
            None

        Returns:
            None

        Raises:
            ThemeTagError: If there are issues adding cards with draw-related tags
        """
        try:
            self.add_by_tags('Conditional Draw', math.ceil(self.ideal_card_advantage * 0.2), self.full_df)
            self.add_by_tags('Unconditional Draw', math.ceil(self.ideal_card_advantage * 0.8), self.nonplaneswalker_df)
        except Exception as e:
            logger.error(f"Error while adding Card Draw: {e}")
    
    def fill_out_deck(self):
        """Fill out the deck to 100 cards with theme-appropriate cards.

        This method completes the deck by adding remaining cards up to the 100-card
        requirement, prioritizing cards that match the deck's themes. The process
        follows these steps:

        1. Calculate how many cards are needed to reach 100
        2. Add cards from each theme with weighted distribution:
           - Hidden theme (if present)
           - Tertiary theme (20% weight if present)
           - Secondary theme (30% weight if present)
           - Primary theme (50% weight)

        The method includes safeguards:
        - Maximum attempts limit to prevent infinite loops
        - Timeout to prevent excessive runtime
        - Progress tracking to break early if insufficient progress

        Args:
            None

        Returns:
            None

        Raises:
            ThemeTagError: If there are issues adding cards with specific theme tags
            TimeoutError: If the process exceeds the maximum allowed time

        Note:
            If the deck cannot be filled to 100 cards, a warning message is logged
            indicating manual additions may be needed.
        """
        print()
        logger.info('Filling out the Library to 100 with cards fitting the themes.')
        cards_needed = 100 - len(self.card_library)
        if cards_needed <= 0:
            return
        
        logger.info(f"Need to add {cards_needed} more cards")
        
        # Define maximum attempts and timeout
        MAX_ATTEMPTS = max(20, cards_needed * 2)
        MAX_TIME = 60  # Maximum time in seconds
        start_time = time.time()
        attempts = 0
        
        while len(self.card_library) < 100 and attempts < MAX_ATTEMPTS:
            # Check timeout
            if time.time() - start_time > MAX_TIME:
                logger.error("Timeout reached while filling deck")
                break
                
            initial_count = len(self.card_library)
            remaining = 100 - len(self.card_library)
            
            # Adjust self.weights based on remaining cards needed
            weight_multiplier = remaining / cards_needed
            
            try:
                # Add cards from each theme with adjusted self.weights
                if self.hidden_theme and remaining > 0:
                    self.add_by_tags(self.hidden_theme, 
                        math.ceil(weight_multiplier),
                        self.full_df,
                        True)
                    
                    # Adjust self.weights based on remaining cards needed
                    remaining = 100 - len(self.card_library)
                    weight_multiplier = remaining / cards_needed
                if self.tertiary_theme and remaining > 0:
                    self.add_by_tags(self.tertiary_theme, 
                        math.ceil(weight_multiplier * 0.2),
                        self.noncreature_df,
                        True)
                    
                if self.secondary_theme and remaining > 0:
                    self.add_by_tags(self.secondary_theme, 
                        math.ceil(weight_multiplier * 0.3),
                        self.noncreature_df,
                        True)
                if remaining > 0:
                    self.add_by_tags(self.primary_theme, 
                        math.ceil(weight_multiplier * 0.5),
                        self.noncreature_df,
                        True)
                
                # Check if we made progress
                if len(self.card_library) == initial_count:
                    attempts += 1
                    if attempts % 5 == 0:
                        print()
                        logger.warning(f"Made {attempts} attempts, still need {100 - len(self.card_library)} cards")
                        
                # Break early if we're stuck
                if attempts >= MAX_ATTEMPTS / 2 and len(self.card_library) < initial_count + (cards_needed / 4):
                    print()
                    logger.warning("Insufficient progress being made, breaking early")
                    break
                    
            except Exception as e:
                print()
                logger.error(f"Error while adding cards: {e}")
                attempts += 1
        
        final_count = len(self.card_library)
        if final_count < 100:
            message = f"\nWARNING: Deck is incomplete with {final_count} cards. Manual additions may be needed."
            print()
            logger.warning(message)
        else:
            print()
            logger.info(f"Successfully filled deck to {final_count} cards in {attempts} attempts")
            
def main():
    """Main entry point for deck builder application."""
    build_deck = DeckBuilder()
    build_deck.determine_commander()
    pprint.pprint(build_deck.commander_dict, sort_dicts=False)

if __name__ == '__main__':
    main()