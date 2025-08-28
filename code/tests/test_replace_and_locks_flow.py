import base64
import json
import importlib
from starlette.testclient import TestClient


def _decode_permalink_state(client: TestClient) -> dict:
    r = client.get('/build/permalink')
    assert r.status_code == 200
    data = r.json()
    if data.get('state'):
        return data['state']
    # If only permalink token provided, decode it for inspection
    url = data.get('permalink') or ''
    assert '/build/from?state=' in url
    token = url.split('state=', 1)[1]
    pad = '=' * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + pad).encode('ascii')).decode('utf-8')
    return json.loads(raw)


def test_replace_updates_locks_and_undo_restores(monkeypatch):
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Start session
    r = client.get('/build')
    assert r.status_code == 200

    # Replace Old -> New (locks: add new, remove old)
    r2 = client.post('/build/replace', data={'old': 'Old Card', 'new': 'New Card'})
    assert r2.status_code == 200
    body = r2.text
    assert 'Locked <strong>New Card</strong> and unlocked <strong>Old Card</strong>' in body

    state = _decode_permalink_state(client)
    locks = {s.lower() for s in state.get('locks', [])}
    assert 'new card' in locks
    assert 'old card' not in locks

    # Undo should remove new and re-add old
    r3 = client.post('/build/replace/undo', data={'old': 'Old Card', 'new': 'New Card'})
    assert r3.status_code == 200
    state2 = _decode_permalink_state(client)
    locks2 = {s.lower() for s in state2.get('locks', [])}
    assert 'old card' in locks2
    assert 'new card' not in locks2


def test_lock_from_list_unlock_emits_oob_updates():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    # Initialize session
    r = client.get('/build')
    assert r.status_code == 200

    # Lock a name
    r1 = client.post('/build/lock', data={'name': 'Test Card', 'locked': '1'})
    assert r1.status_code == 200

    # Now unlock from the locked list path (from_list=1)
    r2 = client.post('/build/lock', data={'name': 'Test Card', 'locked': '0', 'from_list': '1'})
    assert r2.status_code == 200
    body = r2.text
    # Should include out-of-band updates so UI can refresh the locks chip/section
    assert 'hx-swap-oob' in body
    assert 'id="locks-chip"' in body or "id='locks-chip'" in body
