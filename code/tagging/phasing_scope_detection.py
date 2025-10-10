"""
Phasing Scope Detection Module

Detects the scope of phasing effects with multiple dimensions:
- Targeted: Phasing (any targeting effect)
- Self: Phasing (phases itself out)
- Your Permanents: Phasing (phases your permanents out)
- Opponent Permanents: Phasing (phases opponent permanents - removal)
- Blanket: Phasing (phases all permanents out)

Cards can have multiple scope tags (e.g., Targeted + Your Permanents).
"""

import re
from typing import Set
from code.logging_util import get_logger

logger = get_logger(__name__)


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
        # Remove reminder text to avoid false positives
        text_no_reminder = re.sub(r'\([^)]*\)', '', text_lower)
        
        # Check if card grants phasing to others (has granting language in main text)
        # Look for patterns like "enchanted creature has", "other X have", "target", etc.
        grants_to_others = bool(re.search(
            r'(other|target|each|all|enchanted|equipped|creatures? you control|permanents? you control).*phas',
            text_no_reminder
        ))
        
        # If no granting language, it's just self-phasing
        if not grants_to_others:
            tags.add('Self: Phasing')
            return tags  # Early return - static keyword only
    
    # Check if phasing is mentioned in text (including "has phasing", "gain phasing", etc.)
    if 'phas' not in text_lower:  # Changed from 'phase' to 'phas' to catch "phasing" too
        return tags
    
    # Check for targeting (any "target" + phasing)
    # Targeting detection - must have target AND phase in same sentence/clause
    targeting_patterns = [
        r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?(?:[^.]*)?phases?\s+out',
        r'target\s+player\s+controls[^.]*phases?\s+out',
    ]
    
    is_targeted = any(re.search(pattern, text_lower) for pattern in targeting_patterns)
    
    if is_targeted:
        tags.add("Targeted: Phasing")
        logger.debug(f"Card '{card_name}': detected Targeted: Phasing")
    
    # Check for self-phasing
    self_patterns = [
        r'this\s+(?:creature|permanent|artifact|enchantment)\s+phases?\s+out',
        r'~\s+phases?\s+out',
        rf'\b{re.escape(card_name.lower())}\s+phases?\s+out',
        # NEW: Triggered self-phasing (King of the Oathbreakers: "it phases out" as reactive protection)
        r'whenever.*(?:becomes\s+the\s+target|becomes\s+target).*(?:it|this\s+creature)\s+phases?\s+out',
        # NEW: Consequent self-phasing (Cyclonus: "connive. Then...phase out")
        r'(?:then|,)\s+(?:it|this\s+creature)\s+phases?\s+out',
        # NEW: At end of turn/combat self-phasing
        r'(?:at\s+(?:the\s+)?end\s+of|after).*(?:it|this\s+creature)\s+phases?\s+out',
    ]
    
    if any(re.search(pattern, text_lower) for pattern in self_patterns):
        tags.add("Self: Phasing")
        logger.debug(f"Card '{card_name}': detected Self: Phasing")
    
    # Check for opponent permanent phasing (removal effect)
    opponent_patterns = [
        r'target\s+(?:\w+\s+)*(?:creature|permanent)\s+an?\s+opponents?\s+controls?\s+phases?\s+out',
    ]
    
    # Check for unqualified targets (can target opponents' stuff)
    # More flexible to handle various phasing patterns
    unqualified_target_patterns = [
        r'(?:up\s+to\s+)?(?:one\s+|x\s+|that\s+many\s+)?(?:other\s+)?(?:another\s+)?target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?(?:[^.]*)?phases?\s+out',
        r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|land|nonland\s+permanent)(?:,|\s+and)?\s+(?:then|and)?\s+it\s+phases?\s+out',
    ]
    
    has_opponent_specific = any(re.search(pattern, text_lower) for pattern in opponent_patterns)
    has_unqualified_target = any(re.search(pattern, text_lower) for pattern in unqualified_target_patterns)
    
    # If unqualified AND not restricted to "you control", can target opponents
    if has_opponent_specific or (has_unqualified_target and 'you control' not in text_lower):
        tags.add("Opponent Permanents: Phasing")
        logger.debug(f"Card '{card_name}': detected Opponent Permanents: Phasing")
    
    # Check for your permanents phasing
    your_patterns = [
        # Explicit "you control"
        r'(?:target\s+)?(?:creatures?|permanents?|nonland\s+permanents?)\s+you\s+control\s+phases?\s+out',
        r'(?:target\s+)?(?:other\s+)?(?:creatures?|permanents?)\s+you\s+control\s+phases?\s+out',
        r'permanents?\s+you\s+control\s+phase\s+out',
        r'(?:any|up\s+to)\s+(?:number\s+of\s+)?(?:target\s+)?(?:other\s+)?(?:creatures?|permanents?|nonland\s+permanents?)\s+you\s+control\s+phases?\s+out',
        r'all\s+(?:creatures?|permanents?)\s+you\s+control\s+phase\s+out',
        r'each\s+(?:creature|permanent)\s+you\s+control\s+phases?\s+out',
        # Pronoun reference to "you control" context
        r'(?:creatures?|permanents?|planeswalkers?)\s+you\s+control[^.]*(?:those|the)\s+(?:creatures?|permanents?|planeswalkers?)\s+phase\s+out',
        r'creature\s+you\s+control[^.]*(?:it)\s+phases?\s+out',
        # "Those permanents" referring back to controlled permanents (across sentence boundaries)
        r'you\s+control.*those\s+(?:creatures?|permanents?|planeswalkers?)\s+phase\s+out',
        # Equipment/Aura (beneficial to your permanents)
        r'equipped\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?phases?\s+out',
        r'enchanted\s+(?:creature|permanent)\s+(?:gets\s+[^.]*\s+and\s+)?phases?\s+out',
        r'enchanted\s+(?:creature|permanent)\s+(?:has|gains?)\s+phasing',  # NEW: "has phasing" for Cloak of Invisibility, Teferi's Curse
        # Pronoun reference after equipped/enchanted creature mentioned
        r'(?:equipped|enchanted)\s+(?:creature|permanent)[^.]*,?\s+(?:then\s+)?that\s+(?:creature|permanent)\s+phases?\s+out',
        # Target controlled by specific player
        r'(?:each|target)\s+(?:creature|permanent)\s+target\s+player\s+controls\s+phases?\s+out',
    ]
    
    if any(re.search(pattern, text_lower) for pattern in your_patterns):
        tags.add("Your Permanents: Phasing")
        logger.debug(f"Card '{card_name}': detected Your Permanents: Phasing")
    
    # Check for blanket phasing (all permanents, no ownership)
    blanket_patterns = [
        r'all\s+(?:nontoken\s+)?(?:creatures?|permanents?)(?:\s+of\s+that\s+type)?\s+(?:[^.]*\s+)?phase\s+out',
        r'each\s+(?:creature|permanent)\s+(?:[^.]*\s+)?phases?\s+out',
        # NEW: Type-specific blanket (Shimmer: "Each land of the chosen type has phasing")
        r'each\s+(?:land|creature|permanent|artifact|enchantment)\s+of\s+the\s+chosen\s+type\s+has\s+phasing',
        r'(?:lands?|creatures?|permanents?|artifacts?|enchantments?)\s+of\s+the\s+chosen\s+type\s+(?:have|has)\s+phasing',
        # Pronoun reference to "all creatures"
        r'all\s+(?:nontoken\s+)?(?:creatures?|permanents?)[^.]*,?\s+(?:then\s+)?(?:those|the)\s+(?:creatures?|permanents?)\s+phase\s+out',
    ]
    
    # Only blanket if no specific ownership mentioned
    has_blanket_pattern = any(re.search(pattern, text_lower) for pattern in blanket_patterns)
    no_ownership = 'you control' not in text_lower and 'target player controls' not in text_lower and 'opponent' not in text_lower
    
    if has_blanket_pattern and no_ownership:
        tags.add("Blanket: Phasing")
        logger.debug(f"Card '{card_name}': detected Blanket: Phasing")
    
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
