"""
Protection grant detection implementation for M2.

This module provides helpers to distinguish cards that grant protection effects
from cards that have inherent protection effects.

Usage in tagger.py:
    from code.tagging.protection_grant_detection import is_granting_protection
    
    if is_granting_protection(text, keywords):
        # Tag as Protection
"""

import re
from typing import Set, List, Pattern

from code.tagging.tag_constants import CREATURE_TYPES


# Pre-compile kindred detection patterns at module load for performance
# Pattern: (compiled_regex, tag_name_template)
KINDRED_PATTERNS: List[tuple[Pattern, str]] = []

def _init_kindred_patterns():
    """Initialize pre-compiled kindred patterns for all creature types."""
    global KINDRED_PATTERNS
    if KINDRED_PATTERNS:
        return  # Already initialized
    
    for creature_type in CREATURE_TYPES:
        creature_lower = creature_type.lower()
        creature_escaped = re.escape(creature_lower)
        tag_name = f"{creature_type}s Gain Protection"
        
        # Create 3 patterns per type
        patterns_to_compile = [
            (rf'\bother {creature_escaped}s?\b.*\b(have|gain)\b', tag_name),
            (rf'\b{creature_escaped} creatures?\b.*\b(have|gain)\b', tag_name),
            (rf'\btarget {creature_escaped}\b.*\bgains?\b', tag_name),
        ]
        
        for pattern_str, tag in patterns_to_compile:
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                KINDRED_PATTERNS.append((compiled, tag))
            except re.error:
                # Skip patterns that fail to compile
                pass


# Grant verb patterns - cards that give protection to other permanents
# These patterns look for grant verbs that affect OTHER permanents, not self
# M5: Added phasing support
GRANT_VERB_PATTERNS = [
    r'\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',
    r'\bgive[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',
    r'\bgrant[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',
    r'\bhave\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',  # "have hexproof" static grants
    r'\bget[s]?\b.*\+.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',  # "gets +X/+X and has hexproof" direct
    r'\bget[s]?\b.*\+.*\band\b.*\b(gain[s]?|have)\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b',  # "gets +X/+X and gains hexproof"
    r'\bphases? out\b',  # M5: Direct phasing triggers (e.g., "it phases out")
]

# Self-reference patterns that should NOT count as granting
# Reminder text and keyword lines only
# M5: Added phasing support
SELF_REFERENCE_PATTERNS = [
    r'^\s*(hexproof|shroud|indestructible|ward|protection|phasing)',  # Start of text (keyword ability)
    r'\([^)]*\b(hexproof|shroud|indestructible|ward|protection|phasing)[^)]*\)',  # Reminder text in parens
]

# Conditional self-grant patterns - activated/triggered abilities that grant to self
CONDITIONAL_SELF_GRANT_PATTERNS = [
    # Activated abilities
    r'\{[^}]*\}.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    r'discard.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b',
    r'\{t\}.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b',
    r'sacrifice.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b',
    r'pay.*life.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b',
    # Triggered abilities that grant to self only
    r'whenever.*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    r'whenever you (cast|play|attack|cycle|discard|commit).*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    r'at the beginning.*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    r'whenever.*\b(this creature|this permanent)\b (attacks|enters|becomes).*\b(this creature|this permanent|it)\b.*\bgain[s]?\b',
    # Named self-references (e.g., "Pristine Skywise gains")
    r'whenever you cast.*[A-Z][a-z]+.*gains.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    r'whenever you.*[A-Z][a-z]+.*gains.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    # Static conditional abilities (as long as, if you control X)
    r'as long as.*\b(this creature|this permanent|it|has)\b.*(has|gains?).*\b(hexproof|shroud|indestructible|ward|protection)\b',
]

# Mass grant patterns - affects multiple creatures YOU control
MASS_GRANT_PATTERNS = [
    r'creatures you control (have|gain|get)',
    r'other .* you control (have|gain|get)',
    r'(artifacts?|enchantments?|permanents?) you control (have|gain|get)',  # Artifacts you control have...
    r'other (creatures?|artifacts?|enchantments?) (have|gain|get)',  # Other creatures have...
    r'all (creatures?|slivers?|permanents?) (have|gain|get)',  # All creatures/slivers have...
]

