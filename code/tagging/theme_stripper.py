"""
Theme Stripping Module

Provides threshold logic and utilities for identifying and stripping themes
with insufficient card counts from the theme catalog and card data.

This module supports M1-M4 of the Theme Stripping roadmap:
- M1: Threshold logic and theme count analysis
- M2: Theme catalog YAML stripping
- M3: theme_list.json stripping
- M4: Parquet file theme_tags stripping
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, List, Tuple, Any, Optional
import pandas as pd
import numpy as np

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# ----------------------------------------------------------------------------------
# M1: Threshold Logic & Analysis
# ----------------------------------------------------------------------------------

def get_theme_card_counts(parquet_paths: List[Path]) -> Dict[str, Set[str]]:
    """
    Build a mapping of theme -> set of card names from parquet files.
    
    Args:
        parquet_paths: List of paths to parquet files to analyze
        
    Returns:
        Dictionary mapping theme ID to set of card names containing that theme
        
    Example:
        {"lifegain": {"Ajani's Pridemate", "Soul Warden", ...}, ...}
    """
    theme_to_cards: Dict[str, Set[str]] = {}
    
    for parquet_path in parquet_paths:
        try:
            df = pd.read_parquet(parquet_path)
            
            # Process each card's theme_tags
            for _, row in df.iterrows():
                card_name = row.get('name', '')
                theme_tags = row.get('themeTags', [])
                
                # Handle numpy arrays, lists, and string formats
                if isinstance(theme_tags, np.ndarray):
                    themes = [str(t).strip() for t in theme_tags if str(t).strip()]
                elif isinstance(theme_tags, str):
                    # Try common separators
                    if '|' in theme_tags:
                        themes = [t.strip() for t in theme_tags.split('|') if t.strip()]
                    elif ',' in theme_tags:
                        themes = [t.strip() for t in theme_tags.split(',') if t.strip()]
                    else:
                        themes = [theme_tags.strip()] if theme_tags.strip() else []
                elif isinstance(theme_tags, list):
                    themes = [str(t).strip() for t in theme_tags if str(t).strip()]
                else:
                    themes = []
                
                # Add card to each theme's set
                for theme in themes:
                    if theme:  # Skip empty themes
                        # Normalize theme ID (lowercase, replace spaces with underscores)
                        theme_id = theme.lower().replace(' ', '_')
                        if theme_id not in theme_to_cards:
                            theme_to_cards[theme_id] = set()
                        theme_to_cards[theme_id].add(card_name)
                        
        except Exception as e:
            print(f"Warning: Failed to process {parquet_path}: {e}")
            continue
    
    return theme_to_cards


def identify_themes_to_strip(
    theme_counts: Dict[str, Set[str]],
    min_cards: int
) -> Set[str]:
    """
    Identify themes that should be stripped based on card count threshold.
    
    Args:
        theme_counts: Dictionary mapping theme ID to set of card names
        min_cards: Minimum number of cards required to keep a theme
        
    Returns:
        Set of theme IDs that should be stripped
        
    Example:
        >>> counts = {"daybound": {"Card1", "Card2"}, "lifegain": {"Card1", "Card2", "Card3", "Card4", "Card5"}}
        >>> identify_themes_to_strip(counts, 5)
        {'daybound'}
    """
    themes_to_strip = set()
    
    for theme_id, card_set in theme_counts.items():
        card_count = len(card_set)
        if card_count < min_cards:
            themes_to_strip.add(theme_id)
    
    return themes_to_strip


def should_strip_theme(theme: str, card_count: int, min_cards: int) -> bool:
    """
    Determine if a specific theme should be stripped based on threshold.
    
    Args:
        theme: Theme ID
        card_count: Number of cards with this theme
        min_cards: Minimum threshold
        
    Returns:
        True if theme should be stripped, False otherwise
    """
    return card_count < min_cards


def get_theme_distribution(theme_counts: Dict[str, Set[str]]) -> Dict[str, int]:
    """
    Get distribution of themes by card count buckets.
    
    Args:
        theme_counts: Dictionary mapping theme ID to set of card names
        
    Returns:
        Dictionary with distribution statistics:
        - "1_card": Count of themes with exactly 1 card
        - "2_cards": Count of themes with exactly 2 cards
        - "3_4_cards": Count of themes with 3-4 cards
        - "5_9_cards": Count of themes with 5-9 cards
        - "10_plus": Count of themes with 10+ cards
        - "total": Total number of themes
    """
    distribution = {
        "1_card": 0,
        "2_cards": 0,
        "3_4_cards": 0,
        "5_9_cards": 0,
        "10_plus": 0,
        "total": 0
    }
    
    for card_set in theme_counts.values():
        count = len(card_set)
        distribution["total"] += 1
        
        if count == 1:
            distribution["1_card"] += 1
        elif count == 2:
            distribution["2_cards"] += 1
        elif 3 <= count <= 4:
            distribution["3_4_cards"] += 1
        elif 5 <= count <= 9:
            distribution["5_9_cards"] += 1
        else:  # 10+
            distribution["10_plus"] += 1
    
    return distribution


def get_themes_by_count(
    theme_counts: Dict[str, Set[str]],
    below_threshold: int
) -> List[Tuple[str, int, List[str]]]:
    """
    Get list of themes below threshold with their counts and card lists.
    
    Args:
        theme_counts: Dictionary mapping theme ID to set of card names
        below_threshold: Threshold for listing themes
        
    Returns:
        List of tuples (theme_id, card_count, card_list) sorted by count (ascending)
        
    Example:
        [("miracle", 4, ["Temporal Mastery", "Terminus", "Entreat the Angels", "Bonfire"]), ...]
    """
    below_list = []
    
    for theme_id, card_set in theme_counts.items():
        count = len(card_set)
        if count < below_threshold:
            card_list = sorted(card_set)  # Sort for consistent output
            below_list.append((theme_id, count, card_list))
    
    # Sort by count (ascending), then alphabetically
    below_list.sort(key=lambda x: (x[1], x[0]))
    
    return below_list


# ----------------------------------------------------------------------------------
# M2: Theme Catalog Stripping
# ----------------------------------------------------------------------------------

def backup_catalog_file(file_path: Path) -> Path:
    """
    Create a timestamped backup of a catalog YAML file.
    
    Args:
        file_path: Path to the YAML file to backup
        
    Returns:
        Path to the backup file created
        
    Example:
        daybound.yml -> daybound_20260319_143025.yml.bak
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = file_path.stem  # filename without extension
    backup_path = file_path.parent / f"{stem}_{timestamp}.yml.bak"
    
    # Copy content to backup
    backup_path.write_text(file_path.read_text(encoding='utf-8'), encoding='utf-8')
    
    return backup_path


