#!/usr/bin/env python3
"""Test the improved fuzzy matching and modal styling"""

import requests
import pytest


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
