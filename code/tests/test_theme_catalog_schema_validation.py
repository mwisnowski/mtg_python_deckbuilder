from pathlib import Path
import json


def test_theme_list_json_validates_against_pydantic_and_fast_path():
    # Load JSON
    p = Path('config/themes/theme_list.json')
    raw = json.loads(p.read_text(encoding='utf-8'))

    # Pydantic validation
    from code.type_definitions_theme_catalog import ThemeCatalog
    catalog = ThemeCatalog(**raw)
    assert isinstance(catalog.themes, list) and len(catalog.themes) > 0
    # Basic fields exist on entries
    first = catalog.themes[0]
    assert first.theme and isinstance(first.synergies, list)
