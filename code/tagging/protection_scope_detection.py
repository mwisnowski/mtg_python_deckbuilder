"""
Protection Scope Detection Module

Detects the scope of protection effects (Self, Your Permanents, Blanket, Opponent Permanents)
to enable intelligent filtering in deck building.

Part of M5: Protection Effect Granularity milestone.
"""

import re
from typing import Optional, Set
from code.logging_util import get_logger

logger = get_logger(__name__)


# Protection abilities to detect
PROTECTION_ABILITIES = [
    'Protection',
    'Ward',
    'Hexproof',
    'Shroud',
    'Indestructible'
]


def detect_protection_scope(text: str, card_name: str, ability: str) -> Optional[str]:
    """
    Detect the scope of a protection effect.
    
    Detection priority order (prevents misclassification):
    1. Opponent ownership → "Opponent Permanents"
    2. Your ownership → "Your Permanents"
    3. Self-reference → "Self"
    4. No ownership qualifier → "Blanket"
    
    Args:
        text: Card text (lowercase for pattern matching)
        card_name: Card name (for self-reference detection)
        ability: Ability type (Ward, Hexproof, etc.)
        
    Returns:
        Scope prefix or None: "Self", "Your Permanents", "Blanket", "Opponent Permanents"
    """
    if not text or not ability:
        return None
    
    text_lower = text.lower()
    ability_lower = ability.lower()
    card_name_lower = card_name.lower()
    
    # Check if ability is mentioned in text
    if ability_lower not in text_lower:
        return None
    
    # Priority 1: Opponent ownership (grants protection TO opponent's permanents)
    # Note: Must distinguish from hexproof reminder text "opponents control [spells/abilities]"
    # Only match when "opponents control" refers to creatures/permanents, not spells
    opponent_patterns = [
        r'creatures?\s+(?:your\s+)?opponents?\s+control\s+(?:have|gain)',
        r'permanents?\s+(?:your\s+)?opponents?\s+control\s+(?:have|gain)',
        r'each\s+creature\s+an?\s+opponent\s+controls?\s+(?:has|gains?)'
    ]
    
    for pattern in opponent_patterns:
        if re.search(pattern, text_lower):
            return "Opponent Permanents"
    
    # Priority 2: Check for self-reference BEFORE "Your Permanents"
    # This prevents tilde (~) from being caught by creature type patterns
    
    # Check for tilde (~) - strong self-reference indicator
    tilde_patterns = [
        r'~\s+(?:has|gains?)\s+' + ability_lower,
        r'~\s+is\s+' + ability_lower
    ]
    
    for pattern in tilde_patterns:
        if re.search(pattern, text_lower):
            return "Self"
    
    # Check for "this creature/permanent" pronouns
    this_patterns = [
        r'this\s+(?:creature|permanent|artifact|enchantment)\s+(?:has|gains?)\s+' + ability_lower,
        r'^(?:has|gains?)\s+' + ability_lower  # Starts with ability (likely self)
    ]
    
    for pattern in this_patterns:
        if re.search(pattern, text_lower):
            return "Self"
    
    # Check for card name (replace special characters for matching)
    card_name_escaped = re.escape(card_name_lower)
    if re.search(rf'\b{card_name_escaped}\b', text_lower):
        # Make sure it's in a self-protection context
        # e.g., "Svyelun has indestructible" not "Svyelun and other Merfolk"
        self_context_patterns = [
            rf'\b{card_name_escaped}\s+(?:has|gains?)\s+{ability_lower}',
            rf'\b{card_name_escaped}\s+is\s+{ability_lower}'
        ]
        for pattern in self_context_patterns:
            if re.search(pattern, text_lower):
                return "Self"
    
    # NEW: If no grant patterns found at all, assume inherent protection (Self)
    # This catches cards where protection is in the keywords field but not explained in text
    # e.g., "Protection from creatures" as a keyword line
    # Check if we have the ability keyword but no grant patterns
    has_grant_pattern = any(re.search(pattern, text_lower) for pattern in [
        r'(?:have|gain|grant|give|get)[s]?\s+',
        r'other\s+',
        r'creatures?\s+you\s+control',
        r'permanents?\s+you\s+control',
        r'equipped',
        r'enchanted',
        r'target'
    ])
    
    if not has_grant_pattern:
        # No grant verbs found - likely inherent protection
        return "Self"
    
    # Priority 3: Your ownership (most common)
    # Note: "Other [Type]" patterns included for type-specific grants
    # Note: "equipped creature", "target creature", etc. are permanents you control
    your_patterns = [
        r'(?:other\s+)?(?:creatures?|permanents?|artifacts?|enchantments?)\s+you\s+control',
        r'your\s+(?:creatures?|permanents?|artifacts?|enchantments?)',
        r'each\s+(?:creature|permanent)\s+you\s+control',
        r'other\s+\w+s?\s+you\s+control',  # "Other Merfolk you control", etc.
        # NEW: "Other X you control...have Y" pattern for static grants
        r'other\s+(?:\w+\s+)?(?:creatures?|permanents?)\s+you\s+control\s+(?:get\s+[^.]*\s+and\s+)?have\s+' + ability_lower,
        r'other\s+\w+s?\s+you\s+control\s+(?:get\s+[^.]*\s+and\s+)?have\s+' + ability_lower,  # "Other Knights you control...have"
        r'equipped\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower,  # Equipment
        r'enchanted\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower,  # Aura
        r'target\s+(?:\w+\s+)?(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?(?:gains?)\s+' + ability_lower  # Target (with optional adjective)
    ]
    
    for pattern in your_patterns:
        if re.search(pattern, text_lower):
            return "Your Permanents"
    
    # Priority 4: Blanket (no ownership qualifier)
    # Only apply if we have protection keyword but no ownership context
    # Note: Abilities can be listed with "and" (e.g., "gain hexproof and indestructible")
    blanket_patterns = [
        r'all\s+(?:creatures?|permanents?)\s+(?:have|gain)\s+(?:[^.]*\s+and\s+)?' + ability_lower,
        r'each\s+(?:creature|permanent)\s+(?:has|gains?)\s+(?:[^.]*\s+and\s+)?' + ability_lower,
        r'(?:creatures?|permanents?)\s+(?:have|gain)\s+(?:[^.]*\s+and\s+)?' + ability_lower
    ]
    
    for pattern in blanket_patterns:
        if re.search(pattern, text_lower):
            # Double-check no ownership was missed
            if 'you control' not in text_lower and 'opponent' not in text_lower:
                return "Blanket"
    
    return None


def get_protection_scope_tags(text: str, card_name: str) -> Set[str]:
    """
    Get all protection scope metadata tags for a card.
    
    A card can have multiple protection scopes (e.g., self-hexproof + grants ward to others).
    
    Args:
        text: Card text
        card_name: Card name
        
    Returns:
        Set of metadata tags like {"Self: Indestructible", "Your Permanents: Ward"}
    """
    if not text or not card_name:
        return set()
    
    scope_tags = set()
    
    # Check each protection ability
    for ability in PROTECTION_ABILITIES:
        scope = detect_protection_scope(text, card_name, ability)
        
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
