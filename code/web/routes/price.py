"""Price API routes for card price lookups.

Provides endpoints for single-card and batch price queries backed by
the PriceService (Scryfall bulk data + JSON cache).
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional
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
    printing: str = Query(default="", description="Scryfall ID of a specific printing to price"),
):
    """Look up the price for a single card.

    Args:
        card_name: Card name (URL-encoded, case-insensitive).
        region: Price region — ``usd`` or ``eur``.
        foil: If true, return the foil price.
        printing: Optional Scryfall ID of a specific printing to price
            instead of the cheapest-by-name default.

    Returns:
        JSON with ``card_name``, ``price`` (float or null), ``region``,
        ``foil`` (whether the returned ``price`` is actually a foil price --
        may differ from the requested *foil* flag for a foil-only printing),
        ``found`` (bool).
    """
    name = unquote(card_name).strip()
    svc = get_price_service()
    price, actual_foil = svc.get_price_detail(name, region=region, foil=foil, scryfall_id=printing or None)
    ck_price = svc.get_ck_price(name)
    return JSONResponse({
        "card_name": name,
        "price": price,
        "ck_price": ck_price,
        "region": region,
        "foil": actual_foil,
        "found": price is not None,
    })


@router.post("/batch")
@track_route_access("price_batch_lookup")
@log_route_errors("price_batch_lookup")
async def get_prices_batch(
    card_names: List[str] = Body(..., embed=True, max_length=100),
    printing_map: Optional[Dict[str, str]] = Body(default=None, embed=True),
    foil_map: Optional[Dict[str, bool]] = Body(default=None, embed=True),
    region: str = Query("usd", pattern="^(usd|eur)$"),
    foil: bool = Query(False),
):
    """Look up prices for multiple cards in a single request.

    Request body: ``{"card_names": [...], "printing_map": {...}}``.

    Args:
        card_names: List of card names (max 100).
        printing_map: Optional ``{name.lower(): scryfall_id}`` overrides so
            a card with a chosen alternate printing is priced using that
            printing instead of the cheapest-by-name default.
        foil_map: Optional ``{name.lower(): bool}`` per-card foil overrides
            so a card's own foil choice is used instead of the global
            *foil* flag below.
        region: Price region — ``usd`` or ``eur``.
        foil: If true, return foil prices (for any name not in *foil_map*).

    Returns:
        JSON with ``prices`` (dict name→{price, ck_price}) and ``missing``
        (list of names with no TCG price data).
    """
    svc = get_price_service()
    tcg_prices = svc.get_prices_batch(card_names, region=region, foil=foil, printing_map=printing_map, foil_map=foil_map)
    ck_prices = svc.get_ck_prices_batch(card_names)
    missing = [n for n, p in tcg_prices.items() if p is None]
    prices = {
        n: {"price": tcg_prices.get(n), "ck_price": ck_prices.get(n)}
        for n in card_names
    }
    return JSONResponse({
        "prices": prices,
        "missing": missing,
        "region": region,
        "foil": foil,
        "total": len(card_names),
        "found": len(card_names) - len(missing),
    })
