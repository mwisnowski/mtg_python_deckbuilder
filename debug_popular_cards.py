#!/usr/bin/env python3
"""Debug what specific Lightning/Bolt cards exist"""

import pandas as pd

cards_df = pd.read_csv('csv_files/cards.csv')

print("=== Lightning cards that start with 'Light' ===")
lightning_prefix = cards_df[cards_df['name'].str.lower().str.startswith('lightning', na=False)]['name'].unique()
for card in sorted(lightning_prefix):
    print(f"  - {card}")

print(f"\n=== Cards containing 'bolt' ===")
bolt_cards = cards_df[cards_df['name'].str.contains('bolt', case=False, na=False)]['name'].unique()
for card in sorted(bolt_cards):
    print(f"  - {card}")

print(f"\n=== Cards containing 'warp' ===")  
warp_cards = cards_df[cards_df['name'].str.contains('warp', case=False, na=False)]['name'].unique()
for card in sorted(warp_cards):
    print(f"  - {card}")

print(f"\n=== Manual test of 'lightn' against Lightning cards ===")
test_input = "lightn"
lightning_scores = []
from difflib import SequenceMatcher

for card in lightning_prefix:
    score = SequenceMatcher(None, test_input.lower(), card.lower()).ratio()
    lightning_scores.append((score, card))

lightning_scores.sort(key=lambda x: x[0], reverse=True)
print("Top Lightning matches for 'lightn':")
for score, card in lightning_scores[:5]:
    print(f"  {score:.3f} - {card}")
