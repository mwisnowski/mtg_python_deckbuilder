"""MTG Python Deckbuilder setup utilities.

This module provides utility functions for setting up and managing the MTG Python Deckbuilder
application. It handles tasks such as downloading card data, filtering cards by various criteria,
and processing legendary creatures for commander format.

Key Features:
    - Card data download from MTGJSON
    - DataFrame filtering and processing
    - Color identity filtering
    - Commander validation
    - CSV file management

The module integrates with settings.py for configuration and exceptions.py for error handling.
"""

from __future__ import annotations

# Standard library imports
import logging
import os
import requests
from pathlib import Path
from typing import List, Optional, Union, TypedDict

# Third-party imports
import pandas as pd
from tqdm import tqdm

# Local application imports
from settings import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    LEGENDARY_OPTIONS,
    FILL_NA_COLUMNS,
    SORT_CONFIG,
    FILTER_CONFIG,
    COLUMN_ORDER,
    PRETAG_COLUMN_ORDER,
    EXCLUDED_CARD_TYPES,
    TAGGED_COLUMN_ORDER
)
from exceptions import (
    MTGJSONDownloadError,
    DataFrameProcessingError,
    ColorFilterError,
    CommanderValidationError
)
from type_definitions import CardLibraryDF

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/setup_utils.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Type definitions
class FilterRule(TypedDict):
    """Type definition for filter rules configuration."""
    exclude: Optional[List[str]]
    require: Optional[List[str]]

class FilterConfig(TypedDict):
    """Type definition for complete filter configuration."""
    layout: FilterRule
    availability: FilterRule
    promoTypes: FilterRule
    securityStamp: FilterRule
