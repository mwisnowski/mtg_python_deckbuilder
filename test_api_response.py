#!/usr/bin/env python3
"""Test the validation API response to debug badge counting issue."""

import requests
import json

# Test data: Mix of legal and illegal cards for R/U commander
test_data = {
    'include_cards': '''Lightning Bolt
Counterspell
Teferi's Protection''',
    'exclude_cards': '',
    'commander': 'Niv-Mizzet, Parun',  # R/U commander
    'enforcement_mode': 'warn',
    'allow_illegal': False,
    'fuzzy_matching': True
}

try:
    response = requests.post('http://localhost:8080/build/validate/include_exclude', data=test_data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\nFull API Response:")
        print(json.dumps(data, indent=2))
        
        includes = data.get('includes', {})
        print(f"\nIncludes Summary:")
        print(f"  Total count: {includes.get('count', 0)}")
        print(f"  Legal: {len(includes.get('legal', []))} cards - {includes.get('legal', [])}")
        print(f"  Illegal: {len(includes.get('illegal', []))} cards - {includes.get('illegal', [])}")
        print(f"  Color mismatched: {len(includes.get('color_mismatched', []))} cards - {includes.get('color_mismatched', [])}")
        
        # Check for double counting
        legal_set = set(includes.get('legal', []))
        illegal_set = set(includes.get('illegal', []))
        color_mismatch_set = set(includes.get('color_mismatched', []))
        
        overlap_legal_illegal = legal_set & illegal_set
        overlap_legal_color = legal_set & color_mismatch_set
        overlap_illegal_color = illegal_set & color_mismatch_set
        
        print(f"\nOverlap Analysis:")
        print(f"  Legal ∩ Illegal: {overlap_legal_illegal}")
        print(f"  Legal ∩ Color Mismatch: {overlap_legal_color}")
        print(f"  Illegal ∩ Color Mismatch: {overlap_illegal_color}")
        
        # Total unique cards
        all_cards = legal_set | illegal_set | color_mismatch_set
        print(f"  Total unique cards across all categories: {len(all_cards)}")
        print(f"  Expected total: {includes.get('count', 0)}")
        
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Error making request: {e}")
