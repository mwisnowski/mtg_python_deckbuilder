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

import json
import os
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from .data_loader import DataLoader, validate_schema
from .setup_constants import (
    CSV_PROCESSING_COLUMNS,
    CARD_TYPES_TO_EXCLUDE,
    NON_LEGAL_SETS,
    FILTER_CONFIG,
    SORT_CONFIG,
)
from .setup_utils import _load_banned_cards
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
    banned_set = {b.casefold() for b in _load_banned_cards()}
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
    
    # printingCount: number of distinct printings (derived from printings column)
    df['printingCount'] = df['printings'].fillna('').apply(
        lambda x: len([s for s in x.split(',') if s.strip()])
    )
    # isReprint: True if card has been printed more than once
    df['isReprint'] = df['printingCount'] > 1

    # Reorder columns to match CARD_DATA_COLUMNS
    # CARD_DATA_COLUMNS has: name, faceName, edhrecRank, colorIdentity, colors,
    #                        manaCost, manaValue, type, creatureTypes, text,
    #                        power, toughness, keywords, themeTags, layout, side
    # We need to add isCommander, isBackground, printings, printingCount, isReprint at the end
    final_columns = settings.CARD_DATA_COLUMNS + ['isCommander', 'isBackground', 'printings', 'printingCount', 'isReprint']
    
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

    # Step 1b: Download Scryfall bulk data and refresh card lists (banned + game changers)
    # Must run before process_raw_parquet so the dynamic banned list is ready for filtering.
    bulk_path = os.path.join(raw_dir, "scryfall_bulk_data.json")
    try:
        from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient
        logger.info("Downloading fresh Scryfall bulk data …")
        client = ScryfallBulkDataClient()
        info = client.get_bulk_data_info()
        client.download_bulk_data(info["download_uri"], bulk_path)
        refresh_card_lists_from_bulk(bulk_path)
    except Exception as exc:
        logger.warning(f"Could not refresh card lists from bulk data ({exc}). Using existing lists.")

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


