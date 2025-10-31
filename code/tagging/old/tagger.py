from __future__ import annotations

# Standard library imports
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Union

# Third-party imports
import pandas as pd

# Local application imports
from . import regex_patterns as rgx
from . import tag_constants
from . import tag_utils
from .bracket_policy_applier import apply_bracket_policy_tags
from .colorless_filter_applier import apply_colorless_filter_tags
from .multi_face_merger import merge_multi_face_rows
import logging_util
from file_setup import setup
from file_setup.data_loader import DataLoader
from file_setup.setup_utils import enrich_commander_rows_with_tags
from settings import COLORS, CSV_DIRECTORY, MULTIPLE_COPY_CARDS
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# Create DataLoader instance for Parquet operations
_data_loader = DataLoader()


def _get_batch_id_for_color(color: str) -> int:
    """Get unique batch ID for a color (for parallel-safe batch writes).
    
    Args:
        color: Color name (e.g., 'white', 'blue', 'commander')
    
    Returns:
        Unique integer batch ID based on COLORS index
    """
    try:
        return COLORS.index(color)
    except ValueError:
        # Fallback for unknown colors (shouldn't happen)
        logger.warning(f"Unknown color '{color}', using hash-based batch ID")
        return hash(color) % 1000


_MERGE_FLAG_RAW = str(os.getenv("ENABLE_DFC_MERGE", "") or "").strip().lower()
if _MERGE_FLAG_RAW in {"0", "false", "off", "disabled"}:
    logger.warning(
        "ENABLE_DFC_MERGE=%s is deprecated and no longer disables the merge; multi-face merge is always enabled.",
        _MERGE_FLAG_RAW,
    )
elif _MERGE_FLAG_RAW:
    logger.info(
        "ENABLE_DFC_MERGE=%s detected (deprecated); multi-face merge now runs unconditionally.",
        _MERGE_FLAG_RAW,
    )

_COMPAT_FLAG_RAW = os.getenv("DFC_COMPAT_SNAPSHOT")
if _COMPAT_FLAG_RAW is not None:
    _COMPAT_FLAG_NORMALIZED = str(_COMPAT_FLAG_RAW or "").strip().lower()
    DFC_COMPAT_SNAPSHOT = _COMPAT_FLAG_NORMALIZED not in {"0", "false", "off", "disabled"}
else:
    DFC_COMPAT_SNAPSHOT = _MERGE_FLAG_RAW in {"compat", "dual", "both"}

_DFC_COMPAT_DIR = Path(os.getenv("DFC_COMPAT_DIR", "csv_files/compat_faces"))

_PER_FACE_SNAPSHOT_RAW = os.getenv("DFC_PER_FACE_SNAPSHOT")
if _PER_FACE_SNAPSHOT_RAW is not None:
    _PER_FACE_SNAPSHOT_NORMALIZED = str(_PER_FACE_SNAPSHOT_RAW or "").strip().lower()
    DFC_PER_FACE_SNAPSHOT = _PER_FACE_SNAPSHOT_NORMALIZED not in {"0", "false", "off", "disabled"}
else:
    DFC_PER_FACE_SNAPSHOT = False

_DFC_PER_FACE_SNAPSHOT_PATH = Path(os.getenv("DFC_PER_FACE_SNAPSHOT_PATH", "logs/dfc_per_face_snapshot.json"))
_PER_FACE_SNAPSHOT_BUFFER: Dict[str, List[Dict[str, Any]]] = {}


def _record_per_face_snapshot(color: str, payload: Dict[str, Any]) -> None:
    if not DFC_PER_FACE_SNAPSHOT:
        return
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return
    bucket = _PER_FACE_SNAPSHOT_BUFFER.setdefault(color, [])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        faces_data = []
        raw_faces = entry.get("faces")
        if isinstance(raw_faces, list):
            for face in raw_faces:
                if isinstance(face, dict):
                    faces_data.append({k: face.get(k) for k in (
                        "face",
                        "side",
                        "layout",
                        "type",
                        "text",
                        "mana_cost",
                        "mana_value",
                        "produces_mana",
                        "is_land",
                        "themeTags",
                        "roleTags",
                    )})
                else:
                    faces_data.append(face)
        primary_face = entry.get("primary_face")
        if isinstance(primary_face, dict):
            primary_face_copy = dict(primary_face)
        else:
            primary_face_copy = primary_face
        removed_faces = entry.get("removed_faces")
        if isinstance(removed_faces, list):
            removed_faces_copy = [dict(face) if isinstance(face, dict) else face for face in removed_faces]
        else:
            removed_faces_copy = removed_faces
        bucket.append(
            {
                "name": entry.get("name"),
                "total_faces": entry.get("total_faces"),
                "dropped_faces": entry.get("dropped_faces"),
                "layouts": list(entry.get("layouts", [])) if isinstance(entry.get("layouts"), list) else entry.get("layouts"),
                "primary_face": primary_face_copy,
                "faces": faces_data,
                "removed_faces": removed_faces_copy,
                "theme_tags": entry.get("theme_tags"),
                "role_tags": entry.get("role_tags"),
            }
        )


def _flush_per_face_snapshot() -> None:
    if not DFC_PER_FACE_SNAPSHOT:
        _PER_FACE_SNAPSHOT_BUFFER.clear()
        return
    if not _PER_FACE_SNAPSHOT_BUFFER:
        return
    try:
        colors_payload = {color: list(entries) for color, entries in _PER_FACE_SNAPSHOT_BUFFER.items()}
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "mode": "always_on",
            "compat_snapshot": bool(DFC_COMPAT_SNAPSHOT),
            "colors": colors_payload,
        }
        _DFC_PER_FACE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DFC_PER_FACE_SNAPSHOT_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        logger.info("Wrote per-face snapshot to %s", _DFC_PER_FACE_SNAPSHOT_PATH)
    except Exception as exc:
        logger.warning("Failed to write per-face snapshot: %s", exc)
    finally:
        _PER_FACE_SNAPSHOT_BUFFER.clear()


