"""
Utilities for include/exclude card functionality.

Provides fuzzy matching, card name normalization, and validation
for must-include and must-exclude card lists.
"""

from __future__ import annotations

import difflib
import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass


# Fuzzy matching configuration
FUZZY_CONFIDENCE_THRESHOLD = 0.90  # 90% confidence for auto-acceptance
MAX_SUGGESTIONS = 3  # Maximum suggestions to show for fuzzy matches
MAX_INCLUDES = 10  # Maximum include cards allowed
MAX_EXCLUDES = 15  # Maximum exclude cards allowed


@dataclass
@dataclass
class FuzzyMatchResult:
    """Result of a fuzzy card name match."""
    input_name: str
    matched_name: Optional[str]
    confidence: float
    suggestions: List[str]
    auto_accepted: bool


@dataclass
class IncludeExcludeDiagnostics:
    """Diagnostics for include/exclude processing."""
    missing_includes: List[str]
    ignored_color_identity: List[str]
    illegal_dropped: List[str]
    illegal_allowed: List[str]
    excluded_removed: List[str]
    duplicates_collapsed: Dict[str, int]
    include_added: List[str]
    include_over_ideal: Dict[str, List[str]]  # e.g., {"creatures": ["Card A"]} when includes exceed ideal category counts
    fuzzy_corrections: Dict[str, str]
    confirmation_needed: List[Dict[str, any]]
    list_size_warnings: Dict[str, int]


def normalize_card_name(name: str) -> str:
    """
    Normalize card names for robust matching.
    
    Handles:
    - Case normalization (casefold)
    - Punctuation normalization (commas, apostrophes)
    - Whitespace cleanup
    - Unicode apostrophe normalization
    - Arena/Alchemy prefix removal
    
    Args:
        name: Raw card name input
        
    Returns:
        Normalized card name for matching
    """
    if not name:
        return ""
    
    # Basic cleanup
    s = str(name).strip()
    
    # Normalize unicode characters
    s = s.replace('\u2019', "'")  # Curly apostrophe to straight
    s = s.replace('\u2018', "'")  # Opening single quote
    s = s.replace('\u201C', '"')  # Opening double quote
    s = s.replace('\u201D', '"')  # Closing double quote
    s = s.replace('\u2013', "-")  # En dash
    s = s.replace('\u2014', "-")  # Em dash
    
    # Remove Arena/Alchemy prefix
    if s.startswith('A-') and len(s) > 2:
        s = s[2:]
    
    # Normalize whitespace
    s = " ".join(s.split())
    
    # Case normalization
    return s.casefold()


def normalize_punctuation(name: str) -> str:
    """
    Normalize punctuation for fuzzy matching.
    
    Specifically handles the case where users might omit commas:
    "Krenko, Mob Boss" vs "Krenko Mob Boss"
    
    Args:
        name: Card name to normalize
        
    Returns:
        Name with punctuation variations normalized
    """
    if not name:
        return ""
    
    # Remove common punctuation for comparison
    s = normalize_card_name(name)
    
    # Remove commas, colons, and extra spaces for fuzzy matching
    s = re.sub(r'[,:]', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    
    return s.strip()


def fuzzy_match_card_name(
    input_name: str,
    card_names: Set[str],
    confidence_threshold: float = FUZZY_CONFIDENCE_THRESHOLD
) -> FuzzyMatchResult:
    """
    Perform fuzzy matching on a card name against a set of valid names.
    
    Args:
        input_name: User input card name
        card_names: Set of valid card names to match against
        confidence_threshold: Minimum confidence for auto-acceptance
        
    Returns:
        FuzzyMatchResult with match information
    """
    if not input_name or not card_names:
        return FuzzyMatchResult(
            input_name=input_name,
            matched_name=None,
            confidence=0.0,
            suggestions=[],
            auto_accepted=False
        )
    
    # Normalize input for matching
    normalized_input = normalize_punctuation(input_name)
    
    # Create normalized lookup for card names
    normalized_to_original = {}
    for name in card_names:
        normalized = normalize_punctuation(name)
        if normalized not in normalized_to_original:
            normalized_to_original[normalized] = name
    
    normalized_names = set(normalized_to_original.keys())
    
    # Exact match check (after normalization)
    if normalized_input in normalized_names:
        return FuzzyMatchResult(
            input_name=input_name,
            matched_name=normalized_to_original[normalized_input],
            confidence=1.0,
            suggestions=[],
            auto_accepted=True
        )
    
    # Fuzzy matching using difflib
    matches = difflib.get_close_matches(
        normalized_input, 
        normalized_names, 
        n=MAX_SUGGESTIONS + 1,  # Get one extra in case best match is below threshold
        cutoff=0.6  # Lower cutoff to get more candidates
    )
    
    if not matches:
        return FuzzyMatchResult(
            input_name=input_name,
            matched_name=None,
            confidence=0.0,
            suggestions=[],
            auto_accepted=False
        )
    
    # Calculate actual confidence for best match
    best_match = matches[0]
    confidence = difflib.SequenceMatcher(None, normalized_input, best_match).ratio()
    
    # Convert back to original names
    suggestions = [normalized_to_original[match] for match in matches[:MAX_SUGGESTIONS]]
    best_original = normalized_to_original[best_match]
    
    # Auto-accept if confidence is high enough
    auto_accepted = confidence >= confidence_threshold
    matched_name = best_original if auto_accepted else None
    
    return FuzzyMatchResult(
        input_name=input_name,
        matched_name=matched_name,
        confidence=confidence,
        suggestions=suggestions,
        auto_accepted=auto_accepted
    )


def validate_list_sizes(includes: List[str], excludes: List[str]) -> Dict[str, any]:
    """
    Validate that include/exclude lists are within acceptable size limits.
    
    Args:
        includes: List of include card names
        excludes: List of exclude card names
        
    Returns:
        Dictionary with validation results and warnings
    """
    include_count = len(includes)
    exclude_count = len(excludes)
    
    warnings = {}
    errors = []
    
    # Size limit checks
    if include_count > MAX_INCLUDES:
        errors.append(f"Too many include cards: {include_count} (max {MAX_INCLUDES})")
    elif include_count >= int(MAX_INCLUDES * 0.8):  # 80% warning threshold
        warnings['includes_approaching_limit'] = f"Approaching include limit: {include_count}/{MAX_INCLUDES}"
    
    if exclude_count > MAX_EXCLUDES:
        errors.append(f"Too many exclude cards: {exclude_count} (max {MAX_EXCLUDES})")
    elif exclude_count >= int(MAX_EXCLUDES * 0.8):  # 80% warning threshold
        warnings['excludes_approaching_limit'] = f"Approaching exclude limit: {exclude_count}/{MAX_EXCLUDES}"
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'counts': {
            'includes': include_count,
            'excludes': exclude_count,
            'includes_limit': MAX_INCLUDES,
            'excludes_limit': MAX_EXCLUDES
        }
    }


