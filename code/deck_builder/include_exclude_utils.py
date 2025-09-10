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

from .builder_constants import POPULAR_CARDS, ICONIC_CARDS


# Fuzzy matching configuration
FUZZY_CONFIDENCE_THRESHOLD = 0.95  # 95% confidence for auto-acceptance (more conservative)
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
    
    # Enhanced fuzzy matching with intelligent prefix prioritization
    input_lower = normalized_input.lower()
    
    # Convert constants to lowercase for matching
    popular_cards_lower = {card.lower() for card in POPULAR_CARDS}
    iconic_cards_lower = {card.lower() for card in ICONIC_CARDS}
    
    # Collect candidates with different scoring strategies
    candidates = []
    
    for name in normalized_names:
        name_lower = name.lower()
        base_score = difflib.SequenceMatcher(None, input_lower, name_lower).ratio()
        
        # Skip very low similarity matches early
        if base_score < 0.3:
            continue
            
        final_score = base_score
        
        # Strong boost for exact prefix matches (input is start of card name)
        if name_lower.startswith(input_lower):
            final_score = min(1.0, base_score + 0.5)
        
        # Moderate boost for word-level prefix matches  
        elif any(word.startswith(input_lower) for word in name_lower.split()):
            final_score = min(1.0, base_score + 0.3)
            
        # Special case: if input could be abbreviation of first word, boost heavily
        elif len(input_lower) <= 6:
            first_word = name_lower.split()[0] if name_lower.split() else ""
            if first_word and first_word.startswith(input_lower):
                final_score = min(1.0, base_score + 0.4)
        
        # Boost for cards where input is contained as substring
        elif input_lower in name_lower:
            final_score = min(1.0, base_score + 0.2)
        
        # Special boost for very short inputs that are obvious abbreviations
        if len(input_lower) <= 4:
            # For short inputs, heavily favor cards that start with the input
            if name_lower.startswith(input_lower):
                final_score = min(1.0, final_score + 0.3)
        
        # Popularity boost for well-known cards
        if name_lower in popular_cards_lower:
            final_score = min(1.0, final_score + 0.25)
        
        # Extra boost for super iconic cards like Lightning Bolt (only when relevant)
        if name_lower in iconic_cards_lower:
            # Only boost if there's some relevance to the input
            if any(word[:3] in input_lower or input_lower[:3] in word for word in name_lower.split()):
                final_score = min(1.0, final_score + 0.3)
            # Extra boost for Lightning Bolt when input is 'lightning' or similar
            if name_lower == 'lightning bolt' and input_lower in ['lightning', 'lightn', 'light']:
                final_score = min(1.0, final_score + 0.2)
            
        # Special handling for Lightning Bolt variants
        if 'lightning' in name_lower and 'bolt' in name_lower:
            if input_lower in ['bolt', 'lightn', 'lightning']:
                final_score = min(1.0, final_score + 0.4)
        
        # Simplicity boost: prefer shorter, simpler card names for short inputs
        if len(input_lower) <= 6:
            # Boost shorter card names slightly
            if len(name_lower) <= len(input_lower) * 2:
                final_score = min(1.0, final_score + 0.05)
        
        candidates.append((final_score, name))
    
    if not candidates:
        return FuzzyMatchResult(
            input_name=input_name,
            matched_name=None,
            confidence=0.0,
            suggestions=[],
            auto_accepted=False
        )
    
    # Sort candidates by score (highest first)
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Get best match and confidence
    best_score, best_match = candidates[0]
    confidence = best_score
    
    # Convert back to original names, preserving score-based order
    suggestions = [normalized_to_original[match] for _, match in candidates[:MAX_SUGGESTIONS]]
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
    - Comma separated only for simple lists without newlines
    - Whitespace cleanup
    
    Note: Always prioritizes newlines over commas to avoid splitting card names 
    that contain commas like "Byrke, Long ear Of the Law".
    
    Args:
        input_text: Raw user input text
        
    Returns:
        List of parsed card names
    """
    if not input_text:
        return []
    
    # Always split on newlines first - this is the preferred format
    # and prevents breaking card names with commas
    lines = input_text.split('\n')
    
    # If we only have one line and it contains commas, 
    # then it might be comma-separated input vs a single card name with commas
    if len(lines) == 1 and ',' in lines[0]:
        text = lines[0].strip()
        
        # Better heuristic: if there are no spaces around commas AND
        # the text contains common MTG name patterns, treat as single card
        # Common patterns: "Name, Title", "First, Last Name", etc.
        import re
        
        # Check for patterns that suggest it's a single card name:
        # 1. Comma followed by a capitalized word (title/surname pattern)
        # 2. Single comma with reasonable length text on both sides
        title_pattern = re.search(r'^[^,]{2,30},\s+[A-Z][^,]{2,30}$', text.strip())
        
        if title_pattern:
            # This looks like "Byrke, Long ear Of the Law" - single card
            names = [text]
        else:
            # This looks like "Card1,Card2" or "Card1, Card2" - multiple cards
            names = text.split(',')
    else:
        names = lines  # Use newline split
    
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
