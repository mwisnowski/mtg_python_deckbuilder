"""Parquet-based setup for MTG Python Deckbuilder.

This module handles downloading and processing MTGJSON Parquet data for the
MTG Python Deckbuilder. It replaces the old CSV-based multi-file approach
with a single-file Parquet workflow.

Key Changes from CSV approach:
- Single all_cards.parquet file instead of 18+ color-specific CSVs
- Downloads from MTGJSON Parquet API (faster, smaller)
- Adds isCommander and isBackground boolean flags
- Filters to essential columns only (14 base + 4 custom = 18 total)
- Uses DataLoader abstraction for format flexibility

Introduced in v3.0.0 as part of CSV→Parquet migration.
"""

from __future__ import annotations

import os

import pandas as pd
import requests
from tqdm import tqdm

from .data_loader import DataLoader, validate_schema
from .setup_constants import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    BANNED_CARDS,
    FILTER_CONFIG,
    SORT_CONFIG,
)
import logging_util
from path_util import card_files_raw_dir, get_processed_cards_path
import settings

logger = logging_util.get_logger(__name__)

# MTGJSON Parquet API URL
MTGJSON_PARQUET_URL = "https://mtgjson.com/api/v5/parquet/cards.parquet"


def download_parquet_from_mtgjson(output_path: str) -> None:
    """Download MTGJSON cards.parquet file.
    
    Args:
        output_path: Where to save the downloaded Parquet file
        
    Raises:
        requests.RequestException: If download fails
        IOError: If file cannot be written
    """
    logger.info(f"Downloading MTGJSON Parquet from {MTGJSON_PARQUET_URL}")
    
    try:
        response = requests.get(MTGJSON_PARQUET_URL, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get file size for progress bar
        total_size = int(response.headers.get('content-length', 0))
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Download with progress bar
        with open(output_path, 'wb') as f, tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            desc='Downloading cards.parquet'
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                pbar.update(len(chunk))
        
        logger.info(f"✓ Downloaded {total_size / (1024**2):.2f} MB to {output_path}")
        
    except requests.RequestException as e:
        logger.error(f"Failed to download MTGJSON Parquet: {e}")
        raise
    except IOError as e:
        logger.error(f"Failed to write Parquet file: {e}")
        raise


def is_valid_commander(row: pd.Series) -> bool:
    """Determine if a card can be a commander.
    
    Criteria:
    - Legendary Creature
    - OR: Has "can be your commander" in text
    - OR: Background (Partner with Background)
    
    Args:
        row: DataFrame row with card data
        
    Returns:
        True if card can be a commander
    """
    type_line = str(row.get('type', ''))
    text = str(row.get('text', '')).lower()
    
    # Legendary Creature
    if 'Legendary' in type_line and 'Creature' in type_line:
        return True
    
    # Special text (e.g., "can be your commander")
    if 'can be your commander' in text:
        return True
    
    # Backgrounds can be commanders (with Choose a Background)
    if 'Background' in type_line:
        return True
    
    return False


def is_background(row: pd.Series) -> bool:
    """Determine if a card is a Background.
    
    Args:
        row: DataFrame row with card data
        
    Returns:
        True if card has Background type
    """
    type_line = str(row.get('type', ''))
    return 'Background' in type_line


def extract_creature_types(row: pd.Series) -> str:
    """Extract creature types from type line.
    
    Args:
        row: DataFrame row with card data
        
    Returns:
        Comma-separated creature types or empty string
    """
    type_line = str(row.get('type', ''))
    
    # Check if it's a creature
    if 'Creature' not in type_line:
        return ''
    
    # Split on — to get subtypes
    if '—' in type_line:
        parts = type_line.split('—')
        if len(parts) >= 2:
            # Get everything after the dash, strip whitespace
            subtypes = parts[1].strip()
            return subtypes
    
    return ''


def process_raw_parquet(raw_path: str, output_path: str) -> pd.DataFrame:
    """Process raw MTGJSON Parquet into processed all_cards.parquet.
    
    This function:
    1. Loads raw Parquet (all ~82 columns)
    2. Filters to essential columns (CSV_PROCESSING_COLUMNS)
    3. Applies standard filtering (banned cards, illegal sets, special types)
    4. Deduplicates by faceName (keep first printing only)
    5. Adds custom columns: creatureTypes, themeTags, isCommander, isBackground
    6. Validates schema
    7. Writes to processed directory
    
    Args:
        raw_path: Path to raw cards.parquet from MTGJSON
        output_path: Path to save processed all_cards.parquet
        
    Returns:
        Processed DataFrame
        
    Raises:
        ValueError: If schema validation fails
    """
    logger.info(f"Processing {raw_path}")
    
    # Load raw Parquet with DataLoader
    loader = DataLoader()
    df = loader.read_cards(raw_path)
    
    logger.info(f"Loaded {len(df)} cards with {len(df.columns)} columns")
    
    # Step 1: Fill NA values
    logger.info("Filling NA values")
    for col, fill_value in settings.FILL_NA_COLUMNS.items():
        if col in df.columns:
            if col == 'faceName':
                df[col] = df[col].fillna(df['name'])
            else:
                df[col] = df[col].fillna(fill_value)
    
    # Step 2: Apply configuration-based filters (FILTER_CONFIG)
    logger.info("Applying configuration filters")
    for field, rules in FILTER_CONFIG.items():
        if field not in df.columns:
            logger.warning(f"Skipping filter for missing field: {field}")
            continue
        
        for rule_type, values in rules.items():
            if not values:
                continue
            
            if rule_type == 'exclude':
                for value in values:
                    mask = df[field].astype(str).str.contains(value, case=False, na=False, regex=False)
                    before = len(df)
                    df = df[~mask]
                    logger.debug(f"Excluded {field} containing '{value}': {before - len(df)} removed")
            elif rule_type == 'require':
                for value in values:
                    mask = df[field].astype(str).str.contains(value, case=False, na=False, regex=False)
                    before = len(df)
                    df = df[mask]
                    logger.debug(f"Required {field} containing '{value}': {before - len(df)} removed")
    
    # Step 3: Remove illegal sets
    if 'printings' in df.columns:
        logger.info("Removing illegal sets")
        for set_code in NON_LEGAL_SETS:
            before = len(df)
            df = df[~df['printings'].str.contains(set_code, na=False)]
            if len(df) < before:
                logger.debug(f"Removed set {set_code}: {before - len(df)} cards")
    
    # Step 4: Remove banned cards
    logger.info("Removing banned cards")
    banned_set = {b.casefold() for b in BANNED_CARDS}
    name_lc = df['name'].astype(str).str.casefold()
    face_lc = df['faceName'].astype(str).str.casefold() if 'faceName' in df.columns else name_lc
    mask = ~(name_lc.isin(banned_set) | face_lc.isin(banned_set))
    before = len(df)
    df = df[mask]
    logger.debug(f"Removed banned cards: {before - len(df)} filtered out")
    
    # Step 5: Remove special card types
    logger.info("Removing special card types")
    for card_type in CARD_TYPES_TO_EXCLUDE:
        before = len(df)
        df = df[~df['type'].str.contains(card_type, na=False)]
        if len(df) < before:
            logger.debug(f"Removed type {card_type}: {before - len(df)} cards")
    
    # Step 6: Filter to essential columns only (reduce from ~82 to 14)
    logger.info(f"Filtering to {len(CSV_PROCESSING_COLUMNS)} essential columns")
    df = df[CSV_PROCESSING_COLUMNS]
    
    # Step 7: Sort and deduplicate (CRITICAL: keeps only one printing per unique card)
    logger.info("Sorting and deduplicating cards")
    df = df.sort_values(
        by=SORT_CONFIG['columns'],
        key=lambda col: col.str.lower() if not SORT_CONFIG['case_sensitive'] else col
    )
    before = len(df)
    df = df.drop_duplicates(subset='faceName', keep='first')
    logger.info(f"Deduplicated: {before} → {len(df)} cards ({before - len(df)} duplicate printings removed)")
    
    # Step 8: Add custom columns
    logger.info("Adding custom columns: creatureTypes, themeTags, isCommander, isBackground")
    
    # creatureTypes: extracted from type line
    df['creatureTypes'] = df.apply(extract_creature_types, axis=1)
    
    # themeTags: empty placeholder (filled during tagging)
    df['themeTags'] = ''
    
    # isCommander: boolean flag
    df['isCommander'] = df.apply(is_valid_commander, axis=1)
    
    # isBackground: boolean flag
    df['isBackground'] = df.apply(is_background, axis=1)
    
    # Reorder columns to match CARD_DATA_COLUMNS
    # CARD_DATA_COLUMNS has: name, faceName, edhrecRank, colorIdentity, colors,
    #                        manaCost, manaValue, type, creatureTypes, text,
    #                        power, toughness, keywords, themeTags, layout, side
    # We need to add isCommander and isBackground at the end
    final_columns = settings.CARD_DATA_COLUMNS + ['isCommander', 'isBackground']
    
    # Ensure all columns exist
    for col in final_columns:
        if col not in df.columns:
            logger.warning(f"Column {col} missing, adding empty column")
            df[col] = ''
    
    df = df[final_columns]
    
    logger.info(f"Final dataset: {len(df)} cards, {len(df.columns)} columns")
    logger.info(f"Commanders: {df['isCommander'].sum()}")
    logger.info(f"Backgrounds: {df['isBackground'].sum()}")
    
    # Validate schema (check required columns present)
    try:
        validate_schema(df)
        logger.info("✓ Schema validation passed")
    except ValueError as e:
        logger.error(f"Schema validation failed: {e}")
        raise
    
    # Write to processed directory
    logger.info(f"Writing processed Parquet to {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    loader.write_cards(df, output_path)
    
    logger.info(f"✓ Created {output_path}")
    
    return df


def initial_setup() -> None:
    """Download and process MTGJSON Parquet data.
    
    Modern Parquet-based setup workflow (replaces legacy CSV approach).
    
    Workflow:
    1. Download cards.parquet from MTGJSON → card_files/raw/cards.parquet
    2. Process and filter → card_files/processed/all_cards.parquet
    3. No color-specific files (filter at query time instead)
    
    Raises:
        Various exceptions from download/processing steps
    """
    logger.info("=" * 80)
    logger.info("Starting Parquet-based initial setup")
    logger.info("=" * 80)
    
    # Step 1: Download raw Parquet
    raw_dir = card_files_raw_dir()
    raw_path = os.path.join(raw_dir, "cards.parquet")
    
    if os.path.exists(raw_path):
        logger.info(f"Raw Parquet already exists: {raw_path}")
        logger.info("Skipping download (delete file to re-download)")
    else:
        download_parquet_from_mtgjson(raw_path)
    
    # Step 2: Process raw → processed
    processed_path = get_processed_cards_path()
    
    logger.info(f"Processing raw Parquet → {processed_path}")
    process_raw_parquet(raw_path, processed_path)
    
    logger.info("=" * 80)
    logger.info("✓ Parquet setup complete")
    logger.info(f"  Raw: {raw_path}")
    logger.info(f"  Processed: {processed_path}")
    logger.info("=" * 80)
    
    # Step 3: Optional image caching (if enabled)
    try:
        from code.file_setup.image_cache import ImageCache
        cache = ImageCache()
        
        if cache.is_enabled():
            logger.info("=" * 80)
            logger.info("Card image caching enabled - starting download")
            logger.info("=" * 80)
            
            # Download bulk data
            logger.info("Downloading Scryfall bulk data...")
            cache.download_bulk_data()
            
            # Download images
            logger.info("Downloading card images (this may take 1-2 hours)...")
            
            def progress(current, total, card_name):
                if current % 100 == 0:  # Log every 100 cards
                    pct = (current / total) * 100
                    logger.info(f"  Progress: {current}/{total} ({pct:.1f}%) - {card_name}")
            
            stats = cache.download_images(progress_callback=progress)
            
            logger.info("=" * 80)
            logger.info("✓ Image cache complete")
            logger.info(f"  Downloaded: {stats['downloaded']}")
            logger.info(f"  Skipped: {stats['skipped']}")
            logger.info(f"  Failed: {stats['failed']}")
            logger.info("=" * 80)
        else:
            logger.info("Card image caching disabled (CACHE_CARD_IMAGES=0)")
            logger.info("Images will be fetched from Scryfall API on demand")
            
    except Exception as e:
        logger.error(f"Failed to cache images (continuing anyway): {e}")
        logger.error("Images will be fetched from Scryfall API on demand")


def regenerate_processed_parquet() -> None:
    """Regenerate processed Parquet from existing raw file.
    
    Useful when:
    - Column processing logic changes
    - Adding new custom columns
    - Testing without re-downloading
    """
    logger.info("Regenerating processed Parquet from raw file")
    
    raw_path = os.path.join(card_files_raw_dir(), "cards.parquet")
    
    if not os.path.exists(raw_path):
        logger.error(f"Raw Parquet not found: {raw_path}")
        logger.error("Run initial_setup_parquet() first to download")
        raise FileNotFoundError(f"Raw Parquet not found: {raw_path}")
    
    processed_path = get_processed_cards_path()
    process_raw_parquet(raw_path, processed_path)
    
    logger.info(f"✓ Regenerated {processed_path}")
