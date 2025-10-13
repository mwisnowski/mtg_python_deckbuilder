"""
Centralized regex patterns for MTG card tagging.

All patterns compiled with re.IGNORECASE for case-insensitive matching.
Organized by semantic category for maintainability and reusability.

Usage:
    from code.tagging import regex_patterns as rgx
    
    mask = df['text'].str.contains(rgx.YOU_CONTROL, na=False)
    if rgx.GRANT_HEXPROOF.search(text):
        ...
    
    # Or use builder functions
    pattern = rgx.ownership_pattern('creature', 'you')
    mask = df['text'].str.contains(pattern, na=False)
"""

import re
from typing import Pattern, List

# =============================================================================
# OWNERSHIP & CONTROLLER PATTERNS
# =============================================================================

YOU_CONTROL: Pattern = re.compile(r'you control', re.IGNORECASE)
THEY_CONTROL: Pattern = re.compile(r'they control', re.IGNORECASE)
OPPONENT_CONTROL: Pattern = re.compile(r'opponent[s]? control', re.IGNORECASE)

CREATURE_YOU_CONTROL: Pattern = re.compile(r'creature[s]? you control', re.IGNORECASE)
PERMANENT_YOU_CONTROL: Pattern = re.compile(r'permanent[s]? you control', re.IGNORECASE)
ARTIFACT_YOU_CONTROL: Pattern = re.compile(r'artifact[s]? you control', re.IGNORECASE)
ENCHANTMENT_YOU_CONTROL: Pattern = re.compile(r'enchantment[s]? you control', re.IGNORECASE)

# =============================================================================
# GRANT VERB PATTERNS  
# =============================================================================

GAIN: Pattern = re.compile(r'\bgain[s]?\b', re.IGNORECASE)
HAS: Pattern = re.compile(r'\bhas\b', re.IGNORECASE)
HAVE: Pattern = re.compile(r'\bhave\b', re.IGNORECASE)
GET: Pattern = re.compile(r'\bget[s]?\b', re.IGNORECASE)

GRANT_VERBS: List[str] = ['gain', 'gains', 'has', 'have', 'get', 'gets']

# =============================================================================
# TARGETING PATTERNS
# =============================================================================

TARGET_PLAYER: Pattern = re.compile(r'target player', re.IGNORECASE)
TARGET_OPPONENT: Pattern = re.compile(r'target opponent', re.IGNORECASE)
TARGET_CREATURE: Pattern = re.compile(r'target creature', re.IGNORECASE)
TARGET_PERMANENT: Pattern = re.compile(r'target permanent', re.IGNORECASE)
TARGET_ARTIFACT: Pattern = re.compile(r'target artifact', re.IGNORECASE)
TARGET_ENCHANTMENT: Pattern = re.compile(r'target enchantment', re.IGNORECASE)

EACH_PLAYER: Pattern = re.compile(r'each player', re.IGNORECASE)
EACH_OPPONENT: Pattern = re.compile(r'each opponent', re.IGNORECASE)
TARGET_YOU_CONTROL: Pattern = re.compile(r'target .* you control', re.IGNORECASE)

# =============================================================================
# PROTECTION ABILITY PATTERNS
# =============================================================================

HEXPROOF: Pattern = re.compile(r'\bhexproof\b', re.IGNORECASE)
SHROUD: Pattern = re.compile(r'\bshroud\b', re.IGNORECASE)
INDESTRUCTIBLE: Pattern = re.compile(r'\bindestructible\b', re.IGNORECASE)
WARD: Pattern = re.compile(r'\bward\b', re.IGNORECASE)
PROTECTION_FROM: Pattern = re.compile(r'protection from', re.IGNORECASE)

PROTECTION_ABILITIES: List[str] = ['hexproof', 'shroud', 'indestructible', 'ward', 'protection']

CANT_HAVE_PROTECTION: Pattern = re.compile(r"can't have (hexproof|indestructible|ward|shroud)", re.IGNORECASE)
LOSE_PROTECTION: Pattern = re.compile(r"lose[s]? (hexproof|indestructible|ward|shroud|protection)", re.IGNORECASE)

# =============================================================================
# CARD DRAW PATTERNS
# =============================================================================

DRAW_A_CARD: Pattern = re.compile(r'draw[s]? (?:a|one) card', re.IGNORECASE)
DRAW_CARDS: Pattern = re.compile(r'draw[s]? (?:two|three|four|five|x|\d+) card', re.IGNORECASE)
DRAW: Pattern = re.compile(r'\bdraw[s]?\b', re.IGNORECASE)

