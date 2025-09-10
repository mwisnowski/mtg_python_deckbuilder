#!/usr/bin/env python3
"""
Test script to verify that card constants refactoring works correctly.
"""

from code.deck_builder.include_exclude_utils import fuzzy_match_card_name

# Test data - sample card names
sample_cards = [
    'Lightning Bolt',
    'Lightning Strike', 
    'Lightning Helix',
    'Chain Lightning',
    'Lightning Axe',
    'Lightning Volley',
    'Sol Ring',
    'Counterspell',
    'Chaos Warp',
    'Swords to Plowshares',
    'Path to Exile',
    'Volcanic Bolt',
    'Galvanic Bolt'
]

def test_fuzzy_matching():
    """Test fuzzy matching with various inputs."""
    test_cases = [
        ('bolt', 'Lightning Bolt'),  # Should prioritize Lightning Bolt
        ('lightning', 'Lightning Bolt'),  # Should prioritize Lightning Bolt
        ('sol', 'Sol Ring'),  # Should prioritize Sol Ring
        ('counter', 'Counterspell'),  # Should prioritize Counterspell
        ('chaos', 'Chaos Warp'),  # Should prioritize Chaos Warp
        ('swords', 'Swords to Plowshares'),  # Should prioritize Swords to Plowshares
    ]
    
    print("Testing fuzzy matching after constants refactoring:")
    print("-" * 60)
    
    for input_name, expected in test_cases:
        result = fuzzy_match_card_name(input_name, sample_cards)
        
        print(f"Input: '{input_name}'")
        print(f"Expected: {expected}")
        print(f"Matched: {result.matched_name}")
        print(f"Confidence: {result.confidence:.3f}")
        print(f"Auto-accepted: {result.auto_accepted}")
        print(f"Suggestions: {result.suggestions[:3]}")  # Show top 3
        
        if result.matched_name == expected:
            print("✅ PASS")
        else:
            print("❌ FAIL")
        print()

def test_constants_access():
    """Test that constants are accessible from imports."""
    from code.deck_builder.builder_constants import POPULAR_CARDS, ICONIC_CARDS
    
    print("Testing constants access:")
    print("-" * 30)
    
    print(f"POPULAR_CARDS count: {len(POPULAR_CARDS)}")
    print(f"ICONIC_CARDS count: {len(ICONIC_CARDS)}")
    
    # Check that Lightning Bolt is in both sets
    lightning_bolt_in_popular = 'Lightning Bolt' in POPULAR_CARDS
    lightning_bolt_in_iconic = 'Lightning Bolt' in ICONIC_CARDS
    
    print(f"Lightning Bolt in POPULAR_CARDS: {lightning_bolt_in_popular}")
    print(f"Lightning Bolt in ICONIC_CARDS: {lightning_bolt_in_iconic}")
    
    if lightning_bolt_in_popular and lightning_bolt_in_iconic:
        print("✅ Constants are properly set up")
    else:
        print("❌ Constants missing Lightning Bolt")
    
    print()

if __name__ == "__main__":
    test_constants_access()
    test_fuzzy_matching()