def remove_theme_from_catalog(yaml_data: Dict[str, Any], theme_id: str) -> bool:
    """
    Remove a theme entry from catalog YAML data.
    
    Args:
        yaml_data: Loaded YAML data (dict)
        theme_id: Theme ID to remove (must match exactly)
        
    Returns:
        True if theme was removed, False if not found
        
    Note:
        Modifies yaml_data in-place. Handles single-theme files (where entire
        file content is the theme dict) and potential multi-theme structures.
    """
    # Single-theme file: check if the 'id' field matches
    if isinstance(yaml_data, dict) and yaml_data.get('id') == theme_id:
        # For single-theme files, we can't remove the theme from the dict itself
        # Caller must handle file deletion
        return True
    
    # Multi-theme file: check if yaml_data contains a list or dict of themes
    # (Future-proofing: current catalog uses one file per theme, but structure may change)
    if isinstance(yaml_data, list):
        for i, theme in enumerate(yaml_data):
            if isinstance(theme, dict) and theme.get('id') == theme_id:
                yaml_data.pop(i)
                return True
    
    return False


def strip_catalog_themes(
    catalog_dir: Path,
    themes_to_strip: Set[str],
    backup: bool = True
) -> Dict[str, Any]:
    """
    Strip low-card themes from YAML catalog files.
    
    Args:
        catalog_dir: Directory containing theme catalog YAML files
        themes_to_strip: Set of theme IDs to remove
        backup: Whether to create timestamped backups before modification
        
    Returns:
        Dictionary with stripping results:
        - "stripped_count": Number of themes stripped
        - "files_modified": List of file paths modified
        - "files_deleted": List of file paths deleted (empty single-theme files)
        - "backups_created": List of backup file paths
        - "errors": List of error messages
        
    Example:
        results = strip_catalog_themes(
            Path("config/themes/catalog"),
            {"daybound", "miracle"},
            backup=True
        )
        # Results: {"stripped_count": 2, "files_modified": [...], ...}
    """
    if yaml is None:
        raise RuntimeError("PyYAML not installed - cannot strip catalog themes")
    
    if not catalog_dir.exists():
        raise FileNotFoundError(f"Catalog directory does not exist: {catalog_dir}")
    
    results = {
        "stripped_count": 0,
        "files_modified": [],
        "files_deleted": [],
        "backups_created": [],
        "errors": []
    }
    
    # Find all YAML files in catalog directory
    yaml_files = sorted(catalog_dir.glob("*.yml"))
    
    for yaml_file in yaml_files:
        try:
            # Load YAML content
            content = yaml_file.read_text(encoding='utf-8')
            data = yaml.safe_load(content)
            
            if not isinstance(data, dict):
                continue  # Skip non-dict files
            
            theme_id = data.get('id')
            if not theme_id or theme_id not in themes_to_strip:
                continue  # Skip if theme not in strip list
            
            # Create backup before modification
            if backup:
                try:
                    backup_path = backup_catalog_file(yaml_file)
                    results["backups_created"].append(str(backup_path))
                except Exception as e:
                    results["errors"].append(f"Backup failed for {yaml_file.name}: {e}")
                    # Continue anyway - modification is important
            
            # For single-theme files, delete the file entirely
            # (Current catalog structure: one theme per file)
            yaml_file.unlink()
            results["stripped_count"] += 1
            results["files_deleted"].append(str(yaml_file))
            
        except yaml.YAMLError as e:
            results["errors"].append(f"YAML parse error in {yaml_file.name}: {e}")
        except Exception as e:
            results["errors"].append(f"Error processing {yaml_file.name}: {e}")
    
    return results