# =============================================================================
# TOKEN CREATION PATTERNS
# =============================================================================

CREATE_TOKEN: Pattern = re.compile(r'create[s]?.*token', re.IGNORECASE)
PUT_TOKEN: Pattern = re.compile(r'put[s]?.*token', re.IGNORECASE)

CREATE_TREASURE: Pattern = re.compile(r'create.*treasure token', re.IGNORECASE)
CREATE_FOOD: Pattern = re.compile(r'create.*food token', re.IGNORECASE)
CREATE_CLUE: Pattern = re.compile(r'create.*clue token', re.IGNORECASE)
CREATE_BLOOD: Pattern = re.compile(r'create.*blood token', re.IGNORECASE)

# =============================================================================
# COUNTER PATTERNS
# =============================================================================

PLUS_ONE_COUNTER: Pattern = re.compile(r'\+1/\+1 counter', re.IGNORECASE)
MINUS_ONE_COUNTER: Pattern = re.compile(r'\-1/\-1 counter', re.IGNORECASE)
LOYALTY_COUNTER: Pattern = re.compile(r'loyalty counter', re.IGNORECASE)
PROLIFERATE: Pattern = re.compile(r'\bproliferate\b', re.IGNORECASE)

ONE_OR_MORE_COUNTERS: Pattern = re.compile(r'one or more counter', re.IGNORECASE)
ONE_OR_MORE_PLUS_ONE_COUNTERS: Pattern = re.compile(r'one or more \+1/\+1 counter', re.IGNORECASE)
IF_HAD_COUNTERS: Pattern = re.compile(r'if it had counter', re.IGNORECASE)
WITH_COUNTERS_ON_THEM: Pattern = re.compile(r'with counter[s]? on them', re.IGNORECASE)

# =============================================================================
# SACRIFICE & REMOVAL PATTERNS
# =============================================================================

SACRIFICE: Pattern = re.compile(r'sacrifice[s]?', re.IGNORECASE)
SACRIFICED: Pattern = re.compile(r'sacrificed', re.IGNORECASE)
DESTROY: Pattern = re.compile(r'destroy[s]?', re.IGNORECASE)
EXILE: Pattern = re.compile(r'exile[s]?', re.IGNORECASE)
EXILED: Pattern = re.compile(r'exiled', re.IGNORECASE)

SACRIFICE_DRAW: Pattern = re.compile(r'sacrifice (?:a|an) (?:artifact|creature|permanent)(?:[^,]*),?[^,]*draw', re.IGNORECASE)
SACRIFICE_COLON_DRAW: Pattern = re.compile(r'sacrifice [^:]+: draw', re.IGNORECASE)
SACRIFICED_COMMA_DRAW: Pattern = re.compile(r'sacrificed[^,]+, draw', re.IGNORECASE)
EXILE_RETURN_BATTLEFIELD: Pattern = re.compile(r'exile.*return.*to the battlefield', re.IGNORECASE)

# =============================================================================
# DISCARD PATTERNS
# =============================================================================

DISCARD_A_CARD: Pattern = re.compile(r'discard (?:a|one|two|three|x) card', re.IGNORECASE)
DISCARD_YOUR_HAND: Pattern = re.compile(r'discard your hand', re.IGNORECASE)
YOU_DISCARD: Pattern = re.compile(r'you discard', re.IGNORECASE)

# Discard triggers
WHENEVER_YOU_DISCARD: Pattern = re.compile(r'whenever you discard', re.IGNORECASE)
IF_YOU_DISCARDED: Pattern = re.compile(r'if you discarded', re.IGNORECASE)
WHEN_YOU_DISCARD: Pattern = re.compile(r'when you discard', re.IGNORECASE)
FOR_EACH_DISCARDED: Pattern = re.compile(r'for each card you discarded', re.IGNORECASE)

# Opponent discard
TARGET_PLAYER_DISCARDS: Pattern = re.compile(r'target player discards', re.IGNORECASE)
TARGET_OPPONENT_DISCARDS: Pattern = re.compile(r'target opponent discards', re.IGNORECASE)
EACH_PLAYER_DISCARDS: Pattern = re.compile(r'each player discards', re.IGNORECASE)
EACH_OPPONENT_DISCARDS: Pattern = re.compile(r'each opponent discards', re.IGNORECASE)
THAT_PLAYER_DISCARDS: Pattern = re.compile(r'that player discards', re.IGNORECASE)

