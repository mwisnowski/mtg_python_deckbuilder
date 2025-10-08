from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from fastapi import Request

__all__ = [
    "log_commander_page_view",
    "log_commander_create_deck",
    "log_partner_suggestions_generated",
    "log_partner_suggestion_selected",
    "log_include_exclude_toggle",
    "log_frontend_event",
]

_LOGGER = logging.getLogger("web.commander_browser")
_PARTNER_LOGGER = logging.getLogger("web.partner_suggestions")
_MUST_HAVE_LOGGER = logging.getLogger("web.must_haves")
_FRONTEND_LOGGER = logging.getLogger("web.frontend_events")


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


def _extract_dataset_metadata(metadata: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    snapshot: Dict[str, Any] = {}
    for key in ("dataset_version", "generated_at", "record_count", "entry_count", "build_id"):
        if key in metadata:
            snapshot[key] = metadata[key]
    if not snapshot:
        # Fall back to a small subset to avoid logging the full metadata document.
        for key, value in list(metadata.items())[:5]:
            snapshot[key] = value
    return snapshot


def log_partner_suggestions_generated(
    request: Request,
    *,
    commander_display: str,
    commander_canonical: str,
    include_modes: Sequence[str] | None,
    available_modes: Sequence[str],
    total: int,
    mode_counts: Mapping[str, int],
    visible_count: int,
    hidden_count: int,
    limit_per_mode: int,
    visible_limit: int,
    include_hidden: bool,
    refresh_requested: bool,
    dataset_metadata: Mapping[str, Any] | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "event": "partner_suggestions.generated",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "query": _query_snapshot(request),
        "commander": {
            "display": commander_display,
            "canonical": commander_canonical,
        },
        "limits": {
            "per_mode": int(limit_per_mode),
            "visible": int(visible_limit),
            "include_hidden": bool(include_hidden),
        },
        "result": {
            "total": int(total),
            "visible_count": int(visible_count),
            "hidden_count": int(hidden_count),
            "available_modes": list(available_modes),
            "mode_counts": {str(key): int(value) for key, value in mode_counts.items()},
            "metadata": _extract_dataset_metadata(dataset_metadata),
        },
        "filters": {
            "include_modes": [str(mode) for mode in (include_modes or [])],
            "refresh": bool(refresh_requested),
        },
        "client_ip": _client_ip(request),
    }
    _emit(_PARTNER_LOGGER, payload)


def log_partner_suggestion_selected(
    request: Request,
    *,
    commander: str,
    scope: str | None,
    partner_enabled: bool,
    auto_opt_out: bool,
    auto_assigned: bool,
    selection_source: Optional[str],
    secondary_candidate: str | None,
    background_candidate: str | None,
    resolved_secondary: str | None,
    resolved_background: str | None,
    partner_mode: str | None,
    has_preview: bool,
    warnings: Sequence[str] | None,
    error: str | None,
) -> None:
    payload: Dict[str, Any] = {
        "event": "partner_suggestions.selected",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "scope": scope or "",
        "commander": commander,
        "partner_enabled": bool(partner_enabled),
        "auto_opt_out": bool(auto_opt_out),
        "auto_assigned": bool(auto_assigned),
        "selection_source": (selection_source or "") or None,
        "inputs": {
            "secondary_candidate": secondary_candidate,
            "background_candidate": background_candidate,
        },
        "resolved": {
            "partner_mode": partner_mode,
            "secondary": resolved_secondary,
            "background": resolved_background,
        },
        "preview_available": bool(has_preview),
        "warnings_count": len(warnings or []),
        "has_error": bool(error),
        "error": error,
        "client_ip": _client_ip(request),
    }
    if warnings:
        payload["warnings"] = list(warnings)
    _emit(_PARTNER_LOGGER, payload)


def log_include_exclude_toggle(
    request: Request,
    *,
    card_name: str,
    action: str,
    enabled: bool,
    include_count: int,
    exclude_count: int,
) -> None:
    payload: Dict[str, Any] = {
        "event": "must_haves.toggle",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "card": card_name,
        "list": action,
        "enabled": bool(enabled),
        "include_count": int(include_count),
        "exclude_count": int(exclude_count),
        "client_ip": _client_ip(request),
    }
    _emit(_MUST_HAVE_LOGGER, payload)


def log_frontend_event(
    request: Request,
    event: str,
    data: Mapping[str, Any] | None,
) -> None:
    snapshot: Dict[str, Any] = {}
    if isinstance(data, Mapping):
        snapshot = {str(k): data[k] for k in data}
    payload: Dict[str, Any] = {
        "event": f"frontend.{event}",
        "request_id": _request_id(request),
        "path": str(request.url.path),
        "data": snapshot,
        "referer": request.headers.get("referer"),
        "client_ip": _client_ip(request),
    }
    _emit(_FRONTEND_LOGGER, payload)
