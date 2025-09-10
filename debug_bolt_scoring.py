#!/usr/bin/env python3
"""Debug the normalization and scoring for Lightning Bolt specifically"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.include_exclude_utils import normalize_punctuation, fuzzy_match_card_name
import pandas as pd

# Test normalize_punctuation function
print("=== Testing normalize_punctuation ===")
test_names = ["Lightning Bolt", "lightning bolt", "Lightning-Bolt", "Lightning, Bolt"]
for name in test_names:
    normalized = normalize_punctuation(name)
    print(f"'{name}' → '{normalized}'")

# Load cards and test fuzzy matching
print(f"\n=== Loading cards ===")
cards_df = pd.read_csv('csv_files/cards.csv')
available_cards = set(cards_df['name'].dropna().unique())

print(f"Cards loaded: {len(available_cards)}")
print(f"Lightning Bolt in cards: {'Lightning Bolt' in available_cards}")

# Test fuzzy matching for 'bolt' 
print(f"\n=== Testing fuzzy match for 'bolt' ===")
result = fuzzy_match_card_name('bolt', available_cards)
print(f"Input: bolt")
print(f"Matched: {result.matched_name}")
print(f"Confidence: {result.confidence:.3f}")
print(f"Auto-accepted: {result.auto_accepted}")
print(f"Top suggestions: {result.suggestions[:5]}")

# Test fuzzy matching for 'lightn'
print(f"\n=== Testing fuzzy match for 'lightn' ===")
result = fuzzy_match_card_name('lightn', available_cards)
print(f"Input: lightn")
print(f"Matched: {result.matched_name}")
print(f"Confidence: {result.confidence:.3f}")
print(f"Auto-accepted: {result.auto_accepted}")
print(f"Top suggestions: {result.suggestions[:5]}")

# Manual check of scores for Lightning cards
print(f"\n=== Manual scoring for Lightning cards ===")
from difflib import SequenceMatcher

input_test = "lightn"
lightning_cards = [name for name in available_cards if 'lightning' in name.lower()][:10]

for card in lightning_cards:
    normalized_card = normalize_punctuation(card)
    score = SequenceMatcher(None, input_test.lower(), normalized_card.lower()).ratio()
    print(f"{score:.3f} - {card}")
