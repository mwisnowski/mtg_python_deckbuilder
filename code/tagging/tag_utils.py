"""Utility module for tag manipulation and pattern matching in card data processing.

This module provides a collection of functions for working with card tags, types, and text patterns
in a card game context. It includes utilities for:

- Creating boolean masks for filtering cards based on various criteria
- Manipulating and extracting card types
- Managing theme tags and card attributes
- Pattern matching in card text and types
- Mass effect detection (damage, removal, etc.)

The module is designed to work with pandas DataFrames containing card data and provides
vectorized operations for efficient processing of large card collections.
"""
from __future__ import annotations

# Standard library imports
import re
from typing import List, Set, Union, Any

# Third-party imports
import pandas as pd

# Local application imports
from . import tag_constants

def pluralize(word: str) -> str:
    """Convert a word to its plural form using basic English pluralization rules.

    Args:
        word: The singular word to pluralize

    Returns:
        The pluralized word
    """
    if word.endswith('y'):
        return word[:-1] + 'ies'
    elif word.endswith(('s', 'sh', 'ch', 'x', 'z')):
        return word + 'es'
    elif word.endswith(('f')):
        return word[:-1] + 'ves'
    else:
        return word + 's'

def sort_list(items: Union[List[Any], pd.Series]) -> Union[List[Any], pd.Series]:
    """Sort a list or pandas Series in ascending order.

    Args:
        items: List or Series to sort

    Returns:
        Sorted list or Series
    """
    if isinstance(items, (list, pd.Series)):
        return sorted(items) if isinstance(items, list) else items.sort_values()
    return items

def create_type_mask(df: pd.DataFrame, type_text: Union[str, List[str]], regex: bool = True) -> pd.Series[bool]:
    """Create a boolean mask for rows where type matches one or more patterns.

    Args:
        df: DataFrame to search
        type_text: Type text pattern(s) to match. Can be a single string or list of strings.
        regex: Whether to treat patterns as regex expressions (default: True)

    Returns:
        Boolean Series indicating matching rows

    Raises:
        ValueError: If type_text is empty or None
        TypeError: If type_text is not a string or list of strings
    """
    if not type_text:
        raise ValueError("type_text cannot be empty or None")

    if isinstance(type_text, str):
        type_text = [type_text]
    elif not isinstance(type_text, list):
        raise TypeError("type_text must be a string or list of strings")

    if regex:
        pattern = '|'.join(f'{p}' for p in type_text)
        return df['type'].str.contains(pattern, case=False, na=False, regex=True)
    else:
        masks = [df['type'].str.contains(p, case=False, na=False, regex=False) for p in type_text]
        return pd.concat(masks, axis=1).any(axis=1)

def create_text_mask(df: pd.DataFrame, type_text: Union[str, List[str]], regex: bool = True, combine_with_or: bool = True) -> pd.Series[bool]:
    """Create a boolean mask for rows where text matches one or more patterns.

    Args:
        df: DataFrame to search
        type_text: Type text pattern(s) to match. Can be a single string or list of strings.
        regex: Whether to treat patterns as regex expressions (default: True)
        combine_with_or: Whether to combine multiple patterns with OR (True) or AND (False)

    Returns:
        Boolean Series indicating matching rows

    Raises:
        ValueError: If type_text is empty or None
        TypeError: If type_text is not a string or list of strings
    """
    if not type_text:
        raise ValueError("type_text cannot be empty or None")

    if isinstance(type_text, str):
        type_text = [type_text]
    elif not isinstance(type_text, list):
        raise TypeError("type_text must be a string or list of strings")

    if regex:
        pattern = '|'.join(f'{p}' for p in type_text)
        return df['text'].str.contains(pattern, case=False, na=False, regex=True)
    else:
        masks = [df['text'].str.contains(p, case=False, na=False, regex=False) for p in type_text]
        if combine_with_or:
            return pd.concat(masks, axis=1).any(axis=1)
        else:
            return pd.concat(masks, axis=1).all(axis=1)

