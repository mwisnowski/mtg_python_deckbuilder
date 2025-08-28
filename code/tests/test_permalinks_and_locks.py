import base64
import json
from starlette.testclient import TestClient


def test_permalink_includes_locks_and_restores_notice(monkeypatch):
    # Lazy import to ensure fresh app state
    import importlib
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Seed a session with a commander and locks by calling /build and directly touching session via cookie path
    # Start a session
    r = client.get('/build')
    assert r.status_code == 200

    # Now set some session state by invoking endpoints that mutate session
    # Simulate selecting commander and a lock
    # Use /build/from to load a permalink-like payload directly
    payload = {
        "commander": "Atraxa, Praetors' Voice",
        "tags": ["proliferate"],
        "bracket": 3,
        "ideals": {"ramp": 10, "lands": 36, "basic_lands": 18, "creatures": 28, "removal": 10, "wipes": 3, "card_advantage": 8, "protection": 4},
        "tag_mode": "AND",
        "flags": {"owned_only": False, "prefer_owned": False},
        "locks": ["Swords to Plowshares", "Sol Ring"],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode('utf-8')
    token = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    r2 = client.get(f'/build/from?state={token}')
    assert r2.status_code == 200
    # Step 4 should contain the locks restored chip
    body = r2.text
    assert 'locks restored' in body.lower()

    # Ask the server for a permalink now and ensure locks are present
    r3 = client.get('/build/permalink')
    assert r3.status_code == 200
    data = r3.json()
    # Prefer decoded state when token not provided
    state = data.get('state') or {}
    assert 'locks' in state
    assert set([s.lower() for s in state.get('locks', [])]) == {"swords to plowshares", "sol ring"}
