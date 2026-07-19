"""Commander catalog endpoints for the public REST API (R28 Milestone 6).

Reuses `commander_catalog_loader.py` (the same catalog the HTML commander
browser and partner-selection wizard use) instead of duplicating parsing or
filtering logic. All endpoints here are public (no auth required).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder

from ...services.commander_catalog_loader import (
    CommanderRecord,
    find_commander_record,
    load_commander_catalog,
)
from ...utils.api_response import err, ok

router = APIRouter(prefix="/commanders", tags=["commanders"])

MAX_PAGE_SIZE = 100


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _serialize_commander(record: CommanderRecord, *, full: bool = False) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "name": record.display_name,
        "slug": record.slug,
        "color_identity": list(record.color_identity),
        "mana_cost": record.mana_cost,
        "mana_value": record.mana_value,
        "type_line": record.type_line,
        "edhrec_rank": record.edhrec_rank,
        "image_normal_url": record.image_normal_url,
        "is_partner": record.is_partner,
        "supports_backgrounds": record.supports_backgrounds,
        "is_background": record.is_background,
    }
    if full:
        data.update(
            {
                "oracle_text": record.oracle_text,
                "power": record.power,
                "toughness": record.toughness,
                "keywords": list(record.keywords),
                "themes": list(record.themes),
                "partner_with": list(record.partner_with),
                "is_doctor": record.is_doctor,
                "is_doctors_companion": record.is_doctors_companion,
            }
        )
    return jsonable_encoder(data)


@router.get("", summary="Search commanders")
async def list_commanders(
    request: Request,
    q: str = Query("", description="Name / oracle-text search"),
    colors: str = Query("", description="Comma-separated color identity, e.g. W,U (exact match)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Search/filter commanders."""
    catalog = load_commander_catalog()
    records = list(catalog.entries)

    if q:
        q_lower = q.lower()
        records = [r for r in records if q_lower in r.search_haystack]

    if colors:
        color_list = [c.strip().upper() for c in colors.split(",") if c.strip()]
        if "C" in color_list or "COLORLESS" in color_list:
            records = [r for r in records if r.is_colorless]
        elif color_list:
            color_set = set(color_list)
            records = [r for r in records if set(r.color_identity) == color_set]

    total = len(records)
    start = (page - 1) * page_size
    page_records = records[start : start + page_size]

    return ok(
        {
            "commanders": [_serialize_commander(r) for r in page_records],
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        _rid(request),
    )


@router.get("/{name}/partners", summary="Get partner suggestions")
async def get_commander_partners(name: str, request: Request):
    """Valid partner/background suggestions for a commander (reuses build_partners.py)."""
    from ...routes.build_partners import _build_partner_options

    record = find_commander_record(name)
    if record is None:
        return err("Commander not found.", "COMMANDER_NOT_FOUND", 404, _rid(request))
    options, variant = _build_partner_options(record)
    return ok({"variant": variant, "options": jsonable_encoder(options)}, _rid(request))


@router.get("/{name}", summary="Get commander detail")
async def get_commander_detail(name: str, request: Request):
    """Commander detail."""
    record = find_commander_record(name)
    if record is None:
        return err("Commander not found.", "COMMANDER_NOT_FOUND", 404, _rid(request))
    return ok(_serialize_commander(record, full=True), _rid(request))
