"""
Scope Detection Utilities

Generic utilities for detecting the scope of card abilities (protection, phasing, etc.).
Provides reusable pattern-matching logic to avoid duplication across modules.

Created as part of M2: Create Scope Detection Utilities milestone.
"""

# Standard library imports
import re
from dataclasses import dataclass
from typing import List, Optional, Set

# Local application imports
from . import regex_patterns as rgx
from . import tag_utils
from code.logging_util import get_logger

logger = get_logger(__name__)


@dataclass
class ScopePatterns:
    """
    Pattern collections for scope detection.
    
    Attributes:
        opponent: Patterns that indicate opponent ownership
        self_ref: Patterns that indicate self-reference
        your_permanents: Patterns that indicate "you control"
        blanket: Patterns that indicate no ownership qualifier
        targeted: Patterns that indicate targeting (optional)
    """
    opponent: List[re.Pattern]
    self_ref: List[re.Pattern]
    your_permanents: List[re.Pattern]
    blanket: List[re.Pattern]
    targeted: Optional[List[re.Pattern]] = None


def detect_scope(
    text: str,
    card_name: str,
    ability_keyword: str,
    patterns: ScopePatterns,
    allow_multiple: bool = False,
    check_grant_verbs: bool = False,
    keywords: Optional[str] = None,
) -> Optional[str]:
    """
    Generic scope detection with priority ordering.
    
    Detection priority (prevents misclassification):
    0. Static keyword (in keywords field or simple list) → "Self"
    1. Opponent ownership → "Opponent Permanents"
    2. Self-reference → "Self"
    3. Your ownership → "Your Permanents"
    4. No ownership qualifier → "Blanket"
    
    Args:
        text: Card text
        card_name: Card name (for self-reference detection)
        ability_keyword: Ability keyword to look for (e.g., "hexproof", "phasing")
        patterns: ScopePatterns object with pattern collections
        allow_multiple: If True, returns Set[str] instead of single scope
        check_grant_verbs: If True, checks for grant verbs before assuming "Self"
        keywords: Optional keywords field from card data (for static keyword detection)
        
    Returns:
        Scope string or None: "Self", "Your Permanents", "Blanket", "Opponent Permanents"
        If allow_multiple=True, returns Set[str] with all matching scopes
    """
    if not text or not ability_keyword:
        return set() if allow_multiple else None
    
    text_lower = text.lower()
    ability_lower = ability_keyword.lower()
    card_name_lower = card_name.lower() if card_name else ''
    
    # Check if ability is mentioned in text
    if ability_lower not in text_lower:
        return set() if allow_multiple else None
    
    # Priority 0: Check if this is a static keyword ability
    # Static keywords appear in the keywords field or as simple comma-separated lists
    # without grant verbs (e.g., "Flying, first strike, protection from black")
    if check_static_keyword(ability_keyword, keywords, text):
        if allow_multiple:
            return {"Self"}
        else:
            return "Self"
    
    if allow_multiple:
        scopes = set()
    else:
        scopes = None
    
    # Priority 1: Opponent ownership
    for pattern in patterns.opponent:
        if pattern.search(text_lower):
            if allow_multiple:
                scopes.add("Opponent Permanents")
                break
            else:
                return "Opponent Permanents"
    
    # Priority 2: Self-reference
    is_self = _check_self_reference(text_lower, card_name_lower, ability_lower, patterns.self_ref)
    
    # If check_grant_verbs is True, verify we don't have grant patterns before assuming Self
    if is_self and check_grant_verbs:
        has_grant_pattern = _has_grant_verbs(text_lower)
        if not has_grant_pattern:
            if allow_multiple:
                scopes.add("Self")
            else:
                return "Self"
    elif is_self:
        if allow_multiple:
            scopes.add("Self")
        else:
            return "Self"
    
    # Priority 3: Your ownership
    for pattern in patterns.your_permanents:
        if pattern.search(text_lower):
            if allow_multiple:
                scopes.add("Your Permanents")
                break
            else:
                return "Your Permanents"
    
    # Priority 4: Blanket (no ownership qualifier)
    for pattern in patterns.blanket:
        if pattern.search(text_lower):
            # Double-check no ownership was missed
            if not rgx.YOU_CONTROL.search(text_lower) and 'opponent' not in text_lower:
                if allow_multiple:
                    scopes.add("Blanket")
                    break
                else:
                    return "Blanket"
    
    return scopes if allow_multiple else None


