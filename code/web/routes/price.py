"""Price API routes for card price lookups.

Provides endpoints for single-card and batch price queries backed by
the PriceService (Scryfall bulk data + JSON cache).
"""
from __future__ import annotations

import threading
from typing import List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from code.web.services.price_service import get_price_service
from code.web.decorators.telemetry import track_route_access, log_route_errors

router = APIRouter(prefix="/api/price")


@router.get("/stats")
@track_route_access("price_cache_stats")
async def price_cache_stats():
    """Return cache telemetry for the PriceService."""
    svc = get_price_service()
    return JSONResponse(svc.cache_stats())


@router.post("/refresh")
@track_route_access("price_cache_refresh")
async def refresh_price_cache():
    """Trigger a background rebuild of the price cache and parquet price columns.

    Returns immediately — the rebuild runs in a daemon thread.
    """
    def _run() -> None:
        try:
            from code.file_setup.setup import refresh_prices_parquet
            refresh_prices_parquet()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Manual price refresh failed: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="price-manual-refresh")
    t.start()
    return JSONResponse({"ok": True, "message": "Price cache refresh started in background."})


@router.get("/{card_name:path}")
@track_route_access("price_lookup")
@log_route_errors("price_lookup")
async def get_card_price(
    card_name: str,
    region: str = Query("usd", pattern="^(usd|eur)$"),
    foil: bool = Query(False),
):
    """Look up the price for a single card.

    Args:
        card_name: Card name (URL-encoded, case-insensitive).
        region: Price region — ``usd`` or ``eur``.
        foil: If true, return the foil price.

    Returns:
        JSON with ``card_name``, ``price`` (float or null), ``region``,
        ``foil``, ``found`` (bool).
    """
    name = unquote(card_name).strip()
    svc = get_price_service()
    price = svc.get_price(name, region=region, foil=foil)
    return JSONResponse({
        "card_name": name,
        "price": price,
        "region": region,
        "foil": foil,
        "found": price is not None,
    })


@router.post("/batch")
@track_route_access("price_batch_lookup")
@log_route_errors("price_batch_lookup")
async def get_prices_batch(
    card_names: List[str] = Body(..., max_length=100),
    region: str = Query("usd", pattern="^(usd|eur)$"),
    foil: bool = Query(False),
):
    """Look up prices for multiple cards in a single request.

    Request body: JSON array of card name strings (max 100).

    Args:
        card_names: List of card names.
        region: Price region — ``usd`` or ``eur``.
        foil: If true, return foil prices.

    Returns:
        JSON with ``prices`` (dict name→float|null) and ``missing`` (list
        of names with no price data).
    """
    svc = get_price_service()
    prices = svc.get_prices_batch(card_names, region=region, foil=foil)
    missing = [n for n, p in prices.items() if p is None]
    return JSONResponse({
        "prices": prices,
        "missing": missing,
        "region": region,
        "foil": foil,
        "total": len(card_names),
        "found": len(card_names) - len(missing),
    })
