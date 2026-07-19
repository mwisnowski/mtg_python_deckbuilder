"""Card browser endpoints for the public REST API (R28 Milestone 4).

Reuses `AllCardsLoader` (code/services/all_cards_loader.py), `CardSimilarity`
(code/web/services/card_similarity.py), and `get_rulings()` from R27
(code/web/services/rulings.py) -- the same building blocks as the HTML card
browser (code/web/routes/card_browser.py) -- instead of duplicating filter
logic. All endpoints here are public (no auth required).

Route ordering note: `/similar` and `/rulings` are registered before the
bare `/{name}` detail route, using `:path` converters, so double-faced card
names containing `/` (e.g. "Fire // Ice") still resolve correctly -- mirrors
the same trick used in card_browser.py.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder

from code.deck_builder.builder_utils import parse_theme_tags
from code.services.all_cards_loader import AllCardsLoader

from ...services.card_similarity import CardSimilarity
from ...services.rulings import get_rulings
from ...utils.api_response import err, ok

router = APIRouter(prefix="/cards", tags=["cards"])

MAX_PAGE_SIZE = 100

_loader: Optional[AllCardsLoader] = None
_similarity: Optional[CardSimilarity] = None


def _get_loader() -> AllCardsLoader:
    global _loader
    if _loader is None:
        _loader = AllCardsLoader()
    return _loader


def _get_similarity() -> CardSimilarity:
    global _similarity
    if _similarity is None:
        _similarity = CardSimilarity(_get_loader().load())
    return _similarity


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _serialize_card(row, *, full: bool = False) -> Dict[str, Any]:
    card = row.to_dict()
    data: Dict[str, Any] = {
        "name": card.get("name"),
        "type": card.get("type"),
        "manaValue": card.get("manaValue"),
        "colorIdentity": card.get("colorIdentity"),
        "rarity": card.get("rarity"),
        "themeTags": parse_theme_tags(card.get("themeTags")),
        "edhrecRank": card.get("edhrecRank"),
        "scryfallID": card.get("scryfallID"),
    }
    if full:
        data.update(
            {
                "text": card.get("text"),
                "power": card.get("power"),
                "toughness": card.get("toughness"),
                "printings": card.get("printings"),
                "layout": card.get("layout"),
                "isNew": card.get("isNew"),
            }
        )
    return jsonable_encoder(data)


@router.get("", summary="Search cards")
async def list_cards(
    request: Request,
    q: str = Query("", description="Name / type / oracle-text search"),
    colors: str = Query("", description="Comma-separated color identity, e.g. W,U"),
    tags: str = Query("", description="Comma-separated theme tags (AND logic)"),
    min_cmc: Optional[float] = Query(None, ge=0),
    max_cmc: Optional[float] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Search/filter cards. Mirrors card_browser.py's filters, simplified for JSON I/O."""
    df = _get_loader().load()

    if q:
        mask = df["name"].str.contains(q, case=False, na=False)
        if "type" in df.columns:
            mask |= df["type"].str.contains(q, case=False, na=False)
        if "text" in df.columns:
            mask |= df["text"].str.contains(q, case=False, na=False)
        df = df[mask]

    if colors:
        color_list = [c.strip().upper() for c in colors.split(",") if c.strip()]
        if color_list and "colorIdentity" in df.columns:
            df = df[df["colorIdentity"].isin(color_list)]

    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        if tag_list and "themeTags" in df.columns:
            # themeTags may be stored as a string, list, or numpy array depending on
            # source (raw CSV vs. Parquet) -- parse_theme_tags() normalizes all of them.
            parsed = df["themeTags"].apply(lambda v: {t.lower() for t in parse_theme_tags(v)})
            mask = parsed.apply(lambda card_tags: all(tag in card_tags for tag in tag_list))
            df = df[mask]

    if min_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] >= min_cmc]
    if max_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] <= max_cmc]

    total = len(df)
    start = (page - 1) * page_size
    page_df = df.iloc[start : start + page_size]

    return ok(
        {
            "cards": [_serialize_card(row) for _, row in page_df.iterrows()],
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        _rid(request),
    )


@router.get("/{name:path}/similar", summary="Find similar cards")
async def get_card_similar(name: str, request: Request, limit: int = Query(10, ge=1, le=50)):
    """Similar cards by theme-tag overlap (reuses CardSimilarity)."""
    row = _get_loader().get_by_name(name)
    if row is None:
        return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
    similar = _get_similarity().find_similar(name, limit=limit)
    return ok(jsonable_encoder(similar), _rid(request))


@router.get("/{name:path}/rulings", summary="Get card rulings")
async def get_card_rulings(name: str, request: Request):
    """Card rulings, cache-first with a live Scryfall fallback (R27)."""
    row = _get_loader().get_by_name(name)
    if row is None:
        return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
    scryfall_id = row.get("scryfallID") or ""
    rulings = await get_rulings(scryfall_id) if scryfall_id else []
    return ok(jsonable_encoder(rulings), _rid(request))


@router.get("/{name:path}", summary="Get card detail")
async def get_card_detail(name: str, request: Request):
    """Card detail: stats, tags, oracle text, scryfall_id."""
    row = _get_loader().get_by_name(name)
    if row is None:
        return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
    return ok(_serialize_card(row, full=True), _rid(request))
