"""Deck management endpoints for the public REST API (R28 Milestone 5).

Reuses the same per-user deck directory conventions and CSV-download helper
as the HTML web UI (`code/web/routes/decks.py`) instead of duplicating them.

Auth is required for most endpoints here -- decks are scoped to the calling
API user's own directory (`deck_files/{user_id}/`). The `/public` browsing
endpoints are the exception: they don't declare `get_api_user` and mirror
the HTML web UI's "Other Users' Decks" and "Community Builds" sections
(`code/web/routes/decks.py`'s `_index_sections`), so guests and connected-
but-signed-out callers can still see public/community decks.
"""
from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel

from code.services.all_cards_loader import AllCardsLoader
from code.deck_builder import builder_utils as bu
from code.type_definitions import User

from ...utils.api_response import err, ok
from ..decks import (
    _build_csv_download_response,
    _deck_dir,
    _list_decks,
    _list_guest_decks,
    _read_csv_summary,
    _safe_within,
    get_deck_visibility,
    list_public_decks,
)
from .auth import get_api_user, get_api_user_optional

router = APIRouter(prefix="/decks", tags=["decks"])

_loader: Optional[AllCardsLoader] = None


def _get_loader() -> AllCardsLoader:
    global _loader
    if _loader is None:
        _loader = AllCardsLoader()
    return _loader


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _resolve_deck_path(user_id: str, filename: str) -> Optional[Path]:
    base = _deck_dir(user_id)
    p = (base / filename).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return None
    return p


def _parse_deck_cards(csv_path: Path) -> List[Dict[str, Any]]:
    """Parse a deck CSV export into a flat card list for the API."""
    cards: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        idx = {h: i for i, h in enumerate(headers)}

        def col(row: List[str], key: str, default: str = "") -> str:
            i = idx.get(key)
            return row[i] if i is not None and i < len(row) else default

        for row in reader:
            if not row:
                continue
            name = col(row, "Name")
            if not name or name == "Total":
                continue
            tags = [t.strip() for t in col(row, "Tags").split(";") if t.strip()]
            try:
                count = int(float(col(row, "Count", "1") or 1))
            except ValueError:
                count = 1
            cards.append(
                {
                    "name": name,
                    "count": count,
                    "type": col(row, "Type"),
                    "mana_value": col(row, "ManaValue"),
                    "colors": col(row, "Colors"),
                    "role": col(row, "Role"),
                    "tags": tags,
                    "layout": None,
                    "scryfall_id": col(row, "ScryfallID") or None,
                }
            )

    # Double-faced card names contain " // " (e.g. "Akki Lavarunner //
    # Tok-Tok, Volcano Born"); look up each one's Scryfall layout so callers
    # can tell true DFCs (transform/modal_dfc, separate front/back images --
    # eligible for a "flip" control) apart from split/adventure/aftermath
    # cards (single combined image, same " // " name shape, no back face).
    dfc_names = {c["name"] for c in cards if " // " in c["name"]}
    if dfc_names:
        try:
            df = _get_loader().load()
            matches = df[df["name"].isin(dfc_names)][["name", "layout"]]
            layouts = dict(zip(matches["name"], matches["layout"]))
            for c in cards:
                if c["name"] in layouts:
                    c["layout"] = layouts[c["name"]]
        except Exception:
            pass
    return cards


def _set_deck_card_printing(csv_path: Path, name: str, scryfall_id: Optional[str]) -> bool:
    """Set (or clear, when `scryfall_id` is falsy) a saved deck's per-card
    `ScryfallID` column, baking a chosen alternate printing into the deck
    itself -- unlike the card browser, which always shows each card's
    default printing. Thin wrapper around the shared
    `builder_utils.set_card_printing_csv()` helper (also used by the web
    saved-deck view's own printing picker, so both clients stay in sync).
    """
    return bu.set_card_printing_csv(csv_path, name, scryfall_id)


@router.get("", summary="List saved decks")
async def list_decks(request: Request, user: User = Depends(get_api_user)):
    """List the caller's saved decks."""
    decks = _list_decks(str(user["id"]))
    return ok(jsonable_encoder(decks), _rid(request))


@router.get("/public", summary="Browse public and community decks")
async def list_public_and_guest_decks(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    user: Optional[User] = Depends(get_api_user_optional),
):
    """List other users' public decks plus shared guest/community builds.

    No auth required -- mirrors the HTML web UI's "Other Users' Decks" and
    "Community Builds" sections shown on `/decks` (see `_index_sections` in
    `code/web/routes/decks.py`), so it stays visible to guests/connected-
    but-signed-out API callers. If a valid Bearer token IS supplied, the
    caller's own public decks are excluded from the `public` list (they
    already see those under their own `/decks` listing).
    """
    exclude_user_id = user["id"] if user else ""
    public_items = [
        dict(item, section="public") for item in list_public_decks(exclude_user_id=exclude_user_id, limit=limit)
    ]
    guest_items = [dict(item, section="guest", user_id="guest") for item in _list_guest_decks()[:limit]]
    return ok(jsonable_encoder({"public": public_items, "guest": guest_items}), _rid(request))


