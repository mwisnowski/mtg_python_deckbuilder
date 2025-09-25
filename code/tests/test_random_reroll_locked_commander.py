import json
import os
from fastapi.testclient import TestClient


def _new_client():
    os.environ['RANDOM_MODES'] = '1'
    os.environ['RANDOM_UI'] = '1'
    os.environ['CSV_FILES_DIR'] = os.path.join('csv_files','testdata')
    from web.app import app
    return TestClient(app)


def test_reroll_keeps_commander():
    client = _new_client()
    # Initial random build (api path) to get commander + seed
    r1 = client.post('/api/random_reroll', json={})
    assert r1.status_code == 200
    data1 = r1.json()
    commander = data1['commander']
    seed = data1['seed']

    # First reroll with commander lock
    headers = {'Content-Type': 'application/json'}
    body = json.dumps({'seed': seed, 'commander': commander, 'mode': 'reroll_same_commander'})
    r2 = client.post('/hx/random_reroll', data=body, headers=headers)
    assert r2.status_code == 200
    html1 = r2.text
    assert commander in html1

    # Second reroll should keep same commander (seed increments so prior +1 used on server)
    body2 = json.dumps({'seed': seed + 1, 'commander': commander, 'mode': 'reroll_same_commander'})
    r3 = client.post('/hx/random_reroll', data=body2, headers=headers)
    assert r3.status_code == 200
    html2 = r3.text
    assert commander in html2
