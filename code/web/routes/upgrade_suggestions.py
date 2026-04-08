"""Route handlers for the Suggested Upgrades feature (M4).

Endpoints:
  GET /decks/upgrades?name=...&section=new|general&page=N
      Full page with new-card pool or general upgrade suggestions.

  GET /decks/upgrades/cards?name=...&section=new|general&page=N
      HTMX partial — card list + pagination only (replaces #upgrade-card-list).

  GET /decks/upgrades/swaps?name=...&card=...
      HTMX partial — lazy swap candidates for one suggestion card.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ..app import (
    ENABLE_UPGRADE_SUGGESTIONS,
    UPGRADE_PAGE_SIZE,
    templates,
)
from ..app import UPGRADE_WINDOW_MONTHS  # type: ignore[attr-defined]
from ..services.upgrade_suggestions_service import (
    DeckCard,
    UpgradeCandidate,
    UpgradeSuggestionsService,
    _DEFAULT_IDEAL_ROLE_TAGS,
)
from .decks import _deck_dir, _safe_within

router = APIRouter(prefix="/decks", tags=["upgrades"])

# Module-level service instance (stateless except for cached set metadata).
_svc: Optional[UpgradeSuggestionsService] = None


def _get_svc() -> UpgradeSuggestionsService:
    global _svc
    if _svc is None:
        _svc = UpgradeSuggestionsService(
            window_months=int(UPGRADE_WINDOW_MONTHS),
        )
    return _svc


# ---------------------------------------------------------------------------
# Deck loading helpers
# ---------------------------------------------------------------------------

def _load_deck(name: str) -> tuple[Path, dict, list[DeckCard], list[str], list[str]]:
    """Load a deck CSV and return (csv_path, meta, deck_cards, themes, color_identity).

    Parses the CSV directly to capture proper CMC values.  Skips the trailing
    "Total" summary row and any empty-name rows that may be present in exports.

    Raises HTTPException(404) when the file is not found or outside the deck dir.
    """
    import csv as _csv
    import json as _json

    deck_dir = _deck_dir()
    target = (deck_dir / name).resolve()
    if not _safe_within(deck_dir, target):
        raise HTTPException(status_code=404, detail="Deck not found")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Deck not found")

    # Infer commander from filename stem (pattern CommanderName_Themes_YYYYMMDD).
    stem_parts = target.stem.split("_")
    inferred_commander = stem_parts[0] if stem_parts else ""

    # Sidecar overrides filename inference when available.
    sidecar = target.with_suffix(".summary.json")
    sidecar_deck_themes: list[str] = []
    if sidecar.exists():
        try:
            payload = _json.loads(sidecar.read_text(encoding="utf-8"))
            _m = payload.get("meta", {}) if isinstance(payload, dict) else {}
            if _m.get("commander"):
                inferred_commander = _m["commander"]
            sidecar_deck_themes = list(_m.get("tags", []) or [])
        except Exception:
            pass

    commander_name = ""
    color_identity: list[str] = []
    deck_cards: list[DeckCard] = []
    all_themes: set[str] = set()

    try:
        with target.open("r", encoding="utf-8") as f:
            reader = _csv.reader(f)
            headers = next(reader, [])

            name_idx = headers.index("Name") if "Name" in headers else 0
            type_idx = headers.index("Type") if "Type" in headers else 2
            mv_idx = headers.index("ManaValue") if "ManaValue" in headers else (
                headers.index("Mana Value") if "Mana Value" in headers else -1
            )
            tags_idx = headers.index("Tags") if "Tags" in headers else -1
            colors_idx = headers.index("Colors") if "Colors" in headers else -1

            for row in reader:
                if not row:
                    continue
                card_name = row[name_idx].strip() if name_idx < len(row) else ""
                # Skip blank rows and the trailing "Total" summary row.
                if not card_name or card_name.lower() == "total":
                    continue

                type_line = (
                    row[type_idx].strip()
                    if type_idx >= 0 and type_idx < len(row)
                    else ""
                )

                # Detect commander: prefer filename-inferred name, fall back to
                # type-line heuristic.
                is_commander = bool(
                    inferred_commander and card_name == inferred_commander
                )
                if not is_commander:
                    is_commander = "commander" in type_line.lower()

                # Capture color identity from the commander row.
                if is_commander and not color_identity and colors_idx >= 0 and colors_idx < len(row):
                    cid = row[colors_idx] or ""
                    color_identity = list(cid)
                if not commander_name and is_commander:
                    commander_name = card_name

                # Parse proper CMC from ManaValue column.
                cmc = 0.0
                if mv_idx >= 0 and mv_idx < len(row):
                    try:
                        raw_mv = row[mv_idx].strip()
                        if raw_mv and raw_mv.lower() not in ("nan", ""):
                            cmc = float(raw_mv)
                    except (ValueError, AttributeError):
                        cmc = 0.0

                # Roles from the semicolon-separated Tags column.
                roles: list[str] = []
                if tags_idx >= 0 and tags_idx < len(row):
                    roles = [t.strip() for t in row[tags_idx].split(";") if t.strip()]
                for r in roles:
                    all_themes.add(r)

                deck_cards.append(
                    DeckCard(
                        name=card_name,
                        roles=roles,
                        cmc=cmc,
                        is_commander=is_commander,
                        is_locked=False,
                        card_type=type_line,  # full type line; enables land detection
                    )
                )
    except Exception:
        pass

    meta = {"commander": commander_name, "colors": color_identity, "deck_themes": sidecar_deck_themes}
    themes = sorted(all_themes)
    return target, meta, deck_cards, themes, color_identity


def _compute_role_counts(deck_cards: list[DeckCard]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in deck_cards:
        for role in card.roles:
            counts[role] = counts.get(role, 0) + 1
    return counts


def _compute_matched_tags(roles: list[str], deck_themes: list[str]) -> list[str]:
    """Return the subset of `roles` that are relevant to this deck.

    Mirrors the logic in ``get_new_card_pool`` so that the on-demand swap
    endpoint uses the same scoring basis as the pre-computed pool.
    """
    allowed = (
        {t.lower() for t in deck_themes}
        | {t.lower() for t in _DEFAULT_IDEAL_ROLE_TAGS}
    )
    return [t for t in roles if t.lower() in allowed]


def _paginate(items: list, page: int, per_page: int) -> tuple[list, int, int]:
    """Return (page_items, total_pages, clamped_page)."""
    total = len(items)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return items[start : start + per_page], total_pages, page


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _build_new_ctx(
    deck_cards: list[DeckCard],
    color_identity: list[str],
    page: int,
    per_page: int,
    deck_themes: Optional[list[str]] = None,
) -> dict[str, Any]:
    svc = _get_svc()
    window_codes, _cutoff, window_label = svc.resolve_new_card_window()
    # Require 2 matching tags when themes are known (any combo of deck themes
    # + utility roles); 1 when no themes are set.
    _overlap = 2 if deck_themes else 1
    deck_names = {c.name for c in deck_cards}
    pool = svc.get_new_card_pool(
        color_identity,
        deck_themes=deck_themes,
        min_tag_overlap=_overlap,
        deck_card_names=deck_names,
    )
    page_cards, total_pages, page = _paginate(pool, page, per_page)
    for card in page_cards:
        card.swap_candidates = svc.score_swap_candidates(card, deck_cards)
    return {
        "window_label": window_label,
        "cards": page_cards,
        "total_cards": len(pool),
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "section": "new",
        "tiers": {},
    }


def _build_general_ctx(
    deck_cards: list[DeckCard],
    color_identity: list[str],
    themes: list[str],
    page: int,
    per_page: int,
) -> dict[str, Any]:
    svc = _get_svc()
    deck_card_names = {c.name for c in deck_cards}
    role_counts = _compute_role_counts(deck_cards)
    tiers = svc.get_general_suggestions(
        deck_card_names=deck_card_names,
        color_identity=color_identity,
        themes=themes,
        role_counts=role_counts,
        max_per_tier=100,
    )
    # Flatten general tiers into one list for card display; tier info kept for headings
    flat: list[tuple[str, UpgradeCandidate]] = []
    for tier_label, tier_cards in tiers.items():
        for card in tier_cards:
            flat.append((tier_label, card))
    page_items, total_pages, page = _paginate(flat, page, per_page)
    page_cards = [item[1] for item in page_items]
    for card in page_cards:
        card.swap_candidates = svc.score_swap_candidates(card, deck_cards)
    return {
        "window_label": "",
        "cards": page_cards,
        "card_tiers": [item[0] for item in page_items],
        "total_cards": len(flat),
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "section": "general",
        "tiers": tiers,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/upgrades", response_class=HTMLResponse)
async def deck_upgrades(
    request: Request,
    name: str = Query(..., description="Deck CSV filename"),
    section: str = Query("new"),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    if not ENABLE_UPGRADE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Upgrade suggestions disabled")

    per_page = max(5, min(50, int(UPGRADE_PAGE_SIZE)))
    csv_path, meta, deck_cards, themes, color_identity = _load_deck(name)

    if section == "general":
        section_ctx = _build_general_ctx(deck_cards, color_identity, themes, page, per_page)
    else:
        section_ctx = _build_new_ctx(deck_cards, color_identity, page, per_page, deck_themes=meta.get("deck_themes"))
        section = "new"

    ctx = {
        "request": request,
        "name": name,
        "commander": meta.get("commander", ""),
        "color_identity": color_identity,
        "section": section,
        **section_ctx,
    }
    return templates.TemplateResponse("decks/upgrade_suggestions.html", ctx)


@router.get("/upgrades/cards", response_class=HTMLResponse)
async def deck_upgrades_cards(
    request: Request,
    name: str = Query(...),
    section: str = Query("new"),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    if not ENABLE_UPGRADE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Upgrade suggestions disabled")

    per_page = max(5, min(50, int(UPGRADE_PAGE_SIZE)))
    csv_path, meta, deck_cards, themes, color_identity = _load_deck(name)

    if section == "general":
        section_ctx = _build_general_ctx(deck_cards, color_identity, themes, page, per_page)
    else:
        section_ctx = _build_new_ctx(deck_cards, color_identity, page, per_page, deck_themes=meta.get("deck_themes"))
        section = "new"

    ctx = {
        "request": request,
        "name": name,
        "commander": meta.get("commander", ""),
        "color_identity": color_identity,
        "section": section,
        **section_ctx,
    }
    return templates.TemplateResponse("decks/_upgrade_cards_fragment.html", ctx)


@router.get("/upgrades/swaps", response_class=HTMLResponse)
async def deck_upgrades_swaps(
    request: Request,
    name: str = Query(...),
    card: str = Query(...),
) -> HTMLResponse:
    if not ENABLE_UPGRADE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Upgrade suggestions disabled")

    csv_path, meta, deck_cards, themes, color_identity = _load_deck(name)

    # Look up the card's roles from the parquet to build a proper UpgradeCandidate.
    roles: list[str] = []
    cmc = 3.0
    try:
        from code.path_util import get_processed_cards_path
        import os as _os
        from code.web.services.upgrade_suggestions_service import _str_val
        import pandas as _pd

        parquet_path = get_processed_cards_path()
        if _os.path.exists(parquet_path):
            from code.web.services.upgrade_suggestions_service import _parse_tags
            df = _pd.read_parquet(parquet_path, columns=["name", "faceName", "themeTags", "manaValue"])
            mask = df["name"].apply(lambda n: _str_val(n) == card)
            if "faceName" in df.columns:
                mask = mask | df["faceName"].apply(lambda n: _str_val(n) == card)
            row = df[mask].head(1)
            if not row.empty:
                r = row.iloc[0]
                roles = _parse_tags(r.get("themeTags", ""))
                cmc = float(r.get("manaValue") or 3.0)
    except Exception:
        pass

    suggestion = UpgradeCandidate(
        name=card,
        roles=roles,
        matched_tags=_compute_matched_tags(roles, meta.get("deck_themes", [])),
        cmc=cmc,
        set_code="",
        set_name="",
        released_at="",
        is_new_card=False,
    )

    svc = _get_svc()
    swap_cards = svc.score_swap_candidates(suggestion, deck_cards)

    ctx = {
        "request": request,
        "card": card,
        "swaps": swap_cards,
    }
    return templates.TemplateResponse("decks/_upgrade_swaps.html", ctx)
