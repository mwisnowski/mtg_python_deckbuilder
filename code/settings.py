from __future__ import annotations

# Standard library imports
import os
from typing import Dict, List, Optional

# ----------------------------------------------------------------------------------
# COLOR CONSTANTS
# ----------------------------------------------------------------------------------
# NOTE:
# Existing code in setup uses an ordered list (green before red) to align indices
# with the parallel COLOR_ABRV list. The previously defined COLORS list had a
# different ordering (red before green) which made it unsuitable for index based
# mapping. To avoid subtle bugs we expose two explicit constants:
#   SETUP_COLORS  -> ordering required for setup / abbreviation mapping
#   COLORS        -> legacy superset including 'commander' (kept for compatibility)

SETUP_COLORS: List[str] = [
    'colorless', 'white', 'blue', 'black', 'green', 'red',
    'azorius', 'orzhov', 'selesnya', 'boros', 'dimir',
    'simic', 'izzet', 'golgari', 'rakdos', 'gruul',
    'bant', 'esper', 'grixis', 'jund', 'naya',
    'abzan', 'jeskai', 'mardu', 'sultai', 'temur',
    'dune', 'glint', 'ink', 'witch', 'yore', 'wubrg'
]

# Legacy constant (includes 'commander', preserves previous external usage)
COLORS: List[str] = [
    *SETUP_COLORS,
    'commander'
]

COLOR_ABRV: List[str] = [
    'Colorless', 'W', 'U', 'B', 'G', 'R',
    'U, W', 'B, W', 'G, W', 'R, W', 'B, U',
    'G, U', 'R, U', 'B, G', 'B, R', 'G, R',
    'G, U, W', 'B, U, W', 'B, R, U', 'B, G, R', 'G, R, W',
    'B, G, W', 'R, U, W', 'B, R, W', 'B, G, U', 'G, R, U',
    'B, G, R, W', 'B, G, R, U', 'G, R, U, W', 'B, G, U, W',
    'B, R, U, W', 'B, G, R, U, W'
]

# Convenience mapping from long color name to primary abbreviation
PRIMARY_COLOR_ABBR_MAP: Dict[str, str] = {
    'colorless': 'Colorless', 'white': 'W', 'blue': 'U', 'black': 'B', 'green': 'G', 'red': 'R'
}

# ----------------------------------------------------------------------------------
# CARD / DATAFRAME COLUMN CONSTANTS
# ----------------------------------------------------------------------------------
# Unified column definition used across setup, tagging, and deck building modules.
# This consolidates previously duplicated lists: COLUMN_ORDER, TAGGED_COLUMN_ORDER,
# REQUIRED_COLUMNS (tag_constants), and CSV_REQUIRED_COLUMNS (builder_constants).
CARD_DATA_COLUMNS: List[str] = [
    'name', 'faceName', 'edhrecRank', 'colorIdentity', 'colors',
    'manaCost', 'manaValue', 'type', 'creatureTypes', 'text',
    'power', 'toughness', 'keywords', 'themeTags', 'layout', 'side'
]

# Alias for semantic clarity in different contexts
REQUIRED_CARD_COLUMNS = CARD_DATA_COLUMNS  # Validation
CARD_COLUMN_ORDER = CARD_DATA_COLUMNS      # Output / ordering

# ----------------------------------------------------------------------------------
# MENU / UI CONSTANTS
# ----------------------------------------------------------------------------------
MAIN_MENU_ITEMS: List[str] = ['Build A Deck', 'Setup CSV Files', 'Tag CSV Files', 'Quit']
SETUP_MENU_ITEMS: List[str] = ['Initial Setup', 'Regenerate CSV', 'Main Menu']

CSV_DIRECTORY: str = 'csv_files'

# ----------------------------------------------------------------------------------
# DATAFRAME NA HANDLING
# ----------------------------------------------------------------------------------
FILL_NA_COLUMNS: Dict[str, Optional[str]] = {
    'colorIdentity': 'Colorless',  # Default color identity for cards without one
    'faceName': None  # Use card's name column value when face name is not available
}

# ----------------------------------------------------------------------------------
# SPECIAL CARD EXCEPTIONS
# ----------------------------------------------------------------------------------
MULTIPLE_COPY_CARDS = ['Cid, Timeless Artificer', 'Dragon\'s Approach', 'Hare Apparent', 'Nazgûl',
                       'Persistent Petitioners', 'Rat Colony', 'Relentless Rats', 'Seven Dwarves',
                       'Shadowborn Apostle', 'Slime Against Humanity','Tempest Hawk', 'Templar Knights']

# Backwards compatibility exports (older modules may still import these names)
COLUMN_ORDER = CARD_COLUMN_ORDER
TAGGED_COLUMN_ORDER = CARD_COLUMN_ORDER
REQUIRED_COLUMNS = REQUIRED_CARD_COLUMNS

MAIN_MENU_ITEMS: List[str] = ['Build A Deck', 'Setup CSV Files', 'Tag CSV Files', 'Quit']

SETUP_MENU_ITEMS: List[str] = ['Initial Setup', 'Regenerate CSV', 'Main Menu']

CSV_DIRECTORY: str = 'csv_files'
CARD_FILES_DIRECTORY: str = 'card_files'  # Parquet files for consolidated card data

# Configuration for handling null/NA values in DataFrame columns
FILL_NA_COLUMNS: Dict[str, Optional[str]] = {
    'colorIdentity': 'Colorless',  # Default color identity for cards without one
    'faceName': None  # Use card's name column value when face name is not available
}

# ----------------------------------------------------------------------------------
# ALL CARDS CONSOLIDATION FEATURE FLAG
# ----------------------------------------------------------------------------------

# Enable use of consolidated all_cards.parquet file (default: True)
# Set to False to disable and fall back to individual CSV file loading
USE_ALL_CARDS_FILE = os.getenv('USE_ALL_CARDS_FILE', '1').lower() not in ('0', 'false', 'off', 'disabled')

# ----------------------------------------------------------------------------------
# TAGGING REFINEMENT FEATURE FLAGS (M1-M5)
# ----------------------------------------------------------------------------------

# M1: Enable keyword normalization and singleton pruning (completed)
TAG_NORMALIZE_KEYWORDS = os.getenv('TAG_NORMALIZE_KEYWORDS', '1').lower() not in ('0', 'false', 'off', 'disabled')

# M2: Enable protection grant detection (completed)
TAG_PROTECTION_GRANTS = os.getenv('TAG_PROTECTION_GRANTS', '1').lower() not in ('0', 'false', 'off', 'disabled')

# M3: Enable metadata/theme partition (completed)
TAG_METADATA_SPLIT = os.getenv('TAG_METADATA_SPLIT', '1').lower() not in ('0', 'false', 'off', 'disabled')

# M5: Enable protection scope filtering in deck builder (completed - Phase 1-3, in progress Phase 4+)
TAG_PROTECTION_SCOPE = os.getenv('TAG_PROTECTION_SCOPE', '1').lower() not in ('0', 'false', 'off', 'disabled')