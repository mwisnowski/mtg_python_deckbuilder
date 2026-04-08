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

from fastapi import APIRouter, Form, HTTPException, Query, Request
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
            # Include/exclude lists and budget ceiling
            _summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
            _ie = _summary.get("include_exclude_summary", {}) if isinstance(_summary, dict) else {}
            include_names_lower = {n.lower() for n in (_ie.get("include_cards") or [])}
            excluded_names = {n.lower() for n in (_ie.get("exclude_cards") or [])}
            _bc = _m.get("budget_config", {}) or {}
            if _bc.get("card_ceiling"):
                _ceiling = float(_bc["card_ceiling"])
                _tolerance = float(_bc.get("pool_tolerance") or 0.0)
                card_ceiling = _ceiling * (1.0 + _tolerance)
        except Exception:
            pass

    commander_name = ""
    color_identity: list[str] = []
    deck_cards: list[DeckCard] = []
    all_themes: set[str] = set()
    include_names_lower: set[str] = set()
    excluded_names: set[str] = set()
    card_ceiling: Optional[float] = None

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
            dfc_note_idx = headers.index("DFCNote") if "DFCNote" in headers else -1

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

                # Detect DFC from DFCNote column (populated by builder for any
                # double-faced or modal DFC card) or the "//" separator in the name.
                is_dfc = " // " in card_name
                if not is_dfc and dfc_note_idx >= 0 and dfc_note_idx < len(row):
                    is_dfc = bool(row[dfc_note_idx].strip())

                deck_cards.append(
                    DeckCard(
                        name=card_name,
                        roles=roles,
                        cmc=cmc,
                        is_commander=is_commander,
                        is_locked=card_name.lower() in include_names_lower,
                        card_type=type_line,
                        is_dfc=is_dfc,
                    )
                )
    except Exception:
        pass

    meta = {"commander": commander_name, "colors": color_identity, "deck_themes": sidecar_deck_themes, "excluded_names": excluded_names, "card_ceiling": card_ceiling}
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


def _normalize_fit_scores(cards: list[UpgradeCandidate]) -> None:
    """Normalize fit_score in-place to a 1\u201310 scale across the full candidate list.

    Applied to the complete pool before pagination so scores are stable
    across pages and consistently comparable between sections.
    """
    if not cards:
        return
    scores = [c.fit_score for c in cards]
    lo, hi = min(scores), max(scores)
    if hi <= lo:
        for c in cards:
            c.fit_score = 5.0
        return
    for c in cards:
        c.fit_score = round(1.0 + 9.0 * (c.fit_score - lo) / (hi - lo), 1)


def _enrich_prices(page_cards: list[UpgradeCandidate]) -> None:
    """Batch-fetch TCGPlayer prices and populate .price on cards and swap candidates."""
    try:
        from code.web.services.price_service import get_price_service
        all_names: list[str] = []
        for card in page_cards:
            all_names.append(card.name)
            for swap in card.swap_candidates:
                all_names.append(swap.name)
        prices = get_price_service().get_prices_batch(all_names)
        for card in page_cards:
            card.price = prices.get(card.name)
            for swap in card.swap_candidates:
                swap.price = prices.get(swap.name)
    except Exception:
        pass


# Price ratio band applied to recommendations priced ≥ _CHEAP_THRESHOLD.
# e.g. _MAX_PRICE_RATIO=2.0 → a $22 rec won't replace a $10 card.
#      _MIN_PRICE_RATIO=0.5 → a $6 rec won't replace a $20 card.
_MAX_PRICE_RATIO = 2.0
_MIN_PRICE_RATIO = 0.5
# Cards below this threshold use a flat "same price range" rule instead of
# the ratio band: both the recommendation AND its swap target must be < $2.
# This prevents a $0.10 recommendation from pairing against a $20 cut.
_CHEAP_THRESHOLD = 2.0


