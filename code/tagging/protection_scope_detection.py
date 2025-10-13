"""
Protection Scope Detection Module

Detects the scope of protection effects (Self, Your Permanents, Blanket, Opponent Permanents)
to enable intelligent filtering in deck building.

Part of M5: Protection Effect Granularity milestone.
Refactored in M2: Create Scope Detection Utilities to use generic scope detection.
"""

# Standard library imports
import re
from typing import Optional, Set

# Local application imports
from code.logging_util import get_logger
from . import scope_detection_utils as scope_utils
from .tag_constants import PROTECTION_ABILITIES

logger = get_logger(__name__)


# Protection scope pattern definitions
def _get_protection_scope_patterns(ability: str) -> scope_utils.ScopePatterns:
    """
    Build scope patterns for protection abilities.
    
    Args:
        ability: Ability keyword (e.g., "hexproof", "ward")
        
    Returns:
        ScopePatterns object with compiled patterns
    """
    ability_lower = ability.lower()
    
    # Opponent patterns: grants protection TO opponent's permanents
    # Note: Must distinguish from hexproof reminder text "opponents control [spells/abilities]"
    opponent_patterns = [
        re.compile(r'creatures?\s+(?:your\s+)?opponents?\s+control\s+(?:have|gain)', re.IGNORECASE),
        re.compile(r'permanents?\s+(?:your\s+)?opponents?\s+control\s+(?:have|gain)', re.IGNORECASE),
        re.compile(r'each\s+creature\s+an?\s+opponent\s+controls?\s+(?:has|gains?)', re.IGNORECASE),
    ]
    
    # Self-reference patterns
    self_patterns = [
        # Tilde (~) - strong self-reference indicator
        re.compile(r'~\s+(?:has|gains?)\s+' + ability_lower, re.IGNORECASE),
        re.compile(r'~\s+is\s+' + ability_lower, re.IGNORECASE),
        # "this creature/permanent" pronouns
        re.compile(r'this\s+(?:creature|permanent|artifact|enchantment)\s+(?:has|gains?)\s+' + ability_lower, re.IGNORECASE),
        # Starts with ability (likely self)
        re.compile(r'^(?:has|gains?)\s+' + ability_lower, re.IGNORECASE),
    ]
    
    # Your permanents patterns
    your_patterns = [
        re.compile(r'(?:other\s+)?(?:creatures?|permanents?|artifacts?|enchantments?)\s+you\s+control', re.IGNORECASE),
        re.compile(r'your\s+(?:creatures?|permanents?|artifacts?|enchantments?)', re.IGNORECASE),
        re.compile(r'each\s+(?:creature|permanent)\s+you\s+control', re.IGNORECASE),
        re.compile(r'other\s+\w+s?\s+you\s+control', re.IGNORECASE),  # "Other Merfolk you control", etc.
        # "Other X you control...have Y" pattern for static grants
        re.compile(r'other\s+(?:\w+\s+)?(?:creatures?|permanents?)\s+you\s+control\s+(?:get\s+[^.]*\s+and\s+)?have\s+' + ability_lower, re.IGNORECASE),
        re.compile(r'other\s+\w+s?\s+you\s+control\s+(?:get\s+[^.]*\s+and\s+)?have\s+' + ability_lower, re.IGNORECASE),  # "Other Knights you control...have"
        re.compile(r'equipped\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower, re.IGNORECASE),  # Equipment
        re.compile(r'enchanted\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower, re.IGNORECASE),  # Aura
        re.compile(r'target\s+(?:\w+\s+)?(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:gains?)\s+' + ability_lower, re.IGNORECASE),  # Target
    ]
    
    # Blanket patterns (no ownership qualifier)
    # Note: Abilities can be listed with "and" (e.g., "gain hexproof and indestructible")
    blanket_patterns = [
        re.compile(r'all\s+(?:creatures?|permanents?)\s+(?:have|gain)\s+(?:[^.]*\s+and\s+)?' + ability_lower, re.IGNORECASE),
        re.compile(r'each\s+(?:creature|permanent)\s+(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower, re.IGNORECASE),
        re.compile(r'(?:creatures?|permanents?)\s+(?:have|gain)\s+(?:[^.]*\s+and\s+)?' + ability_lower, re.IGNORECASE),
    ]
    
    return scope_utils.ScopePatterns(
        opponent=opponent_patterns,
        self_ref=self_patterns,
        your_permanents=your_patterns,
        blanket=blanket_patterns
    )


def detect_protection_scope(text: str, card_name: str, ability: str, keywords: Optional[str] = None) -> Optional[str]:
    """
    Detect the scope of a protection effect.
    
    Detection priority order (prevents misclassification):
    0. Static keyword → "Self"
    1. Opponent ownership → "Opponent Permanents"
    2. Self-reference → "Self"
    3. Your ownership → "Your Permanents"
    4. No ownership qualifier → "Blanket"
    
    Args:
        text: Card text (lowercase for pattern matching)
        card_name: Card name (for self-reference detection)
        ability: Ability type (Ward, Hexproof, etc.)
        keywords: Optional keywords field for static keyword detection
        
    Returns:
        Scope prefix or None: "Self", "Your Permanents", "Blanket", "Opponent Permanents"
    """
    if not text or not ability:
        return None
    
    # Build patterns for this ability
    patterns = _get_protection_scope_patterns(ability)
    
    # Use generic scope detection with grant verb checking AND keywords
    return scope_utils.detect_scope(
        text=text,
        card_name=card_name,
        ability_keyword=ability,
        patterns=patterns,
        allow_multiple=False,
        check_grant_verbs=True,
        keywords=keywords
    )


def get_protection_scope_tags(text: str, card_name: str, keywords: Optional[str] = None) -> Set[str]:
    """
    Get all protection scope metadata tags for a card.
    
    A card can have multiple protection scopes (e.g., self-hexproof + grants ward to others).
    
    Args:
        text: Card text
        card_name: Card name
        keywords: Optional keywords field for static keyword detection
        
    Returns:
        Set of metadata tags like {"Self: Indestructible", "Your Permanents: Ward"}
    """
    if not text or not card_name:
        return set()
    
    scope_tags = set()
    
    # Check each protection ability
    for ability in PROTECTION_ABILITIES:
        scope = detect_protection_scope(text, card_name, ability, keywords)
        
        if scope:
            # Format: "{Scope}: {Ability}"
            tag = f"{scope}: {ability}"
            scope_tags.add(tag)
            logger.debug(f"Card '{card_name}': detected scope tag '{tag}'")
    
    return scope_tags


def has_any_protection(text: str) -> bool:
    """
    Quick check if card text contains any protection keywords.
    
    Args:
        text: Card text
        
    Returns:
        True if any protection keyword found
    """
    if not text:
        return False
    
    text_lower = text.lower()
    return any(ability.lower() in text_lower for ability in PROTECTION_ABILITIES)
