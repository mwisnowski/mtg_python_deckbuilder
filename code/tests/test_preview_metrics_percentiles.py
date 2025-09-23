from fastapi.testclient import TestClient
from code.web.app import app


def test_preview_metrics_percentiles_present(monkeypatch):
    # Enable diagnostics for metrics endpoint
    monkeypatch.setenv('WEB_THEME_PICKER_DIAGNOSTICS', '1')
    # Force logging on (not required but ensures code path safe)
    monkeypatch.setenv('WEB_THEME_PREVIEW_LOG', '0')
    client = TestClient(app)
    # Hit a few previews to generate durations
    # We need an existing theme id; fetch list API first
    r = client.get('/themes/api/themes?limit=3')
    assert r.status_code == 200, r.text
    data = r.json()
    # API returns 'items' not 'themes'
    assert 'items' in data
    themes = data['items']
    assert themes, 'Expected at least one theme for metrics test'
    theme_id = themes[0]['id']
    for _ in range(3):
        pr = client.get(f'/themes/fragment/preview/{theme_id}')
        assert pr.status_code == 200
    mr = client.get('/themes/metrics')
    assert mr.status_code == 200, mr.text
    metrics = mr.json()
    assert metrics['ok'] is True
    per_theme = metrics['preview']['per_theme']
    # pick first entry in per_theme stats
    # Validate new percentile fields exist (p50_ms, p95_ms) and are numbers
    any_entry = next(iter(per_theme.values())) if per_theme else None
    assert any_entry, 'Expected at least one per-theme metrics entry'
    assert 'p50_ms' in any_entry and 'p95_ms' in any_entry, any_entry
    assert isinstance(any_entry['p50_ms'], (int, float))
    assert isinstance(any_entry['p95_ms'], (int, float))
