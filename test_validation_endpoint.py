#!/usr/bin/env python3
"""
Test the web validation endpoint to confirm fuzzy matching works.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

import requests
import json

def test_validation_with_empty_commander():
    """Test validation without commander to see basic fuzzy logic."""
    print("🔍 Testing validation endpoint with empty commander...")
    
    test_data = {
        'include_cards': 'Lighning',  # Should trigger suggestions
        'exclude_cards': '',
        'commander': '',  # No commander - should still do fuzzy matching
        'enforcement_mode': 'warn',
        'allow_illegal': 'false',
        'fuzzy_matching': 'true'
    }
    
    try:
        response = requests.post('http://localhost:8080/build/validate/include_exclude', data=test_data)
        data = response.json()
        
        print("Response:")
        print(json.dumps(data, indent=2))
        
        return data
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return None

def test_validation_with_false_fuzzy():
    """Test with fuzzy matching disabled."""
    print("\n🎯 Testing with fuzzy matching disabled...")
    
    test_data = {
        'include_cards': 'Lighning',
        'exclude_cards': '',
        'commander': '',
        'enforcement_mode': 'warn',
        'allow_illegal': 'false',
        'fuzzy_matching': 'false'  # Disabled
    }
    
    try:
        response = requests.post('http://localhost:8080/build/validate/include_exclude', data=test_data)
        data = response.json()
        
        print("Response:")
        print(json.dumps(data, indent=2))
        
        return data
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return None

if __name__ == "__main__":
    print("🧪 Testing Web Validation Endpoint")
    print("=" * 45)
    
    data1 = test_validation_with_empty_commander()
    data2 = test_validation_with_false_fuzzy()
    
    print("\n📋 Analysis:")
    if data1:
        has_confirmation = data1.get('confirmation_needed', [])
        print(f"   With fuzzy enabled: {len(has_confirmation)} confirmations needed")
        
    if data2:
        has_confirmation2 = data2.get('confirmation_needed', [])
        print(f"   With fuzzy disabled: {len(has_confirmation2)} confirmations needed")
