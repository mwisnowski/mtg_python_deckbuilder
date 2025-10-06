from __future__ import annotations

from typing import Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from deck_builder.combined_commander import PartnerMode

from ..app import ENABLE_PARTNER_MECHANICS, ENABLE_PARTNER_SUGGESTIONS
from ..services.partner_suggestions import get_partner_suggestions
from ..services.telemetry import log_partner_suggestions_generated

router = APIRouter(prefix="/api/partner", tags=["partner suggestions"])


def _parse_modes(values: Optional[Iterable[str]]) -> list[PartnerMode]:
    if not values:
        return []
    modes: list[PartnerMode] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = str(value).strip().replace("-", "_").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        for mode in PartnerMode:
            if mode.value == normalized:
                modes.append(mode)
                break
    return modes


def _coerce_name_list(values: Optional[Iterable[str]]) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


@router.get("/suggestions")
async def partner_suggestions_api(
    request: Request,
    commander: str = Query(..., min_length=1, description="Primary commander display name"),
    limit: int = Query(5, ge=1, le=20, description="Maximum suggestions per partner mode"),
    visible_limit: int = Query(3, ge=0, le=10, description="Number of suggestions to mark as visible"),
    include_hidden: bool = Query(False, description="When true, include hidden suggestions in the response"),
    partner: Optional[List[str]] = Query(None, description="Available partner commander names"),
    background: Optional[List[str]] = Query(None, description="Available background names"),
    mode: Optional[List[str]] = Query(None, description="Restrict results to specific partner modes"),
    refresh: bool = Query(False, description="When true, force a dataset refresh before scoring"),
):
    if not (ENABLE_PARTNER_MECHANICS and ENABLE_PARTNER_SUGGESTIONS):
        raise HTTPException(status_code=404, detail="Partner suggestions are disabled")

    commander_name = (commander or "").strip()
    if not commander_name:
        raise HTTPException(status_code=400, detail="Commander name is required")

    include_modes = _parse_modes(mode)
    result = get_partner_suggestions(
        commander_name,
        limit_per_mode=limit,
        include_modes=include_modes or None,
        refresh_dataset=refresh,
    )
    if result is None:
        raise HTTPException(status_code=503, detail="Partner suggestion dataset is unavailable")

    partner_names = _coerce_name_list(partner)
    background_names = _coerce_name_list(background)

    # If the client didn't provide select options, fall back to the suggestions themselves.
    if not partner_names:
        for key, entries in result.by_mode.items():
            if key == PartnerMode.BACKGROUND.value:
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name_value = entry.get("name")
                if isinstance(name_value, str) and name_value.strip():
                    partner_names.append(name_value)
    if not background_names:
        background_entries = result.by_mode.get(PartnerMode.BACKGROUND.value, [])
        for entry in background_entries:
            if not isinstance(entry, dict):
                continue
            name_value = entry.get("name")
            if isinstance(name_value, str) and name_value.strip():
                background_names.append(name_value)

    partner_names = _coerce_name_list(partner_names)
    background_names = _coerce_name_list(background_names)

    visible, hidden = result.flatten(partner_names, background_names, visible_limit=visible_limit)
    visible_count = len(visible)
    hidden_count = len(hidden)
    if include_hidden:
        combined_visible = visible + hidden
        remaining = []
    else:
        combined_visible = visible
        remaining = hidden

    payload = {
        "commander": {
            "display_name": result.display_name,
            "canonical": result.canonical,
        },
        "metadata": result.metadata,
        "modes": result.by_mode,
        "visible": combined_visible,
        "hidden": remaining,
        "total": result.total,
        "limit": {
            "per_mode": limit,
            "visible": visible_limit,
        },
        "available_modes": [mode_key for mode_key, entries in result.by_mode.items() if entries],
        "has_hidden": bool(remaining),
    }

    headers = {"Cache-Control": "no-store"}
    try:
        mode_counts = {mode_key: len(entries) for mode_key, entries in result.by_mode.items()}
        available_modes = [mode_key for mode_key, count in mode_counts.items() if count]
        log_partner_suggestions_generated(
            request,
            commander_display=result.display_name,
            commander_canonical=result.canonical,
            include_modes=[mode.value for mode in include_modes] if include_modes else [],
            available_modes=available_modes,
            total=result.total,
            mode_counts=mode_counts,
            visible_count=visible_count,
            hidden_count=hidden_count,
            limit_per_mode=limit,
            visible_limit=visible_limit,
            include_hidden=include_hidden,
            refresh_requested=refresh,
            dataset_metadata=result.metadata,
        )
    except Exception:  # pragma: no cover - telemetry should not break responses
        pass
    return JSONResponse(payload, headers=headers)
