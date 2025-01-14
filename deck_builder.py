from __future__ import annotations

import logging
import math
import numpy as np
import random
import time
from functools import lru_cache
from typing import Dict, List, Optional, Union

import inquirer.prompt # type: ignore
import keyboard # type: ignore 
import pandas as pd # type: ignore
import pprint # type: ignore
from fuzzywuzzy import process # type: ignore

from settings import (
    BASIC_LANDS, CARD_TYPES, CSV_DIRECTORY, multiple_copy_cards,
    COMMANDER_CSV_PATH, FUZZY_MATCH_THRESHOLD, MAX_FUZZY_CHOICES, 
    COMMANDER_POWER_DEFAULT, COMMANDER_TOUGHNESS_DEFAULT, COMMANDER_MANA_COST_DEFAULT,
    COMMANDER_MANA_VALUE_DEFAULT, COMMANDER_TYPE_DEFAULT, COMMANDER_TEXT_DEFAULT, 
    COMMANDER_COLOR_IDENTITY_DEFAULT, COMMANDER_COLORS_DEFAULT, COMMANDER_TAGS_DEFAULT, 
    COMMANDER_THEMES_DEFAULT, COMMANDER_CREATURE_TYPES_DEFAULT,
    CSV_READ_TIMEOUT, CSV_PROCESSING_BATCH_SIZE, CSV_VALIDATION_RULES, CSV_REQUIRED_COLUMNS
)
import builder_utils 
import setup_utils
from setup import determine_commanders
from input_handler import InputHandler
from exceptions import (
    CommanderColorError,
    CommanderLoadError,
    CommanderSelectionError, 
    CommanderValidationError,
    CSVError,
    CSVReadError,
    CSVTimeoutError,
    CSVValidationError,
    DataFrameValidationError,
    DeckBuilderError,
    EmptyDataFrameError,
    EmptyInputError, 
    InvalidNumberError,
    InvalidQuestionTypeError,
    MaxAttemptsError,
    PriceAPIError,
    PriceLimitError, 
    PriceTimeoutError,
    PriceValidationError
)
from type_definitions import (
    CardDict,
    CommanderDict,
    CardLibraryDF,
    CommanderDF,
    LandDF,
    ArtifactDF,
    CreatureDF,
    NonCreatureDF)

# Try to import scrython and price_checker
try:
    import scrython # type: ignore
    from price_check import PriceChecker
    use_scrython = True
except ImportError:
    scrython = None
    PriceChecker = None
    use_scrython = False
    logging.warning("Scrython is not installed. Price checking features will be unavailable."
                    )

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 50)

