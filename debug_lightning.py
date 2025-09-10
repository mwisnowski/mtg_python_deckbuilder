#!/usr/bin/env python3
"""Debug what Lightning cards are in the dataset"""

import pandas as pd

# Load the cards CSV
cards_df = pd.read_csv('csv_files/cards.csv')
print(f"Total cards loaded: {len(cards_df)}")

# Find cards that contain "light" (case insensitive)
light_cards = cards_df[cards_df['name'].str.contains('light', case=False, na=False)]['name'].unique()
print(f"\nCards containing 'light': {len(light_cards)}")
for card in sorted(light_cards)[:20]:  # Show first 20
    print(f"  - {card}")

# Find cards that start with "light" 
light_start = cards_df[cards_df['name'].str.lower().str.startswith('light', na=False)]['name'].unique()
print(f"\nCards starting with 'Light': {len(light_start)}")
for card in sorted(light_start):
    print(f"  - {card}")

# Find specific Lightning cards
lightning_cards = cards_df[cards_df['name'].str.contains('lightning', case=False, na=False)]['name'].unique()
print(f"\nCards containing 'Lightning': {len(lightning_cards)}")
for card in sorted(lightning_cards):
    print(f"  - {card}")

print(f"\nTesting direct matches for 'lightn':")
test_input = "lightn"
candidates = []
for name in cards_df['name'].dropna().unique():
    # Test similarity to lightn
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, test_input.lower(), name.lower()).ratio()
    if similarity > 0.6:
        candidates.append((similarity, name))

# Sort by similarity
candidates.sort(key=lambda x: x[0], reverse=True)
print("Top 10 matches for 'lightn':")
for score, name in candidates[:10]:
    print(f"  {score:.3f} - {name}")
