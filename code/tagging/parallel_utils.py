"""Utilities for parallel card tagging operations.

This module provides functions to split DataFrames by color identity for
parallel processing and merge them back together. This enables the tagging
system to use ProcessPoolExecutor for significant performance improvements
while maintaining the unified Parquet approach.
"""

from __future__ import annotations

from typing import Dict
import pandas as pd
import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)


def split_by_color_identity(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Split DataFrame into color identity groups for parallel processing.
    
    Each color identity group is a separate DataFrame that can be tagged
    independently. This function preserves all columns and ensures no cards
    are lost during the split.
    
    Color identity groups are based on the 'colorIdentity' column which contains
    strings like 'W', 'WU', 'WUB', 'WUBRG', etc.
    
    Args:
        df: DataFrame containing all cards with 'colorIdentity' column
        
    Returns:
        Dictionary mapping color identity strings to DataFrames
        Example: {'W': df_white, 'WU': df_azorius, '': df_colorless, ...}
        
    Raises:
        ValueError: If 'colorIdentity' column is missing
    """
    if 'colorIdentity' not in df.columns:
        raise ValueError("DataFrame must have 'colorIdentity' column for parallel splitting")
    
    # Group by color identity
    groups: Dict[str, pd.DataFrame] = {}
    
    for color_id, group_df in df.groupby('colorIdentity', dropna=False):
        # Handle NaN/None as colorless
        if pd.isna(color_id):
            color_id = ''
        
        # Convert to string (in case it's already a string, this is safe)
        color_id_str = str(color_id)
        
        # Create a copy to avoid SettingWithCopyWarning in parallel workers
        groups[color_id_str] = group_df.copy()
        
        logger.debug(f"Split group '{color_id_str}': {len(group_df)} cards")
    
    # Verify split is complete
    total_split = sum(len(group_df) for group_df in groups.values())
    if total_split != len(df):
        logger.warning(
            f"Split verification failed: {total_split} cards in groups vs {len(df)} original. "
            f"Some cards may be missing!"
        )
    else:
        logger.info(f"Split {len(df)} cards into {len(groups)} color identity groups")
    
    return groups


def merge_color_groups(groups: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge tagged color identity groups back into a single DataFrame.
    
    This function concatenates all color group DataFrames and ensures:
    - All columns are preserved
    - No duplicate cards (by index)
    - Proper index handling
    - Consistent column ordering
    
    Args:
        groups: Dictionary mapping color identity strings to tagged DataFrames
        
    Returns:
        Single DataFrame containing all tagged cards
        
    Raises:
        ValueError: If groups is empty or contains invalid DataFrames
    """
    if not groups:
        raise ValueError("Cannot merge empty color groups")
    
    # Verify all values are DataFrames
    for color_id, group_df in groups.items():
        if not isinstance(group_df, pd.DataFrame):
            raise ValueError(f"Group '{color_id}' is not a DataFrame: {type(group_df)}")
    
    # Concatenate all groups
    # ignore_index=False preserves original indices
    # sort=False maintains column order from first DataFrame
    merged_df = pd.concat(groups.values(), ignore_index=False, sort=False)
    
    # Check for duplicate indices (shouldn't happen if split was lossless)
    if merged_df.index.duplicated().any():
        logger.warning(
            f"Found {merged_df.index.duplicated().sum()} duplicate indices after merge. "
            f"This may indicate a bug in the split/merge process."
        )
        # Remove duplicates (keep first occurrence)
        merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
    
    # Verify merge is complete
    total_merged = len(merged_df)
    total_groups = sum(len(group_df) for group_df in groups.values())
    
    if total_merged != total_groups:
        logger.warning(
            f"Merge verification failed: {total_merged} cards in result vs {total_groups} in groups. "
            f"Lost {total_groups - total_merged} cards!"
        )
    else:
        logger.info(f"Merged {len(groups)} color groups into {total_merged} cards")
    
    # Reset index to ensure clean sequential indexing
    merged_df = merged_df.reset_index(drop=True)
    
    return merged_df


__all__ = [
    'split_by_color_identity',
    'merge_color_groups',
]
