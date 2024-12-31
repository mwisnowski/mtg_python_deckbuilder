from typing import Union, List
import pandas as pd
import re
import logging
from typing import Dict, Optional, Set
from time import perf_counter
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

def sort_list(items: Union[List, pd.Series]) -> Union[List, pd.Series]:
    """Sort a list or pandas Series in ascending order.

    Args:
        items: List or Series to sort

    Returns:
        Sorted list or Series
    """
    if isinstance(items, (list, pd.Series)):
        return sorted(items) if isinstance(items, list) else items.sort_values()
    return items

def create_regex_mask(df: pd.DataFrame, column: str, pattern: str) -> pd.Series:
    """Create a boolean mask for rows where a column matches a regex pattern.

    Args:
        df: DataFrame to search
        column: Column name to search in
        pattern: Regex pattern to match

    Returns:
        Boolean Series indicating matching rows
    """
    return df[column].str.contains(pattern, case=False, na=False, regex=True)

def combine_masks(masks: List[pd.Series], logical_operator: str = 'and') -> pd.Series:
    """Combine multiple boolean masks with a logical operator.

    Args:
        masks: List of boolean Series masks to combine
        logical_operator: Logical operator to use ('and' or 'or')

    Returns:
        Combined boolean mask
    """
    if not masks:
        return pd.Series([], dtype=bool)
        
    result = masks[0]
    for mask in masks[1:]:
        if logical_operator == 'and':
            result = result & mask
        else:
            result = result | mask
    return result

def safe_str_contains(series: pd.Series, patterns: Union[str, List[str]], regex: bool = False) -> pd.Series:
    """Safely check if strings in a Series contain one or more patterns, handling NA values.

    Args:
        series: String Series to check
        patterns: String or list of strings to look for
        regex: Whether to treat patterns as regex expressions

    Returns:
        Boolean Series indicating which strings contain any of the patterns
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    
    if regex:
        pattern = '|'.join(f'({p})' for p in patterns)
        return series.fillna('').str.contains(pattern, case=False, na=False, regex=True)
    else:
        masks = [series.fillna('').str.contains(p, case=False, na=False, regex=False) for p in patterns]
        return pd.concat(masks, axis=1).any(axis=1)

def create_type_mask(df: pd.DataFrame, type_text: Union[str, List[str]], regex: bool = True) -> pd.Series:
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

def create_combined_type_mask(df: pd.DataFrame, type_patterns: Dict[str, List[str]], logical_operator: str = 'and') -> pd.Series:
    """Create a combined boolean mask from multiple type patterns.

    Args:
        df: DataFrame to search
        type_patterns: Dictionary mapping type categories to lists of patterns
        logical_operator: How to combine masks ('and' or 'or')

    Returns:
        Combined boolean mask

    Example:
        patterns = {
            'creature': ['Creature', 'Artifact Creature'],
            'enchantment': ['Enchantment', 'Enchantment Creature']
        }
        mask = create_combined_type_mask(df, patterns, 'or')
    """
    if not type_patterns:
        return pd.Series(True, index=df.index)

    category_masks = []
    for patterns in type_patterns.values():
        category_masks.append(create_type_mask(df, patterns))

    return combine_masks(category_masks, logical_operator)

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

def batch_update_types(df: pd.DataFrame, mask: pd.Series, new_types: List[str]) -> None:
    """Update creature types for multiple rows efficiently.

    Args:
        df: DataFrame to update
        mask: Boolean mask indicating which rows to update
        new_types: List of types to add
    """
    df.loc[mask, 'creatureTypes'] = df.loc[mask, 'creatureTypes'].apply(
        lambda x: sorted(list(set(x + new_types)))
    )

def create_tag_mask(df: pd.DataFrame, tag_patterns: Union[str, List[str]], column: str = 'themeTags') -> pd.Series:
    """Create a boolean mask for rows where tags match specified patterns.

    Args:
        df: DataFrame to search
        tag_patterns: String or list of strings to match against tags
        column: Column containing tags to search (default: 'themeTags')

    Returns:
        Boolean Series indicating matching rows
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
    
def apply_tag_vectorized(df: pd.DataFrame, mask: pd.Series, tags: List[str]) -> None:
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

def log_performance_metrics(start_time: float, operation: str, df_size: int) -> None:
    """Log performance metrics for an operation.

    Args:
        start_time: Start time from perf_counter()
        operation: Description of the operation performed
        df_size: Size of the DataFrame processed
    """
    duration = perf_counter() - start_time
    logging.info(
        f"{operation} completed in {duration:.2f}s for {df_size} rows "
        f"({duration/df_size*1000:.2f}ms per row)"
    )