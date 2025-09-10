#!/usr/bin/env python3
"""
Quick test to verify exclude filtering is working properly.
"""

import pandas as pd
from code.deck_builder.include_exclude_utils import normalize_card_name

def test_exclude_filtering():
    """Test that our exclude filtering logic works correctly"""
    
    # Simulate the cards from user's test case
    test_cards_df = pd.DataFrame([
        {"name": "Sol Ring", "other_col": "value1"},
        {"name": "Byrke, Long Ear of the Law", "other_col": "value2"},
        {"name": "Burrowguard Mentor", "other_col": "value3"},
        {"name": "Hare Apparent", "other_col": "value4"},
        {"name": "Lightning Bolt", "other_col": "value5"},
        {"name": "Counterspell", "other_col": "value6"},
    ])
    
    # User's exclude list from their test
    exclude_list = [
        "Sol Ring",
        "Byrke, Long Ear of the Law", 
        "Burrowguard Mentor",
        "Hare Apparent"
    ]
    
    print("Original cards:")
    print(test_cards_df['name'].tolist())
    print(f"\nExclude list: {exclude_list}")
    
    # Apply the same filtering logic as in builder.py
    if exclude_list:
        normalized_excludes = {normalize_card_name(name): name for name in exclude_list}
        print(f"\nNormalized excludes: {list(normalized_excludes.keys())}")
        
        # Create exclude mask
        exclude_mask = test_cards_df['name'].apply(
            lambda x: normalize_card_name(x) not in normalized_excludes
        )
        
        print(f"\nExclude mask: {exclude_mask.tolist()}")
        
        # Apply filtering
        filtered_df = test_cards_df[exclude_mask].copy()
        
        print(f"\nFiltered cards: {filtered_df['name'].tolist()}")
        
        # Verify results
        excluded_cards = test_cards_df[~exclude_mask]['name'].tolist()
        print(f"Cards that were excluded: {excluded_cards}")
        
        # Check if all exclude cards were properly removed
        remaining_cards = filtered_df['name'].tolist()
        for exclude_card in exclude_list:
            if exclude_card in remaining_cards:
                print(f"ERROR: {exclude_card} was NOT excluded!")
                return False
            else:
                print(f"✓ {exclude_card} was properly excluded")
        
        print(f"\n✓ SUCCESS: All {len(exclude_list)} cards were properly excluded")
        print(f"✓ Remaining cards: {len(remaining_cards)} out of {len(test_cards_df)}")
        return True
    
    return False

if __name__ == "__main__":
    test_exclude_filtering()
