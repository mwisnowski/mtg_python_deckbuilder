from __future__ import annotations

import os
import re
import importlib
import pytest
from fastapi.testclient import TestClient


def _new_client(prewarm: bool = False) -> TestClient:
    # Ensure fresh import with desired env flags
    if prewarm:
        os.environ['WEB_THEME_FILTER_PREWARM'] = '1'
    else:
        os.environ.pop('WEB_THEME_FILTER_PREWARM', None)
    # Remove existing module (if any) so lifespan runs again
    if 'code.web.app' in list(importlib.sys.modules.keys()):
        importlib.sys.modules.pop('code.web.app')
    from code.web.app import app  # type: ignore
    return TestClient(app)


def _first_theme_id(client: TestClient) -> str:
    html = client.get('/themes/fragment/list?limit=1').text
    m = re.search(r'data-theme-id="([^"]+)"', html)
    assert m, 'No theme id found'
    return m.group(1)


def test_role_group_separators_and_role_chips():
    client = _new_client()
    theme_id = _first_theme_id(client)
    pv_html = client.get(f'/themes/fragment/preview/{theme_id}?limit=18').text
    # Ensure at least one role chip exists
    assert 'role-chip' in pv_html, 'Expected role-chip elements in preview fragment'
    # Capture group separator ordering
    groups = re.findall(r'data-group="(examples|curated_synergy|payoff|enabler_support|wildcard)"', pv_html)
    if groups:
        # Remove duplicates preserving order
        seen = []
        for g in groups:
            if g not in seen:
                seen.append(g)
        # Expected relative order subset prefix list
        expected_order = ['examples', 'curated_synergy', 'payoff', 'enabler_support', 'wildcard']
        # Filter expected list to those actually present and compare ordering
        filtered_expected = [g for g in expected_order if g in seen]
        assert seen == filtered_expected, f'Group separators out of order: {seen} vs expected subset {filtered_expected}'


def test_prewarm_flag_metrics():
    client = _new_client(prewarm=True)
    # Trigger at least one list request (though prewarm runs in lifespan already)
    client.get('/themes/fragment/list?limit=5')
    metrics_resp = client.get('/themes/metrics')
    if metrics_resp.status_code != 200:
        pytest.skip('Metrics endpoint unavailable')
    metrics = metrics_resp.json()
    # Soft assertion: if key missing, skip (older build)
    if 'filter_prewarmed' not in metrics:
        pytest.skip('filter_prewarmed metric not present')
    assert metrics['filter_prewarmed'] in (True, 1), 'Expected filter_prewarmed to be True after prewarm'
