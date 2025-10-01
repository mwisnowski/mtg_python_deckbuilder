from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from code.web.app import app  # type: ignore
from code.web.routes import commanders
from code.web.services import commander_catalog_loader
from code.web.services.commander_catalog_loader import clear_commander_catalog_cache, load_commander_catalog


@pytest.fixture
def client(monkeypatch):
    csv_dir = Path("csv_files/testdata").resolve()
    monkeypatch.setenv("CSV_FILES_DIR", str(csv_dir))
    clear_commander_catalog_cache()
    with TestClient(app) as test_client:
        yield test_client
    clear_commander_catalog_cache()


def test_commanders_page_renders(client: TestClient) -> None:
    response = client.get("/commanders")
    assert response.status_code == 200
    body = response.text
    assert "data-commander-slug=\"atraxa-praetors-voice\"" in body
    assert "data-commander-slug=\"krenko-mob-boss\"" in body
    assert "data-theme-summary=\"" in body
    assert 'id="commander-loading"' in body


def test_commanders_search_filters(client: TestClient) -> None:
    response = client.get("/commanders", params={"q": "krenko"})
    assert response.status_code == 200
    body = response.text
    assert "data-commander-slug=\"krenko-mob-boss\"" in body
    assert "data-commander-slug=\"atraxa-praetors-voice\"" not in body


def test_commanders_color_filter(client: TestClient) -> None:
    response = client.get("/commanders", params={"color": "W"})
    assert response.status_code == 200
    body = response.text
    assert "data-commander-slug=\"isamaru-hound-of-konda\"" in body
    assert "data-commander-slug=\"krenko-mob-boss\"" not in body