# Targeted grant patterns - must specify "you control"
TARGETED_GRANT_PATTERNS = [
    r'target .* you control (gains?|gets?|has)',
    r'equipped creature (gains?|gets?|has)',
    r'enchanted creature (gains?|gets?|has)',
]

# Exclusion patterns - cards that remove or prevent protection
EXCLUSION_PATTERNS = [
    r"can't have (hexproof|indestructible|ward|shroud)",
    r"lose[s]? (hexproof|indestructible|ward|shroud|protection)",
    r"without (hexproof|indestructible|ward|shroud)",
    r"protection from.*can't",
]

# Opponent grant patterns - grants to opponent's permanents (EXCLUDE these)
# NOTE: "all creatures" and "all permanents" are BLANKET effects (help you too), 
# not opponent grants. Only exclude effects that ONLY help opponents.
OPPONENT_GRANT_PATTERNS = [
    r'target opponent',
    r'each opponent',
    r'opponents? control',  # creatures your opponents control
    r'opponent.*permanents?.*have',  # opponent's permanents have
]

# Blanket grant patterns - affects all permanents regardless of controller
# These are VALID protection grants that should be tagged (Blanket scope in M5)
BLANKET_GRANT_PATTERNS = [
    r'\ball creatures? (have|gain|get)\b',  # All creatures gain hexproof
    r'\ball permanents? (have|gain|get)\b',  # All permanents gain indestructible
    r'\beach creature (has|gains?|gets?)\b',  # Each creature gains ward
    r'\beach player\b',  # Each player gains hexproof (very rare but valid blanket)
]

