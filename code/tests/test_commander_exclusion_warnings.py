from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from code.web.app import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_candidate_list_includes_exclusion_warning(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    def fake_candidates(_: str, limit: int = 8):
        return [("Sample Front", 10, ["G"])]

    def fake_lookup(name: str):
        if name == "Sample Front":
            return {
                "primary_face": "Sample Front",
                "eligible_faces": ["Sample Back"],
                "reason": "secondary_face_only",
            }
        return None

    monkeypatch.setattr("code.web.routes.build.orch.commander_candidates", fake_candidates)
    monkeypatch.setattr("code.web.routes.build.lookup_commander_detail", fake_lookup)

    response = client.get("/build/new/candidates", params={"commander": "Sample"})
    assert response.status_code == 200
    body = response.text
    assert "Use the back face &#39;Sample Back&#39; when building" in body
    assert "data-name=\"Sample Back\"" in body
    assert "data-display=\"Sample Front\"" in body


def test_front_face_submit_returns_modal_error(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    def fake_lookup(name: str):
        if "Budoka" in name:
            return {
                "primary_face": "Budoka Gardener",
                "eligible_faces": ["Dokai, Weaver of Life"],
                "reason": "secondary_face_only",
            }
        return None

    monkeypatch.setattr("code.web.routes.build.lookup_commander_detail", fake_lookup)
    monkeypatch.setattr("code.web.routes.build.orch.bracket_options", lambda: [{"level": 3, "name": "Upgraded"}])
    monkeypatch.setattr("code.web.routes.build.orch.ideal_labels", lambda: {})
    monkeypatch.setattr("code.web.routes.build.orch.ideal_defaults", lambda: {})

    def fail_select(name: str):  # pragma: no cover - should not trigger
        raise AssertionError(f"commander_select should not be called for {name}")

    monkeypatch.setattr("code.web.routes.build.orch.commander_select", fail_select)

    client.get("/build")
    response = client.post(
        "/build/new",
        data={
            "name": "",
            "commander": "Budoka Gardener",
            "bracket": "3",
            "include_cards": "",
            "exclude_cards": "",
            "enforcement_mode": "warn",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "can&#39;t lead a deck" in body
    assert "Use &#39;Dokai, Weaver of Life&#39; as the commander instead" in body
    assert "value=\"Dokai, Weaver of Life\"" in body
