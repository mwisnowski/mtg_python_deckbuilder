"""Price check endpoint for the public REST API (R28 Milestone 8).

Reuses `price_service.get_price_service()` (the same Scryfall-bulk-data +
JSON-cache backed service used by `code/web/routes/price.py`) instead of
duplicating price-cache logic. Public endpoint (no auth required).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request

from ...services.price_service import get_price_service
from ...utils.api_response import ok

router = APIRouter(prefix="/prices", tags=["prices"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


@router.get("/{card_name:path}", summary="Get card price")
async def get_card_price(
    card_name: str,
    request: Request,
    region: str = Query("usd", pattern="^(usd|eur)$"),
    foil: bool = Query(False),
):
    """TCG (Scryfall) + Card Kingdom price lookup for a single card."""
    svc = get_price_service()
    price = svc.get_price(card_name, region=region, foil=foil)
    ck_price = svc.get_ck_price(card_name)
    return ok(
        {
            "card_name": card_name,
            "price": price,
            "ck_price": ck_price,
            "region": region,
            "foil": foil,
            "found": price is not None,
        },
        _rid(request),
    )
