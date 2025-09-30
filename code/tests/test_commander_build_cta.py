from __future__ import annotations

from pathlib import Path
import html as _html
import re
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from code.web.app import app  # type: ignore
from code.web.services.commander_catalog_loader import clear_commander_catalog_cache


@pytest.fixture
def client(monkeypatch):
    csv_dir = Path("csv_files/testdata").resolve()
    monkeypatch.setenv("CSV_FILES_DIR", str(csv_dir))
    clear_commander_catalog_cache()
    with TestClient(app) as test_client:
        yield test_client
    clear_commander_catalog_cache()


def test_commander_row_has_build_cta_with_return_url(client: TestClient) -> None:
    # Load the commanders page
    resp = client.get("/commanders", params={"q": "atraxa"})
    assert resp.status_code == 200
    body = resp.text
    # Ensure the Build link includes the builder path with commander and return params
    match = re.search(r'href="(/build\?[^\"]+)"', body)
    assert match is not None
    href = _html.unescape(match.group(1))
    assert href.startswith("/build?commander=")
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    assert "return" in params
    return_value = params["return"][0]
    assert return_value.startswith("/commanders")
    parsed_return = urlparse(return_value)
    assert parsed_return.path.rstrip("/") == "/commanders"
    parsed_return_params = parse_qs(parsed_return.query)
    assert parsed_return_params.get("q") == ["atraxa"]
    # Ensure no absolute scheme slipped through
    assert not return_value.startswith("http")


def test_build_page_includes_back_link_for_safe_return(client: TestClient) -> None:
    resp = client.get("/build", params={"return": "/commanders?page=2&color=W"})
    assert resp.status_code == 200
    body = resp.text
    match = re.search(r'href="(/commanders[^\"]+)"', body)
    assert match is not None
    href = _html.unescape(match.group(1))
    parsed = urlparse(href)
    assert parsed.path == "/commanders"
    params = parse_qs(parsed.query)
    assert params.get("page") == ["2"]
    assert params.get("color") == ["W"]


def test_build_page_ignores_external_return(client: TestClient) -> None:
    resp = client.get("/build", params={"return": "https://evil.example.com"})
    assert resp.status_code == 200
    body = resp.text
    assert "Back to Commanders" not in body


def test_commander_launch_preselects_commander_and_requires_theme(client: TestClient) -> None:
    commander_name = "Atraxa, Praetors' Voice"
    resp = client.get(
        "/build",
        params={"commander": commander_name, "return": "/commanders?page=2"},
    )
    assert resp.status_code == 200
    body = resp.text
    init_match = re.search(r'<span id="builder-init"[^>]*data-commander="([^"]+)"', body)
    assert init_match is not None
    assert _html.unescape(init_match.group(1)) == commander_name
    assert "Back to Commanders" in body

    step2 = client.get("/build/step2")
    assert step2.status_code == 200
    step2_body = step2.text
    assert commander_name in _html.unescape(step2_body)
    assert 'name="primary_tag"' in step2_body

    submit = client.post(
        "/build/step2",
        data={
            "commander": commander_name,
            "bracket": "3",
            "tag_mode": "AND",
        },
    )
    assert submit.status_code == 200
    assert "Please choose a primary theme." in submit.text
