import json
from fastapi.testclient import TestClient

from code.web.app import app  # type: ignore


def test_preview_includes_curated_examples_regression():
    """Regression test (2025-09-20): After P2 changes the preview lost curated
    example cards because theme_list.json lacks example_* arrays. We added YAML
    fallback in project_detail; ensure at least one 'example' role appears for
    a theme known to have example_cards in its YAML (aggro.yml)."""
    client = TestClient(app)
    r = client.get('/themes/api/theme/aggro/preview?limit=12')
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get('ok') is True
    sample = data.get('preview', {}).get('sample', [])
    # Collect roles
    roles = { (it.get('roles') or [''])[0] for it in sample }
    assert 'example' in roles, f"expected at least one curated example card role; roles present: {roles} sample={json.dumps(sample, indent=2)[:400]}"