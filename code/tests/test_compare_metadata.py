import importlib
from starlette.testclient import TestClient


def test_compare_options_include_mtime_attribute():
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    r = client.get('/decks/compare')
    assert r.status_code == 200
    body = r.text
    # Ensure at least one option contains data-mtime attribute (present even with empty list structure)
    assert 'data-mtime' in body
