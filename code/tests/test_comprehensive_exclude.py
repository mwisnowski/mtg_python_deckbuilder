#!/usr/bin/env python3
"""
Advanced integration test for exclude functionality.
Tests that excluded cards are completely removed from all dataframe sources.
"""

from code.deck_builder.builder import DeckBuilder

def test_comprehensive_exclude_filtering():
    """Test that excluded cards are completely removed from all dataframe sources."""
    print("=== Comprehensive Exclude Filtering Test ===")
    
    # Create a test builder
    builder = DeckBuilder(headless=True, output_func=lambda x: print(f"Builder: {x}"), input_func=lambda x: "")
    
    # Set some common exclude patterns
    exclude_list = ["Sol Ring", "Rhystic Study", "Cyclonic Rift"]
    builder.exclude_cards = exclude_list
    print(f"Testing exclusion of: {exclude_list}")
    
    # Try to set up a simple commander to get dataframes loaded
    try:
        # Load commander data and select a commander first
        cmd_df = builder.load_commander_data()
        atraxa_row = cmd_df[cmd_df["name"] == "Atraxa, Praetors' Voice"]
        if not atraxa_row.empty:
            builder._apply_commander_selection(atraxa_row.iloc[0])
        else:
            # Fallback to any commander for testing
            if not cmd_df.empty:
                builder._apply_commander_selection(cmd_df.iloc[0])
                print(f"Using fallback commander: {builder.commander_name}")
        
        # Now determine color identity
        builder.determine_color_identity()
        
        # This should trigger the exclude filtering
        combined_df = builder.setup_dataframes()
        
        # Check that excluded cards are not in the combined dataframe
        print(f"\n1. Checking combined dataframe (has {len(combined_df)} cards)...")
        for exclude_card in exclude_list:
            if 'name' in combined_df.columns:
                matches = combined_df[combined_df['name'].str.contains(exclude_card, case=False, na=False)]
                if len(matches) == 0:
                    print(f"   ✓ '{exclude_card}' correctly excluded from combined_df")
                else:
                    print(f"   ✗ '{exclude_card}' still found in combined_df: {matches['name'].tolist()}")
        
        # Check that excluded cards are not in the full dataframe either
        print(f"\n2. Checking full dataframe (has {len(builder._full_cards_df)} cards)...")
        for exclude_card in exclude_list:
            if builder._full_cards_df is not None and 'name' in builder._full_cards_df.columns:
                matches = builder._full_cards_df[builder._full_cards_df['name'].str.contains(exclude_card, case=False, na=False)]
                if len(matches) == 0:
                    print(f"   ✓ '{exclude_card}' correctly excluded from full_df")
                else:
                    print(f"   ✗ '{exclude_card}' still found in full_df: {matches['name'].tolist()}")
        
        # Try to manually lookup excluded cards (this should fail)
        print("\n3. Testing manual card lookups...")
        for exclude_card in exclude_list:
            # Simulate what the builder does when looking up cards
            df_src = builder._full_cards_df if builder._full_cards_df is not None else builder._combined_cards_df
            if df_src is not None and not df_src.empty and 'name' in df_src.columns:
                lookup_result = df_src[df_src['name'].astype(str).str.lower() == exclude_card.lower()]
                if lookup_result.empty:
                    print(f"   ✓ '{exclude_card}' correctly not found in lookup")
                else:
                    print(f"   ✗ '{exclude_card}' incorrectly found in lookup: {lookup_result['name'].tolist()}")
        
        print("\n=== Test Complete ===")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        print(traceback.format_exc())
        assert False
 
