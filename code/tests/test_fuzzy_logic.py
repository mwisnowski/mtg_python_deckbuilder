#!/usr/bin/env python3
"""
Direct test of fuzzy matching functionality.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.include_exclude_utils import fuzzy_match_card_name

def test_fuzzy_matching_direct():
    """Test fuzzy matching directly."""
    print("🔍 Testing fuzzy matching directly...")
    
    # Create a small set of available cards
    available_cards = {
        'Lightning Bolt',
        'Lightning Strike', 
        'Lightning Helix',
        'Chain Lightning',
        'Sol Ring',
        'Mana Crypt'
    }
    
    # Test with typo that should trigger low confidence
    result = fuzzy_match_card_name('Lighning', available_cards)  # Worse typo
    
    print("Input: 'Lighning'")
    print(f"Matched name: {result.matched_name}")
    print(f"Auto accepted: {result.auto_accepted}")
    print(f"Confidence: {result.confidence:.2%}")
    print(f"Suggestions: {result.suggestions}")
    
    if result.matched_name is None and not result.auto_accepted and result.suggestions:
        print("✅ Fuzzy matching correctly triggered confirmation!")
    else:
        print("❌ Fuzzy matching should have triggered confirmation")
        assert False

def test_exact_match_direct():
    """Test exact matching directly."""
    print("\n🎯 Testing exact match directly...")
    
    available_cards = {
        'Lightning Bolt',
        'Lightning Strike', 
        'Lightning Helix',
        'Sol Ring'
    }
    
    result = fuzzy_match_card_name('Lightning Bolt', available_cards)
    
    print("Input: 'Lightning Bolt'")
    print(f"Matched name: {result.matched_name}")
    print(f"Auto accepted: {result.auto_accepted}")
    print(f"Confidence: {result.confidence:.2%}")
    
    if result.matched_name and result.auto_accepted:
        print("✅ Exact match correctly auto-accepted!")
    else:
        print("❌ Exact match should have been auto-accepted")
        assert False

if __name__ == "__main__":
    print("🧪 Testing Fuzzy Matching Logic")
    print("=" * 40)
    
    test1_pass = test_fuzzy_matching_direct()
    test2_pass = test_exact_match_direct()
    
    print("\n📋 Test Summary:")
    print(f"   Fuzzy confirmation: {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"   Exact match: {'✅ PASS' if test2_pass else '❌ FAIL'}")
    
    if test1_pass and test2_pass:
        print("\n🎉 Fuzzy matching logic working correctly!")
    else:
        print("\n🔧 Issues found in fuzzy matching logic")
        
    exit(0 if test1_pass and test2_pass else 1)
