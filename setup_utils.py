from __future__ import annotations

import pandas as pd
import requests
import logging
from tqdm import tqdm
from pathlib import Path
from typing import List, Optional, Union

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
    """Apply standard filters to the cards DataFrame.

    Args:
        df: DataFrame to filter
        banned_cards: List of banned card names to exclude

    Returns:
        Filtered DataFrame

    Raises:
        DataFrameProcessingError: If filtering operations fail
    """
    try:
        # Fill null color identities
        df['colorIdentity'] = df['colorIdentity'].fillna('Colorless')
        
        # Basic filters
        filtered_df = df[
            (df['layout'] != 'reversible_card') &
            (df['availability'].str.contains('paper', na=False)) &
            (df['promoTypes'] != 'playtest') &
            (~df['securityStamp'].str.contains('Heart|Acorn', na=False))
        ]
        
        # Remove illegal sets
        for set_code in NON_LEGAL_SETS:
            filtered_df = filtered_df[
                ~filtered_df['printings'].str.contains(set_code, na=False)
            ]

        # Remove banned cards
        for card in banned_cards:
            filtered_df = filtered_df[~filtered_df['name'].str.contains(card, na=False)]

        # Remove special card types
        for card_type in CARD_TYPES_TO_EXCLUDE:
            filtered_df = filtered_df[~filtered_df['type'].str.contains(card_type, na=False)]

        # Handle face names and duplicates
        filtered_df['faceName'] = filtered_df['faceName'].fillna(filtered_df['name'])
        filtered_df = filtered_df.drop_duplicates(subset='faceName', keep='first')

        # Select and sort columns
        filtered_df = filtered_df[CSV_PROCESSING_COLUMNS]
        
        return filtered_df.sort_values(by=['name', 'side'], 
                                     key=lambda col: col.str.lower())

    except Exception as e:
        raise DataFrameProcessingError(
            "Failed to filter DataFrame",
            "standard_filtering",
            str(e)
        ) from e

def process_legendary_cards(df: pd.DataFrame) -> pd.DataFrame:
    """Process and filter legendary cards for commander eligibility.

    Args:
        df: DataFrame containing all cards

    Returns:
        DataFrame containing only commander-eligible cards

    Raises:
        DataFrameProcessingError: If processing fails
    """
    try:
        # Filter for legendary creatures and eligible cards
        mask = df['type'].str.contains('|'.join(LEGENDARY_OPTIONS), na=False)
        
        # Add cards that can be commanders
        can_be_commander = df['text'].str.contains(
            'can be your commander', 
            na=False
        )
        
        filtered_df = df[mask | can_be_commander].copy()

        # Remove illegal sets
        for set_code in NON_LEGAL_SETS:
            filtered_df = filtered_df[
                ~filtered_df['printings'].str.contains(set_code, na=False)
            ]

        return filtered_df

    except Exception as e:
        raise DataFrameProcessingError(
            "Failed to process legendary cards",
            "commander_processing",
            str(e)
        ) from e