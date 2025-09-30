from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import Request

__all__ = [
    "log_commander_page_view",
    "log_commander_create_deck",
]

_LOGGER = logging.getLogger("web.commander_browser")


def _emit(logger: logging.Logger, payload: Dict[str, Any]) -> None:
    try:
        logger.info(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    except Exception:
        pass


def _request_id(request: Request) -> str | None:
    try:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return str(rid)
    except Exception:
        return None
    return None


def _client_ip(request: Request) -> str | None:
    try:
        client = getattr(request, "client", None)
        if client and getattr(client, "host", None):
            return str(client.host)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    except Exception:
        return None
    return None


def _query_snapshot(request: Request) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    try:
        params = request.query_params
        items = params.multi_items() if hasattr(params, "multi_items") else params.items()
        for key, value in items:
            key = str(key)
            value = str(value)
            if key in snapshot:
                existing = snapshot[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    snapshot[key] = [existing, value]
            else:
                snapshot[key] = value
    except Exception:
        return {}
    return snapshot


def log_commander_page_view(
    request: Request,
    *,
    page: int,
    result_total: int,
    result_count: int,
    is_htmx: bool,
) -> None:
    payload: Dict[str, Any] = {
        "event": "commander_browser.page_view",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "query": _query_snapshot(request),
        "page": int(page),
        "result_total": int(result_total),
        "result_count": int(result_count),
        "is_htmx": bool(is_htmx),
        "client_ip": _client_ip(request),
    }
    _emit(_LOGGER, payload)


def log_commander_create_deck(
    request: Request,
    *,
    commander: str,
    return_url: str | None,
) -> None:
    payload: Dict[str, Any] = {
        "event": "commander_browser.create_deck",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "query": _query_snapshot(request),
        "commander": commander,
        "has_return": bool(return_url),
        "return_url": return_url,
        "client_ip": _client_ip(request),
    }
    _emit(_LOGGER, payload)