def create_keyword_mask(df: pd.DataFrame, type_text: Union[str, List[str]], regex: bool = True) -> pd.Series[bool]:
    """Create a boolean mask for rows where keyword text matches one or more patterns.

    Args:
        df: DataFrame to search
        type_text: Type text pattern(s) to match. Can be a single string or list of strings.
        regex: Whether to treat patterns as regex expressions (default: True)

    Returns:
        Boolean Series indicating matching rows. For rows with empty/null keywords,
        returns False.

    Raises:
        ValueError: If type_text is empty or None
        TypeError: If type_text is not a string or list of strings
        ValueError: If required 'keywords' column is missing from DataFrame
    """
    # Validate required columns
    validate_dataframe_columns(df, {'keywords'})

    # Handle empty DataFrame case
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    if not type_text:
        raise ValueError("type_text cannot be empty or None")

    if isinstance(type_text, str):
        type_text = [type_text]
    elif not isinstance(type_text, list):
        raise TypeError("type_text must be a string or list of strings")

    # Create default mask for null values
    # Handle null values and convert to string
    keywords = df['keywords'].fillna('')
    # Convert non-string values to strings
    keywords = keywords.astype(str)

    if regex:
        pattern = '|'.join(f'{p}' for p in type_text)
        return keywords.str.contains(pattern, case=False, na=False, regex=True)
    else:
        masks = [keywords.str.contains(p, case=False, na=False, regex=False) for p in type_text]
        return pd.concat(masks, axis=1).any(axis=1)

def create_name_mask(df: pd.DataFrame, type_text: Union[str, List[str]], regex: bool = True) -> pd.Series[bool]:
    """Create a boolean mask for rows where name matches one or more patterns.

    Args:
        df: DataFrame to search
        type_text: Type text pattern(s) to match. Can be a single string or list of strings.
        regex: Whether to treat patterns as regex expressions (default: True)

    Returns:
        Boolean Series indicating matching rows

    Raises:
        ValueError: If type_text is empty or None
        TypeError: If type_text is not a string or list of strings
    """
    if not type_text:
        raise ValueError("type_text cannot be empty or None")

    if isinstance(type_text, str):
        type_text = [type_text]
    elif not isinstance(type_text, list):
        raise TypeError("type_text must be a string or list of strings")

    if regex:
        pattern = '|'.join(f'{p}' for p in type_text)
        return df['name'].str.contains(pattern, case=False, na=False, regex=True)
    else:
        masks = [df['name'].str.contains(p, case=False, na=False, regex=False) for p in type_text]
        return pd.concat(masks, axis=1).any(axis=1)

def extract_creature_types(type_text: str, creature_types: List[str], non_creature_types: List[str]) -> List[str]:
    """Extract creature types from a type text string.

    Args:
        type_text: The type line text to parse
        creature_types: List of valid creature types
        non_creature_types: List of non-creature types to exclude

    Returns:
        List of extracted creature types
    """
    types = [t.strip() for t in type_text.split()]
    return [t for t in types if t in creature_types and t not in non_creature_types]

def find_types_in_text(text: str, name: str, creature_types: List[str]) -> List[str]:
    """Find creature types mentioned in card text.

    Args:
        text: Card text to search
        name: Card name to exclude from search
        creature_types: List of valid creature types

    Returns:
        List of found creature types
    """
    if pd.isna(text):
        return []
        
    found_types = []
    words = text.split()
    
    for word in words:
        clean_word = re.sub(r'[^a-zA-Z-]', '', word)
        if clean_word in creature_types:
            if clean_word not in name:
                found_types.append(clean_word)
                
    return list(set(found_types))

def add_outlaw_type(types: List[str], outlaw_types: List[str]) -> List[str]:
    """Add Outlaw type if card has an outlaw-related type.

    Args:
        types: List of current types
        outlaw_types: List of types that qualify for Outlaw

    Returns:
        Updated list of types
    """
    if any(t in outlaw_types for t in types) and 'Outlaw' not in types:
        return types + ['Outlaw']
    return types

