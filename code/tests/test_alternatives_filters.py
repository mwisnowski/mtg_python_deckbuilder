import importlib
from starlette.testclient import TestClient


class FakeBuilder:
    def __init__(self):
        # Minimal attributes accessed by /build/alternatives
        self._card_name_tags_index = {
            'target card': ['ramp', 'mana'],
            'alt good': ['ramp', 'mana'],
            'alt owned': ['ramp'],
            'alt commander': ['ramp'],
            'alt in deck': ['ramp'],
            'alt locked': ['ramp'],
            'unrelated': ['draw'],
        }
        # Simulate pandas DataFrame mapping to preserve display casing
        # Represented as a simple mock object with .empty and .iterrows() for keys above
        class DF:
            empty = False
            def __init__(self, names):
                self._names = names
            def __getattr__(self, name):
                if name == 'empty':
                    return False
                raise AttributeError
            def __iter__(self):
                return iter(self._names)
        # We'll emulate minimal API used: df[ df["name"].astype(str).str.lower().isin(pool) ]
        # To keep it simple, we won't rely on DF in this test; display falls back to lower-case names.
        self._combined_cards_df = None
        self.card_library = {}
        # Simulate deck names containing 'alt in deck'
        self.current_names = ['alt in deck']


def _inject_fake_ctx(client: TestClient, commander: str, locks: list[str]):
    # Touch session to get sid cookie
    r = client.get('/build')
    assert r.status_code == 200
    sid = r.cookies.get('sid')
    assert sid
    # Import session service and mutate directly
    tasks = importlib.import_module('code.web.services.tasks')
    sess = tasks.get_session(sid)
    sess['commander'] = commander
    sess['locks'] = locks
    sess['build_ctx'] = {
        'builder': FakeBuilder(),
        'locks': {s.lower() for s in locks},
    }
    return sid


def test_alternatives_filters_out_commander_in_deck_and_locked():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    _inject_fake_ctx(client, commander='Alt Commander', locks=['alt locked'])
    # owned_only off
    r = client.get('/build/alternatives?name=Target%20Card&owned_only=0')
    assert r.status_code == 200
    body = r.text.lower()
    # Should include alt good and alt owned, but not commander, in deck, or locked
    assert 'alt good' in body or 'alt%20good' in body
    assert 'alt owned' in body or 'alt%20owned' in body
    assert 'alt commander' not in body
    assert 'alt in deck' not in body
    assert 'alt locked' not in body
    assert '"owned_only":"0"' in r.text
    assert 'New pool' in r.text


def test_alternatives_refresh_query():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    _inject_fake_ctx(client, commander='Alt Commander', locks=['alt locked'])
    r = client.get('/build/alternatives?name=Target%20Card&owned_only=0&refresh=1')
    assert r.status_code == 200
    assert 'New pool' in r.text
