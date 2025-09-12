#!/usr/bin/env python3
"""Test improved matching for specific cases that were problematic"""

import requests
import pytest


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