"""
Basic deck builder, primarily intended for building Kindred decks.
Logic for other themes (such as Spellslinger or Wheels), is added.
I plan to also implement having it recommend a commander or themes.

Currently, the script will ask questions to determine number of 
creatures, lands, interaction, ramp, etc... then add cards and 
adjust from there.

Land spread will ideally be handled based on pips and some adjustment
is planned based on mana curve and ramp added.
"""

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
            'Commander': pd.Series(dtype='bool')
        })
        
        # Initialize component dataframes
        self.commander_df: CommanderDF = pd.DataFrame()
        self.land_df: LandDF = pd.DataFrame()
        self.artifact_df: ArtifactDF = pd.DataFrame()
        self.creature_df: CreatureDF = pd.DataFrame()
        self.noncreature_df: NonCreatureDF = pd.DataFrame()
        
        # Initialize other attributes with type hints
        self.commander_info: Dict = {}
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
        self.commander_dict = {
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
            'Themes': self.themes
        }
        self.add_card(self.commander, self.commander_type,
                      self.commander_mana_cost, self.commander_mana_value, True)

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
            self.card_library.to_csv(f'{CSV_DIRECTORY}/test_deck_presort.csv', index=False)
            self.organize_library()
            self.card_library.to_csv(f'{CSV_DIRECTORY}/test_deck_preconcat.csv', index=False)
            
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
            self.card_library.to_csv(f'{CSV_DIRECTORY}/test_deck_done.csv', index=False)
            self.full_df.to_csv(f'{CSV_DIRECTORY}/test_all_after_done.csv', index=False)
            
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
        from settings import OTHER_COLOR_MAP
        
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
            
            # Process in batches
            processed_dfs = []
            for i in range(0, len(df), CSV_PROCESSING_BATCH_SIZE):
                batch = df.iloc[i:i + CSV_PROCESSING_BATCH_SIZE]
                processed_batch = setup_utils.process_card_dataframe(batch, skip_availability_checks=True)
                processed_dfs.append(processed_batch)
            
            df = pd.concat(processed_dfs, ignore_index=True)
            
            # Validate data rules
            for col, rules in CSV_VALIDATION_RULES.items():
                if rules.get('required', False) and df[col].isnull().any():
                    raise CSVValidationError(f"Missing required values in column: {col}")
                if 'type' in rules:
                    expected_type = rules['type']
                    actual_type = df[col].dtype.name
                    if expected_type == 'str' and not actual_type in ['object', 'string']:
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
            for file in self.files_to_load:
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
            
            # Create specialized frames
            self.artifact_df = df[df['type'].str.contains('Artifact')].copy()
            self.battle_df = df[df['type'].str.contains('Battle')].copy()
            self.creature_df = df[df['type'].str.contains('Creature')].copy()
            self.noncreature_df = df[~df['type'].str.contains('Creature')].copy()
            self.enchantment_df = df[df['type'].str.contains('Enchantment')].copy()
            self.instant_df = df[df['type'].str.contains('Instant')].copy()
            self.planeswalker_df = df[df['type'].str.contains('Planeswalker')].copy()
            self.sorcery_df = df[df['type'].str.contains('Sorcery')].copy()
            
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
            self.full_df.sort_values(by='edhrecRank', inplace=True)
            
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
    def determine_themes(self):
        themes = self.commander_tags
        print('Your commander deck will likely have a number of viable themes, but you\'ll want to narrow it down for focus.\n'
                'This will go through the process of choosing up to three themes for the deck.\n')
        while True:
            # Choose a primary theme
            print('Choose a primary theme for your commander deck.\n'
                'This will be the "focus" of the deck, in a kindred deck this will typically be a creature type for example.')
            choice = self.input_handler.questionnaire('Choice', choices_list=themes)
            self.primary_theme = choice
            weights_default = {
                'primary': 1.0,
                'secondary': 0.0,
                'tertiary': 0.0,
                'hidden': 0.0
                }
            weights = weights_default.copy()
            themes.remove(choice)
            themes.append('Stop Here')
            self.primary_weight = weights['primary']

            secondary_theme_chosen = False
            tertiary_theme_chosen = False
            self.hidden_theme = False

            while not secondary_theme_chosen:
                # Secondary theme
                print('Choose a secondary theme for your commander deck.\n'
                    'This will typically be a secondary focus, like card draw for Spellslinger, or +1/+1 counters for Aggro.')
                choice = self.input_handler.questionnaire('Choice', choices_list=themes)
                while True:
                    if choice == 'Stop Here':
                        logger.warning('You\'ve only selected one theme, are you sure you want to stop?\n')
                        confirm_done = self.input_handler.questionnaire('Confirm', False)
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
                        weights = weights_default.copy() # primary = 1.0, secondary = 0.0, tertiary = 0.0
                        self.secondary_theme = choice
                        themes.remove(choice)
                        secondary_theme_chosen = True
                        # Set weights for primary/secondary themes
                        if 'Kindred' in self.primary_theme and 'Kindred' not in self.secondary_theme:
                            weights['primary'] -= 0.1 # 0.8
                            weights['secondary'] += 0.1 # 0.1
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme:
                            weights['primary'] -= 0.7 # 0.7
                            weights['secondary'] += 0.3 # 0.3
                        else:
                            weights['primary'] -= 0.4 # 0.6
                            weights['secondary'] += 0.4 # 0.4
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        break

            while not tertiary_theme_chosen:
                # Tertiary theme
                print('Choose a tertiary theme for your commander deck.\n'
                    'This will typically be a tertiary focus, or just something else to do that your commander is good at.')
                choice = self.input_handler.questionnaire('Choice', choices_list=themes)
                while True:
                    if choice == 'Stop Here':
                        logger.warning('You\'ve only selected two themes, are you sure you want to stop?\n')
                        confirm_done = self.input_handler.questionnaire('Confirm', False)
                        if confirm_done:
                            tertiary_theme_chosen = True
                            self.tertiary_theme = False
                            themes.remove(choice)
                            break
                        else:
                            pass

                    else:
                        weights = weights_default.copy() # primary = 1.0, secondary = 0.0, tertiary = 0.0
                        self.tertiary_theme = choice
                        tertiary_theme_chosen = True
                        
                        # Set weights for themes:
                        if 'Kindred' in self.primary_theme and 'Kindred' not in self.secondary_theme and 'Kindred' not in self.tertiary_theme:
                            weights['primary'] -= 0.2 # 0.8
                            weights['secondary'] += 0.1 # 0.1
                            weights['tertiary'] += 0.1 # 0.1
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme and 'Kindred' not in self.tertiary_theme:
                            weights['primary'] -= 0.3 # 0.7
                            weights['secondary'] += 0.2 # 0.2
                            weights['tertiary'] += 0.1 # 0.1
                        elif 'Kindred' in self.primary_theme and 'Kindred' in self.secondary_theme and 'Kindred' in self.tertiary_theme:
                            weights['primary'] -= 0.5 # 0.5
                            weights['secondary'] += 0.3 # 0.3
                            weights['tertiary'] += 0.2 # 0.2
                        else:
                            weights['primary'] -= 0.6 # 0.4
                            weights['secondary'] += 0.3 # 0.3
                            weights['tertiary'] += 0.3 # 0.3
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        break
            
            self.themes = [self.primary_theme]
            if not self.secondary_theme:
                pass
            else:
                self.themes.append(self.secondary_theme)
            if not self.tertiary_theme:
                pass
            else:
                self.themes.append(self.tertiary_theme)
                
            """
            Setting 'Hidden' themes for multiple-copy cards, such as 'Hare Apparent' or 'Shadowborn Apostle'.
            These are themes that will be prompted for under specific conditions, such as a matching Kindred theme or a matching color combination and Spellslinger theme for example.
            Typically a hidden theme won't come up, but if it does, it will take priority with theme weights to ensure a decent number of the specialty cards are added.
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
                    choice = self.input_handler.questionnaire('Confirm', False)
                    if choice:
                        self.hidden_theme = theme_cards[i]
                        self.themes.append(self.hidden_theme)
                        weights['primary'] = round(weights['primary'] / 3, 2)
                        weights['secondary'] = round(weights['secondary'] / 2, 2)
                        weights['tertiary'] = weights['tertiary'] 
                        weights['hidden'] = round(1.0 - weights['primary'] - weights['secondary'] - weights['tertiary'], 2)
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        self.hidden_weight = weights['hidden']
                    else:
                        continue
                    
                elif (hidden_themes[i] in self.themes
                      and hidden_themes[i] == 'Rat Kindred'
                      and color[i] in self.colors):
                    logger.info(f'Looks like you\'re making a {hidden_themes[i]} deck, would you like it to be a {theme_cards[i][0]} or {theme_cards[i][1]} deck?')
                    choice = self.input_handler.questionnaire('Confirm', False)
                    if choice:
                        print('Which one?')
                        choice = self.input_handler.questionnaire('Choice', choices_list=theme_cards[i])
                        if choice:
                            self.hidden_theme = choice
                            self.themes.append(self.hidden_theme)
                            weights['primary'] = round(weights['primary'] / 3, 2)
                            weights['secondary'] = round(weights['secondary'] / 2, 2)
                            weights['tertiary'] = weights['tertiary'] 
                            weights['hidden'] = round(1.0 - weights['primary'] - weights['secondary'] - weights['tertiary'], 2)
                            self.primary_weight = weights['primary']
                            self.secondary_weight = weights['secondary']
                            self.tertiary_weight = weights['tertiary']
                            self.hidden_weight = weights['hidden']
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
                    choice = self.input_handler.questionnaire('Confirm', False)
                    if choice:
                        self.hidden_theme = theme_cards[i]
                        self.themes.append(self.hidden_theme)
                        weights['primary'] = round(weights['primary'] / 3, 2)
                        weights['secondary'] = round(weights['secondary'] / 2, 2)
                        weights['tertiary'] = weights['tertiary'] 
                        weights['hidden'] = round(1.0 - weights['primary'] - weights['secondary'] - weights['tertiary'], 2)
                        self.primary_weight = weights['primary']
                        self.secondary_weight = weights['secondary']
                        self.tertiary_weight = weights['tertiary']
                        self.hidden_weight = weights['hidden']
                    else:
                        continue
            
            break
    
    def determine_ideals(self):
        # "Free" slots that can be used for anything that isn't the ideals
        self.free_slots = 99
        
        if use_scrython:
            print('Would you like to set an intended max price of the deck?\n'
                  'There will be some leeway of ~10%, with a couple alternative options provided.')
            choice = self.input_handler.questionnaire('Confirm', False)
            if choice:
                print('What would you like the max price to be?')
                max_deck_price = float(self.input_handler.questionnaire('Number', 400))
                self.price_checker.max_deck_price = max_deck_price
                new_line()
            else:
                new_line()
            
            print('Would you like to set a max price per card?\n'
                  'There will be some leeway of ~10% when choosing cards and you can choose to keep it or not.')
            choice = self.input_handler.questionnaire('Confirm', False)
            if choice:
                print('What would you like the max price to be?')
                answer = float(self.input_handler.questionnaire('Number', 20))
                self.price_checker.max_card_price = answer
                new_line()
            else:
                new_line()
        
        # Determine ramp
        print('How many pieces of ramp would you like to include?\n'
              'This includes mana rocks, mana dorks, and land ramp spells.\n'
              'A good baseline is 8-12 pieces, scaling up with higher average CMC\n'
              'Default: 8')
        answer = self.input_handler.questionnaire('Number', 8)
        self.ideal_ramp = int(answer)
        self.free_slots -= self.ideal_ramp
        new_line()
        
        # Determine ideal land count
        print('How many total lands would you like to include?\n'
              'Before ramp is considered, 38-40 lands is typical for most decks.\n'
              "For landfall decks, consider starting at 40 lands before ramp.\n"
              'As a guideline, each mana source from ramp can reduce land count by ~1.\n'
              'Default: 35')
        answer = self.input_handler.questionnaire('Number', 35)
        self.ideal_land_count = int(answer)
        self.free_slots -= self.ideal_land_count
        new_line()
        
        # Determine minimum basics to have
        print('How many basic lands would you like to have at minimum?\n'
              'This can vary widely depending on your commander, colors in color identity, and what you want to do.\n'
              'Some decks may be fine with as low as 10, others may want 25.\n'
              'Default: 20')
        answer = self.input_handler.questionnaire('Number', 20)
        self.min_basics = int(answer)
        new_line()
        
        # Determine ideal creature count
        print('How many creatures would you like to include?\n'
              'Something like 25-30 would be a good starting point.\n'
              "If you're going for a kindred theme, going past 30 is likely normal.\n"
              "Also be sure to take into account token generation, but remember you'll want enough to stay safe\n"
              'Default: 25')
        answer = self.input_handler.questionnaire('Number', 25)
        self.ideal_creature_count = int(answer)
        self.free_slots -= self.ideal_creature_count
        new_line()
        
        # Determine spot/targetted removal
        print('How many spot removal pieces would you like to include?\n'
              'A good starting point is about 8-12 pieces of spot removal.\n'
              'Counterspells can be considered proactive removal and protection.\n'
              'If you\'re going spellslinger, more would be a good idea as you might have less cretaures.\n'
              'Default: 10')
        answer = self.input_handler.questionnaire('Number', 10)
        self.ideal_removal = int(answer)
        self.free_slots -= self.ideal_removal
        new_line()

        # Determine board wipes
        print('How many board wipes would you like to include?\n'
              'Somewhere around 2-3 is good to help eliminate threats, but also prevent the game from running long\n.'
              'This can include damaging wipes like "Blasphemous Act" or toughness reduction like "Meathook Massacre".\n'
              'Default: 2')
        answer = self.input_handler.questionnaire('Number', 2)
        self.ideal_wipes = int(answer)
        self.free_slots -= self.ideal_wipes
        new_line()
        
        # Determine card advantage
        print('How many pieces of card advantage would you like to include?\n'
              '10 pieces of card advantage is good, up to 14 is better.\n'
              'Try to have a majority of it be non-conditional, and only have a couple of "Rhystic Study" style effects.\n'
              'Default: 10')
        answer = self.input_handler.questionnaire('Number', 10)
        self.ideal_card_advantage = int(answer)
        self.free_slots -= self.ideal_card_advantage
        new_line()
        
        # Determine how many protection spells
        print('How many protection spells would you like to include?\n'
              'This can be individual protection, board protection, fogs, or similar effects.\n'
              'Things that grant indestructible, hexproof, phase out, or even just counterspells.\n'
              'It\'s recommended to have 5 to 15, depending on your commander and preferred strategy.\n'
              'Default: 8')
        answer = self.input_handler.questionnaire('Number', 8)
        self.ideal_protection = int(answer)
        self.free_slots -= self.ideal_protection
        new_line()
        
        print(f'Free slots that aren\'t part of the ideals: {self.free_slots}')
        print('Keep in mind that many of the ideals can also cover multiple roles, but this will give a baseline POV.')
    
    def add_card(self, card: str, card_type: str, mana_cost: str, mana_value: int, is_commander: bool = False) -> None:
        """Add a card to the deck library with price checking if enabled.

        Args:
            card (str): Name of the card to add
            card_type (str): Type of the card (e.g., 'Creature', 'Instant')
            mana_cost (str): Mana cost string representation
            mana_value (int): Converted mana cost/mana value
            is_commander (bool, optional): Whether this card is the commander. Defaults to False.

        Returns:
            None

        Raises:
            PriceLimitError: If card price exceeds maximum allowed price
            PriceAPIError: If there is an error fetching the price
            PriceTimeoutError: If the price check times out
            PriceValidationError: If the price data is invalid
        """
        multiple_copies = BASIC_LANDS + multiple_copy_cards

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
        card_entry = [card, card_type, mana_cost, mana_value, is_commander]

        # Add to library
        self.card_library.loc[len(self.card_library)] = card_entry

        logger.debug(f"Added {card} to deck library")
    
    def organize_library(self):
        # Initialize counters dictionary dynamically from CARD_TYPES including Kindred
        all_types = CARD_TYPES + ['Kindred'] if 'Kindred' not in CARD_TYPES else CARD_TYPES
        card_counters = {card_type: 0 for card_type in all_types}

        # Count cards by type
        for card_type in CARD_TYPES:
            type_df = self.card_library[self.card_library['Card Type'].apply(lambda x: card_type in x)]
            card_counters[card_type] = len(type_df)

        # Assign counts to instance variables
        self.artifact_cards = card_counters['Artifact']
        self.battle_cards = card_counters['Battle']
        self.creature_cards = card_counters['Creature']
        self.enchantment_cards = card_counters['Enchantment']
        self.instant_cards = card_counters['Instant']
        self.kindred_cards = card_counters.get('Kindred', 0)  # Use get() with default value
        self.land_cards = card_counters['Land']
        self.planeswalker_cards = card_counters['Planeswalker']
        self.sorcery_cards = card_counters['Sorcery']
    
    def sort_library(self):
        self.card_library['Sort Order'] = pd.Series(dtype='str')
        for index, row in self.card_library.iterrows():
            for card_type in CARD_TYPES:
                if card_type in row['Card Type']:
                    if row['Sort Order'] == 'Creature':
                        continue
                    if row['Sort Order'] != 'Creature':
                        self.card_library.loc[index, 'Sort Order'] = card_type

        custom_order = ['Planeswalker', 'Battle', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land']
        self.card_library['Sort Order'] = pd.Categorical(
            self.card_library['Sort Order'], 
            categories=custom_order, 
            ordered=True
        )
        self.card_library = (self.card_library
            .sort_values(by=['Sort Order', 'Card Name'], ascending=[True, True])
            .drop(columns=['Sort Order'])
            .reset_index(drop=True)
        )

    def commander_to_top(self) -> None:
        """Move commander card to the top of the library while preserving commander status."""
        try:
            commander_row = self.card_library[self.card_library['Commander']].copy()
            if commander_row.empty:
                logger.warning("No commander found in library")
                return
            
            self.card_library = self.card_library[~self.card_library['Commander']]
            
            self.card_library = pd.concat([commander_row, self.card_library], ignore_index=True)
            
            commander_name = commander_row['Card Name'].iloc[0]
            logger.info(f"Successfully moved commander '{commander_name}' to top")
        except Exception as e:
            logger.error(f"Error moving commander to top: {str(e)}")
    def concatenate_duplicates(self):
        """Handle duplicate cards in the library while maintaining data integrity."""
        duplicate_lists = BASIC_LANDS + multiple_copy_cards
        
        # Create a count column for duplicates
        self.card_library['Card Count'] = 1
        
        for duplicate in duplicate_lists:
            mask = self.card_library['Card Name'] == duplicate
            count = mask.sum()
            
            if count > 0:
                logger.info(f'Found {count} copies of {duplicate}')
                
                # Keep first occurrence with updated count
                first_idx = mask.idxmax()
                self.card_library.loc[first_idx, 'Card Count'] = count
                
                # Drop other occurrences
                self.card_library = self.card_library.drop(
                    self.card_library[mask & (self.card_library.index != first_idx)].index
                )
        
        # Update card names with counts where applicable
        mask = self.card_library['Card Count'] > 1
        self.card_library.loc[mask, 'Card Name'] = (
            self.card_library.loc[mask, 'Card Name'] + 
            ' x ' + 
            self.card_library.loc[mask, 'Card Count'].astype(str)
        )
        
        # Clean up
        self.card_library = self.card_library.drop(columns=['Card Count'])
        self.card_library = self.card_library.reset_index(drop=True)
    def drop_card(self, dataframe: pd.DataFrame, index: int) -> None:
        """Safely drop a card from the dataframe by index.
        
        Args:
            dataframe: DataFrame to modify
            index: Index to drop
        """
        try:
            dataframe.drop(index, inplace=True)
        except KeyError:
            logger.warning(f"Attempted to drop non-existent index {index}")
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
        MAX_ADJUSTMENT_ATTEMPTS = 10
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
        base_basics = self.ideal_land_count - 10  # Reserve 10 slots for non-basic lands
        basics_per_color = base_basics // len(self.colors)
        remaining_basics = base_basics % len(self.colors)

        color_to_basic = {
            'W': 'Plains',
            'U': 'Island', 
            'B': 'Swamp',
            'R': 'Mountain',
            'G': 'Forest',
            'COLORLESS': 'Wastes'
        }

        if 'Snow' in self.commander_tags:
            color_to_basic = {
            'W': 'Snow-Covered Plains',
            'U': 'Snow-Covered Island', 
            'B': 'Snow-Covered Swamp',
            'R': 'Snow-Covered Mountain',
            'G': 'Snow-Covered Forest',
            'COLORLESS': 'Snow-Covered Wastes'
            }

        print(f'Adding {base_basics} basic lands distributed across {len(self.colors)} colors')

        # Add equal distribution first
        for color in self.colors:
            basic = color_to_basic.get(color)
            if basic:
                # Add basics with explicit commander flag and track count
                for _ in range(basics_per_color):
                    self.add_card(basic, 'Basic Land', None, 0, is_commander=False)

        # Distribute remaining basics based on color requirements
        if remaining_basics > 0:
            for color in self.colors[:remaining_basics]:
                basic = color_to_basic.get(color)
                if basic:
                    self.add_card(basic, 'Basic Land', None, 0, is_commander=False)

        lands_to_remove = []
        for key in color_to_basic:
            basic = color_to_basic.get(key)
            lands_to_remove.append(basic)
        
        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)

    def add_standard_non_basics(self):
        """Add staple utility lands based on deck requirements."""
        logger.info('Adding staple non-basic lands')
        
        # Define staple lands and their conditions
        staple_lands = {
            'Reliquary Tower': lambda: True,  # Always include
            'Ash Barrens': lambda: 'Landfall' not in self.commander_tags,
            'Command Tower': lambda: len(self.colors) > 1,
            'Exotic Orchard': lambda: len(self.colors) > 1,
            'War Room': lambda: len(self.colors) <= 2,
            'Rogue\'s Passage': lambda: self.commander_power >= 5
        }
        
        self.staples = []
        try:
            # Add lands that meet their conditions
            for land, condition in staple_lands.items():
                if condition():
                    if land not in self.card_library['Card Name'].values:
                        self.add_card(land, 'Land', None, 0)
                        self.staples.append(land)
                        logger.debug(f"Added staple land: {land}")
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(self.staples)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(self.staples)} staple lands')
            
        except Exception as e:
            logger.error(f"Error adding staple lands: {e}")
            raise
    def add_fetches(self):
        # Determine how many fetches in total
        print('How many fetch lands would you like to include?\n'
              'For most decks you\'ll likely be good with 3 or 4, just enough to thin the deck and help ensure the color availability.\n'
              'If you\'re doing Landfall, more fetches would be recommended just to get as many Landfall triggers per turn.')
        answer = self.input_handler.questionnaire('Number', 2)
        MAX_ATTEMPTS = 50  # Maximum attempts to prevent infinite loops
        attempt_count = 0
        desired_fetches = int(answer)
        chosen_fetches = []
        
        generic_fetches = [
            'Evolving Wilds', 'Terramorphic Expanse', 'Shire Terrace', 
            'Escape Tunnel', 'Promising Vein', 'Myriad Landscape', 
            'Fabled Passage', 'Terminal Moraine'
        ]
        fetches = generic_fetches.copy()
        lands_to_remove = generic_fetches.copy()
        
        # Adding in expensive fetches
        if (use_scrython and self.set_max_card_price):
            if self.price_checker.get_card_price('Prismatic Vista') <= self.max_card_price * 1.1:
                lands_to_remove.append('Prismatic Vista')
                fetches.append('Prismatic Vista')
            else:
                lands_to_remove.append('Prismatic Vista')
                pass
        else:
            lands_to_remove.append('Prismatic Vista')
            fetches.append('Prismatic Vista')
        
        color_to_fetch = {
            'W': ['Flooded Strand', 'Windswept Heath', 'Marsh Flats', 'Arid Mesa', 'Brokers Hideout', 'Obscura Storefront', 'Cabaretti Courtyard'],
            'U': ['Flooded Strand', 'Polluted Delta', 'Scalding Tarn', 'Misty Rainforest', 'Brokers Hideout', 'Obscura Storefront', 'Maestros Theater'], 
            'B': ['Polluted Delta', 'Bloodstained Mire', 'Marsh Flats', 'Verdant Catacombs', 'Obscura Storefront', 'Maestros Theater', 'Riveteers Overlook'],
            'R': ['Bloodstained Mire', 'Wooded Foothills', 'Scalding Tarn', 'Arid Mesa', 'Maestros Theater', 'Riveteers Overlook', 'Cabaretti Courtyard'],
            'G': ['Wooded Foothills', 'Windswept Heath', 'Verdant Catacombs', 'Misty Rainforest', 'Brokers Hideout', 'Riveteers Overlook', 'Cabaretti Courtyard']
        }
        
        for color in self.colors:
            fetch = color_to_fetch.get(color)
            if fetch not in fetches:
                fetches.extend(fetch)
                if fetch not in lands_to_remove:
                    lands_to_remove.extend(fetch)
        for color in color_to_fetch:
            fetch = color_to_fetch.get(color)
            if fetch not in fetches:
                fetches.extend(fetch)
                if fetch not in lands_to_remove:
                    lands_to_remove.extend(fetch)
        
        # Randomly choose fetches up to the desired number
        while len(chosen_fetches) < desired_fetches + 3 and attempt_count < MAX_ATTEMPTS:
            if not fetches:  # If we run out of fetches to choose from
                break
                
            fetch_choice = random.choice(fetches)
            if use_scrython and self.set_max_card_price:
                if self.price_checker.get_card_price(fetch_choice) <= self.max_card_price * 1.1:
                    chosen_fetches.append(fetch_choice)
                    fetches.remove(fetch_choice)
            else:
                chosen_fetches.append(fetch_choice)
                fetches.remove(fetch_choice)
                
            attempt_count += 1

        # Select final fetches to add
        fetches_to_add = []
        available_fetches = chosen_fetches[:desired_fetches]
        for fetch in available_fetches:
            if fetch not in fetches_to_add:
                fetches_to_add.append(fetch)

        if attempt_count >= MAX_ATTEMPTS:
            logger.warning(f"Reached maximum attempts ({MAX_ATTEMPTS}) while selecting fetch lands")

        for card in fetches_to_add:
            self.add_card(card, 'Land', None, 0)
            
        self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
        self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
    
    def add_kindred_lands(self):
        """Add lands that support tribal/kindred themes."""
        logger.info('Adding Kindred-themed lands')
        
        # Standard Kindred support lands
        KINDRED_STAPLES = [
            {'name': 'Path of Ancestry', 'type': 'Land'},
            {'name': 'Three Tree City', 'type': 'Legendary Land'},
            {'name': 'Cavern of Souls', 'type': 'Land'}
        ]
        
        kindred_lands = KINDRED_STAPLES.copy()
        lands_to_remove = set()
        
        try:
            # Process each Kindred theme
            for theme in self.themes:
                if 'Kindred' in theme:
                    creature_type = theme.replace(' Kindred', '')
                    logger.info(f'Searching for {creature_type}-specific lands')
                    
                    # Filter lands by creature type
                    type_specific = self.land_df[
                        self.land_df['text'].notna() & 
                        (self.land_df['text'].str.contains(creature_type, case=False) |
                         self.land_df['type'].str.contains(creature_type, case=False))
                    ]
                    
                    # Add matching lands to pool
                    for _, row in type_specific.iterrows():
                        kindred_lands.append({
                            'name': row['name'],
                            'type': row['type'],
                            'manaCost': row['manaCost'],
                            'manaValue': row['manaValue']
                        })
                        lands_to_remove.add(row['name'])
            
            # Add lands to deck
            for card in kindred_lands:
                if card['name'] not in self.card_library['Card Name'].values:
                    self.add_card(card['name'], card['type'], 
                                None, 0)
                    lands_to_remove.add(card['name'])
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(lands_to_remove)} Kindred-themed lands')
            
        except Exception as e:
            logger.error(f"Error adding Kindred lands: {e}")
            raise
    def add_dual_lands(self):
        # Determine dual-color lands available 
        
        # Determine if using the dual-type lands
        print('Would you like to include Dual-type lands (i.e. lands that count as both a Plains and a Swamp for example)?')
        choice = self.input_handler.questionnaire('Confirm', True)
        color_filter = []
        color_dict = {
            'azorius': 'Plains Island',
            'dimir': 'Island Swamp',
            'rakdos': 'Swamp Mountain',
            'gruul': 'Mountain Forest',
            'selesnya': 'Forest Plains',
            'orzhov': 'Plains Swamp',
            'golgari': 'Swamp Forest',
            'simic': 'Forest Island',
            'izzet': 'Island Mountain',
            'boros': 'Mountain Plains'
        }
        
        if choice:
            for key in color_dict:
                if key in self.files_to_load:
                    color_filter.extend([f'Land — {color_dict[key]}', f'Snow Land — {color_dict[key]}'])
            
            dual_df = self.land_df[self.land_df['type'].isin(color_filter)].copy()
            
            # Convert to list of card dictionaries
            card_pool = []
            for _, row in dual_df.iterrows():
                card = {
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue']
                }
                card_pool.append(card)
            
            lands_to_remove = []
            for card in card_pool:
                self.add_card(card['name'], card['type'], 
                            card['manaCost'], card['manaValue'])
                lands_to_remove.append(card['name'])

            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(card_pool)} Dual-type land cards.')
            
        if not choice:
            logger.info('Skipping adding Dual-type land cards.')
    
    def add_triple_lands(self):
        # Determine if using Triome lands
        print('Would you like to include triome lands (i.e. lands that count as a Mountain, Forest, and Plains for example)?')
        choice = self.input_handler.questionnaire('Confirm', True)
        
        color_filter = []
        color_dict = {
            'bant': 'Forest Plains Island',
            'esper': 'Plains Island Swamp',
            'grixis': 'Island Swamp Mountain',
            'jund': 'Swamp Mountain Forest',
            'naya': 'Mountain Forest Plains',
            'mardu': 'Mountain Plains Swamp',
            'abzan': 'Plains Swamp Forest',
            'sultai': 'Swamp Forest Island',
            'temur': 'Forest Island Mountain',
            'jeska': 'Island Mountain Plains'
        }
        
        if choice:
            for key in color_dict:
                if key in self.files_to_load:
                    color_filter.extend([f'Land — {color_dict[key]}'])
            
            triome_df = self.land_df[self.land_df['type'].isin(color_filter)].copy()
        
            # Convert to list of card dictionaries
            card_pool = []
            for _, row in triome_df.iterrows():
                card = {
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue']
                }
                card_pool.append(card)
            
            lands_to_remove = []
            for card in card_pool:
                self.add_card(card['name'], card['type'], 
                            card['manaCost'], card['manaValue'])
                lands_to_remove.append(card['name'])

            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(card_pool)} Triome land cards.')
            
        if not choice:
            logger.info('Skipping adding Triome land cards.')
    
    def add_misc_lands(self):
        """Add additional utility lands that fit the deck's color identity."""
        logger.info('Adding miscellaneous utility lands')
        
        MIN_MISC_LANDS = 5
        MAX_MISC_LANDS = 15
        MAX_POOL_SIZE = 100
        
        try:
            # Create filtered pool of candidate lands
            land_pool = (self.land_df
                        .head(MAX_POOL_SIZE)
                        .copy()
                        .reset_index(drop=True))
            
            # Convert to card dictionaries
            card_pool = [
                {
                    'name': row['name'],
                    'type': row['type'],
                    'manaCost': row['manaCost'],
                    'manaValue': row['manaValue']
                }
                for _, row in land_pool.iterrows()
                if row['name'] not in self.card_library['Card Name'].values
            ]
            
            if not card_pool:
                logger.warning("No eligible misc lands found")
                return
            
            # Randomly select lands within constraints
            target_count = random.randint(MIN_MISC_LANDS, MAX_MISC_LANDS)
            cards_to_add = []
            
            while card_pool and len(cards_to_add) < target_count:
                card = random.choice(card_pool)
                card_pool.remove(card)
                
                # Check price if enabled
                if use_scrython and self.set_max_card_price:
                    price = self.price_checker.get_card_price(card['name'])
                    if price > self.max_card_price * 1.1:
                        continue
                
                cards_to_add.append(card)
            
            # Add selected lands
            lands_to_remove = set()
            for card in cards_to_add:
                self.add_card(card['name'], card['type'],
                            card['manaCost'], card['manaValue'])
                lands_to_remove.add(card['name'])
            
            # Update land database
            self.land_df = self.land_df[~self.land_df['name'].isin(lands_to_remove)]
            self.land_df.to_csv(f'{CSV_DIRECTORY}/test_lands.csv', index=False)
            
            logger.info(f'Added {len(cards_to_add)} miscellaneous lands')
            
        except Exception as e:
            logger.error(f"Error adding misc lands: {e}")
            raise
    def check_basics(self):
        """Check and display counts of each basic land type."""
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
        for land in basic_lands:
            count = len(self.card_library[self.card_library['Card Name'] == land])
            basic_lands[land] = count
            self.total_basics += count
        
        logger.info("\nBasic Land Counts:")
        for land, count in basic_lands.items():
            if count > 0:
                logger.info(f"{land}: {count}")
        logger.info(f"Total basic lands: {self.total_basics}\n")
   
    def remove_basic(self, max_attempts: int = 3):
        """
        Remove a basic land while maintaining color balance.
        Attempts to remove from colors with more basics first.
        
        Args:
            max_attempts: Maximum number of removal attempts before falling back to non-basics
        """
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
        """Remove a random non-basic, non-staple land from the deck."""
        logger.info('Removing a random nonbasic land.')

        # Define basic lands including snow-covered variants
        basic_lands = [
            'Plains', 'Island', 'Swamp', 'Mountain', 'Forest',
            'Snow-Covered Plains', 'Snow-Covered Island', 'Snow-Covered Swamp',
            'Snow-Covered Mountain', 'Snow-Covered Forest'
        ]

        try:
            # Filter for non-basic, non-staple lands
            library_filter = self.card_library[
                (self.card_library['Card Type'].str.contains('Land')) & 
                (~self.card_library['Card Name'].isin(basic_lands + self.staples))
            ].copy()

            if len(library_filter) == 0:
                logger.warning("No suitable non-basic lands found to remove.")
                return

            # Select random land to remove
            card_index = np.random.choice(library_filter.index)
            card_name = self.card_library.loc[card_index, 'Card Name']

            logger.info(f"Removing {card_name}")
            self.card_library.drop(card_index, inplace=True)
            self.card_library.reset_index(drop=True, inplace=True)
            logger.info("Card removed successfully.")

        except Exception as e:
            logger.error(f"Error removing land: {e}")
            logger.warning("Failed to remove land card.")
    
    def count_pips(self):
        """Count and display the number of colored mana symbols in casting costs using vectorized operations."""
        logger.info('Analyzing color pip distribution...')
        
        # Define colors to check
        colors = ['W', 'U', 'B', 'R', 'G']
        
        # Use vectorized string operations
        mana_costs = self.card_library['Mana Cost'].dropna()
        pip_counts = {color: mana_costs.str.count(color).sum() for color in colors}
        
        total_pips = sum(pip_counts.values())
        if total_pips == 0:
            logger.error("No colored mana symbols found in casting costs.")
            return
        
        logger.info("\nColor Pip Distribution:")
        for color, count in pip_counts.items():
            if count > 0:
                percentage = (count / total_pips) * 100
                print(f"{color}: {count} pips ({percentage:.1f}%)")
        logger.info(f"Total colored pips: {total_pips}\n")
        
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
    
    def weight_by_theme(self, tag, ideal=1, weight=1, df=None):
        # First grab the first 50/30/20 cards that match each theme
        """Add cards with specific tag up to ideal_value count"""
        ideal_value = math.ceil(ideal * weight * 0.9)
        print(f'Finding {ideal_value} cards with the "{tag}" tag...')
        if 'Kindred' in tag:
            tags = [tag, 'Kindred Support']
        else:
            tags = [tag]
        # Filter cards with the given tag
        tag_df = df.copy()
        tag_df.sort_values(by='edhrecRank', inplace=True)
        tag_df = tag_df[tag_df['themeTags'].apply(lambda x: any(tag in x for tag in tags))]
        # Take top cards based on ideal value
        pool_size = int(ideal_value * random.randint(15, 20) /10)
        tag_df = tag_df.head(pool_size)
        
        # Convert to list of card dictionaries
        card_pool = [
            {
                'name': row['name'],
                'type': row['type'],
                'manaCost': row['manaCost'],
                'manaValue': row['manaValue']
            }
            for _, row in tag_df.iterrows()
        ]

        # Randomly select cards up to ideal value
        cards_to_add = []
        while len(cards_to_add) < ideal_value and card_pool:
            card = random.choice(card_pool)
            card_pool.remove(card)
            
            # Check price constraints if enabled
            if use_scrython and self.set_max_card_price:
                price = self.price_checker.get_card_price(card['name'])
                if price > self.max_card_price * 1.1:
                    continue
                    
            # Add card if not already in library
            
            if card['name'] in multiple_copy_cards:
                if card['name'] == 'Nazgûl':
                    for _ in range(9):
                        cards_to_add.append(card)
                elif card['name'] == 'Seven Dwarves':
                    for _ in range(7):
                        cards_to_add.append(card)
                else:
                    num_to_add = ideal_value - len(cards_to_add)
                    for _ in range(num_to_add):
                        cards_to_add.append(card)
            
            elif (card['name'] not in multiple_copy_cards
                  and card['name'] not in self.card_library['Card Name'].values):
                cards_to_add.append(card)
                
            elif (card['name'] not in multiple_copy_cards
                  and card['name'] in self.card_library['Card Name'].values):
                logger.warning(f"{card['name']} already in Library, skipping it.")
                continue
        
        # Add selected cards to library
        for card in cards_to_add:
            self.add_card(card['name'], card['type'], 
                         card['manaCost'], card['manaValue'])
        
        card_pool_names = [item['name'] for item in card_pool]
        self.full_df = self.full_df[~self.full_df['name'].isin(card_pool_names)]
        self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(card_pool_names)]
        logger.info(f'Added {len(cards_to_add)} {tag} cards')
        #tag_df.to_csv(f'{CSV_DIRECTORY}/test_{tag}.csv', index=False)
    
    def add_by_tags(self, tag, ideal_value=1, df=None):
        """Add cards with specific tag up to ideal_value count"""
        print(f'Finding {ideal_value} cards with the "{tag}" tag...')

        # Filter cards with the given tag
        skip_creatures = self.creature_cards > self.ideal_creature_count * 1.1
        tag_df = df.copy()
        tag_df.sort_values(by='edhrecRank', inplace=True)
        tag_df = tag_df[tag_df['themeTags'].apply(lambda x: tag in x)]
        # Take top cards based on ideal value
        pool_size = int(ideal_value * random.randint(2, 3))
        tag_df = tag_df.head(pool_size)

        # Convert to list of card dictionaries
        card_pool = [
            {
                'name': row['name'],
                'type': row['type'],
                'manaCost': row['manaCost'],
                'manaValue': row['manaValue']
            }
            for _, row in tag_df.iterrows()
        ]

        # Randomly select cards up to ideal value
        cards_to_add = []
        while len(cards_to_add) < ideal_value and card_pool:
            card = random.choice(card_pool)
            card_pool.remove(card)

            # Check price constraints if enabled
            if use_scrython and self.set_max_card_price:
                price = self.price_checker.get_card_price(card['name'])
                if price > self.max_card_price * 1.1:
                    continue

            # Add card if not already in library
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
                            card['manaCost'], card['manaValue'])
            else:
                continue

        card_pool_names = [item['name'] for item in card_pool]
        self.full_df = self.full_df[~self.full_df['name'].isin(card_pool_names)]
        self.noncreature_df = self.noncreature_df[~self.noncreature_df['name'].isin(card_pool_names)]
        logger.info(f'Added {len(cards_to_add)} {tag} cards')
        #tag_df.to_csv(f'{CSV_DIRECTORY}/test_{tag}.csv', index=False)
        
    def add_creatures(self):
        """
        Add creatures to the deck based on themes and weights.
        
        This method processes the primary, secondary, and tertiary themes to add
        creatures proportionally according to their weights. The total number of
        creatures added will approximate the ideal_creature_count.
        
        Themes are processed in order of importance (primary -> secondary -> tertiary)
        with error handling to ensure the deck building process continues even if
        a particular theme encounters issues.
        """
        print(f'Adding creatures to deck based on the ideal creature count of {self.ideal_creature_count}...')
        
        try:
            if self.hidden_theme:
                print(f'Processing Hidden theme: {self.hidden_theme}')
                self.weight_by_theme(self.hidden_theme, self.ideal_creature_count, self.hidden_weight, self.creature_df)
            
            print(f'Processing primary theme: {self.primary_theme}')
            self.weight_by_theme(self.primary_theme, self.ideal_creature_count, self.primary_weight, self.creature_df)
            
            if self.secondary_theme:
                print(f'Processing secondary theme: {self.secondary_theme}')
                self.weight_by_theme(self.secondary_theme, self.ideal_creature_count, self.secondary_weight, self.creature_df)
            
            if self.tertiary_theme:
                print(f'Processing tertiary theme: {self.tertiary_theme}')
                self.weight_by_theme(self.tertiary_theme, self.ideal_creature_count, self.tertiary_weight, self.creature_df)
                
        except Exception as e:
            logger.error(f"Error while adding creatures: {e}")
        finally:
            self.organize_library()
            logger.info(f'Creature addition complete. Total creatures (including commander): {self.creature_cards}')
    
    def add_ramp(self):
        try:
            self.add_by_tags('Mana Rock', math.ceil(self.ideal_ramp / 3), self.noncreature_df)
            self.add_by_tags('Mana Dork', math.ceil(self.ideal_ramp / 4), self.creature_df)
            self.add_by_tags('Ramp', math.ceil(self.ideal_ramp / 2), self.noncreature_df)
        except Exception as e:
            logger.error(f"Error while adding Ramp: {e}")
        finally:
            logger.info('Adding Ramp complete.')
    
    def add_interaction(self):
        try:
            self.add_by_tags('Removal', self.ideal_removal, self.noncreature_nonplaneswaker_df)
            self.add_by_tags('Protection', self.ideal_protection, self.noncreature_nonplaneswaker_df)
        except Exception as e:
            logger.error(f"Error while adding Interaction: {e}")
        finally:
            logger.info('Adding Interaction complete.')
        
    def add_board_wipes(self):
        try:
            self.add_by_tags('Board Wipes', self.ideal_wipes, self.full_df)
        except Exception as e:
            logger.error(f"Error while adding Board Wipes: {e}")
        finally:
            logger.info('Adding Board Wipes complete.')
        
    def add_card_advantage(self):
        try:
            self.add_by_tags('Conditional Draw', math.ceil(self.ideal_card_advantage * 0.2), self.full_df)
            self.add_by_tags('Unconditional Draw', math.ceil(self.ideal_card_advantage * 0.8), self.noncreature_nonplaneswaker_df)
        except Exception as e:
            logger.error(f"Error while adding Card Draw: {e}")
        finally:
            logger.info('Adding Card Draw complete.')
    
    def fill_out_deck(self):
        """Fill out the deck to 100 cards with theme-appropriate cards."""
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
            
            # Adjust weights based on remaining cards needed
            weight_multiplier = remaining / cards_needed
            
            try:
                # Add cards from each theme with adjusted weights
                if self.tertiary_theme:
                    self.add_by_tags(self.tertiary_theme, 
                        math.ceil(self.tertiary_weight * 10 * weight_multiplier),
                        self.noncreature_df)
                if self.secondary_theme:
                    self.add_by_tags(self.secondary_theme, 
                        math.ceil(self.secondary_weight * 3 * weight_multiplier),
                        self.noncreature_df)
                self.add_by_tags(self.primary_theme, 
                    math.ceil(self.primary_weight * 2 * weight_multiplier),
                    self.noncreature_df)
                
                # Check if we made progress
                if len(self.card_library) == initial_count:
                    attempts += 1
                    if attempts % 5 == 0:
                        logger.warning(f"Made {attempts} attempts, still need {100 - len(self.card_library)} cards")
                        
                # Break early if we're stuck
                if attempts >= MAX_ATTEMPTS / 2 and len(self.card_library) < initial_count + (cards_needed / 4):
                    logger.warning("Insufficient progress being made, breaking early")
                    break
                    
            except Exception as e:
                logger.error(f"Error while adding cards: {e}")
                attempts += 1
        
        final_count = len(self.card_library)
        if final_count < 100:
            message = f"\nWARNING: Deck is incomplete with {final_count} cards. Manual additions may be needed."
            logger.warning(message)
        else:
            logger.info(f"Successfully filled deck to {final_count} cards in {attempts} attempts")
def main():
    """Main entry point for deck builder application."""
    build_deck = DeckBuilder()
    build_deck.determine_commander()
    pprint.pprint(build_deck.commander_dict, sort_dicts=False)

if __name__ == '__main__':
    main()