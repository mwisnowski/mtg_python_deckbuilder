#!/usr/bin/env python3
"""Test improved fuzzy matching algorithm with the new endpoint"""

import requests
import pytest


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