def detect_multi_scope(
    text: str,
    card_name: str,
    ability_keyword: str,
    patterns: ScopePatterns,
    check_grant_verbs: bool = False,
    keywords: Optional[str] = None,
) -> Set[str]:
    """
    Detect multiple scopes for cards with multiple effects.
    
    Some cards grant abilities to multiple scopes:
    - Self-hexproof + grants ward to others
    - Target phasing + your permanents phasing
    
    Args:
        text: Card text
        card_name: Card name
        ability_keyword: Ability keyword to look for
        patterns: ScopePatterns object
        check_grant_verbs: If True, checks for grant verbs before assuming "Self"
        keywords: Optional keywords field for static keyword detection
        
    Returns:
        Set of scope strings
    """
    scopes = set()
    
    if not text or not ability_keyword:
        return scopes
    
    text_lower = text.lower()
    ability_lower = ability_keyword.lower()
    card_name_lower = card_name.lower() if card_name else ''
    
    # Check for static keyword first
    if check_static_keyword(ability_keyword, keywords, text):
        scopes.add("Self")
        # For static keywords, we usually don't have multiple scopes
        # But continue checking in case there are additional effects
    
    # Check if ability is mentioned
    if ability_lower not in text_lower:
        return scopes
    
    # Check opponent patterns
    if any(pattern.search(text_lower) for pattern in patterns.opponent):
        scopes.add("Opponent Permanents")
    
    # Check self-reference
    is_self = _check_self_reference(text_lower, card_name_lower, ability_lower, patterns.self_ref)
    
    if is_self:
        if check_grant_verbs:
            has_grant_pattern = _has_grant_verbs(text_lower)
            if not has_grant_pattern:
                scopes.add("Self")
        else:
            scopes.add("Self")
    
    # Check your permanents
    if any(pattern.search(text_lower) for pattern in patterns.your_permanents):
        scopes.add("Your Permanents")
    
    # Check blanket (no ownership)
    has_blanket = any(pattern.search(text_lower) for pattern in patterns.blanket)
    no_ownership = not rgx.YOU_CONTROL.search(text_lower) and 'opponent' not in text_lower
    
    if has_blanket and no_ownership:
        scopes.add("Blanket")
    
    # Optional: Check for targeting
    if patterns.targeted:
        if any(pattern.search(text_lower) for pattern in patterns.targeted):
            scopes.add("Targeted")
    
    return scopes


def _check_self_reference(
    text_lower: str,
    card_name_lower: str,
    ability_lower: str,
    self_patterns: List[re.Pattern]
) -> bool:
    """
    Check if text contains self-reference patterns.
    
    Args:
        text_lower: Lowercase card text
        card_name_lower: Lowercase card name
        ability_lower: Lowercase ability keyword
        self_patterns: List of self-reference patterns
        
    Returns:
        True if self-reference found
    """
    # Check provided self patterns
    for pattern in self_patterns:
        if pattern.search(text_lower):
            return True
    
    # Check for card name reference (if provided)
    if card_name_lower:
        card_name_escaped = re.escape(card_name_lower)
        card_name_pattern = re.compile(rf'\b{card_name_escaped}\b', re.IGNORECASE)
        
        if card_name_pattern.search(text_lower):
            # Make sure it's in a self-ability context
            self_context_patterns = [
                re.compile(rf'\b{card_name_escaped}\s+(?:has|gains?)\s+{ability_lower}', re.IGNORECASE),
                re.compile(rf'\b{card_name_escaped}\s+is\s+{ability_lower}', re.IGNORECASE),
            ]
            
            for pattern in self_context_patterns:
                if pattern.search(text_lower):
                    return True
    
    return False