# Discard cost
ADDITIONAL_COST_DISCARD: Pattern = re.compile(r'as an additional cost to (?:cast this spell|activate this ability),? discard (?:a|one) card', re.IGNORECASE)
ADDITIONAL_COST_DISCARD_SHORT: Pattern = re.compile(r'as an additional cost,? discard (?:a|one) card', re.IGNORECASE)

MADNESS: Pattern = re.compile(r'\bmadness\b', re.IGNORECASE)

# =============================================================================
# DAMAGE & LIFE LOSS PATTERNS
# =============================================================================

DEALS_ONE_DAMAGE: Pattern = re.compile(r'deals\s+1\s+damage', re.IGNORECASE)
EXACTLY_ONE_DAMAGE: Pattern = re.compile(r'exactly\s+1\s+damage', re.IGNORECASE)
LOSES_ONE_LIFE: Pattern = re.compile(r'loses\s+1\s+life', re.IGNORECASE)

# =============================================================================
# COST REDUCTION PATTERNS
# =============================================================================

COST_LESS: Pattern = re.compile(r'cost[s]? \{[\d\w]\} less', re.IGNORECASE)
COST_LESS_TO_CAST: Pattern = re.compile(r'cost[s]? less to cast', re.IGNORECASE)
WITH_X_IN_COST: Pattern = re.compile(r'with \{[xX]\} in (?:its|their)', re.IGNORECASE)
AFFINITY_FOR: Pattern = re.compile(r'affinity for', re.IGNORECASE)
SPELLS_COST: Pattern = re.compile(r'spells cost', re.IGNORECASE)
SPELLS_YOU_CAST_COST: Pattern = re.compile(r'spells you cast cost', re.IGNORECASE)

# =============================================================================
# MONARCH & INITIATIVE PATTERNS
# =============================================================================

BECOME_MONARCH: Pattern = re.compile(r'becomes? the monarch', re.IGNORECASE)
IS_MONARCH: Pattern = re.compile(r'is the monarch', re.IGNORECASE)
WAS_MONARCH: Pattern = re.compile(r'was the monarch', re.IGNORECASE)
YOU_ARE_MONARCH: Pattern = re.compile(r"you are the monarch|you're the monarch", re.IGNORECASE)
YOU_BECOME_MONARCH: Pattern = re.compile(r'you become the monarch', re.IGNORECASE)
CANT_BECOME_MONARCH: Pattern = re.compile(r"can't become the monarch", re.IGNORECASE)

# =============================================================================
# KEYWORD ABILITY PATTERNS
# =============================================================================

PARTNER_BASIC: Pattern = re.compile(r'\bpartner\b(?!\s*(?:with|[-—–]))', re.IGNORECASE)
PARTNER_WITH: Pattern = re.compile(r'partner with', re.IGNORECASE)
PARTNER_SURVIVORS: Pattern = re.compile(r'Partner\s*[-—–]\s*Survivors', re.IGNORECASE)
PARTNER_FATHER_SON: Pattern = re.compile(r'Partner\s*[-—–]\s*Father\s*&\s*Son', re.IGNORECASE)

FLYING: Pattern = re.compile(r'\bflying\b', re.IGNORECASE)
VIGILANCE: Pattern = re.compile(r'\bvigilance\b', re.IGNORECASE)
TRAMPLE: Pattern = re.compile(r'\btrample\b', re.IGNORECASE)
HASTE: Pattern = re.compile(r'\bhaste\b', re.IGNORECASE)
LIFELINK: Pattern = re.compile(r'\blifelink\b', re.IGNORECASE)
DEATHTOUCH: Pattern = re.compile(r'\bdeathtouch\b', re.IGNORECASE)
DOUBLE_STRIKE: Pattern = re.compile(r'double strike', re.IGNORECASE)
FIRST_STRIKE: Pattern = re.compile(r'first strike', re.IGNORECASE)
MENACE: Pattern = re.compile(r'\bmenace\b', re.IGNORECASE)
REACH: Pattern = re.compile(r'\breach\b', re.IGNORECASE)

UNDYING: Pattern = re.compile(r'\bundying\b', re.IGNORECASE)
PERSIST: Pattern = re.compile(r'\bpersist\b', re.IGNORECASE)
PHASING: Pattern = re.compile(r'\bphasing\b', re.IGNORECASE)
FLASH: Pattern = re.compile(r'\bflash\b', re.IGNORECASE)
TOXIC: Pattern = re.compile(r'toxic\s*\d+', re.IGNORECASE)

