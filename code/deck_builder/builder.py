from __future__ import annotations

import math
import numpy as np
import os
import random
import time
from functools import lru_cache
from typing import Dict, List, Optional, Union

import inquirer.prompt
import keyboard
import pandas as pd
import pprint
from fuzzywuzzy import process
from tqdm import tqdm

from settings import CSV_DIRECTORY, MULTIPLE_COPY_CARDS
from .builder_constants import (
    BASIC_LANDS, CARD_TYPES, DEFAULT_NON_BASIC_LAND_SLOTS,
    COMMANDER_CSV_PATH, FUZZY_MATCH_THRESHOLD, MAX_FUZZY_CHOICES, FETCH_LAND_DEFAULT_COUNT,
    COMMANDER_POWER_DEFAULT, COMMANDER_TOUGHNESS_DEFAULT, COMMANDER_MANA_COST_DEFAULT,
    COMMANDER_MANA_VALUE_DEFAULT, COMMANDER_TYPE_DEFAULT, COMMANDER_TEXT_DEFAULT, 
    THEME_PRIORITY_BONUS, THEME_POOL_SIZE_MULTIPLIER, DECK_DIRECTORY,
    COMMANDER_COLOR_IDENTITY_DEFAULT, COMMANDER_COLORS_DEFAULT, COMMANDER_TAGS_DEFAULT, 
    COMMANDER_THEMES_DEFAULT, COMMANDER_CREATURE_TYPES_DEFAULT, DUAL_LAND_TYPE_MAP,
    CSV_READ_TIMEOUT, CSV_PROCESSING_BATCH_SIZE, CSV_VALIDATION_RULES, CSV_REQUIRED_COLUMNS,
    STAPLE_LAND_CONDITIONS, TRIPLE_LAND_TYPE_MAP, MISC_LAND_MAX_COUNT, MISC_LAND_MIN_COUNT,
    MISC_LAND_POOL_SIZE, LAND_REMOVAL_MAX_ATTEMPTS, PROTECTED_LANDS,
    MANA_COLORS, MANA_PIP_PATTERNS, THEME_WEIGHT_MULTIPLIER
)
from . import builder_utils
from file_setup import setup_utils
from input_handler import InputHandler
from exceptions import (
    BasicLandCountError,
    BasicLandError,
    CommanderMoveError,
    CardTypeCountError,
    CommanderColorError,
    CommanderSelectionError, 
    CommanderValidationError,
    CSVError,
    CSVReadError,
    CSVTimeoutError,
    CSVValidationError,
    DataFrameValidationError,
    DuplicateCardError,
    DeckBuilderError,
    EmptyDataFrameError,
    FetchLandSelectionError,
    FetchLandValidationError,
    IdealDeterminationError,
    LandRemovalError,
    LibraryOrganizationError,
    LibrarySortError,
    PriceAPIError,
    PriceConfigurationError,
    PriceLimitError, 
    PriceTimeoutError,
    PriceValidationError,
    ThemeSelectionError,
    ThemeWeightError,
    StapleLandError,
    ManaPipError,
    ThemeTagError,
    ThemeWeightingError,
    ThemePoolError
)
from type_definitions import (
    CommanderDict,
    CardLibraryDF,
    CommanderDF,
    LandDF,
    ArtifactDF,
    CreatureDF,
    NonCreatureDF,
    PlaneswalkerDF,
    NonPlaneswalkerDF)

import logging_util

# Create logger for this module
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# Try to import scrython and price_checker
try:
    import scrython
    from price_check import PriceChecker
    use_scrython = True
except ImportError:
    scrython = None
    PriceChecker = None
    use_scrython = False
    logger.warning("Scrython is not installed. Price checking features will be unavailable."
                    )

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', 50)