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

# Word-boundaried so "phase in" doesn't false-positive inside unrelated text
# like "...beginning phase includes..." (Sphinx of the Second Sun).
_PHASING_RE = re.compile(
    r'\bphase\s+out\b|\bphases\s+out\b|\bphasing\b|\bphase\s+in\b|\bphases\s+in\b',
    re.IGNORECASE,
)

# Anti-phasing text ("target permanent can't phase out") describes preventing
# phasing, not causing it - strip it out before scope detection so it doesn't
# masquerade as removal/protection (e.g. Spatial Binding).
_NEGATED_PHASING_RE = re.compile(
    r"(?:can't|cannot|can\s+not)\s+phase\s+(?:in|out)", re.IGNORECASE
)


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
        # Sentence-boundary continuation (Slip Out the Back: "target creature. It phases out.")
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?\.\s*it\s+phases?\s+out', re.IGNORECASE),
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
        # Pronoun self-reference (Kaito Shizuki: "he phases out")
        re.compile(r'\b(?:he|she)\s+phases?\s+out\b', re.IGNORECASE),
        # Mutual self+other phasing (Dream Fighter: "this creature and that creature phase out")
        re.compile(r'this\s+creature\s+and\s+that\s+creature\s+phase\s+out', re.IGNORECASE),
    ]
    
    # Opponent patterns
    opponent_patterns = [
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent)\s+an?\s+opponents?\s+controls?\s+phases?\s+out', re.IGNORECASE),
        # Unqualified targets (can target opponents' stuff if no "you control" restriction)
        re.compile(r'(?:up\s+to\s+)?(?:one\s+|x\s+|that\s+many\s+)?(?:other\s+)?(?:another\s+)?target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?(?:[^.]*)?phases?\s+out', re.IGNORECASE),
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|land|nonland\s+permanent)(?:,|\s+and)?\s+(?:then|and)?\s+it\s+phases?\s+out', re.IGNORECASE),
        # "target opponent controls" wording (Teferi, Timeless Voyager), distinct from "an opponent controls"
        re.compile(r'target\s+opponent\s+controls\s+phases?\s+out', re.IGNORECASE),
        # Sentence-boundary continuation, unqualified target (Slip Out the Back: "target creature. It phases out.")
        re.compile(r'target\s+(?:\w+\s+)*(?:creature|permanent|artifact|enchantment|nonland\s+permanent)s?\.\s*it\s+phases?\s+out', re.IGNORECASE),
        # "target player controls" (Galadriel's Dismissal) - caster picks any player at
        # cast time (including themselves), so this is an ambiguous single-player
        # wipe, not a global one. The dual-scope fallback below adds "Your Permanents"
        # too since this isn't restricted to "you control" or "opponent".
        re.compile(r'(?:each|target)\s+(?:creature|permanent)\s+target\s+player\s+controls\s+phases?\s+out', re.IGNORECASE),
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
        # Sentence-boundary pronoun continuation (The Moment: "creature you control. It phases out")
        re.compile(r'creature\s+you\s+control.*it\s+phases?\s+out', re.IGNORECASE),
        # Bare pronoun "them" continuation (Change of Plans: "you control connive. You may have any number of them phase out")
        re.compile(r'you\s+control.*\bthem\s+phases?\s+out', re.IGNORECASE),
        # Missing noun class: lands (Taniwha: "all lands you control phase out")
        re.compile(r'all\s+lands\s+you\s+control\s+phase\s+out', re.IGNORECASE),
        # Missing noun class: planeswalkers (Vronos, Masked Inquisitor: "target planeswalkers you control phase out")
        re.compile(r'planeswalkers?\s+you\s+control\s+phases?\s+out', re.IGNORECASE),
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
        # Compound type list (The City on the Edge of Forever: "All artifacts and creatures phase out")
        re.compile(r'all\s+(?:\w+\s+and\s+)?(?:creatures?|permanents?|artifacts?|enchantments?|lands?)\s+phase\s+out', re.IGNORECASE),
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
    
    # Strip negated phasing text ("can't phase out") so anti-phasing tech
    # doesn't get misread as a phasing effect itself.
    scope_text = _NEGATED_PHASING_RE.sub('', text)
    if 'phas' not in scope_text.lower():
        return tags
    
    # Detect all scopes (phasing can have multiple)
    # word_boundary=False: 'phas' is a stem (never a whole word on its own), so
    # the default \bphas\b word-boundary check would never match real phasing
    # text ("phase"/"phases"/"phasing"). Safe here because the substring check
    # above already gates on 'phas' being present at all.
    scopes = scope_utils.detect_multi_scope(
        text=scope_text,
        card_name=card_name,
        ability_keyword='phas',  # Use 'phas' to catch both 'phase' and 'phasing'
        patterns=patterns,
        check_grant_verbs=False,  # Phasing doesn't need grant verb checking
        word_boundary=False,
    )
    
    # Cards explicitly restricted to "you control" shouldn't also get an
    # Opponent Permanents tag from the unqualified targeting catch-all pattern
    # (e.g. Clever Concealment, Guardian of Faith, Haystack).
    if 'you control' in text_lower and 'Your Permanents' in scopes:
        scopes.discard('Opponent Permanents')

    # Truly unqualified targets ("target creature phases out") aren't
    # restricted to your board or an opponent's, so they can hit either
    # depending on how the caster targets - add the missing "Your Permanents"
    # side for the dual Protection+Removal treatment (e.g. Brokers Confluence,
    # March of Swirling Mist, Slip Out the Back). Equipment/Aura "grant
    # phasing" effects (Cloak of Invisibility, Robe of Stars, Vanishing) are
    # excluded since those only ever benefit the enchanted/equipped permanent,
    # so they're intentionally left "Your Permanents"-only.
    is_restricted = (
        'you control' in text_lower
        or 'opponent' in text_lower
        or "don't control" in text_lower
        or "doesn't control" in text_lower
    )
    if not is_restricted and 'Opponent Permanents' in scopes:
        scopes.add('Your Permanents')

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
    
    return bool(_PHASING_RE.search(text))


def is_removal_phasing(tags: Set[str]) -> bool:
    """
    Check if phasing effect acts as removal (targets opponent permanents).
    
    Args:
        tags: Set of phasing scope tags
        
    Returns:
        True if this is removal-style phasing
    """
    return "Opponent Permanents: Phasing" in tags
