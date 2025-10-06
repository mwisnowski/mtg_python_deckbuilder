import json
import logging
from typing import Any, Dict

import pytest
from starlette.requests import Request

from code.web.services.telemetry import (
    log_partner_suggestion_selected,
    log_partner_suggestions_generated,
)


async def _receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(path: str, method: str = "GET", query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string.encode("utf-8"),
        "headers": [],
        "client": ("203.0.113.5", 52345),
        "server": ("testserver", 80),
    }
    request = Request(scope, receive=_receive)
    request.state.request_id = "req-123"
    return request


def test_log_partner_suggestions_generated_emits_payload(caplog: pytest.LogCaptureFixture) -> None:
    request = _make_request("/api/partner/suggestions", query_string="commander=Akiri&mode=partner")
    metadata = {"dataset_version": "2025-10-05", "record_count": 42}

    with caplog.at_level(logging.INFO, logger="web.partner_suggestions"):
        log_partner_suggestions_generated(
            request,
            commander_display="Akiri, Fearless Voyager",
            commander_canonical="akiri, fearless voyager",
            include_modes=["partner"],
            available_modes=["partner"],
            total=3,
            mode_counts={"partner": 3},
            visible_count=2,
            hidden_count=1,
            limit_per_mode=5,
            visible_limit=3,
            include_hidden=False,
            refresh_requested=False,
            dataset_metadata=metadata,
        )

    matching = [record for record in caplog.records if record.name == "web.partner_suggestions"]
    assert matching, "Expected partner suggestions telemetry log"
    payload = json.loads(matching[-1].message)
    assert payload["event"] == "partner_suggestions.generated"
    assert payload["commander"]["display"] == "Akiri, Fearless Voyager"
    assert payload["filters"]["include_modes"] == ["partner"]
    assert payload["result"]["mode_counts"]["partner"] == 3
    assert payload["result"]["visible_count"] == 2
    assert payload["result"]["metadata"]["dataset_version"] == "2025-10-05"
    assert payload["query"]["mode"] == "partner"


def test_log_partner_suggestion_selected_emits_payload(caplog: pytest.LogCaptureFixture) -> None:
    request = _make_request("/build/partner/preview", method="POST")

    with caplog.at_level(logging.INFO, logger="web.partner_suggestions"):
        log_partner_suggestion_selected(
            request,
            commander="Rograkh, Son of Rohgahh",
            scope="partner",
            partner_enabled=True,
            auto_opt_out=False,
            auto_assigned=False,
            selection_source="suggestion",
            secondary_candidate="Silas Renn, Seeker Adept",
            background_candidate=None,
            resolved_secondary="Silas Renn, Seeker Adept",
            resolved_background=None,
            partner_mode="partner",
            has_preview=True,
            warnings=["Color identity expanded"],
            error=None,
        )

    matching = [record for record in caplog.records if record.name == "web.partner_suggestions"]
    assert matching, "Expected partner suggestion selection telemetry log"
    payload = json.loads(matching[-1].message)
    assert payload["event"] == "partner_suggestions.selected"
    assert payload["selection_source"] == "suggestion"
    assert payload["resolved"]["partner_mode"] == "partner"
    assert payload["warnings_count"] == 1
    assert payload["has_error"] is False