def download_cards_csv(url: str, output_path: Union[str, Path]) -> None:
    """Download cards data from MTGJSON and save to CSV.

    Downloads card data from the specified MTGJSON URL and saves it to a local CSV file.
    Shows a progress bar during download using tqdm.

    Args:
        url: URL to download cards data from (typically MTGJSON API endpoint)
        output_path: Path where the downloaded CSV file will be saved

    Raises:
        MTGJSONDownloadError: If download fails due to network issues or invalid response

    Example:
        >>> download_cards_csv('https://mtgjson.com/api/v5/cards.csv', 'cards.csv')
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            with tqdm(total=total_size, unit='iB', unit_scale=True, desc='Downloading cards data') as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    size = f.write(chunk)
                    pbar.update(size)
            
    except requests.RequestException as e:
        logger.error(f'Failed to download cards data from {url}')
        raise MTGJSONDownloadError(
            "Failed to download cards data",
            url,
            getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        ) from e
def check_csv_exists(filepath: Union[str, Path]) -> bool:
    """Check if a CSV file exists at the specified path.

    Verifies the existence of a CSV file at the given path. This function is used
    to determine if card data needs to be downloaded or if it already exists locally.

    Args:
        filepath: Path to the CSV file to check

    Returns:
        bool: True if the file exists, False otherwise

    Example:
        >>> if not check_csv_exists('cards.csv'):
        ...     download_cards_csv(MTGJSON_API_URL, 'cards.csv')
    """
    return Path(filepath).is_file()

def filter_dataframe(df: pd.DataFrame, banned_cards: List[str]) -> pd.DataFrame:
    """Apply standard filters to the cards DataFrame using configuration from settings.

    Applies a series of filters to the cards DataFrame based on configuration from settings.py.
    This includes handling null values, applying basic filters, removing illegal sets and banned cards,
    and processing special card types.

    Args:
        df: pandas DataFrame containing card data to filter
        banned_cards: List of card names that are banned and should be excluded

    Returns:
        pd.DataFrame: A new DataFrame containing only the cards that pass all filters

    Raises:
        DataFrameProcessingError: If any filtering operation fails

    Example:
        >>> filtered_df = filter_dataframe(cards_df, ['Channel', 'Black Lotus'])
    """
    try:
        logger.info('Starting standard DataFrame filtering')
        
        # Fill null values according to configuration
        for col, fill_value in FILL_NA_COLUMNS.items():
            if col == 'faceName':
                fill_value = df['name']
            df[col] = df[col].fillna(fill_value)
            logger.debug(f'Filled NA values in {col} with {fill_value}')
        
        # Apply basic filters from configuration
        filtered_df = df.copy()
        filter_config: FilterConfig = FILTER_CONFIG  # Type hint for configuration
        for field, rules in filter_config.items():
            for rule_type, values in rules.items():
                if rule_type == 'exclude':
                    for value in values:
                        filtered_df = filtered_df[~filtered_df[field].str.contains(value, na=False)]
                elif rule_type == 'require':
                    for value in values:
                        filtered_df = filtered_df[filtered_df[field].str.contains(value, na=False)]
                logger.debug(f'Applied {rule_type} filter for {field}: {values}')
        
        # Remove illegal sets
        for set_code in NON_LEGAL_SETS:
            filtered_df = filtered_df[~filtered_df['printings'].str.contains(set_code, na=False)]
        logger.debug('Removed illegal sets')

        # Remove banned cards
        for card in banned_cards:
            filtered_df = filtered_df[~filtered_df['name'].str.contains(card, na=False)]
        logger.debug('Removed banned cards')

        # Remove special card types
        for card_type in CARD_TYPES_TO_EXCLUDE:
            filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type, na=False)]
        logger.debug('Removed special card types')

        # Select columns, sort, and drop duplicates
        filtered_df = filtered_df[CSV_PROCESSING_COLUMNS]
        filtered_df = filtered_df.sort_values(
            by=SORT_CONFIG['columns'],
            key=lambda col: col.str.lower() if not SORT_CONFIG['case_sensitive'] else col
        )
        filtered_df = filtered_df.drop_duplicates(subset='faceName', keep='first')
        logger.info('Completed standard DataFrame filtering')
        
        return filtered_df

    except Exception as e:
        logger.error(f'Failed to filter DataFrame: {str(e)}')
        raise DataFrameProcessingError(
            "Failed to filter DataFrame",
            "standard_filtering",
            str(e)
        ) from e
def filter_by_color_identity(df: pd.DataFrame, color_identity: str) -> pd.DataFrame:
    """Filter DataFrame by color identity with additional color-specific processing.

    This function extends the base filter_dataframe functionality with color-specific
    filtering logic. It is used by setup.py's filter_by_color function but provides
    a more robust and configurable implementation.

    Args:
        df: DataFrame to filter
        color_identity: Color identity to filter by (e.g., 'W', 'U,B', 'Colorless')

    Returns:
        DataFrame filtered by color identity

    Raises:
        ColorFilterError: If color identity is invalid or filtering fails
        DataFrameProcessingError: If general filtering operations fail
    """
    try:
        logger.info(f'Filtering cards for color identity: {color_identity}')

        # Validate color identity
        with tqdm(total=1, desc='Validating color identity') as pbar:
            if not isinstance(color_identity, str):
                raise ColorFilterError(
                    "Invalid color identity type",
                    str(color_identity),
                    "Color identity must be a string"
                )
            pbar.update(1)
            
        # Apply base filtering
        with tqdm(total=1, desc='Applying base filtering') as pbar:
            filtered_df = filter_dataframe(df, [])
            pbar.update(1)
            
        # Filter by color identity
        with tqdm(total=1, desc='Filtering by color identity') as pbar:
            filtered_df = filtered_df[filtered_df['colorIdentity'] == color_identity]
            logger.debug(f'Applied color identity filter: {color_identity}')
            pbar.update(1)
            
        # Additional color-specific processing
        with tqdm(total=1, desc='Performing color-specific processing') as pbar:
            # Placeholder for future color-specific processing
            pbar.update(1)
        logger.info(f'Completed color identity filtering for {color_identity}')
        return filtered_df
        
    except DataFrameProcessingError as e:
        raise ColorFilterError(
            "Color filtering failed",
            color_identity,
            str(e)
        ) from e
    except Exception as e:
        raise ColorFilterError(
            "Unexpected error during color filtering",
            color_identity,
            str(e)
        ) from e
        
def process_legendary_cards(df: pd.DataFrame) -> pd.DataFrame:
    """Process and filter legendary cards for commander eligibility with comprehensive validation.

    Args:
        df: DataFrame containing all cards

    Returns:
        DataFrame containing only commander-eligible cards

    Raises:
        CommanderValidationError: If validation fails for legendary status, special cases, or set legality
        DataFrameProcessingError: If general processing fails
    """
    try:
        logger.info('Starting commander validation process')

        filtered_df = df.copy()
        # Step 1: Check legendary status
        try:
            with tqdm(total=1, desc='Checking legendary status') as pbar:
                mask = filtered_df['type'].str.contains('|'.join(LEGENDARY_OPTIONS), na=False)
                if not mask.any():
                    raise CommanderValidationError(
                        "No legendary creatures found",
                        "legendary_check",
                        "DataFrame contains no cards matching legendary criteria"
                    )
                filtered_df = filtered_df[mask].copy()
                logger.debug(f'Found {len(filtered_df)} legendary cards')
                pbar.update(1)
        except Exception as e:
            raise CommanderValidationError(
                "Legendary status check failed",
                "legendary_check",
                str(e)
            ) from e

        # Step 2: Validate special cases
        try:
            with tqdm(total=1, desc='Validating special cases') as pbar:
                special_cases = df['text'].str.contains('can be your commander', na=False)
                special_commanders = df[special_cases].copy()
                filtered_df = pd.concat([filtered_df, special_commanders]).drop_duplicates()
                logger.debug(f'Added {len(special_commanders)} special commander cards')
                pbar.update(1)
        except Exception as e:
            raise CommanderValidationError(
                "Special case validation failed",
                "special_cases",
                str(e)
            ) from e

        # Step 3: Verify set legality
        try:
            with tqdm(total=1, desc='Verifying set legality') as pbar:
                initial_count = len(filtered_df)
                for set_code in NON_LEGAL_SETS:
                    filtered_df = filtered_df[
                        ~filtered_df['printings'].str.contains(set_code, na=False)
                    ]
                removed_count = initial_count - len(filtered_df)
                logger.debug(f'Removed {removed_count} cards from illegal sets')
                pbar.update(1)
        except Exception as e:
            raise CommanderValidationError(
                "Set legality verification failed",
                "set_legality",
                str(e)
            ) from e
        logger.info(f'Commander validation complete. {len(filtered_df)} valid commanders found')
        return filtered_df

    except CommanderValidationError:
        raise
    except Exception as e:
        raise DataFrameProcessingError(
            "Failed to process legendary cards",
            "commander_processing",
            str(e)
        ) from e

def process_card_dataframe(df: CardLibraryDF, batch_size: int = 1000, columns_to_keep: Optional[List[str]] = None,
                         include_commander_cols: bool = False, skip_availability_checks: bool = False) -> CardLibraryDF:
    """Process DataFrame with common operations in batches.

    Args:
        df: DataFrame to process
        batch_size: Size of batches for processing
        columns_to_keep: List of columns to keep (default: COLUMN_ORDER)
        include_commander_cols: Whether to include commander-specific columns
        skip_availability_checks: Whether to skip availability and security checks (default: False)

    Args:
        df: DataFrame to process
        batch_size: Size of batches for processing
        columns_to_keep: List of columns to keep (default: COLUMN_ORDER)
        include_commander_cols: Whether to include commander-specific columns

    Returns:
        CardLibraryDF: Processed DataFrame with standardized structure
    """
    logger.info("Processing card DataFrame...")

    if columns_to_keep is None:
        columns_to_keep = TAGGED_COLUMN_ORDER.copy()
        if include_commander_cols:
            commander_cols = ['printings', 'text', 'power', 'toughness', 'keywords']
            columns_to_keep.extend(col for col in commander_cols if col not in columns_to_keep)

    # Fill NA values
    df.loc[:, 'colorIdentity'] = df['colorIdentity'].fillna('Colorless')
    df.loc[:, 'faceName'] = df['faceName'].fillna(df['name'])

    # Process in batches
    total_batches = len(df) // batch_size + 1
    processed_dfs = []

    for i in tqdm(range(total_batches), desc="Processing batches"):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(df))
        batch = df.iloc[start_idx:end_idx].copy()

        if not skip_availability_checks:
            columns_to_keep = COLUMN_ORDER.copy()
            logger.debug("Performing column checks...")
            # Common processing steps
            batch = batch[batch['availability'].str.contains('paper', na=False)]
            batch = batch.loc[batch['layout'] != 'reversible_card']
            batch = batch.loc[batch['promoTypes'] != 'playtest']
            batch = batch.loc[batch['securityStamp'] != 'heart']
            batch = batch.loc[batch['securityStamp'] != 'acorn']
            # Keep only specified columns
            batch = batch[columns_to_keep]
            processed_dfs.append(batch)
        else:
            logger.debug("Skipping column checks...")
    
    # Keep only specified columns
    batch = batch[columns_to_keep]
    processed_dfs.append(batch)

    # Combine processed batches
    result = pd.concat(processed_dfs, ignore_index=True)

    # Final processing
    result.drop_duplicates(subset='faceName', keep='first', inplace=True)
    result.sort_values(by=['name', 'side'], key=lambda col: col.str.lower(), inplace=True)

    logger.info("DataFrame processing completed")
    return result
