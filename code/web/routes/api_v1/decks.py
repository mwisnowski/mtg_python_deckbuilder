"""Deck management endpoints for the public REST API (R28 Milestone 5).

Reuses the same per-user deck directory conventions and CSV-download helper
as the HTML web UI (`code/web/routes/decks.py`) instead of duplicating them.

Auth required for every endpoint here -- decks are always scoped to the
calling API user's own directory (`deck_files/{user_id}/`). There is no
guest/legacy/public browsing surface in the public API; that's a web-UI-only
concept for now (see roadmap_28_public_api.md's Milestone 5 note).
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

from code.type_definitions import User

from ...utils.api_response import err, ok
from ..decks import _build_csv_download_response, _deck_dir, _list_decks, _safe_within
from .auth import get_api_user

router = APIRouter(prefix="/decks", tags=["decks"])


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
                }
            )
    return cards


@router.get("", summary="List saved decks")
async def list_decks(request: Request, user: User = Depends(get_api_user)):
    """List the caller's saved decks."""
    decks = _list_decks(str(user["id"]))
    return ok(jsonable_encoder(decks), _rid(request))


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