def _merge_summary_recorder(color: str):
    def _recorder(payload: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(payload)
        enriched["mode"] = "always_on"
        enriched["compat_snapshot"] = bool(DFC_COMPAT_SNAPSHOT)
        if DFC_PER_FACE_SNAPSHOT:
            _record_per_face_snapshot(color, payload)
        return enriched

    return _recorder


def _write_compat_snapshot(df: pd.DataFrame, color: str) -> None:
    try:
        _DFC_COMPAT_DIR.mkdir(parents=True, exist_ok=True)
        path = _DFC_COMPAT_DIR / f"{color}_cards_unmerged.csv"
        df.to_csv(path, index=False)
        logger.info("Wrote unmerged snapshot for %s to %s", color, path)
    except Exception as exc:
        logger.warning("Failed to write unmerged snapshot for %s: %s", color, exc)


def _classify_and_partition_tags(
    tags: List[str], 
    metadata_counts: Dict[str, int], 
    theme_counts: Dict[str, int]
) -> tuple[List[str], List[str], int, int]:
    """Classify tags as metadata or theme and update counters.
    
    Args:
        tags: List of tags to classify
        metadata_counts: Dict to track metadata tag counts
        theme_counts: Dict to track theme tag counts
        
    Returns:
        Tuple of (metadata_tags, theme_tags, metadata_moved, theme_kept)
    """
    metadata_tags = []
    theme_tags = []
    metadata_moved = 0
    theme_kept = 0
    
    for tag in tags:
        classification = tag_utils.classify_tag(tag)
        
        if classification == "metadata":
            metadata_tags.append(tag)
            metadata_counts[tag] = metadata_counts.get(tag, 0) + 1
            metadata_moved += 1
        else:
            theme_tags.append(tag)
            theme_counts[tag] = theme_counts.get(tag, 0) + 1
            theme_kept += 1
    
    return metadata_tags, theme_tags, metadata_moved, theme_kept


def _build_partition_diagnostics(
    total_rows: int,
    rows_with_tags: int,
    total_metadata_moved: int,
    total_theme_kept: int,
    metadata_counts: Dict[str, int],
    theme_counts: Dict[str, int]
) -> Dict[str, Any]:
    """Build diagnostics dictionary for metadata partition operation.
    
    Args:
        total_rows: Total rows processed
        rows_with_tags: Rows that had any tags
        total_metadata_moved: Total metadata tags moved
        total_theme_kept: Total theme tags kept
        metadata_counts: Count of each metadata tag
        theme_counts: Count of each theme tag
        
    Returns:
        Diagnostics dictionary
    """
    most_common_metadata = sorted(metadata_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    most_common_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "enabled": True,
        "total_rows": total_rows,
        "rows_with_tags": rows_with_tags,
        "metadata_tags_moved": total_metadata_moved,
        "theme_tags_kept": total_theme_kept,
        "unique_metadata_tags": len(metadata_counts),
        "unique_theme_tags": len(theme_counts),
        "most_common_metadata": most_common_metadata,
        "most_common_themes": most_common_themes
    }


def _apply_metadata_partition(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Partition tags into themeTags and metadataTags columns.
    
    Metadata tags are diagnostic, bracket-related, or internal annotations that
    should not appear in theme catalogs or player-facing lists. This function:
    1. Creates a new 'metadataTags' column
    2. Classifies each tag in 'themeTags' as metadata or theme
    3. Moves metadata tags to 'metadataTags' column
    4. Keeps theme tags in 'themeTags' column
    5. Returns summary diagnostics
    
    Args:
        df: DataFrame with 'themeTags' column (list of tag strings)
        
    Returns:
        Tuple of (modified DataFrame, diagnostics dict)
    """
    tag_metadata_split = os.getenv('TAG_METADATA_SPLIT', '1').lower() not in ('0', 'false', 'off', 'disabled')
    
    if not tag_metadata_split:
        logger.info("TAG_METADATA_SPLIT disabled, skipping metadata partition")
        return df, {
            "enabled": False,
            "total_rows": len(df),
            "message": "Feature disabled via TAG_METADATA_SPLIT=0"
        }
    
    if 'themeTags' not in df.columns:
        logger.warning("No 'themeTags' column found, skipping metadata partition")
        return df, {
            "enabled": True,
            "error": "Missing themeTags column",
            "total_rows": len(df)
        }
    df['metadataTags'] = pd.Series([[] for _ in range(len(df))], index=df.index)
    metadata_counts: Dict[str, int] = {}
    theme_counts: Dict[str, int] = {}
    total_metadata_moved = 0
    total_theme_kept = 0
    rows_with_tags = 0
    for idx in df.index:
        tags = df.at[idx, 'themeTags']
        
        if not isinstance(tags, list) or not tags:
            continue
        
        rows_with_tags += 1
        
        # Classify and partition tags
        metadata_tags, theme_tags, meta_moved, theme_kept = _classify_and_partition_tags(
            tags, metadata_counts, theme_counts
        )
        
        total_metadata_moved += meta_moved
        total_theme_kept += theme_kept
        df.at[idx, 'themeTags'] = theme_tags
        df.at[idx, 'metadataTags'] = metadata_tags
    diagnostics = _build_partition_diagnostics(
        len(df), rows_with_tags, total_metadata_moved, total_theme_kept,
        metadata_counts, theme_counts
    )
    logger.info(
        f"Metadata partition complete: {total_metadata_moved} metadata tags moved, "
        f"{total_theme_kept} theme tags kept across {rows_with_tags} rows"
    )
    
    if diagnostics["most_common_metadata"]:
        top_5_metadata = ', '.join([f"{tag}({ct})" for tag, ct in diagnostics["most_common_metadata"][:5]])
        logger.info(f"Top metadata tags: {top_5_metadata}")
    
    return df, diagnostics

### Setup
## Load the dataframe
def load_dataframe(color: str) -> None:
    """
    Load and validate the card dataframe for a given color.

    Args:
        color (str): The color of cards to load ('white', 'blue', etc)

    Raises:
        FileNotFoundError: If CSV file doesn't exist and can't be regenerated
        ValueError: If required columns are missing
    """
    try:
        filepath = f'{CSV_DIRECTORY}/{color}_cards.csv'

        # Check if file exists, regenerate if needed
        if not os.path.exists(filepath):
            logger.warning(f'{color}_cards.csv not found, regenerating it.')
            setup.regenerate_csv_by_color(color)
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Failed to generate {filepath}")

        # Load initial dataframe for validation
        check_df = pd.read_csv(filepath)
        required_columns = ['creatureTypes', 'themeTags'] 
        missing_columns = [col for col in required_columns if col not in check_df.columns]
        if missing_columns:
            logger.warning(f"Missing columns: {missing_columns}")
            if 'creatureTypes' not in check_df.columns:
                kindred_tagging(check_df, color)
            if 'themeTags' not in check_df.columns:
                create_theme_tags(check_df, color)

            # Persist newly added columns before re-reading with converters
            try:
                check_df.to_csv(filepath, index=False)
            except Exception as e:
                logger.error(f'Failed to persist added columns to {filepath}: {e}')
                raise

            # Verify columns were added successfully
            check_df = pd.read_csv(filepath)
            still_missing = [col for col in required_columns if col not in check_df.columns]
            if still_missing:
                raise ValueError(f"Failed to add required columns: {still_missing}")

        # Load final dataframe with proper converters
        # M3: metadataTags is optional (may not exist in older CSVs)
        converters = {'themeTags': pd.eval, 'creatureTypes': pd.eval}
        if 'metadataTags' in check_df.columns:
            converters['metadataTags'] = pd.eval
        
        df = pd.read_csv(filepath, converters=converters)
        tag_by_color(df, color)

    except FileNotFoundError as e:
        logger.error(f'Error: {e}')
        raise
    except pd.errors.ParserError as e:
        logger.error(f'Error parsing the CSV file: {e}')
        raise
    except Exception as e:
        logger.error(f'An unexpected error occurred: {e}')
        raise

def _tag_foundational_categories(df: pd.DataFrame, color: str) -> None:
    """Apply foundational card categorization (creature types, card types, keywords).
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    kindred_tagging(df, color)
    print('\n====================\n')
    create_theme_tags(df, color)
    print('\n====================\n')
    add_creatures_to_tags(df, color)
    print('\n====================\n')
    tag_for_card_types(df, color)
    print('\n====================\n')
    tag_for_keywords(df, color)
    print('\n====================\n')
    tag_for_partner_effects(df, color)
    print('\n====================\n')


def _tag_mechanical_themes(df: pd.DataFrame, color: str) -> None:
    """Apply mechanical theme tags (cost reduction, draw, artifacts, enchantments, etc.).
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    tag_for_cost_reduction(df, color)
    print('\n====================\n')
    tag_for_freerunning(df, color)
    print('\n====================\n')
    tag_for_card_draw(df, color)
    print('\n====================\n')
    tag_for_discard_matters(df, color)
    print('\n====================\n')
    tag_for_explore_and_map(df, color)
    print('\n====================\n')
    tag_for_artifacts(df, color)
    print('\n====================\n')
    tag_for_enchantments(df, color)
    print('\n====================\n')
    tag_for_craft(df, color)
    print('\n====================\n')
    tag_for_exile_matters(df, color)
    print('\n====================\n')
    tag_for_bending(df, color)
    print('\n====================\n')
    tag_for_land_types(df, color)
    print('\n====================\n')
    tag_for_web_slinging(df, color)
    print('\n====================\n')
    tag_for_tokens(df, color)
    print('\n====================\n')
    tag_for_rad_counters(df, color)
    print('\n====================\n')
    tag_for_life_matters(df, color)
    print('\n====================\n')
    tag_for_counters(df, color)
    print('\n====================\n')


def _tag_strategic_themes(df: pd.DataFrame, color: str) -> None:
    """Apply strategic theme tags (voltron, lands, spellslinger, ramp).
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    tag_for_voltron(df, color)
    print('\n====================\n')
    tag_for_lands_matter(df, color)
    print('\n====================\n')
    tag_for_spellslinger(df, color)
    print('\n====================\n')
    tag_for_spree(df, color)
    print('\n====================\n')
    tag_for_ramp(df, color)
    print('\n====================\n')
    tag_for_themes(df, color)
    print('\n====================\n')
    tag_for_interaction(df, color)
    print('\n====================\n')


def _tag_archetype_themes(df: pd.DataFrame, color: str) -> None:
    """Apply high-level archetype tags (midrange, toolbox, pillowfort, politics).
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    tag_for_midrange_archetype(df, color)
    print('\n====================\n')
    tag_for_toolbox_archetype(df, color)
    print('\n====================\n')
    tag_for_pillowfort(df, color)
    print('\n====================\n')
    tag_for_politics(df, color)
    print('\n====================\n')


## Tag cards on a color-by-color basis
def tag_by_color(df: pd.DataFrame, color: str) -> None:
    """Orchestrate all tagging operations for a color's DataFrame.
    
    Applies tags in this order:
    1. Foundational categories (creature types, card types, keywords)
    2. Mechanical themes (cost reduction, draw, artifacts, tokens, etc.)
    3. Strategic themes (voltron, lands matter, spellslinger, ramp)
    4. High-level archetypes (midrange, toolbox, pillowfort, politics)
    5. Bracket policy tags
    
    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    _tag_foundational_categories(df, color)
    _tag_mechanical_themes(df, color)
    _tag_strategic_themes(df, color)
    _tag_archetype_themes(df, color)
    
    # Apply bracket policy tags (from config/card_lists/*.json)
    apply_bracket_policy_tags(df)
    
    # Apply colorless filter tags (M1: Useless in Colorless)
    apply_colorless_filter_tags(df)
    print('\n====================\n')

    # Merge multi-face entries before final ordering (feature-flagged)
    if DFC_COMPAT_SNAPSHOT:
        try:
            _write_compat_snapshot(df.copy(deep=True), color)
        except Exception:
            pass

    df = merge_multi_face_rows(df, color, logger=logger, recorder=_merge_summary_recorder(color))

    if color == 'commander':
        df = enrich_commander_rows_with_tags(df, CSV_DIRECTORY)

    # Sort all theme tags for easier reading and reorder columns
    df = sort_theme_tags(df, color)
    
    # M3: Partition metadata tags from theme tags
    df, partition_diagnostics = _apply_metadata_partition(df)
    if partition_diagnostics.get("enabled"):
        logger.info(f"Metadata partition for {color}: {partition_diagnostics['metadata_tags_moved']} metadata, "
                   f"{partition_diagnostics['theme_tags_kept']} theme tags")
    
    df.to_csv(f'{CSV_DIRECTORY}/{color}_cards.csv', index=False)
    #print(df)
    print('\n====================\n')
    logger.info(f'Tags are done being set on {color}_cards.csv')
    #keyboard.wait('esc')

## Determine any non-creature cards that have creature types mentioned
def kindred_tagging(df: pd.DataFrame, color: str) -> None:
    """Tag cards with creature types and related types.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Setting creature type tags on {color}_cards.csv')

    try:
        df['creatureTypes'] = pd.Series([[] for _ in range(len(df))], index=df.index)

        # Detect creature types using vectorized split/filter
        creature_mask = tag_utils.create_type_mask(df, 'Creature')
        if creature_mask.any():
            df.loc[creature_mask, 'creatureTypes'] = (
                df.loc[creature_mask, 'type']
                  .fillna('')
                  .str.split()
                  .apply(lambda ts: [
                      t for t in ts
                      if t in tag_constants.CREATURE_TYPES and t not in tag_constants.NON_CREATURE_TYPES
                  ])
            )

        creature_time = pd.Timestamp.now()
        logger.info(f'Creature type detection completed in {(creature_time - start_time).total_seconds():.2f}s')
        print('\n==========\n')
        
        logger.info(f'Setting Outlaw creature type tags on {color}_cards.csv')
        outlaws = tag_constants.OUTLAW_TYPES
        df['creatureTypes'] = df.apply(
            lambda row: tag_utils.add_outlaw_type(row['creatureTypes'], outlaws)
            if isinstance(row['creatureTypes'], list) else row['creatureTypes'],
            axis=1
        )

        outlaw_time = pd.Timestamp.now()
        logger.info(f'Outlaw type processing completed in {(outlaw_time - creature_time).total_seconds():.2f}s')

        # Find creature types in text
        logger.info('Checking for creature types in card text')
        # Check for creature types in text (i.e. how 'Voja, Jaws of the Conclave' cares about Elves)
        logger.info(f'Checking for and setting creature types found in the text of cards in {color}_cards.csv')
        ignore_list = [
            'Elite Inquisitor', 'Breaker of Armies',
            'Cleopatra, Exiled Pharaoh', 'Nath\'s Buffoon'
        ]

        # Compute text-based types using vectorized apply over rows
        text_types_series = df.apply(
            lambda r: tag_utils.find_types_in_text(r['text'], r['name'], tag_constants.CREATURE_TYPES)
            if r['name'] not in ignore_list else [], axis=1
        )
        has_text_types = text_types_series.apply(bool)
        if has_text_types.any():
            df.loc[has_text_types, 'creatureTypes'] = df.loc[has_text_types].apply(
                lambda r: sorted(list(set((r['creatureTypes'] if isinstance(r['creatureTypes'], list) else []) + text_types_series.at[r.name]))),
                axis=1
            )

        text_time = pd.Timestamp.now()
        logger.info(f'Text-based type detection completed in {(text_time - outlaw_time).total_seconds():.2f}s')

        # Skip intermediate disk writes; final save happens at end of tag_by_color
        total_time = pd.Timestamp.now() - start_time
        logger.info(f'Creature type tagging completed in {total_time.total_seconds():.2f}s')

    # Overwrite file with creature type tags
    except Exception as e:
        logger.error(f'Error in kindred_tagging: {e}')
        raise
    
def create_theme_tags(df: pd.DataFrame, color: str) -> None:
    """Initialize and configure theme tags for a card DataFrame.

    This function initializes the themeTags column, validates the DataFrame structure,
    and reorganizes columns in an efficient manner. It uses vectorized operations
    for better performance.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Returns:
        The processed DataFrame with initialized theme tags and reorganized columns

    Raises:
        ValueError: If required columns are missing or color is invalid
        TypeError: If inputs are not of correct type
    """
    logger.info('Initializing theme tags for %s cards', color)
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not isinstance(color, str):
        raise TypeError("color must be a string")
    if color not in COLORS:
        raise ValueError(f"Invalid color: {color}")

    try:
        df['themeTags'] = pd.Series([[] for _ in range(len(df))], index=df.index)

        # Define expected columns
        required_columns = {
            'name', 'text', 'type', 'keywords',
            'creatureTypes', 'power', 'toughness'
        }
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Define column order
        columns_to_keep = tag_constants.REQUIRED_COLUMNS

        # Reorder columns efficiently
        available_cols = [col for col in columns_to_keep if col in df.columns]
        df = df.reindex(columns=available_cols)
        
        # Skip intermediate disk writes; final save happens at end of tag_by_color
        logger.info('Theme tags initialized for %s', color)
            
    except Exception as e:
        logger.error('Error initializing theme tags: %s', str(e))
        raise

def tag_for_card_types(df: pd.DataFrame, color: str) -> None:
    """Tag cards based on their types using vectorized operations.

    This function efficiently applies tags based on card types using vectorized operations.
    It handles special cases for different card types and maintains compatibility with
    the existing tagging system.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required columns are missing
    """
    try:
        required_cols = {'type', 'themeTags'}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"Missing required columns: {required_cols - set(df.columns)}")

        # Define type-to-tag mapping
        type_tag_map = tag_constants.TYPE_TAG_MAPPING
        rules = [
            { 'mask': tag_utils.create_type_mask(df, card_type), 'tags': tags }
            for card_type, tags in type_tag_map.items()
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'card type tags', color=color, logger=logger
        )

    except Exception as e:
        logger.error('Error in tag_for_card_types: %s', str(e))
        raise

## Add creature types to the theme tags
def add_creatures_to_tags(df: pd.DataFrame, color: str) -> None:
    """Add kindred tags to theme tags based on creature types using vectorized operations.

    This function efficiently processes creature types and adds corresponding kindred tags
    using pandas vectorized operations instead of row-by-row iteration.

    Args:
        df: DataFrame containing card data with creatureTypes and themeTags columns
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required columns are missing
        TypeError: If inputs are not of correct type
    """
    logger.info(f'Adding creature types to theme tags in {color}_cards.csv')

    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'creatureTypes', 'themeTags'}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        has_creatures_mask = df['creatureTypes'].apply(lambda x: bool(x) if isinstance(x, list) else False)

        if has_creatures_mask.any():
            creature_rows = df[has_creatures_mask]

            # Generate kindred tags vectorized
            def add_kindred_tags(row):
                current_tags = row['themeTags']
                kindred_tags = [f"{ct} Kindred" for ct in row['creatureTypes']]
                return sorted(list(set(current_tags + kindred_tags)))
            df.loc[has_creatures_mask, 'themeTags'] = creature_rows.apply(add_kindred_tags, axis=1)

            logger.info(f'Added kindred tags to {has_creatures_mask.sum()} cards')

        else:
            logger.info('No cards with creature types found')

    except Exception as e:
        logger.error(f'Error in add_creatures_to_tags: {str(e)}')
        raise

    logger.info(f'Creature types added to theme tags in {color}_cards.csv')

## Add keywords to theme tags
def tag_for_keywords(df: pd.DataFrame, color: str) -> None:
    """Tag cards based on their keywords using vectorized operations.
    
    When TAG_NORMALIZE_KEYWORDS is enabled, applies normalization:
    - Canonical mapping (e.g., "Commander Ninjutsu" -> "Ninjutsu")
    - Singleton pruning (unless allowlisted)
    - Case normalization

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    logger.info('Tagging cards with keywords in %s_cards.csv', color)
    start_time = pd.Timestamp.now()

    try:
        from settings import TAG_NORMALIZE_KEYWORDS
        
        # Load frequency map if normalization is enabled
        frequency_map: dict[str, int] = {}
        if TAG_NORMALIZE_KEYWORDS:
            freq_map_path = Path(__file__).parent / 'keyword_frequency_map.json'
            if freq_map_path.exists():
                with open(freq_map_path, 'r', encoding='utf-8') as f:
                    frequency_map = json.load(f)
                logger.info('Loaded keyword frequency map with %d entries', len(frequency_map))
            else:
                logger.warning('Keyword frequency map not found, normalization disabled for this run')
                TAG_NORMALIZE_KEYWORDS = False
        has_keywords = pd.notna(df['keywords'])

        if has_keywords.any():
            # Vectorized split and merge into themeTags
            keywords_df = df.loc[has_keywords, ['themeTags', 'keywords']].copy()
            exclusion_keywords = {'partner'}

            def _merge_keywords(row: pd.Series) -> list[str]:
                base_tags = row['themeTags'] if isinstance(row['themeTags'], list) else []
                keywords_raw = row['keywords']

                if isinstance(keywords_raw, str):
                    keywords_iterable = [part.strip() for part in keywords_raw.split(',')]
                elif isinstance(keywords_raw, (list, tuple, set)):
                    keywords_iterable = [str(part).strip() for part in keywords_raw]
                else:
                    keywords_iterable = []

                # Apply normalization if enabled
                if TAG_NORMALIZE_KEYWORDS and frequency_map:
                    normalized_keywords = tag_utils.normalize_keywords(
                        keywords_iterable,
                        tag_constants.KEYWORD_ALLOWLIST,
                        frequency_map
                    )
                    return sorted(list(set(base_tags + normalized_keywords)))
                else:
                    # Legacy behavior: simple exclusion filter
                    filtered_keywords = [
                        kw for kw in keywords_iterable
                        if kw and kw.lower() not in exclusion_keywords
                    ]
                    return sorted(list(set(base_tags + filtered_keywords)))

            df.loc[has_keywords, 'themeTags'] = keywords_df.apply(_merge_keywords, axis=1)

        duration = (pd.Timestamp.now() - start_time).total_seconds()
        logger.info('Tagged %d cards with keywords in %.2f seconds', has_keywords.sum(), duration)
        
        if TAG_NORMALIZE_KEYWORDS:
            logger.info('Keyword normalization enabled for %s', color)

    except Exception as e:
        logger.error('Error tagging keywords: %s', str(e))
        raise

## Sort any set tags
def sort_theme_tags(df, color):
    logger.info(f'Alphabetically sorting theme tags in {color}_cards.csv.')

    # Sort the list of tags in-place per row
    df['themeTags'] = df['themeTags'].apply(tag_utils.sort_list)

    # Reorder columns for final CSV output; return a reindexed copy
    columns_to_keep = ['name', 'faceName','edhrecRank', 'colorIdentity', 'colors', 'manaCost', 'manaValue', 'type', 'creatureTypes', 'text', 'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side']
    available = [c for c in columns_to_keep if c in df.columns]
    logger.info(f'Theme tags alphabetically sorted in {color}_cards.csv.')
    return df.reindex(columns=available)

### Partner Mechanics
def tag_for_partner_effects(df: pd.DataFrame, color: str) -> None:
    """Tag cards for partner-related keywords.

    Looks for 'partner', 'partner with', and permutations in rules text and
    applies tags accordingly.
    """
    try:
        rules = [
            {'mask': tag_utils.create_text_mask(df, r"\bpartner\b(?!\s*(?:with|[-—–]))"), 'tags': ['Partner']},
            {'mask': tag_utils.create_text_mask(df, 'partner with'), 'tags': ['Partner with']},
            {'mask': tag_utils.create_text_mask(df, r"Partner\s*[-—–]\s*Survivors"), 'tags': ['Partner - Survivors']},
            {'mask': tag_utils.create_text_mask(df, r"Partner\s*[-—–]\s*Father\s*&\s*Son"), 'tags': ['Partner - Father & Son']},
            {'mask': tag_utils.create_text_mask(df, 'Friends forever'), 'tags': ['Friends Forever']},
            {'mask': tag_utils.create_text_mask(df, "Doctor's companion"), 'tags': ["Doctor's Companion"]},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'partner effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging partner keywords: {str(e)}')
        raise

### Cost reductions
def tag_for_cost_reduction(df: pd.DataFrame, color: str) -> None:
    """Tag cards that reduce spell costs using vectorized operations.

    This function identifies cards that reduce casting costs through various means including:
    - General cost reduction effects
    - Artifact cost reduction
    - Enchantment cost reduction 
    - Affinity and similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        cost_mask = tag_utils.create_text_mask(df, tag_constants.PATTERN_GROUPS['cost_reduction'])

        # Add specific named cards
        named_cards = [
            'Ancient Cellarspawn', 'Beluna Grandsquall', 'Cheering Fanatic',
            'Cloud Key', 'Conduit of Ruin', 'Eluge, the Shoreless Sea',
            'Goblin Anarchomancer', 'Goreclaw, Terror of Qal Sisma',
            'Helm of Awakening', 'Hymn of the Wilds', 'It that Heralds the End',
            'K\'rrik, Son of Yawgmoth', 'Killian, Ink Duelist', 'Krosan Drover',
            'Memory Crystal', 'Myth Unbound', 'Mistform Warchief',
            'Ranar the Ever-Watchful', 'Rowan, Scion of War', 'Semblence Anvil',
            'Spectacle Mage', 'Spellwild Ouphe', 'Strong Back',
            'Thryx, the Sudden Storm', 'Urza\'s Filter', 'Will, Scion of Peace',
            'Will Kenrith'
        ]
        named_mask = tag_utils.create_name_mask(df, named_cards)
        final_mask = cost_mask | named_mask
        spell_mask = final_mask & tag_utils.create_text_mask(df, r"Sorcery|Instant|noncreature")
        tag_utils.tag_with_rules_and_logging(df, [
            { 'mask': final_mask, 'tags': ['Cost Reduction'] },
            { 'mask': spell_mask, 'tags': ['Spellslinger', 'Spells Matter'] },
        ], 'cost reduction cards', color=color, logger=logger)

    except Exception as e:
        logger.error('Error tagging cost reduction cards: %s', str(e))
        raise

### Card draw/advantage
## General card draw/advantage
def tag_for_card_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have card draw effects or care about drawing cards.

    This function identifies and tags cards with various types of card draw effects including:
    - Conditional draw (triggered/activated abilities)
    - Looting effects (draw + discard)
    - Cost-based draw (pay life/sacrifice)
    - Replacement draw effects
    - Wheel effects
    - Unconditional draw

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting card draw effect tagging for {color}_cards.csv')

    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of draw effect
        tag_for_conditional_draw(df, color)
        logger.info('Completed conditional draw tagging')
        print('\n==========\n')

        tag_for_loot_effects(df, color)
        logger.info('Completed loot effects tagging')
        print('\n==========\n')

        tag_for_cost_draw(df, color)
        logger.info('Completed cost-based draw tagging')
        print('\n==========\n')

        tag_for_replacement_draw(df, color)
        logger.info('Completed replacement draw tagging')
        print('\n==========\n')

        tag_for_wheels(df, color)
        logger.info('Completed wheel effects tagging')
        print('\n==========\n')

        tag_for_unconditional_draw(df, color)
        logger.info('Completed unconditional draw tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all card draw tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_card_draw: {str(e)}')
        raise

## Conditional card draw (i.e. Rhystic Study or Trouble In Pairs)    
def create_unconditional_draw_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with unconditional draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have unconditional draw effects
    """
    draw_mask = tag_utils.create_numbered_phrase_mask(df, 'draw', 'card')
    excluded_tags = tag_constants.DRAW_RELATED_TAGS
    tag_mask = tag_utils.create_tag_mask(df, excluded_tags)
    text_patterns = tag_constants.DRAW_EXCLUSION_PATTERNS
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    return draw_mask & ~(tag_mask | text_mask)

def tag_for_unconditional_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have unconditional draw effects using vectorized operations.

    This function identifies and tags cards that draw cards without conditions or
    additional costs. It excludes cards that already have conditional draw tags
    or specific keywords.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        draw_mask = create_unconditional_draw_mask(df)
        tag_utils.tag_with_logging(df, draw_mask, ['Unconditional Draw', 'Card Draw'], 'unconditional draw effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging unconditional draw effects: {str(e)}')
        raise

## Conditional card draw (i.e. Rhystic Study or Trouble In Pairs)
def create_conditional_draw_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from conditional draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    excluded_tags = tag_constants.DRAW_RELATED_TAGS
    tag_mask = tag_utils.create_tag_mask(df, excluded_tags)
    text_patterns = tag_constants.DRAW_EXCLUSION_PATTERNS + ['whenever you draw a card']
    text_mask = tag_utils.create_text_mask(df, text_patterns)
    excluded_names = ['relic vial', 'vexing bauble']
    name_mask = tag_utils.create_name_mask(df, excluded_names)

    return tag_mask | text_mask | name_mask

def create_conditional_draw_trigger_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with conditional draw triggers.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have trigger patterns
    """
    subjects = [
        'a permanent',
        'a creature',
        'a player',
        'an opponent',
        'another creature',
        'enchanted player',
        'one or more creatures',
        'one or more other creatures',
        'you',
    ]
    trigger_mask = tag_utils.create_trigger_mask(df, subjects, include_attacks=True)

    # Add other trigger patterns
    other_patterns = ['created a token', 'draw a card for each']
    other_mask = tag_utils.create_text_mask(df, other_patterns)

    return trigger_mask | other_mask

def create_conditional_draw_effect_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have draw effects
    """
    # Create draw patterns using helper plus extras
    base_mask = tag_utils.create_numbered_phrase_mask(df, 'draw', 'card')
    extra_mask = tag_utils.create_text_mask(df, ['created a token.*draw', 'draw a card for each'])
    return base_mask | extra_mask

def tag_for_conditional_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have conditional draw effects using vectorized operations.

    This function identifies and tags cards that draw cards based on triggers or conditions.
    It handles various patterns including:
    - Permanent/creature triggers
    - Player-based triggers
    - Token creation triggers
    - 'Draw for each' effects

    The function excludes cards that:
    - Already have certain tags (Cycling, Imprint, etc.)
    - Contain specific text patterns (annihilator, ravenous)
    - Have specific names (relic vial, vexing bauble)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Build masks
        exclusion_mask = create_conditional_draw_exclusion_mask(df)
        trigger_mask = create_conditional_draw_trigger_mask(df)
        
        # Create draw effect mask with extra patterns
        draw_mask = tag_utils.create_numbered_phrase_mask(df, 'draw', 'card')
        draw_mask = draw_mask | tag_utils.create_text_mask(df, ['created a token.*draw', 'draw a card for each'])

        # Combine: trigger & draw & ~exclusion
        final_mask = trigger_mask & draw_mask & ~exclusion_mask
        tag_utils.tag_with_logging(df, final_mask, ['Conditional Draw', 'Card Draw'], 'conditional draw effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging conditional draw effects: {str(e)}')
        raise

## Loot effects, I.E. draw a card, discard a card. Or discard a card, draw a card
def create_loot_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with standard loot effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have loot effects
    """
    # Exclude cards that already have other loot-like effects
    has_other_loot = tag_utils.create_tag_mask(df, ['Cycling', 'Connive']) | df['text'].str.contains('blood token', case=False, na=False)
    
    # Match draw + discard patterns
    discard_patterns = [
        'discard the rest',
        'for each card drawn this way, discard',
        'if you do, discard',
        'then discard'
    ]
    
    has_draw = tag_utils.create_numbered_phrase_mask(df, 'draw', 'card')
    has_discard = tag_utils.create_text_mask(df, discard_patterns)
    
    return ~has_other_loot & has_draw & has_discard

def create_connive_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with connive effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have connive effects
    """
    has_keyword = tag_utils.create_keyword_mask(df, 'Connive')
    has_text = tag_utils.create_text_mask(df, 'connives?')
    return has_keyword | has_text

def create_cycling_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with cycling effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have cycling effects
    """
    has_keyword = tag_utils.create_keyword_mask(df, 'Cycling')
    has_text = tag_utils.create_text_mask(df, 'cycling')
    return has_keyword | has_text

def create_blood_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with blood token effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have blood token effects
    """
    return tag_utils.create_text_mask(df, 'blood token')

def tag_for_loot_effects(df: pd.DataFrame, color: str) -> None:
    """Tag cards with loot-like effects using vectorized operations.

    This function handles tagging of all loot-like effects including:
    - Standard loot (draw + discard)
    - Connive
    - Cycling
    - Blood tokens

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    loot_mask = create_loot_mask(df)
    connive_mask = create_connive_mask(df)
    cycling_mask = create_cycling_mask(df)
    blood_mask = create_blood_mask(df)
    rules = [
        {'mask': loot_mask, 'tags': ['Loot', 'Card Draw', 'Discard Matters']},
        {'mask': connive_mask, 'tags': ['Connive', 'Loot', 'Card Draw', 'Discard Matters']},
        {'mask': cycling_mask, 'tags': ['Cycling', 'Loot', 'Card Draw', 'Discard Matters']},
        {'mask': blood_mask, 'tags': ['Blood Token', 'Loot', 'Card Draw', 'Discard Matters']},
    ]
    tag_utils.tag_with_rules_and_logging(df, rules, 'loot-like effects', color=color, logger=logger)

## Sacrifice or pay life to draw effects
def tag_for_cost_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that draw cards by paying life or sacrificing permanents.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    life_mask = df['text'].str.contains('life: draw', case=False, na=False)
    
    # Use compiled patterns from regex_patterns module
    sac_mask = (
        df['text'].str.contains(rgx.SACRIFICE_DRAW.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(rgx.SACRIFICE_COLON_DRAW.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(rgx.SACRIFICED_COMMA_DRAW.pattern, case=False, na=False, regex=True)
    )
    rules = [
        {'mask': life_mask, 'tags': ['Life to Draw', 'Card Draw']},
        {'mask': sac_mask, 'tags': ['Sacrifice to Draw', 'Card Draw']},
    ]
    tag_utils.tag_with_rules_and_logging(df, rules, 'cost-based draw effects', color=color, logger=logger)

## Replacement effects, that might have you draw more cards
def create_replacement_draw_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with replacement draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have replacement draw effects
    """
    # Create trigger patterns
    trigger_patterns = []
    for trigger in tag_constants.TRIGGERS:
        trigger_patterns.extend([
            f'{trigger} a player.*instead.*draw',
            f'{trigger} an opponent.*instead.*draw', 
            f'{trigger} the beginning of your draw step.*instead.*draw',
            f'{trigger} you.*instead.*draw'
        ])

    # Create other replacement patterns
    replacement_patterns = [
        'if a player would.*instead.*draw',
        'if an opponent would.*instead.*draw', 
        'if you would.*instead.*draw'
    ]
    all_patterns = '|'.join(trigger_patterns + replacement_patterns)
    base_mask = tag_utils.create_text_mask(df, all_patterns)

    # Add mask for specific card numbers
    number_mask = tag_utils.create_numbered_phrase_mask(df, 'draw', 'card')

    # Add mask for non-specific numbers
    nonspecific_mask = tag_utils.create_text_mask(df, 'draw that many plus|draws that many plus') # df['text'].str.contains('draw that many plus|draws that many plus', case=False, na=False)

    return base_mask & (number_mask | nonspecific_mask)

def create_replacement_draw_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from replacement draw effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    excluded_tags = tag_constants.DRAW_RELATED_TAGS
    tag_mask = tag_utils.create_tag_mask(df, excluded_tags)
    text_patterns = tag_constants.DRAW_EXCLUSION_PATTERNS + ['skips that turn instead']
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    return tag_mask | text_mask

def tag_for_replacement_draw(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have replacement draw effects using vectorized operations.

    This function identifies and tags cards that modify or replace card draw effects,
    such as drawing additional cards or replacing normal draw effects with other effects.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Example patterns tagged:
        - Trigger-based replacement effects ("whenever you draw...instead")
        - Conditional replacement effects ("if you would draw...instead")
        - Specific card number replacements
        - Non-specific card number replacements ("draw that many plus")
    """
    try:
        # Build masks
        replacement_mask = create_replacement_draw_mask(df)
        exclusion_mask = create_replacement_draw_exclusion_mask(df)
        specific_cards_mask = tag_utils.create_name_mask(df, 'sylvan library')

        # Combine: (replacement & ~exclusion) OR specific cards
        final_mask = (replacement_mask & ~exclusion_mask) | specific_cards_mask
        tag_utils.tag_with_logging(df, final_mask, ['Replacement Draw', 'Card Draw'], 'replacement draw effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging replacement draw effects: {str(e)}')
        raise

## Wheels
def tag_for_wheels(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have wheel effects or care about drawing/discarding cards.

    This function identifies and tags cards that:
    - Force excess draw and discard
    - Have payoffs for drawing/discarding
    - Care about wheel effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Build text and name masks
        wheel_patterns = [
            'an opponent draws a card', 'cards you\'ve drawn', 'draw your second card', 'draw that many cards',
            'draws an additional card', 'draws a card', 'draws cards', 'draws half that many cards',
            'draws their first second card', 'draws their second second card', 'draw two cards instead',
            'draws two additional cards', 'discards that card', 'discards their hand, then draws',
            'each card your opponents have drawn', 'each draw a card', 'each opponent draws a card',
            'each player draws', 'has no cards in hand', 'have no cards in hand', 'may draw a card',
            'maximum hand size', 'no cards in it, you win the game instead', 'opponent discards',
            'you draw a card', 'whenever you draw a card'
        ]
        wheel_cards = [
            'arcane denial', 'bloodchief ascension', 'dark deal', 'elenda and azor', 'elixir of immortality',
            'forced fruition', 'glunch, the bestower', 'kiora the rising tide', 'kynaios and tiro of meletis',
            'library of leng', 'loran of the third path', 'mr. foxglove', 'raffine, scheming seer',
            'sauron, the dark lord', 'seizan, perverter of truth', 'triskaidekaphile', 'twenty-toed toad',
            'waste not', 'wedding ring', 'whispering madness'
        ]
        
        text_mask = tag_utils.create_text_mask(df, wheel_patterns)
        name_mask = tag_utils.create_name_mask(df, wheel_cards)
        final_mask = text_mask | name_mask

        # Build trigger submask for Draw Triggers tag
        trigger_pattern = '|'.join(tag_constants.TRIGGERS)
        trigger_mask = final_mask & df['text'].str.contains(trigger_pattern, case=False, na=False)
        rules = [
            {'mask': final_mask, 'tags': ['Card Draw', 'Wheels']},
            {'mask': trigger_mask, 'tags': ['Draw Triggers']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'wheel effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging "Wheel" effects: {str(e)}')
        raise

### Artifacts
def tag_for_artifacts(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about Artifacts or are specific kinds of Artifacts
    (i.e. Equipment or Vehicles).

    This function identifies and tags cards with Artifact-related effects including:
    - Creating Artifact tokens
    - Casting Artifact spells
    - Equipment
    - Vehicles

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting "Artifact" and "Artifacts Matter" tagging for {color}_cards.csv')
    print('\n==========\n')
    
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of artifact effect
        tag_for_artifact_tokens(df, color)
        logger.info('Completed Artifact token tagging')
        print('\n==========\n')
        
        tag_for_artifact_triggers(df, color)
        logger.info('Completed Artifact trigger tagging')
        print('\n==========\n')

        tag_equipment(df, color)
        logger.info('Completed Equipment tagging')
        print('\n==========\n')

        tag_vehicles(df, color)
        logger.info('Completed Vehicle tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all "Artifact" and "Artifacts Matter" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_enchantments: {str(e)}')
        raise

## Artifact Tokens
def tag_for_artifact_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about artifact tokens using vectorized operations.

    This function handles tagging of:
    - Generic artifact token creation
    - Predefined artifact token types (Treasure, Food, etc)
    - Fabricate keyword

    The function applies both generic artifact token tags and specific token type tags
    (e.g., 'Treasure Token', 'Food Token') based on the tokens created.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        generic_mask = create_generic_artifact_mask(df)
        predefined_mask, token_map = create_predefined_artifact_mask(df)
        fabricate_mask = create_fabricate_mask(df)

        # Apply base artifact token tags via rules engine
        rules = [
            {'mask': generic_mask, 'tags': ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter']},
            {'mask': predefined_mask, 'tags': ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter']},
            {'mask': fabricate_mask, 'tags': ['Artifact Tokens', 'Artifacts Matter', 'Token Creation', 'Tokens Matter']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'artifact tokens', color=color, logger=logger)

        # Apply specific token type tags (special handling for predefined tokens)
        if predefined_mask.any():
            token_to_indices: dict[str, list[int]] = {}
            for idx, token_type in token_map.items():
                token_to_indices.setdefault(token_type, []).append(idx)

            for token_type, indices in token_to_indices.items():
                mask = pd.Series(False, index=df.index)
                mask.loc[indices] = True
                tag_utils.apply_tag_vectorized(df, mask, [f'{token_type} Token'])

            # Log token type breakdown
            logger.info('Predefined artifact token breakdown:')
            for token_type, indices in token_to_indices.items():
                logger.info('  - %s: %d cards', token_type, len(indices))

    except Exception as e:
        logger.error('Error in tag_for_artifact_tokens: %s', str(e))
        raise

# Generic Artifact tokens, such as karnstructs, or artifact soldiers
def create_generic_artifact_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create non-predefined artifact tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create generic artifact tokens
    """
    # Exclude specific cards
    excluded_cards = [
        'diabolical salvation',
        'lifecraft awakening',
        'sandsteppe war riders',
        'transmutation font'
    ]
    name_exclusions = tag_utils.create_name_mask(df, excluded_cards)

    # Create text pattern matches
    has_create = tag_utils.create_text_mask(df, tag_constants.CREATE_ACTION_PATTERN)

    token_patterns = [
        'artifact creature token',
        'artifact token',
        'construct artifact',
        'copy of enchanted artifact',
        'copy of target artifact',
        'copy of that artifact'
    ]
    has_token = tag_utils.create_text_mask(df, token_patterns)

    # Named cards that create artifact tokens
    named_cards = [
        'bloodforged battle-axe', 'court of vantress', 'elmar, ulvenwald informant',
        'faerie artisans', 'feldon of the third path', 'lenoardo da vinci',
        'march of progress', 'nexus of becoming', 'osgir, the reconstructor',
        'prototype portal', 'red sun\'s twilight', 'saheeli, the sun\'s brilliance',
        'season of weaving', 'shaun, father of synths', 'sophia, dogged detective',
        'vaultborn tyrant', 'wedding ring'
    ]
    named_matches = tag_utils.create_name_mask(df, named_cards)

    # Exclude fabricate cards
    has_fabricate = tag_utils.create_text_mask(df, 'fabricate')

    return (has_create & has_token & ~name_exclusions & ~has_fabricate) | named_matches

def create_predefined_artifact_mask(df: pd.DataFrame) -> tuple[pd.Series, dict[int, str]]:
    """Create a boolean mask for cards that create predefined artifact tokens and track token types.

    Args:
        df: DataFrame to search

    Returns:
        Tuple containing:
            - Boolean Series indicating which cards create predefined artifact tokens
            - Dictionary mapping row indices to their matched token types
    """
    has_create = tag_utils.create_text_mask(df, tag_constants.CREATE_ACTION_PATTERN)

    # Initialize token mapping dictionary
    token_map = {}
    token_masks = []
    
    for token in tag_constants.ARTIFACT_TOKENS:
        token_mask = tag_utils.create_text_mask(df, token.lower())

        # Handle exclusions
        if token == 'Blood':
            token_mask &= df['name'] != 'Bloodroot Apothecary'
        elif token == 'Gold':
            token_mask &= ~df['name'].isin(['Goldspan Dragon', 'The Golden-Gear Colossus'])
        elif token == 'Junk':
            token_mask &= df['name'] != 'Junkyard Genius'

        # Store token type for matching rows
        matching_indices = df[token_mask].index
        for idx in matching_indices:
            if idx not in token_map:  # Only store first match
                token_map[idx] = token

        token_masks.append(token_mask)
    final_mask = has_create & pd.concat(token_masks, axis=1).any(axis=1)

    return final_mask, token_map
def create_fabricate_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with fabricate keyword.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have fabricate
    """
    return tag_utils.create_text_mask(df, 'fabricate')

## Artifact Triggers
def create_artifact_triggers_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about artifacts.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards care about artifacts
    """
    # Define artifact-related patterns
    ability_patterns = [
        'abilities of artifact', 'ability of artifact'
    ]

    artifact_state_patterns = [
        'are artifacts in addition', 'artifact enters', 'number of artifacts',
        'number of other artifacts', 'number of tapped artifacts',
        'number of artifact'
    ]

    artifact_type_patterns = [
        'all artifact', 'another artifact', 'another target artifact',
        'artifact card', 'artifact creature you control',
        'artifact creatures you control', 'artifact you control',
        'artifacts you control', 'each artifact', 'target artifact'
    ]

    casting_patterns = [
        'affinity for artifacts', 'artifact spells as though they had flash',
        'artifact spells you cast', 'cast an artifact', 'choose an artifact',
        'whenever you cast a noncreature', 'whenever you cast an artifact'
    ]

    counting_patterns = [
        'mana cost among artifact', 'mana value among artifact',
        'artifact with the highest mana value',
    ]

    search_patterns = [
        'search your library for an artifact'
    ]

    trigger_patterns = [
        'whenever a nontoken artifact', 'whenever an artifact',
        'whenever another nontoken artifact', 'whenever one or more artifact'
    ]
    all_patterns = (
        ability_patterns + artifact_state_patterns + artifact_type_patterns +
        casting_patterns + counting_patterns + search_patterns + trigger_patterns +
        ['metalcraft', 'prowess', 'copy of any artifact']
    )
    pattern = '|'.join(all_patterns)

    # Create mask
    return df['text'].str.contains(pattern, case=False, na=False, regex=True)

def tag_for_artifact_triggers(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about artifacts using vectorized operations.

    This function identifies and tags cards that:
    - Have abilities that trigger off artifacts
    - Care about artifact states or counts
    - Interact with artifact spells or permanents
    - Have metalcraft or similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Create artifact triggers mask
        triggers_mask = create_artifact_triggers_mask(df)
        tag_utils.tag_with_logging(
            df, triggers_mask, ['Artifacts Matter'],
            'cards that care about artifacts', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error tagging artifact triggers: {str(e)}')
        raise

## Equipment
def create_equipment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Equipment

    This function identifies cards that:
    - Have the Equipment subtype

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards are Equipment
    """
    # Create type-based mask
    type_mask = tag_utils.create_type_mask(df, 'Equipment')

    return type_mask

def create_equipment_cares_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about Equipment.

    This function identifies cards that:
    - Have abilities that trigger off Equipment
    - Care about equipped creatures
    - Modify Equipment or equipped creatures
    - Have Equipment-related keywords

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards care about Equipment
    """
    # Create text pattern mask
    text_patterns = [
        'equipment you control',
        'equipped creature',
        'attach',
        'equip',
        'equipment spells',
        'equipment abilities',
        'modified',
        'reconfigure'
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    # Create keyword mask
    keyword_patterns = ['Modified', 'Equip', 'Reconfigure']
    keyword_mask = tag_utils.create_keyword_mask(df, keyword_patterns)

    # Create specific cards mask
    specific_cards = tag_constants.EQUIPMENT_SPECIFIC_CARDS
    name_mask = tag_utils.create_name_mask(df, specific_cards)

    return text_mask | keyword_mask | name_mask

def tag_equipment(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Equipment or care about Equipment using vectorized operations.

    This function identifies and tags:
    - Equipment cards
    - Cards that care about Equipment
    - Cards with Equipment-related abilities
    - Cards that modify Equipment or equipped creatures

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        # Apply tagging rules with enhanced utilities
        rules = [
            { 'mask': create_equipment_mask(df), 'tags': ['Equipment', 'Equipment Matters', 'Voltron'] },
            { 'mask': create_equipment_cares_mask(df), 'tags': ['Artifacts Matter', 'Equipment Matters', 'Voltron'] }
        ]
        
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Equipment cards and cards that care about Equipment', color=color, logger=logger
        )

    except Exception as e:
        logger.error('Error tagging Equipment cards: %s', str(e))
        raise
    
## Vehicles
def create_vehicle_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Vehicles or care about Vehicles.

    This function identifies cards that:
    - Have the Vehicle subtype
    - Have crew abilities
    - Care about Vehicles or Pilots

    Args:
        df: DataFrame containing card data

    Returns:
        Boolean Series indicating which cards are Vehicles or care about them
    """
    return tag_utils.build_combined_mask(
        df,
        type_patterns=['Vehicle', 'Pilot'],
        text_patterns=['vehicle', 'crew', 'pilot']
    )

def tag_vehicles(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Vehicles or care about Vehicles using vectorized operations.

    This function identifies and tags:
    - Vehicle cards
    - Pilot cards
    - Cards that care about Vehicles
    - Cards with crew abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        # Use enhanced tagging utility
        tag_utils.tag_with_logging(
            df,
            create_vehicle_mask(df),
            ['Artifacts Matter', 'Vehicles'],
            'Vehicle-related cards',
            color=color,
            logger=logger
        )

    except Exception as e:
        logger.error('Error tagging Vehicle cards: %s', str(e))
        raise
    
### Enchantments
def tag_for_enchantments(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about Enchantments or are specific kinds of Enchantments
    (i.e. Equipment or Vehicles).

    This function identifies and tags cards with Enchantment-related effects including:
    - Creating Enchantment tokens
    - Casting Enchantment spells
    - Auras
    - Constellation
    - Cases
    - Rooms
    - Classes
    - Backrounds
    - Shrines

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting "Enchantment" and "Enchantments Matter" tagging for {color}_cards.csv')
    print('\n==========\n')
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of enchantment effect
        tag_for_enchantment_tokens(df, color)
        logger.info('Completed Enchantment token tagging')
        print('\n==========\n')

        tag_for_enchantments_matter(df, color)
        logger.info('Completed "Enchantments Matter" tagging')
        print('\n==========\n')

        tag_auras(df, color)
        logger.info('Completed Aura tagging')
        print('\n==========\n')
        
        tag_constellation(df, color)
        logger.info('Completed Constellation tagging')
        print('\n==========\n')
        
        tag_sagas(df, color)
        logger.info('Completed Saga tagging')
        print('\n==========\n')
        
        tag_cases(df, color)
        logger.info('Completed Case tagging')
        print('\n==========\n')
        
        tag_rooms(df, color)
        logger.info('Completed Room tagging')
        print('\n==========\n')
        
        tag_backgrounds(df, color)
        logger.info('Completed Background tagging')
        print('\n==========\n')
        
        tag_shrines(df, color)
        logger.info('Completed Shrine tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all "Enchantment" and "Enchantments Matter" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_artifacts: {str(e)}')
        raise

## Enchantment tokens
def tag_for_enchantment_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about enchantment tokens using vectorized operations.

    This function handles tagging of:
    - Generic enchantmeny token creation
    - Predefined enchantment token types (Roles, Shards, etc)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        generic_mask = create_generic_enchantment_mask(df)
        predefined_mask = create_predefined_enchantment_mask(df)
        rules = [
            {'mask': generic_mask, 'tags': ['Enchantment Tokens', 'Enchantments Matter', 'Token Creation', 'Tokens Matter']},
            {'mask': predefined_mask, 'tags': ['Enchantment Tokens', 'Enchantments Matter', 'Token Creation', 'Tokens Matter']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'enchantment tokens', color=color, logger=logger)

    except Exception as e:
        logger.error('Error in tag_for_enchantment_tokens: %s', str(e))
        raise

def create_generic_enchantment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create predefined enchantment tokens.
    
    Args:
        df: DataFrame to search
    
    Returns:
    Boolean Series indicating which cards create predefined enchantment tokens
    """
    # Create text pattern matches
    has_create = tag_utils.create_text_mask(df, tag_constants.CREATE_ACTION_PATTERN)
    
    token_patterns = [
        'copy of enchanted enchantment',
        'copy of target enchantment',
        'copy of that enchantment',
        'enchantment creature token',
        'enchantment token'
    ]
    has_token = tag_utils.create_text_mask(df, token_patterns)
    
    # Named cards that create enchantment tokens
    named_cards = [
        'court of vantress',
        'fellhide spiritbinder',
        'hammer of purphoros'
    ]
    named_matches = tag_utils.create_name_mask(df, named_cards)
    
    return (has_create & has_token) | named_matches

def create_predefined_enchantment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create non-predefined enchantment tokens.
    
    Args:
        df: DataFrame to search
    
    Returns:
        Boolean Series indicating which cards create generic enchantmnet tokens
    """
    # Create text pattern matches
    has_create = tag_utils.create_text_mask(df, tag_constants.CREATE_ACTION_PATTERN)
    token_masks = []
    for token in tag_constants.ENCHANTMENT_TOKENS:
        token_mask = tag_utils.create_text_mask(df, token.lower())
        
        token_masks.append(token_mask)
        
    return has_create & pd.concat(token_masks, axis=1).any(axis=1)
    
## General enchantments matter
def tag_for_enchantments_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about enchantments using vectorized operations.

    This function identifies and tags cards that:
    - Have abilities that trigger off enchantments
    - Care about enchantment states or counts
    - Interact with enchantment spells or permanents
    - Have constellation or similar mechanics

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Define enchantment-related patterns
        ability_patterns = [
            'abilities of enchantment', 'ability of enchantment'
        ]

        state_patterns = [
            'are enchantments in addition', 'enchantment enters'
        ]

        type_patterns = [
            'all enchantment', 'another enchantment', 'enchantment card',
            'enchantment creature you control', 'enchantment creatures you control',
            'enchantment you control', 'enchantments you control'
        ]

        casting_patterns = [
            'cast an enchantment', 'enchantment spells as though they had flash',
            'enchantment spells you cast'
        ]

        counting_patterns = [
            'mana value among enchantment', 'number of enchantment'
        ]

        search_patterns = [
            'search your library for an enchantment'
        ]

        trigger_patterns = [
            'whenever a nontoken enchantment', 'whenever an enchantment',
            'whenever another nontoken enchantment', 'whenever one or more enchantment'
        ]
        all_patterns = (
            ability_patterns + state_patterns + type_patterns +
            casting_patterns + counting_patterns + search_patterns + trigger_patterns
        )
        triggers_mask = tag_utils.create_text_mask(df, all_patterns)

        # Exclusions
        exclusion_mask = tag_utils.create_name_mask(df, 'luxa river shrine')

        # Final mask
        final_mask = triggers_mask & ~exclusion_mask

        # Apply tag
        tag_utils.tag_with_logging(
            df, final_mask, ['Enchantments Matter'],
            'cards that care about enchantments', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error tagging enchantment triggers: {str(e)}')
        raise

    logger.info(f'Completed tagging cards that care about enchantments in {color}_cards.csv')

## Aura
def tag_auras(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are Auras or care about Auras using vectorized operations.

    This function identifies cards that:
    - Have abilities that trigger off Auras
    - Care about enchanted permanents
    - Modify Auras or enchanted permanents
    - Have Aura-related keywords

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        aura_mask = tag_utils.create_type_mask(df, 'Aura')
        cares_mask = tag_utils.build_combined_mask(
            df, 
            text_patterns=['aura', 'aura enters', 'aura you control enters', 'enchanted'],
            name_list=tag_constants.AURA_SPECIFIC_CARDS
        )
        
        rules = [
            {'mask': aura_mask, 'tags': ['Auras', 'Enchantments Matter', 'Voltron']},
            {'mask': cares_mask, 'tags': ['Auras', 'Enchantments Matter', 'Voltron']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Aura cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Aura cards: %s', str(e))
        raise
    
## Constellation
def tag_constellation(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Constellation using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        constellation_mask = tag_utils.create_keyword_mask(df, 'Constellation')
        tag_utils.tag_with_logging(
            df, constellation_mask, ['Constellation', 'Enchantments Matter'], 'Constellation cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Constellation cards: {str(e)}')
        raise

## Sagas
def tag_sagas(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Saga type using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        saga_mask = tag_utils.create_type_mask(df, 'Saga')
        cares_mask = tag_utils.create_text_mask(df, ['saga', 'put a saga', 'final chapter', 'lore counter'])
        
        rules = [
            {'mask': saga_mask, 'tags': ['Enchantments Matter', 'Sagas Matter']},
            {'mask': cares_mask, 'tags': ['Enchantments Matter', 'Sagas Matter']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Saga cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Saga cards: {str(e)}')
        raise
    
## Cases
def tag_cases(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Case subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        case_mask = tag_utils.create_type_mask(df, 'Case')
        cares_mask = tag_utils.create_text_mask(df, 'solve a case')
        
        rules = [
            {'mask': case_mask, 'tags': ['Enchantments Matter', 'Cases Matter']},
            {'mask': cares_mask, 'tags': ['Enchantments Matter', 'Cases Matter']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Case cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Case cards: {str(e)}')
        raise

## Rooms
def tag_rooms(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the room subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        room_mask = tag_utils.create_type_mask(df, 'Room')
        keyword_mask = tag_utils.create_keyword_mask(df, 'Eerie')
        cares_mask = tag_utils.create_text_mask(df, 'target room')
        
        rules = [
            {'mask': room_mask, 'tags': ['Enchantments Matter', 'Rooms Matter']},
            {'mask': keyword_mask, 'tags': ['Enchantments Matter', 'Rooms Matter']},
            {'mask': cares_mask, 'tags': ['Enchantments Matter', 'Rooms Matter']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Room cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Room cards: {str(e)}')
        raise

## Classes
def tag_classes(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Class subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        class_mask = tag_utils.create_type_mask(df, 'Class')
        tag_utils.tag_with_logging(
            df, class_mask, ['Enchantments Matter', 'Classes Matter'], 'Class cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Class cards: {str(e)}')
        raise

## Background
def tag_backgrounds(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Background subtype or which let you choose a background using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        class_mask = tag_utils.create_type_mask(df, 'Background')
        cares_mask = tag_utils.create_text_mask(df, 'Background')
        
        rules = [
            {'mask': class_mask, 'tags': ['Enchantments Matter', 'Backgrounds Matter']},
            {'mask': cares_mask, 'tags': ['Enchantments Matter', 'Backgrounds Matter']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Background cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Background cards: {str(e)}')
        raise
    
## Shrines
def tag_shrines(df: pd.DataFrame, color: str) -> None:
    """Tag cards with the Shrine subtype using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFramecolumns are missing
    """
    try:
        class_mask = tag_utils.create_type_mask(df, 'Shrine')
        tag_utils.tag_with_logging(
            df, class_mask, ['Enchantments Matter', 'Shrines Matter'], 'Shrine cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Shrine cards: {str(e)}')
        raise

### Exile Matters
## Exile Matter effects, such as Impulse draw, foretell, etc...
def tag_for_exile_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about exiling cards and casting them from exile.

    This function identifies and tags cards with cast-from exile effects such as:
    - Cascade
    - Discover
    - Foretell
    - Imprint
    - Impulse
    - Plot
    - Suspend

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Card Draw', 'Spellslinger', etc.

    Args:
        df: DataFrame containing card data to process
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting "Exile Matters" tagging for {color}_cards.csv')
    print('\n==========\n')
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of Exile matters effect
        tag_for_general_exile_matters(df, color)
        logger.info('Completed general Exile Matters tagging')
        print('\n==========\n')

        tag_for_cascade(df, color)
        logger.info('Completed Cascade tagging')
        print('\n==========\n')

        tag_for_discover(df, color)
        logger.info('Completed Discover tagging')
        print('\n==========\n')

        tag_for_foretell(df, color)
        logger.info('Completed Foretell tagging')
        print('\n==========\n')

        tag_for_imprint(df, color)
        logger.info('Completed Imprint tagging')
        print('\n==========\n')

        tag_for_impulse(df, color)
        logger.info('Completed Impulse tagging')
        print('\n==========\n')

        tag_for_plot(df, color)
        logger.info('Completed Plot tagging')
        print('\n==========\n')

        tag_for_suspend(df, color)
        logger.info('Completed Suspend tagging')
        print('\n==========\n')

        tag_for_warp(df, color)
        logger.info('Completed Warp tagging')
        print('\n==========\n')

        # New: Time counters and Time Travel support
        tag_for_time_counters(df, color)
        logger.info('Completed Time Counters tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all "Exile Matters" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_exile_matters: {str(e)}')
        raise

def tag_for_general_exile_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have a general care about casting from Exile theme.

    This function identifies cards that:
    - Trigger off casting a card from exile
    - Trigger off playing a land from exile
    - Putting cards into exile to later play
    
    Args:
        df: DataFrame containing card data
    color: Color identifier for logging purposes
    
    Raises:
        ValueError: if required DataFrame columns are missing
    """
    try:
        # Create exile mask
        text_patterns = [
            'cards in exile',
            'cast a spell from exile',
            'cast but don\'t own',
            'cast from exile',
            'casts a spell from exile',
            'control but don\'t own',
            'exiled with',
            'from anywhere but their hand',
            'from anywhere but your hand',
            'from exile',
            'own in exile',
            'play a card from exile',
            'plays a card from exile',
            'play a land from exile',
            'plays a land from exile',
            'put into exile',
            'remains exiled'
            ]
        text_mask = tag_utils.create_text_mask(df, text_patterns)
        tag_utils.tag_with_logging(
            df, text_mask, ['Exile Matters'], 'General Exile Matters cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Exile Matters cards: %s', str(e))
        raise

## Cascade cards
def tag_for_cascade(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have or otherwise give the Cascade ability

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        text_patterns = ['gain cascade', 'has cascade', 'have cascade', 'have "cascade', 'with cascade']
        text_mask = tag_utils.create_text_mask(df, text_patterns)
        keyword_mask = tag_utils.create_keyword_mask(df, 'Cascade')
        
        rules = [
            {'mask': text_mask, 'tags': ['Cascade', 'Exile Matters']},
            {'mask': keyword_mask, 'tags': ['Cascade', 'Exile Matters']}
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Cascade cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Cascade cards: %s', str(e))
        raise
    
## Discover cards
def tag_for_discover(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Discover using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        keyword_mask = tag_utils.create_keyword_mask(df, 'Discover')
        tag_utils.tag_with_logging(
            df, keyword_mask, ['Discover', 'Exile Matters'], 'Discover cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Discover cards: {str(e)}')
        raise

## Foretell cards, and cards that care about foretell
def tag_for_foretell(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Foretell using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Foretell', text_patterns='Foretell'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Foretell', 'Exile Matters'], 'Foretell cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Foretell cards: {str(e)}')
        raise

## Cards that have or care about imprint
def tag_for_imprint(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Imprint using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Imprint', text_patterns='Imprint'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Imprint', 'Exile Matters'], 'Imprint cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Imprint cards: {str(e)}')
        raise

## Cards that have or care about impulse
def create_impulse_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with impulse-like effects.

    This function identifies cards that exile cards from the top of libraries
    and allow playing them for a limited time, including:
    - Exile top card(s) with may cast/play effects
    - Named cards with similar effects
    - Junk token creation

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have Impulse effects
    """
    # Define text patterns
    exile_patterns = [
        'exile the top',
        'exiles the top'
    ]

    play_patterns = [
        'may cast',
        'may play'
    ]

    # Named cards with Impulse effects
    impulse_cards = [
        'daxos of meletis', 'bloodsoaked insight', 'florian, voldaren scion',
        'possibility storm', 'ragava, nimble pilferer', 'rakdos, the muscle',
        'stolen strategy', 'urabrask, heretic praetor', 'valakut exploration',
        'wild wasteland'
    ]

    # Create exclusion patterns
    exclusion_patterns = [
        'damage to each', 'damage to target', 'deals combat damage',
        'raid', 'target opponent\'s hand',
        ]
    secondary_exclusion_patterns = [
        'each opponent', 'morph', 'opponent\'s library',
        'skip your draw', 'target opponent', 'that player\'s',
        'you may look at the top card'
        ]
 
    # Create masks
    tag_mask = tag_utils.create_tag_mask(df, 'Imprint')
    exile_mask = tag_utils.create_text_mask(df, exile_patterns)
    play_mask = tag_utils.create_text_mask(df, play_patterns)
    named_mask = tag_utils.create_name_mask(df, impulse_cards)
    junk_mask = tag_utils.create_text_mask(df, 'junk token')
    first_exclusion_mask = tag_utils.create_text_mask(df, exclusion_patterns)
    planeswalker_mask = df['type'].str.contains('Planeswalker', case=False, na=False)
    second_exclusion_mask = tag_utils.create_text_mask(df, secondary_exclusion_patterns)
    exclusion_mask = (~first_exclusion_mask & ~planeswalker_mask) & second_exclusion_mask
    impulse_mask = ((exile_mask & play_mask & ~exclusion_mask & ~tag_mask) | 
                   named_mask | junk_mask)
 
    return impulse_mask

def tag_for_impulse(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have impulse-like effects using vectorized operations.

    This function identifies and tags cards that exile cards from library tops
    and allow playing them for a limited time, including:
    - Exile top card(s) with may cast/play effects 
    - Named cards with similar effects
    - Junk token creation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Build masks
        impulse_mask = create_impulse_mask(df)
        junk_mask = tag_utils.create_text_mask(df, 'junk token')
        rules = [
            {'mask': impulse_mask, 'tags': ['Exile Matters', 'Impulse']},
            {'mask': (impulse_mask & junk_mask), 'tags': ['Junk Tokens']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'impulse effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging Impulse effects: {str(e)}')
        raise

## Cards that have or care about plotting
def tag_for_plot(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Plot using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Plot', text_patterns='Plot'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Plot', 'Exile Matters'], 'Plot cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Plot cards: {str(e)}')
        raise

## Cards that have or care about suspend
def tag_for_suspend(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Suspend using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Suspend', text_patterns='Suspend'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Suspend', 'Exile Matters'], 'Suspend cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Suspend cards: {str(e)}')
        raise

## Cards that have or care about Warp
def tag_for_warp(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Warp using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Warp', text_patterns='Warp'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Warp', 'Exile Matters'], 'Warp cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Warp cards: {str(e)}')
        raise

def create_time_counters_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that mention time counters or Time Travel.

    This captures interactions commonly associated with Suspend without
    requiring the Suspend keyword (e.g., Time Travel effects, adding/removing
    time counters, or Vanishing).

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards interact with time counters
    """
    # Text patterns around time counters and time travel
    text_patterns = [
        'time counter',
        'time counters',
        'remove a time counter',
        'add a time counter',
        'time travel'
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    # Keyword-based patterns that imply time counters
    keyword_mask = tag_utils.create_keyword_mask(df, ['Vanishing'])

    return text_mask | keyword_mask

def tag_for_time_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that interact with time counters or Time Travel.

    Applies a base 'Time Counters' tag. Adds 'Exile Matters' when the card also
    mentions exile or Suspend, since those imply interaction with suspended
    cards in exile.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        time_mask = create_time_counters_mask(df)
        
        # Conditionally add Exile Matters if the card references exile or suspend
        exile_mask = tag_utils.create_text_mask(df, tag_constants.PATTERN_GROUPS['exile'])
        suspend_mask = tag_utils.create_keyword_mask(df, 'Suspend') | tag_utils.create_text_mask(df, 'Suspend')
        time_exile_mask = time_mask & (exile_mask | suspend_mask)
        
        rules = [
            { 'mask': time_mask, 'tags': ['Time Counters'] },
            { 'mask': time_exile_mask, 'tags': ['Exile Matters'] }
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Time Counters cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Time Counters interactions: {str(e)}')
        raise

### Tokens
def create_creature_token_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that create creature tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards create creature tokens
    """
    has_create = tag_utils.create_text_mask(df, tag_constants.CREATE_ACTION_PATTERN)
    token_patterns = [
        'artifact creature token',
        'creature token',
        'enchantment creature token'
    ]
    has_token = tag_utils.create_text_mask(df, token_patterns)

    # Create exclusion mask
    exclusion_patterns = ['fabricate', 'modular']
    exclusion_mask = tag_utils.create_text_mask(df, exclusion_patterns)

    # Create name exclusion mask
    excluded_cards = ['agatha\'s soul cauldron']
    name_exclusions = tag_utils.create_name_mask(df, excluded_cards)

    return has_create & has_token & ~exclusion_mask & ~name_exclusions

def create_token_modifier_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that modify token creation.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards modify token creation
    """
    modifier_patterns = [
        'create one or more',
        'one or more creature',
        'one or more tokens would be created',
        'one or more tokens would be put',
        'one or more tokens would enter',
        'one or more tokens you control',
        'put one or more'
    ]
    has_modifier = tag_utils.create_text_mask(df, modifier_patterns)
    effect_patterns = ['instead', 'plus']
    has_effect = tag_utils.create_text_mask(df, effect_patterns)

    # Create name exclusion mask
    excluded_cards = [
        'cloakwood swarmkeeper',
        'neyali, sun\'s vanguard',
        'staff of the storyteller'
    ]
    name_exclusions = tag_utils.create_name_mask(df, excluded_cards)

    return has_modifier & has_effect & ~name_exclusions

def create_tokens_matter_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about tokens.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards care about tokens
    """
    text_patterns = [
        'tokens.*you.*control',
        'that\'s a token',
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    return text_mask

def tag_for_tokens(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or modify tokens using vectorized operations.

    This function identifies and tags:
    - Cards that create creature tokens
    - Cards that modify token creation (doublers, replacement effects)
    - Cards that care about tokens

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    print('\n==========\n')

    try:
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Build masks
        creature_mask = create_creature_token_mask(df)
        modifier_mask = create_token_modifier_mask(df)
        matters_mask = create_tokens_matter_mask(df)

        # Eldrazi Spawn/Scion special case
        spawn_patterns = [
            'eldrazi spawn creature token',
            'eldrazi scion creature token',
            'spawn creature token with "sacrifice',
            'scion creature token with "sacrifice'
        ]
        spawn_scion_mask = tag_utils.create_text_mask(df, spawn_patterns)
        rules = [
            {'mask': creature_mask, 'tags': ['Creature Tokens', 'Token Creation', 'Tokens Matter']},
            {'mask': modifier_mask, 'tags': ['Token Modification', 'Token Creation', 'Tokens Matter']},
            {'mask': matters_mask, 'tags': ['Tokens Matter']},
            {'mask': spawn_scion_mask, 'tags': ['Aristocrats', 'Ramp']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'token-related cards', color=color, logger=logger)

    except Exception as e:
        logger.error('Error tagging token cards: %s', str(e))
        raise

### Freerunning (cost reduction variant)
def tag_for_freerunning(df: pd.DataFrame, color: str) -> None:
    """Tag cards that reference the Freerunning mechanic.

    Adds Cost Reduction to ensure consistency, and a specific Freerunning tag for filtering.
    """
    try:
        required = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required)
        mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Freerunning', text_patterns=['freerunning', 'free running']
        )
        tag_utils.tag_with_logging(
            df, mask, ['Cost Reduction', 'Freerunning'], 'Freerunning cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Freerunning: %s', str(e))
        raise

### Craft (transform mechanic with exile/graveyard/artifact hooks)
def tag_for_craft(df: pd.DataFrame, color: str) -> None:
    """Tag cards with Craft. Adds Transform; conditionally adds Artifacts Matter, Exile Matters, and Graveyard Matters."""
    try:
        craft_mask = tag_utils.create_keyword_mask(df, 'Craft') | tag_utils.create_text_mask(df, ['craft with', 'craft —', ' craft '])
        
        # Conditionals
        artifact_cond = craft_mask & tag_utils.create_text_mask(df, ['artifact', 'artifacts'])
        exile_cond = craft_mask & tag_utils.create_text_mask(df, ['exile'])
        gy_cond = craft_mask & tag_utils.create_text_mask(df, ['graveyard'])
        
        rules = [
            { 'mask': craft_mask, 'tags': ['Transform'] },
            { 'mask': artifact_cond, 'tags': ['Artifacts Matter'] },
            { 'mask': exile_cond, 'tags': ['Exile Matters'] },
            { 'mask': gy_cond, 'tags': ['Graveyard Matters'] }
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Craft cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Craft: %s', str(e))
        raise

def tag_for_spree(df: pd.DataFrame, color: str) -> None:
    """Tag Spree spells with Modal and Cost Scaling."""
    try:
        mask = tag_utils.build_combined_mask(
            df, keyword_patterns='Spree', text_patterns='spree'
        )
        tag_utils.tag_with_logging(
            df, mask, ['Modal', 'Cost Scaling'], 'Spree cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Spree: %s', str(e))
        raise

def tag_for_explore_and_map(df: pd.DataFrame, color: str) -> None:
    """Tag Explore and Map token interactions.

    - Explore: add Card Selection; if it places +1/+1 counters, add +1/+1 Counters
    - Map Tokens: add Card Selection and Tokens Matter
    """
    try:
        explore_mask = tag_utils.create_keyword_mask(df, 'Explore') | tag_utils.create_text_mask(df, ['explores', 'explore.'])
        map_mask = tag_utils.create_text_mask(df, ['map token', 'map tokens'])
        explore_counters = explore_mask & tag_utils.create_text_mask(df, ['+1/+1 counter'], regex=False)
        rules = [
            { 'mask': explore_mask, 'tags': ['Card Selection'] },
            { 'mask': explore_counters, 'tags': ['+1/+1 Counters'] },
            { 'mask': map_mask, 'tags': ['Card Selection', 'Tokens Matter'] }
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Explore/Map cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Explore/Map: %s', str(e))
        raise

### Rad counters
def tag_for_rad_counters(df: pd.DataFrame, color: str) -> None:
    """Tag Rad counter interactions as a dedicated theme."""
    try:
        required = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required)
        rad_mask = tag_utils.create_text_mask(df, ['rad counter', 'rad counters'])
        tag_utils.tag_with_logging(
            df, rad_mask, ['Rad Counters'], 'Rad counter cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Rad counters: %s', str(e))
        raise

### Discard Matters
def tag_for_discard_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that discard or care about discarding.

    Adds Discard Matters for:
    - Text that makes you discard a card (costs or effects)
    - Triggers on discarding
    Also adds Loot where applicable is handled elsewhere; this focuses on the theme surface.
    """
    try:
        # Events where YOU discard (as part of a cost or effect). Keep generic 'discard a card' but filter out opponent/each-player cases.
        discard_action_patterns = [
            r'you discard (?:a|one|two|three|x) card',
            r'discard (?:a|one|two|three|x) card',
            r'discard your hand',
            r'as an additional cost to (?:cast this spell|activate this ability),? discard (?:a|one) card',
            r'as an additional cost,? discard (?:a|one) card'
        ]
        action_mask = tag_utils.create_text_mask(df, discard_action_patterns)
        exclude_opponent_patterns = [
            r'target player discards',
            r'target opponent discards',
            r'each player discards',
            r'each opponent discards',
            r'that player discards'
        ]
        exclude_mask = tag_utils.create_text_mask(df, exclude_opponent_patterns)

        # Triggers/conditions that care when you discard
        discard_trigger_patterns = [
            r'whenever you discard',
            r'if you discarded',
            r'for each card you discarded',
            r'when you discard'
        ]
        trigger_mask = tag_utils.create_text_mask(df, discard_trigger_patterns)

        # Blood tokens enable rummage (discard), and Madness explicitly cares about discarding
        blood_patterns = [r'create (?:a|one|two|three|x|\d+) blood token']
        blood_mask = tag_utils.create_text_mask(df, blood_patterns)
        madness_mask = tag_utils.create_text_mask(df, [r'\bmadness\b'])

        final_mask = ((action_mask & ~exclude_mask) | trigger_mask | blood_mask | madness_mask)
        tag_utils.tag_with_logging(
            df, final_mask, ['Discard Matters'], 'Discard Matters cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error('Error tagging Discard Matters: %s', str(e))
        raise

### Life Matters
def tag_for_life_matters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about life totals, life gain/loss, and related effects using vectorized operations.

    This function coordinates multiple subfunctions to handle different life-related aspects:
    - Lifegain effects and triggers
    - Lifelink and lifelink-like abilities
    - Life loss triggers and effects
    - Food token creation and effects
    - Life-related kindred synergies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting "Life Matters" tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'type', 'creatureTypes'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of life effect
        tag_for_lifegain(df, color)
        logger.info('Completed lifegain tagging')
        print('\n==========\n')

        tag_for_lifelink(df, color)
        logger.info('Completed lifelink tagging')
        print('\n==========\n')

        tag_for_life_loss(df, color)
        logger.info('Completed life loss tagging')
        print('\n==========\n')

        tag_for_food(df, color)
        logger.info('Completed food token tagging')
        print('\n==========\n')

        tag_for_life_kindred(df, color)
        logger.info('Completed life kindred tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all "Life Matters" tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_life_matters: {str(e)}')
        raise

def tag_for_lifegain(df: pd.DataFrame, color: str) -> None:
    """Tag cards with lifegain effects using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        gain_mask = (
            tag_utils.create_numbered_phrase_mask(df, ['gain', 'gains'], 'life')
            | tag_utils.create_text_mask(df, ['gain life', 'gains life'])
        )

        # Exclude replacement effects
        replacement_mask = tag_utils.create_text_mask(df, ['if you would gain life', 'whenever you gain life'])
        
        # Compute masks
        final_mask = gain_mask & ~replacement_mask
        trigger_mask = tag_utils.create_text_mask(df, ['if you would gain life', 'whenever you gain life'])

        rules = [
            { 'mask': final_mask,  'tags': ['Lifegain', 'Life Matters'] },
            { 'mask': trigger_mask, 'tags': ['Lifegain', 'Lifegain Triggers', 'Life Matters'] },
        ]
        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Lifegain cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging lifegain effects: {str(e)}')
        raise

def tag_for_lifelink(df: pd.DataFrame, color: str) -> None:
    """Tag cards with lifelink and lifelink-like effects using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        lifelink_mask = tag_utils.create_text_mask(df, 'lifelink')
        lifelike_mask = tag_utils.create_text_mask(df, [
            'deals damage, you gain that much life',
            'loses life.*gain that much life'
        ])

        # Exclude combat damage references for life loss conversion
        damage_mask = tag_utils.create_text_mask(df, 'deals damage')
        life_loss_mask = lifelike_mask & ~damage_mask
        final_mask = lifelink_mask | lifelike_mask | life_loss_mask

        tag_utils.tag_with_logging(
            df, final_mask, ['Lifelink', 'Lifegain', 'Life Matters'],
            'Lifelink cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging lifelink effects: {str(e)}')
        raise

def tag_for_life_loss(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about life loss using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        text_patterns = [
            'you lost life',
            'you gained and lost life',
            'you gained or lost life',
            'you would lose life',
            'you\'ve gained and lost life this turn',
            'you\'ve lost life',
            'whenever you gain or lose life',
            'whenever you lose life'
        ]
        text_mask = tag_utils.create_text_mask(df, text_patterns)

        tag_utils.tag_with_logging(
            df, text_mask, ['Lifeloss', 'Lifeloss Triggers', 'Life Matters'],
            'Life loss cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging life loss effects: {str(e)}')
        raise

def tag_for_food(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create or care about Food using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        final_mask = tag_utils.build_combined_mask(
            df, text_patterns='food', type_patterns='food'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Food', 'Lifegain', 'Life Matters'], 'Food cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Food effects: {str(e)}')
        raise

def tag_for_life_kindred(df: pd.DataFrame, color: str) -> None:
    """Tag cards with life-related kindred synergies using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        life_tribes = ['Angel', 'Bat', 'Cleric', 'Vampire']
        kindred_mask = df['creatureTypes'].apply(lambda x: any(tribe in x for tribe in life_tribes))
        
        tag_utils.tag_with_logging(
            df, kindred_mask, ['Lifegain', 'Life Matters'], 'life-related kindred cards', 
            color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging life kindred effects: {str(e)}')
        raise

### Counters
def tag_for_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about or interact with counters using vectorized operations.

    This function identifies and tags cards that:
    - Add or remove counters (+1/+1, -1/-1, special counters)
    - Care about counters being placed or removed
    - Have counter-based abilities (proliferate, undying, etc)
    - Create or modify counters

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Counters Matter', '+1/+1 Counters', etc.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting counter-related tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'name', 'creatureTypes'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of counter effect
        tag_for_general_counters(df, color)
        logger.info('Completed general counter tagging')
        print('\n==========\n')

        tag_for_plus_counters(df, color)
        logger.info('Completed +1/+1 counter tagging')
        print('\n==========\n')

        tag_for_minus_counters(df, color)
        logger.info('Completed -1/-1 counter tagging')
        print('\n==========\n')

        tag_for_special_counters(df, color)
        logger.info('Completed special counter tagging')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all counter-related tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_counters: {str(e)}')
        raise

def tag_for_general_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about counters in general using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        text_patterns = [
            'choose a kind of counter',
            'if it had counters',
            'move a counter',
            'one or more counters',
            'proliferate',
            'remove a counter',
            'with counters on them'
        ]
        text_mask = tag_utils.create_text_mask(df, text_patterns)
        specific_cards = [
            'banner of kinship',
            'damning verdict',
            'ozolith'
        ]
        name_mask = tag_utils.create_name_mask(df, specific_cards)
        final_mask = text_mask | name_mask

        tag_utils.tag_with_logging(
            df, final_mask, ['Counters Matter'], 'General counter cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging general counter effects: {str(e)}')
        raise

def tag_for_plus_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about +1/+1 counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Create text pattern mask using compiled patterns
        text_mask = (
            df['text'].str.contains(rgx.PLUS_ONE_COUNTER.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.IF_HAD_COUNTERS.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.ONE_OR_MORE_COUNTERS.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.ONE_OR_MORE_PLUS_ONE_COUNTERS.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.PROLIFERATE.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.UNDYING.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.WITH_COUNTERS_ON_THEM.pattern, case=False, na=False, regex=True)
        )
        # Create creature type mask
        type_mask = df['creatureTypes'].apply(lambda x: 'Hydra' in x if isinstance(x, list) else False)
        final_mask = text_mask | type_mask

        tag_utils.tag_with_logging(
            df, final_mask, ['+1/+1 Counters', 'Counters Matter', 'Voltron'],
            '+1/+1 counter cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging +1/+1 counter effects: {str(e)}')
        raise

def tag_for_minus_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about -1/-1 counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        # Create text pattern mask
        text_patterns = [
            '-1/-1 counter',
            'if it had counters',
            'infect',
            'one or more counter',
            'one or more -1/-1 counter',
            'persist',
            'proliferate',
            'wither'
        ]
        text_mask = tag_utils.create_text_mask(df, text_patterns)
        
        tag_utils.tag_with_logging(
            df, text_mask, ['-1/-1 Counters', 'Counters Matter'],
            '-1/-1 counter cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging -1/-1 counter effects: {str(e)}')
        raise

def tag_for_special_counters(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about special counters using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes
    """
    try:
        rules = []
        for counter_type in tag_constants.COUNTER_TYPES:
            pattern = f'{counter_type} counter'
            mask = tag_utils.create_text_mask(df, pattern)
            tags = [f'{counter_type} Counters', 'Counters Matter']
            rules.append({ 'mask': mask, 'tags': tags })

        tag_utils.tag_with_rules_and_logging(
            df, rules, 'Special counter cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging special counter effects: {str(e)}')
        raise

### Voltron
def create_voltron_commander_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that are Voltron commanders.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Voltron commanders
    """
    return tag_utils.create_name_mask(df, tag_constants.VOLTRON_COMMANDER_CARDS)

def create_voltron_support_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that support Voltron strategies.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards support Voltron strategies
    """
    return tag_utils.create_text_mask(df, tag_constants.VOLTRON_PATTERNS)

def create_voltron_equipment_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for Equipment-based Voltron cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Equipment-based Voltron cards
    """
    return tag_utils.create_type_mask(df, 'Equipment')

def create_voltron_aura_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for Aura-based Voltron cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Aura-based Voltron cards
    """
    return tag_utils.create_type_mask(df, 'Aura')

def tag_for_voltron(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Voltron strategy.

    This function identifies and tags cards that support the Voltron strategy including:
    - Voltron commanders
    - Equipment and Auras
    - Cards that care about equipped/enchanted creatures
    - Cards that enhance single creatures

    The function uses vectorized operations for performance and follows patterns
    established in other tagging functions.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'type', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        commander_mask = create_voltron_commander_mask(df)
        support_mask = create_voltron_support_mask(df)
        equipment_mask = create_voltron_equipment_mask(df)
        aura_mask = create_voltron_aura_mask(df)
        final_mask = commander_mask | support_mask | equipment_mask | aura_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Voltron'],
            'Voltron strategy cards', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_voltron: {str(e)}')
        raise

### Lands matter
def create_lands_matter_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about lands in general.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have lands matter effects
    """
    name_mask = tag_utils.create_name_mask(df, tag_constants.LANDS_MATTER_SPECIFIC_CARDS)

    # Create text pattern masks
    play_mask = tag_utils.create_text_mask(df, tag_constants.LANDS_MATTER_PATTERNS['land_play'])
    search_mask = tag_utils.create_text_mask(df, tag_constants.LANDS_MATTER_PATTERNS['land_search']) 
    state_mask = tag_utils.create_text_mask(df, tag_constants.LANDS_MATTER_PATTERNS['land_state'])
    return name_mask | play_mask | search_mask | state_mask

def create_domain_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with domain effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have domain effects
    """
    keyword_mask = tag_utils.create_keyword_mask(df, tag_constants.DOMAIN_PATTERNS['keyword'])
    text_mask = tag_utils.create_text_mask(df, tag_constants.DOMAIN_PATTERNS['text'])
    return keyword_mask | text_mask

def create_landfall_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with landfall triggers.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have landfall effects
    """
    keyword_mask = tag_utils.create_keyword_mask(df, tag_constants.LANDFALL_PATTERNS['keyword'])
    trigger_mask = tag_utils.create_text_mask(df, tag_constants.LANDFALL_PATTERNS['triggers'])
    return keyword_mask | trigger_mask

def create_landwalk_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with landwalk abilities.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have landwalk abilities
    """
    basic_mask = tag_utils.create_text_mask(df, tag_constants.LANDWALK_PATTERNS['basic'])
    nonbasic_mask = tag_utils.create_text_mask(df, tag_constants.LANDWALK_PATTERNS['nonbasic'])
    return basic_mask | nonbasic_mask

def create_land_types_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that care about specific land types.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards care about specific land types
    """
    # Create type-based mask
    type_mask = tag_utils.create_type_mask(df, tag_constants.LAND_TYPES)
    text_masks = []
    for land_type in tag_constants.LAND_TYPES:
        patterns = [
            f'search your library for a {land_type.lower()}',
            f'search your library for up to two {land_type.lower()}',
            f'{land_type} you control'
        ]
        text_masks.append(tag_utils.create_text_mask(df, patterns))
    return type_mask | pd.concat(text_masks, axis=1).any(axis=1)

def tag_for_lands_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about lands using vectorized operations.

    This function identifies and tags cards with land-related effects including:
    - General lands matter effects (searching, playing additional lands, etc)
    - Domain effects
    - Landfall triggers
    - Landwalk abilities
    - Specific land type matters

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    print('\n==========\n')

    try:
        required_cols = {'text', 'themeTags', 'type', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        lands_mask = create_lands_matter_mask(df)
        domain_mask = create_domain_mask(df)
        landfall_mask = create_landfall_mask(df)
        landwalk_mask = create_landwalk_mask(df)
        types_mask = create_land_types_mask(df)
        rules = [
            {'mask': lands_mask, 'tags': ['Lands Matter']},
            {'mask': domain_mask, 'tags': ['Domain', 'Lands Matter']},
            {'mask': landfall_mask, 'tags': ['Landfall', 'Lands Matter']},
            {'mask': landwalk_mask, 'tags': ['Landwalk', 'Lands Matter']},
            {'mask': types_mask, 'tags': ['Land Types Matter', 'Lands Matter']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'lands matter effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error in tag_for_lands_matter: {str(e)}')
        raise

### Spells Matter
def create_spellslinger_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spellslinger text patterns.

    This function identifies cards that care about casting spells through text patterns like:
    - Casting modal spells
    - Casting spells from anywhere
    - Casting instant/sorcery spells
    - Casting noncreature spells
    - First/next spell cast triggers

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spellslinger text patterns
    """
    text_patterns = [
        'cast a modal',
        'cast a spell from anywhere',
        'cast an instant',
        'cast a noncreature',
        'casts an instant',
        'casts a noncreature',
        'first instant',
        'first spell',
        'next cast an instant',
        'next instant',
        'next spell',
        'second instant',
        'second spell',
        'you cast an instant',
        'you cast a spell'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_spellslinger_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spellslinger-related keywords.

    This function identifies cards with keywords that indicate they care about casting spells:
    - Magecraft
    - Storm
    - Prowess
    - Surge
    
    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spellslinger keywords
    """
    keyword_patterns = [
        'Magecraft',
        'Storm',
        'Prowess',
        'Surge'
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_spellslinger_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for instant/sorcery type cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are instants or sorceries
    """
    return tag_utils.create_type_mask(df, ['Instant', 'Sorcery'])

def create_spellslinger_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from spellslinger tagging.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    excluded_names = [
        'Possibility Storm',
        'Wild-Magic Sorcerer'
    ]
    return tag_utils.create_name_mask(df, excluded_names)

def tag_for_spellslinger(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about casting spells using vectorized operations.

    This function identifies and tags cards that care about spellcasting including:
    - Cards that trigger off casting spells
    - Instant and sorcery spells
    - Cards with spellslinger-related keywords
    - Cards that care about noncreature spells

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Spellslinger', 'Spells Matter', etc.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    logger.info(f'Starting Spellslinger tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_spellslinger_text_mask(df)
        keyword_mask = create_spellslinger_keyword_mask(df)
        type_mask = create_spellslinger_type_mask(df)
        exclusion_mask = create_spellslinger_exclusion_mask(df)
        final_mask = (text_mask | keyword_mask | type_mask) & ~exclusion_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Spellslinger', 'Spells Matter'],
            'general Spellslinger cards', color=color, logger=logger
        )
        
        # Run non-generalized tags
        tag_for_storm(df, color)
        tag_for_magecraft(df, color)
        tag_for_cantrips(df, color)
        tag_for_spell_copy(df, color)

    except Exception as e:
        logger.error(f'Error in tag_for_spellslinger: {str(e)}')
        raise

def create_storm_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with storm effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have storm effects
    """
    # Create keyword mask
    keyword_mask = tag_utils.create_keyword_mask(df, 'Storm')

    # Create text mask
    text_patterns = [
        'gain storm',
        'has storm',
        'have storm'
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    return keyword_mask | text_mask

def tag_for_storm(df: pd.DataFrame, color: str) -> None:
    """Tag cards with storm effects using vectorized operations.

    This function identifies and tags cards that:
    - Have the storm keyword
    - Grant or care about storm

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        storm_mask = create_storm_mask(df)
        tag_utils.tag_with_logging(
            df, storm_mask, ['Storm', 'Spellslinger', 'Spells Matter'],
            'Storm cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Storm effects: {str(e)}')
        raise

## Tag for Cantrips
def tag_for_cantrips(df: pd.DataFrame, color: str) -> None:
    """Tag cards in the DataFrame as cantrips based on specific criteria.

    Cantrips are defined as low-cost spells (mana value <= 2) that draw cards.
    The function excludes certain card types, keywords, and specific named cards
    from being tagged as cantrips.

    Args:
        df: The DataFrame containing card data
        color: The color identifier for logging purposes
    """
    try:
        # Convert mana value to numeric
        df['manaValue'] = pd.to_numeric(df['manaValue'], errors='coerce')

        # Create exclusion masks
        excluded_types = tag_utils.create_type_mask(df, 'Land|Equipment')
        excluded_keywords = tag_utils.create_keyword_mask(df, ['Channel', 'Cycling', 'Connive', 'Learn', 'Ravenous'])
        has_loot = df['themeTags'].apply(lambda x: 'Loot' in x)

        # Define name exclusions
        EXCLUDED_NAMES = {
            'Archivist of Oghma', 'Argothian Enchantress', 'Audacity', 'Betrayal', 'Bequeathal', 'Blood Scrivener', 'Brigon, Soldier of Meletis',
            'Compost', 'Concealing curtains // Revealing Eye', 'Cryptbreaker', 'Curiosity', 'Cuse of Vengeance', 'Cryptek', 'Dakra Mystic',
            'Dawn of a New Age', 'Dockside Chef', 'Dreamcatcher', 'Edgewall Innkeeper', 'Eidolon of Philosophy', 'Evolved Sleeper',
            'Femeref Enchantress', 'Finneas, Ace Archer', 'Flumph', 'Folk Hero', 'Frodo, Adventurous Hobbit', 'Goblin Artisans',
            'Goldberry, River-Daughter', 'Gollum, Scheming Guide', 'Hatching Plans', 'Ideas Unbound', 'Ingenius Prodigy', 'Ior Ruin Expedition',
            "Jace's Erasure", 'Keeper of the Mind', 'Kor Spiritdancer', 'Lodestone Bauble', 'Puresteel Paladin', 'Jeweled Bird', 'Mindblade Render',
            "Multani's Presence", "Nahiri's Lithoforming", 'Ordeal of Thassa', 'Pollywog Prodigy', 'Priest of Forgotten Gods', 'Ravenous Squirrel',
            'Read the Runes', 'Red Death, Shipwrecker', 'Roil Cartographer', 'Sage of Lat-Name', 'Saprazzan Heir', 'Scion of Halaster', 'See Beyond',
            'Selhoff Entomber', 'Shielded Aether Theif', 'Shore Keeper', 'silverquill Silencer', 'Soldevi Sage', 'Soldevi Sentry', 'Spiritual Focus',
            'Sram, Senior Edificer', 'Staff of the Storyteller', 'Stirge', 'Sylvan Echoes', "Sythis Harvest's Hand", 'Sygg, River Cutthroat',
            'Tenuous Truce', 'Test of Talents', 'Thalakos seer', "Tribute to Horobi // Echo of Deaths Wail", 'Vampire Gourmand', 'Vampiric Rites',
            'Vampirism', 'Vessel of Paramnesia', "Witch's Caultron", 'Wall of Mulch', 'Waste Not', 'Well Rested'
            # Add other excluded names here
        }
        excluded_names = df['name'].isin(EXCLUDED_NAMES)

        # Create cantrip condition masks
        has_draw = tag_utils.create_text_mask(df, tag_constants.PATTERN_GROUPS['draw'])
        low_cost = df['manaValue'].fillna(float('inf')) <= 2

        # Combine conditions
        cantrip_mask = (
            ~excluded_types &
            ~excluded_keywords &
            ~has_loot &
            ~excluded_names &
            has_draw &
            low_cost
        )
        tag_utils.apply_rules(df, [
            { 'mask': cantrip_mask, 'tags': tag_constants.TAG_GROUPS['Cantrips'] },
        ])

        # Log results
        cantrip_count = cantrip_mask.sum()
        logger.info(f'Tagged {cantrip_count} Cantrip cards')

    except Exception as e:
        logger.error('Error tagging Cantrips in %s_cards.csv: %s', color, str(e))
        raise

## Magecraft
def create_magecraft_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with magecraft effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have magecraft effects
    """
    return tag_utils.create_keyword_mask(df, 'Magecraft')

def tag_for_magecraft(df: pd.DataFrame, color: str) -> None:
    """Tag cards with magecraft using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        magecraft_mask = create_magecraft_mask(df)
        tag_utils.tag_with_logging(
            df, magecraft_mask, ['Magecraft', 'Spellslinger', 'Spells Matter'],
            'Magecraft cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error tagging Magecraft effects: {str(e)}')
        raise
    
## Spell Copy
def create_spell_copy_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spell copy text patterns.

    This function identifies cards that copy spells through text patterns like:
    - Copy target spell
    - Copy that spell
    - Copy the next spell
    - Create copies of spells

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spell copy text patterns
    """
    text_patterns = [
        'copy a spell',
        'copy it',
        'copy that spell',
        'copy target',
        'copy the next',
        'create a copy',
        'creates a copy'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_spell_copy_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with spell copy related keywords.

    This function identifies cards with keywords that indicate they copy spells:
    - Casualty
    - Conspire
    - Replicate
    - Storm
    
    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have spell copy keywords
    """
    keyword_patterns = [
        'Casualty',
        'Conspire',
        'Replicate',
        'Storm'
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def tag_for_spell_copy(df: pd.DataFrame, color: str) -> None:
    """Tag cards that copy spells using vectorized operations.

    This function identifies and tags cards that copy spells including:
    - Cards that directly copy spells
    - Cards with copy-related keywords
    - Cards that create copies of spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_spell_copy_text_mask(df)
        keyword_mask = create_spell_copy_keyword_mask(df)
        final_mask = text_mask | keyword_mask
        tag_utils.apply_rules(df, [
            { 'mask': final_mask, 'tags': ['Spell Copy', 'Spellslinger', 'Spells Matter'] },
        ])

        # Log results
        spellcopy_count = final_mask.sum()
        logger.info(f'Tagged {spellcopy_count} spell copy cards')
    
    except Exception as e:
        logger.error(f'Error in tag_for_spell_copy: {str(e)}')
        raise

### Ramp
def create_mana_dork_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures that produce mana.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are mana dorks
    """
    # Create base creature mask
    creature_mask = tag_utils.create_type_mask(df, 'Creature')

    # Create text pattern masks
    tap_mask = tag_utils.create_text_mask(df, ['{T}: Add', '{T}: Untap'])
    sac_mask = tag_utils.create_text_mask(df, ['creature: add', 'control: add'])

    # Create mana symbol mask
    mana_patterns = [f'add {{{c}}}' for c in ['C', 'W', 'U', 'B', 'R', 'G']]
    mana_mask = tag_utils.create_text_mask(df, mana_patterns)

    # Create specific cards mask
    specific_cards = ['Awaken the Woods', 'Forest Dryad']
    name_mask = tag_utils.create_name_mask(df, specific_cards)

    return creature_mask & (tap_mask | sac_mask | mana_mask) | name_mask

def create_mana_rock_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for artifacts that produce mana.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are mana rocks
    """
    # Create base artifact mask
    artifact_mask = tag_utils.create_type_mask(df, 'Artifact')

    # Create text pattern masks
    tap_mask = tag_utils.create_text_mask(df, ['{T}: Add', '{T}: Untap'])
    sac_mask = tag_utils.create_text_mask(df, ['creature: add', 'control: add'])

    # Create mana symbol mask
    mana_patterns = [f'add {{{c}}}' for c in ['C', 'W', 'U', 'B', 'R', 'G']]
    mana_mask = tag_utils.create_text_mask(df, mana_patterns)

    # Create token mask
    token_mask = tag_utils.create_tag_mask(df, ['Powerstone Tokens', 'Treasure Tokens', 'Gold Tokens']) | \
                 tag_utils.create_text_mask(df, 'token named meteorite')

    return (artifact_mask & (tap_mask | sac_mask | mana_mask)) | token_mask

def create_extra_lands_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that allow playing additional lands.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards allow playing extra lands
    """
    text_patterns = [
        'additional land',
        'play an additional land',
        'play two additional lands',
        'put a land',
        'put all land',
        'put those land',
        'return all land',
        'return target land'
    ]

    return tag_utils.create_text_mask(df, text_patterns)

def create_land_search_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that search for lands.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards search for lands
    """
    # Create basic search patterns
    search_patterns = [
        'search your library for a basic',
        'search your library for a land',
        'search your library for up to',
        'each player searches',
        'put those land'
    ]

    # Create land type specific patterns
    land_types = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest', 'Wastes']
    for land_type in land_types:
        search_patterns.extend([
            f'search your library for a basic {land_type.lower()}',
            f'search your library for a {land_type.lower()}',
            f'search your library for an {land_type.lower()}'
        ])

    return tag_utils.create_text_mask(df, search_patterns)

def tag_for_ramp(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide mana acceleration using vectorized operations.

    This function identifies and tags cards that provide mana acceleration through:
    - Mana dorks (creatures that produce mana)
    - Mana rocks (artifacts that produce mana)
    - Extra land effects
    - Land search effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    print('\n==========\n')

    try:
        dork_mask = create_mana_dork_mask(df)
        rock_mask = create_mana_rock_mask(df)
        lands_mask = create_extra_lands_mask(df)
        search_mask = create_land_search_mask(df)
        rules = [
            {'mask': dork_mask, 'tags': ['Mana Dork', 'Ramp']},
            {'mask': rock_mask, 'tags': ['Mana Rock', 'Ramp']},
            {'mask': lands_mask, 'tags': ['Lands Matter', 'Ramp']},
            {'mask': search_mask, 'tags': ['Lands Matter', 'Ramp']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'ramp effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error in tag_for_ramp: {str(e)}')
        raise

### Other Misc Themes
def tag_for_themes(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit other themes that haven't been done so far.

    This function will call on functions to tag for:
    - Aggo
    - Aristocrats
    - Big Mana
    - Blink
    - Burn
    - Clones
    - Control
    - Energy
    - Infect
    - Legends Matter
    - Little Creatures
    - Mill
    - Monarch
    - Multiple Copy Cards (i.e. Hare Apparent or Dragon's Approach)
    - Superfriends
    - Reanimate
    - Stax
    - Theft
    - Toughess Matters
    - Topdeck
    - X Spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting tagging for remaining themes in {color}_cards.csv')
    print('\n===============\n')
    tag_for_aggro(df, color)
    print('\n==========\n')
    tag_for_aristocrats(df, color)
    print('\n==========\n')
    tag_for_big_mana(df, color)
    print('\n==========\n')
    tag_for_blink(df, color)
    print('\n==========\n')
    tag_for_burn(df, color)
    print('\n==========\n')
    tag_for_clones(df, color)
    print('\n==========\n')
    tag_for_control(df, color)
    print('\n==========\n')
    tag_for_energy(df, color)
    print('\n==========\n')
    tag_for_infect(df, color)
    print('\n==========\n')
    tag_for_legends_matter(df, color)
    print('\n==========\n')
    tag_for_little_guys(df, color)
    print('\n==========\n')
    tag_for_mill(df, color)
    print('\n==========\n')
    tag_for_monarch(df, color)
    print('\n==========\n')
    tag_for_multiple_copies(df, color)
    print('\n==========\n')
    tag_for_planeswalkers(df, color)
    print('\n==========\n')
    tag_for_reanimate(df, color)
    print('\n==========\n')
    tag_for_stax(df, color)
    print('\n==========\n')
    tag_for_theft(df, color)
    print('\n==========\n')
    tag_for_toughness(df, color)
    print('\n==========\n')
    tag_for_topdeck(df, color)
    print('\n==========\n')
    tag_for_x_spells(df, color)
    print('\n==========\n')
    
    duration = (pd.Timestamp.now() - start_time).total_seconds()
    logger.info(f'Completed theme tagging in {duration:.2f}s')
    
## Aggro
def create_aggro_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro text patterns
    """
    text_patterns = [
        'a creature attacking',
        'deal combat damage',
        'deals combat damage', 
        'have riot',
        'this creature attacks',
        'whenever you attack',
        'whenever .* attack',
        'whenever .* deals combat',
        'you control attack',
        'you control deals combat',
        'untap all attacking creatures'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_aggro_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro keywords
    """
    keyword_patterns = [
        'Blitz',
        'Deathtouch',
        'Double Strike', 
        'First Strike',
        'Fear',
        'Haste',
        'Menace',
        'Myriad',
        'Prowl',
        'Raid',
        'Shadow',
        'Spectacle',
        'Trample'
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_aggro_theme_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aggro-related themes.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aggro themes
    """
    return tag_utils.create_tag_mask(df, ['Voltron'])

def tag_for_aggro(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Aggro theme using vectorized operations.

    This function identifies and tags cards that support aggressive strategies including:
    - Cards that care about attacking
    - Cards with combat-related keywords
    - Cards that deal combat damage
    - Cards that support Voltron strategies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_aggro_text_mask(df)
        keyword_mask = create_aggro_keyword_mask(df)
        theme_mask = create_aggro_theme_mask(df)
        final_mask = text_mask | keyword_mask | theme_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Aggro', 'Combat Matters'],
            'Aggro strategy cards', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_aggro: {str(e)}')
        raise


## Aristocrats
def create_aristocrat_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aristocrat-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aristocrat text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.ARISTOCRAT_TEXT_PATTERNS)

def create_aristocrat_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific aristocrat-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific aristocrat cards
    """
    return tag_utils.create_name_mask(df, tag_constants.ARISTOCRAT_SPECIFIC_CARDS)

def create_aristocrat_self_sacrifice_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures with self-sacrifice effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which creatures have self-sacrifice effects
    """
    # Create base creature mask
    creature_mask = tag_utils.create_type_mask(df, 'Creature')
    
    # Create name-based patterns
    def check_self_sacrifice(row):
        if pd.isna(row['text']) or pd.isna(row['name']):
            return False
        name = row['name'].lower()
        text = row['text'].lower()
        return f'sacrifice {name}' in text or f'when {name} dies' in text
    
    # Apply patterns to creature cards
    return creature_mask & df.apply(check_self_sacrifice, axis=1)

def create_aristocrat_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with aristocrat-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have aristocrat keywords
    """
    return tag_utils.create_keyword_mask(df, 'Blitz')

def create_aristocrat_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from aristocrat effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return tag_utils.create_text_mask(df, tag_constants.ARISTOCRAT_EXCLUSION_PATTERNS)

def tag_for_aristocrats(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Aristocrats or Sacrifice Matters themes using vectorized operations.

    This function identifies and tags cards that care about sacrificing permanents or creatures dying, including:
    - Cards with sacrifice abilities or triggers
    - Cards that care about creatures dying
    - Cards with self-sacrifice effects
    - Cards with Blitz or similar mechanics

    The function uses efficient vectorized operations and separate mask creation functions
    for different aspects of the aristocrats theme. It handles:
    - Text-based patterns for sacrifice and death triggers
    - Specific named cards known for aristocrats strategies
    - Self-sacrifice effects on creatures
    - Relevant keywords like Blitz
    - Proper exclusions to avoid false positives

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'name', 'type', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_aristocrat_text_mask(df)
        name_mask = create_aristocrat_name_mask(df)
        self_sacrifice_mask = create_aristocrat_self_sacrifice_mask(df)
        keyword_mask = create_aristocrat_keyword_mask(df)
        exclusion_mask = create_aristocrat_exclusion_mask(df)
        final_mask = (text_mask | name_mask | self_sacrifice_mask | keyword_mask) & ~exclusion_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Aristocrats', 'Sacrifice Matters'],
            'aristocrats effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_aristocrats: {str(e)}')
        raise

### Bending
def tag_for_bending(df: pd.DataFrame, color: str) -> None:
    """Tag cards for bending-related keywords.

    Looks for 'airbend', 'waterbend', 'firebend', 'earthbend' in rules text and
    applies tags accordingly.
    """
    try:
        air_mask = tag_utils.create_text_mask(df, 'airbend')
        water_mask = tag_utils.create_text_mask(df, 'waterbend')
        fire_mask = tag_utils.create_text_mask(df, 'firebend')
        earth_mask = tag_utils.create_text_mask(df, 'earthbend')
        bending_mask = air_mask | water_mask | fire_mask | earth_mask
        rules = [
            {'mask': air_mask, 'tags': ['Airbending', 'Exile Matters', 'Leave the Battlefield']},
            {'mask': water_mask, 'tags': ['Waterbending', 'Cost Reduction', 'Big Mana']},
            {'mask': fire_mask, 'tags': ['Aggro', 'Combat Matters', 'Firebending', 'Mana Dork', 'Ramp', 'X Spells']},
            {'mask': earth_mask, 'tags': ['Earthbending', 'Lands Matter', 'Landfall']},
            {'mask': bending_mask, 'tags': ['Bending']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'bending effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging Bending keywords: {str(e)}')
        raise

### Web-Slinging
def tag_for_web_slinging(df: pd.DataFrame, color: str) -> None:
    """Tag cards for web-slinging related keywords.

    Looks for 'web-slinging' in rules text and applies tags accordingly.
    """
    try:
        webslinging_mask = tag_utils.create_text_mask(df, 'web-slinging')
        rules = [
            {'mask': webslinging_mask, 'tags': ['Web-slinging']},
        ]
        tag_utils.tag_with_rules_and_logging(df, rules, 'web-slinging effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging Web-Slinging keywords: {str(e)}')
        raise

### Tag for land types
def tag_for_land_types(df: pd.DataFrame, color: str) -> None:
    """Tag card for specific non-basic land types.

    Looks for 'Cave', 'Desert', 'Gate', 'Lair', 'Locus', 'Sphere', 'Urza's' in rules text and applies tags accordingly.
    """
    try:
        cave_mask = (
            (tag_utils.create_text_mask(df, 'Cave') & ~tag_utils.create_text_mask(df, 'scavenge')) |
            tag_utils.create_type_mask(df, 'Cave')
        )
        desert_mask = (
            tag_utils.create_text_mask(df, 'Desert') |
            tag_utils.create_type_mask(df, 'Desert')
        )
        gate_mask = (
            (
                tag_utils.create_text_mask(df, 'Gate') & 
                ~tag_utils.create_text_mask(df, 'Agate') &
                ~tag_utils.create_text_mask(df, 'Legate') &
                ~tag_utils.create_text_mask(df, 'Throw widethe Gates') &
                ~tag_utils.create_text_mask(df, 'Eternity Gate') &
                ~tag_utils.create_text_mask(df, 'Investigates')
            ) |
            tag_utils.create_text_mask(df, 'Gate card') |
            tag_utils.create_type_mask(df, 'Gate')
        )
        lair_mask = (tag_utils.create_type_mask(df, 'Lair'))
        locus_mask = (tag_utils.create_type_mask(df, 'Locus'))
        sphere_mask = (
            (tag_utils.create_text_mask(df, 'Sphere') & ~tag_utils.create_text_mask(df, 'Detention Sphere')) |
            tag_utils.create_type_mask(df, 'Sphere'))
        urzas_mask = (tag_utils.create_type_mask(df, "Urza's"))
        rules = [
            {'mask': cave_mask, 'tags': ['Caves Matter', 'Lands Matter']},
            {'mask': desert_mask, 'tags': ['Deserts Matter', 'Lands Matter']},
            {'mask': gate_mask, 'tags': ['Gates Matter', 'Lands Matter']},
            {'mask': lair_mask, 'tags': ['Lairs Matter', 'Lands Matter']},
            {'mask': locus_mask, 'tags': ['Locus Matter', 'Lands Matter']},
            {'mask': sphere_mask, 'tags': ['Spheres Matter', 'Lands Matter']},
            {'mask': urzas_mask, 'tags': ["Urza's Lands Matter", 'Lands Matter']},
        ]
        
        tag_utils.tag_with_rules_and_logging(df, rules, 'non-basic land types', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error tagging non-basic land types: {str(e)}')
        raise

## Big Mana
def create_big_mana_cost_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with high mana costs or X costs.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have high/X mana costs
    """
    # High mana value mask
    high_cost = df['manaValue'].fillna(0).astype(float) >= 5
    
    # X cost mask
    x_cost = df['manaCost'].fillna('').str.contains('{X}', case=False, regex=False)
    
    return high_cost | x_cost

def tag_for_big_mana(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about or generate large amounts of mana using vectorized operations.

    This function identifies and tags cards that:
    - Have high mana costs (5 or greater)
    - Care about high mana values or power
    - Generate large amounts of mana
    - Have X costs
    - Have keywords related to mana generation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'manaValue', 'manaCost', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = tag_utils.create_text_mask(df, tag_constants.BIG_MANA_TEXT_PATTERNS)
        keyword_mask = tag_utils.create_keyword_mask(df, tag_constants.BIG_MANA_KEYWORDS)
        cost_mask = create_big_mana_cost_mask(df)
        specific_mask = tag_utils.create_name_mask(df, tag_constants.BIG_MANA_SPECIFIC_CARDS)
        tag_mask = tag_utils.create_tag_mask(df, 'Cost Reduction')
        final_mask = text_mask | keyword_mask | cost_mask | specific_mask | tag_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Big Mana'],
            'big mana effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_big_mana: {str(e)}')
        raise

## Blink
def create_etb_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with enter-the-battlefield effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have ETB effects
    """
    text_patterns = [
        'creature entering causes',
        'permanent entering the battlefield',
        'permanent you control enters',
        'whenever another creature enters',
        'whenever another nontoken creature enters',
        'when this creature enters',
        'whenever this creature enters'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_ltb_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with leave-the-battlefield effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have LTB effects
    """
    text_patterns = [
        'when this creature leaves',
        'whenever this creature leaves'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_blink_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with blink/flicker text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have blink/flicker effects
    """
    text_patterns = [
        'exile any number of other',
        'exile one or more cards from your hand',
        'permanent you control, then return',
        'permanents you control, then return',
        'triggered ability of a permanent'
    ]
    # Include centralized return-to-battlefield phrasing
    return_mask = tag_utils.create_text_mask(df, tag_constants.PHRASE_GROUPS['blink_return'])
    base_mask = tag_utils.create_text_mask(df, text_patterns)
    return return_mask | base_mask

def tag_for_blink(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have blink/flicker effects using vectorized operations.

    This function identifies and tags cards with blink/flicker effects including:
    - Enter-the-battlefield (ETB) triggers
    - Leave-the-battlefield (LTB) triggers
    - Exile and return effects
    - Permanent flicker effects

    The function maintains proper tag hierarchy and ensures consistent application
    of related tags like 'Blink', 'Enter the Battlefield', and 'Leave the Battlefield'.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        etb_mask = create_etb_mask(df)
        ltb_mask = create_ltb_mask(df)
        blink_mask = create_blink_text_mask(df)

        # Create name-based masks
        name_patterns = df.apply(
            lambda row: re.compile(
                f'when {row["name"]} enters|whenever {row["name"]} enters|when {row["name"]} leaves|whenever {row["name"]} leaves',
                re.IGNORECASE
            ),
            axis=1
        )
        name_mask = df.apply(
            lambda row: bool(name_patterns[row.name].search(row['text'])) if pd.notna(row['text']) else False,
            axis=1
        )
        final_mask = etb_mask | ltb_mask | blink_mask | name_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Blink', 'Enter the Battlefield', 'Leave the Battlefield'],
            'blink/flicker effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_blink: {str(e)}')
        raise

## Burn
def create_burn_damage_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with damage-dealing effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have damage effects
    """
    # Match any numeric or X damage in a single regex for performance
    damage_pattern = r'deals\s+(?:[0-9]+|x)\s+damage'
    damage_mask = tag_utils.create_text_mask(df, damage_pattern)

    # Create general damage trigger patterns
    trigger_patterns = [
        'deals damage',
        'deals noncombat damage', 
        'deals that much damage',
        'excess damage',
        'excess noncombat damage',
        'would deal an amount of noncombat damage',
        'would deal damage',
        'would deal noncombat damage'
    ]
    trigger_mask = tag_utils.create_text_mask(df, trigger_patterns)

    # Create pinger patterns using compiled patterns
    pinger_mask = (
        df['text'].str.contains(rgx.DEALS_ONE_DAMAGE.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(rgx.EXACTLY_ONE_DAMAGE.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(rgx.LOSES_ONE_LIFE.pattern, case=False, na=False, regex=True)
    )

    return damage_mask | trigger_mask | pinger_mask

def create_burn_life_loss_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with life loss effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have life loss effects
    """
    # Create life loss patterns using a single numbered phrase mask
    life_mask = tag_utils.create_numbered_phrase_mask(df, verb=['lose', 'loses'], noun='life')

    # Create general life loss trigger patterns 
    trigger_patterns = [
        'each 1 life',
        'loses that much life',
        'opponent lost life',
        'opponent loses life', 
        'player loses life',
        'unspent mana causes that player to lose that much life',
        'would lose life'
    ]
    trigger_mask = tag_utils.create_text_mask(df, trigger_patterns)

    return life_mask | trigger_mask

def create_burn_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with burn-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have burn keywords
    """
    keyword_patterns = ['Bloodthirst', 'Spectacle']
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_burn_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from burn effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_burn(df: pd.DataFrame, color: str) -> None:
    """Tag cards that deal damage or cause life loss using vectorized operations.

    This function identifies and tags cards with burn effects including:
    - Direct damage dealing
    - Life loss effects
    - Burn-related keywords (Bloodthirst, Spectacle)
    - Pinger effects (1 damage)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        damage_mask = create_burn_damage_mask(df)
        life_mask = create_burn_life_loss_mask(df)
        keyword_mask = create_burn_keyword_mask(df)
        exclusion_mask = create_burn_exclusion_mask(df)
        burn_mask = (damage_mask | life_mask | keyword_mask) & ~exclusion_mask
        
        # Pinger mask using compiled patterns (eliminates duplication)
        pinger_mask = (
            df['text'].str.contains(rgx.DEALS_ONE_DAMAGE.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.EXACTLY_ONE_DAMAGE.pattern, case=False, na=False, regex=True) |
            df['text'].str.contains(rgx.LOSES_ONE_LIFE.pattern, case=False, na=False, regex=True)
        )
        tag_utils.tag_with_rules_and_logging(df, [
            {'mask': burn_mask, 'tags': ['Burn']},
            {'mask': pinger_mask & ~exclusion_mask, 'tags': ['Pingers']},
        ], 'burn effects', color=color, logger=logger)

    except Exception as e:
        logger.error(f'Error in tag_for_burn: {str(e)}')
        raise

## Clones
def create_clone_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with clone-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have clone text patterns
    """
    text_patterns = [
        'a copy of a creature',
        'a copy of an aura',
        'a copy of a permanent',
        'a token that\'s a copy of',
        'as a copy of',
        'becomes a copy of',
        '"legend rule" doesn\'t apply',
        'twice that many of those tokens'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_clone_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with clone-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have clone keywords
    """
    return tag_utils.create_keyword_mask(df, 'Myriad')

def create_clone_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from clone effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_clones(df: pd.DataFrame, color: str) -> None:
    """Tag cards that create copies or have clone effects using vectorized operations.

    This function identifies and tags cards that:
    - Create copies of creatures or permanents
    - Have copy-related keywords like Myriad
    - Ignore the legend rule
    - Double token creation

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_clone_text_mask(df)
        keyword_mask = create_clone_keyword_mask(df)
        exclusion_mask = create_clone_exclusion_mask(df)
        final_mask = (text_mask | keyword_mask) & ~exclusion_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Clones'],
            'clone effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_clones: {str(e)}')
        raise

## Control
def create_control_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with control-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have control text patterns
    """
    text_patterns = [
        'a player casts',
        'can\'t attack you',
        'cast your first spell during each opponent\'s turn', 
        'choose new target',
        'choose target opponent',
        'counter target',
        'of an opponent\'s choice',
        'opponent cast',
        'return target',
        'tap an untapped creature',
        'your opponents cast'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_control_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with control-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have control keywords
    """
    keyword_patterns = ['Council\'s dilemma']
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_control_specific_cards_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific control-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific control cards
    """
    specific_cards = [
        'Azor\'s Elocutors',
        'Baral, Chief of Compliance',
        'Dragonlord Ojutai',
        'Grand Arbiter Augustin IV',
        'Lavinia, Azorius Renegade',
        'Talrand, Sky Summoner'
    ]
    return tag_utils.create_name_mask(df, specific_cards)

def tag_for_control(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Control theme using vectorized operations.

    This function identifies and tags cards that control the game through:
    - Counter magic
    - Bounce effects
    - Tap effects
    - Opponent restrictions
    - Council's dilemma effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_control_text_mask(df)
        keyword_mask = create_control_keyword_mask(df)
        specific_mask = create_control_specific_cards_mask(df)
        final_mask = text_mask | keyword_mask | specific_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Control'],
            'control effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_control: {str(e)}')
        raise

## Energy
def tag_for_energy(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about energy counters using vectorized operations.

    This function identifies and tags cards that:
    - Use energy counters ({E})
    - Care about energy counters
    - Generate or spend energy

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        energy_mask = tag_utils.create_text_mask(df, [r'\{e\}', 'energy counter', 'energy counters'])
        tag_utils.tag_with_logging(
            df, energy_mask, ['Energy', 'Resource Engine'], 'energy cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_energy: {str(e)}')
        raise

## Infect
def create_infect_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with infect-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have infect text patterns
    """
    # Use compiled patterns for regex, plain strings for simple searches
    return (
        df['text'].str.contains('one or more counter', case=False, na=False) |
        df['text'].str.contains('poison counter', case=False, na=False) |
        df['text'].str.contains(rgx.TOXIC.pattern, case=False, na=False, regex=True)
    )

def create_infect_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with infect-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have infect keywords
    """
    keyword_patterns = [
        'Infect',
        'Proliferate', 
        'Toxic',
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_infect_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from infect effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return pd.Series(False, index=df.index)

def tag_for_infect(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have infect-related effects using vectorized operations.

    This function identifies and tags cards with infect effects including:
    - Infect keyword ability
    - Toxic keyword ability 
    - Proliferate mechanic
    - Poison counter effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        text_mask = create_infect_text_mask(df)
        keyword_mask = create_infect_keyword_mask(df)
        exclusion_mask = create_infect_exclusion_mask(df)
        final_mask = (text_mask | keyword_mask) & ~exclusion_mask

        tag_utils.tag_with_logging(
            df, final_mask, ['Infect'], 'infect cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_infect: {str(e)}')
        raise

## Legends Matter
def create_legends_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with legendary/historic text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have legendary/historic text patterns
    """
    text_patterns = [
        'a legendary creature',
        'another legendary',
        'cast a historic',
        'cast a legendary', 
        'cast legendary',
        'equip legendary',
        'historic cards',
        'historic creature',
        'historic permanent',
        'historic spells',
        'legendary creature you control',
        'legendary creatures you control',
        'legendary permanents',
        'legendary spells you',
        'number of legendary',
        'other legendary',
        'play a historic',
        'play a legendary',
        'target legendary',
        'the "legend rule" doesn\'t'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_legends_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with Legendary in their type line.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Legendary
    """
    return tag_utils.create_type_mask(df, 'Legendary')

def tag_for_legends_matter(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about legendary permanents using vectorized operations.

    This function identifies and tags cards that:
    - Are legendary permanents
    - Care about legendary permanents
    - Care about historic spells/permanents
    - Modify the legend rule

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'type'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_legends_text_mask(df)
        type_mask = create_legends_type_mask(df)
        final_mask = text_mask | type_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Historics Matter', 'Legends Matter'], 
            'legendary/historic effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_legends_matter: {str(e)}')
        raise

## Little Fellas
def create_little_guys_power_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for creatures with power 2 or less.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have power 2 or less
    """
    valid_power = pd.to_numeric(df['power'], errors='coerce')
    return (valid_power <= 2) & pd.notna(valid_power)

def tag_for_little_guys(df: pd.DataFrame, color: str) -> None:
    """Tag cards that are or care about low-power creatures using vectorized operations.

    This function identifies and tags:
    - Creatures with power 2 or less
    - Cards that care about creatures with low power
    - Cards that reference power thresholds of 2 or less

    The function handles edge cases like '*' in power values and maintains proper
    tag hierarchy.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'power', 'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        power_mask = create_little_guys_power_mask(df)
        text_mask = tag_utils.create_text_mask(df, 'power 2 or less')
        final_mask = power_mask | text_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Little Fellas'],
            'low-power creatures', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_little_guys: {str(e)}')
        raise

## Mill
def create_mill_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with mill-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have mill text patterns
    """
    # Create text pattern masks
    text_patterns = [
        'descended',
        'from a graveyard',
        'from your graveyard', 
        'in your graveyard',
        'into his or her graveyard',
        'into their graveyard',
        'into your graveyard',
        'mills that many cards',
        'opponent\'s graveyard',
        'put into a graveyard',
        'put into an opponent\'s graveyard', 
        'put into your graveyard',
        'rad counter',
        'surveil',
        'would mill'
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    # Create mill number patterns using a numbered phrase mask
    number_mask_cards = tag_utils.create_numbered_phrase_mask(df, ['mill', 'mills'], noun='cards')
    number_mask_plain = tag_utils.create_numbered_phrase_mask(df, ['mill', 'mills'])

    return text_mask | number_mask_cards | number_mask_plain

def create_mill_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with mill-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have mill keywords
    """
    keyword_patterns = ['Descend', 'Mill', 'Surveil']
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def tag_for_mill(df: pd.DataFrame, color: str) -> None:
    """Tag cards that mill cards or care about milling using vectorized operations.

    This function identifies and tags cards with mill effects including:
    - Direct mill effects (putting cards from library to graveyard)
    - Mill-related keywords (Descend, Mill, Surveil)
    - Cards that care about graveyards
    - Cards that track milled cards

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_mill_text_mask(df)
        keyword_mask = create_mill_keyword_mask(df)
        final_mask = text_mask | keyword_mask
        tag_utils.tag_with_logging(
            df, final_mask, ['Mill'],
            'mill effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_mill: {str(e)}')
        raise

def tag_for_monarch(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about the monarch mechanic using vectorized operations.

    This function identifies and tags cards that interact with the monarch mechanic, including:
    - Cards that make you become the monarch
    - Cards that prevent becoming the monarch
    - Cards with monarch-related triggers
    - Cards with the monarch keyword

    The function uses vectorized operations for performance and follows patterns
    established in other tagging functions.

    Args:
        df: DataFrame containing card data with text and keyword columns
        color: Color identifier for logging purposes (e.g. 'white', 'blue')

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Combine text and keyword masks
        final_mask = tag_utils.build_combined_mask(
            df, text_patterns=tag_constants.PHRASE_GROUPS['monarch'], keyword_patterns='Monarch'
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Monarch'], 'monarch cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_monarch: {str(e)}')
        raise

## Multi-copy cards
def tag_for_multiple_copies(df: pd.DataFrame, color: str) -> None:
    """Tag cards that allow having multiple copies in a deck using vectorized operations.

    This function identifies and tags cards that can have more than 4 copies in a deck,
    like Seven Dwarves or Persistent Petitioners. It uses the multiple_copy_cards list
    from settings to identify these cards.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'name', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        multiple_copies_mask = tag_utils.create_name_mask(df, MULTIPLE_COPY_CARDS)
        if multiple_copies_mask.any():
            matching_cards = df[multiple_copies_mask]['name'].unique()
            rules = [{'mask': multiple_copies_mask, 'tags': ['Multiple Copies']}]
            # Add per-card rules for individual name tags
            rules.extend({'mask': (df['name'] == card_name), 'tags': [card_name]} for card_name in matching_cards)
            tag_utils.apply_rules(df, rules=rules)
            logger.info(f'Tagged {multiple_copies_mask.sum()} cards with multiple copies effects for {color}')

    except Exception as e:
        logger.error(f'Error in tag_for_multiple_copies: {str(e)}')
        raise

## Planeswalkers
def create_planeswalker_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with planeswalker-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have planeswalker text patterns
    """
    text_patterns = [
        'a planeswalker',
        'affinity for planeswalker',
        'enchant planeswalker',
        'historic permanent',
        'legendary permanent', 
        'loyalty ability',
        'one or more counter',
        'planeswalker spells',
        'planeswalker type'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_planeswalker_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with Planeswalker type.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are Planeswalkers
    """
    return tag_utils.create_type_mask(df, 'Planeswalker')

def create_planeswalker_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with planeswalker-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have planeswalker keywords
    """
    return tag_utils.create_keyword_mask(df, 'Proliferate')

def tag_for_planeswalkers(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about planeswalkers using vectorized operations.

    This function identifies and tags cards that:
    - Are planeswalker cards
    - Care about planeswalkers
    - Have planeswalker-related keywords like Proliferate
    - Interact with loyalty abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_planeswalker_text_mask(df)
        type_mask = create_planeswalker_type_mask(df)
        keyword_mask = create_planeswalker_keyword_mask(df)
        final_mask = text_mask | type_mask | keyword_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Planeswalkers', 'Superfriends'], 
            'planeswalker effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_planeswalkers: {str(e)}')
        raise

## Reanimator
def create_reanimator_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator text patterns
    """
    text_patterns = [
        'descended',
        'discard your hand',
        'from a graveyard',
        'in a graveyard',
        'into a graveyard', 
        'leave a graveyard',
        'in your graveyard',
        'into your graveyard',
        'leave your graveyard'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_reanimator_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator keywords
    """
    keyword_patterns = [
        'Blitz',
        'Connive', 
        'Descend',
        'Escape',
        'Flashback',
        'Mill'
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_reanimator_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with reanimator-related creature types.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have reanimator creature types
    """
    return df['creatureTypes'].apply(lambda x: 'Zombie' in x if isinstance(x, list) else False)

def tag_for_reanimate(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about graveyard recursion using vectorized operations.

    This function identifies and tags cards with reanimator effects including:
    - Cards that interact with graveyards
    - Cards with reanimator-related keywords (Blitz, Connive, etc)
    - Cards that loot or mill
    - Zombie tribal synergies

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords', 'creatureTypes'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_reanimator_text_mask(df)
        keyword_mask = create_reanimator_keyword_mask(df)
        type_mask = create_reanimator_type_mask(df)
        final_mask = text_mask | keyword_mask | type_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Reanimate'], 
            'reanimator effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_reanimate: {str(e)}')
        raise

## Stax
def create_stax_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with stax-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.STAX_TEXT_PATTERNS)

def create_stax_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards used in stax strategies.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax text patterns
    """
    return tag_utils.create_name_mask(df, tag_constants.STAX_SPECIFIC_CARDS)

def create_stax_tag_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with stax-related tags.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have stax tags
    """
    return tag_utils.create_tag_mask(df, 'Control')

def create_stax_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from stax effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Add specific exclusion patterns here if needed
    return tag_utils.create_text_mask(df, tag_constants.STAX_EXCLUSION_PATTERNS)

def tag_for_stax(df: pd.DataFrame, color: str) -> None:
    """Tag cards that fit the Stax theme using vectorized operations.

    This function identifies and tags cards that restrict or tax opponents including:
    - Cards that prevent actions (can't attack, can't cast, etc)
    - Cards that tax actions (spells cost more)
    - Cards that control opponents' resources
    - Cards that create asymmetric effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_stax_text_mask(df)
        name_mask = create_stax_name_mask(df)
        tag_mask = create_stax_tag_mask(df)
        exclusion_mask = create_stax_exclusion_mask(df)
        final_mask = (text_mask | tag_mask | name_mask) & ~exclusion_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Stax'], 
            'stax effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_stax: {str(e)}')
        raise

## Pillowfort
def tag_for_pillowfort(df: pd.DataFrame, color: str) -> None:
    """Tag classic deterrent / taxation defensive permanents as Pillowfort.

    Heuristic: any card that either (a) appears in the specific card list or (b) contains a
    deterrent combat pattern in its rules text. Excludes cards already tagged as Stax where
    Stax intent is broader; we still allow overlap but do not require it.
    """
    try:
        required_cols = {'text','themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        final_mask = tag_utils.build_combined_mask(
            df, text_patterns=tag_constants.PILLOWFORT_TEXT_PATTERNS,
            name_list=tag_constants.PILLOWFORT_SPECIFIC_CARDS
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Pillowfort'], 'Pillowfort cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_pillowfort: {e}')
        raise

## Politics
def tag_for_politics(df: pd.DataFrame, color: str) -> None:
    """Tag cards that promote table negotiation, shared resources, votes, or gifting.

    Heuristic: match text patterns (vote, each player draws/gains, tempt offers, gifting target opponent, etc.)
    plus a curated list of high-signal political commanders / engines.
    """
    try:
        required_cols = {'text','themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        final_mask = tag_utils.build_combined_mask(
            df, text_patterns=tag_constants.POLITICS_TEXT_PATTERNS, 
            name_list=tag_constants.POLITICS_SPECIFIC_CARDS
        )
        tag_utils.tag_with_logging(
            df, final_mask, ['Politics'], 'Politics cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_politics: {e}')
        raise

## Control Archetype
## (Control archetype functions removed to avoid duplication; existing tag_for_control covers it)

## Midrange Archetype
def tag_for_midrange_archetype(df: pd.DataFrame, color: str) -> None:
    """Tag resilient, incremental value permanents for Midrange identity."""
    try:
        required_cols = {'text','themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        mask = tag_utils.build_combined_mask(
            df, text_patterns=tag_constants.MIDRANGE_TEXT_PATTERNS,
            name_list=tag_constants.MIDRANGE_SPECIFIC_CARDS
        )
        tag_utils.tag_with_logging(
            df, mask, ['Midrange'], 'Midrange archetype cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_midrange_archetype: {e}')
        raise

## Toolbox Archetype
def tag_for_toolbox_archetype(df: pd.DataFrame, color: str) -> None:
    """Tag tutor / search engine pieces that enable a toolbox plan."""
    try:
        required_cols = {'text','themeTags'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        mask = tag_utils.build_combined_mask(
            df, text_patterns=tag_constants.TOOLBOX_TEXT_PATTERNS,
            name_list=tag_constants.TOOLBOX_SPECIFIC_CARDS
        )
        tag_utils.tag_with_logging(
            df, mask, ['Toolbox'], 'Toolbox archetype cards', color=color, logger=logger
        )
    except Exception as e:
        logger.error(f'Error in tag_for_toolbox_archetype: {e}')
        raise

## Theft
def create_theft_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with theft-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have theft text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.THEFT_TEXT_PATTERNS)

def create_theft_name_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific theft-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific theft cards
    """
    return tag_utils.create_name_mask(df, tag_constants.THEFT_SPECIFIC_CARDS)

def tag_for_theft(df: pd.DataFrame, color: str) -> None:
    """Tag cards that steal or use opponents' resources using vectorized operations.

    This function identifies and tags cards that:
    - Cast spells owned by other players
    - Take control of permanents
    - Use opponents' libraries
    - Create theft-related effects

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_theft_text_mask(df)
        name_mask = create_theft_name_mask(df)
        final_mask = text_mask | name_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Theft'], 
            'theft effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_theft: {str(e)}')
        raise
    
## Toughness Matters
def create_toughness_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with toughness-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness text patterns
    """
    text_patterns = [
        'card\'s toughness',
        'creature\'s toughness',
        'damage equal to its toughness',
        'lesser toughness',
        'total toughness',
        'toughness greater',
        'with defender'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_toughness_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with toughness-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness keywords
    """
    return tag_utils.create_keyword_mask(df, 'Defender')

def _is_valid_numeric_comparison(power: Union[int, str, None], toughness: Union[int, str, None]) -> bool:
    """Check if power and toughness values allow valid numeric comparison.

    Args:
        power: Power value to check
        toughness: Toughness value to check

    Returns:
        True if values can be compared numerically, False otherwise
    """
    try:
        if power is None or toughness is None:
            return False
        return True
    except (ValueError, TypeError):
        return False

def create_power_toughness_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards where toughness exceeds power.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have toughness > power
    """
    valid_comparison = df.apply(
        lambda row: _is_valid_numeric_comparison(row['power'], row['toughness']),
        axis=1
    )
    numeric_mask = valid_comparison & (pd.to_numeric(df['toughness'], errors='coerce') > 
                                     pd.to_numeric(df['power'], errors='coerce'))
    return numeric_mask

def tag_for_toughness(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about toughness using vectorized operations.

    This function identifies and tags cards that:
    - Reference toughness in their text
    - Have the Defender keyword
    - Have toughness greater than power
    - Care about high toughness values

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords', 'power', 'toughness'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_toughness_text_mask(df)
        keyword_mask = create_toughness_keyword_mask(df)
        power_toughness_mask = create_power_toughness_mask(df)
        final_mask = text_mask | keyword_mask | power_toughness_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Toughness Matters'], 
            'toughness effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_toughness: {str(e)}')
        raise

## Topdeck
def create_topdeck_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with topdeck-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have topdeck text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.TOPDECK_TEXT_PATTERNS)

def create_topdeck_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with topdeck-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have topdeck keywords
    """
    return tag_utils.create_keyword_mask(df, tag_constants.TOPDECK_KEYWORDS)

def create_topdeck_specific_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific topdeck-related cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific topdeck cards
    """
    return tag_utils.create_name_mask(df, tag_constants.TOPDECK_SPECIFIC_CARDS)

def create_topdeck_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from topdeck effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return tag_utils.create_text_mask(df, tag_constants.TOPDECK_EXCLUSION_PATTERNS)

def tag_for_topdeck(df: pd.DataFrame, color: str) -> None:
    """Tag cards that manipulate the top of library using vectorized operations.

    This function identifies and tags cards that interact with the top of the library including:
    - Cards that look at or reveal top cards
    - Cards with scry or surveil effects
    - Cards with miracle or similar mechanics
    - Cards that care about the order of the library

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_topdeck_text_mask(df)
        keyword_mask = create_topdeck_keyword_mask(df)
        specific_mask = create_topdeck_specific_mask(df)
        exclusion_mask = create_topdeck_exclusion_mask(df)
        final_mask = (text_mask | keyword_mask | specific_mask) & ~exclusion_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Topdeck'], 
            'topdeck effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_topdeck: {str(e)}')
        raise

## X Spells
def create_x_spells_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with X spell-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have X spell text patterns
    """
    # Use compiled patterns for regex, plain strings for simple searches
    return (
        df['text'].str.contains(rgx.COST_LESS.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(r"don\'t lose (?:this|unspent|unused)", case=False, na=False, regex=True) |
        df['text'].str.contains('unused mana would empty', case=False, na=False) |
        df['text'].str.contains(rgx.WITH_X_IN_COST.pattern, case=False, na=False, regex=True) |
        df['text'].str.contains(rgx.SPELLS_YOU_CAST_COST.pattern, case=False, na=False, regex=True)
    )

def create_x_spells_mana_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with X in their mana cost.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have X in mana cost
    """
    return df['manaCost'].fillna('').str.contains('{X}', case=True, regex=False)

def tag_for_x_spells(df: pd.DataFrame, color: str) -> None:
    """Tag cards that care about X spells using vectorized operations.

    This function identifies and tags cards that:
    - Have X in their mana cost
    - Care about X spells or mana values
    - Have cost reduction effects for X spells
    - Preserve unspent mana

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'manaCost'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_x_spells_text_mask(df)
        mana_mask = create_x_spells_mana_mask(df)
        final_mask = text_mask | mana_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['X Spells'], 
            'X spell effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_x_spells: {str(e)}')
        raise

### Interaction
## Overall tag for interaction group
def tag_for_interaction(df: pd.DataFrame, color: str) -> None:
    """Tag cards that interact with the board state or stack.

    This function coordinates tagging of different interaction types including:
    - Counterspells
    - Board wipes
    - Combat tricks
    - Protection effects
    - Spot removal

    The function maintains proper tag hierarchy and ensures consistent application
    of interaction-related tags.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    start_time = pd.Timestamp.now()
    logger.info(f'Starting interaction effect tagging for {color}_cards.csv')
    print('\n==========\n')

    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'name', 'type', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Process each type of interaction
        sub_start = pd.Timestamp.now()
        tag_for_counterspells(df, color)
        logger.info(f'Completed counterspell tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_board_wipes(df, color)
        logger.info(f'Completed board wipe tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_combat_tricks(df, color)
        logger.info(f'Completed combat trick tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')

        sub_start = pd.Timestamp.now()
        tag_for_protection(df, color)
        logger.info(f'Completed protection tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')
        
        sub_start = pd.Timestamp.now()
        tag_for_phasing(df, color)
        logger.info(f'Completed phasing tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')
        
        sub_start = pd.Timestamp.now()
        tag_for_removal(df, color)
        logger.info(f'Completed removal tagging in {(pd.Timestamp.now() - sub_start).total_seconds():.2f}s')
        print('\n==========\n')
        duration = pd.Timestamp.now() - start_time
        logger.info(f'Completed all interaction tagging in {duration.total_seconds():.2f}s')

    except Exception as e:
        logger.error(f'Error in tag_for_interaction: {str(e)}')
        raise

## Counterspells
def create_counterspell_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with counterspell text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have counterspell text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.COUNTERSPELL_TEXT_PATTERNS)

def create_counterspell_specific_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for specific counterspell cards.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are specific counterspell cards
    """
    return tag_utils.create_name_mask(df, tag_constants.COUNTERSPELL_SPECIFIC_CARDS)

def create_counterspell_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from counterspell effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return tag_utils.create_text_mask(df, tag_constants.COUNTERSPELL_EXCLUSION_PATTERNS)

def tag_for_counterspells(df: pd.DataFrame, color: str) -> None:
    """Tag cards that counter spells using vectorized operations.

    This function identifies and tags cards that:
    - Counter spells directly
    - Return spells to hand/library
    - Exile spells from the stack
    - Care about countering spells

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
    """
    try:
        required_cols = {'text', 'themeTags', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_counterspell_text_mask(df)
        specific_mask = create_counterspell_specific_mask(df)
        exclusion_mask = create_counterspell_exclusion_mask(df)
        final_mask = (text_mask | specific_mask) & ~exclusion_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Counterspells', 'Interaction', 'Spellslinger', 'Spells Matter'],
            'counterspell effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_counterspells: {str(e)}')
        raise

## Board Wipes
def tag_for_board_wipes(df: pd.DataFrame, color: str) -> None:
    """Tag cards that have board wipe effects using vectorized operations.

    This function identifies and tags cards with board wipe effects including:
    - Mass destruction effects (destroy all/each)
    - Mass exile effects (exile all/each)
    - Mass bounce effects (return all/each)
    - Mass sacrifice effects (sacrifice all/each)
    - Mass damage effects (damage to all/each)

    The function uses helper functions to identify different types of board wipes
    and applies tags consistently using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'name'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        destroy_mask = tag_utils.create_mass_effect_mask(df, 'mass_destruction')
        exile_mask = tag_utils.create_mass_effect_mask(df, 'mass_exile')
        bounce_mask = tag_utils.create_mass_effect_mask(df, 'mass_bounce')
        sacrifice_mask = tag_utils.create_mass_effect_mask(df, 'mass_sacrifice')
        damage_mask = tag_utils.create_mass_damage_mask(df)

        # Create exclusion mask
        exclusion_mask = tag_utils.create_text_mask(df, tag_constants.BOARD_WIPE_EXCLUSION_PATTERNS)

        # Create specific cards mask
        specific_mask = tag_utils.create_name_mask(df, tag_constants.BOARD_WIPE_SPECIFIC_CARDS)
        final_mask = (
            destroy_mask | exile_mask | bounce_mask | 
            sacrifice_mask | damage_mask | specific_mask
        ) & ~exclusion_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Board Wipes', 'Interaction'],
            'board wipe effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_board_wipes: {str(e)}')
        raise

    logger.info(f'Completed board wipe tagging for {color}_cards.csv')

## Combat Tricks
def create_combat_tricks_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with combat trick text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have combat trick text patterns
    """
    # Numeric buff patterns (handles +N/+N, +N/+0, 0/+N, and negatives; N can be digits or X)
    buff_regex = r'\bget(?:s)?\s+[+\-]?(?:\d+|X)\s*/\s*[+\-]?(?:\d+|X)\b'

    # Base power/toughness setting patterns (e.g., "has base power and toughness 3/3")
    base_pt_regex = r'\b(?:has|with)\s+base\s+power\s+and\s+toughness\s+[+\-]?(?:\d+|X)\s*/\s*[+\-]?(?:\d+|X)\b'

    other_patterns = [
        buff_regex,
        base_pt_regex,
        'bolster',
        'double strike',
        'first strike',
        'untap all creatures',
        'untap target creature',
    ]

    return tag_utils.create_text_mask(df, other_patterns)

def create_combat_tricks_type_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for instant-speed combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards are instant-speed combat tricks
    """
    return tag_utils.create_type_mask(df, 'Instant')

def create_combat_tricks_flash_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for flash-based combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have flash-based combat tricks
    """
    return tag_utils.create_keyword_mask(df, 'Flash')

def create_combat_tricks_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from combat tricks.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    # Specific cards to exclude
    excluded_cards = [
        'Assimilate Essence',
        'Mantle of Leadership',
        'Michiko\'s Reign of Truth // Portrait of Michiko'
    ]
    name_mask = tag_utils.create_name_mask(df, excluded_cards)

    # Text patterns to exclude
    text_patterns = [
        'remains tapped',
        'only as a sorcery'
    ]
    text_mask = tag_utils.create_text_mask(df, text_patterns)

    return name_mask | text_mask

def tag_for_combat_tricks(df: pd.DataFrame, color: str) -> None:
    """Tag cards that function as combat tricks using vectorized operations.

    This function identifies and tags cards that modify combat through:
    - Power/toughness buffs at instant speed
    - Flash creatures and enchantments with combat effects
    - Tap abilities that modify power/toughness
    - Combat-relevant keywords and abilities

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'type', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_combat_tricks_text_mask(df)
        type_mask = create_combat_tricks_type_mask(df)
        flash_mask = create_combat_tricks_flash_mask(df)
        exclusion_mask = create_combat_tricks_exclusion_mask(df)
        final_mask = ((text_mask & (type_mask | flash_mask)) | 
                     (flash_mask & tag_utils.create_type_mask(df, 'Enchantment'))) & ~exclusion_mask

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Combat Tricks', 'Interaction'],
            'combat trick effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_combat_tricks: {str(e)}')
        raise
    
## Protection/Safety spells
def create_protection_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with protection-related text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have protection text patterns
    """
    text_patterns = [
        'has indestructible',
        'has protection',
        'has shroud',
        'has ward',
        'have indestructible', 
        'have protection',
        'have shroud',
        'have ward',
        'hexproof from',
        'gain hexproof',
        'gain indestructible',
        'gain protection',
        'gain shroud', 
        'gain ward',
        'gains hexproof',
        'gains indestructible',
        'gains protection',
        'gains shroud',
        'gains ward',
        'phases out',
        'protection from'
    ]
    return tag_utils.create_text_mask(df, text_patterns)

def create_protection_keyword_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with protection-related keywords.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have protection keywords
    """
    keyword_patterns = [
        'Hexproof',
        'Indestructible',
        'Protection',
        'Shroud',
        'Ward'
    ]
    return tag_utils.create_keyword_mask(df, keyword_patterns)

def create_protection_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from protection effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    excluded_cards = [
        'Out of Time',
        'The War Doctor'
    ]
    return tag_utils.create_name_mask(df, excluded_cards)

def _identify_protection_granting_cards(df: pd.DataFrame) -> pd.Series:
    """Identify cards that grant protection to other permanents.
    
    Args:
        df: DataFrame containing card data
        
    Returns:
        Boolean Series indicating which cards grant protection
    """
    from code.tagging.protection_grant_detection import is_granting_protection
    
    grant_mask = df.apply(
        lambda row: is_granting_protection(
            str(row.get('text', '')), 
            str(row.get('keywords', ''))
        ),
        axis=1
    )
    return grant_mask


def _apply_kindred_protection_tags(df: pd.DataFrame, grant_mask: pd.Series) -> int:
    """Apply creature-type-specific protection tags.
    
    Args:
        df: DataFrame containing card data
        grant_mask: Boolean Series indicating which cards grant protection
        
    Returns:
        Number of cards tagged with kindred protection
    """
    from code.tagging.protection_grant_detection import get_kindred_protection_tags
    
    kindred_count = 0
    for idx, row in df[grant_mask].iterrows():
        text = str(row.get('text', ''))
        kindred_tags = get_kindred_protection_tags(text)
        
        if kindred_tags:
            current_tags = row.get('themeTags', [])
            if not isinstance(current_tags, list):
                current_tags = []
            
            updated_tags = list(set(current_tags) | set(kindred_tags))
            df.at[idx, 'themeTags'] = updated_tags
            kindred_count += 1
    
    return kindred_count


def _apply_protection_scope_tags(df: pd.DataFrame) -> int:
    """Apply scope metadata tags (Self, Your Permanents, Blanket, Opponent).
    
    Applies to ALL cards with protection effects, not just those that grant protection.
    
    Args:
        df: DataFrame containing card data
        
    Returns:
        Number of cards tagged with scope metadata
    """
    from code.tagging.protection_scope_detection import get_protection_scope_tags, has_any_protection
    
    scope_count = 0
    for idx, row in df.iterrows():
        text = str(row.get('text', ''))
        name = str(row.get('name', ''))
        keywords = str(row.get('keywords', ''))
        
        # Check if card has ANY protection effects
        if not has_any_protection(text) and not any(k in keywords.lower() for k in ['hexproof', 'shroud', 'indestructible', 'ward', 'protection', 'phasing']):
            continue
        
        scope_tags = get_protection_scope_tags(text, name, keywords)
        
        if scope_tags:
            current_tags = row.get('themeTags', [])
            if not isinstance(current_tags, list):
                current_tags = []
            
            updated_tags = list(set(current_tags) | set(scope_tags))
            df.at[idx, 'themeTags'] = updated_tags
            scope_count += 1
    
    return scope_count


def _get_all_protection_mask(df: pd.DataFrame) -> pd.Series:
    """Build mask for ALL cards with protection keywords (granting or inherent).
    
    Args:
        df: DataFrame containing card data
        
    Returns:
        Boolean Series indicating which cards have protection keywords
    """
    text_series = tag_utils._ensure_norm_series(df, 'text', '__text_s')
    keywords_series = tag_utils._ensure_norm_series(df, 'keywords', '__keywords_s')
    
    all_protection_mask = (
        text_series.str.contains('hexproof|shroud|indestructible|ward|protection from|protection|phasing', case=False, regex=True, na=False) |
        keywords_series.str.contains('hexproof|shroud|indestructible|ward|protection|phasing', case=False, regex=True, na=False)
    )
    return all_protection_mask


def _apply_specific_protection_ability_tags(df: pd.DataFrame, all_protection_mask: pd.Series) -> int:
    """Apply specific protection ability tags (Hexproof, Indestructible, etc.).
    
    Args:
        df: DataFrame containing card data
        all_protection_mask: Boolean Series indicating cards with protection
        
    Returns:
        Number of cards tagged with specific abilities
    """
    ability_tag_count = 0
    for idx, row in df[all_protection_mask].iterrows():
        text = str(row.get('text', ''))
        keywords = str(row.get('keywords', ''))
        
        ability_tags = set()
        text_lower = text.lower()
        keywords_lower = keywords.lower()
        
        # Check for each protection ability
        if 'hexproof' in text_lower or 'hexproof' in keywords_lower:
            ability_tags.add('Hexproof')
        if 'indestructible' in text_lower or 'indestructible' in keywords_lower:
            ability_tags.add('Indestructible')
        if 'shroud' in text_lower or 'shroud' in keywords_lower:
            ability_tags.add('Shroud')
        if 'ward' in text_lower or 'ward' in keywords_lower:
            ability_tags.add('Ward')
        
        # Distinguish types of protection
        if 'protection from' in text_lower or 'protection from' in keywords_lower:
            # Check for color protection
            if any(color in text_lower or color in keywords_lower for color in ['white', 'blue', 'black', 'red', 'green', 'multicolored', 'monocolored', 'colorless', 'each color', 'all colors', 'the chosen color', 'a color']):
                ability_tags.add('Protection from Color')
            # Check for creature type protection
            elif 'protection from creatures' in text_lower or 'protection from creatures' in keywords_lower:
                ability_tags.add('Protection from Creatures')
            elif any(ctype.lower() in text_lower for ctype in ['Dragons', 'Zombies', 'Vampires', 'Demons', 'Humans', 'Elves', 'Goblins', 'Werewolves']):
                ability_tags.add('Protection from Creature Type')
            else:
                ability_tags.add('Protection from Quality')
        
        if ability_tags:
            current_tags = row.get('themeTags', [])
            if not isinstance(current_tags, list):
                current_tags = []
            
            updated_tags = list(set(current_tags) | ability_tags)
            df.at[idx, 'themeTags'] = updated_tags
            ability_tag_count += 1
    
    return ability_tag_count


def tag_for_protection(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide or have protection effects using vectorized operations.

    This function identifies and tags cards with protection effects including:
    - Indestructible
    - Protection from [quality]
    - Hexproof/Shroud
    - Ward
    - Phase out

    With TAG_PROTECTION_GRANTS=1, only tags cards that grant protection to other
    permanents, filtering out cards with inherent protection.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)

        # Check if grant detection is enabled (M2 feature flag)
        use_grant_detection = os.getenv('TAG_PROTECTION_GRANTS', '1').lower() in ('1', 'true', 'yes')

        if use_grant_detection:
            # M2: Use grant detection to filter out inherent-only protection
            final_mask = _identify_protection_granting_cards(df)
            logger.info('Using M2 grant detection (TAG_PROTECTION_GRANTS=1)')
            
            # Apply kindred metadata tags for creature-type-specific grants
            kindred_count = _apply_kindred_protection_tags(df, final_mask)
            if kindred_count > 0:
                logger.info(f'Applied kindred protection tags to {kindred_count} cards (will be moved to metadata by partition)')
            
            # M5: Add protection scope metadata tags
            scope_count = _apply_protection_scope_tags(df)
            if scope_count > 0:
                logger.info(f'Applied protection scope tags to {scope_count} cards (will be moved to metadata by partition)')
        else:
            # Legacy: Use original text/keyword patterns
            text_mask = create_protection_text_mask(df)
            keyword_mask = create_protection_keyword_mask(df)
            exclusion_mask = create_protection_exclusion_mask(df)
            final_mask = (text_mask | keyword_mask) & ~exclusion_mask

        # Build comprehensive mask for ALL cards with protection keywords
        all_protection_mask = _get_all_protection_mask(df)
        
        # Apply generic 'Protective Effects' tag to ALL cards with protection
        tag_utils.apply_rules(df, rules=[
            {'mask': all_protection_mask, 'tags': ['Protective Effects']}
        ])
        
        # Apply 'Interaction' tag ONLY to cards that GRANT protection
        tag_utils.apply_rules(df, rules=[
            {'mask': final_mask, 'tags': ['Interaction']}
        ])
        
        # Apply specific protection ability tags
        ability_tag_count = _apply_specific_protection_ability_tags(df, all_protection_mask)
        if ability_tag_count > 0:
            logger.info(f'Applied specific protection ability tags to {ability_tag_count} cards')

        # Log results
        logger.info(f'Tagged {final_mask.sum()} cards with protection effects for {color}')

    except Exception as e:
        logger.error(f'Error in tag_for_protection: {str(e)}')
        raise

## Phasing effects
def tag_for_phasing(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide phasing effects using vectorized operations.

    This function identifies and tags cards with phasing effects including:
    - Cards that phase permanents out
    - Cards with phasing keyword
    
    Similar to M5 protection tagging, adds scope metadata tags:
    - Self: Phasing (card phases itself out)
    - Your Permanents: Phasing (phases your permanents out)
    - Blanket: Phasing (phases all permanents out)

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        from code.tagging.phasing_scope_detection import has_phasing, get_phasing_scope_tags, is_removal_phasing
        
        phasing_mask = df.apply(
            lambda row: has_phasing(str(row.get('text', ''))) or 
                       'phasing' in str(row.get('keywords', '')).lower(),
            axis=1
        )
        
        # Apply generic "Phasing" theme tag first
        tag_utils.apply_rules(df, rules=[
            {
                'mask': phasing_mask,
                'tags': ['Phasing', 'Interaction']
            }
        ])
        
        # Add phasing scope metadata tags and removal tags
        scope_count = 0
        removal_count = 0
        for idx, row in df[phasing_mask].iterrows():
            text = str(row.get('text', ''))
            name = str(row.get('name', ''))
            keywords = str(row.get('keywords', ''))
            
            # Check if card has phasing (in text or keywords)
            if not has_phasing(text) and 'phasing' not in keywords.lower():
                continue
            
            scope_tags = get_phasing_scope_tags(text, name, keywords)
            
            if scope_tags:
                current_tags = row.get('themeTags', [])
                if not isinstance(current_tags, list):
                    current_tags = []
                
                # Add scope tags to themeTags (partition will move to metadataTags)
                updated_tags = list(set(current_tags) | scope_tags)
                
                # If this is removal-style phasing, add Removal tag
                if is_removal_phasing(scope_tags):
                    updated_tags.append('Removal')
                    removal_count += 1
                
                df.at[idx, 'themeTags'] = updated_tags
                scope_count += 1
        
        if scope_count > 0:
            logger.info(f'Applied phasing scope tags to {scope_count} cards (will be moved to metadata by partition)')
        if removal_count > 0:
            logger.info(f'Applied Removal tag to {removal_count} cards with opponent-targeting phasing')

        # Log results
        logger.info(f'Tagged {phasing_mask.sum()} cards with phasing effects for {color}')

    except Exception as e:
        logger.error(f'Error in tag_for_phasing: {str(e)}')
        raise

## Spot removal
def create_removal_text_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards with removal text patterns.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have removal text patterns
    """
    return tag_utils.create_text_mask(df, tag_constants.REMOVAL_TEXT_PATTERNS)

def create_removal_exclusion_mask(df: pd.DataFrame) -> pd.Series:
    """Create a boolean mask for cards that should be excluded from removal effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards should be excluded
    """
    return tag_utils.create_text_mask(df, tag_constants.REMOVAL_EXCLUSION_PATTERNS)


def tag_for_removal(df: pd.DataFrame, color: str) -> None:
    """Tag cards that provide spot removal using vectorized operations.

    This function identifies and tags cards that remove permanents through:
    - Destroy effects
    - Exile effects
    - Bounce effects
    - Sacrifice effects
    
    The function uses helper functions to identify different types of removal
    and applies tags consistently using vectorized operations.

    Args:
        df: DataFrame containing card data
        color: Color identifier for logging purposes

    Raises:
        ValueError: If required DataFrame columns are missing
        TypeError: If inputs are not of correct type
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        if not isinstance(color, str):
            raise TypeError("color must be a string")
        required_cols = {'text', 'themeTags', 'keywords'}
        tag_utils.validate_dataframe_columns(df, required_cols)
        text_mask = create_removal_text_mask(df)
        exclude_mask = create_removal_exclusion_mask(df)

        # Combine masks (and exclude self-targeting effects like 'target permanent you control')
        final_mask = text_mask & (~exclude_mask)

        # Apply tags via utility
        tag_utils.tag_with_logging(
            df, final_mask, ['Removal', 'Interaction'],
            'removal effects', color=color, logger=logger
        )

    except Exception as e:
        logger.error(f'Error in tag_for_removal: {str(e)}')
        raise

def run_tagging(parallel: bool = False, max_workers: int | None = None):
    """Run tagging across all COLORS.

    Args:
        parallel: If True, process colors in parallel using multiple processes.
        max_workers: Optional cap on worker processes.
    """
    start_time = pd.Timestamp.now()

    if parallel and DFC_PER_FACE_SNAPSHOT:
        logger.warning("DFC_PER_FACE_SNAPSHOT=1 detected; per-face metadata snapshots require sequential tagging. Parallel run will skip snapshot emission.")

    if parallel:
        try:
            import concurrent.futures as _f
            # Use processes to bypass GIL; each color reads/writes distinct CSV
            with _f.ProcessPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(load_dataframe, color): color for color in COLORS}
                for fut in _f.as_completed(futures):
                    color = futures[fut]
                    try:
                        fut.result()
                    except Exception as e:
                        logger.error(f'Parallel worker failed for {color}: {e}')
                        raise
        except Exception:
            # Fallback to sequential on any multiprocessing setup error
            logger.warning('Parallel mode failed to initialize; falling back to sequential.')
            for color in COLORS:
                load_dataframe(color)
    else:
        for color in COLORS:
            load_dataframe(color)

    _flush_per_face_snapshot()
    duration = (pd.Timestamp.now() - start_time).total_seconds()
    logger.info(f'Tagged cards in {duration:.2f}s')
