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
from typing import List, Pattern, Set
from . import regex_patterns as rgx
from . import tag_utils
from .tag_constants import CONTEXT_WINDOW_SIZE, CREATURE_TYPES, PROTECTION_KEYWORDS


# Pre-compile kindred detection patterns at module load for performance
# Pattern: (compiled_regex, tag_name_template)
def _build_kindred_patterns() -> List[tuple[Pattern, str]]:
    """Build pre-compiled kindred patterns for all creature types.
    
    Returns:
        List of tuples containing (compiled_pattern, tag_name)
    """
    patterns = []
    
    for creature_type in CREATURE_TYPES:
        creature_lower = creature_type.lower()
        creature_escaped = re.escape(creature_lower)
        tag_name = f"{creature_type}s Gain Protection"
        pattern_templates = [
            rf'\bother {creature_escaped}s?\b.*\b(have|gain)\b',
            rf'\b{creature_escaped} creatures?\b.*\b(have|gain)\b',
            rf'\btarget {creature_escaped}\b.*\bgains?\b',
        ]
        
        for pattern_str in pattern_templates:
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                patterns.append((compiled, tag_name))
            except re.error:
                # Skip patterns that fail to compile
                pass
    
    return patterns
KINDRED_PATTERNS: List[tuple[Pattern, str]] = _build_kindred_patterns()