def create_tag_mask(df: pd.DataFrame, tag_patterns: Union[str, List[str]], column: str = 'themeTags') -> pd.Series[bool]:
    """Create a boolean mask for rows where tags match specified patterns.

    Args:
        df: DataFrame to search
        tag_patterns: String or list of strings to match against tags
        column: Column containing tags to search (default: 'themeTags')

    Returns:
        Boolean Series indicating matching rows

    Examples:
        # Match cards with draw-related tags
        >>> mask = create_tag_mask(df, ['Card Draw', 'Conditional Draw'])
        >>> mask = create_tag_mask(df, 'Unconditional Draw')
    """
    if isinstance(tag_patterns, str):
        tag_patterns = [tag_patterns]

    # Handle empty DataFrame case
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    # Create mask for each pattern
    masks = [df[column].apply(lambda x: any(pattern in tag for tag in x)) for pattern in tag_patterns]
    
    # Combine masks with OR
    return pd.concat(masks, axis=1).any(axis=1)

def validate_dataframe_columns(df: pd.DataFrame, required_columns: Set[str]) -> None:
    """Validate that DataFrame contains all required columns.

    Args:
        df: DataFrame to validate
        required_columns: Set of column names that must be present

    Raises:
        ValueError: If any required columns are missing
    """
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
def apply_tag_vectorized(df: pd.DataFrame, mask: pd.Series[bool], tags: Union[str, List[str]]) -> None:
    """Apply tags to rows in a dataframe based on a boolean mask.
    
    Args:
        df: The dataframe to modify
        mask: Boolean series indicating which rows to tag
        tags: List of tags to apply
    """
    if not isinstance(tags, list):
        tags = [tags]
        
    # Get current tags for masked rows
    current_tags = df.loc[mask, 'themeTags']
    
    # Add new tags
    df.loc[mask, 'themeTags'] = current_tags.apply(lambda x: sorted(list(set(x + tags))))

def create_mass_effect_mask(df: pd.DataFrame, effect_type: str) -> pd.Series[bool]:
    """Create a boolean mask for cards with mass removal effects of a specific type.

    Args:
        df: DataFrame to search
        effect_type: Type of mass effect to match ('destruction', 'exile', 'bounce', 'sacrifice', 'damage')

    Returns:
        Boolean Series indicating which cards have mass effects of the specified type

    Raises:
        ValueError: If effect_type is not recognized
    """
    if effect_type not in tag_constants.BOARD_WIPE_TEXT_PATTERNS:
        raise ValueError(f"Unknown effect type: {effect_type}")

    patterns = tag_constants.BOARD_WIPE_TEXT_PATTERNS[effect_type]
    return create_text_mask(df, patterns)

def create_damage_pattern(number: Union[int, str]) -> str:
    """Create a pattern for matching X damage effects.

    Args:
        number: Number or variable (X) for damage amount

    Returns:
        Pattern string for matching damage effects
    """
    return f'deals {number} damage'

def create_mass_damage_mask(df: pd.DataFrame) -> pd.Series[bool]:
    """Create a boolean mask for cards with mass damage effects.

    Args:
        df: DataFrame to search

    Returns:
        Boolean Series indicating which cards have mass damage effects
    """
    # Create patterns for numeric damage
    number_patterns = [create_damage_pattern(i) for i in range(1, 21)]
    
    # Add X damage pattern
    number_patterns.append(create_damage_pattern('X'))
    
    # Add patterns for damage targets
    target_patterns = [
        'to each creature',
        'to all creatures',
        'to each player',
        'to each opponent',
        'to everything'
    ]
    
    # Create masks
    damage_mask = create_text_mask(df, number_patterns)
    target_mask = create_text_mask(df, target_patterns)
    
    return damage_mask & target_mask