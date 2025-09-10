#!/usr/bin/env python3
"""
Test script to verify fuzzy match confirmation modal functionality.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

import requests
import json

def test_fuzzy_match_confirmation():
    """Test that fuzzy matching returns confirmation_needed items for low confidence matches."""
    print("🔍 Testing fuzzy match confirmation modal backend...")
    
    # Test with a typo that should trigger confirmation
    test_data = {
        'include_cards': 'Lighning',  # Worse typo to trigger confirmation
        'exclude_cards': '',
        'commander': 'Alesha, Who Smiles at Death',  # Valid commander with red identity
        'enforcement_mode': 'warn',
        'allow_illegal': 'false',
        'fuzzy_matching': 'true'
    }
    
    try:
        response = requests.post('http://localhost:8080/build/validate/include_exclude', data=test_data)
        
        if response.status_code != 200:
            print(f"❌ Request failed with status {response.status_code}")
            return False
            
        data = response.json()
        
        # Check if confirmation_needed is populated
        if 'confirmation_needed' not in data:
            print("❌ No confirmation_needed field in response")
            return False
            
        if not data['confirmation_needed']:
            print("❌ confirmation_needed is empty")
            print(f"Response: {json.dumps(data, indent=2)}")
            return False
            
        confirmation = data['confirmation_needed'][0]
        expected_fields = ['input', 'suggestions', 'confidence', 'type']
        
        for field in expected_fields:
            if field not in confirmation:
                print(f"❌ Missing field '{field}' in confirmation")
                return False
        
        print(f"✅ Fuzzy match confirmation working!")
        print(f"   Input: {confirmation['input']}")
        print(f"   Suggestions: {confirmation['suggestions']}")
        print(f"   Confidence: {confirmation['confidence']:.2%}")
        print(f"   Type: {confirmation['type']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def test_exact_match_no_confirmation():
    """Test that exact matches don't trigger confirmation."""
    print("\n🎯 Testing exact match (no confirmation)...")
    
    test_data = {
        'include_cards': 'Lightning Bolt',  # Exact match
        'exclude_cards': '',
        'commander': 'Alesha, Who Smiles at Death',  # Valid commander with red identity
        'enforcement_mode': 'warn',
        'allow_illegal': 'false',
        'fuzzy_matching': 'true'
    }
    
    try:
        response = requests.post('http://localhost:8080/build/validate/include_exclude', data=test_data)
        
        if response.status_code != 200:
            print(f"❌ Request failed with status {response.status_code}")
            return False
            
        data = response.json()
        
        # Should not have confirmation_needed for exact match
        if data.get('confirmation_needed'):
            print(f"❌ Exact match should not trigger confirmation: {data['confirmation_needed']}")
            return False
            
        # Should have legal includes
        if not data.get('includes', {}).get('legal'):
            print("❌ Exact match should be in legal includes")
            print(f"Response: {json.dumps(data, indent=2)}")
            return False
            
        print("✅ Exact match correctly bypasses confirmation!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Fuzzy Match Confirmation Modal")
    print("=" * 50)
    
    test1_pass = test_fuzzy_match_confirmation()
    test2_pass = test_exact_match_no_confirmation()
    
    print("\n📋 Test Summary:")
    print(f"   Fuzzy confirmation: {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"   Exact match: {'✅ PASS' if test2_pass else '❌ FAIL'}")
    
    if test1_pass and test2_pass:
        print("\n🎉 All fuzzy match tests passed!")
        print("💡 Modal functionality ready for user testing")
    else:
        print("\n🔧 Some tests failed - check implementation")
        
    exit(0 if test1_pass and test2_pass else 1)
