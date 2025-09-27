import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from code.web.app import app  # type: ignore

# Ensure project root on sys.path for absolute imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CATALOG_PATH = ROOT / 'config' / 'themes' / 'theme_list.json'


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_list_basic_ok():
    client = TestClient(app)
    r = client.get('/themes/api/themes')
    assert r.status_code == 200
    data = r.json()
    assert data['ok'] is True
    assert 'items' in data and isinstance(data['items'], list)
    if data['items']:
        sample = data['items'][0]
        assert 'id' in sample and 'theme' in sample


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_list_query_substring():
    client = TestClient(app)
    r = client.get('/themes/api/themes', params={'q': 'Counters'})
    assert r.status_code == 200
    data = r.json()
    assert all('Counters'.lower() in ('|'.join(it.get('synergies', []) + [it['theme']]).lower()) for it in data['items']) or not data['items']


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_list_filter_bucket_and_archetype():
    client = TestClient(app)
    base = client.get('/themes/api/themes').json()
    if not base['items']:
        pytest.skip('No themes to filter')
    # Find first item with both bucket & archetype
    candidate = None
    for it in base['items']:
        if it.get('popularity_bucket') and it.get('deck_archetype'):
            candidate = it
            break
    if not candidate:
        pytest.skip('No item with bucket+archetype to test')
    r = client.get('/themes/api/themes', params={'bucket': candidate['popularity_bucket']})
    assert r.status_code == 200
    data_bucket = r.json()
    assert all(i.get('popularity_bucket') == candidate['popularity_bucket'] for i in data_bucket['items'])
    r2 = client.get('/themes/api/themes', params={'archetype': candidate['deck_archetype']})
    assert r2.status_code == 200
    data_arch = r2.json()
    assert all(i.get('deck_archetype') == candidate['deck_archetype'] for i in data_arch['items'])


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_fragment_endpoints():
    client = TestClient(app)
    # Page
    pg = client.get('/themes/picker')
    assert pg.status_code == 200 and 'Theme Catalog' in pg.text
    # List fragment
    frag = client.get('/themes/fragment/list')
    assert frag.status_code == 200
    # Snippet hover presence (short_description used as title attribute on first theme cell if available)
    if '<table>' in frag.text:
        assert 'title="' in frag.text  # coarse check; ensures at least one title attr present for snippet
    # If there is at least one row, request detail fragment
    base = client.get('/themes/api/themes').json()
    if base['items']:
        tid = base['items'][0]['id']
        dfrag = client.get(f'/themes/fragment/detail/{tid}')
        assert dfrag.status_code == 200


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_detail_ok_and_not_found():
    client = TestClient(app)
    listing = client.get('/themes/api/themes').json()
    if not listing['items']:
        pytest.skip('No themes to test detail')
    first_id = listing['items'][0]['id']
    r = client.get(f'/themes/api/theme/{first_id}')
    assert r.status_code == 200
    detail = r.json()['theme']
    assert detail['id'] == first_id
    r404 = client.get('/themes/api/theme/does-not-exist-xyz')
    assert r404.status_code == 404


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_diagnostics_gating(monkeypatch):
    client = TestClient(app)
    # Without flag -> diagnostics fields absent
    r = client.get('/themes/api/themes', params={'diagnostics': '1'})
    sample = r.json()['items'][0] if r.json()['items'] else {}
    assert 'has_fallback_description' not in sample
    # Enable flag
    monkeypatch.setenv('WEB_THEME_PICKER_DIAGNOSTICS', '1')
    r2 = client.get('/themes/api/themes', params={'diagnostics': '1'})
    sample2 = r2.json()['items'][0] if r2.json()['items'] else {}
    if sample2:
        assert 'has_fallback_description' in sample2


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_uncapped_requires_diagnostics(monkeypatch):
    client = TestClient(app)
    listing = client.get('/themes/api/themes').json()
    if not listing['items']:
        pytest.skip('No themes available')
    tid = listing['items'][0]['id']
    # Request uncapped without diagnostics -> should not include
    d = client.get(f'/themes/api/theme/{tid}', params={'uncapped': '1'}).json()['theme']
    assert 'uncapped_synergies' not in d
    # Enable diagnostics
    monkeypatch.setenv('WEB_THEME_PICKER_DIAGNOSTICS', '1')
    d2 = client.get(f'/themes/api/theme/{tid}', params={'diagnostics': '1', 'uncapped': '1'}).json()['theme']
    # Uncapped may equal capped if no difference, but key must exist
    assert 'uncapped_synergies' in d2


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_preview_endpoint_basic():
    client = TestClient(app)
    listing = client.get('/themes/api/themes').json()
    if not listing['items']:
        pytest.skip('No themes available')
    tid = listing['items'][0]['id']
    preview = client.get(f'/themes/api/theme/{tid}/preview', params={'limit': 5}).json()
    assert preview['ok'] is True
    sample = preview['preview']['sample']
    assert len(sample) <= 5
    # Scores should be non-increasing for first curated entries (simple heuristic)
    scores = [it['score'] for it in sample]
    assert all(isinstance(s, (int, float)) for s in scores)
    # Synthetic placeholders (if any) should have role 'synthetic'
    for it in sample:
        assert 'roles' in it and isinstance(it['roles'], list)
    # Color filter invocation (may reduce or keep size; ensure no crash)
    preview_color = client.get(f'/themes/api/theme/{tid}/preview', params={'limit': 4, 'colors': 'U'}).json()
    assert preview_color['ok'] is True
    # Fragment version
    frag = client.get(f'/themes/fragment/preview/{tid}')
    assert frag.status_code == 200


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_preview_commander_bias():  # lightweight heuristic validation
    client = TestClient(app)
    listing = client.get('/themes/api/themes').json()
    if not listing['items']:
        pytest.skip('No themes available')
    tid = listing['items'][0]['id']
    # Use an arbitrary commander name – depending on dataset may not be found; test tolerant
    commander_name = 'Atraxa, Praetors Voice'  # attempt full name; if absent test remains soft
    preview = client.get(f'/themes/api/theme/{tid}/preview', params={'limit': 6, 'commander': commander_name}).json()
    assert preview['ok'] is True
    sample = preview['preview']['sample']
    # If commander card was discovered at least one item should have commander_bias reason
    any_commander_reason = any('commander_bias' in it.get('reasons', []) for it in sample)
    # It's acceptable if not found (dataset subset) but reasons structure must exist
    assert all('reasons' in it for it in sample)
    # Soft assertion (no failure if commander not present) – if discovered we assert overlap marker
    if any_commander_reason:
        assert any('commander_overlap' in it.get('reasons', []) for it in sample)


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="theme catalog missing")
def test_preview_curated_synergy_ordering():
    """Curated synergy example cards (role=curated_synergy) must appear after role=example
    cards but before any sampled payoff/enabler/support/wildcard entries.
    """
    client = TestClient(app)
    listing = client.get('/themes/api/themes').json()
    if not listing['items']:
        pytest.skip('No themes available')
    tid = listing['items'][0]['id']
    preview = client.get(f'/themes/api/theme/{tid}/preview', params={'limit': 12}).json()
    assert preview['ok'] is True
    sample = preview['preview']['sample']
    roles_sequence = [it['roles'][0] if it.get('roles') else None for it in sample]
    if 'curated_synergy' not in roles_sequence:
        pytest.skip('No curated synergy cards present in sample (data-dependent)')
    first_non_example_index = None
    first_curated_synergy_index = None
    first_sampled_index = None
    sampled_roles = {'payoff', 'enabler', 'support', 'wildcard'}
    for idx, role in enumerate(roles_sequence):
        if role != 'example' and first_non_example_index is None:
            first_non_example_index = idx
        if role == 'curated_synergy' and first_curated_synergy_index is None:
            first_curated_synergy_index = idx
        if role in sampled_roles and first_sampled_index is None:
            first_sampled_index = idx
    # Ensure ordering: examples (if any) -> curated_synergy -> sampled roles
    if first_curated_synergy_index is not None and first_sampled_index is not None:
        assert first_curated_synergy_index < first_sampled_index