# =============================================================================
# RETURN TO BATTLEFIELD PATTERNS
# =============================================================================

RETURN_TO_BATTLEFIELD: Pattern = re.compile(r'return.*to the battlefield', re.IGNORECASE)
RETURN_IT_TO_BATTLEFIELD: Pattern = re.compile(r'return it to the battlefield', re.IGNORECASE)
RETURN_THAT_CARD_TO_BATTLEFIELD: Pattern = re.compile(r'return that card to the battlefield', re.IGNORECASE)
RETURN_THEM_TO_BATTLEFIELD: Pattern = re.compile(r'return them to the battlefield', re.IGNORECASE)
RETURN_THOSE_CARDS_TO_BATTLEFIELD: Pattern = re.compile(r'return those cards to the battlefield', re.IGNORECASE)

RETURN_TO_HAND: Pattern = re.compile(r'return.*to.*hand', re.IGNORECASE)
RETURN_YOU_CONTROL_TO_HAND: Pattern = re.compile(r'return target.*you control.*to.*hand', re.IGNORECASE)

# =============================================================================
# SCOPE & QUALIFIER PATTERNS
# =============================================================================

OTHER_CREATURES: Pattern = re.compile(r'other creature[s]?', re.IGNORECASE)
ALL_CREATURES: Pattern = re.compile(r'\ball creature[s]?\b', re.IGNORECASE)
ALL_PERMANENTS: Pattern = re.compile(r'\ball permanent[s]?\b', re.IGNORECASE)
ALL_SLIVERS: Pattern = re.compile(r'\ball sliver[s]?\b', re.IGNORECASE)

EQUIPPED_CREATURE: Pattern = re.compile(r'equipped creature', re.IGNORECASE)
ENCHANTED_CREATURE: Pattern = re.compile(r'enchanted creature', re.IGNORECASE)
ENCHANTED_PERMANENT: Pattern = re.compile(r'enchanted permanent', re.IGNORECASE)
ENCHANTED_ENCHANTMENT: Pattern = re.compile(r'enchanted enchantment', re.IGNORECASE)

# =============================================================================
# COMBAT PATTERNS
# =============================================================================

ATTACK: Pattern = re.compile(r'\battack[s]?\b', re.IGNORECASE)
ATTACKS: Pattern = re.compile(r'\battacks\b', re.IGNORECASE)
BLOCK: Pattern = re.compile(r'\bblock[s]?\b', re.IGNORECASE)
BLOCKS: Pattern = re.compile(r'\bblocks\b', re.IGNORECASE)
COMBAT_DAMAGE: Pattern = re.compile(r'combat damage', re.IGNORECASE)

WHENEVER_ATTACKS: Pattern = re.compile(r'whenever .* attacks', re.IGNORECASE)
WHEN_ATTACKS: Pattern = re.compile(r'when .* attacks', re.IGNORECASE)

# =============================================================================
# TYPE LINE PATTERNS
# =============================================================================

INSTANT: Pattern = re.compile(r'\bInstant\b', re.IGNORECASE)
SORCERY: Pattern = re.compile(r'\bSorcery\b', re.IGNORECASE)
ARTIFACT: Pattern = re.compile(r'\bArtifact\b', re.IGNORECASE)
ENCHANTMENT: Pattern = re.compile(r'\bEnchantment\b', re.IGNORECASE)
CREATURE: Pattern = re.compile(r'\bCreature\b', re.IGNORECASE)
PLANESWALKER: Pattern = re.compile(r'\bPlaneswalker\b', re.IGNORECASE)
LAND: Pattern = re.compile(r'\bLand\b', re.IGNORECASE)

AURA: Pattern = re.compile(r'\bAura\b', re.IGNORECASE)
EQUIPMENT: Pattern = re.compile(r'\bEquipment\b', re.IGNORECASE)
VEHICLE: Pattern = re.compile(r'\bVehicle\b', re.IGNORECASE)
SAGA: Pattern = re.compile(r'\bSaga\b', re.IGNORECASE)

NONCREATURE: Pattern = re.compile(r'noncreature', re.IGNORECASE)

# =============================================================================
# PATTERN BUILDER FUNCTIONS
# =============================================================================

