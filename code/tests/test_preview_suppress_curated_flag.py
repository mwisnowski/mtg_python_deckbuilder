from fastapi.testclient import TestClient
from code.web.app import app  # type: ignore


def test_preview_fragment_suppress_curated_removes_examples():
    client = TestClient(app)
    # Get HTML fragment with suppress_curated
    r = client.get('/themes/fragment/preview/aggro?suppress_curated=1&limit=14')
    assert r.status_code == 200
    html = r.text
    # Should not contain group label Curated Examples
    assert 'Curated Examples' not in html
    # Should still contain payoff/enabler group labels
    assert 'Payoffs' in html or 'Enablers & Support' in html
    # No example role chips: role-example occurrences removed
    # Ensure no rendered span with curated example role (avoid style block false positive)
    assert '<span class="mini-badge role-example"' not in html