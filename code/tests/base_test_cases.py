"""Base test case classes for the MTG Python Deckbuilder web layer.

Provides reusable base classes and mixins that reduce boilerplate in route,
service, and validation tests. Import what you need — don't inherit everything.

Usage:
    from code.tests.base_test_cases import RouteTestCase, ServiceTestCase

    class TestMyRoute(RouteTestCase):
        def test_something(self):
            resp = self.client.get("/my-route")
            self.assert_ok(resp)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Route test base
# ---------------------------------------------------------------------------

class RouteTestCase:
    """Base class for route integration tests.

    Provides a shared TestClient and assertion helpers. Subclasses can override
    `app_fixture` to use a different FastAPI app (e.g., a minimal test app).

    Example:
        class TestBuildWizard(RouteTestCase):
            def test_step1_renders(self):
                resp = self.get("/build/step1")
                self.assert_ok(resp)
                assert "Commander" in resp.text
    """

    @pytest.fixture(autouse=True)
    def setup_client(self, monkeypatch):
        """Create a TestClient for the full app. Override to customise."""
        from code.web.app import app
        with TestClient(app) as c:
            self.client = c
        yield

    # --- Shorthand request helpers ---

    def get(self, path: str, *, headers: dict | None = None, cookies: dict | None = None, **params) -> Any:
        return self.client.get(path, headers=headers or {}, cookies=cookies or {}, params=params or {})

    def post(self, path: str, data: dict | None = None, *, json: dict | None = None,
             headers: dict | None = None, cookies: dict | None = None) -> Any:
        return self.client.post(path, data=data, json=json, headers=headers or {}, cookies=cookies or {})

    def htmx_get(self, path: str, *, cookies: dict | None = None, **params) -> Any:
        """GET with HX-Request header set (simulates HTMX fetch)."""
        return self.client.get(path, headers={"HX-Request": "true"}, cookies=cookies or {}, params=params or {})

    def htmx_post(self, path: str, data: dict | None = None, *, cookies: dict | None = None) -> Any:
        """POST with HX-Request header set (simulates HTMX form submission)."""
        return self.client.post(path, data=data, headers={"HX-Request": "true"}, cookies=cookies or {})

    # --- Assertion helpers ---

    def assert_ok(self, resp, *, contains: str | None = None) -> None:
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        if contains:
            assert contains in resp.text, f"Expected {contains!r} in response"

    def assert_status(self, resp, status: int) -> None:
        assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text[:200]}"

    def assert_json_error(self, resp, *, status: int, error_type: str | None = None) -> dict:
        """Assert a standardized error JSON response (M4 format)."""
        assert resp.status_code == status
        data = resp.json()
        assert data.get("error") is True, f"Expected error=True in: {data}"
        assert "request_id" in data
        if error_type:
            assert data.get("error_type") == error_type, f"Expected error_type={error_type!r}, got {data.get('error_type')!r}"
        return data

    def assert_redirect(self, resp, *, to: str | None = None) -> None:
        assert resp.status_code in (301, 302, 303, 307, 308), f"Expected redirect, got {resp.status_code}"
        if to:
            assert to in resp.headers.get("location", "")

    def with_session(self, commander: str = "Atraxa, Praetors' Voice", **extra) -> tuple[str, dict]:
        """Create a session with basic commander state. Returns (sid, session_dict)."""
        from code.web.services.tasks import get_session, new_sid
        sid = new_sid()
        sess = get_session(sid)
        sess["commander"] = {"name": commander, "ok": True}
        sess.update(extra)
        return sid, sess


# ---------------------------------------------------------------------------
# Error handler test base
# ---------------------------------------------------------------------------

class ErrorHandlerTestCase:
    """Base for tests targeting the DeckBuilderError → HTTP response pipeline.

    Spins up a minimal FastAPI app with only the error handler — no routes from
    the real app, so tests are fast and isolated.

    Example:
        class TestMyErrors(ErrorHandlerTestCase):
            def test_custom_error(self):
                from code.exceptions import ThemeSelectionError
                self._register_raiser("/raise", ThemeSelectionError("bad theme"))
                resp = self.error_client.get("/raise")
                self.assert_json_error(resp, status=400, error_type="ThemeSelectionError")
    """

    @pytest.fixture(autouse=True)
    def setup_error_app(self):
        from fastapi import FastAPI, Request
        from code.exceptions import DeckBuilderError
        from code.web.utils.responses import deck_builder_error_response

        self._mini_app = FastAPI()
        self._raisers: dict[str, Exception] = {}

        app = self._mini_app

        @app.exception_handler(Exception)
        async def handler(request: Request, exc: Exception):
            if isinstance(exc, DeckBuilderError):
                return deck_builder_error_response(request, exc)
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "unhandled", "detail": str(exc)}, status_code=500)

        with TestClient(app, raise_server_exceptions=False) as c:
            self.error_client = c
        yield

    def _register_raiser(self, path: str, exc: Exception) -> None:
        """Add a GET endpoint that raises `exc` when called."""
        from fastapi import Request

        @self._mini_app.get(path)
        async def _raiser(request: Request):
            raise exc

        # Rebuild the client after adding the route
        with TestClient(self._mini_app, raise_server_exceptions=False) as c:
            self.error_client = c

    def assert_json_error(self, resp, *, status: int, error_type: str | None = None) -> dict:
        assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("error") is True
        if error_type:
            assert data.get("error_type") == error_type
        return data


# ---------------------------------------------------------------------------
# Service test base
# ---------------------------------------------------------------------------

class ServiceTestCase:
    """Base class for service unit tests.

    Provides helpers for creating mock dependencies and asserting common
    service behaviors. No TestClient — services are tested directly.

    Example:
        class TestSessionManager(ServiceTestCase):
            def test_new_session_is_empty(self):
                from code.web.services.tasks import SessionManager
                mgr = SessionManager()
                sess = mgr.get("new-key")
                assert sess == {}
    """

    def make_mock(self, **attrs) -> MagicMock:
        """Create a MagicMock with the given attributes pre-set."""
        m = MagicMock()
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    def assert_raises(self, exc_type, fn, *args, **kwargs):
        """Assert that fn(*args, **kwargs) raises exc_type."""
        with pytest.raises(exc_type):
            fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Validation test mixin
# ---------------------------------------------------------------------------

class ValidationTestMixin:
    """Mixin for Pydantic model validation tests.

    Example:
        class TestBuildRequest(ValidationTestMixin):
            MODEL = BuildRequest

            def test_commander_required(self):
                self.assert_validation_error(commander="")
    """

    MODEL = None  # Set in subclass

    def build(self, **kwargs) -> Any:
        """Instantiate MODEL with kwargs. Raises ValidationError on invalid input."""
        assert self.MODEL is not None, "Set MODEL in your test class"
        return self.MODEL(**kwargs)

    def assert_validation_error(self, **kwargs) -> None:
        """Assert that MODEL(**kwargs) raises a Pydantic ValidationError."""
        from pydantic import ValidationError
        assert self.MODEL is not None
        with pytest.raises(ValidationError):
            self.MODEL(**kwargs)
