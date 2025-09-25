import os
import time
from glob import glob
from fastapi.testclient import TestClient


def _client():
    os.environ['RANDOM_UI'] = '1'
    os.environ['RANDOM_MODES'] = '1'
    os.environ['CSV_FILES_DIR'] = os.path.join('csv_files','testdata')
    from web.app import app
    return TestClient(app)


def _recent_files(pattern: str, since: float):
    out = []
    for p in glob(pattern):
        try:
            if os.path.getmtime(p) >= since:
                out.append(p)
        except Exception:
            pass
    return out


def test_locked_reroll_generates_summary_and_compliance():
    c = _client()
    # First random build (api) to establish commander/seed
    r = c.post('/api/random_reroll', json={})
    assert r.status_code == 200, r.text
    data = r.json()
    commander = data['commander']
    seed = data['seed']

    start = time.time()
    # Locked reroll via HTMX path (form style)
    form_body = f"seed={seed}&commander={commander}&mode=reroll_same_commander"
    r2 = c.post('/hx/random_reroll', data=form_body, headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert r2.status_code == 200, r2.text

    # Look for new sidecar/compliance created after start
    recent_summary = _recent_files('deck_files/*_*.summary.json', start)
    recent_compliance = _recent_files('deck_files/*_compliance.json', start)
    assert recent_summary, 'Expected at least one new summary json after locked reroll'
    assert recent_compliance, 'Expected at least one new compliance json after locked reroll'