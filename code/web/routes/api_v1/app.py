"""FastAPI sub-application for the public `/api/v1` REST API.

Mounted onto the main app via `app.mount("/api/v1", api_v1_app)` in
`code/web/app.py`. Deliberately a full `FastAPI` instance (not just an
`APIRouter`) so it gets:

  - its own OpenAPI schema and Swagger/Redoc docs, isolated from the main
    app's `/docs` (which covers every internal HTML/HTMX route)
  - its own exception handlers, wrapping every error into the `{ok, ...}`
    envelope without touching the main app's HTML error pages

See roadmap_28_public_api.md's "Docs isolation" and "Global error envelope"
decisions.
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ...utils.api_response import err

logger = logging.getLogger(__name__)


def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# Set 0 to disable interactive docs (e.g. in production).
API_DOCS_ENABLED = _as_bool(os.getenv("API_DOCS_ENABLED"), True)

api_v1_app = FastAPI(
    title="MTG Deckbuilder API",
    version="1",
    description=(
        "Public REST API for the MTG Commander/EDH deckbuilder. Every response is a "
        "JSON envelope: `{\"ok\": true, \"data\": ..., \"request_id\": \"...\"}` on "
        "success, or `{\"ok\": false, \"error\": \"...\", \"code\": \"SNAKE_CASE\", "
        "\"request_id\": \"...\"}` on failure. Authenticate with `Authorization: "
        "Bearer <api_key>` (obtained via `POST /auth/login` or `POST /keys`); "
        "endpoints without that requirement are public."
    ),
    docs_url="/docs" if API_DOCS_ENABLED else None,
    redoc_url="/redoc" if API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if API_DOCS_ENABLED else None,
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


@api_v1_app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = _request_id(request)
    code = f"HTTP_{exc.status_code}"
    headers = getattr(exc, "headers", None)
    return err(str(exc.detail), code, exc.status_code, rid, headers=headers)


@api_v1_app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = _request_id(request)
    return err("Invalid request parameters.", "VALIDATION_ERROR", 422, rid, details=exc.errors())


@api_v1_app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    rid = _request_id(request)
    logger.error(
        "api_v1 unhandled exception [rid=%s] %s %s",
        rid, request.method, request.url.path, exc_info=True,
    )
    return err("Internal server error.", "INTERNAL_ERROR", 500, rid)


# Sub-routers
from .keys import router as keys_router  # noqa: E402
from .builds import router as builds_router  # noqa: E402
from .cards import router as cards_router  # noqa: E402
from .decks import router as decks_router  # noqa: E402
from .commanders import router as commanders_router  # noqa: E402
from .themes import router as themes_router  # noqa: E402
from .owned import router as owned_router  # noqa: E402
from .prices import router as prices_router  # noqa: E402
from .configs import router as configs_router  # noqa: E402
from .users import router as users_router  # noqa: E402

api_v1_app.include_router(keys_router)
api_v1_app.include_router(builds_router)
api_v1_app.include_router(cards_router)
api_v1_app.include_router(decks_router)
api_v1_app.include_router(commanders_router)
api_v1_app.include_router(themes_router)
api_v1_app.include_router(owned_router)
api_v1_app.include_router(prices_router)
api_v1_app.include_router(configs_router)
api_v1_app.include_router(users_router)
