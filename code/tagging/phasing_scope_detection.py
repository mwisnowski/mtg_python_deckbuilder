"""
Phasing Scope Detection Module

Detects the scope of phasing effects with multiple dimensions:
- Targeted: Phasing (any targeting effect)
- Self: Phasing (phases itself out)
- Your Permanents: Phasing (phases your permanents out)
- Opponent Permanents: Phasing (phases opponent permanents - removal)
- Blanket: Phasing (phases all permanents out)

Cards can have multiple scope tags (e.g., Targeted + Your Permanents).

Refactored in M2: Create Scope Detection Utilities to use generic scope detection.
"""

# Standard library imports
import re
from typing import Set

# Local application imports
from . import scope_detection_utils as scope_utils
from code.logging_util import get_logger

logger = get_logger(__name__)


# Phasing scope pattern definitions
def _get_phasing_scope_patterns() -> scope_utils.ScopePatterns:
    """
    Build scope patterns for phasing abilities.
    
    Returns:
        ScopePatterns object with compiled patterns
    """
    # Targeting patterns (special for phasing - detects "target...phases out")
    targeting_patterns = [
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?(?:[^.]*)?phases?\s+out', re.IGNORECASE),
        re.compile(r'target\s+player\s+controls[^.]*phases?\s+out', re.IGNORECASE),
    ]
    
    # Self-reference patterns
    self_patterns = [
        re.compile(r'this\s+(?:creature|permanent|artifact|enchantment)\s+phases?\s+out', re.IGNORECASE),
        re.compile(r'~\s+phases?\s+out', re.IGNORECASE),
        # Triggered self-phasing (King of the Oathbreakers)
        re.compile(r'whenever.*(?:becomes\s+the\s+target|becomes\s+target).*(?:it|this\s+creature)\s+phases?\s+out', re.IGNORECASE),
        # Consequent self-phasing (Cyclonus: "connive. Then...phase out")
        re.compile(r'(?:then|,)\s+(?:it|this\s+creature)\s+phases?\s+out', re.IGNORECASE),
        # At end of turn/combat self-phasing
        re.compile(r'(?:at\s+(?:the\s+)?end\s+of|after).*(?:it|this\s+creature)\s+phases?\s+out', re.IGNORECASE),
    ]
    
    # Opponent patterns
    opponent_patterns = [
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent)\s+an?\s+opponents?\s+controls?\s+phases?\s+out', re.IGNORECASE),
        # Unqualified targets (can target opponents' stuff if no "you control" restriction)
        re.compile(r'(?:up\s+to\s+)?(?:one\s+|x\s+|that\s+many\s+)?(?:other\s+)?(?:another\s+)?target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?(?:[^.]*)?phases?\s+out', re.IGNORECASE),
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|land|nonland\s+permanent)(?:,|\s+and)?\s+(?:then|and)?\s+it\s+phases?\s+out', re.IGNORECASE),
    ]
    
    # Your permanents patterns
    your_patterns = [
        # Explicit "you control"
        re.compile(r'(?:target\s+)?(?:creatures?|permanents?|nonland\s+permanents?)\s+you\s+control\s+phases?\s+out', re.IGNORECASE),
        re.compile(r'(?:target\s+)?(?:other\s+)?(?:creatures?|permanents?)\s+you\s+control\s+phases?\s+out', re.IGNORECASE),
        re.compile(r'permanents?\s+you\s+control\s+phase\s+out', re.IGNORECASE),
        re.compile(r'(?:any|up\s+to)\s+(?:number\s+of\s+)?(?:target\s+)?(?:other\s+)?(?:creatures?|permanents?|nonland\s+permanents?)\s+you\s+control\s+phases?\s+out', re.IGNORECASE),
        re.compile(r'all\s+(?:creatures?|permanents?)\s+you\s+control\s+phase\s+out', re.IGNORECASE),
        re.compile(r'each\s+(?:creature|permanent)\s+you\s+control\s+phases?\s+out', re.IGNORECASE),
        # Pronoun reference to "you control" context
        re.compile(r'(?:creatures?|permanents?|planeswalkers?)\s+you\s+control[^.]*(?:those|the)\s+(?:creatures?|permanents?|planeswalkers?)\s+phase\s+out', re.IGNORECASE),
        re.compile(r'creature\s+you\s+control[^.]*(?:it)\s+phases?\s+out', re.IGNORECASE),
        re.compile(r'you\s+control.*those\s+(?:creatures?|permanents?|planeswalkers?)\s+phase\s+out', re.IGNORECASE),
        # Equipment/Aura
        re.compile(r'equipped\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?phases?\s+out', re.IGNORECASE),
        re.compile(r'enchanted\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?phases?\s+out', re.IGNORECASE),
        re.compile(r'enchanted\s+(?:creature|permanent)\s+(?:has|gains?)\s+phasing', re.IGNORECASE),
        re.compile(r'(?:equipped|enchanted)\s+(?:creature|permanent)[^.]*,?\s+(?:then\s+)?that\s+(?:creature|permanent)\s+phases?\s+out', re.IGNORECASE),
        # Target controlled by specific player
        re.compile(r'(?:each|target)\s+(?:creature|permanent)\s+target\s+player\s+controls\s+phases?\s+out', re.IGNORECASE),
    ]
    
    # Blanket patterns
    blanket_patterns = [
        re.compile(r'all\s+(?:nontoken\s+)?(?:creatures?|permanents?)(?:\s+of\s+that\s+type)?\s+(?:[^.]*\s+)?phase\s+out', re.IGNORECASE),
        re.compile(r'each\s+(?:creature|permanent)\s+(?:[^.]*\s+)?phases?\s+out', re.IGNORECASE),
        # Type-specific blanket (Shimmer)
        re.compile(r'each\s+(?:land|creature|permanent|artifact|enchantment)\s+of\s+the\s+chosen\s+type\s+has\s+phasing', re.IGNORECASE),
        re.compile(r'(?:lands?|creatures?|permanents?|artifacts?|enchantments?)\s+of\s+the\s+chosen\s+type\s+(?:have|has)\s+phasing', re.IGNORECASE),
        # Pronoun reference to "all creatures"
        re.compile(r'all\s+(?:nontoken\s+)?(?:creatures?|permanents?)[^.]*,?\s+(?:then\s+)?(?:those|the)\s+(?:creatures?|permanents?)\s+phase\s+out', re.IGNORECASE),
    ]
    
    return scope_utils.ScopePatterns(
        opponent=opponent_patterns,
        self_ref=self_patterns,
        your_permanents=your_patterns,
        blanket=blanket_patterns,
        targeted=targeting_patterns
    )


