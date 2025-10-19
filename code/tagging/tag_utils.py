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
import re
from functools import lru_cache
from typing import Any, List, Set, Tuple, Union
import numpy as np
import pandas as pd
from . import tag_constants


# --- Internal helpers for performance -----------------------------------------------------------
@lru_cache(maxsize=2048)
def _build_joined_pattern(parts: Tuple[str, ...]) -> str:
    """Join multiple regex parts with '|'. Cached for reuse across calls."""
    return '|'.join(parts)


@lru_cache(maxsize=2048)
def _compile_pattern(pattern: str, ignore_case: bool = True):
    """Compile a regex pattern with optional IGNORECASE. Cached for reuse."""
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(pattern, flags)

def _ensure_norm_series(df: pd.DataFrame, source_col: str, norm_col: str) -> pd.Series:
    """Ensure a cached normalized string series exists on df for source_col.

    Normalization here means: fillna('') and cast to str once. This avoids
    repeating fill/astype work on every mask creation. Extra columns are
    later dropped by final reindex in output.

    Args:
        df: DataFrame containing the column
        source_col: Name of the source column (e.g., 'text')
        norm_col: Name of the cache column to create/use (e.g., '__text_s')

    Returns:
        The normalized pandas Series.
    """
    if norm_col in df.columns:
        return df[norm_col]
    series = df[source_col].fillna('') if source_col in df.columns else pd.Series([''] * len(df), index=df.index)
    series = series.astype(str)
    df[norm_col] = series
    return df[norm_col]

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

    if len(df) == 0:
        return pd.Series([], dtype=bool)
    type_series = _ensure_norm_series(df, 'type', '__type_s')

    if regex:
        pattern = _build_joined_pattern(tuple(type_text)) if len(type_text) > 1 else type_text[0]
        compiled = _compile_pattern(pattern, ignore_case=True)
        return type_series.str.contains(compiled, na=False, regex=True)
    else:
        masks = [type_series.str.contains(p, case=False, na=False, regex=False) for p in type_text]
        if not masks:
            return pd.Series(False, index=df.index)
        return pd.Series(np.logical_or.reduce(masks), index=df.index)

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

    if len(df) == 0:
        return pd.Series([], dtype=bool)
    text_series = _ensure_norm_series(df, 'text', '__text_s')

    if regex:
        pattern = _build_joined_pattern(tuple(type_text)) if len(type_text) > 1 else type_text[0]
        compiled = _compile_pattern(pattern, ignore_case=True)
        return text_series.str.contains(compiled, na=False, regex=True)
    else:
        masks = [text_series.str.contains(p, case=False, na=False, regex=False) for p in type_text]
        if not masks:
            return pd.Series(False, index=df.index)
        reduced = np.logical_or.reduce(masks) if combine_with_or else np.logical_and.reduce(masks)
        return pd.Series(reduced, index=df.index)

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
    validate_dataframe_columns(df, {'keywords'})
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    if not type_text:
        raise ValueError("type_text cannot be empty or None")

    if isinstance(type_text, str):
        type_text = [type_text]
    elif not isinstance(type_text, list):
        raise TypeError("type_text must be a string or list of strings")
    keywords = _ensure_norm_series(df, 'keywords', '__keywords_s')

    if regex:
        pattern = _build_joined_pattern(tuple(type_text)) if len(type_text) > 1 else type_text[0]
        compiled = _compile_pattern(pattern, ignore_case=True)
        return keywords.str.contains(compiled, na=False, regex=True)
    else:
        masks = [keywords.str.contains(p, case=False, na=False, regex=False) for p in type_text]
        if not masks:
            return pd.Series(False, index=df.index)
        return pd.Series(np.logical_or.reduce(masks), index=df.index)

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

    if len(df) == 0:
        return pd.Series([], dtype=bool)
    name_series = _ensure_norm_series(df, 'name', '__name_s')

    if regex:
        pattern = _build_joined_pattern(tuple(type_text)) if len(type_text) > 1 else type_text[0]
        compiled = _compile_pattern(pattern, ignore_case=True)
        return name_series.str.contains(compiled, na=False, regex=True)
    else:
        masks = [name_series.str.contains(p, case=False, na=False, regex=False) for p in type_text]
        if not masks:
            return pd.Series(False, index=df.index)
        return pd.Series(np.logical_or.reduce(masks), index=df.index)

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
        >>> mask = create_tag_mask(df, ['Card Draw', 'Conditional Draw'])
        >>> mask = create_tag_mask(df, 'Unconditional Draw')
    """
    if isinstance(tag_patterns, str):
        tag_patterns = [tag_patterns]
    if len(df) == 0:
        return pd.Series([], dtype=bool)
    masks = [df[column].apply(lambda x: any(pattern in tag for tag in x)) for pattern in tag_patterns]
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
    current_tags = df.loc[mask, 'themeTags']
    df.loc[mask, 'themeTags'] = current_tags.apply(lambda x: sorted(list(set(x + tags))))

def apply_rules(df: pd.DataFrame, rules: List[dict]) -> None:
        """Apply a list of rules to a DataFrame.

        Each rule dict supports:
            - mask: pd.Series of booleans or a callable df->mask
            - tags: str|List[str]

        Example:
            rules = [
                { 'mask': lambda d: create_text_mask(d, 'lifelink'), 'tags': ['Lifelink'] },
            ]

        Args:
                df: DataFrame to update
                rules: list of rule dicts
        """
        for rule in rules:
                mask = rule.get('mask')
                if callable(mask):
                        mask = mask(df)
                if mask is None:
                        continue
                tags = rule.get('tags', [])
                apply_tag_vectorized(df, mask, tags)

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

def create_trigger_mask(
    df: pd.DataFrame,
    subjects: Union[str, List[str]],
    include_attacks: bool = False,
) -> pd.Series:
    """Create a mask for text that contains trigger phrases followed by subjects.

    Example: with subjects=['a creature','you'] builds patterns:
      'when a creature', 'whenever you', 'at you', etc.

    Args:
        df: DataFrame
        subjects: A subject string or list (will be normalized to list)
        include_attacks: If True, also include '{trigger} .* attacks'

    Returns:
        Boolean Series mask
    """
    subs = [subjects] if isinstance(subjects, str) else subjects
    patterns: List[str] = []
    for trig in tag_constants.TRIGGERS:
        patterns.extend([f"{trig} {s}" for s in subs])
        if include_attacks:
            patterns.append(f"{trig} .* attacks")
    return create_text_mask(df, patterns)

def create_numbered_phrase_mask(
    df: pd.DataFrame,
    verb: Union[str, List[str]],
    noun: str = '',
    numbers: List[str] | None = None,
) -> pd.Series:
    """Create a boolean mask for phrases like 'draw {num} card'.

    Args:
        df: DataFrame to search
    verb: Action verb or list of verbs (e.g., 'draw' or ['gain', 'gains'])
    noun: Optional object noun in singular form (e.g., 'card'); if empty, omitted
        numbers: Optional list of number words/digits (defaults to tag_constants.NUM_TO_SEARCH)

    Returns:
        Boolean Series mask
    """
    if numbers is None:
        numbers = tag_constants.NUM_TO_SEARCH
    # Normalize verbs to list
    verbs = [verb] if isinstance(verb, str) else verb
    if noun:
        patterns = [fr"{v}\s+{num}\s+{noun}" for v in verbs for num in numbers]
    else:
        patterns = [fr"{v}\s+{num}" for v in verbs for num in numbers]
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
    number_patterns = [create_damage_pattern(i) for i in range(1, 21)]
    number_patterns.append(create_damage_pattern('X'))
    target_patterns = [
        'to each creature',
        'to all creatures',
        'to each player',
        'to each opponent',
        'to everything'
    ]
    damage_mask = create_text_mask(df, number_patterns)
    target_mask = create_text_mask(df, target_patterns)
    
    return damage_mask & target_mask


# ==============================================================================
# Keyword Normalization (M1 - Tagging Refinement)
# ==============================================================================

def normalize_keywords(
    raw: Union[List[str], Set[str], Tuple[str, ...]],
    allowlist: Set[str],
    frequency_map: dict[str, int]
) -> list[str]:
    """Normalize keyword strings for theme tagging.
    
    Applies normalization rules:
    1. Case normalization (via normalization map)
    2. Canonical mapping (e.g., "Commander Ninjutsu" -> "Ninjutsu")
    3. Singleton pruning (unless allowlisted)
    4. Deduplication
    5. Exclusion of blacklisted keywords
    
    Args:
        raw: Iterable of raw keyword strings
        allowlist: Set of keywords that should survive singleton pruning
        frequency_map: Dict mapping keywords to their occurrence count
    
    Returns:
        Deduplicated list of normalized keywords
        
    Raises:
        ValueError: If raw is not iterable
        
    Examples:
        >>> normalize_keywords(
        ...     ['Commander Ninjutsu', 'Flying', 'Allons-y!'],
        ...     {'Flying', 'Ninjutsu'},
        ...     {'Commander Ninjutsu': 2, 'Flying': 100, 'Allons-y!': 1}
        ... )
        ['Ninjutsu', 'Flying']  # 'Allons-y!' pruned as singleton
    """
    if not hasattr(raw, '__iter__') or isinstance(raw, (str, bytes)):
        raise ValueError(f"raw must be iterable, got {type(raw)}")
    
    normalized_keywords: set[str] = set()
    
    for keyword in raw:
        if not isinstance(keyword, str):
            continue
        keyword = keyword.strip()
        if not keyword:
            continue
        if keyword.lower() in tag_constants.KEYWORD_EXCLUSION_SET:
            continue
        normalized = tag_constants.KEYWORD_NORMALIZATION_MAP.get(keyword, keyword)
        frequency = frequency_map.get(keyword, 0)
        is_singleton = frequency == 1
        is_allowlisted = normalized in allowlist or keyword in allowlist
        
        # Prune singletons that aren't allowlisted
        if is_singleton and not is_allowlisted:
            continue
        
        normalized_keywords.add(normalized)
    
    return sorted(list(normalized_keywords))


# ==============================================================================
# M3: Metadata vs Theme Tag Classification
# ==============================================================================

def classify_tag(tag: str) -> str:
    """Classify a tag as either 'metadata' or 'theme'.
    
    Metadata tags are diagnostic, bracket-related, or internal annotations that
    should not appear in theme catalogs or player-facing tag lists. Theme tags
    represent gameplay mechanics and deck archetypes.
    
    Classification rules (in order of precedence):
    1. Prefix match: Tags starting with METADATA_TAG_PREFIXES → metadata
    2. Exact match: Tags in METADATA_TAG_ALLOWLIST → metadata
    3. Kindred pattern: "{Type}s Gain Protection" → metadata
    4. Default: All other tags → theme
    
    Args:
        tag: Tag string to classify
        
    Returns:
        "metadata" or "theme"
        
    Examples:
        >>> classify_tag("Applied: Cost Reduction")
        'metadata'
        >>> classify_tag("Bracket: Game Changer")
        'metadata'
        >>> classify_tag("Knights Gain Protection")
        'metadata'
        >>> classify_tag("Card Draw")
        'theme'
        >>> classify_tag("Spellslinger")
        'theme'
    """
    # Prefix-based classification
    for prefix in tag_constants.METADATA_TAG_PREFIXES:
        if tag.startswith(prefix):
            return "metadata"
    
    # Exact match classification
    if tag in tag_constants.METADATA_TAG_ALLOWLIST:
        return "metadata"
    
    # Kindred protection metadata patterns: "{Type} Gain {Ability}"
    # Covers all protective abilities: Protection, Ward, Hexproof, Shroud, Indestructible
    # Examples: "Knights Gain Protection", "Spiders Gain Ward", "Merfolk Gain Ward"
    # Note: Checks for " Gain " pattern since some creature types like "Merfolk" don't end in 's'
    kindred_abilities = ["Protection", "Ward", "Hexproof", "Shroud", "Indestructible"]
    for ability in kindred_abilities:
        if " Gain " in tag and tag.endswith(ability):
            return "metadata"
    
    # Protection scope metadata patterns (M5): "{Scope}: {Ability}"
    # Indicates whether protection applies to self, your permanents, all permanents, or opponent's permanents
    # Examples: "Self: Hexproof", "Your Permanents: Ward", "Blanket: Indestructible"
    # These enable deck builder to filter for board-relevant protection vs self-only
    protection_scopes = ["Self:", "Your Permanents:", "Blanket:", "Opponent Permanents:"]
    for scope in protection_scopes:
        if tag.startswith(scope):
            return "metadata"
    
    # Phasing scope metadata patterns: "{Scope}: Phasing"
    # Indicates whether phasing applies to self, your permanents, all permanents, or opponents
    # Examples: "Self: Phasing", "Your Permanents: Phasing", "Blanket: Phasing", 
    #           "Targeted: Phasing", "Opponent Permanents: Phasing"
    # Similar to protection scopes, enables filtering for board-relevant phasing
    # Opponent Permanents: Phasing also triggers Removal tag (removal-style phasing)
    if tag in ["Self: Phasing", "Your Permanents: Phasing", "Blanket: Phasing", 
               "Targeted: Phasing", "Opponent Permanents: Phasing"]:
        return "metadata"
    
    # Default: treat as theme tag
    return "theme"


# --- Text Processing Helpers (M0.6) ---------------------------------------------------------
def strip_reminder_text(text: str) -> str:
    """Remove reminder text (content in parentheses) from card text.
    
    Reminder text often contains keywords and patterns that can cause false positives
    in pattern matching. This function strips all parenthetical content to focus on
    the actual game text.
    
    Args:
        text: Card text possibly containing reminder text in parentheses
        
    Returns:
        Text with all parenthetical content removed
        
    Example:
        >>> strip_reminder_text("Hexproof (This creature can't be the target of spells)")
        "Hexproof "
    """
    if not text:
        return text
    return re.sub(r'\([^)]*\)', '', text)


def extract_context_window(text: str, match_start: int, match_end: int, 
                           window_size: int = None, include_before: bool = False) -> str:
    """Extract a context window around a regex match for validation.
    
    When pattern matching finds a potential match, we often need to examine
    the surrounding text to validate the match or check for additional keywords.
    This function extracts a window of text around the match position.
    
    Args:
        text: Full text to extract context from
        match_start: Start position of the regex match
        match_end: End position of the regex match
        window_size: Number of characters to include after the match.
                    If None, uses CONTEXT_WINDOW_SIZE from tag_constants (default: 70).
                    To include context before the match, use include_before=True.
        include_before: If True, includes window_size characters before the match
                       in addition to after. If False (default), only includes after.
        
    Returns:
        Substring of text containing the match plus surrounding context
        
    Example:
        >>> text = "Creatures you control have hexproof and vigilance"
        >>> match = re.search(r'creatures you control', text)
        >>> extract_context_window(text, match.start(), match.end(), window_size=30)
        'Creatures you control have hexproof and '
    """
    if not text:
        return text
    if window_size is None:
        from .tag_constants import CONTEXT_WINDOW_SIZE
        window_size = CONTEXT_WINDOW_SIZE
    
    # Calculate window boundaries
    if include_before:
        context_start = max(0, match_start - window_size)
    else:
        context_start = match_start
    
    context_end = min(len(text), match_end + window_size)
    
    return text[context_start:context_end]


# --- Enhanced Tagging Utilities (M3.5/M3.6) ----------------------------------------------------

def build_combined_mask(
    df: pd.DataFrame,
    text_patterns: Union[str, List[str], None] = None,
    type_patterns: Union[str, List[str], None] = None,
    keyword_patterns: Union[str, List[str], None] = None,
    name_list: Union[List[str], None] = None,
    exclusion_patterns: Union[str, List[str], None] = None,
    combine_with_or: bool = True
) -> pd.Series[bool]:
    """Build a combined boolean mask from multiple pattern types.
    
    This utility reduces boilerplate when creating complex masks by combining
    text, type, keyword, and name patterns into a single mask. Patterns are
    combined with OR by default, but can be combined with AND.
    
    Args:
        df: DataFrame to search
        text_patterns: Patterns to match in 'text' column
        type_patterns: Patterns to match in 'type' column  
        keyword_patterns: Patterns to match in 'keywords' column
        name_list: List of exact card names to match
        exclusion_patterns: Text patterns to exclude from final mask
        combine_with_or: If True, combine masks with OR (default).
                        If False, combine with AND (requires all conditions)
    
    Returns:
        Boolean Series combining all specified patterns
        
    Example:
        >>> # Match cards with flying OR haste, exclude creatures
        >>> mask = build_combined_mask(
        ...     df,
        ...     keyword_patterns=['Flying', 'Haste'],
        ...     exclusion_patterns='Creature'
        ... )
    """
    if combine_with_or:
        result = pd.Series([False] * len(df), index=df.index)
    else:
        result = pd.Series([True] * len(df), index=df.index)
    masks = []
    
    if text_patterns is not None:
        masks.append(create_text_mask(df, text_patterns))
    
    if type_patterns is not None:
        masks.append(create_type_mask(df, type_patterns))
    
    if keyword_patterns is not None:
        masks.append(create_keyword_mask(df, keyword_patterns))
    
    if name_list is not None:
        masks.append(create_name_mask(df, name_list))
    if masks:
        if combine_with_or:
            for mask in masks:
                result |= mask
        else:
            for mask in masks:
                result &= mask
    if exclusion_patterns is not None:
        exclusion_mask = create_text_mask(df, exclusion_patterns)
        result &= ~exclusion_mask
    
    return result


def tag_with_logging(
    df: pd.DataFrame,
    mask: pd.Series[bool],
    tags: Union[str, List[str]],
    log_message: str,
    color: str = '',
    logger=None
) -> int:
    """Apply tags with standardized logging.
    
    This utility wraps the common pattern of applying tags and logging the count.
    It provides consistent formatting for log messages across the tagging module.
    
    Args:
        df: DataFrame to modify
        mask: Boolean mask indicating which rows to tag
        tags: Tag(s) to apply
        log_message: Description of what's being tagged (e.g., "flying creatures")
        color: Color identifier for context (optional)
        logger: Logger instance to use (optional, uses print if None)
    
    Returns:
        Count of cards tagged
        
    Example:
        >>> count = tag_with_logging(
        ...     df,
        ...     flying_mask,
        ...     'Flying',
        ...     'creatures with flying ability',
        ...     color='blue',
        ...     logger=logger
        ... )
        # Logs: "Tagged 42 blue creatures with flying ability"
    """
    count = mask.sum()
    if count > 0:
        apply_tag_vectorized(df, mask, tags)
    color_part = f'{color} ' if color else ''
    full_message = f'Tagged {count} {color_part}{log_message}'
    
    if logger:
        logger.info(full_message)
    else:
        print(full_message)
    
    return count


def tag_with_rules_and_logging(
    df: pd.DataFrame,
    rules: List[dict],
    summary_message: str,
    color: str = '',
    logger=None
) -> int:
    """Apply multiple tag rules with summarized logging.
    
    This utility combines apply_rules with logging, providing a summary of
    all cards affected across multiple rules.
    
    Args:
        df: DataFrame to modify
        rules: List of rule dicts (each with 'mask' and 'tags')
        summary_message: Overall description (e.g., "card draw effects")
        color: Color identifier for context (optional)
        logger: Logger instance to use (optional)
    
    Returns:
        Total count of unique cards affected by any rule
        
    Example:
        >>> rules = [
        ...     {'mask': flying_mask, 'tags': ['Flying']},
        ...     {'mask': haste_mask, 'tags': ['Haste', 'Aggro']}
        ... ]
        >>> count = tag_with_rules_and_logging(
        ...     df, rules, 'evasive creatures', color='red', logger=logger
        ... )
    """
    affected = pd.Series([False] * len(df), index=df.index)
    for rule in rules:
        mask = rule.get('mask')
        if callable(mask):
            mask = mask(df)
        if mask is not None and mask.any():
            tags = rule.get('tags', [])
            apply_tag_vectorized(df, mask, tags)
            affected |= mask
    
    count = affected.sum()
    # M4 (Parquet Migration): Display color identity more clearly
    if color:
        # Map color codes to friendly names
        color_map = {
            'w': 'white',
            'u': 'blue',
            'b': 'black',
            'r': 'red',
            'g': 'green',
            'wu': 'Azorius',
            'wb': 'Orzhov',
            'wr': 'Boros',
            'wg': 'Selesnya',
            'ub': 'Dimir',
            'ur': 'Izzet',
            'ug': 'Simic',
            'br': 'Rakdos',
            'bg': 'Golgari',
            'rg': 'Gruul',
            'wub': 'Esper',
            'wur': 'Jeskai',
            'wug': 'Bant',
            'wbr': 'Mardu',
            'wbg': 'Abzan',
            'wrg': 'Naya',
            'ubr': 'Grixis',
            'ubg': 'Sultai',
            'urg': 'Temur',
            'brg': 'Jund',
            'wubrg': '5-color',
            '': 'colorless'
        }
        color_display = color_map.get(color, color)
        color_part = f'{color_display} '
    else:
        color_part = ''
    full_message = f'Tagged {count} {color_part}{summary_message}'
    
    if logger:
        logger.info(full_message)
    else:
        print(full_message)
    
    return count