#!/usr/bin/env python3
"""
Comprehensive fuzzy matching test suite.

This file consolidates all fuzzy matching tests from multiple source files:
  - test_fuzzy_logic.py (Early Fuzzy Logic Tests - Direct API)
  - test_improved_fuzzy.py (Improved Fuzzy Tests - HTTP API)
  - test_final_fuzzy.py (Final Fuzzy Tests - HTTP API)
  - test_specific_matches.py (Specific Match Tests - HTTP API)

The tests are organized into logical sections to maintain clarity about
test evolution and purpose. All original test logic and assertions are
preserved exactly as written.
"""

import sys
import os
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.include_exclude_utils import fuzzy_match_card_name


# ============================================================================
# Section 1: Early Fuzzy Logic Tests (from test_fuzzy_logic.py)
# ============================================================================
# These tests use direct API calls to test core fuzzy matching logic


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


# ============================================================================
# Section 2: Improved Fuzzy Tests (from test_improved_fuzzy.py)
# ============================================================================
# These tests validate improved fuzzy matching via HTTP endpoint


@pytest.mark.parametrize(
    "input_text,description",
    [
        ("lightn", "Should find Lightning cards"),
        ("light", "Should find Light cards"),
        ("bolt", "Should find Bolt cards"),
        ("blightni", "Should find Blightning"),
        ("lightn bo", "Should be unclear match"),
    ],
)
def test_improved_fuzzy(input_text: str, description: str):
    # Skip if local server isn't running
    try:
        requests.get('http://localhost:8080/', timeout=0.5)
    except Exception:
        pytest.skip('Local web server is not running on http://localhost:8080; skipping HTTP-based test')

    print(f"\n🔍 Testing: '{input_text}' ({description})")
    test_data = {
        "include_cards": input_text,
        "exclude_cards": "",
        "commander": "",
        "enforcement_mode": "warn",
        "allow_illegal": "false",
        "fuzzy_matching": "true",
    }

    response = requests.post(
        "http://localhost:8080/build/validate/include_exclude",
        data=test_data,
        timeout=10,
    )
    assert response.status_code == 200
    data = response.json()
    # Ensure we got some structured response
    assert isinstance(data, dict)
    assert 'includes' in data or 'confirmation_needed' in data or 'invalid' in data


# ============================================================================
# Section 3: Final Fuzzy Tests (from test_final_fuzzy.py)
# ============================================================================
# These tests validate final fuzzy matching implementation and modal styling


@pytest.mark.parametrize(
    "input_text,description",
    [
        ("lightn", "Should find Lightning cards"),
        ("lightni", "Should find Lightning with slight typo"),
        ("bolt", "Should find Bolt cards"),
        ("bligh", "Should find Blightning"),
        ("unknowncard", "Should trigger confirmation modal"),
        ("ligth", "Should find Light cards"),
        ("boltt", "Should find Bolt with typo"),
    ],
)
def test_final_fuzzy(input_text: str, description: str):
    # Skip if local server isn't running
    try:
        requests.get('http://localhost:8080/', timeout=0.5)
    except Exception:
        pytest.skip('Local web server is not running on http://localhost:8080; skipping HTTP-based test')

    print(f"\n🔍 Testing: '{input_text}' ({description})")
    test_data = {
        "include_cards": input_text,
        "exclude_cards": "",
        "commander": "",
        "enforcement_mode": "warn",
        "allow_illegal": "false",
        "fuzzy_matching": "true",
    }
    response = requests.post(
        "http://localhost:8080/build/validate/include_exclude",
        data=test_data,
        timeout=10,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert 'includes' in data or 'confirmation_needed' in data or 'invalid' in data


# ============================================================================
# Section 4: Specific Match Tests (from test_specific_matches.py)
# ============================================================================
# These tests focus on specific cases that were previously problematic


@pytest.mark.parametrize(
    "input_text,description",
    [
        ("lightn", "Should prioritize Lightning Bolt over Blightning/Flight"),
        ("cahso warp", "Should clearly find Chaos Warp first"),
        ("bolt", "Should find Lightning Bolt"),
        ("warp", "Should find Chaos Warp"),
    ],
)
def test_specific_matches(input_text: str, description: str):
    # Skip if local server isn't running
    try:
        requests.get('http://localhost:8080/', timeout=0.5)
    except Exception:
        pytest.skip('Local web server is not running on http://localhost:8080; skipping HTTP-based test')

    print(f"\n🔍 Testing: '{input_text}' ({description})")
    test_data = {
        "include_cards": input_text,
        "exclude_cards": "",
        "commander": "",
        "enforcement_mode": "warn",
        "allow_illegal": "false",
        "fuzzy_matching": "true",
    }

    response = requests.post(
        "http://localhost:8080/build/validate/include_exclude",
        data=test_data,
        timeout=10,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # At least one of the expected result containers should exist
    assert (
        data.get("confirmation_needed") is not None
        or data.get("includes") is not None
        or data.get("invalid") is not None
    )


# ============================================================================
# Main Entry Point (from test_fuzzy_logic.py)
# ============================================================================

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