def get_phasing_scope_tags(text: str, card_name: str, keywords: str = '') -> Set[str]:
    """
    Get all phasing scope metadata tags for a card.
    
    A card can have multiple scope tags:
    - "Targeted: Phasing" - Uses targeting
    - "Self: Phasing" - Phases itself out
    - "Your Permanents: Phasing" - Phases your permanents
    - "Opponent Permanents: Phasing" - Phases opponent permanents (removal)
    - "Blanket: Phasing" - Phases all permanents
    
    Args:
        text: Card text
        card_name: Card name
        keywords: Card keywords (to check for static "Phasing" ability)
        
    Returns:
        Set of metadata tags
    """
    if not card_name:
        return set()
    
    text_lower = text.lower() if text else ''
    keywords_lower = keywords.lower() if keywords else ''
    tags = set()
    
    # Check for static "Phasing" keyword ability (self-phasing)
    # Only add Self tag if card doesn't grant phasing to others
    if 'phasing' in keywords_lower:
        # Define patterns for checking if card grants phasing to others
        grants_pattern = [re.compile(
            r'(other|target|each|all|enchanted|equipped|creatures? you control|permanents? you control).*phas',
            re.IGNORECASE
        )]
        
        is_static = scope_utils.check_static_keyword_legacy(
            keywords=keywords,
            static_keyword='phasing',
            text=text,
            grant_patterns=grants_pattern
        )
        
        if is_static:
            tags.add('Self: Phasing')
            return tags  # Early return - static keyword only
    
    # Check if phasing is mentioned in text
    if 'phas' not in text_lower:
        return tags
    
    # Build phasing patterns and detect scopes
    patterns = _get_phasing_scope_patterns()
    
    # Detect all scopes (phasing can have multiple)
    scopes = scope_utils.detect_multi_scope(
        text=text,
        card_name=card_name,
        ability_keyword='phas',  # Use 'phas' to catch both 'phase' and 'phasing'
        patterns=patterns,
        check_grant_verbs=False  # Phasing doesn't need grant verb checking
    )
    
    # Format scope tags with "Phasing" ability name
    for scope in scopes:
        if scope == "Targeted":
            tags.add("Targeted: Phasing")
        else:
            tags.add(scope_utils.format_scope_tag(scope, "Phasing"))
        logger.debug(f"Card '{card_name}': detected {scope}: Phasing")
    
    return tags


def has_phasing(text: str) -> bool:
    """
    Quick check if card text contains phasing keywords.
    
    Args:
        text: Card text
        
    Returns:
        True if phasing keyword found
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Check for phasing keywords
    phasing_keywords = [
        'phase out',
        'phases out',
        'phasing',
        'phase in',
        'phases in',
    ]
    
    return any(keyword in text_lower for keyword in phasing_keywords)


def is_removal_phasing(tags: Set[str]) -> bool:
    """
    Check if phasing effect acts as removal (targets opponent permanents).
    
    Args:
        tags: Set of phasing scope tags
        
    Returns:
        True if this is removal-style phasing
    """
    return "Opponent Permanents: Phasing" in tags
