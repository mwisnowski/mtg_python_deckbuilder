from typing import Dict, List, Tuple, Optional, Any, Callable, TypeVar, Union
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
    DATAFRAME_REQUIRED_COLUMNS
)
from exceptions import (
    DeckBuilderError,
    CSVValidationError,
    DataFrameValidationError,
    DataFrameTimeoutError,
    EmptyDataFrameError
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