# Kindred-specific grant patterns for metadata tagging
KINDRED_GRANT_PATTERNS = {
    'Knights Gain Protection': [
        r'knight[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other knight[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Merfolk Gain Protection': [
        r'merfolk you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other merfolk.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Zombies Gain Protection': [
        r'zombie[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other zombie[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'target.*zombie.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Vampires Gain Protection': [
        r'vampire[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other vampire[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Elves Gain Protection': [
        r'el(f|ves) you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other el(f|ves).*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Dragons Gain Protection': [
        r'dragon[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other dragon[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Goblins Gain Protection': [
        r'goblin[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other goblin[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Slivers Gain Protection': [
        r'sliver[s]? you control.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'all sliver[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other sliver[s]?.*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Artifacts Gain Protection': [
        r'artifact[s]? you control (have|gain).*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other artifact[s]? (have|gain).*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
    'Enchantments Gain Protection': [
        r'enchantment[s]? you control (have|gain).*\b(hexproof|shroud|indestructible|ward|protection)\b',
        r'other enchantment[s]? (have|gain).*\b(hexproof|shroud|indestructible|ward|protection)\b',
    ],
}

# Protection keyword patterns for inherent check
PROTECTION_KEYWORDS = {
    'hexproof',
    'shroud', 
    'indestructible',
    'ward',
    'protection from',
    'protection',
}


def get_kindred_protection_tags(text: str) -> Set[str]:
    """
    Identify kindred-specific protection grants for metadata tagging.
    
    Returns a set of metadata tag names like:
    - "Knights Gain Hexproof"
    - "Spiders Gain Ward"
    - "Artifacts Gain Indestructible"
    
    Uses both predefined patterns and dynamic creature type detection,
    with specific ability detection (hexproof, ward, indestructible, shroud, protection).
    
    IMPORTANT: Only tags the specific abilities that appear in the same sentence
    as the creature type grant to avoid false positives like Svyelun.
    """
    if not text:
        return set()
    
    # Initialize pre-compiled patterns if needed
    _init_kindred_patterns()
    
    text_lower = text.lower()
    tags = set()
    
    # Only proceed if protective abilities are present (performance optimization)
    protective_abilities = ['hexproof', 'shroud', 'indestructible', 'ward', 'protection']
    if not any(keyword in text_lower for keyword in protective_abilities):
        return tags
    
    # Check predefined patterns (specific kindred types we track)
    for tag_base, patterns in KINDRED_GRANT_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Extract creature type from tag_base (e.g., "Knights" from "Knights Gain Protection")
                creature_type = tag_base.split(' Gain ')[0]
                # Get the matched text to check which abilities are in this specific grant
                matched_text = match.group(0)
                # Only tag abilities that appear in the matched phrase
                if 'hexproof' in matched_text:
                    tags.add(f"{creature_type} Gain Hexproof")
                if 'shroud' in matched_text:
                    tags.add(f"{creature_type} Gain Shroud")
                if 'indestructible' in matched_text:
                    tags.add(f"{creature_type} Gain Indestructible")
                if 'ward' in matched_text:
                    tags.add(f"{creature_type} Gain Ward")
                if 'protection' in matched_text:
                    tags.add(f"{creature_type} Gain Protection")
                break  # Found match for this kindred type, move to next
    
    # Use pre-compiled patterns for all creature types
    for compiled_pattern, tag_template in KINDRED_PATTERNS:
        match = compiled_pattern.search(text_lower)
        if match:
            # Extract creature type from tag_template (e.g., "Knights" from "Knights Gain Protection")
            creature_type = tag_template.split(' Gain ')[0]
            # Get the matched text to check which abilities are in this specific grant
            matched_text = match.group(0)
            # Only tag abilities that appear in the matched phrase
            if 'hexproof' in matched_text:
                tags.add(f"{creature_type} Gain Hexproof")
            if 'shroud' in matched_text:
                tags.add(f"{creature_type} Gain Shroud")
            if 'indestructible' in matched_text:
                tags.add(f"{creature_type} Gain Indestructible")
            if 'ward' in matched_text:
                tags.add(f"{creature_type} Gain Ward")
            if 'protection' in matched_text:
                tags.add(f"{creature_type} Gain Protection")
            # Don't break - a card could grant to multiple creature types
    
    return tags


def is_opponent_grant(text: str) -> bool:
    """
    Check if card grants protection to opponent's permanents ONLY.
    
    Returns True if this grants ONLY to opponents (should be excluded from Protection tag).
    Does NOT exclude blanket effects like "all creatures gain hexproof" which help you too.
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Remove reminder text (in parentheses) to avoid false positives
    # Reminder text often mentions "opponents control" for hexproof/shroud explanations
    text_no_reminder = re.sub(r'\([^)]*\)', '', text_lower)
    
    # Check for opponent-specific grant patterns in the main text (not reminder)
    for pattern in OPPONENT_GRANT_PATTERNS:
        match = re.search(pattern, text_no_reminder, re.IGNORECASE)
        if match:
            # Must be in context of granting protection
            if any(prot in text_lower for prot in ['hexproof', 'shroud', 'indestructible', 'ward', 'protection']):
                # Check the context around the match
                context_start = max(0, match.start() - 30)
                context_end = min(len(text_no_reminder), match.end() + 70)
                context = text_no_reminder[context_start:context_end]
                
                # If "you control" appears in the context, it's limiting to YOUR permanents, not opponents
                if 'you control' not in context:
                    return True
    
    return False


def has_conditional_self_grant(text: str) -> bool:
    """
    Check if card has any conditional self-grant patterns.
    This does NOT check if it ALSO grants to others.
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Check for conditional self-grant patterns (activated/triggered abilities)
    for pattern in CONDITIONAL_SELF_GRANT_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    return False


def is_conditional_self_grant(text: str) -> bool:
    """
    Check if card only conditionally grants protection to itself.
    
    Examples: 
    - "{B}, Discard a card: This creature gains hexproof until end of turn."
    - "Whenever you cast a noncreature spell, untap this creature. It gains protection..."
    - "Whenever this creature attacks, it gains indestructible until end of turn."
    
    These should be excluded as they don't provide protection to OTHER permanents.
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Check if it has conditional self-grant patterns
    found_conditional_self = has_conditional_self_grant(text)
    
    if not found_conditional_self:
        return False
    
    # If we found a conditional self-grant, check if there's ALSO a grant to others
    # Look for patterns that grant to creatures besides itself
    has_other_grant = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in [
        r'other creatures',
        r'creatures you control (have|gain)',
        r'target (creature|permanent) you control gains',
        r'another target (creature|permanent)',
        r'equipped creature (has|gains)',
        r'enchanted creature (has|gains)',
        r'target legendary',
        r'permanents you control gain',
    ])
    
    # Return True only if it's ONLY conditional self-grants (no other grants)
    return not has_other_grant


def is_granting_protection(text: str, keywords: str, exclude_kindred: bool = False) -> bool:
    """
    Determine if a card grants protection effects to other permanents.
    
    Returns True if the card gives/grants protection to other cards unconditionally.
    Returns False if:
    - Card only has inherent protection
    - Card only conditionally grants to itself
    - Card grants to opponent's permanents
    - Card grants only to specific kindred types (when exclude_kindred=True)
    - Card creates tokens with protection (not granting to existing permanents)
    - Card only modifies non-protection stats of other permanents
    
    Args:
        text: Card text to analyze
        keywords: Card keywords (comma-separated)
        exclude_kindred: If True, exclude kindred-specific grants
        
    Returns:
        True if card grants broad protection, False otherwise
    """
    if not text:
        return False
        
    text_lower = text.lower()
    
    # EXCLUDE: Opponent grants
    if is_opponent_grant(text):
        return False
    
    # EXCLUDE: Conditional self-grants only
    if is_conditional_self_grant(text):
        return False
    
    # EXCLUDE: Cards that remove protection
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return False
    
    # EXCLUDE: Token creation with protection (not granting to existing permanents)
    if re.search(r'create.*token.*with.*(hexproof|shroud|indestructible|ward|protection)', text_lower, re.IGNORECASE):
        # Check if there's ALSO granting to other permanents
        has_grant_to_others = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in MASS_GRANT_PATTERNS)
        if not has_grant_to_others:
            return False
    
    # EXCLUDE: Kindred-specific grants if requested
    if exclude_kindred:
        kindred_tags = get_kindred_protection_tags(text)
        if kindred_tags:
            # If we detected kindred tags, check if there's ALSO a non-kindred grant
            # Look for grant patterns that explicitly grant to ALL creatures/permanents broadly
            has_broad_grant = False
            
            # Patterns that indicate truly broad grants (not type-specific)
            broad_only_patterns = [
                r'\bcreatures you control (have|gain)\b(?!.*(knight|merfolk|zombie|elf|dragon|goblin|sliver))',  # Only if not followed by type
                r'\bpermanents you control (have|gain)\b',
                r'\beach (creature|permanent) you control',
                r'\ball (creatures?|permanents?)',
            ]
            
            for pattern in broad_only_patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    has_broad_grant = True
                    break
            
            if not has_broad_grant:
                return False  # Only kindred grants, exclude
    
    # Check if card has inherent protection keywords
    has_inherent = False
    if keywords:
        keywords_lower = keywords.lower()
        has_inherent = any(k in keywords_lower for k in PROTECTION_KEYWORDS)
    
    # Check for explicit grants with protection keywords
    found_grant = False
    
    # Blanket grant patterns (all creatures gain hexproof) - these are VALID grants
    for pattern in BLANKET_GRANT_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            # Check if protection keyword appears nearby
            context_start = match.start()
            context_end = min(len(text_lower), match.end() + 70)
            context = text_lower[context_start:context_end]
            
            if any(prot in context for prot in PROTECTION_KEYWORDS):
                found_grant = True
                break
    
    # Mass grant patterns (creatures you control have/gain)
    if not found_grant:
        for pattern in MASS_GRANT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Check if protection keyword appears in the same sentence or nearby (within 70 chars AFTER the match)
                # This ensures we're looking at "creatures you control HAVE hexproof" not just having both phrases
                context_start = match.start()
                context_end = min(len(text_lower), match.end() + 70)
                context = text_lower[context_start:context_end]
                
                if any(prot in context for prot in PROTECTION_KEYWORDS):
                    found_grant = True
                    break
    
    # Targeted grant patterns (target creature gains)
    if not found_grant:
        for pattern in TARGETED_GRANT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Check if protection keyword appears after the grant verb (within 70 chars)
                context_start = match.start()
                context_end = min(len(text_lower), match.end() + 70)
                context = text_lower[context_start:context_end]
                
                if any(prot in context for prot in PROTECTION_KEYWORDS):
                        found_grant = True
                        break
    
    # Grant verb patterns (creature gains/gets hexproof)
    if not found_grant:
        for pattern in GRANT_VERB_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                found_grant = True
                break
    
    # If we have inherent protection and the ONLY text is about stats (no grant words), exclude
    if has_inherent and not found_grant:
        # Check if text only talks about other stats (power/toughness, +X/+X)
        has_stat_only = bool(re.search(r'(get[s]?|gain[s]?)\s+[+\-][0-9X]+/[+\-][0-9X]+', text_lower))
        # Check if text mentions "other" without protection keywords
        mentions_other_without_prot = 'other' in text_lower and not any(prot in text_lower for prot in PROTECTION_KEYWORDS if prot in text_lower[text_lower.find('other'):])
        
        if has_stat_only or mentions_other_without_prot:
            return False
    
    return found_grant


def categorize_protection_card(name: str, text: str, keywords: str, card_type: str, exclude_kindred: bool = False) -> str:
    """
    Categorize a Protection-tagged card for audit purposes.
    
    Args:
        name: Card name
        text: Card text
        keywords: Card keywords
        card_type: Card type line
        exclude_kindred: If True, kindred-specific grants are categorized as metadata, not Grant
    
    Returns:
        'Grant' - gives broad protection to others
        'Kindred' - gives kindred-specific protection (metadata tag)
        'Inherent' - has protection itself
        'ConditionalSelf' - only conditionally grants to itself
        'Opponent' - grants to opponent's permanents
        'Neither' - false positive
    """
    keywords_lower = keywords.lower() if keywords else ''
    
    # Check for opponent grants first
    if is_opponent_grant(text):
        return 'Opponent'
    
    # Check for conditional self-grants (ONLY self, no other grants)
    if is_conditional_self_grant(text):
        return 'ConditionalSelf'
    
    # Check if it has conditional self-grant (may also have other grants)
    has_cond_self = has_conditional_self_grant(text)
    
    # Check if it has inherent protection
    has_inherent = any(k in keywords_lower for k in PROTECTION_KEYWORDS)
    
    # Check for kindred-specific grants
    kindred_tags = get_kindred_protection_tags(text)
    if kindred_tags and exclude_kindred:
        # Check if there's ALSO a broad grant (excluding kindred)
        grants_broad = is_granting_protection(text, keywords, exclude_kindred=True)
        
        if grants_broad and has_inherent:
            # Has inherent + kindred + broad grants
            return 'Mixed'
        elif grants_broad:
            # Has kindred + broad grants (but no inherent)
            # This is just Grant with kindred metadata tags
            return 'Grant'
        elif has_inherent:
            # Has inherent + kindred only (not broad)
            # This is still just Kindred category (inherent is separate from granting)
            return 'Kindred'
        else:
            # Only kindred grants, no inherent or broad
            return 'Kindred'
    
    # Check if it grants protection broadly (not kindred-specific)
    grants_protection = is_granting_protection(text, keywords, exclude_kindred=exclude_kindred)
    
    # Categorize based on what it does
    if grants_protection and has_cond_self:
        # Has conditional self-grant + grants to others = Mixed
        return 'Mixed'
    elif grants_protection and has_inherent:
        return 'Mixed'  # Has inherent + grants broadly
    elif grants_protection:
        return 'Grant'  # Only grants broadly
    elif has_inherent:
        return 'Inherent'  # Only has inherent
    else:
        return 'Neither'  # False positive
