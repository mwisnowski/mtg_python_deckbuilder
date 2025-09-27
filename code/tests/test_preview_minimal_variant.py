from fastapi.testclient import TestClient
from code.web.app import app  # type: ignore


def test_minimal_variant_hides_controls_and_headers():
    client = TestClient(app)
    r = client.get('/themes/fragment/preview/aggro?suppress_curated=1&minimal=1')
    assert r.status_code == 200
    html = r.text
    assert 'Curated Only' not in html
    assert 'Commander Overlap & Diversity Rationale' not in html
    # Ensure sample cards still render
    assert 'card-sample' in html