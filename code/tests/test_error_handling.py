"""Tests for M4 error handling integration.

Covers:
- DeckBuilderError → HTTP response conversion
- HTMX vs JSON response detection
- Status code mapping for exception hierarchy
- app.py DeckBuilderError exception handler
- Web-specific exceptions (SessionExpiredError, BuildNotFoundError, FeatureDisabledError)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request

from code.exceptions import (
    DeckBuilderError,
    CommanderValidationError,
    CommanderTypeError,
    ThemeSelectionError,
    SessionExpiredError,
    BuildNotFoundError,
    FeatureDisabledError,
    CSVFileNotFoundError,
    PriceAPIError,
)
from code.web.utils.responses import (
    deck_error_to_status,
    deck_builder_error_response,
    is_htmx_request,
)


# ---------------------------------------------------------------------------
# Unit tests: exception → status mapping
# ---------------------------------------------------------------------------

class TestDeckErrorToStatus:
    def test_commander_validation_400(self):
        assert deck_error_to_status(CommanderValidationError("bad")) == 400

    def test_commander_type_400(self):
        assert deck_error_to_status(CommanderTypeError("bad type")) == 400

    def test_theme_selection_400(self):
        assert deck_error_to_status(ThemeSelectionError("bad theme")) == 400

    def test_session_expired_401(self):
        assert deck_error_to_status(SessionExpiredError()) == 401

    def test_build_not_found_404(self):
        assert deck_error_to_status(BuildNotFoundError()) == 404

    def test_feature_disabled_404(self):
        assert deck_error_to_status(FeatureDisabledError("test_feature")) == 404

    def test_csv_file_not_found_503(self):
        assert deck_error_to_status(CSVFileNotFoundError("cards.csv")) == 503

    def test_price_api_error_503(self):
        assert deck_error_to_status(PriceAPIError("http://x", 500)) == 503

    def test_base_deck_builder_error_500(self):
        assert deck_error_to_status(DeckBuilderError("generic")) == 500

    def test_subclass_not_in_map_falls_back_via_mro(self):
        # CommanderTypeError is a subclass of CommanderValidationError
        exc = CommanderTypeError("oops")
        assert deck_error_to_status(exc) == 400


# ---------------------------------------------------------------------------
# Unit tests: HTMX detection
# ---------------------------------------------------------------------------

class TestIsHtmxRequest:
    def _make_request(self, hx_header: str | None = None) -> Request:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }
        if hx_header is not None:
            scope["headers"] = [(b"hx-request", hx_header.encode())]
        return Request(scope)

    def test_htmx_true_header(self):
        req = self._make_request("true")
        assert is_htmx_request(req) is True

    def test_no_htmx_header(self):
        req = self._make_request()
        assert is_htmx_request(req) is False

    def test_htmx_false_header(self):
        req = self._make_request("false")
        assert is_htmx_request(req) is False


# ---------------------------------------------------------------------------
# Unit tests: deck_builder_error_response
# ---------------------------------------------------------------------------

class TestDeckBuilderErrorResponse:
    def _make_request(self, htmx: bool = False) -> Request:
        headers = []
        if htmx:
            headers.append((b"hx-request", b"true"))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/build/new",
            "query_string": b"",
            "headers": headers,
        }
        req = Request(scope)
        req.state.request_id = "test-rid-123"
        return req

    def test_json_response_structure(self):
        from fastapi.responses import JSONResponse
        req = self._make_request(htmx=False)
        exc = CommanderValidationError("Invalid commander")
        resp = deck_builder_error_response(req, exc)
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 400
        import json
        body = json.loads(resp.body)
        assert body["error"] is True
        assert body["status"] == 400
        assert body["error_type"] == "CommanderValidationError"
        assert body["message"] == "Invalid commander"
        assert body["request_id"] == "test-rid-123"
        assert "timestamp" in body
        assert "path" in body

    def test_htmx_response_is_html(self):
        from fastapi.responses import HTMLResponse
        req = self._make_request(htmx=True)
        exc = ThemeSelectionError("Invalid theme")
        resp = deck_builder_error_response(req, exc)
        assert isinstance(resp, HTMLResponse)
        assert resp.status_code == 400
        assert "Invalid theme" in resp.body.decode()
        assert resp.headers.get("X-Request-ID") == "test-rid-123"

    def test_request_id_in_response_header(self):
        req = self._make_request(htmx=False)
        exc = BuildNotFoundError()
        resp = deck_builder_error_response(req, exc)
        assert resp.headers.get("X-Request-ID") == "test-rid-123"


# ---------------------------------------------------------------------------
# Integration tests: app exception handler
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_app():
    """Minimal FastAPI app that raises DeckBuilderErrors for testing."""
    app = FastAPI()

    @app.get("/raise/commander")
    async def raise_commander(request: Request):
        raise CommanderValidationError("Commander 'Foo' not found")

    @app.get("/raise/session")
    async def raise_session(request: Request):
        raise SessionExpiredError(sid="abc123")

    @app.get("/raise/feature")
    async def raise_feature(request: Request):
        raise FeatureDisabledError("partner_suggestions")

    @app.get("/raise/generic")
    async def raise_generic(request: Request):
        raise DeckBuilderError("Something went wrong")

    # Wire the same handler as app.py
    from code.exceptions import DeckBuilderError as DBE
    from code.web.utils.responses import deck_builder_error_response

    @app.exception_handler(Exception)
    async def handler(request: Request, exc: Exception):
        if isinstance(exc, DBE):
            return deck_builder_error_response(request, exc)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unhandled"}, status_code=500)

    return app


@pytest.fixture(scope="module")
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)


class TestAppExceptionHandler:
    def test_commander_validation_returns_400(self, client):
        resp = client.get("/raise/commander")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] is True
        assert data["error_type"] == "CommanderValidationError"
        assert "Commander 'Foo' not found" in data["message"]

    def test_session_expired_returns_401(self, client):
        resp = client.get("/raise/session")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_type"] == "SessionExpiredError"

    def test_feature_disabled_returns_404(self, client):
        resp = client.get("/raise/feature")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error_type"] == "FeatureDisabledError"

    def test_generic_deck_builder_error_returns_500(self, client):
        resp = client.get("/raise/generic")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error_type"] == "DeckBuilderError"

    def test_htmx_commander_error_returns_html(self, client):
        resp = client.get("/raise/commander", headers={"HX-Request": "true"})
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Commander 'Foo' not found" in resp.text


# ---------------------------------------------------------------------------
# Web-specific exception constructors
# ---------------------------------------------------------------------------

class TestWebExceptions:
    def test_session_expired_has_code(self):
        exc = SessionExpiredError(sid="xyz")
        assert exc.code == "SESSION_EXPIRED"
        assert "xyz" in str(exc.details)

    def test_build_not_found_has_code(self):
        exc = BuildNotFoundError(sid="abc")
        assert exc.code == "BUILD_NOT_FOUND"

    def test_feature_disabled_has_feature_name(self):
        exc = FeatureDisabledError("partner_suggestions")
        assert exc.code == "FEATURE_DISABLED"
        assert "partner_suggestions" in exc.message
