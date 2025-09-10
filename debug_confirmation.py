#!/usr/bin/env python3
"""Debug the confirmation_needed response structure"""

import requests
import json

test_data = {
    "include_cards": "lightn",
    "exclude_cards": "",
    "commander": "",
    "enforcement_mode": "warn",
    "allow_illegal": "false",
    "fuzzy_matching": "true"
}

response = requests.post(
    "http://localhost:8080/build/validate/include_exclude",
    data=test_data,
    timeout=10
)

if response.status_code == 200:
    data = response.json()
    print("Full response:")
    print(json.dumps(data, indent=2))
    print("\nConfirmation needed items:")
    for i, item in enumerate(data.get('confirmation_needed', [])):
        print(f"Item {i}: {json.dumps(item, indent=2)}")
else:
    print(f"HTTP {response.status_code}: {response.text}")
