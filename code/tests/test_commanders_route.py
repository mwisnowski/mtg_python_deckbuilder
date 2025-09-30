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
    fake_catalog = SimpleNamespace(entries=tuple(records))
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
    fake_catalog = SimpleNamespace(entries=(enriched,))

    def loader() -> SimpleNamespace:
        return fake_catalog

    monkeypatch.setattr(commander_catalog_loader, "load_commander_catalog", loader)
    monkeypatch.setattr(commanders, "load_commander_catalog", loader)

    response = client.get("/commanders")
    assert response.status_code == 200
    body = response.text

    assert "commander-theme-chip-more" not in body  # no overflow badge rendered
    for name in themes:
        assert name in body
