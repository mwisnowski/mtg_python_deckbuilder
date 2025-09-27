from fastapi.testclient import TestClient
from code.web.app import app

def test_preview_error_rate_metrics(monkeypatch):
    monkeypatch.setenv('WEB_THEME_PICKER_DIAGNOSTICS', '1')
    client = TestClient(app)
    # Trigger one preview to ensure request counter increments
    themes_resp = client.get('/themes/api/themes?limit=1')
    assert themes_resp.status_code == 200
    theme_id = themes_resp.json()['items'][0]['id']
    pr = client.get(f'/themes/fragment/preview/{theme_id}')
    assert pr.status_code == 200
    # Simulate two client fetch error structured log events
    for _ in range(2):
        r = client.post('/themes/log', json={'event':'preview_fetch_error'})
        assert r.status_code == 200
    metrics = client.get('/themes/metrics').json()
    assert metrics['ok'] is True
    preview_block = metrics['preview']
    assert 'preview_client_fetch_errors' in preview_block
    assert preview_block['preview_client_fetch_errors'] >= 2
    assert 'preview_error_rate_pct' in preview_block
