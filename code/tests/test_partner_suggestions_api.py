from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request


def _write_dataset(path: Path) -> Path:
    payload = {
        "metadata": {
            "generated_at": "2025-10-06T12:00:00Z",
            "version": "test-fixture",
        },
        "commanders": {
            "akiri_line_slinger": {
                "name": "Akiri, Line-Slinger",
                "display_name": "Akiri, Line-Slinger",
                "color_identity": ["R", "W"],
                "themes": ["Artifacts", "Aggro"],
                "role_tags": ["Aggro"],
                "partner": {
                    "has_partner": True,
                    "partner_with": ["Silas Renn, Seeker Adept"],
                    "supports_backgrounds": False,
                },
            },
            "silas_renn_seeker_adept": {
                "name": "Silas Renn, Seeker Adept",
                "display_name": "Silas Renn, Seeker Adept",
                "color_identity": ["U", "B"],
                "themes": ["Artifacts", "Value"],
                "role_tags": ["Value"],
                "partner": {
                    "has_partner": True,
                    "partner_with": ["Akiri, Line-Slinger"],
                    "supports_backgrounds": False,
                },
            },
            "ishai_ojutai_dragonspeaker": {
                "name": "Ishai, Ojutai Dragonspeaker",
                "display_name": "Ishai, Ojutai Dragonspeaker",
                "color_identity": ["W", "U"],
                "themes": ["Artifacts", "Counters"],
                "role_tags": ["Aggro"],
                "partner": {
                    "has_partner": True,
                    "partner_with": [],
                    "supports_backgrounds": False,
                },
            },
            "reyhan_last_of_the_abzan": {
                "name": "Reyhan, Last of the Abzan",
                "display_name": "Reyhan, Last of the Abzan",
                "color_identity": ["B", "G"],
                "themes": ["Counters", "Artifacts"],
                "role_tags": ["Counters"],
                "partner": {
                    "has_partner": True,
                    "partner_with": [],
                    "supports_backgrounds": False,
                },
            },
        },
        "pairings": {
            "records": [
                {
                    "mode": "partner_with",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "silas_renn_seeker_adept",
                    "count": 12,
                },
                {
                    "mode": "partner",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "ishai_ojutai_dragonspeaker",
                    "count": 6,
                },
                {
                    "mode": "partner",
                    "primary_canonical": "akiri_line_slinger",
                    "secondary_canonical": "reyhan_last_of_the_abzan",
                    "count": 4,
                },
            ]
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fresh_client(tmp_path: Path) -> tuple[TestClient, Path]:
    dataset_path = _write_dataset(tmp_path / "partner_synergy.json")
    os.environ["ENABLE_PARTNER_MECHANICS"] = "1"
    os.environ["ENABLE_PARTNER_SUGGESTIONS"] = "1"
    for module_name in (
        "code.web.app",
        "code.web.routes.partner_suggestions",
        "code.web.services.partner_suggestions",
    ):
        sys.modules.pop(module_name, None)
    from code.web.services import partner_suggestions as partner_service

    partner_service.configure_dataset_path(dataset_path)
    from code.web.app import app

    client = TestClient(app)
    return client, dataset_path


async def _receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(path: str = "/api/partner/suggestions", query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string.encode("utf-8"),
        "headers": [],
        "client": ("203.0.113.5", 52345),
        "server": ("testserver", 80),
    }
    request = Request(scope, receive=_receive)
    request.state.request_id = "req-telemetry"
    return request


def test_partner_suggestions_api_returns_ranked_candidates(tmp_path: Path) -> None:
    client, dataset_path = _fresh_client(tmp_path)
    try:
        params = {
            "commander": "Akiri, Line-Slinger",
            "visible_limit": 1,
            "partner": [
                "Silas Renn, Seeker Adept",
                "Ishai, Ojutai Dragonspeaker",
                "Reyhan, Last of the Abzan",
            ],
        }
        response = client.get("/api/partner/suggestions", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["visible"], "expected at least one visible suggestion"
        assert len(data["visible"]) == 1
        assert data["hidden"], "expected hidden suggestions when visible_limit=1"
        assert data["has_hidden"] is True
        names = [item["name"] for item in data["visible"]]
        assert names[0] == "Silas Renn, Seeker Adept"
        assert data["metadata"]["generated_at"] == "2025-10-06T12:00:00Z"

        response_all = client.get(
            "/api/partner/suggestions",
            params={**params, "include_hidden": 1},
        )
        assert response_all.status_code == 200
        data_all = response_all.json()
        assert len(data_all["visible"]) >= data_all["total"] or len(data_all["visible"]) >= 3
        assert not data_all["hidden"]
        assert data_all["available_modes"]
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            from code.web.services import partner_suggestions as partner_service

            partner_service.configure_dataset_path(None)
        except Exception:
            pass
        os.environ.pop("ENABLE_PARTNER_MECHANICS", None)
        os.environ.pop("ENABLE_PARTNER_SUGGESTIONS", None)
        for module_name in (
            "code.web.app",
            "code.web.routes.partner_suggestions",
            "code.web.services.partner_suggestions",
        ):
            sys.modules.pop(module_name, None)
        if dataset_path.exists():
            dataset_path.unlink()


def test_load_dataset_refresh_retries_after_prior_failure(tmp_path: Path, monkeypatch) -> None:
    analytics_dir = tmp_path / "config" / "analytics"
    analytics_dir.mkdir(parents=True)
    dataset_path = (analytics_dir / "partner_synergy.json").resolve()

    from code.web.services import partner_suggestions as partner_service
    from code.web.services import orchestrator as orchestrator_service

    original_default = partner_service.DEFAULT_DATASET_PATH
    original_path = partner_service._DATASET_PATH
    original_cache = partner_service._DATASET_CACHE
    original_attempted = partner_service._DATASET_REFRESH_ATTEMPTED

    partner_service.DEFAULT_DATASET_PATH = dataset_path
    partner_service._DATASET_PATH = dataset_path
    partner_service._DATASET_CACHE = None
    partner_service._DATASET_REFRESH_ATTEMPTED = True

    calls = {"count": 0}

    payload_path = tmp_path / "seed_dataset.json"
    _write_dataset(payload_path)

    def seeded_refresh(out_func=None, *, force=False, root=None):
        calls["count"] += 1
        dataset_path.write_text(payload_path.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(orchestrator_service, "_maybe_refresh_partner_synergy", seeded_refresh)

    try:
        result_none = partner_service.load_dataset()
        assert result_none is None
        assert calls["count"] == 0

        dataset = partner_service.load_dataset(refresh=True, force=True)
        assert dataset is not None
        assert calls["count"] == 1
    finally:
        partner_service.DEFAULT_DATASET_PATH = original_default
        partner_service._DATASET_PATH = original_path
        partner_service._DATASET_CACHE = original_cache
        partner_service._DATASET_REFRESH_ATTEMPTED = original_attempted
        try:
            dataset_path.unlink()
        except FileNotFoundError:
            pass
        try:
            payload_path.unlink()
        except FileNotFoundError:
            pass


def test_partner_suggestions_api_refresh_flag(monkeypatch) -> None:
    from code.web.routes import partner_suggestions as route
    from code.web.services.partner_suggestions import PartnerSuggestionResult

    monkeypatch.setattr(route, "ENABLE_PARTNER_MECHANICS", True)
    monkeypatch.setattr(route, "ENABLE_PARTNER_SUGGESTIONS", True)

    captured: dict[str, bool] = {"refresh": False}

    def fake_get_partner_suggestions(
        commander_name: str,
        *,
        limit_per_mode: int = 5,
        include_modes=None,
        min_score: float = 0.15,
        refresh_dataset: bool = False,
    ) -> PartnerSuggestionResult:
        captured["refresh"] = refresh_dataset
        return PartnerSuggestionResult(
            commander=commander_name,
            display_name=commander_name,
            canonical=commander_name.casefold(),
            metadata={},
            by_mode={},
            total=0,
        )

    monkeypatch.setattr(route, "get_partner_suggestions", fake_get_partner_suggestions)

    request = _make_request()

    response = asyncio.run(
        route.partner_suggestions_api(
            request,
            commander="Akiri, Line-Slinger",
            limit=5,
            visible_limit=3,
            include_hidden=False,
            partner=None,
            background=None,
            mode=None,
            refresh=False,
        )
    )
    assert response.status_code == 200
    assert captured["refresh"] is False

    response_refresh = asyncio.run(
        route.partner_suggestions_api(
            _make_request(query_string="refresh=1"),
            commander="Akiri, Line-Slinger",
            limit=5,
            visible_limit=3,
            include_hidden=False,
            partner=None,
            background=None,
            mode=None,
            refresh=True,
        )
    )
    assert response_refresh.status_code == 200
    assert captured["refresh"] is True
