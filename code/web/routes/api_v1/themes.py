"""Theme catalog endpoints for the public REST API (R28 Milestone 6).

Reuses `theme_catalog_loader.py` (list/filter/detail projections) and
`theme_preview.py`'s `get_theme_preview()` (the same cached preview-card
sampler used by the HTML theme browser) instead of duplicating logic. All
endpoints here are public (no auth required).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder

from ...services.theme_catalog_loader import (
    filter_slugs_fast,
    load_index,
    summaries_for_slugs,
)
from ...services.theme_preview import get_theme_preview
from ...utils.api_response import err, ok

router = APIRouter(prefix="/themes", tags=["themes"])

MAX_PAGE_SIZE = 100


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


@router.get("", summary="List themes")
async def list_themes(
    request: Request,
    q: str = Query("", description="Substring filter on theme name/synergies"),
    colors: str = Query("", description="Comma-separated color initials, e.g. G,W"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
):
    """List/search all themes."""
    try:
        idx = load_index()
    except FileNotFoundError:
        return err("Theme catalog unavailable.", "CATALOG_UNAVAILABLE", 503, _rid(request))

    color_list: Optional[list] = [c.strip() for c in colors.split(",") if c.strip()] if colors else None
    slugs = filter_slugs_fast(idx, q=q or None, archetype=None, bucket=None, colors=color_list)

    total = len(slugs)
    start = (page - 1) * page_size
    page_slugs = slugs[start : start + page_size]
    items = summaries_for_slugs(idx, page_slugs)
    for item in items:
        item.pop("has_fallback_description", None)
        item.pop("editorial_quality", None)

    return ok(
        {
            "themes": jsonable_encoder(items),
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        _rid(request),
    )


@router.get("/{theme:path}", summary="Get theme detail and preview")
async def get_theme_detail(
    theme: str,
    request: Request,
    preview_limit: int = Query(12, ge=1, le=30, description="Number of preview cards to include"),
):
    """Theme detail plus a sample of preview cards (reuses theme_preview.get_theme_preview)."""
    try:
        payload = get_theme_preview(theme, limit=preview_limit)
    except KeyError:
        return err("Theme not found.", "THEME_NOT_FOUND", 404, _rid(request))
    except FileNotFoundError:
        return err("Theme catalog unavailable.", "CATALOG_UNAVAILABLE", 503, _rid(request))
    payload.pop("has_fallback_description", None)
    payload.pop("editorial_quality", None)
    return ok(jsonable_encoder(payload), _rid(request))