def _resolve_public_deck_path(owner_id: str, filename: str) -> Optional[Path]:
    """Resolve a public/community deck's path, or None if not viewable.

    `owner_id` is either a real user id (must have a `public`/`unlisted`
    deck matching `filename`) or the literal `"guest"` (the shared community
    directory is always readable, matching `_list_guest_decks()`'s behavior).
    """
    if owner_id != "guest" and get_deck_visibility(owner_id, filename) not in ("public", "unlisted"):
        return None
    base = _deck_dir(owner_id)
    p = (base / filename).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return None
    return p


@router.get("/public/{owner_id}/{filename}", summary="Get a public or community deck's detail")
async def get_public_deck_detail(owner_id: str, filename: str, request: Request):
    """Deck detail for a deck from the `/public` listing above. No auth required."""
    p = _resolve_public_deck_path(owner_id, filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))
    cards = _parse_deck_cards(p)
    return ok(
        {"name": p.name, "cards": cards, "card_count": sum(c["count"] for c in cards)},
        _rid(request),
    )


@router.get("/public/{owner_id}/{filename}/export", summary="Export a public or community deck")
async def export_public_deck(
    owner_id: str,
    filename: str,
    request: Request,
    format: str = Query("csv", pattern="^(csv|txt|json)$"),
):
    """Download a deck export from the `/public` listing above. No auth required."""
    p = _resolve_public_deck_path(owner_id, filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))

    fmt = format.lower()
    if fmt == "csv":
        return _build_csv_download_response(p)
    if fmt == "txt":
        txt_p = p.with_suffix(".txt")
        if not txt_p.exists():
            return err("TXT export not available for this deck.", "EXPORT_NOT_FOUND", 404, _rid(request))
        return Response(
            content=txt_p.read_bytes(),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{txt_p.name}"'},
        )
    cards = _parse_deck_cards(p)
    payload = jsonable_encoder({"name": p.name, "cards": cards, "card_count": sum(c["count"] for c in cards)})
    return Response(
        content=json.dumps(payload, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{p.stem}.json"'},
    )


@router.get("/{filename}", summary="Get deck detail")
async def get_deck_detail(filename: str, request: Request, user: User = Depends(get_api_user)):
    """Deck detail: filename + parsed card list."""
    p = _resolve_deck_path(str(user["id"]), filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))
    cards = _parse_deck_cards(p)
    return ok(
        {"name": p.name, "cards": cards, "card_count": sum(c["count"] for c in cards)},
        _rid(request),
    )


class SetDeckPrintingRequest(BaseModel):
    name: str
    scryfall_id: Optional[str] = None


@router.post("/{filename}/printing", summary="Set a saved deck's card printing")
async def set_deck_card_printing(
    filename: str, body: SetDeckPrintingRequest, request: Request, user: User = Depends(get_api_user)
):
    """Choose (or clear, when `scryfall_id` is omitted/null) an alternate
    printing's artwork for a card already in a saved deck, baked directly
    into the deck's CSV `ScryfallID` column -- unlike the card browser,
    which always shows each card's default printing.
    """
    p = _resolve_deck_path(str(user["id"]), filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))
    found = _set_deck_card_printing(p, body.name, body.scryfall_id)
    if not found:
        return err(f"'{body.name}' is not in this deck.", "CARD_NOT_IN_DECK", 404, _rid(request))
    return ok({"name": body.name, "scryfall_id": (body.scryfall_id or None)}, _rid(request))


@router.get("/{filename}/analysis", summary="Get deck mana analysis")
async def get_deck_analysis(filename: str, request: Request, user: User = Depends(get_api_user)):
    """Commander, mana curve, pip distribution, mana sources, land summary
    (including MDFC lands), and total price.

    Reads the same `.summary.json` sidecar the HTML deck-view page uses
    (`_render_deck_view` in `code/web/routes/decks.py`) so this data matches
    what's shown there exactly, instead of recomputing it. Falls back to a
    CSV-only reconstruction (curve only; pips/sources/land summary default to
    empty/zero) for decks that predate/lack a sidecar, via the same
    `_read_csv_summary` helper the HTML route uses for that case.

    Total price is computed from the local price cache (`price_service`,
    already used by `/api/v1/prices/{card_name}`), not a live Scryfall call
    per card.
    """
    p = _resolve_deck_path(str(user["id"]), filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))

    summary: Optional[Dict[str, Any]] = None
    commander = ""
    sidecar = p.with_suffix(".summary.json")
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary = payload.get("summary")
                meta = payload.get("meta", {})
                if isinstance(meta, dict):
                    commander = meta.get("commander") or ""
        except Exception:
            summary = None

    if not summary:
        summary, _type_counts, _curve_counts, _type_cards = _read_csv_summary(p)

    if not commander:
        parts = p.stem.split("_")
        commander = parts[0] if parts else ""

    total_price: Optional[float] = None
    try:
        from ...services.price_service import get_price_service

        cards = _parse_deck_cards(p)
        names = [c["name"] for c in cards if c["name"] != commander]
        printing_map = {
            c["name"].lower(): c["scryfall_id"]
            for c in cards
            if c.get("scryfall_id") and c["name"] != commander
        }
        prices = get_price_service().get_prices_batch(names, printing_map=printing_map or None)
        found = [prices[name] * next(c["count"] for c in cards if c["name"] == name) for name in prices if prices[name] is not None]
        if found:
            total_price = round(sum(found), 2)
    except Exception:
        total_price = None

    return ok(
        jsonable_encoder(
            {
                "commander": commander,
                "colors": summary.get("colors", []) if summary else [],
                "mana_curve": (summary or {}).get("mana_curve", {}),
                "pip_distribution": (summary or {}).get("pip_distribution", {}),
                "mana_generation": (summary or {}).get("mana_generation", {}),
                "land_summary": (summary or {}).get("land_summary", {}),
                "total_price": total_price,
            }
        ),
        _rid(request),
    )


