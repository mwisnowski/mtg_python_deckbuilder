from typing import Dict, List, Tuple, Optional, Any, Callable, TypeVar, Union, cast
import pandas as pd
from price_check import PriceChecker
from input_handler import InputHandler
import logging
import functools
import time
import pandas as pd
from fuzzywuzzy import process
from settings import (
    COMMANDER_CSV_PATH,
    FUZZY_MATCH_THRESHOLD,
    MAX_FUZZY_CHOICES,
    COMMANDER_CONVERTERS,
    DATAFRAME_VALIDATION_RULES,
    DATAFRAME_VALIDATION_TIMEOUT,
    DATAFRAME_BATCH_SIZE,
    DATAFRAME_TRANSFORM_TIMEOUT,
    DATAFRAME_REQUIRED_COLUMNS,
    WEIGHT_ADJUSTMENT_FACTORS,
    DEFAULT_MAX_DECK_PRICE,
    DEFAULT_MAX_CARD_PRICE,
    DECK_COMPOSITION_PROMPTS,
    DEFAULT_RAMP_COUNT,
    DEFAULT_LAND_COUNT,
    DEFAULT_BASIC_LAND_COUNT,
    DEFAULT_CREATURE_COUNT,
    DEFAULT_REMOVAL_COUNT,
    DEFAULT_CARD_ADVANTAGE_COUNT,
    DEFAULT_PROTECTION_COUNT,
    DEFAULT_WIPES_COUNT,
    CARD_TYPE_SORT_ORDER,
    DUPLICATE_CARD_FORMAT,
    COLOR_TO_BASIC_LAND,
    SNOW_BASIC_LAND_MAPPING,
    KINDRED_STAPLE_LANDS,
)
from exceptions import (
    DeckBuilderError,
    DuplicateCardError,
    CSVValidationError,
    DataFrameValidationError,
    DataFrameTimeoutError,
    EmptyDataFrameError,
    FetchLandSelectionError,
    FetchLandValidationError,
    KindredLandSelectionError,
    KindredLandValidationError,
    ThemeSelectionError,
    ThemeWeightError,
    CardTypeCountError
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Type variables for generic functions
T = TypeVar('T')
DataFrame = TypeVar('DataFrame', bound=pd.DataFrame)

def timeout_wrapper(timeout: float) -> Callable:
    """Decorator to add timeout to functions.

    Args:
        timeout: Maximum execution time in seconds

    Returns:
        Decorated function with timeout

    Raises:
        DataFrameTimeoutError: If operation exceeds timeout
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                raise DataFrameTimeoutError(
                    func.__name__,
                    timeout,
                    elapsed,
                    {'args': args, 'kwargs': kwargs}
                )
            return result
        return wrapper
    return decorator

def get_validation_rules(data_type: str) -> Dict[str, Dict[str, Any]]:
    """Get validation rules for specific data type.

    Args:
        data_type: Type of data to get rules for

    Returns:
        Dictionary of validation rules
    """
    from settings import (
        CREATURE_VALIDATION_RULES,
        SPELL_VALIDATION_RULES,
        LAND_VALIDATION_RULES
    )
    
    rules_map = {
        'creature': CREATURE_VALIDATION_RULES,
        'spell': SPELL_VALIDATION_RULES,
        'land': LAND_VALIDATION_RULES
    }
    
    return rules_map.get(data_type, DATAFRAME_VALIDATION_RULES)

@timeout_wrapper(DATAFRAME_VALIDATION_TIMEOUT)
def validate_dataframe(df: pd.DataFrame, rules: Dict[str, Dict[str, Any]]) -> bool:
    """Validate DataFrame against provided rules.

    Args:
        df: DataFrame to validate
        rules: Validation rules to apply

    Returns:
        True if validation passes

    Raises:
        DataFrameValidationError: If validation fails
    """
    #print(df.columns)
    if df.empty:
        raise EmptyDataFrameError("validate_dataframe")
        
    try:
        validate_required_columns(df)
        validate_column_types(df, rules)
        return True
    except Exception as e:
        raise DataFrameValidationError(
            "DataFrame validation failed",
            {'rules': rules, 'error': str(e)}
        )

def validate_column_types(df: pd.DataFrame, rules: Dict[str, Dict[str, Any]]) -> bool:
    """Validate column types against rules.

    Args:
        df: DataFrame to validate
        rules: Type validation rules

    Returns:
        True if validation passes

    Raises:
        DataFrameValidationError: If type validation fails
    """
    for col, rule in rules.items():
        if col not in df.columns:
            continue
            
        expected_type = rule.get('type')
        if not expected_type:
            continue
            
        if isinstance(expected_type, tuple):
            valid = any(df[col].dtype.name.startswith(t) for t in expected_type)
        else:
            valid = df[col].dtype.name.startswith(expected_type)
            
        if not valid:
            raise DataFrameValidationError(
                col,
                rule,
                {'actual_type': df[col].dtype.name}
            )
    
    return True

def validate_required_columns(df: pd.DataFrame) -> bool:
    """Validate presence of required columns.

    Args:
        df: DataFrame to validate

    Returns:
        True if validation passes

    Raises:
        DataFrameValidationError: If required columns are missing
    """
    #print(df.columns)
    missing = set(DATAFRAME_REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise DataFrameValidationError(
            "missing_columns",
            {'required': DATAFRAME_REQUIRED_COLUMNS},
            {'missing': list(missing)}
        )
    return True

@timeout_wrapper(DATAFRAME_TRANSFORM_TIMEOUT)
def process_dataframe_batch(df: pd.DataFrame, batch_size: int = DATAFRAME_BATCH_SIZE) -> pd.DataFrame:
    """Process DataFrame in batches.

    Args:
        df: DataFrame to process
        batch_size: Size of each batch

    Returns:
        Processed DataFrame

    Raises:
        DataFrameTimeoutError: If processing exceeds timeout
    """
    processed_dfs = []
    
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i + batch_size].copy()
        processed = transform_dataframe(batch)
        processed_dfs.append(processed)
        
    return pd.concat(processed_dfs, ignore_index=True)

def transform_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply transformations to DataFrame.

    Args:
        df: DataFrame to transform

    Returns:
        Transformed DataFrame
    """
    df = df.copy()
    
    # Fill missing values
    df['colorIdentity'] = df['colorIdentity'].fillna('COLORLESS')
    df['colors'] = df['colors'].fillna('COLORLESS')
    
    # Convert types
    numeric_cols = ['manaValue', 'edhrecRank']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def combine_dataframes(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Combine multiple DataFrames with validation.

    Args:
        dfs: List of DataFrames to combine

    Returns:
        Combined DataFrame

    Raises:
        EmptyDataFrameError: If no valid DataFrames to combine
    """
    if not dfs:
        raise EmptyDataFrameError("No DataFrames to combine")
        
    valid_dfs = []
    for df in dfs:
        try:
            if validate_dataframe(df, DATAFRAME_VALIDATION_RULES):
                valid_dfs.append(df)
        except DataFrameValidationError as e:
            logger.warning(f"Skipping invalid DataFrame: {e}")
            
    if not valid_dfs:
        raise EmptyDataFrameError("No valid DataFrames to combine")
        
    return pd.concat(valid_dfs, ignore_index=True)

def load_commander_data(csv_path: str = COMMANDER_CSV_PATH, 
                       converters: Dict = COMMANDER_CONVERTERS) -> pd.DataFrame:
    """Load and prepare commander data from CSV file.

    Args:
        csv_path (str): Path to commander CSV file. Defaults to COMMANDER_CSV_PATH.
        converters (Dict): Column converters for CSV loading. Defaults to COMMANDER_CONVERTERS.

    Returns:
        pd.DataFrame: Processed commander dataframe

    Raises:
        DeckBuilderError: If CSV file cannot be loaded or processed
    """
    try:
        df = pd.read_csv(csv_path, converters=converters)
        df['colorIdentity'] = df['colorIdentity'].fillna('COLORLESS')
        df['colors'] = df['colors'].fillna('COLORLESS')
        return df
    except FileNotFoundError:
        logger.error(f"Commander CSV file not found at {csv_path}")
        raise DeckBuilderError(f"Commander data file not found: {csv_path}")
    except Exception as e:
        logger.error(f"Error loading commander data: {e}")
        raise DeckBuilderError(f"Failed to load commander data: {str(e)}")

def process_fuzzy_matches(card_name: str, 
                         df: pd.DataFrame,
                         threshold: int = FUZZY_MATCH_THRESHOLD,
                         max_choices: int = MAX_FUZZY_CHOICES) -> Tuple[str, List[Tuple[str, int]], bool]:
    """Process fuzzy matching for commander name selection.

    Args:
        card_name (str): Input card name to match
        df (pd.DataFrame): Commander dataframe to search
        threshold (int): Minimum score for direct match. Defaults to FUZZY_MATCH_THRESHOLD.
        max_choices (int): Maximum number of choices to return. Defaults to MAX_FUZZY_CHOICES.

    Returns:
        Tuple[str, List[Tuple[str, int]], bool]: Selected card name, list of matches with scores, and match status
    """
    try:
        match, score, _ = process.extractOne(card_name, df['name'])
        if score >= threshold:
            return match, [], True
        
        fuzzy_choices = process.extract(card_name, df['name'], limit=max_choices)
        fuzzy_choices = [(name, score) for name, score in fuzzy_choices]
        return "", fuzzy_choices, False
    except Exception as e:
        logger.error(f"Error in fuzzy matching: {e}")
        raise DeckBuilderError(f"Failed to process fuzzy matches: {str(e)}")

def validate_commander_selection(df: pd.DataFrame, commander_name: str) -> Dict:
    """Validate and format commander data from selection.

    Args:
        df (pd.DataFrame): Commander dataframe
        commander_name (str): Selected commander name

    Returns:
        Dict: Formatted commander data dictionary

    Raises:
        DeckBuilderError: If commander data is invalid or missing
    """
    try:
        filtered_df = df[df['name'] == commander_name]
        if filtered_df.empty:
            raise DeckBuilderError(f"No commander found with name: {commander_name}")
            
        commander_dict = filtered_df.to_dict('list')
        
        # Validate required fields
        required_fields = ['name', 'type', 'colorIdentity', 'colors', 'manaCost', 'manaValue']
        for field in required_fields:
            if field not in commander_dict or not commander_dict[field]:
                raise DeckBuilderError(f"Missing required commander data: {field}")
                
        return commander_dict
    except Exception as e:
        logger.error(f"Error validating commander selection: {e}")
        raise DeckBuilderError(f"Failed to validate commander selection: {str(e)}")

def select_theme(themes_list: List[str], prompt: str, optional=False) -> str:
    """Handle the selection of a theme from a list with user interaction.

    Args:
        themes_list: List of available themes to choose from
        prompt: Message to display when prompting for theme selection

    Returns:
        str: Selected theme name

    Raises:
        ThemeSelectionError: If user chooses to stop without selecting a theme
    """
    try:
        if not themes_list:
            raise ThemeSelectionError("No themes available for selection")

        print(prompt)
        for idx, theme in enumerate(themes_list, 1):
            print(f"{idx}. {theme}")
        print("0. Stop selection")

        while True:
            try:
                choice = int(input("Enter the number of your choice: "))
                if choice == 0:
                    return 'Stop Here'
                if 1 <= choice <= len(themes_list):
                    return themes_list[choice - 1]
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a valid number.")

    except Exception as e:
        logger.error(f"Error in theme selection: {e}")
        raise ThemeSelectionError(f"Theme selection failed: {str(e)}")

def adjust_theme_weights(primary_theme: str,
                        secondary_theme: str,
                        tertiary_theme: str,
                        weights: Dict[str, float]) -> Dict[str, float]:
    """Calculate adjusted theme weights based on theme combinations.

    Args:
        primary_theme: The main theme selected
        secondary_theme: The second theme selected
        tertiary_theme: The third theme selected
        weights: Initial theme weights dictionary

    Returns:
        Dict[str, float]: Adjusted theme weights

    Raises:
        ThemeWeightError: If weight calculations fail
    """
    try:
        adjusted_weights = weights.copy()
        
        for theme, factors in WEIGHT_ADJUSTMENT_FACTORS.items():
            if theme in [primary_theme, secondary_theme, tertiary_theme]:
                for target_theme, factor in factors.items():
                    if target_theme in adjusted_weights:
                        adjusted_weights[target_theme] = round(adjusted_weights[target_theme] * factor, 2)

        # Normalize weights to ensure they sum to 1.0
        total_weight = sum(adjusted_weights.values())
        if total_weight > 0:
            adjusted_weights = {k: round(v/total_weight, 2) for k, v in adjusted_weights.items()}

        print(adjusted_weights)
        return adjusted_weights

    except Exception as e:
        logger.error(f"Error adjusting theme weights: {e}")
        raise ThemeWeightError(f"Failed to adjust theme weights: {str(e)}")
def configure_price_settings(price_checker: Optional[PriceChecker], input_handler: InputHandler) -> None:
    """Handle configuration of price settings if price checking is enabled.

    Args:
        price_checker: Optional PriceChecker instance for price validation
        input_handler: InputHandler instance for user input

    Returns:
        None

    Raises:
        ValueError: If invalid price values are provided
    """
    if not price_checker:
        return

    try:
        # Configure max deck price
        print('Would you like to set an intended max price of the deck?\n'
              'There will be some leeway of ~10%, with a couple alternative options provided.')
        if input_handler.questionnaire('Confirm', message='', default_value=False):
            print('What would you like the max price to be?')
            max_deck_price = float(input_handler.questionnaire('Number', default_value=DEFAULT_MAX_DECK_PRICE))
            price_checker.max_deck_price = max_deck_price
            print()

        # Configure max card price 
        print('Would you like to set a max price per card?\n'
              'There will be some leeway of ~10% when choosing cards and you can choose to keep it or not.')
        if input_handler.questionnaire('Confirm', message='', default_value=False):
            print('What would you like the max price to be?')
            max_card_price = float(input_handler.questionnaire('Number', default_value=DEFAULT_MAX_CARD_PRICE))
            price_checker.max_card_price = max_card_price
            print()

    except ValueError as e:
        logger.error(f"Error configuring price settings: {e}")
        raise
    
def get_deck_composition_values(input_handler: InputHandler) -> Dict[str, int]:
    """Collect deck composition values from the user.

    Args:
        input_handler: InputHandler instance for user input

    Returns:
        Dict[str, int]: Mapping of component names to their values

    Raises:
        ValueError: If invalid numeric values are provided
    """
    try:
        composition = {}
        for component, prompt in DECK_COMPOSITION_PROMPTS.items():
            if component not in ['max_deck_price', 'max_card_price']:
                default_map = {
                    'ramp': DEFAULT_RAMP_COUNT,
                    'lands': DEFAULT_LAND_COUNT,
                    'basic_lands': DEFAULT_BASIC_LAND_COUNT,
                    'creatures': DEFAULT_CREATURE_COUNT,
                    'removal': DEFAULT_REMOVAL_COUNT,
                    'wipes': DEFAULT_WIPES_COUNT,
                    'card_advantage': DEFAULT_CARD_ADVANTAGE_COUNT,
                    'protection': DEFAULT_PROTECTION_COUNT
                }
                default_value = default_map.get(component, 0)

                print(prompt)
                composition[component] = int(input_handler.questionnaire('Number', message='Default', default_value=default_value))
                print()

        return composition

    except ValueError as e:
        logger.error(f"Error getting deck composition values: {e}")
        raise

def assign_sort_order(df: pd.DataFrame) -> pd.DataFrame:
    """Assign sort order to cards based on their types.

    This function adds a 'Sort Order' column to the DataFrame based on the
    CARD_TYPE_SORT_ORDER constant from settings. Cards are sorted according to
    their primary type, with the order specified in CARD_TYPE_SORT_ORDER.

    Args:
        df: DataFrame containing card information with a 'Card Type' column

    Returns:
        DataFrame with an additional 'Sort Order' column

    Example:
        >>> df = pd.DataFrame({
        ...     'Card Type': ['Creature', 'Instant', 'Land']
        ... })
        >>> sorted_df = assign_sort_order(df)
        >>> sorted_df['Sort Order'].tolist()
        ['Creature', 'Instant', 'Land']
    """
    # Create a copy of the input DataFrame
    df = df.copy()

    # Initialize Sort Order column with default value
    df['Sort Order'] = 'Other'

    # Assign sort order based on card types
    for card_type in CARD_TYPE_SORT_ORDER:
        mask = df['Card Type'].str.contains(card_type, case=False, na=False)
        df.loc[mask, 'Sort Order'] = card_type

    # Convert Sort Order to categorical for proper sorting
    df['Sort Order'] = pd.Categorical(
        df['Sort Order'],
        categories=CARD_TYPE_SORT_ORDER + ['Other'],
        ordered=True
    )
    return df

def process_duplicate_cards(card_library: pd.DataFrame, duplicate_lists: List[str]) -> pd.DataFrame:
    """Process duplicate cards in the library and consolidate them with updated counts.

    This function identifies duplicate cards that are allowed to have multiple copies
    (like basic lands and certain special cards), consolidates them into single entries,
    and updates their counts. Card names are formatted using DUPLICATE_CARD_FORMAT.

    Args:
        card_library: DataFrame containing the deck's card library
        duplicate_lists: List of card names allowed to have multiple copies

    Returns:
        DataFrame with processed duplicate cards and updated counts

    Raises:
        DuplicateCardError: If there are issues processing duplicate cards

    Example:
        >>> card_library = pd.DataFrame({
        ...     'name': ['Forest', 'Forest', 'Mountain', 'Mountain', 'Sol Ring'],
        ...     'type': ['Basic Land', 'Basic Land', 'Basic Land', 'Basic Land', 'Artifact']
        ... })
        >>> duplicate_lists = ['Forest', 'Mountain']
        >>> result = process_duplicate_cards(card_library, duplicate_lists)
        >>> print(result['name'].tolist())
        ['Forest x 2', 'Mountain x 2', 'Sol Ring']
    """
    try:
        # Create a copy of the input DataFrame
        processed_library = card_library.copy()
        
        # Process each allowed duplicate card
        for card_name in duplicate_lists:
            # Find all instances of the card
            card_mask = processed_library['name'] == card_name
            card_count = card_mask.sum()
            
            if card_count > 1:
                # Keep only the first instance and update its name with count
                first_instance = processed_library[card_mask].iloc[0]
                processed_library = processed_library[~card_mask]
                
                first_instance['name'] = DUPLICATE_CARD_FORMAT.format(
                    card_name=card_name,
                    count=card_count
                )
                processed_library = pd.concat([processed_library, pd.DataFrame([first_instance])])
        
        return processed_library.reset_index(drop=True)
        
    except Exception as e:
        raise DuplicateCardError(
            f"Failed to process duplicate cards: {str(e)}",
            details={'error': str(e)}
        )

def count_cards_by_type(card_library: pd.DataFrame, card_types: List[str]) -> Dict[str, int]:
    """Count the number of cards for each specified card type in the library.

    Args:
        card_library: DataFrame containing the card library
        card_types: List of card types to count

    Returns:
        Dictionary mapping card types to their counts

    Raises:
        CardTypeCountError: If counting fails for any card type
    """
    try:
        type_counts = {}
        for card_type in card_types:
            # Use pandas str.contains() for efficient type matching
            # Case-insensitive matching with na=False to handle missing values
            type_mask = card_library['type'].str.contains(
                card_type, 
                case=False, 
                na=False
            )
            type_counts[card_type] = int(type_mask.sum())
        
        return type_counts
    except Exception as e:
        logger.error(f"Error counting cards by type: {e}")
        raise CardTypeCountError(f"Failed to count cards by type: {str(e)}")

def calculate_basics_per_color(total_basics: int, num_colors: int) -> Tuple[int, int]:
    """Calculate the number of basic lands per color and remaining basics.

    Args:
        total_basics: Total number of basic lands to distribute
        num_colors: Number of colors in the deck

    Returns:
        Tuple containing (basics per color, remaining basics)

    Example:
        >>> calculate_basics_per_color(20, 3)
        (6, 2)  # 6 basics per color with 2 remaining
    """
    if num_colors == 0:
        return 0, total_basics

    basics_per_color = total_basics // num_colors
    remaining_basics = total_basics % num_colors

    return basics_per_color, remaining_basics

def get_basic_land_mapping(use_snow_covered: bool = False) -> Dict[str, str]:
    """Get the appropriate basic land mapping based on snow-covered preference.

    Args:
        use_snow_covered: Whether to use snow-covered basic lands

    Returns:
        Dictionary mapping colors to their corresponding basic land names

    Example:
        >>> get_basic_land_mapping(False)
        {'W': 'Plains', 'U': 'Island', ...}
        >>> get_basic_land_mapping(True)
        {'W': 'Snow-Covered Plains', 'U': 'Snow-Covered Island', ...}
    """
    return SNOW_BASIC_LAND_MAPPING if use_snow_covered else COLOR_TO_BASIC_LAND

def distribute_remaining_basics(
    basics_per_color: Dict[str, int],
    remaining_basics: int,
    colors: List[str]
) -> Dict[str, int]:
    """Distribute remaining basic lands across colors.

    This function takes the initial distribution of basic lands and distributes
    any remaining basics across the colors. The distribution prioritizes colors
    based on their position in the color list (typically WUBRG order).

    Args:
        basics_per_color: Initial distribution of basics per color
        remaining_basics: Number of remaining basics to distribute
        colors: List of colors to distribute basics across

    Returns:
        Updated dictionary with final basic land counts per color

    Example:
        >>> distribute_remaining_basics(
        ...     {'W': 6, 'U': 6, 'B': 6},
        ...     2,
        ...     ['W', 'U', 'B']
        ... )
        {'W': 7, 'U': 7, 'B': 6}
    """
    if not colors:
        return basics_per_color

    # Create a copy to avoid modifying the input dictionary
    final_distribution = basics_per_color.copy()

    # Distribute remaining basics
    color_index = 0
    while remaining_basics > 0 and color_index < len(colors):
        color = colors[color_index]
        if color in final_distribution:
            final_distribution[color] += 1
            remaining_basics -= 1
        color_index = (color_index + 1) % len(colors)

    return final_distribution

def validate_staple_land_conditions(
    land_name: str,
    conditions: dict,
    commander_tags: List[str],
    colors: List[str],
    commander_power: int
) -> bool:
    """Validate if a staple land meets its inclusion conditions.

    Args:
        land_name: Name of the staple land to validate
        conditions: Dictionary mapping land names to their condition functions
        commander_tags: List of tags associated with the commander
        colors: List of colors in the deck
        commander_power: Power level of the commander

    Returns:
        bool: True if the land meets its conditions, False otherwise

    Example:
        >>> conditions = {'Command Tower': lambda tags, colors, power: len(colors) > 1}
        >>> validate_staple_land_conditions('Command Tower', conditions, [], ['W', 'U'], 7)
        True
    """
    condition = conditions.get(land_name)
    if not condition:
        return False
    return condition(commander_tags, colors, commander_power)

def process_staple_lands(
    lands_to_add: List[str],
    card_library: pd.DataFrame,
    land_df: pd.DataFrame
) -> pd.DataFrame:
    """Update the land DataFrame by removing added staple lands.

    Args:
        lands_to_add: List of staple land names to be added
        card_library: DataFrame containing all available cards
        land_df: DataFrame containing available lands

    Returns:
        Updated land DataFrame with staple lands removed

    Example:
        >>> process_staple_lands(['Command Tower'], card_library, land_df)
        DataFrame without 'Command Tower' in the available lands
    """
    updated_land_df = land_df[~land_df['name'].isin(lands_to_add)]
    return updated_land_df

def validate_fetch_land_count(count: int, min_count: int = 0, max_count: int = 9) -> int:
    """Validate the requested number of fetch lands.

    Args:
        count: Number of fetch lands requested
        min_count: Minimum allowed fetch lands (default: 0)
        max_count: Maximum allowed fetch lands (default: 9)

    Returns:
        Validated fetch land count

    Raises:
        FetchLandValidationError: If count is invalid

    Example:
        >>> validate_fetch_land_count(5)
        5
        >>> validate_fetch_land_count(-1)  # raises FetchLandValidationError
    """
    try:
        fetch_count = int(count)
        if fetch_count < min_count or fetch_count > max_count:
            raise FetchLandValidationError(
                f"Fetch land count must be between {min_count} and {max_count}",
                {"requested": fetch_count, "min": min_count, "max": max_count}
            )
        return fetch_count
    except ValueError:
        raise FetchLandValidationError(
            f"Invalid fetch land count: {count}",
            {"value": count}
        )

def get_available_fetch_lands(colors: List[str], price_checker: Optional[Any] = None,
                            max_price: Optional[float] = None) -> List[str]:
    """Get list of fetch lands available for the deck's colors and budget.

    Args:
        colors: List of deck colors
        price_checker: Optional price checker instance
        max_price: Maximum allowed price per card

    Returns:
        List of available fetch land names

    Example:
        >>> get_available_fetch_lands(['U', 'R'])
        ['Scalding Tarn', 'Flooded Strand', ...]
    """
    from settings import GENERIC_FETCH_LANDS, COLOR_TO_FETCH_LANDS

    # Start with generic fetches that work in any deck
    available_fetches = GENERIC_FETCH_LANDS.copy()

    # Add color-specific fetches
    for color in colors:
        if color in COLOR_TO_FETCH_LANDS:
            available_fetches.extend(COLOR_TO_FETCH_LANDS[color])

    # Remove duplicates while preserving order
    available_fetches = list(dict.fromkeys(available_fetches))

    # Filter by price if price checking is enabled
    if price_checker and max_price:
        available_fetches = [
            fetch for fetch in available_fetches
            if price_checker.get_card_price(fetch) <= max_price * 1.1
        ]

    return available_fetches

def select_fetch_lands(available_fetches: List[str], count: int,
                      allow_duplicates: bool = False) -> List[str]:
    """Randomly select fetch lands from the available pool.

    Args:
        available_fetches: List of available fetch lands
        count: Number of fetch lands to select
        allow_duplicates: Whether to allow duplicate selections

    Returns:
        List of selected fetch land names

    Raises:
        FetchLandSelectionError: If unable to select required number of fetches

    Example:
        >>> select_fetch_lands(['Flooded Strand', 'Polluted Delta'], 2)
        ['Polluted Delta', 'Flooded Strand']
    """
    import random

    if not available_fetches:
        raise FetchLandSelectionError(
            "No fetch lands available to select from",
            {"requested": count}
        )

    if not allow_duplicates and count > len(available_fetches):
        raise FetchLandSelectionError(
            f"Not enough unique fetch lands available (requested {count}, have {len(available_fetches)})",
            {"requested": count, "available": len(available_fetches)}
        )

    if allow_duplicates:
        return random.choices(available_fetches, k=count)
    else:
        return random.sample(available_fetches, k=count)

def validate_kindred_lands(land_name: str, commander_tags: List[str], colors: List[str]) -> bool:
    """Validate if a Kindred land meets inclusion criteria.

    Args:
        land_name: Name of the Kindred land to validate
        commander_tags: List of tags associated with the commander
        colors: List of colors in the deck

    Returns:
        bool: True if the land meets criteria, False otherwise

    Raises:
        KindredLandValidationError: If validation fails

    Example:
        >>> validate_kindred_lands('Cavern of Souls', ['Elf Kindred'], ['G'])
        True
    """
    try:
        # Check if any commander tags are Kindred-related
        has_kindred_theme = any('Kindred' in tag for tag in commander_tags)
        if not has_kindred_theme:
            return False

        # Validate color requirements
        if land_name in KINDRED_STAPLE_LANDS:
            return True

        # Additional validation logic can be added here
        return True

    except Exception as e:
        raise KindredLandValidationError(
            f"Failed to validate Kindred land {land_name}",
            {"error": str(e), "tags": commander_tags, "colors": colors}
        )

def get_available_kindred_lands(colors: List[str], commander_tags: List[str],
                              price_checker: Optional[Any] = None,
                              max_price: Optional[float] = None) -> List[str]:
    """Get list of Kindred lands available for the deck's colors and themes.

    Args:
        colors: List of deck colors
        commander_tags: List of commander theme tags
        price_checker: Optional price checker instance
        max_price: Maximum allowed price per card

    Returns:
        List of available Kindred land names

    Example:
        >>> get_available_kindred_lands(['G'], ['Elf Kindred'])
        ['Cavern of Souls', 'Path of Ancestry', ...]
    """
    # Start with staple Kindred lands
    available_lands = [land['name'] for land in KINDRED_STAPLE_LANDS]

    # Filter by price if price checking is enabled
    if price_checker and max_price:
        available_lands = [
            land for land in available_lands
            if price_checker.get_card_price(land) <= max_price * 1.1
        ]

    return available_lands

def select_kindred_lands(available_lands: List[str], count: int,
                       allow_duplicates: bool = False) -> List[str]:
    """Select Kindred lands from the available pool.

    Args:
        available_lands: List of available Kindred lands
        count: Number of Kindred lands to select
        allow_duplicates: Whether to allow duplicate selections

    Returns:
        List of selected Kindred land names

    Raises:
        KindredLandSelectionError: If unable to select required number of lands

    Example:
        >>> select_kindred_lands(['Cavern of Souls', 'Path of Ancestry'], 2)
        ['Path of Ancestry', 'Cavern of Souls']
    """
    import random

    if not available_lands:
        raise KindredLandSelectionError(
            "No Kindred lands available to select from",
            {"requested": count}
        )

    if not allow_duplicates and count > len(available_lands):
        raise KindredLandSelectionError(
            f"Not enough unique Kindred lands available (requested {count}, have {len(available_lands)})",
            {"requested": count, "available": len(available_lands)}
        )

    if allow_duplicates:
        return random.choices(available_lands, k=count)
    else:
        return random.sample(available_lands, k=count)

def process_kindred_lands(lands_to_add: List[str], card_library: pd.DataFrame,
                        land_df: pd.DataFrame) -> pd.DataFrame:
    """Update the land DataFrame by removing added Kindred lands.

    Args:
        lands_to_add: List of Kindred land names to be added
        card_library: DataFrame containing all available cards
        land_df: DataFrame containing available lands

    Returns:
        Updated land DataFrame with Kindred lands removed

    Example:
        >>> process_kindred_lands(['Cavern of Souls'], card_library, land_df)
        DataFrame without 'Cavern of Souls' in the available lands
    """
    updated_land_df = land_df[~land_df['name'].isin(lands_to_add)]
    return updated_land_df