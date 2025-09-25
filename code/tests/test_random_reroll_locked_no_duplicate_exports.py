import os
import glob
from fastapi.testclient import TestClient

def _client():
    os.environ['RANDOM_UI'] = '1'
    os.environ['RANDOM_MODES'] = '1'
    os.environ['CSV_FILES_DIR'] = os.path.join('csv_files','testdata')
    from web.app import app
    return TestClient(app)


def test_locked_reroll_single_export():
    c = _client()
    # Initial surprise build
    r = c.post('/api/random_reroll', json={})
    assert r.status_code == 200
    seed = r.json()['seed']
    commander = r.json()['commander']
    before_csvs = set(glob.glob('deck_files/*.csv'))
    form_body = f"seed={seed}&commander={commander}&mode=reroll_same_commander"
    r2 = c.post('/hx/random_reroll', data=form_body, headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert r2.status_code == 200
    after_csvs = set(glob.glob('deck_files/*.csv'))
    new_csvs = after_csvs - before_csvs
    # Expect exactly 1 new csv file for the reroll (not two)
    assert len(new_csvs) == 1, f"Expected 1 new csv, got {len(new_csvs)}: {new_csvs}"