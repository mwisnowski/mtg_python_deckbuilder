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

import asyncio
import logging
import math
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder

from code.deck_builder.builder_utils import parse_theme_tags
from code.services.all_cards_loader import AllCardsLoader

from ...services.card_search import (
    ColorClause,
    ManaCostClause,
    NumericClause,
    ParsedSearch,
    apply_color_clauses as _apply_color_clauses,
    apply_mana_cost_clauses as _apply_mana_cost_clauses,
    apply_name_clauses as _apply_name_clauses,
    apply_numeric_clauses as _apply_numeric_clauses,
    apply_text_clauses as _apply_text_clauses,
    parse_color_cell as _parse_color_cell,
    parse_search_query as _parse_search_query,
)
from ...services.card_similarity import CardSimilarity
from ...services.rulings import get_rulings
from ...utils.api_response import err, ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])

# --- Live Scryfall fallback for cards missing from the local tagged dataset
#
# Basic lands (Plains, Island, Swamp, Mountain, Forest, Wastes, and their
# snow-covered variants) are intentionally excluded from tagging/all_cards.parquet
# -- there's nothing to tag on a card with no rules text -- but the mobile app's
# card detail/summary dialog still needs *something* to show for them. More
# generally, any card can be temporarily missing if the local database hasn't
# been refreshed yet, so this fallback applies to every miss, not just basics.
_SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
_SCRYFALL_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"
_SCRYFALL_FALLBACK_RATE_LIMIT = 0.1  # 100ms between live fetches (10 req/s)
_scryfall_fallback_lock = asyncio.Lock()
_scryfall_fallback_last_fetch: float = 0.0


async def _scryfall_card_fallback(name: str) -> Optional[Dict[str, Any]]:
    """Live Scryfall lookup for a card missing from the local tagged dataset,
    shaped like _serialize_card(..., full=True). Returns None on any miss/error."""
    global _scryfall_fallback_last_fetch
    async with _scryfall_fallback_lock:
        wait = _SCRYFALL_FALLBACK_RATE_LIMIT - (time.monotonic() - _scryfall_fallback_last_fetch)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(headers={"User-Agent": _SCRYFALL_USER_AGENT}, timeout=10.0) as client:
                resp = await client.get(_SCRYFALL_NAMED_URL, params={"exact": name})
                _scryfall_fallback_last_fetch = time.monotonic()
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"Scryfall card fallback failed for '{name}': {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error in Scryfall card fallback for '{name}': {e}")
            return None

    card_faces = data.get("card_faces") or []
    primary_face = card_faces[0] if card_faces else {}
    result: Dict[str, Any] = {
        "name": data.get("name"),
        "type": data.get("type_line"),
        "manaValue": data.get("cmc"),
        "colorIdentity": ",".join(data.get("color_identity") or []),
        "rarity": data.get("rarity"),
        "themeTags": [],
        "edhrecRank": data.get("edhrec_rank"),
        "scryfallID": data.get("id"),
        "text": data.get("oracle_text") or primary_face.get("oracle_text"),
        "power": data.get("power") or primary_face.get("power"),
        "toughness": data.get("toughness") or primary_face.get("toughness"),
        "printings": None,
        "layout": data.get("layout"),
        "isNew": None,
        "faces": [
            {
                "name": face.get("name"),
                "side": chr(ord("a") + i),
                "type": face.get("type_line"),
                "text": face.get("oracle_text"),
                "manaValue": face.get("cmc"),
                "power": face.get("power"),
                "toughness": face.get("toughness"),
                "colorIdentity": ",".join(face.get("colors") or []),
            }
            for i, face in enumerate(card_faces)
        ]
        if len(card_faces) > 1
        else [],
    }
    return jsonable_encoder({k: _json_safe(v) for k, v in result.items()})

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


_RAW_CARDS_PATH = Path("card_files/raw/cards.parquet")
_raw_faces_df: Optional[pd.DataFrame] = None