def ownership_pattern(subject: str, owner: str = "you") -> Pattern:
    """
    Build ownership pattern like 'creatures you control', 'permanents opponent controls'.
    
    Args:
        subject: The card type (e.g., 'creature', 'permanent', 'artifact')
        owner: Controller ('you', 'opponent', 'they', etc.)
    
    Returns:
        Compiled regex pattern
    
    Examples:
        >>> ownership_pattern('creature', 'you')
        # Matches "creatures you control"
        >>> ownership_pattern('artifact', 'opponent')
        # Matches "artifacts opponent controls"
    """
    pattern = fr'{subject}[s]?\s+{owner}\s+control[s]?'
    return re.compile(pattern, re.IGNORECASE)


def grant_pattern(subject: str, verb: str, ability: str) -> Pattern:
    """
    Build grant pattern like 'creatures you control gain hexproof'.
    
    Args:
        subject: What gains the ability ('creatures you control', 'target creature', etc.)
        verb: Grant verb ('gain', 'has', 'get', etc.)
        ability: Ability granted ('hexproof', 'flying', 'ward', etc.)
    
    Returns:
        Compiled regex pattern
    
    Examples:
        >>> grant_pattern('creatures you control', 'gain', 'hexproof')
        # Matches "creatures you control gain hexproof"
    """
    pattern = fr'{subject}\s+{verb}[s]?\s+{ability}'
    return re.compile(pattern, re.IGNORECASE)


def token_creation_pattern(quantity: str, token_type: str) -> Pattern:
    """
    Build token creation pattern like 'create two 1/1 Soldier tokens'.
    
    Args:
        quantity: Number word or variable ('one', 'two', 'x', etc.)
        token_type: Token name ('treasure', 'food', 'soldier', etc.)
    
    Returns:
        Compiled regex pattern
    
    Examples:
        >>> token_creation_pattern('two', 'treasure')
        # Matches "create two Treasure tokens"
    """
    pattern = fr'create[s]?\s+(?:{quantity})\s+.*{token_type}\s+token'
    return re.compile(pattern, re.IGNORECASE)


def kindred_grant_pattern(tribe: str, ability: str) -> Pattern:
    """
    Build kindred grant pattern like 'knights you control gain protection'.
    
    Args:
        tribe: Creature type ('knight', 'elf', 'zombie', etc.)
        ability: Ability granted ('hexproof', 'protection', etc.)
    
    Returns:
        Compiled regex pattern
    
    Examples:
        >>> kindred_grant_pattern('knight', 'hexproof')
        # Matches "Knights you control gain hexproof"
    """
    pattern = fr'{tribe}[s]?\s+you\s+control.*\b{ability}\b'
    return re.compile(pattern, re.IGNORECASE)


