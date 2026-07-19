"""Response envelope helpers for the public `/api/v1` REST API.

Every `/api/v1` endpoint returns one of two shapes:

    Success: {"ok": true, "data": ..., "request_id": "..."}
    Error:   {"ok": false, "error": "...", "code": "SNAKE_CASE", "request_id": "...", "details"?: ...}

Kept separate from `code/web/utils/responses.py` (the HTML/HTMX-era error
builder) since the public API contract intentionally differs from the
internal web UI's error shape.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from fastapi.responses import JSONResponse


def ok(data: Any, request_id: str, status_code: int = 200) -> JSONResponse:
    """Build a success envelope response."""
    return JSONResponse({"ok": True, "data": data, "request_id": request_id}, status_code=status_code)


def err(
    message: str,
    code: str,
    status_code: int,
    request_id: str,
    *,
    details: Optional[Any] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    """Build an error envelope response."""
    content: dict[str, Any] = {"ok": False, "error": message, "code": code, "request_id": request_id}
    if details is not None:
        content["details"] = details
    return JSONResponse(content, status_code=status_code, headers=dict(headers) if headers else None)
