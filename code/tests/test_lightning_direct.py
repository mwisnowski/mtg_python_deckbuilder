#!/usr/bin/env python3
"""Test Lightning Bolt directly - M4: Updated for Parquet"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.include_exclude_utils import fuzzy_match_card_name
import pandas as pd
from path_util import get_processed_cards_path

# M4: Load from Parquet instead of CSV
cards_df = pd.read_parquet(get_processed_cards_path())
available_cards = set(cards_df['name'].dropna().unique())

# Test if Lightning Bolt gets the right score
result = fuzzy_match_card_name('bolt', available_cards)
print(f"'bolt' matches: {result.suggestions[:5]}")

result = fuzzy_match_card_name('lightn', available_cards)  
print(f"'lightn' matches: {result.suggestions[:5]}")

# Check if Lightning Bolt is in the suggestions
if 'Lightning Bolt' in result.suggestions:
    print(f"Lightning Bolt is suggestion #{result.suggestions.index('Lightning Bolt') + 1}")
else:
    print("Lightning Bolt NOT in suggestions!")
    
# Test a few more obvious ones
result = fuzzy_match_card_name('lightning', available_cards)
print(f"'lightning' matches: {result.suggestions[:3]}")

result = fuzzy_match_card_name('warp', available_cards)
print(f"'warp' matches: {result.suggestions[:3]}")

# Also test the exact card name to make sure it's working
result = fuzzy_match_card_name('Lightning Bolt', available_cards)
print(f"'Lightning Bolt' exact: {result.matched_name} (confidence: {result.confidence:.3f})")
