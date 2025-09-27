import json
from code.web.routes.themes import _load_fast_theme_list

def test_fast_theme_list_derives_ids(monkeypatch, tmp_path):
    # Create a minimal theme_list.json without explicit 'id' fields to simulate current build output
    data = {
        "themes": [
            {"theme": "+1/+1 Counters", "description": "Foo desc that is a bit longer to ensure trimming works properly and demonstrates snippet logic."},
            {"theme": "Artifacts", "description": "Artifacts matter deck."},
        ],
        "generated_from": "merge"
    }
    # Write to a temporary file and monkeypatch THEME_LIST_PATH to point there
    theme_json = tmp_path / 'theme_list.json'
    theme_json.write_text(json.dumps(data), encoding='utf-8')

    from code.web.routes import themes as themes_module
    monkeypatch.setattr(themes_module, 'THEME_LIST_PATH', theme_json)

    lst = _load_fast_theme_list()
    assert lst is not None
    # Should derive slug ids
    ids = {e['id'] for e in lst}
    assert 'plus1-plus1-counters' in ids
    assert 'artifacts' in ids
    # Should generate short_description
    for e in lst:
        assert 'short_description' in e
        assert e['short_description']

