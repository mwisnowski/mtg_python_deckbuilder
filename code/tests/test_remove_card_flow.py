import importlib
from starlette.testclient import TestClient


class FakeBuilder:
    def __init__(self, card_library=None):
        self.card_library = card_library or {}
        self.exclude_cards = []


def _inject_fake_ctx(client: TestClient, card_library):
    r = client.get('/build')
    assert r.status_code == 200
    sid = r.cookies.get('sid')
    assert sid
    tasks = importlib.import_module('code.web.services.tasks')
    sess = tasks.get_session(sid)
    sess['build_ctx'] = {'builder': FakeBuilder(card_library), 'locks': set()}
    return sid, sess


def test_remove_card_deletes_from_library_without_permanent_exclude():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    library = {
        'Cavern of Souls': {'Count': 1, 'Card Type': 'Land', 'Role': 'Land', 'SubRole': 'Kindred'},
    }
    sid, sess = _inject_fake_ctx(client, library)

    r = client.post('/build/remove-card', data={'name': 'Cavern of Souls'})
    assert r.status_code == 200
    body = r.text
    assert 'Removed <strong>Cavern of Souls</strong>' in body

    builder = sess['build_ctx']['builder']
    assert 'Cavern of Souls' not in builder.card_library
    # Removal is one-run-only: it must not block the card from being re-added later
    # (e.g. by a rerun or land backfill step), so exclude_cards stays untouched.
    assert builder.exclude_cards == []


def test_remove_card_undo_restores_entry():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    library = {
        'Cavern of Souls': {'Count': 1, 'Card Type': 'Land', 'Role': 'Land', 'SubRole': 'Kindred'},
    }
    sid, sess = _inject_fake_ctx(client, library)

    r = client.post('/build/remove-card', data={'name': 'Cavern of Souls'})
    assert r.status_code == 200
    builder = sess['build_ctx']['builder']
    assert 'Cavern of Souls' not in builder.card_library

    r2 = client.post('/build/remove-card/undo', data={'name': 'Cavern of Souls'})
    assert r2.status_code == 200
    assert 'Restored' in r2.text
    assert 'Cavern of Souls' in builder.card_library
    assert builder.card_library['Cavern of Souls']['Count'] == 1


def test_remove_card_refuses_to_remove_commander():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    library = {
        'My Commander': {'Count': 1, 'Card Type': 'Legendary Creature', 'Commander': True},
    }
    sid, sess = _inject_fake_ctx(client, library)

    r = client.post('/build/remove-card', data={'name': 'My Commander'})
    assert r.status_code == 200
    # Guard trips the fallback path since the commander can't be removed inline
    assert 'card-removed' in r.text
    assert 'My Commander' in r.text
    builder = sess['build_ctx']['builder']
    assert 'My Commander' in builder.card_library


def test_remove_card_fallback_without_builder_and_undo():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)

    r = client.get('/build')
    assert r.status_code == 200

    r2 = client.post('/build/remove-card', data={'name': 'Command Tower'})
    assert r2.status_code == 200
    assert 'card-removed' in r2.text
    assert 'Command Tower' in r2.text

    r3 = client.post('/build/remove-card/undo', data={'name': 'Command Tower'})
    assert r3.status_code == 200
    assert 'Restored' in r3.text or 'No changes to undo' in r3.text

