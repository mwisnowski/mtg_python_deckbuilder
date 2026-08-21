"""
Card browser web UI routes (HTML views with HTMX).

Provides paginated card browsing with filters, search, and cursor-based pagination.
Complements the existing API routes in cards.py for tag-based card queries.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import pandas as pd
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from ..app import templates
from ..services.tasks import get_session, new_sid

# Import existing services
try:
    from code.services.all_cards_loader import AllCardsLoader
    from code.deck_builder.builder_utils import parse_theme_tags
    from code.deck_builder.color_identity_utils import color_identity_badges
    from code.settings import ENABLE_CARD_DETAILS
    from code.web.routes.api_v1.cards import _get_card_faces
    from code.web.routes.api import _image_cache
    from code.web.services.card_search import (
        apply_extra_clauses,
        apply_name_clauses,
        apply_parsed_search,
        has_structured_flags,
        parse_search_query,
        resolve_collector_number_printings,
        get_set_collector_number_sort_map,
    )
except ImportError:
    from services.all_cards_loader import AllCardsLoader
    from deck_builder.builder_utils import parse_theme_tags
    from deck_builder.color_identity_utils import color_identity_badges
    from settings import ENABLE_CARD_DETAILS
    from web.routes.api_v1.cards import _get_card_faces
    from web.routes.api import _image_cache
    from web.services.card_search import (
        apply_extra_clauses,
        apply_name_clauses,
        apply_parsed_search,
        has_structured_flags,
        parse_search_query,
        resolve_collector_number_printings,
        get_set_collector_number_sort_map,
    )

if TYPE_CHECKING:
    from code.web.services.card_similarity import CardSimilarity
    from code.web.services.card_search import ParsedSearch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["card-browser"])

# Cached loader instance and theme index
_loader: AllCardsLoader | None = None
_theme_index: dict[str, set[int]] | None = None  # theme_lower -> set of card indices
_theme_catalog: list[str] | None = None  # cached list of all theme names from catalog
_similarity: "CardSimilarity | None" = None  # cached CardSimilarity instance


def get_loader() -> AllCardsLoader:
    """Get cached AllCardsLoader instance."""
    global _loader
    if _loader is None:
        _loader = AllCardsLoader()
    return _loader


def _printings_context(request: Request) -> tuple[dict[str, str], str, bool]:
    """Return (selected-printings dict, sid, had_cookie) for the printing picker.

    Session-scoped and shared with the build wizard's `sess["printings"]`
    (see `code/web/routes/build_permalinks.py`); the card browser only reads
    it here, callers must set the `sid` cookie on the response if `had_cookie`
    is False so a picker selection persists.
    """
    had_cookie = bool(request.cookies.get("sid"))
    sid = request.cookies.get("sid") or new_sid()
    return dict(get_session(sid).get("printings") or {}), sid, had_cookie


def _foils_context(request: Request, sid: str | None = None) -> dict[str, bool]:
    """Return the selected-foils dict for the foil toggle button.

    Session-scoped and shared with the build wizard's `sess["foils"]`
    (see `code/web/routes/build_permalinks.py`); mirrors `_printings_context`.
    Pass the `sid` already resolved by `_printings_context` to avoid
    generating a second, unused session id on a cookie-less first request.
    """
    sid = sid or request.cookies.get("sid") or new_sid()
    return dict(get_session(sid).get("foils") or {})


def _set_scoped_printings(
    cards_list: list[dict],
    parsed: "ParsedSearch | None",
    base_printings: dict[str, str],
) -> dict[str, str]:
    """Build a set-scoped printing overlay for the current search's results.

    For each card not already present in `base_printings` (a manual "Choose
    Printing" pick always wins), tries each code in `parsed.set_include` in
    sorted order, using the first set that has a match. Cards with a match
    in more than one searched set get a `parsed.notices` entry noting
    alternates are available. Returns `{}` unchanged if there's no `set:`
    filter to scope to.
    """
    overlay: dict[str, str] = {}
    if not parsed or not parsed.set_include:
        return overlay

    set_codes = sorted(parsed.set_include)
    alt_available: list[str] = []
    for card in cards_list:
        name = card.get("name")
        if not name:
            continue
        key = name.lower()
        if key in base_printings:
            continue
        matched_sets = []
        for code in set_codes:
            scryfall_id = _image_cache.get_printing_id_for_set(name, code)
            if scryfall_id:
                matched_sets.append((code, scryfall_id))
        if matched_sets:
            overlay[key] = matched_sets[0][1]
            if len(matched_sets) > 1:
                alt_available.append(name)

    if alt_available:
        shown = ", ".join(alt_available[:5])
        parsed.notices.append(
            f"Showing the searched set's printing for: {shown}. "
            "Alternate printings are also available in the other searched sets."
        )
    return overlay


def _apply_set_scoped_printings(
    sid: str,
    cards_list: list[dict],
    parsed: "ParsedSearch | None",
    printings: dict[str, str],
) -> dict[str, str]:
    """Merge a set-scoped printing overlay into `printings` for template rendering.

    Reads/writes `sess["search_set_printings"]` (kept separate from the
    manual picker's `sess["printings"]`, see `_printings_context`): a fresh
    `set:` query (different codes than last time) replaces the stored
    overlay outright; the same `set:` query across HTMX pagination
    accumulates entries instead of losing earlier pages' overrides. Manual
    "Choose Printing" picks in `printings` always take precedence.
    """
    session = get_session(sid)
    stored = session.get("search_set_printings") or {}
    set_codes = sorted(parsed.set_include) if parsed and parsed.set_include else []

    if not set_codes:
        if stored:
            session["search_set_printings"] = {}
        return printings

    if stored.get("codes") != set_codes:
        stored = {"codes": set_codes, "entries": {}}
    new_overlay = _set_scoped_printings(cards_list, parsed, printings)
    stored["entries"].update(new_overlay)
    session["search_set_printings"] = stored
    return {**stored["entries"], **printings}


def _apply_collector_number_printings(
    sid: str,
    parsed: "ParsedSearch | None",
    printings: dict[str, str],
) -> dict[str, str]:
    """Merge a `cn:`/`number:`-pinned printing overlay into `printings`.

    Unlike `_set_scoped_printings()`, this resolves against the *entire*
    printings index (not just the current page's `cards_list`), so it needs
    no pagination-accumulation logic -- it's simply recomputed and fully
    replaces `sess["search_cn_printings"]` on every request (cleared to `{}`
    once `cn:`/`number:` is dropped from the query, so a stale pin can't
    outlive the search that produced it). Wins over the plain set-scoped
    overlay but still loses to a manual "Choose Printing" pick.
    """
    session = get_session(sid)
    overlay = resolve_collector_number_printings(parsed) if parsed else {}
    session["search_cn_printings"] = overlay
    return {**printings, **overlay} if overlay else printings


def _set_number_badges(
    cards_list: list[dict],
    parsed: "ParsedSearch | None",
    printings: dict[str, str],
) -> dict[str, dict]:
    """Build a `{name.lower(): {set, set_name, collector_number}}` badge overlay.

    Only populated when exactly one `set:` code is active (Milestone 5
    scope) -- a badge can't unambiguously describe more than one searched
    set. Looks up the printing actually being displayed (the resolved
    `printings` overlay entry, which already reflects cn:/manual-pick
    precedence) so the badge always matches the shown art; falls back to
    the set's own best-scored printing if nothing's been resolved yet.
    """
    if not parsed or len(parsed.set_include) != 1:
        return {}
    set_code = next(iter(parsed.set_include))
    badges: dict[str, dict] = {}
    for card in cards_list:
        name = card.get("name")
        if not name:
            continue
        key = name.lower()
        meta = _image_cache.get_printing_meta(name, scryfall_id=printings.get(key), set_code=set_code)
        if meta:
            badges[key] = meta
    return badges


def _card_printed_sets(card_name: str) -> list[dict]:
    """One chip per unique set a card has been printed in, newest first."""
    printings = _image_cache.get_printings(card_name)
    if not printings:
        return []
    by_code: dict[str, dict] = {}
    for p in printings:
        code = str(p.get("set") or "").upper()
        if not code or code in by_code:
            continue
        by_code[code] = {"code": code, "name": str(p.get("set_name") or code), "released_at": str(p.get("released_at") or "")}
    return sorted(by_code.values(), key=lambda s: s["released_at"], reverse=True)


def get_similarity() -> "CardSimilarity":
    """
    Get cached CardSimilarity instance.
    
    CardSimilarity initialization is expensive (pre-computes tags for 29k cards,
    loads cache with 277k entries). Cache it globally to avoid re-initialization
    on every card detail page load.
    
    Returns:
        Cached CardSimilarity instance
    """
    global _similarity
    if _similarity is None:
        from code.web.services.card_similarity import CardSimilarity
        loader = get_loader()
        df = loader.load()
        logger.info("Initializing CardSimilarity singleton (one-time cost)...")
        _similarity = CardSimilarity(df)
        logger.info("CardSimilarity singleton ready")
    return _similarity


def get_theme_catalog() -> list[str]:
    """
    Get cached list of all theme names from theme_list.json.
    
    theme_list.json is regenerated automatically by every tagging run (unlike
    the supplemental theme_catalog.csv, which needs a separate manual script),
    so it's the more reliably up-to-date source for autocomplete. Only theme
    names are needed here, not the CSV's per-theme counts.
    
    Returns ~900+ themes (as of latest generation).
    """
    global _theme_catalog
    if _theme_catalog is None:
        import json
        from pathlib import Path
        import os
        
        print("Loading theme catalog...", flush=True)
        
        # Try multiple possible paths (local dev vs Docker).
        # NOTE: parents[3] from code/web/routes/card_browser.py is the repo root
        # (code/web/routes -> code/web -> code -> root); code/config/themes/ is a
        # small committed CI fixture (editorial_governance tests), not the real catalog.
        possible_paths = [
            Path(__file__).resolve().parents[3] / "config" / "themes" / "theme_list.json",  # Local dev
            Path("/app/config/themes/theme_list.json"),  # Docker
            Path(os.environ.get("CONFIG_DIR", "/app/config")) / "themes" / "theme_list.json",  # Env var
        ]
        
        themes = []
        loaded = False
        
        for catalog_path in possible_paths:
            print(f"Checking path: {catalog_path} (exists: {catalog_path.exists()})", flush=True)
            if catalog_path.exists():
                try:
                    with open(catalog_path, 'r', encoding='utf-8') as f:
                        payload = json.load(f)
                    
                    themes = [
                        entry["theme"]
                        for entry in payload.get("themes", [])
                        if entry.get("theme")
                    ]
                    
                    _theme_catalog = themes
                    print(f"Loaded {len(themes)} themes from catalog: {catalog_path}", flush=True)
                    logger.info(f"Loaded {len(themes)} themes from catalog: {catalog_path}")
                    loaded = True
                    break
                except Exception as e:
                    print(f"❌ Failed to load from {catalog_path}: {e}", flush=True)  # Debug log
                    logger.warning(f"Failed to load theme catalog from {catalog_path}: {e}")
        
        if not loaded:
            print("⚠️ No catalog found, falling back to parsing cards", flush=True)  # Debug log
            logger.warning("Failed to load theme catalog from all paths, falling back to parsing cards")
            # Fallback: extract from theme index
            theme_index = get_theme_index()
            _theme_catalog = [theme.title() for theme in theme_index.keys()]
    
    return _theme_catalog


def get_theme_index() -> dict[str, set[int]]:
    """
    Get cached theme-to-card-index mapping for fast lookups.
    
    Returns dict mapping lowercase theme names to sets of card indices.
    Built once on first access and reused for all subsequent theme queries.
    """
    global _theme_index
    if _theme_index is None:
        logger.info("Building theme index for fast lookups...")
        _theme_index = {}
        loader = get_loader()
        df = loader.load()
        
        for idx, row in enumerate(df.itertuples()):
            themes = parse_theme_tags(row.themeTags if hasattr(row, 'themeTags') else '')
            for theme in themes:
                theme_lower = theme.lower()
                if theme_lower not in _theme_index:
                    _theme_index[theme_lower] = set()
                _theme_index[theme_lower].add(idx)
        
        logger.info(f"Theme index built with {len(_theme_index)} unique themes")
    
    return _theme_index


def _apply_search_query(filtered_df: "pd.DataFrame", search: str) -> tuple["pd.DataFrame", "ParsedSearch | None"]:
    """Apply the search box. A query containing any Scryfall-style flags
    (t:/o:/c:/id:/m:/mv:/pow:/tou:/loy:/r:/tag:/is:new/set:) is filtered
    structurally via card_search.py; a plain name-only query keeps this
    browser's existing typo-tolerant fuzzy matching (exact match first,
    then same-word-count fuzzy, then substring/fuzzy), which is more
    forgiving than a strict substring search for the "just typing a card
    name" common case.

    Returns `(filtered_df, parsed)` -- `parsed` is the `ParsedSearch` used
    for structured queries (so callers can read `set_include` for the
    set-scoped printing overlay), or `None` for a plain name search / no
    search at all.
    """
    if not search:
        return filtered_df, None

    parsed = parse_search_query(search)
    if has_structured_flags(parsed):
        filtered_df = apply_parsed_search(filtered_df, parsed)
        filtered_df = apply_extra_clauses(filtered_df, parsed)
        return filtered_df, parsed

    query_lower = search.lower().strip()
    query_words = set(query_lower.split())
    query_norm = _normalize_search_text(search)

    exact_matches = []
    word_count_matches = []
    fuzzy_candidates = []
    fuzzy_indices = []

    for idx, card_name in enumerate(filtered_df['name']):
        card_lower = card_name.lower()
        # For double-faced cards, get the front face name
        front_name = card_lower.split(' // ')[0].strip() if ' // ' in card_lower else card_lower

        # Exact match (full name or front face) -- punctuation-insensitive
        # (commas/apostrophes) so "Alania Divergent Storm" matches "Alania,
        # Divergent Storm" the same way typing the comma would, instead of
        # falling through to the much noisier fuzzy/any-word branch below.
        if (
            card_lower == query_lower
            or front_name == query_lower
            or _normalize_search_text(card_name) == query_norm
            or _normalize_search_text(front_name) == query_norm
        ):
            exact_matches.append(idx)
        # Word count match (same number of words + high similarity)
        elif len(query_lower.split()) == len(front_name.split()) and (
            query_lower in card_lower or any(word in card_lower for word in query_words)
        ):
            word_count_matches.append((idx, card_name))
        # Fuzzy candidate
        elif query_lower in card_lower or any(word in card_lower for word in query_words):
            fuzzy_candidates.append(card_name)
            fuzzy_indices.append(idx)

    final_matches = []
    if exact_matches:
        final_matches = exact_matches
    else:
        if word_count_matches:
            scored_wc = [(idx, _fuzzy_card_name_score(search, name), name)
                         for idx, name in word_count_matches]
            scored_wc.sort(key=lambda x: -x[1])
            final_matches.extend([idx for idx, score, name in scored_wc if score >= 0.3])
        if fuzzy_candidates:
            scored_fuzzy = [(fuzzy_indices[i], _fuzzy_card_name_score(search, name), name)
                             for i, name in enumerate(fuzzy_candidates)]
            scored_fuzzy.sort(key=lambda x: -x[1])
            final_matches.extend([idx for idx, score, name in scored_fuzzy if score >= 0.3])

    if final_matches:
        seen = set()
        unique_matches = []
        for idx in final_matches:
            if idx not in seen:
                seen.add(idx)
                unique_matches.append(idx)
        return filtered_df.iloc[unique_matches], None
    return filtered_df.iloc[0:0], None


@router.get("/", response_class=HTMLResponse)
async def card_browser_index(
    request: Request,
    search: str = Query("", description="Card name search, or Scryfall-style flags (t:/o:/c:/id:/m:/mv:/pow:/tou:/loy:/r:/tag:/art:/is:new/set:)"),
    themes: list[str] = Query([], description="Theme tag filters (AND logic)"),
    sort: str = Query("name_asc", description="Sort order"),
):
    """
    Main card browser page.
    
    Displays initial grid of cards with filters and search bar.
    Uses HTMX for dynamic updates (pagination, filtering, search).
    """
    try:
        loader = get_loader()
        df = loader.load()
        
        # Apply filters
        filtered_df = df.copy()
        
        filtered_df, parsed = _apply_search_query(filtered_df, search)
        
        # Multi-select theme filtering (AND logic: card must have ALL selected themes)
        if themes:
            theme_index = get_theme_index()
            
            # For each theme, get matching card indices
            all_theme_matches = []
            for theme in themes:
                theme_lower = theme.lower().strip()
                
                # Try exact match first (instant lookup)
                if theme_lower in theme_index:
                    # Direct index lookup - O(1) instead of O(n)
                    matching_indices = theme_index[theme_lower]
                    all_theme_matches.append(matching_indices)
                else:
                    # Fuzzy match: check all themes in index for similarity
                    matching_indices = set()
                    for indexed_theme, card_indices in theme_index.items():
                        if _fuzzy_theme_match_score(theme, indexed_theme) >= 0.5:
                            matching_indices.update(card_indices)
                    all_theme_matches.append(matching_indices)
            
            # Apply AND logic: card must be in ALL theme match sets
            if all_theme_matches:
                # Start with first theme's matches
                intersection = all_theme_matches[0]
                # Intersect with all other theme matches
                for theme_matches in all_theme_matches[1:]:
                    intersection = intersection & theme_matches
                
                # Intersect with current filtered_df indices
                current_indices = set(filtered_df.index)
                valid_indices = intersection & current_indices
                if valid_indices:
                    filtered_df = filtered_df.loc[list(valid_indices)]
                else:
                    filtered_df = filtered_df.iloc[0:0]

        # Apply sorting
        set_cn_sort_map: dict = {}
        if sort == "name_asc" and parsed and len(parsed.set_include) == 1:
            (only_set_code,) = parsed.set_include
            set_cn_sort_map = get_set_collector_number_sort_map(only_set_code)
        if set_cn_sort_map:
            # Single-set search: default to collector-number order instead of alphabetical.
            filtered_df['_cn_sort'] = filtered_df['name'].str.lower().map(set_cn_sort_map).fillna(float('inf'))
            filtered_df = filtered_df.sort_values(['_cn_sort', 'name'], ascending=[True, True])
            filtered_df = filtered_df.drop('_cn_sort', axis=1)
        elif sort == "name_desc":
            # Name Z-A
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower(), ascending=False)
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        elif sort == "cmc_asc":
            # CMC Low-High, then name
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[True, True])
        elif sort == "cmc_desc":
            # CMC High-Low, then name
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[False, True])
        elif sort == "power_desc":
            # Power High-Low (creatures first, then non-creatures)
            # Convert power to numeric, NaN becomes -1 for sorting
            filtered_df['_power_sort'] = pd.to_numeric(filtered_df['power'], errors='coerce').fillna(-1)
            filtered_df = filtered_df.sort_values(['_power_sort', 'name'], ascending=[False, True])
            filtered_df = filtered_df.drop('_power_sort', axis=1)
        elif sort == "edhrec_asc":
            # EDHREC rank (low number = popular)
            if 'edhrecRank' in filtered_df.columns:
                # NaN goes to end (high value)
                filtered_df['_edhrec_sort'] = filtered_df['edhrecRank'].fillna(999999)
                filtered_df = filtered_df.sort_values(['_edhrec_sort', 'name'], ascending=[True, True])
                filtered_df = filtered_df.drop('_edhrec_sort', axis=1)
            else:
                # Fallback to name sort
                filtered_df = filtered_df.sort_values('name')
        else:
            # Default: Name A-Z (name_asc)
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower())
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        
        total_cards = len(filtered_df)
        
        # Get first page (20 cards)
        per_page = 20
        cards_page = filtered_df.head(per_page)
        
        # Convert to list of dicts
        cards_list = cards_page.to_dict('records')
        
        # Parse theme tags and color identity for each card
        for card in cards_list:
            card['themeTags_parsed'] = parse_theme_tags(card.get('themeTags', ''))
            # Parse colorIdentity which can be:
            # - "Colorless" -> [] (but mark as colorless)
            # - "W" -> ['W']
            # - "B, R, U" -> ['B', 'R', 'U']
            # - "['W', 'U']" -> ['W', 'U']
            # - empty/None -> []
            raw_color = card.get('colorIdentity', '')
            is_colorless = False
            if raw_color and isinstance(raw_color, str):
                if raw_color.lower() == 'colorless':
                    card['colorIdentity'] = []
                    is_colorless = True
                elif raw_color.startswith('['):
                    # Parse list-like strings e.g. "['W', 'U']"
                    card['colorIdentity'] = parse_theme_tags(raw_color)
                elif ', ' in raw_color:
                    # Parse comma-separated e.g. "B, R, U"
                    card['colorIdentity'] = [c.strip() for c in raw_color.split(',')]
                else:
                    # Single color e.g. "W"
                    card['colorIdentity'] = [raw_color.strip()]
            elif not raw_color:
                card['colorIdentity'] = []
            card['is_colorless'] = is_colorless
            card['color_badges'] = color_identity_badges(card['colorIdentity'])
            # TODO: Add owned card checking when integrated
            card['is_owned'] = False
        
        # Calculate pagination info
        per_page = 20
        total_filtered = len(filtered_df)
        total_pages = (total_filtered + per_page - 1) // per_page  # Ceiling division
        current_page = 1  # Always page 1 on initial load (cursor-based makes exact page tricky)
        
        # Determine if there's a next page
        has_next = total_cards > per_page
        last_card_name = cards_list[-1]['name'] if cards_list else ""
        
        printings, sid, had_cookie = _printings_context(request)
        manual_printings = printings
        printings = _apply_set_scoped_printings(sid, cards_list, parsed, printings)
        printings = _apply_collector_number_printings(sid, parsed, printings)
        printings = {**printings, **manual_printings}
        set_badges = _set_number_badges(cards_list, parsed, printings)

        # A search that narrows to exactly one card skips the results grid
        # entirely and jumps straight to that card's detail page -- any
        # set:-scoped printing is already carried over via the session
        # overlay above, which card_detail() also reads.
        if search and total_filtered == 1 and cards_list:
            from urllib.parse import quote
            resp = RedirectResponse(url=f"/cards/{quote(cards_list[0]['name'])}", status_code=302)
            if not had_cookie:
                try:
                    resp.set_cookie("sid", sid, max_age=60 * 60 * 8, httponly=True, samesite="lax")
                except Exception:
                    pass
            return resp

        foils = _foils_context(request, sid)
        resp = templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": cards_list,
                "total_cards": len(df),  # Original unfiltered count
                "filtered_count": total_filtered,  # After filters applied
                "has_next": has_next,
                "last_card": last_card_name,
                "search": search,
                "themes": themes,
                "sort": sort,
                "per_page": per_page,
                "current_page": current_page,
                "total_pages": total_pages,
                "enable_card_details": ENABLE_CARD_DETAILS,
                "printings": printings,
                "foils": foils,
                "set_badges": set_badges,
            },
        )
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60 * 60 * 8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
    
    except FileNotFoundError as e:
        logger.error(f"Card data not found: {e}")
        return templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": [],
                "total_cards": 0,
                "has_next": False,
                "last_card": "",
                "search": "",
                "per_page": 20,
                "error": "Card data not available. Please run setup to generate all_cards.parquet.",
                "enable_card_details": ENABLE_CARD_DETAILS,
            },
        )
    except Exception as e:
        logger.error(f"Error loading card browser: {e}", exc_info=True)
        return templates.TemplateResponse(
            "browse/cards/index.html",
            {
                "request": request,
                "cards": [],
                "total_cards": 0,
                "has_next": False,
                "last_card": "",
                "search": "",
                "per_page": 20,
                "error": f"Error loading cards: {str(e)}",
                "enable_card_details": ENABLE_CARD_DETAILS,
            },
        )


@router.get("/grid", response_class=HTMLResponse)
async def card_browser_grid(
    request: Request,
    cursor: str = Query("", description="Last card name from previous page"),
    search: str = Query("", description="Card name search, or Scryfall-style flags (t:/o:/c:/id:/m:/mv:/pow:/tou:/loy:/r:/tag:/art:/is:new/set:)"),
    themes: list[str] = Query([], description="Theme tag filters (AND logic)"),
    sort: str = Query("name_asc", description="Sort order"),
):
    """
    HTMX endpoint for paginated card grid.
    
    Returns only the grid partial HTML for seamless pagination.
    Uses cursor-based pagination (last_card_name) for performance.
    """
    try:
        loader = get_loader()
        df = loader.load()
        
        # Apply filters
        filtered_df = df.copy()
        
        filtered_df, parsed = _apply_search_query(filtered_df, search)
        
        # Multi-select theme filtering (AND logic: card must have ALL selected themes)
        if themes:
            theme_index = get_theme_index()
            
            # For each theme, get matching card indices
            all_theme_matches = []
            for theme in themes:
                theme_lower = theme.lower().strip()
                
                # Try exact match first (instant lookup)
                if theme_lower in theme_index:
                    # Direct index lookup - O(1) instead of O(n)
                    matching_indices = theme_index[theme_lower]
                    all_theme_matches.append(matching_indices)
                else:
                    # Fuzzy match: check all themes in index for similarity
                    matching_indices = set()
                    for indexed_theme, card_indices in theme_index.items():
                        if _fuzzy_theme_match_score(theme, indexed_theme) >= 0.5:
                            matching_indices.update(card_indices)
                    all_theme_matches.append(matching_indices)
            
            # Apply AND logic: card must be in ALL theme match sets
            if all_theme_matches:
                # Start with first theme's matches
                intersection = all_theme_matches[0]
                # Intersect with all other theme matches
                for theme_matches in all_theme_matches[1:]:
                    intersection = intersection & theme_matches
                
                # Intersect with current filtered_df indices
                current_indices = set(filtered_df.index)
                valid_indices = intersection & current_indices
                if valid_indices:
                    filtered_df = filtered_df.loc[list(valid_indices)]
                else:
                    filtered_df = filtered_df.iloc[0:0]
        
        # Apply sorting (same logic as main endpoint)
        set_cn_sort_map: dict = {}
        if sort == "name_asc" and parsed and len(parsed.set_include) == 1:
            (only_set_code,) = parsed.set_include
            set_cn_sort_map = get_set_collector_number_sort_map(only_set_code)
        if set_cn_sort_map:
            filtered_df['_cn_sort'] = filtered_df['name'].str.lower().map(set_cn_sort_map).fillna(float('inf'))
            filtered_df = filtered_df.sort_values(['_cn_sort', 'name'], ascending=[True, True])
            filtered_df = filtered_df.drop('_cn_sort', axis=1)
        elif sort == "name_desc":
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower(), ascending=False)
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        elif sort == "cmc_asc":
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[True, True])
        elif sort == "cmc_desc":
            filtered_df = filtered_df.sort_values(['manaValue', 'name'], ascending=[False, True])
        elif sort == "power_desc":
            filtered_df['_power_sort'] = pd.to_numeric(filtered_df['power'], errors='coerce').fillna(-1)
            filtered_df = filtered_df.sort_values(['_power_sort', 'name'], ascending=[False, True])
            filtered_df = filtered_df.drop('_power_sort', axis=1)
        elif sort == "edhrec_asc":
            if 'edhrecRank' in filtered_df.columns:
                filtered_df['_edhrec_sort'] = filtered_df['edhrecRank'].fillna(999999)
                filtered_df = filtered_df.sort_values(['_edhrec_sort', 'name'], ascending=[True, True])
                filtered_df = filtered_df.drop('_edhrec_sort', axis=1)
            else:
                filtered_df = filtered_df.sort_values('name')
        else:
            # Default: Name A-Z
            filtered_df['_sort_key'] = filtered_df['name'].str.replace('"', '', regex=False).str.replace("'", '', regex=False)
            filtered_df['_sort_key'] = filtered_df['_sort_key'].apply(
                lambda x: x.replace('_', ' ') if x.startswith('_') else x
            )
            filtered_df = filtered_df.sort_values('_sort_key', key=lambda col: col.str.lower())
            filtered_df = filtered_df.drop('_sort_key', axis=1)
        
        # Cursor-based pagination
        # Cursor is the card name - skip all cards until we find it, then take next batch
        if cursor:
            try:
                # Find the position of the cursor card in the sorted dataframe
                cursor_position = filtered_df[filtered_df['name'] == cursor].index
                if len(cursor_position) > 0:
                    # Get the iloc position (row number, not index label)
                    cursor_iloc = filtered_df.index.get_loc(cursor_position[0])
                    # Skip past the cursor card (take everything after it)
                    filtered_df = filtered_df.iloc[cursor_iloc + 1:]
            except (KeyError, IndexError):
                # Cursor card not found - might have been filtered out, just proceed
                pass
        
        per_page = 20
        cards_page = filtered_df.head(per_page)
        cards_list = cards_page.to_dict('records')
        
        # Parse theme tags and color identity
        for card in cards_list:
            card['themeTags_parsed'] = parse_theme_tags(card.get('themeTags', ''))
            # Parse colorIdentity which can be:
            # - "Colorless" -> [] (but mark as colorless)
            # - "W" -> ['W']
            # - "B, R, U" -> ['B', 'R', 'U']
            # - "['W', 'U']" -> ['W', 'U']
            # - empty/None -> []
            raw_color = card.get('colorIdentity', '')
            is_colorless = False
            if raw_color and isinstance(raw_color, str):
                if raw_color.lower() == 'colorless':
                    card['colorIdentity'] = []
                    is_colorless = True
                elif raw_color.startswith('['):
                    # Parse list-like strings e.g. "['W', 'U']"
                    card['colorIdentity'] = parse_theme_tags(raw_color)
                elif ', ' in raw_color:
                    # Parse comma-separated e.g. "B, R, U"
                    card['colorIdentity'] = [c.strip() for c in raw_color.split(',')]
                else:
                    # Single color e.g. "W"
                    card['colorIdentity'] = [raw_color.strip()]
            elif not raw_color:
                card['colorIdentity'] = []
            card['is_colorless'] = is_colorless
            card['color_badges'] = color_identity_badges(card['colorIdentity'])
            card['is_owned'] = False  # TODO: Add owned card checking
        
        has_next = len(filtered_df) > per_page
        last_card_name = cards_list[-1]['name'] if cards_list else ""
        
        printings, sid, had_cookie = _printings_context(request)
        manual_printings = printings
        printings = _apply_set_scoped_printings(sid, cards_list, parsed, printings)
        printings = _apply_collector_number_printings(sid, parsed, printings)
        printings = {**printings, **manual_printings}
        set_badges = _set_number_badges(cards_list, parsed, printings)
        foils = _foils_context(request, sid)
        resp = templates.TemplateResponse(
            "browse/cards/_card_grid.html",
            {
                "request": request,
                "cards": cards_list,
                "has_next": has_next,
                "last_card": last_card_name,
                "search": search,
                "themes": themes,
                "sort": sort,
                "enable_card_details": ENABLE_CARD_DETAILS,
                "printings": printings,
                "foils": foils,
                "set_badges": set_badges,
            },
        )
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60 * 60 * 8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
    
    except Exception as e:
        logger.error(f"Error loading card grid: {e}", exc_info=True)
        return HTMLResponse(
            f'<div class="error">Error loading cards: {str(e)}</div>',
            status_code=500,
        )


def _fuzzy_theme_match_score(query: str, theme: str) -> float:
    """
    Calculate fuzzy match score between query and theme name.
    Handles typos in the middle of words.
    
    Returns score from 0.0 to 1.0, higher is better match.
    """
    query_lower = query.lower()
    theme_lower = theme.lower()
    
    # Use sequence matcher for proper fuzzy matching (handles typos)
    base_score = SequenceMatcher(None, query_lower, theme_lower).ratio()
    
    # Bonus for substring match
    substring_bonus = 0.0
    if theme_lower.startswith(query_lower):
        substring_bonus = 0.3  # Strong bonus for prefix
    elif query_lower in theme_lower:
        substring_bonus = 0.2  # Moderate bonus for substring
    
    # Word overlap bonus (for multi-word themes)
    query_words = set(query_lower.split())
    theme_words = set(theme_lower.split())
    word_overlap = 0.0
    if query_words and theme_words:
        overlap_ratio = len(query_words & theme_words) / len(query_words)
        word_overlap = overlap_ratio * 0.2
    
    # Combine scores
    return min(1.0, base_score + substring_bonus + word_overlap)


@router.get("/search", response_class=HTMLResponse)
async def card_browser_search(
    request: Request,
    q: str = Query("", description="Search query"),
):
    """
    Live search autocomplete endpoint.
    
    Returns matching card names for autocomplete suggestions.
    """
    try:
        if not q or len(q) < 2:
            return HTMLResponse("<ul></ul>")
        
        loader = get_loader()
        df = loader.load()

        # Fuzzy-tolerant name match (falls back to typo/punctuation-tolerant
        # matching when the strict substring search yields nothing), same
        # as the main card grid and manual deck builder search.
        matches = apply_name_clauses(df, [q], [])
        matches = matches.sort_values('name').head(10)
        
        card_names = matches['name'].tolist()
        
        # Return as simple HTML list
        html = "<ul>"
        for name in card_names:
            html += f'<li><a href="/cards?search={name}">{name}</a></li>'
        html += "</ul>"
        
        return HTMLResponse(html)
    
    except Exception as e:
        logger.error(f"Error in card search: {e}", exc_info=True)
        return HTMLResponse("<ul></ul>")


def _normalize_search_text(value: str | None) -> str:
    """Normalize search text for fuzzy matching (lowercase, alphanumeric only)."""
    if not value:
        return ""
    # Keep letters, numbers, spaces; convert to lowercase
    import re
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return " ".join(tokens) if tokens else ""


def _fuzzy_card_name_score(query: str, card_name: str) -> float:
    """
    Calculate fuzzy match score between query and card name.
    
    Uses multiple scoring methods similar to commanders.py:
    - Base sequence matching
    - Partial ratio (substring matching)
    - Token matching
    - Word count matching bonus
    - Substring bonuses
    
    Returns score from 0.0 to 1.0, higher is better match.
    """
    normalized_query = _normalize_search_text(query)
    normalized_card = _normalize_search_text(card_name)
    
    if not normalized_query or not normalized_card:
        return 0.0
    
    # Base sequence matching
    base_score = SequenceMatcher(None, normalized_query, normalized_card).ratio()
    
    # Partial ratio - best matching substring
    query_len = len(normalized_query)
    if query_len <= len(normalized_card):
        best_partial = 0.0
        for i in range(len(normalized_card) - query_len + 1):
            substr = normalized_card[i:i + query_len]
            ratio = SequenceMatcher(None, normalized_query, substr).ratio()
            if ratio > best_partial:
                best_partial = ratio
    else:
        best_partial = base_score
    
    # Token matching
    query_tokens = normalized_query.split()
    card_tokens = normalized_card.split()
    
    if query_tokens and card_tokens:
        # Average token score
        token_scores = []
        for q_token in query_tokens:
            best_token_match = max(
                (SequenceMatcher(None, q_token, c_token).ratio() for c_token in card_tokens),
                default=0.0
            )
            token_scores.append(best_token_match)
        token_avg = sum(token_scores) / len(token_scores) if token_scores else 0.0
        
        # Word count bonus: prioritize same number of words
        # "peer parker" (2 words) should match "peter parker" (2 words) over "peter parker amazing" (3 words)
        word_count_bonus = 0.0
        if len(query_tokens) == len(card_tokens):
            word_count_bonus = 0.15  # Significant bonus for same word count
    else:
        token_avg = 0.0
        word_count_bonus = 0.0
    
    # Substring bonuses
    substring_bonus = 0.0
    if normalized_card.startswith(normalized_query):
        substring_bonus = 1.0
    elif normalized_query in normalized_card:
        substring_bonus = 0.9
    elif query_tokens and all(token in card_tokens for token in query_tokens):
        substring_bonus = 0.85
    
    # Combine scores with word count bonus
    base_result = max(base_score, best_partial, token_avg, substring_bonus)
    return min(1.0, base_result + word_count_bonus)  # Cap at 1.0



@router.get("/theme-autocomplete", response_class=HTMLResponse)
async def card_theme_autocomplete(
    request: Request,
    q: str = Query(..., min_length=2, description="Theme search query"),
    limit: int = Query(10, ge=1, le=20),
) -> HTMLResponse:
    """
    HTMX endpoint for theme tag autocomplete with fuzzy matching.
    
    Uses theme catalog for instant lookups (no card parsing required).
    """
    try:
        # Use cached theme catalog (loaded from CSV, not parsed from cards)
        all_themes = get_theme_catalog()
        
        # Fuzzy match themes using helper function
        scored_themes: list[tuple[float, str]] = []
        
        # Only check against theme names from catalog (~575 themes)
        for theme in all_themes:
            score = _fuzzy_theme_match_score(q, theme)
            # Only include if score is reasonable (0.5+ = 50%+ match)
            if score >= 0.5:
                scored_themes.append((score, theme))
        
        # Sort by score (desc), then alphabetically
        scored_themes.sort(key=lambda x: (-x[0], x[1].lower()))
        top_matches = scored_themes[:limit]
        
        # Generate HTML suggestions
        html_parts = []
        for score, theme in top_matches:
            safe_theme = theme.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            html_parts.append(
                f'<div class="autocomplete-item" data-value="{safe_theme}" role="option">'
                f'{safe_theme}</div>'
            )
        
        html = "\n".join(html_parts) if html_parts else '<div class="autocomplete-empty">No matching themes</div>'
        
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Error in theme autocomplete: {e}", exc_info=True)
        return HTMLResponse(content=f'<div class="autocomplete-error">Error: {str(e)}</div>')


@router.get("/{card_name:path}/similar")
async def get_similar_cards_partial(request: Request, card_name: str):
    """
    HTMX endpoint: Returns just the similar cards section for a given card.
    Used for refreshing similar cards without reloading the entire page.
    
    Note: Uses :path to capture DFC names with // in them.
    Must be registered BEFORE the /{card_name:path} catch-all route.
    """
    try:
        from urllib.parse import unquote
        
        # Decode URL-encoded card name
        card_name = unquote(card_name)
        
        # Load cards data
        loader = get_loader()
        df = loader.load()
        
        # Get main card for theme tags
        card_row = df[df['name'] == card_name]
        if card_row.empty:
            return templates.TemplateResponse(
                "browse/cards/_similar_cards.html",
                {
                    "request": request,
                    "similar_cards": [],
                    "main_card_tags": [],
                }
            )
        
        card = card_row.iloc[0].to_dict()
        main_card_tags = parse_theme_tags(card.get('themeTags', ''))
        
        # Calculate similar cards
        similarity = get_similarity()
        similar_cards = similarity.find_similar(
            card_name,
            threshold=0.8,
            limit=15,
            min_results=3,
            adaptive=True
        )
        
        # Enrich similar cards with full data
        for similar in similar_cards:
            similar_row = df[df['name'] == similar['name']]
            if not similar_row.empty:
                similar_data = similar_row.iloc[0].to_dict()
                theme_tags_parsed = parse_theme_tags(similar_data.get('themeTags', ''))
                similar.update(similar_data)
                similar['themeTags'] = theme_tags_parsed
        
        logger.info(f"Similar cards refresh for '{card_name}': {len(similar_cards)} cards")
        
        return templates.TemplateResponse(
            "browse/cards/_similar_cards.html",
            {
                "request": request,
                "card": card,
                "similar_cards": similar_cards,
                "main_card_tags": main_card_tags,
            }
        )
        
    except Exception as e:
        logger.error(f"Error loading similar cards for '{card_name}': {e}", exc_info=True)
        # Try to get card data for error case too
        try:
            loader = get_loader()
            df = loader.load()
            card_row = df[df['name'] == card_name]
            card = card_row.iloc[0].to_dict() if not card_row.empty else {"name": card_name}
        except Exception:
            card = {"name": card_name}
        
        return templates.TemplateResponse(
            "browse/cards/_similar_cards.html",
            {
                "request": request,
                "card": card,
                "similar_cards": [],
                "main_card_tags": [],
            }
        )


@router.get("/{card_name:path}", response_class=HTMLResponse)
async def card_detail(request: Request, card_name: str, ref: str = Query("", description="Referring page (owned)")):
    """
    Display detailed information about a single card with similar cards.
    
    Args:
        card_name: URL-encoded card name (using :path to capture names with / like DFCs)
    
    Returns:
        HTML page with card details and similar cards section
    """
    try:
        from urllib.parse import unquote
        
        # Decode URL-encoded card name
        card_name = unquote(card_name)
        
        # Load card data
        loader = get_loader()
        df = loader.load()
        
        # Find the card
        card_row = df[df['name'] == card_name]
        
        if card_row.empty:
            # Card not found - return 404 page
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error_code": 404,
                    "error_message": f"Card not found: {card_name}",
                    "back_link": "/cards",
                    "back_text": "Back to Card Browser"
                },
                status_code=404
            )
        
        # Get card data as dict
        card = card_row.iloc[0].to_dict()
        
        # Parse theme tags using helper function
        card['themeTags_parsed'] = parse_theme_tags(card.get('themeTags', ''))
        card['artTags_parsed'] = parse_theme_tags(card.get('artTags', ''))
        card['metadataTags_parsed'] = parse_theme_tags(card.get('metadataTags', ''))
        
        # Calculate similar cards using cached singleton
        similarity = get_similarity()
        similar_cards = similarity.find_similar(
            card_name,
            threshold=0.8,  # Start at 80%
            limit=15,       # Show up to 15 cards
            min_results=3,  # Target minimum 3
            adaptive=True   # Enable adaptive thresholds (80% → 60%)
        )
        
        # Enrich similar cards with full data
        for similar in similar_cards:
            similar_row = df[df['name'] == similar['name']]
            if not similar_row.empty:
                similar_data = similar_row.iloc[0].to_dict()
                
                # Parse theme tags before updating (so we have the list, not string)
                theme_tags_parsed = parse_theme_tags(similar_data.get('themeTags', ''))
                
                similar.update(similar_data)
                
                # Set the parsed tags list (not the string version from df)
                similar['themeTags'] = theme_tags_parsed
        
        # Log card detail page access
        if similar_cards:
            threshold_pct = similar_cards[0].get('threshold_used', 0) * 100
            logger.info(
                f"Card detail page for '{card_name}': found {len(similar_cards)} similar cards "
                f"(threshold: {threshold_pct:.0f}%)"
            )
        else:
            logger.info(f"Card detail page for '{card_name}': no similar cards found")
        
        # Get main card's theme tags for overlap highlighting
        main_card_tags = card.get('themeTags_parsed', [])

        # Fetch rulings (cache-first, live fallback)
        from code.web.services.rulings import get_rulings
        from urllib.parse import quote_plus
        scryfall_id = card.get('scryfallID') or ''
        rulings = await get_rulings(scryfall_id) if scryfall_id else []

        # External links (URL-encoded so apostrophes/commas are safe)
        _encoded_name = quote_plus(card_name)
        scryfall_url = f"https://scryfall.com/search?q=%21%22{_encoded_name}%22"
        gatherer_url = f"https://gatherer.wizards.com/Pages/Card/Details.aspx?name={_encoded_name}"

        # Smart back button: go back to whichever page linked here
        _ref = ref.strip().lower() if ref else ""
        back_url  = "/owned" if _ref == "owned" else "/cards"
        back_text = "Back to Owned Library" if _ref == "owned" else "Back to Card Browser"

        printings, sid, had_cookie = _printings_context(request)
        # Carry over a `set:`/`cn:` search's printing overlay (see
        # _apply_set_scoped_printings / _apply_collector_number_printings) so
        # following a search result into its detail page still shows that
        # search's art; manual picks still win.
        session = get_session(sid)
        set_overlay = session.get("search_set_printings", {}).get("entries", {})
        cn_overlay = session.get("search_cn_printings", {})
        printings = {**set_overlay, **cn_overlay, **printings}
        foils = _foils_context(request, sid)

        # M5 set+cn badge: only when the last search was scoped to exactly
        # one set: (see _set_number_badges' docstring for why).
        set_codes = session.get("search_set_printings", {}).get("codes") or []
        set_badge = None
        if len(set_codes) == 1:
            set_badge = _image_cache.get_printing_meta(
                card_name, scryfall_id=printings.get(card_name.lower()), set_code=set_codes[0]
            )

        # Per-face details (type/text/mana value/power/toughness) for the
        # "Transform" flip button on double-faced/split/flip/meld cards --
        # the tagged dataset collapses multi-face cards to a single
        # primary-face row, so the back face's text/stats have to be
        # recovered from the raw MTGJSON data (see _get_card_faces()).
        try:
            faces = _get_card_faces(card_name)
        except Exception:
            faces = []

        card_printed_sets = _card_printed_sets(card_name)

        resp = templates.TemplateResponse(
            "browse/cards/detail.html",
            {
                "request": request,
                "card": card,
                "faces": faces,
                "similar_cards": similar_cards,
                "main_card_tags": main_card_tags,
                "rulings": rulings,
                "scryfall_url": scryfall_url,
                "gatherer_url": gatherer_url,
                "back_url": back_url,
                "back_text": back_text,
                "printings": printings,
                "foils": foils,
                "set_badge": set_badge,
                "card_printed_sets": card_printed_sets,
            }
        )
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60 * 60 * 8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
        
    except Exception as e:
        logger.error(f"Error loading card detail for '{card_name}': {e}", exc_info=True)
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_code": 500,
                "error_message": f"Error loading card details: {str(e)}",
                "back_link": "/cards",
                "back_text": "Back to Card Browser"
            },
            status_code=500
        )