def test_commanders_htmx_fragment(client: TestClient) -> None:
    response = client.get(
        "/commanders",
        params={"q": "atraxa"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    body = response.text
    assert "commander-row" in body
    assert "<section class=\"commander-page\"" not in body


def _install_paginated_catalog(monkeypatch: pytest.MonkeyPatch, total: int) -> None:
    base_catalog = load_commander_catalog()
    sample = base_catalog.entries[0]
    records = []
    for index in range(total):
        name = f"Pagination Test {index:02d}"
        record = replace(
            sample,
            name=name,
            face_name=name,
            display_name=name,
            slug=f"pagination-test-{index:02d}",
            search_haystack=f"{name.lower()}"
        )
        records.append(record)
    _install_custom_catalog(monkeypatch, records)


def _install_custom_catalog(monkeypatch: pytest.MonkeyPatch, records: list) -> None:
    fake_catalog = SimpleNamespace(
        entries=tuple(records),
        by_slug={record.slug: record for record in records},
    )

    def loader() -> SimpleNamespace:
        return fake_catalog

    monkeypatch.setattr(commander_catalog_loader, "load_commander_catalog", loader)
    monkeypatch.setattr(commanders, "load_commander_catalog", loader)


def test_commanders_pagination_limits_results(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_paginated_catalog(monkeypatch, total=35)

    response = client.get("/commanders")
    assert response.status_code == 200
    body = response.text

    assert "Page 1 of 2" in body
    assert "Showing 1&nbsp;&ndash;&nbsp;20 of 35" in body
    assert body.count('href="/commanders?page=2"') == 2
    assert body.count('data-commander-slug="pagination-test-') == 20


def test_commanders_second_page_shows_remaining_results(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_paginated_catalog(monkeypatch, total=35)

    response = client.get("/commanders", params={"page": 2})
    assert response.status_code == 200
    body = response.text

    assert "Page 2 of 2" in body
    assert 'data-commander-slug="pagination-test-00"' not in body
    assert 'data-commander-slug="pagination-test-20"' in body
    assert 'data-commander-slug="pagination-test-34"' in body
    assert 'href="/commanders?page=1"' in body


def test_commanders_show_all_themes_without_overflow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    themes = tuple(f"Theme {idx}" for idx in range(1, 9))
    enriched = replace(
        sample,
        themes=themes,
        theme_tokens=tuple(theme.lower() for theme in themes),
    )
    _install_custom_catalog(monkeypatch, [enriched])

    response = client.get("/commanders")
    assert response.status_code == 200
    body = response.text

    assert "commander-theme-chip-more" not in body  # no overflow badge rendered
    for name in themes:
        assert name in body


def _commander_fixture(sample, *, name: str, slug: str, themes: tuple[str, ...] = ()):
    return replace(
        sample,
        name=name,
        face_name=name,
        display_name=name,
        slug=slug,
        themes=themes,
        theme_tokens=tuple(theme.lower() for theme in themes),
        search_haystack="|".join([name.lower(), *[theme.lower() for theme in themes]]),
    )


def test_commanders_search_ignores_theme_tokens(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    target = _commander_fixture(
        sample,
        name="Avatar Aang // Aang, Master of Elements",
        slug="avatar-aang",
        themes=("Elemental", "Avatar"),
    )
    other = _commander_fixture(
        sample,
        name="Generic Guardian",
        slug="generic-guardian",
        themes=("Avatar", "Guardian"),
    )
    _install_custom_catalog(monkeypatch, [target, other])

    response = client.get("/commanders", params={"q": "Avatar Aang"})
    assert response.status_code == 200
    body = response.text

    assert 'data-commander-slug="avatar-aang"' in body
    assert 'data-commander-slug="generic-guardian"' not in body


def test_commanders_search_supports_token_reordering(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    target = _commander_fixture(
        sample,
        name="Avatar Aang // Aang, Master of Elements",
        slug="avatar-aang",
        themes=("Elemental",),
    )
    fallback = _commander_fixture(
        sample,
        name="Master of Avatar Arts",
        slug="master-of-avatar-arts",
        themes=("Avatar",),
    )
    _install_custom_catalog(monkeypatch, [target, fallback])

    response = client.get("/commanders", params={"q": "Aang Avatar"})
    assert response.status_code == 200
    body = response.text

    assert 'data-commander-slug="avatar-aang"' in body
    assert 'data-commander-slug="master-of-avatar-arts"' not in body


def test_commanders_theme_search_filters(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    aggro_commander = _commander_fixture(
        sample,
        name="Aggro Ace",
        slug="aggro-ace",
        themes=("Aggro", "Combat"),
    )
    control_commander = _commander_fixture(
        sample,
        name="Control Keeper",
        slug="control-keeper",
        themes=("Control", "Value"),
    )
    _install_custom_catalog(monkeypatch, [aggro_commander, control_commander])

    response = client.get("/commanders", params={"theme": "Aggo"})
    assert response.status_code == 200
    body = response.text

    assert 'data-commander-slug="aggro-ace"' in body
    assert 'data-commander-slug="control-keeper"' not in body
    assert 'data-theme-suggestion="Aggro"' in body
    assert 'id="theme-suggestions"' in body
    assert 'option value="Aggro"' in body


def test_commanders_theme_recommendations_render_in_fragment(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    aggro_commander = _commander_fixture(
        sample,
        name="Aggro Ace",
        slug="aggro-ace",
        themes=("Aggro", "Combat"),
    )
    control_commander = _commander_fixture(
        sample,
        name="Control Keeper",
        slug="control-keeper",
        themes=("Control", "Value"),
    )
    _install_custom_catalog(monkeypatch, [aggro_commander, control_commander])

    response = client.get(
        "/commanders",
        params={"theme": "Aggo"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    body = response.text

    assert 'data-theme-suggestion="Aggro"' in body
    assert 'data-commander-slug="aggro-ace"' in body


def test_commander_name_fuzzy_tightened(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_commander_catalog()
    sample = catalog.entries[0]
    finneas = _commander_fixture(
        sample,
        name="Finneas, Ace Archer",
        slug="finneas-ace-archer",
        themes=("Aggro", "Counters"),
    )
    torgal = _commander_fixture(
        sample,
        name="Torgal, A Fine Hound",
        slug="torgal-a-fine-hound",
        themes=("Aggro", "Combat"),
    )
    gorbag = _commander_fixture(
        sample,
        name="Gorbag of Minas Morgul",
        slug="gorbag-of-minas-morgul",
        themes=("Aggro", "Treasure"),
    )
    _install_custom_catalog(monkeypatch, [finneas, torgal, gorbag])

    response = client.get("/commanders", params={"q": "Finneas"})
    assert response.status_code == 200
    body = response.text

    assert 'data-commander-slug="finneas-ace-archer"' in body
    assert 'data-commander-slug="torgal-a-fine-hound"' not in body
    assert 'data-commander-slug="gorbag-of-minas-morgul"' not in body