def _compute_is_new_from_bulk(bulk_path: str, window_months: int, today) -> "frozenset[str]":
    """Return a frozenset of lowercase card names that qualify as 'new'.

    A card is new when all of:
    - released_at <= today (no spoilers)
    - reprint == False (first printing only)
    - set belongs to last 3 expansion windows OR released_at >= today - window_months months
    """
    import json
    import datetime

    if not os.path.exists(bulk_path):
        return frozenset()

    rolling_cutoff = today - datetime.timedelta(days=window_months * 30)

    # Pass 1: determine last 3 expansion windows (expansion + commander precons)
    expansion_sets: dict = {}
    try:
        with open(bulk_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue
                st = card.get("set_type", "")
                sc = card.get("set", "")
                ra = card.get("released_at", "")
                if st in ("expansion", "commander") and ra and sc and sc not in expansion_sets:
                    try:
                        d = datetime.date.fromisoformat(ra)
                        if d <= today:
                            expansion_sets[sc] = d
                    except ValueError:
                        pass
    except Exception:
        pass

    all_dates = sorted(set(expansion_sets.values()), reverse=True)
    window_dates = set(all_dates[:3])
    window_set_codes = frozenset(sc for sc, d in expansion_sets.items() if d in window_dates)

    # Pass 2: collect card names that match the new-card criteria
    new_names: set = set()
    try:
        with open(bulk_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = card.get("name", "")
                ra = card.get("released_at", "")
                reprint = card.get("reprint", True)
                sc = card.get("set", "")
                if not name or not ra or reprint:
                    continue
                try:
                    card_date = datetime.date.fromisoformat(ra)
                except ValueError:
                    continue
                if card_date > today:
                    continue
                # For set-based window: require the card's own released_at matches the
                # set's registered window date.  This prevents mixed-date sets (e.g. FIC
                # which has cards at both 2025-06-13 and 2025-12-05) from pulling in old
                # cards just because a newer batch in the same set code hit the window.
                in_set_window = (sc in window_set_codes and card_date == expansion_sets.get(sc))
                if in_set_window or card_date >= rolling_cutoff:
                    lower = name.lower()
                    new_names.add(lower)
                    if " // " in name:  # also index each DFC face
                        for face in name.split(" // "):
                            new_names.add(face.strip().lower())
    except Exception:
        pass

    return frozenset(new_names)


_new_card_names_cache: "tuple[float, frozenset] | None" = None


def refresh_card_lists_from_bulk(bulk_path: str, output_func=None) -> None:
    """Scan the local Scryfall bulk data and update card list JSON files.

    Writes (or overwrites) two files:
    - ``config/card_lists/game_changers.json`` — cards where ``game_changer == True``
    - ``config/card_lists/banned_cards.json``  — cards where ``legalities.commander == "banned"``

    This keeps both lists in sync with Scryfall without manual maintenance.
    Called automatically during ``refresh_prices_parquet()`` which already downloads
    a fresh copy of the bulk data.

    Args:
        bulk_path: Path to the local Scryfall bulk data JSON file.
        output_func: Optional callable(str) for progress messages.
    """
    import datetime as _dt

    _log = output_func or (lambda msg: logger.info(msg))

    if not os.path.exists(bulk_path):
        _log("Warning: Scryfall bulk data not found — skipping card list refresh.")
        return

    _log("Refreshing card lists from Scryfall bulk data …")
    game_changers: set[str] = set()
    banned: set[str] = set()

    try:
        with open(bulk_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue

                name: str = card.get("name", "")
                if not name:
                    continue

                # Game Changers
                if card.get("game_changer") is True:
                    game_changers.add(name)

                # Commander banned list
                legalities = card.get("legalities") or {}
                if legalities.get("commander") == "banned":
                    banned.add(name)

    except Exception as exc:
        _log(f"Warning: Error scanning bulk data for card lists ({exc}). Skipping.")
        return

    now_iso = _dt.datetime.utcnow().strftime("%Y-%m-%d")

    # Write game_changers.json
    gc_path = Path("config/card_lists/game_changers.json")
    try:
        gc_path.parent.mkdir(parents=True, exist_ok=True)
        gc_data = {
            "cards": sorted(game_changers),
            "list_version": f"scryfall-{now_iso}",
            "generated_at": now_iso,
            "source": "scryfall bulk data (game_changer field)",
        }
        gc_path.write_text(json.dumps(gc_data, indent=2, ensure_ascii=False), encoding="utf-8")
        _log(f"Updated game_changers.json — {len(game_changers)} cards.")
    except Exception as exc:
        _log(f"Warning: Could not write game_changers.json ({exc}).")

    # Write banned_cards.json
    ban_path = Path("config/card_lists/banned_cards.json")
    try:
        ban_data = {
            "cards": sorted(banned),
            "list_version": f"scryfall-{now_iso}",
            "generated_at": now_iso,
            "source": "scryfall bulk data (legalities.commander == banned)",
        }
        ban_path.write_text(json.dumps(ban_data, indent=2, ensure_ascii=False), encoding="utf-8")
        _log(f"Updated banned_cards.json — {len(banned)} cards.")
    except Exception as exc:
        _log(f"Warning: Could not write banned_cards.json ({exc}).")


def get_new_card_names() -> "frozenset[str]":
    """Return a frozenset of lowercase names currently marked isNew in parquet.
    Cached for 1 hour so repeated template calls are cheap.
    """
    import time
    global _new_card_names_cache
    now = time.time()
    if _new_card_names_cache is not None and (now - _new_card_names_cache[0]) < 3600.0:
        return _new_card_names_cache[1]
    try:
        processed_path = get_processed_cards_path()
        if not os.path.exists(processed_path):
            return frozenset()
        df = pd.read_parquet(processed_path)
        if "isNew" not in df.columns:
            return frozenset()
        name_col = "faceName" if "faceName" in df.columns else "name"
        mask = df["isNew"].fillna(False).astype(bool)
        names = frozenset(df.loc[mask, name_col].dropna().str.lower().tolist())
        _new_card_names_cache = (now, names)
        return names
    except Exception:
        return frozenset()


def refresh_prices_parquet(output_func=None) -> None:
    """Rebuild the price cache from local Scryfall bulk data and write
    ``price`` / ``priceUpdated`` / ``scryfallID`` / ``ckPrice`` / ``ckPriceUpdated`` columns into all_cards.parquet and
    commander_cards.parquet.

    This is safe to call from both the web app and CLI contexts.

    Args:
        output_func: Optional callable(str) for progress messages.  Defaults
            to the module logger.
    """
    import datetime
    from code.web.services.price_service import get_price_service

    _log = output_func or (lambda msg: logger.info(msg))

    # Download a fresh copy of the Scryfall bulk data before rebuilding,
    # but skip the network fetch if initial_setup already downloaded it recently (< 1 h).
    import time as _time
    try:
        from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient
        from code.path_util import card_files_raw_dir
        bulk_path = os.path.join(card_files_raw_dir(), "scryfall_bulk_data.json")
        _bulk_age_h = ((_time.time() - os.path.getmtime(bulk_path)) / 3600) if os.path.exists(bulk_path) else None
        if _bulk_age_h is None or _bulk_age_h > 1:
            _log("Downloading fresh Scryfall bulk data …")
            client = ScryfallBulkDataClient()
            info = client.get_bulk_data_info()
            client.download_bulk_data(info["download_uri"], bulk_path)
            _log("Scryfall bulk data downloaded.")
        else:
            _log(f"Scryfall bulk data is fresh ({_bulk_age_h:.1f}h old) — skipping re-download.")
    except Exception as exc:
        _log(f"Warning: Could not download fresh bulk data ({exc}). Using existing local copy.")

    # Refresh game_changers.json and banned_cards.json from the fresh bulk data.
    try:
        refresh_card_lists_from_bulk(bulk_path, output_func=_log)
    except Exception as exc:
        _log(f"Warning: Card list refresh failed ({exc}). Existing lists unchanged.")

    _log("Rebuilding price cache from Scryfall bulk data …")
    svc = get_price_service()
    svc._rebuild_cache()

    processed_path = get_processed_cards_path()
    if not os.path.exists(processed_path):
        _log("No processed parquet found — run Setup first.")
        return

    _log("Loading card database …")
    df = pd.read_parquet(processed_path)
    name_col = "faceName" if "faceName" in df.columns else "name"
    card_names = df[name_col].fillna("").tolist()

    # --- scryfallID column (from the map populated during _rebuild_cache) ---
    scryfall_id_map = getattr(svc, "_scryfall_id_map", {})
    if scryfall_id_map:
        df["scryfallID"] = df[name_col].map(lambda n: scryfall_id_map.get(n.lower()) if n else None)
        mapped = df["scryfallID"].notna().sum()
        _log(f"Added scryfallID column — {mapped:,} of {len(card_names):,} cards mapped.")
    else:
        _log("Warning: scryfallID map empty; skipping scryfallID column.")

    # --- TCGPlayer (Scryfall) prices ---
    _log(f"Fetching TCGPlayer prices for {len(card_names):,} cards …")
    prices = svc.get_prices_batch(card_names)
    priced = sum(1 for p in prices.values() if p is not None)

    now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    df["price"] = df[name_col].map(lambda n: prices.get(n) if n else None)
    df["priceUpdated"] = now_iso

    # --- Card Kingdom prices ---
    _log("Fetching Card Kingdom price list …")
    try:
        svc._rebuild_ck_cache()
        ck_prices = svc.get_ck_prices_batch(card_names)
        ck_priced = sum(1 for p in ck_prices.values() if p is not None)
        df["ckPrice"] = df[name_col].map(lambda n: ck_prices.get(n) if n else None)
        df["ckPriceUpdated"] = now_iso
        _log(f"Added ckPrice column — {ck_priced:,} of {len(card_names):,} cards priced.")
    except Exception as exc:
        _log(f"Warning: CK price fetch failed ({exc}). Skipping ckPrice column.")

    # --- isNew / isNewUpdated columns (new-card detection window) ---
    import datetime as _dt
    try:
        _today = _dt.date.today()
        _window_months = int(os.environ.get("UPGRADE_WINDOW_MONTHS", "6"))
        _is_new = _compute_is_new_from_bulk(bulk_path, _window_months, _today)
        df["isNew"] = df[name_col].fillna("").str.lower().isin(_is_new)
        df["isNewUpdated"] = _today.isoformat()
        _log(f"Added isNew column — {int(df['isNew'].sum()):,} new cards in window.")
    except Exception as _exc:
        _log(f"Warning: Could not compute isNew column ({_exc}). Setting to False.")
        df["isNew"] = False
        df["isNewUpdated"] = ""

    loader = DataLoader()
    loader.write_cards(df, processed_path)
    _log(f"Updated all_cards.parquet — {priced:,} of {len(card_names):,} cards priced (TCGPlayer).")

    # Update commander_cards.parquet by applying the same price columns.
    processed_dir = os.path.dirname(processed_path)
    commander_path = os.path.join(processed_dir, "commander_cards.parquet")
    if os.path.exists(commander_path) and "isCommander" in df.columns:
        cmd_df = df[df["isCommander"] == True].copy()  # noqa: E712
        loader.write_cards(cmd_df, commander_path)
        _log(f"Updated commander_cards.parquet ({len(cmd_df):,} commanders).")

    _log("Price refresh complete.")


def run_full_pipeline(output_func=None, parallel: bool = True) -> None:
    """Run the complete local setup pipeline in the correct order.

    Steps (must run in this sequence):
    1. initial_setup()        — download MTGJSON parquet + process
    2. run_tagging()          — tag all cards (must precede prices)
    3. refresh_prices_parquet() — write price / isNew columns into parquet
    4. build_cache()          — pre-compute similarity cache

    Use this instead of calling each step individually.  The web orchestrator
    runs the steps separately for fine-grained progress reporting; all other
    entry points (CLI, headless, dev commands) should call this function.

    Args:
        output_func: Optional callable(str) for progress messages.
        parallel: Use parallel processing for tagging and similarity cache.
    """
    _log = output_func or (lambda msg: logger.info(msg))

    _log("=" * 70)
    _log("Starting full setup pipeline")
    _log("=" * 70)

    # Step 1: download + process raw parquet
    _log("[1/4] Running initial setup (download + process)...")
    initial_setup()
    _log("✓ Initial setup complete")

    # Step 2: tag all cards (must come before prices)
    _log(f"[2/4] Running tagging (parallel={parallel})...")
    from code.tagging.tagger import run_tagging
    run_tagging(parallel=parallel)
    _log("✓ Tagging complete")

    # Step 3: refresh prices + isNew (must come after tagging)
    _log("[3/4] Refreshing prices and isNew window...")
    refresh_prices_parquet(output_func=output_func)
    _log("✓ Prices and isNew refreshed")

    # Step 4: build similarity cache
    _log(f"[4/4] Building similarity cache (parallel={parallel})...")
    from code.scripts.build_similarity_cache_parquet import build_cache
    build_cache(parallel=parallel, checkpoint_interval=1000, force=True)
    _log("✓ Similarity cache built")

    _log("=" * 70)
    _log("Full pipeline complete")
    _log("=" * 70)
