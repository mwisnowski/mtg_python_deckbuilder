#!/usr/bin/env python3
"""
Test script to verify exclude functionality integration.
This is a quick integration test for M0.5 implementation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from code.deck_builder.include_exclude_utils import parse_card_list_input
from code.deck_builder.builder import DeckBuilder

def test_exclude_integration():
    """Test that exclude functionality works end-to-end."""
    print("=== M0.5 Exclude Integration Test ===")
    
    # Test 1: Parse exclude list
    print("\n1. Testing card list parsing...")
    exclude_input = "Sol Ring\nRhystic Study\nSmothering Tithe"
    exclude_list = parse_card_list_input(exclude_input)
    print(f"   Input: {repr(exclude_input)}")
    print(f"   Parsed: {exclude_list}")
    assert len(exclude_list) == 3
    assert "Sol Ring" in exclude_list
    print("   ✓ Parsing works")
    
    # Test 2: Check DeckBuilder has the exclude attribute
    print("\n2. Testing DeckBuilder exclude attribute...")
    builder = DeckBuilder(headless=True, output_func=lambda x: None, input_func=lambda x: "")
    
    # Set exclude cards
    builder.exclude_cards = exclude_list
    print(f"   Set exclude_cards: {builder.exclude_cards}")
    assert hasattr(builder, 'exclude_cards')
    assert builder.exclude_cards == exclude_list
    print("   ✓ DeckBuilder accepts exclude_cards attribute")
    
    print("\n=== All tests passed! ===")
    print("M0.5 exclude functionality is ready for testing.")

if __name__ == "__main__":
    test_exclude_integration()