def _filter_swap_candidates_by_price(
    page_cards: list[UpgradeCandidate],
    card_ceiling: Optional[float],
) -> None:
    """Filter swap candidates by price reasonableness.

    Two-tier logic based on the recommendation's price:

    - rec < $2 ("cheap range"): swap target must also be < $2.
      Prevents dirt-cheap suggestions from pairing against expensive cuts
      while still allowing any cheap-to-cheap swap.

    - rec ≥ $2: swap target must fall within 50%–200% of the rec price
      (e.g. a $5 rec pairs with targets priced $2.50–$10).

    Additionally:
    - If the rec exceeds the deck's card ceiling, all swaps are stripped
      (tile still renders for reference).
    - Swap candidates with no price data always pass through.
    """
    for card in page_cards:
        if not card.swap_candidates:
            continue
        add_price = card.price

        # Above ceiling → strip all swaps for this tile
        if add_price is not None and card_ceiling and add_price > card_ceiling:
            card.swap_candidates = []
            continue

        # No price data → can't filter, keep all swaps
        if add_price is None:
            continue

        filtered = []
        for swap in card.swap_candidates:
            remove_price = swap.price
            if remove_price is None:
                # No price on the cut card → always allow
                filtered.append(swap)
                continue

            if add_price < _CHEAP_THRESHOLD:
                # Cheap rec: target must also be cheap
                if remove_price >= _CHEAP_THRESHOLD:
                    continue
            else:
                # Pricier rec: apply 50%–200% ratio band
                if remove_price > 0:
                    ratio = add_price / remove_price
                    if ratio > _MAX_PRICE_RATIO or ratio < _MIN_PRICE_RATIO:
                        continue

            filtered.append(swap)
        card.swap_candidates = filtered


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _build_new_ctx(
    deck_cards: list[DeckCard],
    color_identity: list[str],
    page: int,
    per_page: int,
    deck_themes: Optional[list[str]] = None,
    excluded_names: set[str] = frozenset(),
    card_ceiling: Optional[float] = None,
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
    if excluded_names:
        pool = [c for c in pool if c.name.lower() not in excluded_names]
    _normalize_fit_scores(pool)
    # Score + price the full pool before paginating so the viable subset is
    # known and pages always contain exactly per_page cards.
    for card in pool:
        card.swap_candidates = svc.score_swap_candidates(card, deck_cards)
    _enrich_prices(pool)
    _filter_swap_candidates_by_price(pool, card_ceiling)
    viable = [c for c in pool if len(c.swap_candidates) >= 2]
    page_cards, total_pages, page = _paginate(viable, page, per_page)
    return {
        "window_label": window_label,
        "cards": page_cards,
        "possible_cards": [],
        "total_cards": len(viable),
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
    excluded_names: set[str] = frozenset(),
    card_ceiling: Optional[float] = None,
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
    flat: list[tuple[str, UpgradeCandidate]] = []
    for tier_label, tier_cards in tiers.items():
        for card in tier_cards:
            if not excluded_names or card.name.lower() not in excluded_names:
                flat.append((tier_label, card))
    _normalize_fit_scores([item[1] for item in flat])
    # Score + price the full flat list before paginating so the viable subset
    # is known and pages always contain exactly per_page cards.
    all_cards = [item[1] for item in flat]
    all_tiers = [item[0] for item in flat]
    for card in all_cards:
        card.swap_candidates = svc.score_swap_candidates(card, deck_cards)
    _enrich_prices(all_cards)
    _filter_swap_candidates_by_price(all_cards, card_ceiling)
    viable_pairs = [(t, c) for t, c in zip(all_tiers, all_cards) if len(c.swap_candidates) >= 2]
    page_items, total_pages, page = _paginate(viable_pairs, page, per_page)
    return {
        "window_label": "",
        "cards": [c for _, c in page_items],
        "card_tiers": [t for t, _ in page_items],
        "possible_cards": [],
        "total_cards": len(viable_pairs),
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "section": "general",
        "tiers": tiers,
    }


def _build_possible_ctx(
    deck_cards: list[DeckCard],
    color_identity: list[str],
    themes: list[str],
    page: int,
    per_page: int,
    excluded_names: set[str] = frozenset(),
    card_ceiling: Optional[float] = None,
) -> dict[str, Any]:
    """Same pool as general upgrades, but shows cards with <2 viable swap targets.

    Scores swaps and enriches prices for the full pool first so the possible
    subset is accurately filtered before pagination.
    """
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
    all_candidates: list[UpgradeCandidate] = [
        card
        for tier_cards in tiers.values()
        for card in tier_cards
        if not excluded_names or card.name.lower() not in excluded_names
    ]
    _normalize_fit_scores(all_candidates)
    # Score swaps + prices for the full list so filtering is based on real data
    for card in all_candidates:
        card.swap_candidates = svc.score_swap_candidates(card, deck_cards)
    _enrich_prices(all_candidates)
    _filter_swap_candidates_by_price(all_candidates, card_ceiling)
    possible = [c for c in all_candidates if len(c.swap_candidates) < 2]
    page_cards, total_pages, page = _paginate(possible, page, per_page)
    return {
        "window_label": "",
        "cards": page_cards,
        "card_tiers": [],
        "possible_cards": [],
        "total_cards": len(possible),
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "section": "possible",
        "tiers": {},
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
    excluded_names: set[str] = meta.get("excluded_names") or set()
    card_ceiling: Optional[float] = meta.get("card_ceiling")

    if section == "general":
        section_ctx = _build_general_ctx(deck_cards, color_identity, themes, page, per_page, excluded_names=excluded_names, card_ceiling=card_ceiling)
    elif section == "possible":
        section_ctx = _build_possible_ctx(deck_cards, color_identity, themes, page, per_page, excluded_names=excluded_names, card_ceiling=card_ceiling)
    else:
        section_ctx = _build_new_ctx(deck_cards, color_identity, page, per_page, deck_themes=meta.get("deck_themes"), excluded_names=excluded_names, card_ceiling=card_ceiling)
        section = "new"

    ctx = {
        "request": request,
        "name": name,
        "commander": meta.get("commander", ""),
        "color_identity": color_identity,
        "section": section,
        "card_ceiling": card_ceiling,
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
    excluded_names: set[str] = meta.get("excluded_names") or set()
    card_ceiling: Optional[float] = meta.get("card_ceiling")

    if section == "general":
        section_ctx = _build_general_ctx(deck_cards, color_identity, themes, page, per_page, excluded_names=excluded_names, card_ceiling=card_ceiling)
    elif section == "possible":
        section_ctx = _build_possible_ctx(deck_cards, color_identity, themes, page, per_page, excluded_names=excluded_names, card_ceiling=card_ceiling)
    else:
        section_ctx = _build_new_ctx(deck_cards, color_identity, page, per_page, deck_themes=meta.get("deck_themes"), excluded_names=excluded_names, card_ceiling=card_ceiling)
        section = "new"

    ctx = {
        "request": request,
        "name": name,
        "commander": meta.get("commander", ""),
        "color_identity": color_identity,
        "section": section,
        "card_ceiling": card_ceiling,
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


# ---------------------------------------------------------------------------
# M6: Apply swap helpers
# ---------------------------------------------------------------------------

def _look_up_card_meta(add_name: str) -> dict:
    """Look up card metadata from all_cards.parquet for building a CSV row.

    Returns a dict with keys: type, mana_value, power, toughness, tags, is_new,
    color_identity.  Falls back to safe empty/zero defaults on any failure.
    """
    result: dict = {
        "type": "",
        "mana_value": "",
        "power": "",
        "toughness": "",
        "tags": "",
        "is_new": False,
        "color_identity": "",
    }
    try:
        import os as _os
        import pandas as _pd
        from code.path_util import get_processed_cards_path
        from code.web.services.upgrade_suggestions_service import _str_val, _parse_tags

        parquet_path = get_processed_cards_path()
        if not _os.path.exists(parquet_path):
            return result

        wanted = ["name", "faceName", "type", "manaValue", "power", "toughness",
                  "themeTags", "isNew", "colorIdentity"]
        # Discover available columns via schema (cheap — no data read).
        import pyarrow.parquet as _pq
        _schema_cols = set(_pq.read_schema(parquet_path).names)
        available = [c for c in wanted if c in _schema_cols]
        df = _pd.read_parquet(parquet_path, columns=available)
        name_lower = add_name.lower()
        mask = df["name"].apply(lambda n: _str_val(n).lower() == name_lower)
        if "faceName" in df.columns:
            mask = mask | df["faceName"].apply(lambda n: _str_val(n).lower() == name_lower)
        row = df[mask].head(1)
        if row.empty:
            return result
        r = row.iloc[0]
        type_line = str(r.get("type") or "")
        tags_list = _parse_tags(r.get("themeTags", ""))
        result["type"] = type_line
        result["mana_value"] = str(r.get("manaValue") or "")
        result["power"] = str(r.get("power") or "")
        result["toughness"] = str(r.get("toughness") or "")
        result["tags"] = ";".join(tags_list)
        result["is_new"] = bool(r.get("isNew") or False)
        cid_raw = r.get("colorIdentity") or ""
        if isinstance(cid_raw, (list, tuple)):
            result["color_identity"] = "".join(str(c) for c in cid_raw)
        else:
            result["color_identity"] = str(cid_raw)
    except Exception:
        pass
    return result


def _derive_role(type_line: str) -> str:
    tl = type_line.lower()
    if "land" in tl:
        return "land"
    if "creature" in tl:
        return "creature"
    return "spell"


def _apply_csv_swap(
    csv_path: Path, remove_name: str, add_name: str, add_meta: dict
) -> tuple[str, Optional[str]]:
    """Remove remove_name row and insert add_name row in the deck CSV.

    Creates a .bak backup before writing.  Returns ("ok", None) on success
    or ("error", reason) on failure.  Does not raise exceptions.
    """
    import csv as _csv
    import shutil as _shutil

    try:
        rows: list[list[str]] = []
        headers: list[str] = []
        found = False
        old_row: list[str] = []

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = _csv.reader(f)
            headers = next(reader, [])
            for row in reader:
                rows.append(row)

        name_idx = headers.index("Name") if "Name" in headers else 0
        count_idx = headers.index("Count") if "Count" in headers else 1
        type_idx = headers.index("Type") if "Type" in headers else 2
        mv_idx = next((i for i, h in enumerate(headers) if h in ("ManaValue", "Mana Value")), -1)
        power_idx = headers.index("Power") if "Power" in headers else -1
        tough_idx = headers.index("Toughness") if "Toughness" in headers else -1
        role_idx = headers.index("Role") if "Role" in headers else -1
        sub_role_idx = headers.index("SubRole") if "SubRole" in headers else -1
        added_by_idx = headers.index("AddedBy") if "AddedBy" in headers else -1
        trigger_idx = headers.index("TriggerTag") if "TriggerTag" in headers else -1
        synergy_idx = headers.index("Synergy") if "Synergy" in headers else -1
        tags_idx = headers.index("Tags") if "Tags" in headers else -1
        meta_tags_idx = headers.index("MetadataTags") if "MetadataTags" in headers else -1
        text_idx = headers.index("Text") if "Text" in headers else -1
        dfc_idx = headers.index("DFCNote") if "DFCNote" in headers else -1
        price_idx = next((i for i, h in enumerate(headers) if "Price" in h), -1)
        colors_idx = headers.index("Colors") if "Colors" in headers else -1

        new_rows: list[list[str]] = []
        for row in rows:
            if not row:
                new_rows.append(row)
                continue
            cell_name = row[name_idx].strip() if name_idx < len(row) else ""
            if cell_name.lower() == remove_name.lower() and not found:
                found = True
                old_row = row[:]
                # Build replacement row: start from old row (preserves Count, Owned, etc.),
                # overwrite card-specific columns with new card data.
                new = row[:]
                new[name_idx] = add_name
                if type_idx >= 0 and type_idx < len(new):
                    new[type_idx] = add_meta.get("type", "")
                if mv_idx >= 0 and mv_idx < len(new):
                    new[mv_idx] = add_meta.get("mana_value", "")
                if power_idx >= 0 and power_idx < len(new):
                    new[power_idx] = add_meta.get("power", "")
                if tough_idx >= 0 and tough_idx < len(new):
                    new[tough_idx] = add_meta.get("toughness", "")
                if role_idx >= 0 and role_idx < len(new):
                    new[role_idx] = _derive_role(add_meta.get("type", ""))
                if sub_role_idx >= 0 and sub_role_idx < len(new):
                    new[sub_role_idx] = ""
                if added_by_idx >= 0 and added_by_idx < len(new):
                    new[added_by_idx] = ""
                if trigger_idx >= 0 and trigger_idx < len(new):
                    new[trigger_idx] = ""
                if synergy_idx >= 0 and synergy_idx < len(new):
                    new[synergy_idx] = ""
                if tags_idx >= 0 and tags_idx < len(new):
                    new[tags_idx] = add_meta.get("tags", "")
                if meta_tags_idx >= 0 and meta_tags_idx < len(new):
                    new[meta_tags_idx] = ""
                if text_idx >= 0 and text_idx < len(new):
                    new[text_idx] = ""
                if dfc_idx >= 0 and dfc_idx < len(new):
                    new[dfc_idx] = ""
                if colors_idx >= 0 and colors_idx < len(new):
                    new[colors_idx] = add_meta.get("color_identity", "")
                if price_idx >= 0 and price_idx < len(new):
                    new[price_idx] = ""
                new_rows.append(new)
            else:
                new_rows.append(row)

        if not found:
            return ("error", f"Card \"{ remove_name}\" not found in deck")

        # Sort: commander rows first (Role == "commander"), then type precedence, then alpha.
        # Mirrors the sort order of the original deck export.
        def _row_sort_key(r: list) -> tuple:
            if not r:
                return (999, "")
            raw_role = (r[role_idx].lower().strip() if role_idx >= 0 and role_idx < len(r) else "")
            if raw_role == "commander":
                prec = 0
            else:
                tl = (r[type_idx].lower() if type_idx >= 0 and type_idx < len(r) else "")
                if "battle" in tl:         prec = 1
                elif "planeswalker" in tl: prec = 2
                elif "creature" in tl:     prec = 3
                elif "instant" in tl:      prec = 4
                elif "sorcery" in tl:      prec = 5
                elif "artifact" in tl:     prec = 6
                elif "enchantment" in tl:  prec = 7
                elif "land" in tl:         prec = 8
                else:                       prec = 9
            nm = (r[name_idx].lower() if name_idx >= 0 and name_idx < len(r) else "")
            return (prec, nm)
        new_rows = [r for r in new_rows if r]  # drop any blank rows
        new_rows.sort(key=_row_sort_key)

        # Backup then write.
        bak_path = csv_path.with_suffix(".csv.bak")
        _shutil.copy2(csv_path, bak_path)

        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = _csv.writer(f)
            writer.writerow(headers)
            writer.writerows(new_rows)

        old_count = 1
        if old_row and count_idx < len(old_row):
            try:
                old_count = int(float(old_row[count_idx]))
            except (ValueError, TypeError):
                old_count = 1
        return ("ok", None)

    except Exception as exc:
        return ("error", f"Failed to write deck: {exc}")


def _update_txt(txt_path: Path, remove_name: str, add_name: str) -> None:
    """Replace the '1 {remove_name}' line with '1 {add_name}' in the txt export."""
    if not txt_path.exists():
        return
    try:
        lines = txt_path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated: list[str] = []
        replaced = False
        for line in lines:
            stripped = line.rstrip("\n\r")
            # Match exactly "1 {remove_name}" (DFC cards use the full combined name)
            if not replaced and stripped == f"1 {remove_name}":
                updated.append(f"1 {add_name}\n")
                replaced = True
            else:
                updated.append(line)
        txt_path.write_text("".join(updated), encoding="utf-8")
    except Exception:
        pass


def _patch_summary_json(
    summary_path: Path, remove_name: str, add_name: str, add_meta: dict, old_count: int
) -> None:
    """Targeted patch of .summary.json: swap card entry in type_breakdown."""
    if not summary_path.exists():
        return
    try:
        import json as _json

        payload: dict = _json.loads(summary_path.read_text(encoding="utf-8"))
        summary = payload.get("summary") or {}
        tb: dict = (summary.get("type_breakdown") or {})
        cards: dict = (tb.get("cards") or {})
        counts: dict = (tb.get("counts") or {})

        # Find and remove old card from its type bucket.
        old_type_cat: str = ""
        for cat, clist in cards.items():
            before_len = len(clist)
            cards[cat] = [c for c in clist if str(c.get("name", "")).lower() != remove_name.lower()]
            if len(cards[cat]) < before_len:
                old_type_cat = cat
                break

        # Determine new card's type category.
        type_line = add_meta.get("type", "")
        tl = type_line.lower()
        if "battle" in tl:
            new_cat = "Battle"
        elif "planeswalker" in tl:
            new_cat = "Planeswalker"
        elif "creature" in tl:
            new_cat = "Creature"
        elif "instant" in tl:
            new_cat = "Instant"
        elif "sorcery" in tl:
            new_cat = "Sorcery"
        elif "artifact" in tl:
            new_cat = "Artifact"
        elif "enchantment" in tl:
            new_cat = "Enchantment"
        elif "land" in tl:
            new_cat = "Land"
        else:
            new_cat = "Other"

        # Build new card entry.
        tags_raw = add_meta.get("tags", "")
        tags_list = [t.strip() for t in tags_raw.split(";") if t.strip()]
        new_entry = {
            "name": add_name,
            "count": old_count,
            "role": _derive_role(type_line),
            "tags": tags_list,
            "isNew": bool(add_meta.get("is_new", False)),
        }
        cards.setdefault(new_cat, []).append(new_entry)

        # Update counts.
        if old_type_cat and old_type_cat in counts:
            counts[old_type_cat] = max(0, counts[old_type_cat] - old_count)
        if new_cat in counts:
            counts[new_cat] += old_count
        else:
            counts[new_cat] = old_count

        # Sort cards alphabetically within each type bucket.
        for cat in cards:
            cards[cat].sort(key=lambda c: c.get("name", "").lower())

        # Persist.
        tb["cards"] = cards
        tb["counts"] = counts
        summary["type_breakdown"] = tb
        payload["summary"] = summary
        summary_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _remove_compliance(csv_path: Path) -> None:
    """Delete the compliance JSON sidecar — it is stale after a card swap."""
    compliance = csv_path.parent / f"{csv_path.stem}_compliance.json"
    try:
        if compliance.exists():
            compliance.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# M6: Apply-swap route
# ---------------------------------------------------------------------------

@router.post("/upgrades/apply-swap", response_class=HTMLResponse)
async def deck_upgrades_apply_swap(
    request: Request,
    name: str = Form(...),
    remove: str = Form(...),
    add: str = Form(...),
) -> HTMLResponse:
    """Apply a card swap: remove `remove` from the deck and insert `add`.

    Returns a small HTMX fragment replacing the swap-item row:
    - Success: a green "Swapped" confirmation chip
    - Failure: a red inline error message
    """
    if not ENABLE_UPGRADE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Upgrade suggestions disabled")

    # --- Resolve and validate deck path ---
    deck_dir = _deck_dir()
    csv_path = (deck_dir / name).resolve()
    if not _safe_within(deck_dir, csv_path):
        raise HTTPException(status_code=403, detail="Invalid deck path")
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="Deck not found")

    # --- Load deck to validate remove/add ---
    _, meta, deck_cards, _, _ = _load_deck(name)

    deck_names_lower = {c.name.lower() for c in deck_cards}
    commanders_lower = {c.name.lower() for c in deck_cards if c.is_commander}

    if remove.lower() not in deck_names_lower:
        return HTMLResponse(
            f'<span class="upgrade-swap-error">Card not found in deck.</span>'
        )
    if remove.lower() in commanders_lower:
        return HTMLResponse(
            f'<span class="upgrade-swap-error">Cannot remove the commander.</span>'
        )
    if add.lower() in deck_names_lower:
        return HTMLResponse(
            f'<span class="upgrade-swap-error">\u201c{add}\u201d is already in the deck.</span>'
        )

    # --- Look up new card metadata ---
    add_meta = _look_up_card_meta(add)

    # --- Determine old card count (for summary patch) ---
    old_count = 1
    for dc in deck_cards:
        if dc.name.lower() == remove.lower():
            break  # count always 1 in this deck format; preserved from CSV in _apply_csv_swap

    # --- Apply CSV swap ---
    status, reason = _apply_csv_swap(csv_path, remove, add, add_meta)
    if status == "error":
        return HTMLResponse(
            f'<span class="upgrade-swap-error">{reason}</span>'
        )

    # --- Update sidecar files ---
    _update_txt(csv_path.with_suffix(".txt"), remove, add)
    _patch_summary_json(csv_path.with_suffix(".summary.json"), remove, add, add_meta, old_count)
    _remove_compliance(csv_path)

    import json as _json
    remove_js = _json.dumps(remove)          # safely quoted for inline JS (handles apostrophes in names)
    add_js = _json.dumps(add)
    rem_sel = f".upgrade-swap-item[data-card-name={remove_js}]"
    add_sel = f".card-browser-tile[data-card-name={add_js}]"
    html = (
        f'<span class="upgrade-swap-applied" title="{remove} removed, {add} added">Swapped \u2713</span>'
        f"<script>(function(){{"
        # Find the specific chosen tile — the one that now has the .upgrade-swap-applied chip
        f"var chosenTile=null;"
        f"document.querySelectorAll('{rem_sel}').forEach(function(el){{"
        f"if(!chosenTile&&el.querySelector('.upgrade-swap-applied')){{chosenTile=el;}}"
        f"}});"
        f"if(chosenTile){{chosenTile.classList.add('upgrade-swap-chosen');}}"
        # Dim all other tiles for the same removed card
        f"document.querySelectorAll('{rem_sel}').forEach(function(el){{"
        f"if(el!==chosenTile){{el.classList.add('upgrade-swap-stale');}}"
        f"}});"
        # Dim the upgrade card tile so its remaining swap buttons can't be clicked
        f"document.querySelectorAll('{add_sel}').forEach(function(el){{el.classList.add('upgrade-swap-stale');}});"
        # Show the stale-page banner
        f"var b=document.getElementById('upgrade-stale-banner');"
        f"if(b){{b.style.display='';}}"
        f"}})();</script>"
    )
    return HTMLResponse(html)
