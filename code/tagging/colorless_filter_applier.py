"""Apply 'Useless in Colorless' metadata tags to cards that don't work in colorless identity decks.

This module identifies and tags cards using regex patterns to match oracle text:
1. Cards referencing "your commander's color identity"
2. Cards that reduce costs of colored spells
3. Cards that trigger on casting colored spells

Examples include:
- Arcane Signet, Command Tower (commander color identity)
- Pearl/Sapphire/Jet/Ruby/Emerald Medallion (colored cost reduction)
- Oketra's/Kefnet's/Bontu's/Hazoret's/Rhonas's Monument (colored creature cost reduction)
- Shrine of Loyal Legions, etc. (colored spell triggers)
"""
from __future__ import annotations
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Regex patterns for cards that don't work in colorless identity decks
COLORLESS_FILTER_PATTERNS = [
    # Cards referencing "your commander's color identity"
    # BUT exclude Commander's Plate (protection from colors NOT in identity = amazing in colorless!)
    # and Study Hall (still draws/scrys in colorless)
    r"commander'?s?\s+color\s+identity",
    
    # Colored cost reduction - medallions and monuments
    # Matches: "white spells you cast cost", "blue creature spells you cast cost", etc.
    # Use non-capturing groups to avoid pandas UserWarning
    r"(?:white|blue|black|red|green)\s+(?:creature\s+)?spells?\s+you\s+cast\s+cost.*less",
    
    # Colored spell triggers - shrines and similar
    # Matches: "whenever you cast a white spell", etc.
    # Use non-capturing groups to avoid pandas UserWarning
    r"whenever\s+you\s+cast\s+a\s+(?:white|blue|black|red|green)\s+spell",
]

# Cards that should NOT be filtered despite matching patterns
# These cards actually work great in colorless decks
COLORLESS_FILTER_EXCEPTIONS = [
    "Commander's Plate",  # Protection from colors NOT in identity = protection from all colors in colorless!
    "Study Hall",         # Still provides colorless mana and scrys when casting commander
]

USELESS_IN_COLORLESS_TAG = "Useless in Colorless"


def apply_colorless_filter_tags(df: pd.DataFrame) -> None:
    """Apply 'Useless in Colorless' metadata tag to cards that don't work in colorless decks.
    
    Uses regex patterns to identify cards in oracle text that:
    - Reference "your commander's color identity"
    - Reduce costs of colored spells
    - Trigger on casting colored spells
    
    Modifies the DataFrame in-place by adding tags to the 'themeTags' column.
    These tags will later be moved to 'metadataTags' during the partition phase.
    
    Args:
        df: DataFrame with 'name', 'text', and 'themeTags' columns
        
    Returns:
        None (modifies DataFrame in-place)
    """
    if 'name' not in df.columns:
        logger.warning("No 'name' column found, skipping colorless filter tagging")
        return
        
    if 'text' not in df.columns:
        logger.warning("No 'text' column found, skipping colorless filter tagging")
        return
        
    if 'themeTags' not in df.columns:
        logger.warning("No 'themeTags' column found, skipping colorless filter tagging")
        return
    
    # Combine all patterns with OR (use non-capturing groups to avoid pandas warning)
    combined_pattern = "|".join(f"(?:{pattern})" for pattern in COLORLESS_FILTER_PATTERNS)
    
    # Find cards matching any pattern
    df['text'] = df['text'].fillna('')
    matches_pattern = df['text'].str.contains(
        combined_pattern,
        case=False,
        regex=True,
        na=False
    )
    
    # Exclude cards that work well in colorless despite matching patterns
    is_exception = df['name'].isin(COLORLESS_FILTER_EXCEPTIONS)
    matches_pattern = matches_pattern & ~is_exception
    
    tagged_count = 0
    
    for idx in df[matches_pattern].index:
        card_name = df.at[idx, 'name']
        tags = df.at[idx, 'themeTags']
        
        # Ensure themeTags is a list
        if not isinstance(tags, list):
            tags = []
        
        # Add tag if not already present
        if USELESS_IN_COLORLESS_TAG not in tags:
            tags.append(USELESS_IN_COLORLESS_TAG)
            df.at[idx, 'themeTags'] = tags
            tagged_count += 1
            logger.debug(f"Tagged '{card_name}' with '{USELESS_IN_COLORLESS_TAG}'")
    
    if tagged_count > 0:
        logger.info(f"Applied '{USELESS_IN_COLORLESS_TAG}' tag to {tagged_count} cards")
    else:
        logger.info(f"No '{USELESS_IN_COLORLESS_TAG}' tags applied (no matches or already tagged)")


__all__ = [
    "apply_colorless_filter_tags",
    "COLORLESS_FILTER_PATTERNS",
    "COLORLESS_FILTER_EXCEPTIONS",
    "USELESS_IN_COLORLESS_TAG",
]
