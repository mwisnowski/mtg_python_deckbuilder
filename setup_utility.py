from __future__ import annotations

import logging
import os
from typing import List, Optional, Union
from datetime import datetime, timedelta
import pandas as pd
import requests
from tqdm import tqdm

from settings import (banned_cards, CSV_DIRECTORY, COLUMN_ORDER,
                      PRETAG_COLUMN_ORDER, EXCLUDED_CARD_TYPES)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def file_needs_update(file_path: str, max_age_days: int = 14) -> bool:
    """Check if file needs to be updated based on age or existence.

    Args:
        file_path: Path to the file to check
        max_age_days: Maximum age in days before update needed

    Returns:
        bool: True if file needs update, False otherwise
    """
    if not os.path.exists(file_path):
        return True

    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
    age_limit = datetime.now() - timedelta(days=max_age_days)

    return file_time < age_limit

def download_cards_csv(url: str = 'https://mtgjson.com/api/v5/csv/cards.csv') -> bool:
    """Download cards.csv from MTGJSON.

    Args:
        url: URL to download cards.csv from (default: MTGJSON API)

    Returns:
        bool: True if download successful, False otherwise

    Raises:
        requests.RequestException: If download fails
        OSError: If file cannot be written
    """
    # Create directory if it doesn't exist
    os.makedirs(CSV_DIRECTORY, exist_ok=True)
    file_path = f'{CSV_DIRECTORY}/cards.csv'

    # Check if file needs updating
    if not file_needs_update(file_path):
        logger.info("cards.csv is up to date, skipping download")
        return True

    try:
        logger.info("Downloading cards.csv from MTGJSON...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Get total size for progress bar
        total_size = int(response.headers.get('content-length', 0))

        # Write file with progress bar
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        logger.info("Download completed successfully")
        return True

    except requests.RequestException as e:
        logger.error(f"Failed to download cards.csv: {e}")
        raise
    except OSError as e:
        logger.error(f"Failed to write cards.csv: {e}")
        raise

def validate_card_dataframe(df: pd.DataFrame, skip_availability_checks: bool = False) -> bool:
    """Validate DataFrame has required columns and structure.

    Args:
        df: DataFrame to validate
        skip_availability_checks: Whether to skip availability and security checks (default: False)

    Returns:
        bool: True if valid, False otherwise

    Raises:
        ValueError: If required columns are missing
    """
    if not skip_availability_checks:
        missing_cols = set(COLUMN_ORDER) - set(df.columns)
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            raise ValueError(f"DataFrame missing required columns: {missing_cols}")
        logger.debug("Performing availability checks...")
        # Check for required availability values
        if not all(df['availability'].str.contains('paper', na=False)):
            logger.error("Invalid availability values found")
            return False

        # Check for invalid layouts
        if any(df['layout'] == 'reversible_card'):
            logger.error("Invalid card layouts found")
            return False

        # Check for invalid promo types
        if any(df['promoTypes'] == 'playtest'):
            logger.error("Invalid promo types found")
            return False

        # Check for invalid security stamps
        if any(df['securityStamp'].isin(['heart', 'acorn'])):
            logger.error("Invalid security stamps found")
            return False
    else:
        logger.debug("Skipping availability checks...")
        missing_cols = set(PRETAG_COLUMN_ORDER) - set(df.columns)
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            raise ValueError(f"DataFrame missing required columns: {missing_cols}")

    logger.info("DataFrame validation successful")
    return True
def filter_banned_cards(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out banned cards from DataFrame.

    Args:
        df: DataFrame to filter

    Returns:
        Filtered DataFrame without banned cards
    """
    logger.info("Filtering banned cards...")
    for card in banned_cards:
        df = df[~df['name'].str.contains(card, na=False)]
    return df

def filter_card_types(df: pd.DataFrame, excluded_types: List[str] = EXCLUDED_CARD_TYPES) -> pd.DataFrame:
    """Filter cards by type.

    Args:
        df: DataFrame to filter
        excluded_types: List of card types to exclude

    Returns:
        Filtered DataFrame
    """
    logger.info("Filtering card types...")
    for card_type in excluded_types:
        df = df[~df['type'].str.contains(card_type, na=False)]
    return df

def process_card_dataframe(df: pd.DataFrame, batch_size: int = 1000, columns_to_keep: Optional[List[str]] = None,
                         include_commander_cols: bool = False, skip_availability_checks: bool = False) -> pd.DataFrame:
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
        Processed DataFrame
    """
    logger.info("Processing card DataFrame...")

    if columns_to_keep is None:
        columns_to_keep = PRETAG_COLUMN_ORDER.copy()
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

def validate_commander_eligibility(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and filter cards based on commander eligibility requirements.

    Args:
        df: DataFrame to validate

    Returns:
        Filtered DataFrame containing only commander-eligible cards
    """
    logger.info("Validating commander eligibility...")

    # Filter legendary creatures and eligible commanders
    legendary_options = ['Legendary Creature', 'Legendary Artifact', 'Legendary Artifact Creature',
                        'Legendary Enchantment Creature', 'Legendary Planeswalker']
    df = df[df['type'].str.contains('|'.join(legendary_options), na=False)]

    # Check for 'can be your commander' text in non-creature legendaries
    non_creature_mask = ((df['type'].str.contains('Legendary Artifact', na=False) |
                         df['type'].str.contains('Legendary Planeswalker', na=False)) &
                        ~df['type'].str.contains('Creature', na=False))
    df = df[~non_creature_mask | df['text'].str.contains('can be your commander', na=False)]

    # Remove illegal sets and formats
    illegal_sets = ['PHTR', 'PH17', 'PH18', 'PH19', 'PH20', 'PH21', 'UGL', 'UND', 'UNH', 'UST']
    for illegal_set in illegal_sets:
        df = df[~df['printings'].str.contains(illegal_set, na=False)]

    logger.info("Commander eligibility validation complete")
    return df

def filter_commander_cards(df: pd.DataFrame) -> pd.DataFrame:
    """Filter cards based on commander-specific requirements.

    Args:
        df: DataFrame to filter

    Returns:
        Filtered DataFrame containing only valid commander cards
    """
    logger.info("Filtering commander cards...")

    # Validate commander eligibility
    df = validate_commander_eligibility(df)

    # Process with commander-specific columns and skip availability checks
    df = process_card_dataframe(df, include_commander_cols=True, skip_availability_checks=True)

    # Apply commander-specific banned list and filters
    df = filter_banned_cards(df)
    df = filter_card_types(df)

    logger.info("Commander card filtering complete")
    return df

def filter_card_dataframe(df: pd.DataFrame,
                         column_name: str,
                         value: Union[str, List[str]],
                         new_csv_name: str) -> None:
    """Filter DataFrame and save to CSV.

    Args:
        df: DataFrame to filter
        column_name: Column to filter on
        value: Value(s) to filter for
        new_csv_name: Output CSV file name
    """
    logger.info(f"Filtering DataFrame for {column_name}={value}")

    # Filter DataFrame
    filtered_df = df[df[column_name] == value]

    # Process filtered DataFrame - skip availability checks since they're already done
    filtered_df = process_card_dataframe(filtered_df, skip_availability_checks=True)

    # Save to CSV
    filtered_df.to_csv(new_csv_name, index=False)
    logger.info(f"Saved filtered DataFrame to {new_csv_name}")