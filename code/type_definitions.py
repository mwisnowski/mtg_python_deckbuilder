from __future__ import annotations

from typing import Dict, List, TypedDict, Union, Optional, Literal
import pandas as pd

class CardDict(TypedDict):
    """Type definition for card dictionary structure used in deck_builder.py.
    
    Contains all the necessary fields to represent a Magic: The Gathering card
    in the deck building process.
    """
    name: str
    type: str
    manaCost: Union[str, None]
    manaValue: int

class CommanderDict(TypedDict):
    """Type definition for commander dictionary structure used in deck_builder.py.
    
    Contains all the necessary fields to represent a commander card and its
    associated metadata.
    """
    Commander_Name: str
    Mana_Cost: str
    Mana_Value: int
    Color_Identity: str
    Colors: List[str]
    Type: str
    Creature_Types: str
    Text: str
    Power: int
    Toughness: int
    Themes: List[str]
    CMC: float

# Type alias for price cache dictionary used in price_checker.py
PriceCache = Dict[str, float]

# DataFrame type aliases for different card categories
CardLibraryDF = pd.DataFrame
CommanderDF = pd.DataFrame
LandDF = pd.DataFrame
ArtifactDF = pd.DataFrame
CreatureDF = pd.DataFrame
NonCreatureDF = pd.DataFrame
EnchantmentDF = pd.DataFrame
InstantDF = pd.DataFrame
PlaneswalkerDF = pd.DataFrame
NonPlaneswalkerDF = pd.DataFrame
SorceryDF = pd.DataFrame

# Bracket compliance typing
Verdict = Literal["PASS", "WARN", "FAIL"]

class CategoryFinding(TypedDict, total=False):
    count: int
    limit: Optional[int]
    flagged: List[str]
    status: Verdict
    notes: List[str]

class ComplianceReport(TypedDict, total=False):
    bracket: str
    level: int
    enforcement: Literal["validate", "prefer", "strict"]
    overall: Verdict
    commander_flagged: bool
    categories: Dict[str, CategoryFinding]
    combos: List[Dict[str, Union[str, bool]]]
    list_versions: Dict[str, Optional[str]]
    messages: List[str]