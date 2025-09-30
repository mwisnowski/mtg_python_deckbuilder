from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code.web.app import app  # type: ignore
from code.web.services import telemetry
from code.web.services.commander_catalog_loader import clear_commander_catalog_cache


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    csv_dir = Path("csv_files/testdata").resolve()
    monkeypatch.setenv("CSV_FILES_DIR", str(csv_dir))
    clear_commander_catalog_cache()
    with TestClient(app) as test_client:
        yield test_client
    clear_commander_catalog_cache()


def test_commander_page_logs_event(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    def capture(_logger, payload):
        events.append(payload)

    monkeypatch.setattr(telemetry, "_emit", capture)

    response = client.get("/commanders", params={"q": "atraxa"})
    assert response.status_code == 200
    assert events, "expected telemetry events to be emitted"
    event = events[-1]
    assert event["event"] == "commander_browser.page_view"
    assert event["page"] == 1
    assert event["query"]["q"] == "atraxa"
    assert event["is_htmx"] is False


def test_commander_create_deck_logs_event(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    def capture(_logger, payload):
        events.append(payload)

    monkeypatch.setattr(telemetry, "_emit", capture)

    response = client.get("/build", params={"commander": "Atraxa", "return": "/commanders"})
    assert response.status_code == 200
    assert events, "expected telemetry events to be emitted"
    event = events[-1]
    assert event["event"] == "commander_browser.create_deck"
    assert event["commander"] == "Atraxa"
    assert event["has_return"] is True
    assert event["return_url"] == "/commanders"
