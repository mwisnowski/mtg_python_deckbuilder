#!/usr/bin/env python3
"""
Debug test to trace the exclude flow end-to-end
"""

import sys
import os

# Add the code directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.builder import DeckBuilder

def test_direct_exclude_filtering():
    """Test exclude filtering directly on a DeckBuilder instance"""
    
    print("=== Direct DeckBuilder Exclude Test ===")
    
    # Create a builder instance
    builder = DeckBuilder()
    
    # Set exclude cards directly
    exclude_list = [
        "Sol Ring",
        "Byrke, Long Ear of the Law", 
        "Burrowguard Mentor",
        "Hare Apparent"
    ]
    
    print(f"1. Setting exclude_cards: {exclude_list}")
    builder.exclude_cards = exclude_list
    
    print(f"2. Checking attribute: {getattr(builder, 'exclude_cards', 'NOT SET')}")
    print(f"3. hasattr check: {hasattr(builder, 'exclude_cards')}")
    
    # Mock some cards in the dataframe
    import pandas as pd
    test_cards = pd.DataFrame([
        {"name": "Sol Ring", "color_identity": "", "type_line": "Artifact"},
        {"name": "Byrke, Long Ear of the Law", "color_identity": "W", "type_line": "Legendary Creature"},
        {"name": "Burrowguard Mentor", "color_identity": "W", "type_line": "Creature"},
        {"name": "Hare Apparent", "color_identity": "W", "type_line": "Creature"},
        {"name": "Lightning Bolt", "color_identity": "R", "type_line": "Instant"},
    ])
    
    print(f"4. Test cards before filtering: {len(test_cards)}")
    print(f"   Cards: {test_cards['name'].tolist()}")
    
    # Clear any cached dataframes to force rebuild
    builder._combined_cards_df = None
    builder._full_cards_df = None
    
    # Mock the files_to_load to avoid CSV loading issues
    builder.files_to_load = []
    
    # Call setup_dataframes, but since files_to_load is empty, we need to manually set the data
    # Let's instead test the filtering logic more directly
    
    print("5. Setting up test data and calling exclude filtering directly...")
    
    # Set the combined dataframe and call the filtering logic
    builder._combined_cards_df = test_cards.copy()
    
    # Now manually trigger the exclude filtering logic
    combined = builder._combined_cards_df.copy()
    
    # This is the actual exclude filtering code from setup_dataframes
    if hasattr(builder, 'exclude_cards') and builder.exclude_cards:
        print("   DEBUG: Exclude filtering condition met!")
        try:
            from code.deck_builder.include_exclude_utils import normalize_card_name
            
            # Find name column
            name_col = None
            if 'name' in combined.columns:
                name_col = 'name'
            elif 'Card Name' in combined.columns:
                name_col = 'Card Name'
                
            if name_col is not None:
                excluded_matches = []
                original_count = len(combined)
                
                # Normalize exclude patterns for matching
                normalized_excludes = {normalize_card_name(pattern): pattern for pattern in builder.exclude_cards}
                print(f"   Normalized excludes: {normalized_excludes}")
                
                # Create a mask to track which rows to exclude
                exclude_mask = pd.Series([False] * len(combined), index=combined.index)
                
                # Check each card against exclude patterns
                for idx, card_name in combined[name_col].items():
                    if not exclude_mask[idx]:  # Only check if not already excluded
                        normalized_card = normalize_card_name(str(card_name))
                        print(f"   Checking card: '{card_name}' -> normalized: '{normalized_card}'")
                        
                        # Check if this card matches any exclude pattern
                        for normalized_exclude, original_pattern in normalized_excludes.items():
                            if normalized_card == normalized_exclude:
                                print(f"   MATCH: '{card_name}' matches pattern '{original_pattern}'")
                                excluded_matches.append({
                                    'pattern': original_pattern,
                                    'matched_card': str(card_name),
                                    'similarity': 1.0
                                })
                                exclude_mask[idx] = True
                                break  # Found a match, no need to check other patterns
                
                # Apply the exclusions in one operation
                if exclude_mask.any():
                    combined = combined[~exclude_mask].copy()
                    print(f"   Excluded {len(excluded_matches)} cards from pool (was {original_count}, now {len(combined)})")
                else:
                    print(f"   No cards matched exclude patterns: {', '.join(builder.exclude_cards)}")
            else:
                print("   No recognizable name column found")
        except Exception as e:
            print(f"   Error during exclude filtering: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("   DEBUG: Exclude filtering condition NOT met!")
        print(f"   hasattr: {hasattr(builder, 'exclude_cards')}")
        print(f"   exclude_cards value: {getattr(builder, 'exclude_cards', 'NOT SET')}")
        print(f"   exclude_cards bool: {bool(getattr(builder, 'exclude_cards', None))}")
    
    # Update the builder's dataframe
    builder._combined_cards_df = combined
    
    print(f"6. Cards after filtering: {len(combined)}")
    print(f"   Remaining cards: {combined['name'].tolist()}")
    
    # Check if exclusions worked
    remaining_cards = combined['name'].tolist()
    failed_exclusions = []
    
    for exclude_card in exclude_list:
        if exclude_card in remaining_cards:
            failed_exclusions.append(exclude_card)
            print(f"   ❌ {exclude_card} was NOT excluded!")
        else:
            print(f"   ✅ {exclude_card} was properly excluded")
    
    if failed_exclusions:
        print(f"\n❌ FAILED: {len(failed_exclusions)} cards were not excluded: {failed_exclusions}")
        assert False
    else:
        print(f"\n✅ SUCCESS: All {len(exclude_list)} cards were properly excluded")

if __name__ == "__main__":
    success = test_direct_exclude_filtering()
    sys.exit(0 if success else 1)