def _has_grant_verbs(text_lower: str) -> bool:
    """
    Check if text contains grant verb patterns.
    
    Used to distinguish inherent abilities from granted abilities.
    
    Args:
        text_lower: Lowercase card text
        
    Returns:
        True if grant verbs found
    """
    grant_patterns = [
        re.compile(r'(?:have|gain|grant|give|get)[s]?\s+', re.IGNORECASE),
        rgx.OTHER_CREATURES,
        rgx.CREATURE_YOU_CONTROL,
        rgx.PERMANENT_YOU_CONTROL,
        rgx.EQUIPPED_CREATURE,
        rgx.ENCHANTED_CREATURE,
        rgx.TARGET_CREATURE,
    ]
    
    return any(pattern.search(text_lower) for pattern in grant_patterns)


def format_scope_tag(scope: str, ability: str) -> str:
    """
    Format a scope and ability into a metadata tag.
    
    Args:
        scope: Scope string (e.g., "Self", "Your Permanents")
        ability: Ability name (e.g., "Hexproof", "Phasing")
        
    Returns:
        Formatted tag string (e.g., "Self: Hexproof")
    """
    return f"{scope}: {ability}"


def has_keyword(text: str, keywords: List[str]) -> bool:
    """
    Quick check if card text contains any of the specified keywords.
    
    Args:
        text: Card text
        keywords: List of keywords to search for
        
    Returns:
        True if any keyword found
    """
    if not text:
        return False
    
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def check_static_keyword(
    ability_keyword: str,
    keywords: Optional[str] = None,
    text: Optional[str] = None
) -> bool:
    """
    Check if card has ability as a static keyword (not granted to others).
    
    A static keyword is one that appears:
    1. In the keywords field, OR
    2. As a simple comma-separated list without grant verbs
       (e.g., "Flying, first strike, protection from black")
    
    Args:
        ability_keyword: Ability to check (e.g., "Protection", "Hexproof")
        keywords: Optional keywords field from card data
        text: Optional card text for fallback detection
        
    Returns:
        True if ability appears as static keyword
    """
    ability_lower = ability_keyword.lower()
    
    # Check keywords field first (most reliable)
    if keywords:
        keywords_lower = keywords.lower()
        if ability_lower in keywords_lower:
            return True
    
    # Fallback: Check if ability appears in simple comma-separated keyword list
    # Pattern: starts with keywords (Flying, First strike, etc.) without grant verbs
    # Example: "Flying, first strike, vigilance, trample, haste, protection from black"
    if text:
        text_lower = text.lower()
        
        # Check if ability appears in text but WITHOUT grant verbs
        if ability_lower in text_lower:
            # Look for grant verbs that would indicate this is NOT a static keyword
            grant_verbs = ['have', 'has', 'gain', 'gains', 'get', 'gets', 'grant', 'grants', 'give', 'gives']
            
            # Find the position of the ability in text
            ability_pos = text_lower.find(ability_lower)
            
            # Check the 50 characters before the ability for grant verbs
            # This catches patterns like "creatures gain protection" or "has hexproof"
            context_before = text_lower[max(0, ability_pos - 50):ability_pos]
            
            # If no grant verbs found nearby, it's likely a static keyword
            if not any(verb in context_before for verb in grant_verbs):
                # Additional check: is it part of a comma-separated list?
                # This helps with "Flying, first strike, protection from X" patterns
                context_before_30 = text_lower[max(0, ability_pos - 30):ability_pos]
                if ',' in context_before_30 or ability_pos < 10:
                    return True
    
    return False


def check_static_keyword_legacy(
    keywords: str,
    static_keyword: str,
    text: str,
    grant_patterns: Optional[List[re.Pattern]] = None
) -> bool:
    """
    LEGACY: Check if card has static keyword without granting it to others.
    
    Used for abilities like "Phasing" that can be both static and granted.
    
    Args:
        keywords: Card keywords field
        static_keyword: Keyword to search for (e.g., "phasing")
        text: Card text
        grant_patterns: Optional patterns to check for granting language
        
    Returns:
        True if static keyword found and not granted to others
    """
    if not keywords:
        return False
    
    keywords_lower = keywords.lower()
    
    if static_keyword.lower() not in keywords_lower:
        return False
    
    # If grant patterns provided, check if card grants to others
    if grant_patterns:
        text_no_reminder = tag_utils.strip_reminder_text(text.lower()) if text else ''
        grants_to_others = any(pattern.search(text_no_reminder) for pattern in grant_patterns)
        
        # Only return True if NOT granting to others
        return not grants_to_others
    
    return True