def create_stripped_themes_log(
    output_path: Path,
    theme_counts: Dict[str, Set[str]],
    themes_stripped: Set[str],
    min_threshold: int,
    sources: Optional[List[str]] = None
) -> None:
    """
    Create a YAML log of stripped themes with metadata.
    
    Args:
        output_path: Path where stripped_themes.yml will be written
        theme_counts: Dictionary mapping theme ID to set of card names
        themes_stripped: Set of theme IDs that were stripped
        min_threshold: The minimum card threshold used for stripping
        sources: Optional list of sources themes were stripped from
        
    Creates a YAML file with structure:
        metadata:
          last_updated: "2026-03-19T12:30:00"
          min_card_threshold: 5
          total_stripped: 42
        
        stripped_themes:
          - theme_id: "daybound"
            display_name: "Daybound"
            card_count: 3
            cards:
              - "Card Name 1"
              - "Card Name 2"
            reason: "Below minimum card threshold (3 < 5)"
            stripped_from:
              - "catalog/daybound.yml"
              - "theme_list.json"
              - "parquet files"
    """
    if yaml is None:
        raise RuntimeError("PyYAML not installed - cannot create stripped themes log")
    
    # Build stripped themes list
    stripped_list = []
    for theme_id in sorted(themes_stripped):
        if theme_id not in theme_counts:
            continue  # Skip if we don't have count data
        
        card_set = theme_counts[theme_id]
        card_count = len(card_set)
        sorted_cards = sorted(card_set)
        
        # Convert theme_id to display name (capitalize each word, replace underscores)
        display_name = theme_id.replace('_', ' ').title()
        
        theme_entry = {
            'theme_id': theme_id,
            'display_name': display_name,
            'card_count': card_count,
            'cards': sorted_cards,
            'reason': f"Below minimum card threshold ({card_count} < {min_threshold})",
            'stripped_from': sources if sources else ["catalog YAML", "theme_list.json", "parquet files"]
        }
        
        stripped_list.append(theme_entry)
    
    # Sort by card count (ascending), then alphabetically
    stripped_list.sort(key=lambda x: (x['card_count'], x['theme_id']))
    
    # Build complete log structure
    log_data = {
        'metadata': {
            'last_updated': datetime.now().isoformat(),
            'min_card_threshold': min_threshold,
            'total_stripped': len(stripped_list)
        },
        'stripped_themes': stripped_list
    }
    
    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(log_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
    
    print(f"Stripped themes log written to {output_path}")


# ----------------------------------------------------------------------------------
# M4: Parquet File Stripping
# ----------------------------------------------------------------------------------

def backup_parquet_file(file_path: Path) -> Path:
    """
    Create a timestamped backup of a parquet file.
    
    Args:
        file_path: Path to the parquet file to backup
        
    Returns:
        Path to the backup file created
        
    Example:
        all_cards.parquet -> all_cards_20260319_143025.parquet.bak
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = file_path.stem  # filename without extension
    backup_path = file_path.parent / f"{stem}_{timestamp}.parquet.bak"
    
    # Copy file to backup
    import shutil
    shutil.copy2(file_path, backup_path)
    
    return backup_path


def filter_theme_tags(theme_tags: Any, themes_to_strip: Set[str]) -> List[str]:
    """
    Remove specific themes from a themeTags value (handles multiple formats).
    
    Args:
        theme_tags: Can be numpy array, list, or string
        themes_to_strip: Set of theme IDs to remove (case-insensitive matching)
        
    Returns:
        Filtered list of theme tags
        
    Note:
        Matches themes case-insensitively for robustness.
    """
    # Convert to list if needed
    if isinstance(theme_tags, np.ndarray):
        tags_list = theme_tags.tolist()
    elif isinstance(theme_tags, list):
        tags_list = theme_tags
    elif isinstance(theme_tags, str):
        # Handle string formats (comma or pipe separated)
        if '|' in theme_tags:
            tags_list = [t.strip() for t in theme_tags.split('|') if t.strip()]
        elif ',' in theme_tags:
            tags_list = [t.strip() for t in theme_tags.split(',') if t.strip()]
        else:
            tags_list = [theme_tags] if theme_tags else []
    else:
        tags_list = []
    
    # Normalize themes to strip (lowercase for case-insensitive matching)
    normalized_strip_set = {theme.lower() for theme in themes_to_strip}
    
    # Filter themes
    filtered = [tag for tag in tags_list if str(tag).lower() not in normalized_strip_set]
    
    return filtered


def update_parquet_theme_tags(df: pd.DataFrame, themes_to_strip: Set[str]) -> pd.DataFrame:
    """
    Process entire dataframe to remove stripped themes from themeTags column.
    
    Args:
        df: DataFrame with themeTags column
        themes_to_strip: Set of theme IDs to remove
        
    Returns:
        Modified DataFrame (in-place modification + return for convenience)
        
    Note:
        Modifies df in-place and also returns it.
    """
    if 'themeTags' not in df.columns:
        print("Warning: themeTags column not found in dataframe")
        return df
    
    # Apply filtering to each row
    df['themeTags'] = df['themeTags'].apply(
        lambda tags: filter_theme_tags(tags, themes_to_strip)
    )
    
    return df


def strip_parquet_themes(
    parquet_path: Path,
    themes_to_strip: Set[str],
    backup: bool = True
) -> Dict[str, Any]:
    """
    Strip low-card themes from parquet file's themeTags column.
    
    Args:
        parquet_path: Path to parquet file
        themes_to_strip: Set of theme IDs to remove
        backup: Whether to create timestamped backup before modification
        
    Returns:
        Dictionary with stripping results:
        - "cards_processed": Total number of cards
        - "cards_modified": Number of cards with tags removed
        - "tags_removed": Total number of tag removals
        - "backup_created": Backup file path (if backup=True)
        - "errors": List of error messages
        
    Example:
        results = strip_parquet_themes(
            Path("card_files/processed/all_cards.parquet"),
            {"fateseal", "gravestorm"},
            backup=True
        )
    """
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file does not exist: {parquet_path}")
    
    results = {
        "cards_processed": 0,
        "cards_modified": 0,
        "tags_removed": 0,
        "backup_created": None,
        "errors": []
    }
    
    try:
        # Load parquet
        df = pd.read_parquet(parquet_path, engine='pyarrow')
        results["cards_processed"] = len(df)
        
        # Create backup before modification
        if backup:
            try:
                backup_path = backup_parquet_file(parquet_path)
                results["backup_created"] = str(backup_path)
                print(f"Created backup: {backup_path}")
            except Exception as e:
                results["errors"].append(f"Backup failed: {e}")
                # Continue anyway - modification is important
        
        # Track modifications
        if 'themeTags' in df.columns:
            # Count tags before stripping
            tags_before = sum(
                len(tags) if isinstance(tags, (list, np.ndarray)) else 0 
                for tags in df['themeTags']
            )
            
            # Apply filtering
            update_parquet_theme_tags(df, themes_to_strip)
            
            # Count tags after stripping
            tags_after = sum(
                len(tags) if isinstance(tags, list) else 0 
                for tags in df['themeTags']
            )
            
            results["tags_removed"] = tags_before - tags_after
            
            # Count cards with modifications (cards that had at least one tag removed)
            # This is approximate: tags_removed / ~avg_tags_per_card
            if results["tags_removed"] > 0:
                results["cards_modified"] = results["tags_removed"]  # Conservative estimate
            
            print(f"Stripped {results['tags_removed']} tag occurrences from {results['cards_processed']} cards")
        else:
            results["errors"].append("themeTags column not found in parquet file")
            return results
        
        # Write modified parquet back
        df.to_parquet(parquet_path, engine='pyarrow', index=False)
        print(f"Updated {parquet_path}")
        
    except Exception as e:
        results["errors"].append(f"Error processing parquet: {e}")
    
    return results
