#!/usr/bin/env python3
"""
Test the web validation endpoint to confirm fuzzy matching works.
Skips if the local web server is not running.
"""

import requests
import json
import pytest

def test_validation_with_empty_commander():
    """Test validation without commander to see basic fuzzy logic."""
    print("🔍 Testing validation endpoint with empty commander...")
    # Skip if local server isn't running
    try:
        requests.get('http://localhost:8080/', timeout=0.5)
    except Exception:
        pytest.skip('Local web server is not running on http://localhost:8080; skipping HTTP-based test')
    
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
        assert response.status_code == 200
        data = response.json()
        # Check expected structure keys exist
        assert isinstance(data, dict)
        assert 'includes' in data or 'confirmation_needed' in data or 'invalid' in data
        print("Response:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        assert False

def test_validation_with_false_fuzzy():
    """Test with fuzzy matching disabled."""
    print("\n🎯 Testing with fuzzy matching disabled...")
    # Skip if local server isn't running
    try:
        requests.get('http://localhost:8080/', timeout=0.5)
    except Exception:
        pytest.skip('Local web server is not running on http://localhost:8080; skipping HTTP-based test')
    
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
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("Response:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        assert False

if __name__ == "__main__":
    print("🧪 Run this test with pytest for proper reporting")