def targeting_pattern(target: str, subject: str = None) -> Pattern:
    """
    Build targeting pattern like 'target creature you control'.
    
    Args:
        target: What is targeted ('player', 'opponent', 'creature', etc.)
        subject: Optional qualifier ('you control', 'opponent controls', etc.)
    
    Returns:
        Compiled regex pattern
    
    Examples:
        >>> targeting_pattern('creature', 'you control')
        # Matches "target creature you control"
        >>> targeting_pattern('opponent')
        # Matches "target opponent"
    """
    if subject:
        pattern = fr'target\s+{target}\s+{subject}'
    else:
        pattern = fr'target\s+{target}'
    return re.compile(pattern, re.IGNORECASE)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Ownership
    'YOU_CONTROL', 'THEY_CONTROL', 'OPPONENT_CONTROL',
    'CREATURE_YOU_CONTROL', 'PERMANENT_YOU_CONTROL', 'ARTIFACT_YOU_CONTROL',
    'ENCHANTMENT_YOU_CONTROL',
    
    # Grant verbs
    'GAIN', 'HAS', 'HAVE', 'GET', 'GRANT_VERBS',
    
    # Targeting
    'TARGET_PLAYER', 'TARGET_OPPONENT', 'TARGET_CREATURE', 'TARGET_PERMANENT',
    'TARGET_ARTIFACT', 'TARGET_ENCHANTMENT', 'EACH_PLAYER', 'EACH_OPPONENT',
    'TARGET_YOU_CONTROL',
    
    # Protection abilities
    'HEXPROOF', 'SHROUD', 'INDESTRUCTIBLE', 'WARD', 'PROTECTION_FROM',
    'PROTECTION_ABILITIES', 'CANT_HAVE_PROTECTION', 'LOSE_PROTECTION',
    
    # Draw
    'DRAW_A_CARD', 'DRAW_CARDS', 'DRAW',
    
    # Tokens
    'CREATE_TOKEN', 'PUT_TOKEN',
    'CREATE_TREASURE', 'CREATE_FOOD', 'CREATE_CLUE', 'CREATE_BLOOD',
    
    # Counters
    'PLUS_ONE_COUNTER', 'MINUS_ONE_COUNTER', 'LOYALTY_COUNTER', 'PROLIFERATE',
    'ONE_OR_MORE_COUNTERS', 'ONE_OR_MORE_PLUS_ONE_COUNTERS', 'IF_HAD_COUNTERS', 'WITH_COUNTERS_ON_THEM',
    
    # Removal
    'SACRIFICE', 'SACRIFICED', 'DESTROY', 'EXILE', 'EXILED',
    'SACRIFICE_DRAW', 'SACRIFICE_COLON_DRAW', 'SACRIFICED_COMMA_DRAW',
    'EXILE_RETURN_BATTLEFIELD',
    
    # Discard
    'DISCARD_A_CARD', 'DISCARD_YOUR_HAND', 'YOU_DISCARD',
    'WHENEVER_YOU_DISCARD', 'IF_YOU_DISCARDED', 'WHEN_YOU_DISCARD', 'FOR_EACH_DISCARDED',
    'TARGET_PLAYER_DISCARDS', 'TARGET_OPPONENT_DISCARDS', 'EACH_PLAYER_DISCARDS',
    'EACH_OPPONENT_DISCARDS', 'THAT_PLAYER_DISCARDS',
    'ADDITIONAL_COST_DISCARD', 'ADDITIONAL_COST_DISCARD_SHORT', 'MADNESS',
    
    # Damage & Life Loss
    'DEALS_ONE_DAMAGE', 'EXACTLY_ONE_DAMAGE', 'LOSES_ONE_LIFE',
    
    # Cost reduction
    'COST_LESS', 'COST_LESS_TO_CAST', 'WITH_X_IN_COST', 'AFFINITY_FOR', 'SPELLS_COST', 'SPELLS_YOU_CAST_COST',
    
    # Monarch
    'BECOME_MONARCH', 'IS_MONARCH', 'WAS_MONARCH', 'YOU_ARE_MONARCH',
    'YOU_BECOME_MONARCH', 'CANT_BECOME_MONARCH',
    
    # Keywords
    'PARTNER_BASIC', 'PARTNER_WITH', 'PARTNER_SURVIVORS', 'PARTNER_FATHER_SON',
    'FLYING', 'VIGILANCE', 'TRAMPLE', 'HASTE', 'LIFELINK', 'DEATHTOUCH',
    'DOUBLE_STRIKE', 'FIRST_STRIKE', 'MENACE', 'REACH',
    'UNDYING', 'PERSIST', 'PHASING', 'FLASH', 'TOXIC',
    
    # Return
    'RETURN_TO_BATTLEFIELD', 'RETURN_IT_TO_BATTLEFIELD', 'RETURN_THAT_CARD_TO_BATTLEFIELD',
    'RETURN_THEM_TO_BATTLEFIELD', 'RETURN_THOSE_CARDS_TO_BATTLEFIELD',
    'RETURN_TO_HAND', 'RETURN_YOU_CONTROL_TO_HAND',
    
    # Scope
    'OTHER_CREATURES', 'ALL_CREATURES', 'ALL_PERMANENTS', 'ALL_SLIVERS',
    'EQUIPPED_CREATURE', 'ENCHANTED_CREATURE', 'ENCHANTED_PERMANENT', 'ENCHANTED_ENCHANTMENT',
    
    # Combat
    'ATTACK', 'ATTACKS', 'BLOCK', 'BLOCKS', 'COMBAT_DAMAGE',
    'WHENEVER_ATTACKS', 'WHEN_ATTACKS',
    
    # Type line
    'INSTANT', 'SORCERY', 'ARTIFACT', 'ENCHANTMENT', 'CREATURE', 'PLANESWALKER', 'LAND',
    'AURA', 'EQUIPMENT', 'VEHICLE', 'SAGA', 'NONCREATURE',
    
    # Builders
    'ownership_pattern', 'grant_pattern', 'token_creation_pattern',
    'kindred_grant_pattern', 'targeting_pattern',
]
