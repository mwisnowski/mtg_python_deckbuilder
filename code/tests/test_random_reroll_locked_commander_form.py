from fastapi.testclient import TestClient
from urllib.parse import quote_plus
import os


def _new_client():
    os.environ['RANDOM_MODES'] = '1'
    os.environ['RANDOM_UI'] = '1'
    os.environ['CSV_FILES_DIR'] = os.path.join('csv_files','testdata')
    from web.app import app
    return TestClient(app)


def test_reroll_keeps_commander_form_encoded():
    client = _new_client()
    r1 = client.post('/api/random_reroll', json={})
    assert r1.status_code == 200
    data1 = r1.json()
    commander = data1['commander']
    seed = data1['seed']

    form_body = f"seed={seed}&commander={quote_plus(commander)}&mode=reroll_same_commander"
    r2 = client.post('/hx/random_reroll', content=form_body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert r2.status_code == 200
    assert commander in r2.text

    # second reroll with incremented seed
    form_body2 = f"seed={seed+1}&commander={quote_plus(commander)}&mode=reroll_same_commander"
    r3 = client.post('/hx/random_reroll', content=form_body2, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert r3.status_code == 200
    assert commander in r3.text