@router.get("/{filename}/export", summary="Export a deck")
async def export_deck(
    filename: str,
    request: Request,
    format: str = Query("csv", pattern="^(csv|txt|json)$"),
    user: User = Depends(get_api_user),
):
    """Download a deck export. `format` is one of csv (default), txt, json."""
    p = _resolve_deck_path(str(user["id"]), filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))

    fmt = format.lower()
    if fmt == "csv":
        return _build_csv_download_response(p)

    if fmt == "txt":
        txt_p = p.with_suffix(".txt")
        if not txt_p.exists():
            return err("TXT export not available for this deck.", "EXPORT_NOT_FOUND", 404, _rid(request))
        return Response(
            content=txt_p.read_bytes(),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{txt_p.name}"'},
        )

    # json
    cards = _parse_deck_cards(p)
    payload = jsonable_encoder(
        {"name": p.name, "cards": cards, "card_count": sum(c["count"] for c in cards)}
    )
    return Response(
        content=json.dumps(payload, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{p.stem}.json"'},
    )


@router.delete("/{filename}", summary="Delete a deck")
async def delete_deck(filename: str, request: Request, user: User = Depends(get_api_user)):
    """Delete a deck and its sidecars (CSV, TXT, summary/compliance JSON)."""
    p = _resolve_deck_path(str(user["id"]), filename)
    if p is None:
        return err("Deck not found.", "DECK_NOT_FOUND", 404, _rid(request))

    stem = p.stem
    for suffix in (".csv", ".txt", ".summary.json", "_compliance.json"):
        candidate = p.parent / (stem + suffix)
        try:
            if candidate.exists():
                candidate.unlink()
        except Exception:
            pass
    return ok({"deleted": True}, _rid(request))


@router.get("/{filename}/upgrades", summary="Get upgrade suggestions")
async def get_deck_upgrades(
    filename: str,
    request: Request,
    section: str = Query("general", pattern="^(new|general|possible)$"),
    page: int = Query(1, ge=1),
    user: User = Depends(get_api_user),
):
    """Upgrade suggestions for a saved deck (R28 Milestone 8).

    Reuses `upgrade_suggestions.py`'s deck loading + suggestion-building
    helpers -- the same ones backing the HTML "Suggested Upgrades" page --
    instead of duplicating the CSV-parsing/scoring logic.
    """
    from ...app import ENABLE_UPGRADE_SUGGESTIONS, UPGRADE_PAGE_SIZE
    from .. import upgrade_suggestions as upg

    if not ENABLE_UPGRADE_SUGGESTIONS:
        return err("Upgrade suggestions are disabled.", "FEATURE_DISABLED", 404, _rid(request))

    uid = str(user["id"])
    csv_path, meta, deck_cards, themes, color_identity = upg._load_deck(filename, uid)
    per_page = max(5, min(50, int(UPGRADE_PAGE_SIZE)))
    excluded_names = meta.get("excluded_names") or set()
    card_ceiling = meta.get("card_ceiling")

    if section == "general":
        section_ctx = upg._build_general_ctx(
            deck_cards, color_identity, themes, page, per_page,
            excluded_names=excluded_names, card_ceiling=card_ceiling,
        )
    elif section == "possible":
        section_ctx = upg._build_possible_ctx(
            deck_cards, color_identity, themes, page, per_page,
            excluded_names=excluded_names, card_ceiling=card_ceiling,
        )
    else:
        section_ctx = upg._build_new_ctx(
            deck_cards, color_identity, page, per_page,
            deck_themes=meta.get("deck_themes"), excluded_names=excluded_names,
            card_ceiling=card_ceiling,
        )

    return ok(
        jsonable_encoder(
            {
                "commander": meta.get("commander", ""),
                "color_identity": color_identity,
                **section_ctx,
            }
        ),
        _rid(request),
    )