def collapse_duplicates(card_names: List[str]) -> Tuple[List[str], Dict[str, int]]:
    """
    Remove duplicates from card list and track collapsed counts.
    
    Commander format allows only one copy of each card (except for exceptions),
    so duplicate entries in user input should be collapsed to single copies.
    
    Args:
        card_names: List of card names (may contain duplicates)
        
    Returns:
        Tuple of (unique_names, duplicate_counts)
    """
    if not card_names:
        return [], {}
    
    seen = {}
    unique_names = []
    
    for name in card_names:
        if not name or not name.strip():
            continue
            
        name = name.strip()
        normalized = normalize_card_name(name)
        
        if normalized not in seen:
            seen[normalized] = {'original': name, 'count': 1}
            unique_names.append(name)
        else:
            seen[normalized]['count'] += 1
    
    # Extract duplicate counts (only for names that appeared more than once)
    duplicates = {
        data['original']: data['count'] 
        for data in seen.values() 
        if data['count'] > 1
    }
    
    return unique_names, duplicates


def parse_card_list_input(input_text: str) -> List[str]:
    """
    Parse user input text into a list of card names.
    
    Supports:
    - Newline separated (preferred for cards with commas in names)
    - Comma separated (only when no newlines present)
    - Whitespace cleanup
    
    Note: If input contains both newlines and commas, newlines take precedence
    to avoid splitting card names that contain commas.
    
    Args:
        input_text: Raw user input text
        
    Returns:
        List of parsed card names
    """
    if not input_text:
        return []
    
    # If input contains newlines, split only on newlines
    # This prevents breaking card names with commas like "Krenko, Mob Boss"
    if '\n' in input_text:
        names = input_text.split('\n')
    else:
        # Only split on commas if no newlines present
        names = input_text.split(',')
    
    # Clean up each name
    cleaned = []
    for name in names:
        name = name.strip()
        if name:  # Skip empty entries
            cleaned.append(name)
    
    return cleaned


def get_baseline_performance_metrics() -> Dict[str, any]:
    """
    Get baseline performance metrics for regression testing.
    
    Returns:
        Dictionary with timing and memory baselines
    """
    import time
    
    start_time = time.time()
    
    # Simulate some basic operations for baseline
    test_names = ['Lightning Bolt', 'Krenko, Mob Boss', 'Sol Ring'] * 100
    for name in test_names:
        normalize_card_name(name)
        normalize_punctuation(name)
    
    end_time = time.time()
    
    return {
        'normalization_time_ms': (end_time - start_time) * 1000,
        'operations_count': len(test_names) * 2,  # 2 operations per name
        'timestamp': time.time()
    }