def _get_raw_faces_df() -> Optional[pd.DataFrame]:
    """Lazily load + cache a deduplicated (name, side) slice of the raw
    MTGJSON card data (one row per printing), used only to recover
    secondary-face details -- type, text, mana value, power/toughness --
    for split/adventure/transform/flip/etc. cards. The tagged dataset
    (`AllCardsLoader`) collapses multi-face cards down to a single
    primary-face row during tagging (see `multi_face_merger.py`), dropping
    everything but the back face's type (for MDFC land detection).
    """
    global _raw_faces_df
    if _raw_faces_df is None:
        if not _RAW_CARDS_PATH.exists():
            return None
        cols = [
            "name", "faceName", "side", "type", "text", "faceManaValue", "manaCost", "power", "toughness",
            "colorIdentity",
        ]
        try:
            df = pd.read_parquet(_RAW_CARDS_PATH, columns=cols)
        except Exception:
            return None
        df = df[df["side"].notna() & (df["side"].astype(str) != "")]
        df = df.drop_duplicates(subset=["name", "side"], keep="first")
        _raw_faces_df = df
    return _raw_faces_df


def _get_card_faces(name: str) -> List[Dict[str, Any]]:
    """Per-face details (type/text/mana value/power/toughness) for a
    multi-faced card, sorted front-to-back (side a, b, c...). Returns an
    empty list for single-faced cards or if the raw dataset is unavailable.
    """
    df = _get_raw_faces_df()
    if df is None:
        return []
    rows = df[df["name"] == name]
    if len(rows) < 2:
        return []
    rows = rows.sort_values("side")
    faces: List[Dict[str, Any]] = []
    for _, row in rows.iterrows():
        faces.append(
            {
                "name": _json_safe(row.get("faceName")) or _json_safe(row.get("name")),
                "side": _json_safe(row.get("side")),
                "type": _json_safe(row.get("type")) or None,
                "text": _json_safe(row.get("text")) or None,
                "manaValue": _json_safe(row.get("faceManaValue")),
                "manaCost": _json_safe(row.get("manaCost")) or None,
                "power": _json_safe(row.get("power")) or None,
                "toughness": _json_safe(row.get("toughness")) or None,
                "colorIdentity": _json_safe(row.get("colorIdentity")) or None,
            }
        )
    return faces


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _json_safe(value: Any) -> Any:
    """Convert NaN/Infinity floats (common for missing edhrecRank/manaValue
    values in the card data) to None -- Starlette's JSONResponse uses
    allow_nan=False, so leaving these in raises a 500 at render time."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


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
                "loyalty": card.get("loyalty"),
                "printings": card.get("printings"),
                "layout": card.get("layout"),
                "isNew": card.get("isNew"),
                "faces": _get_card_faces(str(card.get("name") or "")),
            }
        )
    data = {k: _json_safe(v) for k, v in data.items()}
    return jsonable_encoder(data)


@router.get("", summary="Search cards")
async def list_cards(
    request: Request,
    q: str = Query(
        "",
        description=(
            "Search box text. Plain words match the card name (default). "
            "Also supports real Scryfall search keywords (see "
            "https://scryfall.com/docs/syntax): c:/color:, id:/identity:, "
            "t:/type:, o:/oracle:, m:/mana:, mv:/cmc:/manavalue:, pow:/power:, "
            "tou:/toughness: -- each accepts :, =, >, <, >=, <=, or != and may be "
            "negated with a leading -. Note: bare `id:br` matches anything playable "
            "with a black/red identity (subset, incl. colorless), while `id=br` "
            "matches only exact black/red; bare `color:br` matches cards including "
            "at least black and red (superset), while `color=br` is exact-only. "
            "e.g. `c:rg t:creature o:\"draw a card\" pow>=4`"
        ),
    ),
    colors: str = Query("", description="Comma-separated colors, e.g. W,U -- cards whose color identity is a subset of these are matched; include C to also allow colorless"),
    tags: str = Query("", description="Comma-separated theme tags (AND logic)"),
    is_new: bool = Query(False, description="Only recently released cards"),
    min_cmc: Optional[float] = Query(None, ge=0),
    max_cmc: Optional[float] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Search/filter cards. Mirrors card_browser.py's filters, simplified for JSON I/O."""
    df = _get_loader().load()

    parsed = _parse_search_query(q) if q else ParsedSearch()

    df = _apply_name_clauses(df, parsed.name_include, parsed.name_exclude)
    df = _apply_text_clauses(df, "type", parsed.type_include, parsed.type_exclude)
    df = _apply_text_clauses(df, "text", parsed.oracle_include, parsed.oracle_exclude)

    # Colors (c:/color:) match the card's own mana cost colors; identity
    # (id:/identity:) matches its commander color identity -- two separate
    # columns/concepts.
    df = _apply_color_clauses(df, "colors", parsed.color_clauses)
    df = _apply_color_clauses(df, "colorIdentity", parsed.identity_clauses)

    df = _apply_numeric_clauses(df, "power", parsed.power_clauses)
    df = _apply_numeric_clauses(df, "toughness", parsed.toughness_clauses)
    df = _apply_numeric_clauses(df, "loyalty", parsed.loyalty_clauses)
    df = _apply_numeric_clauses(df, "manaValue", parsed.cmc_clauses)
    df = _apply_mana_cost_clauses(df, parsed.mana_cost_clauses)

    if parsed.rarity and "rarity" in df.columns:
        df = df[df["rarity"].str.lower().isin(parsed.rarity)]

    if "isNew" in df.columns:
        if parsed.is_new is True or is_new:
            df = df[df["isNew"] == True]  # noqa: E712
        elif parsed.is_new is False:
            df = df[df["isNew"] == False]  # noqa: E712

    # Colors -- the explicit `colors` param (used by the mobile app's chip
    # filter UI) is a simple subset-match against colorIdentity, separate
    # from the id:/identity: flag syntax parsed above.
    requested_colors = {c.strip().upper() for c in colors.split(",") if c.strip()}
    if requested_colors and "colorIdentity" in df.columns:
        allow_colorless = "C" in requested_colors
        color_letters = requested_colors - {"C"}

        def _matches_colors(raw: Any) -> bool:
            card_colors = _parse_color_cell(raw)
            if not card_colors:
                return allow_colorless
            return card_colors.issubset(color_letters)

        df = df[df["colorIdentity"].apply(_matches_colors)]

    # Theme tags -- combine the explicit `tags` param with any `tag=` flags
    # parsed out of `q`; AND logic (a card must have all requested tags).
    requested_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}
    if parsed.tags:
        requested_tags |= parsed.tags
    if requested_tags and "themeTags" in df.columns:
        # themeTags may be stored as a string, list, or numpy array depending on
        # source (raw CSV vs. Parquet) -- parse_theme_tags() normalizes all of them.
        card_tag_sets = df["themeTags"].apply(lambda v: {t.lower() for t in parse_theme_tags(v)})
        mask = card_tag_sets.apply(lambda card_tags: all(tag in card_tags for tag in requested_tags))
        df = df[mask]


    if min_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] >= min_cmc]
    if max_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] <= max_cmc]

    # Default sort: Name A-Z, matching the HTML card browser's default sort
    # (card_browser.py's "name_asc"), so results aren't left in arbitrary
    # data-file order.
    if "name" in df.columns and len(df):
        sort_key = df["name"].str.replace('"', "", regex=False).str.replace("'", "", regex=False)
        sort_key = sort_key.apply(lambda x: x.replace("_", " ") if isinstance(x, str) and x.startswith("_") else x)
        df = df.assign(_sort_key=sort_key).sort_values("_sort_key", key=lambda col: col.str.lower()).drop(columns="_sort_key")

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
    """Card detail: stats, tags, oracle text, scryfall_id.

    Falls back to a live Scryfall lookup when the card isn't in the local
    tagged dataset (e.g. basic lands, which are excluded from tagging).
    """
    row = _get_loader().get_by_name(name)
    if row is not None:
        return ok(_serialize_card(row, full=True), _rid(request))
    fallback = await _scryfall_card_fallback(name)
    if fallback is not None:
        return ok(fallback, _rid(request))
    return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
