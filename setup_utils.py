from __future__ import annotations

import pandas as pd
import requests
import logging
from tqdm import tqdm
from pathlib import Path
from typing import List, Optional, Union, Dict, Any

from settings import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    LEGENDARY_OPTIONS,
    FILL_NA_COLUMNS,
    SORT_CONFIG,
    FILTER_CONFIG
)
from exceptions import CSVFileNotFoundError, MTGJSONDownloadError, DataFrameProcessingError, ColorFilterError, CommanderValidationError
from settings import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    LEGENDARY_OPTIONS
)
from exceptions import CSVFileNotFoundError, MTGJSONDownloadError, DataFrameProcessingError

def download_cards_csv(url: str, output_path: Union[str, Path]) -> None:
    """Download cards data from MTGJSON and save to CSV.

    Args:
        url: URL to download cards data from
        output_path: Path to save the downloaded CSV file

    Raises:
        MTGJSONDownloadError: If download fails or response is invalid
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
        raise MTGJSONDownloadError(
            "Failed to download cards data",
            url,
            getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        ) from e

def check_csv_exists(filepath: Union[str, Path]) -> bool:
    """Check if a CSV file exists at the specified path.

    Args:
        filepath: Path to check for CSV file

    Returns:
        True if file exists, False otherwise
    """
    return Path(filepath).is_file()

def filter_dataframe(df: pd.DataFrame, banned_cards: List[str]) -> pd.DataFrame:
    """Apply standard filters to the cards DataFrame using configuration from settings.

    Args:
        df: DataFrame to filter
        banned_cards: List of banned card names to exclude

    Returns:
        Filtered DataFrame

    Raises:
        DataFrameProcessingError: If filtering operations fail
    """
    try:
        logging.info('Starting standard DataFrame filtering')
        
        # Fill null values according to configuration
        for col, fill_value in FILL_NA_COLUMNS.items():
            if col == 'faceName':
                fill_value = df['name']
            df[col] = df[col].fillna(fill_value)
            logging.debug(f'Filled NA values in {col} with {fill_value}')
        
        # Apply basic filters from configuration
        filtered_df = df.copy()
        for field, rules in FILTER_CONFIG.items():
            for rule_type, values in rules.items():
                if rule_type == 'exclude':
                    for value in values:
                        filtered_df = filtered_df[~filtered_df[field].str.contains(value, na=False)]
                elif rule_type == 'require':
                    for value in values:
                        filtered_df = filtered_df[filtered_df[field].str.contains(value, na=False)]
                logging.debug(f'Applied {rule_type} filter for {field}: {values}')
        
        # Remove illegal sets
        for set_code in NON_LEGAL_SETS:
            filtered_df = filtered_df[~filtered_df['printings'].str.contains(set_code, na=False)]
        logging.debug('Removed illegal sets')

        # Remove banned cards
        for card in banned_cards:
            filtered_df = filtered_df[~filtered_df['name'].str.contains(card, na=False)]
        logging.debug('Removed banned cards')

        # Remove special card types
        for card_type in CARD_TYPES_TO_EXCLUDE:
            filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type, na=False)]
        logging.debug('Removed special card types')

        # Select columns, sort, and drop duplicates
        filtered_df = filtered_df[CSV_PROCESSING_COLUMNS]
        filtered_df = filtered_df.sort_values(
            by=SORT_CONFIG['columns'],
            key=lambda col: col.str.lower() if not SORT_CONFIG['case_sensitive'] else col
        )
        filtered_df = filtered_df.drop_duplicates(subset='faceName', keep='first')
        logging.info('Completed standard DataFrame filtering')
        
        return filtered_df

    except Exception as e:
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
        logging.info(f'Filtering cards for color identity: {color_identity}')
        
        # Define processing steps for progress tracking
        steps = [
            'Validating color identity',
            'Applying base filtering',
            'Filtering by color identity',
            'Performing color-specific processing'
        ]
        
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
            logging.debug(f'Applied color identity filter: {color_identity}')
            pbar.update(1)
            
        # Additional color-specific processing
        with tqdm(total=1, desc='Performing color-specific processing') as pbar:
            # Placeholder for future color-specific processing
            pbar.update(1)
        logging.info(f'Completed color identity filtering for {color_identity}')
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
        logging.info('Starting commander validation process')
        validation_steps = [
            'Checking legendary status',
            'Validating special cases',
            'Verifying set legality'
        ]

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
                logging.debug(f'Found {len(filtered_df)} legendary cards')
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
                logging.debug(f'Added {len(special_commanders)} special commander cards')
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
                logging.debug(f'Removed {removed_count} cards from illegal sets')
                pbar.update(1)
        except Exception as e:
            raise CommanderValidationError(
                "Set legality verification failed",
                "set_legality",
                str(e)
            ) from e
        logging.info(f'Commander validation complete. {len(filtered_df)} valid commanders found')
        return filtered_df

    except CommanderValidationError:
        raise
    except Exception as e:
        raise DataFrameProcessingError(
            "Failed to process legendary cards",
            "commander_processing",
            str(e)
        ) from e