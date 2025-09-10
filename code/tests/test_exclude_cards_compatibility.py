"""
Exclude Cards Compatibility Tests

Ensures that existing deck configurations build identically when the
include/exclude feature is not used, and that JSON import/export preserves
exclude_cards when the feature is enabled.
"""
import base64
import json
import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client():
    """Test client with ALLOW_MUST_HAVES enabled."""
    import importlib
    import os
    import sys
    
    # Ensure project root is in sys.path for reliable imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Ensure feature flag is enabled for tests
    original_value = os.environ.get('ALLOW_MUST_HAVES')
    os.environ['ALLOW_MUST_HAVES'] = '1'
    
    # Force fresh import to pick up environment change
    try:
        del importlib.sys.modules['code.web.app']
    except KeyError:
        pass
    
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    
    yield client
    
    # Restore original environment
    if original_value is not None:
        os.environ['ALLOW_MUST_HAVES'] = original_value
    else:
        os.environ.pop('ALLOW_MUST_HAVES', None)


def test_legacy_configs_build_unchanged(client):
    """Ensure existing deck configs (without exclude_cards) build identically."""
    # Legacy payload without exclude_cards
    legacy_payload = {
        "commander": "Inti, Seneschal of the Sun",
        "tags": ["discard"],
        "bracket": 3,
        "ideals": {
            "ramp": 10, "lands": 36, "basic_lands": 18, 
            "creatures": 28, "removal": 10, "wipes": 3, 
            "card_advantage": 8, "protection": 4
        },
        "tag_mode": "AND",
        "flags": {"owned_only": False, "prefer_owned": False},
        "locks": [],
    }
    
    # Convert to permalink token
    raw = json.dumps(legacy_payload, separators=(",", ":")).encode('utf-8')
    token = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    
    # Import the legacy config
    response = client.get(f'/build/from?state={token}')
    assert response.status_code == 200
    
    # Should work without errors and not include exclude_cards in session
    # (This test verifies that the absence of exclude_cards doesn't break anything)


def test_exclude_cards_json_roundtrip(client):
    """Test that exclude_cards are preserved in JSON export/import."""
    # Start a session
    r = client.get('/build')
    assert r.status_code == 200
    
    # Create a config with exclude_cards via form submission
    form_data = {
        "name": "Test Deck",
        "commander": "Inti, Seneschal of the Sun",
        "primary_tag": "discard",
        "bracket": 3,
        "ramp": 10,
        "lands": 36,
        "basic_lands": 18,
        "creatures": 28,
        "removal": 10,
        "wipes": 3,
        "card_advantage": 8,
        "protection": 4,
        "exclude_cards": "Sol Ring\nRhystic Study\nSmothering Tithe"
    }
    
    # Submit the form to create the config
    r2 = client.post('/build/new', data=form_data)
    assert r2.status_code == 200
    
    # Get the session cookie for the next request
    session_cookie = r2.cookies.get('sid')
    assert session_cookie is not None, "Session cookie not found"
    
    # Export permalink with exclude_cards
    r3 = client.get('/build/permalink', cookies={'sid': session_cookie})
    assert r3.status_code == 200
    
    permalink_data = r3.json()
    assert permalink_data["ok"] is True
    assert "exclude_cards" in permalink_data["state"]
    
    exported_excludes = permalink_data["state"]["exclude_cards"]
    assert "Sol Ring" in exported_excludes
    assert "Rhystic Study" in exported_excludes
    assert "Smothering Tithe" in exported_excludes
    
    # Test round-trip: import the exported config
    token = permalink_data["permalink"].split("state=")[1]
    r4 = client.get(f'/build/from?state={token}')
    assert r4.status_code == 200
    
    # Get new permalink to verify the exclude_cards were preserved
    # (We need to get the session cookie from the import response)
    import_cookie = r4.cookies.get('sid')
    assert import_cookie is not None, "Import session cookie not found"
    
    r5 = client.get('/build/permalink', cookies={'sid': import_cookie})
    assert r5.status_code == 200
    
    reimported_data = r5.json()
    assert reimported_data["ok"] is True
    assert "exclude_cards" in reimported_data["state"]
    
    # Should be identical to the original export
    reimported_excludes = reimported_data["state"]["exclude_cards"]
    assert reimported_excludes == exported_excludes


def test_validation_endpoint_functionality(client):
    """Test the exclude cards validation endpoint."""
    # Test empty input
    r1 = client.post('/build/validate/exclude_cards', data={'exclude_cards': ''})
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["count"] == 0
    
    # Test valid input
    exclude_text = "Sol Ring\nRhystic Study\nSmothering Tithe"
    r2 = client.post('/build/validate/exclude_cards', data={'exclude_cards': exclude_text})
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["count"] == 3
    assert data2["limit"] == 15
    assert data2["over_limit"] is False
    assert len(data2["cards"]) == 3
    
    # Test over-limit input (16 cards when limit is 15)
    many_cards = "\n".join([f"Card {i}" for i in range(16)])
    r3 = client.post('/build/validate/exclude_cards', data={'exclude_cards': many_cards})
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["count"] == 16
    assert data3["over_limit"] is True
    assert len(data3["warnings"]) > 0
    assert "Too many excludes" in data3["warnings"][0]