# Grant verb patterns - cards that give protection to other permanents
# These patterns look for grant verbs that affect OTHER permanents, not self
# M5: Added phasing support
# Pre-compiled at module load for performance
GRANT_VERB_PATTERNS: List[Pattern] = [
    re.compile(r'\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),
    re.compile(r'\bgive[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),
    re.compile(r'\bgrant[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),
    re.compile(r'\bhave\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),  # "have hexproof" static grants
    re.compile(r'\bget[s]?\b.*\+.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),  # "gets +X/+X and has hexproof" direct
    re.compile(r'\bget[s]?\b.*\+.*\band\b.*\b(gain[s]?|have)\b.*\b(hexproof|shroud|indestructible|ward|protection|phasing)\b', re.IGNORECASE),  # "gets +X/+X and gains hexproof"
    re.compile(r'\bphases? out\b', re.IGNORECASE),  # M5: Direct phasing triggers (e.g., "it phases out")
]

# Self-reference patterns that should NOT count as granting
# Reminder text and keyword lines only
# M5: Added phasing support
# Pre-compiled at module load for performance
SELF_REFERENCE_PATTERNS: List[Pattern] = [
    re.compile(r'^\s*(hexproof|shroud|indestructible|ward|protection|phasing)', re.IGNORECASE),  # Start of text (keyword ability)
    re.compile(r'\([^)]*\b(hexproof|shroud|indestructible|ward|protection|phasing)[^)]*\)', re.IGNORECASE),  # Reminder text in parens
]

# Conditional self-grant patterns - activated/triggered abilities that grant to self
# Pre-compiled at module load for performance
CONDITIONAL_SELF_GRANT_PATTERNS: List[Pattern] = [
    # Activated abilities
    re.compile(r'\{[^}]*\}.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    re.compile(r'discard.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b', re.IGNORECASE),
    re.compile(r'\{t\}.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b', re.IGNORECASE),
    re.compile(r'sacrifice.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b', re.IGNORECASE),
    re.compile(r'pay.*life.*:.*\bthis (creature|permanent|artifact|enchantment)\b.*\bgain[s]?\b', re.IGNORECASE),
    # Triggered abilities that grant to self only
    re.compile(r'whenever.*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    re.compile(r'whenever you (cast|play|attack|cycle|discard|commit).*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    re.compile(r'at the beginning.*\b(this creature|this permanent|it)\b.*\bgain[s]?\b.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    re.compile(r'whenever.*\b(this creature|this permanent)\b (attacks|enters|becomes).*\b(this creature|this permanent|it)\b.*\bgain[s]?\b', re.IGNORECASE),
    # Named self-references (e.g., "Pristine Skywise gains")
    re.compile(r'whenever you cast.*[A-Z][a-z]+.*gains.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    re.compile(r'whenever you.*[A-Z][a-z]+.*gains.*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
    # Static conditional abilities (as long as, if you control X)
    re.compile(r'as long as.*\b(this creature|this permanent|it|has)\b.*(has|gains?).*\b(hexproof|shroud|indestructible|ward|protection)\b', re.IGNORECASE),
]

# Mass grant patterns - affects multiple creatures YOU control
# Pre-compiled at module load for performance
MASS_GRANT_PATTERNS: List[Pattern] = [
    re.compile(r'creatures you control (have|gain|get)', re.IGNORECASE),
    re.compile(r'other .* you control (have|gain|get)', re.IGNORECASE),
    re.compile(r'(artifacts?|enchantments?|permanents?) you control (have|gain|get)', re.IGNORECASE),  # Artifacts you control have...
    re.compile(r'other (creatures?|artifacts?|enchantments?) (have|gain|get)', re.IGNORECASE),  # Other creatures have...
    re.compile(r'all (creatures?|slivers?|permanents?) (have|gain|get)', re.IGNORECASE),  # All creatures/slivers have...
]

# Targeted grant patterns - must specify "you control"
# Pre-compiled at module load for performance
TARGETED_GRANT_PATTERNS: List[Pattern] = [
    re.compile(r'target .* you control (gains?|gets?|has)', re.IGNORECASE),
    re.compile(r'equipped creature (gains?|gets?|has)', re.IGNORECASE),
    re.compile(r'enchanted enchantment (gains?|gets?|has)', re.IGNORECASE),
]

# Exclusion patterns - cards that remove or prevent protection
# Pre-compiled at module load for performance
EXCLUSION_PATTERNS: List[Pattern] = [
    re.compile(r"can't have (hexproof|indestructible|ward|shroud)", re.IGNORECASE),
    re.compile(r"lose[s]? (hexproof|indestructible|ward|shroud|protection)", re.IGNORECASE),
    re.compile(r"without (hexproof|indestructible|ward|shroud)", re.IGNORECASE),
    re.compile(r"protection from.*can't", re.IGNORECASE),
]

# Opponent grant patterns - grants to opponent's permanents (EXCLUDE these)
# NOTE: "all creatures" and "all permanents" are BLANKET effects (help you too), 
# not opponent grants. Only exclude effects that ONLY help opponents.
# Pre-compiled at module load for performance
OPPONENT_GRANT_PATTERNS: List[Pattern] = [
    rgx.TARGET_OPPONENT,
    rgx.EACH_OPPONENT,
    rgx.OPPONENT_CONTROL,
    re.compile(r'opponent.*permanents?.*have', re.IGNORECASE),  # opponent's permanents have
]

# Blanket grant patterns - affects all permanents regardless of controller
# These are VALID protection grants that should be tagged (Blanket scope in M5)
# Pre-compiled at module load for performance
BLANKET_GRANT_PATTERNS: List[Pattern] = [
    re.compile(r'\ball creatures? (have|gain|get)\b', re.IGNORECASE),  # All creatures gain hexproof
    re.compile(r'\ball permanents? (have|gain|get)\b', re.IGNORECASE),  # All permanents gain indestructible
    re.compile(r'\beach creature (has|gains?|gets?)\b', re.IGNORECASE),  # Each creature gains ward
    rgx.EACH_PLAYER,  # Each player gains hexproof (very rare but valid blanket)
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
    
    text_lower = text.lower()
    tags = set()
    
    # Only proceed if protective abilities are present (performance optimization)
    protective_abilities = ['hexproof', 'shroud', 'indestructible', 'ward', 'protection']
    if not any(keyword in text_lower for keyword in protective_abilities):
        return tags
    for tag_base, patterns in KINDRED_GRANT_PATTERNS.items():
        for pattern in patterns:
            pattern_compiled = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
            match = pattern_compiled.search(text_lower)
            if match:
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
    text_no_reminder = tag_utils.strip_reminder_text(text_lower)
    for pattern in OPPONENT_GRANT_PATTERNS:
        match = pattern.search(text_no_reminder)
        if match:
            # Must be in context of granting protection
            if any(prot in text_lower for prot in ['hexproof', 'shroud', 'indestructible', 'ward', 'protection']):
                context = tag_utils.extract_context_window(
                    text_no_reminder, match.start(), match.end(), 
                    window_size=CONTEXT_WINDOW_SIZE, include_before=True
                )
                
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
    for pattern in CONDITIONAL_SELF_GRANT_PATTERNS:
        if pattern.search(text_lower):
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
    found_conditional_self = has_conditional_self_grant(text)
    
    if not found_conditional_self:
        return False
    
    # If we found a conditional self-grant, check if there's ALSO a grant to others
    other_grant_patterns = [
        rgx.OTHER_CREATURES,
        re.compile(r'creatures you control (have|gain)', re.IGNORECASE),
        re.compile(r'target (creature|permanent) you control gains', re.IGNORECASE),
        re.compile(r'another target (creature|permanent)', re.IGNORECASE),
        re.compile(r'equipped creature (has|gains)', re.IGNORECASE),
        re.compile(r'enchanted creature (has|gains)', re.IGNORECASE),
        re.compile(r'target legendary', re.IGNORECASE),
        re.compile(r'permanents you control gain', re.IGNORECASE),
    ]
    has_other_grant = any(pattern.search(text_lower) for pattern in other_grant_patterns)
    
    # Return True only if it's ONLY conditional self-grants (no other grants)
    return not has_other_grant


def _should_exclude_token_creation(text_lower: str) -> bool:
    """Check if card only creates tokens with protection (not granting to existing permanents).
    
    Args:
        text_lower: Lowercased card text
        
    Returns:
        True if card only creates tokens, False if it also grants
    """
    token_with_protection = re.compile(r'create.*token.*with.*(hexproof|shroud|indestructible|ward|protection)', re.IGNORECASE)
    if token_with_protection.search(text_lower):
        has_grant_to_others = any(pattern.search(text_lower) for pattern in MASS_GRANT_PATTERNS)
        return not has_grant_to_others
    return False


def _should_exclude_kindred_only(text: str, text_lower: str, exclude_kindred: bool) -> bool:
    """Check if card only grants to specific kindred types.
    
    Args:
        text: Original card text
        text_lower: Lowercased card text
        exclude_kindred: Whether to exclude kindred-specific grants
        
    Returns:
        True if card only has kindred grants, False if it has broad grants
    """
    if not exclude_kindred:
        return False
    
    kindred_tags = get_kindred_protection_tags(text)
    if not kindred_tags:
        return False
    broad_only_patterns = [
        re.compile(r'\bcreatures you control (have|gain)\b(?!.*(knight|merfolk|zombie|elf|dragon|goblin|sliver))', re.IGNORECASE),
        re.compile(r'\bpermanents you control (have|gain)\b', re.IGNORECASE),
        re.compile(r'\beach (creature|permanent) you control', re.IGNORECASE),
        re.compile(r'\ball (creatures?|permanents?)', re.IGNORECASE),
    ]
    
    has_broad_grant = any(pattern.search(text_lower) for pattern in broad_only_patterns)
    return not has_broad_grant


def _check_pattern_grants(text_lower: str, pattern_list: List[Pattern]) -> bool:
    """Check if text contains protection grants matching pattern list.
    
    Args:
        text_lower: Lowercased card text
        pattern_list: List of grant patterns to check
        
    Returns:
        True if protection grant found, False otherwise
    """
    for pattern in pattern_list:
        match = pattern.search(text_lower)
        if match:
            context = tag_utils.extract_context_window(text_lower, match.start(), match.end())
            if any(prot in context for prot in PROTECTION_KEYWORDS):
                return True
    return False


def _has_inherent_protection_only(text_lower: str, keywords: str, found_grant: bool) -> bool:
    """Check if card only has inherent protection without granting.
    
    Args:
        text_lower: Lowercased card text
        keywords: Card keywords
        found_grant: Whether a grant pattern was found
        
    Returns:
        True if card only has inherent protection, False otherwise
    """
    if not keywords:
        return False
    
    keywords_lower = keywords.lower()
    has_inherent = any(k in keywords_lower for k in PROTECTION_KEYWORDS)
    
    if not has_inherent or found_grant:
        return False
    stat_only_pattern = re.compile(r'(get[s]?|gain[s]?)\s+[+\-][0-9X]+/[+\-][0-9X]+', re.IGNORECASE)
    has_stat_only = bool(stat_only_pattern.search(text_lower))
    mentions_other_without_prot = False
    if 'other' in text_lower:
        other_idx = text_lower.find('other')
        remaining_text = text_lower[other_idx:]
        mentions_other_without_prot = not any(prot in remaining_text for prot in PROTECTION_KEYWORDS)
    
    return has_stat_only or mentions_other_without_prot


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
    
    # Early exclusion checks
    if is_opponent_grant(text):
        return False
    
    if is_conditional_self_grant(text):
        return False
    
    if any(pattern.search(text_lower) for pattern in EXCLUSION_PATTERNS):
        return False
    
    if _should_exclude_token_creation(text_lower):
        return False
    
    if _should_exclude_kindred_only(text, text_lower, exclude_kindred):
        return False
    found_grant = False
    if _check_pattern_grants(text_lower, BLANKET_GRANT_PATTERNS):
        found_grant = True
    elif _check_pattern_grants(text_lower, MASS_GRANT_PATTERNS):
        found_grant = True
    elif _check_pattern_grants(text_lower, TARGETED_GRANT_PATTERNS):
        found_grant = True
    elif any(pattern.search(text_lower) for pattern in GRANT_VERB_PATTERNS):
        found_grant = True
    if _has_inherent_protection_only(text_lower, keywords, found_grant):
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
    if is_opponent_grant(text):
        return 'Opponent'
    if is_conditional_self_grant(text):
        return 'ConditionalSelf'
    has_cond_self = has_conditional_self_grant(text)
    has_inherent = any(k in keywords_lower for k in PROTECTION_KEYWORDS)
    kindred_tags = get_kindred_protection_tags(text)
    if kindred_tags and exclude_kindred:
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
