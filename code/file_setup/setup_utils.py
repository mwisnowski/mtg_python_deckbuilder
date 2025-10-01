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
import requests
from pathlib import Path
from typing import List, Optional, Union, TypedDict

# Third-party imports
import pandas as pd
from tqdm import tqdm

# Local application imports
from .setup_constants import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    SORT_CONFIG,
    FILTER_CONFIG,
    COLUMN_ORDER,
    TAGGED_COLUMN_ORDER,
    SETUP_COLORS,
    COLOR_ABRV,
    BANNED_CARDS,
)
from exceptions import (
    MTGJSONDownloadError,
    DataFrameProcessingError,
    ColorFilterError,
    CommanderValidationError
)
from type_definitions import CardLibraryDF
from settings import FILL_NA_COLUMNS
import logging_util

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

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

def save_color_filtered_csvs(df: pd.DataFrame, out_dir: Union[str, Path]) -> None:
    """Generate and save color-identity filtered CSVs for all configured colors.

    Iterates across configured color names and their corresponding color identity
    abbreviations, filters the provided DataFrame using standard filters plus
    color identity, and writes each filtered set to CSV in the provided directory.

    Args:
        df: Source DataFrame containing card data.
        out_dir: Output directory for the generated CSV files.

    Raises:
        DataFrameProcessingError: If filtering fails.
        ColorFilterError: If color filtering fails for a specific color.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Base-filter once for efficiency, then per-color filter without redoing base filters
    try:
        # Apply full standard filtering including banned list once, then slice per color
        base_df = filter_dataframe(df, BANNED_CARDS)
    except Exception as e:
        # Wrap any unexpected issues as DataFrameProcessingError
        raise DataFrameProcessingError(
            "Failed to prepare base DataFrame for color filtering",
            "base_color_filtering",
            str(e)
        ) from e

    for color_name, color_id in zip(SETUP_COLORS, COLOR_ABRV):
        try:
            logger.info(f"Generating {color_name}_cards.csv")
            color_df = base_df[base_df['colorIdentity'] == color_id]
            color_df.to_csv(out_path / f"{color_name}_cards.csv", index=False)
        except Exception as e:
            raise ColorFilterError(
                "Failed to generate color CSV",
                color_id,
                str(e)
            ) from e

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
            if field not in filtered_df.columns:
                logger.warning('Skipping filter for missing field %s', field)
                continue

            for rule_type, values in rules.items():
                if not values:
                    continue

                if rule_type == 'exclude':
                    for value in values:
                        mask = filtered_df[field].astype(str).str.contains(
                            value,
                            case=False,
                            na=False,
                            regex=False
                        )
                        filtered_df = filtered_df[~mask]
                elif rule_type == 'require':
                    for value in values:
                        mask = filtered_df[field].astype(str).str.contains(
                            value,
                            case=False,
                            na=False,
                            regex=False
                        )
                        filtered_df = filtered_df[mask]
                else:
                    logger.warning('Unknown filter rule type %s for field %s', rule_type, field)
                    continue

                logger.debug(f'Applied {rule_type} filter for {field}: {values}')
        
        # Remove illegal sets
        for set_code in NON_LEGAL_SETS:
            filtered_df = filtered_df[~filtered_df['printings'].str.contains(set_code, na=False)]
        logger.debug('Removed illegal sets')

        # Remove banned cards (exact, case-insensitive match on name or faceName)
        if banned_cards:
            banned_set = {b.casefold() for b in banned_cards}
            name_lc = filtered_df['name'].astype(str).str.casefold()
            face_lc = filtered_df['faceName'].astype(str).str.casefold()
            mask = ~(name_lc.isin(banned_set) | face_lc.isin(banned_set))
            before = len(filtered_df)
            filtered_df = filtered_df[mask]
            after = len(filtered_df)
            logger.debug(f'Removed banned cards: {before - after} filtered out')

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
            filtered_df = filter_dataframe(df, BANNED_CARDS)
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
                # Normalize type line for matching
                type_line = filtered_df['type'].astype(str).str.lower()

                # Base predicates
                is_legendary = type_line.str.contains('legendary')
                is_creature = type_line.str.contains('creature')
                # Planeswalkers are only eligible if they explicitly state they can be your commander (handled in special cases step)
                is_enchantment = type_line.str.contains('enchantment')
                is_artifact = type_line.str.contains('artifact')
                is_vehicle_or_spacecraft = type_line.str.contains('vehicle') | type_line.str.contains('spacecraft')

                # 1. Always allow Legendary Creatures (includes artifact/enchantment creatures already)
                allow_legendary_creature = is_legendary & is_creature

                # 2. Allow Legendary Enchantment Creature (already covered by legendary creature) – ensure no plain legendary enchantments without creature type slip through
                allow_enchantment_creature = is_legendary & is_enchantment & is_creature

                # 3. Allow certain Legendary Artifacts:
                #    a) Vehicles/Spacecraft that have printed power & toughness
                has_power_toughness = filtered_df['power'].notna() & filtered_df['toughness'].notna()
                allow_artifact_vehicle = is_legendary & is_artifact & is_vehicle_or_spacecraft & has_power_toughness

                # (Artifacts or planeswalkers with explicit permission text will be added in special cases step.)

                baseline_mask = allow_legendary_creature | allow_enchantment_creature | allow_artifact_vehicle
                filtered_df = filtered_df[baseline_mask].copy()

                if filtered_df.empty:
                    raise CommanderValidationError(
                        "No baseline eligible commanders found",
                        "legendary_check",
                        "After applying commander rules no cards qualified"
                    )

                logger.debug(
                    "Baseline commander counts: total=%d legendary_creatures=%d enchantment_creatures=%d artifact_vehicles=%d", 
                    len(filtered_df),
                    int((allow_legendary_creature).sum()),
                    int((allow_enchantment_creature).sum()),
                    int((allow_artifact_vehicle).sum())
                )
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
                # Add any card (including planeswalkers, artifacts, non-legendary cards) that explicitly allow being a commander
                special_cases = df['text'].str.contains('can be your commander', na=False, case=False)
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
            # Even when skipping availability checks, still ensure columns_to_keep if provided
            if columns_to_keep is not None:
                try:
                    batch = batch[columns_to_keep]
                except Exception:
                    # If requested columns are not present, keep as-is
                    pass
            processed_dfs.append(batch)

    # Combine processed batches
    result = pd.concat(processed_dfs, ignore_index=True)

    # Final processing
    result.drop_duplicates(subset='faceName', keep='first', inplace=True)
    result.sort_values(by=['name', 'side'], key=lambda col: col.str.lower(), inplace=True)

    logger.info("DataFrame processing completed")
    return result

# Backward-compatibility wrapper used by deck_builder.builder
def regenerate_csvs_all() -> None:  # pragma: no cover - simple delegator
    """Delegate to setup.regenerate_csvs_all to preserve existing imports.

    Some modules import regenerate_csvs_all from setup_utils. Keep this
    function as a stable indirection to avoid breaking callers.
    """
    from . import setup as setup_module  # local import to avoid circular import
    setup_module.regenerate_csvs_all()
