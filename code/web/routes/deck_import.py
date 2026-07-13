"""Route handlers for deck import (M5/M4 — Roadmap 24).

Endpoints:
  GET  /decks/import                     — upload/paste form page
  POST /decks/import                     — parse + validate + analyse; returns analysis partial
  GET  /decks/import/upgrades            — upgrade suggestions for an imported deck (token-based)
  GET  /decks/import/upgrades/cards      — HTMX pagination partial for import upgrades
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..app import templates
from ..services.deck_import_service import (
    DeckListParser,
    FillSuggestion,
    analyze_composition,
    apply_prune,
    build_deck_cards_from_enriched,
    get_fill_suggestions,
    get_replacements_for_card,
    load_temp_session,
    purge_old_temp_sessions,
    rank_cut_candidates,
    save_imported_deck,
    validate_and_enrich,
    write_temp_session,
)
from ..services.tasks import get_session_value, new_sid, set_session_value

router = APIRouter(prefix="/decks", tags=["import"])

_parser = DeckListParser()

_MAX_FILE_BYTES = 512 * 1024  # 512 KB


@router.get("/import", response_class=HTMLResponse)
async def get_import_page(
    request: Request,
    token: Optional[str] = Query(None),
    expired: bool = Query(False),
) -> HTMLResponse:
    """Render the deck import page.

    When ``token`` is provided, attempts to restore a previous analysis from
    the in-memory session or temp file and pre-renders the result into the
    page so "Back to Import" returns the user to their analysis instead of a
    blank form.
    """
    if token:
        # 1. Try live session
        session_result = _get_import_session(token)
        if session_result is not None:
            enriched, analysis = session_result
            parsed_warnings: list[str] = []
        else:
            # 2. Fall back to temp file
            temp_result = load_temp_session(token)
            if temp_result is not None:
                enriched, analysis, parsed_warnings = temp_result
                # Restore into session for subsequent requests
                from ..services.tasks import set_session_value  # noqa: PLC0415
                set_session_value(token, "import_enriched", enriched)
                set_session_value(token, "import_analysis", analysis)
            else:
                # 3. Expired / not found — show blank form with notice
                return templates.TemplateResponse(
                    "decks/import.html",
                    {"request": request, "session_expired": True},
                )

        unrecognized_pct = (
            len(enriched.unrecognized) / max(len(enriched.cards), 1) * 100
        )

        total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
        n_over = max(total - 100, 0)
        cut_candidates = rank_cut_candidates(enriched, analysis, min(n_over + 15, total)) if n_over > 0 else []

        partial_ctx = _build_analysis_ctx(token, enriched, analysis, parsed_warnings, cut_candidates)
        partial_ctx["request"] = request
        preloaded_result = templates.env.get_template(
            "decks/_import_analysis.html"
        ).render(partial_ctx)
        return templates.TemplateResponse(
            "decks/import.html",
            {"request": request, "preloaded_result": preloaded_result},
        )

    return templates.TemplateResponse(
        "decks/import.html",
        {"request": request, "session_expired": expired, "placeholder_themes": _random_theme_examples()},
    )


def _random_theme_examples(n: int = 3) -> str:
    """Return N random theme names from the catalog, with at most one Kindred theme."""
    import random as _random  # noqa: PLC0415
    try:
        from code.deck_builder.theme_catalog_loader import load_theme_catalog  # noqa: PLC0415
        entries, _ = load_theme_catalog()
        names = [e.theme for e in entries if e.theme]
        kindred = [t for t in names if "kindred" in t.lower() or "tribal" in t.lower()]
        non_kindred = [t for t in names if t not in kindred]
        result: list[str] = []
        if kindred and _random.random() < 0.4:  # ~40% chance to include one kindred theme
            result.append(_random.choice(kindred))
        remaining = _random.sample(non_kindred, min(n - len(result), len(non_kindred)))
        result.extend(remaining)
        _random.shuffle(result)
        return ", ".join(result[:n])
    except Exception:
        return "Spells Matter, Go Wide, Artifacts"


@router.post("/import", response_class=HTMLResponse)
async def post_import(
    request: Request,
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    commander: Optional[str] = Form(None),
    themes: Optional[str] = Form(None),
    auto_detect: bool = Form(True),
) -> HTMLResponse:
    """Parse, validate, and analyse a submitted deck list.

    Accepts either a pasted text block or a .txt file upload (max 512 KB).
    Returns the _import_analysis.html partial for HTMX swap, or the full page
    for non-HTMX requests.
    """
    raw_text: str = ""
    errors: list[str] = []

    # --- Input resolution: file takes priority over text ---
    if file and file.filename:
        content_type = (file.content_type or "").lower()
        # Accept text/plain and application/octet-stream (browser-dependent)
        if content_type and "text" not in content_type and content_type not in (
            "application/octet-stream", ""
        ):
            errors.append(
                f"Unsupported file type '{content_type}'. Only plain-text (.txt) files are accepted."
            )
        else:
            raw_bytes = await file.read(_MAX_FILE_BYTES + 1)
            if len(raw_bytes) > _MAX_FILE_BYTES:
                errors.append("File too large (max 512 KB).")
            else:
                try:
                    raw_text = raw_bytes.decode("utf-8", errors="replace")
                except Exception:
                    errors.append("Could not decode file as UTF-8 text.")
    elif text:
        raw_text = text

    if not raw_text and not errors:
        errors.append("No deck list provided. Paste your deck or upload a .txt file.")

    if errors:
        ctx = {
            "request": request,
            "parse_errors": errors,
        }
        template = "decks/_import_analysis.html"
        return templates.TemplateResponse(template, ctx, status_code=400)

    # --- M1: parse ---
    parsed = _parser.parse(raw_text)

    # Commander override from form
    if commander and commander.strip():
        parsed.commander = commander.strip()

    # --- M2: validate & enrich ---
    enriched = validate_and_enrich(parsed)

    # --- M3: analyse ---
    user_theme_list: list[str] = []
    if themes and themes.strip():
        user_theme_list = [t.strip() for t in themes.split(",") if t.strip()]

    from ..services.deck_import_service import detect_themes  # noqa: PLC0415
    # Manual themes take full precedence — disable auto-detection if themes were provided
    effective_auto_detect = auto_detect and not user_theme_list
    theme_result = detect_themes(enriched, user_themes=user_theme_list or None, auto_detect=effective_auto_detect)

    analysis = analyze_composition(enriched)
    analysis.themes = theme_result

    # --- Store in session ---
    sid = new_sid()
    set_session_value(sid, "import_enriched", enriched)
    set_session_value(sid, "import_analysis", analysis)
    analysis.upgrade_token = sid

    # --- Persist to temp file for "Back to Import" navigation ---
    write_temp_session(sid, enriched, analysis, list(parsed.warnings))
    purge_old_temp_sessions()

    # Pre-compute cut candidates if deck is over 100
    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_over = max(total - 100, 0)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_over + 15, total)) if n_over > 0 else []

    ctx = _build_analysis_ctx(sid, enriched, analysis, list(parsed.warnings), cut_candidates)
    ctx["parsed"] = parsed  # use real parsed for warnings display
    ctx["request"] = request

    template = "decks/_import_analysis.html"
    return templates.TemplateResponse(template, ctx)


def _get_import_session(token: str) -> tuple | None:
    """Retrieve (enriched, analysis) from session; returns None if missing/expired."""
    enriched = get_session_value(token, "import_enriched")
    analysis = get_session_value(token, "import_analysis")
    if enriched is None or analysis is None:
        return None
    return enriched, analysis


def _build_analysis_ctx(
    token: str,
    enriched: "EnrichedDeck",
    analysis: "DeckAnalysis",
    parsed_warnings: list[str],
    cut_candidates: list | None = None,
    recently_cut: list | None = None,
) -> dict:
    """Build the template context dict for _import_analysis.html."""
    from ..services.deck_import_service import ParsedDeck  # noqa: PLC0415

    unrecognized_pct = (
        len(enriched.unrecognized) / max(len(enriched.cards), 1) * 100
    )
    # Detect non-basic cards with qty > 1 (likely Commander format violations)
    duplicate_cards = [
        c for c in enriched.cards
        if c.quantity > 1 and "Basic Land" not in (c.type_line or "")
        and c.section != "Sideboard"
    ]
    # Simulate a minimal ParsedDeck-like object for the warnings slot
    class _FakeParsed:
        warnings = parsed_warnings
    return {
        "parsed": _FakeParsed(),
        "enriched": enriched,
        "analysis": analysis,
        "upgrade_token": token,
        "unrecognized_pct": round(unrecognized_pct, 1),
        "parse_errors": [],
        "cut_candidates": cut_candidates or [],
        "recently_cut": recently_cut or [],
        "duplicate_cards": duplicate_cards,
    }


def _build_import_upgrade_ctx(token: str, section: str, page: int) -> dict | None:
    """Build the context dict for the import upgrades page; returns None if session missing."""
    from ..app import UPGRADE_PAGE_SIZE  # noqa: PLC0415
    from ..routes.upgrade_suggestions import (  # noqa: PLC0415
        _build_general_ctx,
        _build_new_ctx,
        _build_possible_ctx,
    )

    result = _get_import_session(token)
    if result is None:
        return None
    enriched, analysis = result

    deck_cards = build_deck_cards_from_enriched(enriched)
    color_identity: list[str] = []
    deck_themes: list[str] = []
    commander_name = ""
    if enriched.commander_row is not None:
        try:
            ci = enriched.commander_row.get("colorIdentity") or []
            color_identity = list(ci) if isinstance(ci, (list, tuple)) else list(str(ci))
            deck_themes = list(analysis.themes.user_confirmed + analysis.themes.confirmed)
            if not deck_themes:
                raw = enriched.commander_row.get("themeTags") or []
                deck_themes = list(raw) if isinstance(raw, (list, tuple)) else []
            commander_name = str(enriched.commander_row.get("name") or "")
        except Exception:
            pass

    per_page = max(5, min(50, int(UPGRADE_PAGE_SIZE)))

    if section == "general":
        section_ctx = _build_general_ctx(deck_cards, color_identity, deck_themes, page, per_page)
    elif section == "possible":
        section_ctx = _build_possible_ctx(deck_cards, color_identity, deck_themes, page, per_page)
    else:
        section_ctx = _build_new_ctx(deck_cards, color_identity, page, per_page, deck_themes=deck_themes)
        section = "new"

    # Detect non-basic duplicate cards to surface a warning in the upgrades UI
    duplicate_card_names = [
        c.name for c in enriched.cards
        if c.quantity > 1 and "Basic Land" not in (c.type_line or "")
        and c.section != "Sideboard"
    ]

    return {
        "commander": commander_name,
        "color_identity": color_identity,
        "section": section,
        "card_ceiling": None,
        "import_token": token,
        "duplicate_card_names": duplicate_card_names,
        **section_ctx,
    }


@router.get("/import/upgrades", response_class=HTMLResponse)
async def get_import_upgrades(
    request: Request,
    token: str = Query(..., description="Import session token"),
    section: str = Query("new"),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """Upgrade suggestions for an imported deck, retrieved from session by token."""
    ctx = _build_import_upgrade_ctx(token, section, page)
    if ctx is None:
        return RedirectResponse(url="/decks/import?expired=1", status_code=302)
    return templates.TemplateResponse(
        "decks/upgrade_suggestions.html",
        {"request": request, "name": "", "back_url": f"/decks/import?token={token}", **ctx},
    )


@router.get("/import/upgrades/cards", response_class=HTMLResponse)
async def get_import_upgrades_cards(
    request: Request,
    token: str = Query(...),
    section: str = Query("new"),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """HTMX pagination partial for import upgrade suggestions."""
    ctx = _build_import_upgrade_ctx(token, section, page)
    if ctx is None:
        return HTMLResponse("<p>Session expired. Please re-import your deck.</p>", status_code=404)
    return templates.TemplateResponse(
        "decks/_upgrade_cards_fragment.html",
        {"request": request, "name": "", **ctx},
    )


@router.post("/import/save", response_class=HTMLResponse)
async def post_import_save(
    request: Request,
    token: str = Form(...),
) -> HTMLResponse:
    """Save an imported deck to deck_files/ as permanent CSV + TXT + summary.json.

    Reads enriched/analysis from session (primary) or temp file (fallback).
    On success, redirects to the new deck's view page.
    On session miss, redirects back to /decks/import?expired=1.
    """
    # Resolve session
    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return RedirectResponse(url="/decks/import?expired=1", status_code=302)
        enriched, analysis, _ = temp_result

    try:
        csv_name, _txt_name, _summary_name = save_imported_deck(token, enriched, analysis)
    except Exception as exc:
        ctx = {
            "request": request,
            "parse_errors": [f"Save failed: {exc}"],
        }
        return templates.TemplateResponse("decks/_import_analysis.html", ctx, status_code=500)

    return RedirectResponse(url=f"/decks/view?name={csv_name}", status_code=303)


# ---------------------------------------------------------------------------
# /import/prune — deck pruning (auto-cut or manual selection)
# ---------------------------------------------------------------------------

def _reanalyse_and_store(
    token: str,
    enriched: "EnrichedDeck",
    parsed_warnings: list[str],
) -> tuple["EnrichedDeck", "DeckAnalysis", list[str]]:
    """Re-run theme detection + composition analysis on pruned enriched deck and update session."""
    from ..services.deck_import_service import detect_themes  # noqa: PLC0415

    # Restore themes from existing session to preserve user choices
    session_result = _get_import_session(token)
    old_analysis = session_result[1] if session_result else None

    if old_analysis:
        old_themes = old_analysis.themes
        theme_result = detect_themes(
            enriched,
            user_themes=old_themes.user_confirmed or None,
            auto_detect=not old_themes.user_confirmed,
        )
    else:
        theme_result = detect_themes(enriched)

    analysis = analyze_composition(enriched)
    analysis.themes = theme_result

    set_session_value(token, "import_enriched", enriched)
    set_session_value(token, "import_analysis", analysis)
    set_session_value(token, "import_parsed_warnings", parsed_warnings)
    analysis.upgrade_token = token
    write_temp_session(token, enriched, analysis, parsed_warnings)

    return enriched, analysis, parsed_warnings


@router.post("/import/prune", response_class=HTMLResponse)
async def post_import_prune(
    request: Request,
    token: str = Form(...),
    mode: str = Form("auto"),          # "auto" or "manual"
    remove: list[str] = Form(default=[]),  # card names for manual removal
) -> HTMLResponse:
    """Prune over-limit cards from an imported deck.

    - mode=auto: compute cut candidates automatically (weakest first) and remove them.
    - mode=manual: remove exactly the card names listed in `remove`.

    In both cases, re-runs analysis and refreshes the session, then re-renders the
    analysis partial so the user can review and save or prune further.
    """
    # Resolve session
    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return RedirectResponse(url="/decks/import?expired=1", status_code=302)
        enriched, analysis, _ = temp_result

    parsed_warnings: list[str] = get_session_value(token, "import_parsed_warnings") or []

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")

    if mode == "auto":
        n_to_cut = max(total - 100, 0)
        recently_cut: list = []
        if n_to_cut > 0:
            to_cut = rank_cut_candidates(enriched, analysis, n_to_cut)
            recently_cut = to_cut
            names = [c.card.name for c in to_cut]
            enriched = apply_prune(enriched, names)
    else:
        recently_cut = []
        # manual — remove the names supplied by the form checkboxes
        if remove:
            enriched = apply_prune(enriched, list(remove))

    enriched, analysis, parsed_warnings = _reanalyse_and_store(token, enriched, parsed_warnings)

    # Build cut candidate list for the prune panel (for next round, if still over)
    new_total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_still_over = max(new_total - 100, 0)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_still_over + 15, new_total)) if new_total > 85 else []

    ctx = _build_analysis_ctx(token, enriched, analysis, parsed_warnings, cut_candidates, recently_cut)
    return templates.TemplateResponse(
        "decks/_import_analysis.html",
        {"request": request, **ctx},
    )


@router.get("/import/prune/candidates", response_class=HTMLResponse)
async def get_prune_candidates(
    request: Request,
    token: str = Query(...),
) -> HTMLResponse:
    """Return the manual-prune card list partial for HTMX swap."""
    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return HTMLResponse("<p>Session expired.</p>", status_code=404)
        enriched, analysis, _ = temp_result

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_over = max(total - 100, 0)
    # Show the worst ~15 suggestions plus enough extras to reach 100
    n_show = max(n_over + 15, 10)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_show, total))

    return templates.TemplateResponse(
        "decks/_prune_candidates.html",
        {"request": request, "cut_candidates": cut_candidates, "token": token, "n_to_cut": n_over},
    )


@router.get("/import/duplicate-replacements", response_class=HTMLResponse)
async def get_duplicate_replacements(
    request: Request,
    token: str = Query(...),
    card_name: str = Query(...),
) -> HTMLResponse:
    """Return a replacement-picker panel for one duplicate card (HTMX swap)."""
    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return HTMLResponse("<p class='muted'>Session expired — please re-import.</p>", status_code=404)
        enriched, analysis, _ = temp_result

    # Find the card in the deck
    card = next((c for c in enriched.cards if c.name.lower() == card_name.lower()), None)
    if card is None:
        return HTMLResponse("<p class='muted'>Card not found in deck.</p>", status_code=404)

    replacements = get_replacements_for_card(card, enriched, analysis.color_identity)

    return templates.TemplateResponse(
        "decks/_duplicate_replacements.html",
        {
            "request": request,
            "token": token,
            "card": card,
            "replacements": replacements,
        },
    )


@router.get("/import/fill-suggestions", response_class=HTMLResponse)
async def get_fill_suggestions_route(
    request: Request,
    token: str = Query(...),
) -> HTMLResponse:
    """Return fill suggestion cards for an under-100 deck (HTMX swap)."""
    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return HTMLResponse("<p class='muted'>Session expired — please re-import.</p>", status_code=404)
        enriched, analysis, _ = temp_result

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_to_add = max(100 - total, 0)
    if n_to_add == 0:
        return HTMLResponse("")

    suggestions = get_fill_suggestions(
        enriched, analysis, list(analysis.color_identity), n_to_add
    )

    return templates.TemplateResponse(
        "decks/_fill_suggestions.html",
        {"request": request, "suggestions": suggestions, "token": token, "n_to_add": n_to_add},
    )


@router.post("/import/swap-duplicate", response_class=HTMLResponse)
async def post_swap_duplicate(
    request: Request,
    token: str = Form(...),
    remove_card: str = Form(...),       # name of the duplicate card (removes 1 copy)
    replacement_name: str = Form(""),   # name of the card to add in its place
) -> HTMLResponse:
    """Remove one extra copy of a duplicate and optionally add a replacement.

    If replacement_name is provided, adds that card to the deck using enriched
    data from all_cards.parquet. Re-runs analysis and re-renders the analysis partial.
    """
    from ..services.deck_import_service import (  # noqa: PLC0415
        EnrichedCard,
        _get_all_cards,
        _parse_tags,
    )

    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return RedirectResponse(url="/decks/import?expired=1", status_code=302)
        enriched, analysis, _ = temp_result

    parsed_warnings: list[str] = get_session_value(token, "import_parsed_warnings") or []

    # 1. Remove one copy of the duplicate
    enriched = apply_prune(enriched, [remove_card])

    # 2. Add the replacement if chosen
    if replacement_name.strip():
        df = _get_all_cards()
        repl_row = None
        if df is not None:
            matches = df[df["name"].str.lower() == replacement_name.strip().lower()]
            if not matches.empty:
                repl_row = matches.iloc[0]

        if repl_row is not None:
            tags = _parse_tags(repl_row.get("themeTags"))
            import dataclasses as _dc  # noqa: PLC0415
            new_card = EnrichedCard(
                name=str(repl_row.get("name") or replacement_name),
                quantity=1,
                tags=tags,
                cmc=float(repl_row.get("manaValue") or 0.0),
                type_line=str(repl_row.get("type") or ""),
                is_new=bool(repl_row.get("isNew") or False),
                price=float(repl_row.get("price")) if repl_row.get("price") is not None else None,
                edhrec_rank=int(repl_row.get("edhrecRank")) if repl_row.get("edhrecRank") is not None else None,
                section="Mainboard",
            )
            enriched = _dc.replace(enriched, cards=enriched.cards + [new_card])
            parsed_warnings.append(f"Added '{new_card.name}' as replacement for '{remove_card}'.")
        else:
            parsed_warnings.append(
                f"Replacement '{replacement_name}' not found in card database — only removed the duplicate."
            )

    enriched, analysis, parsed_warnings = _reanalyse_and_store(token, enriched, parsed_warnings)

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_over = max(total - 100, 0)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_over + 15, total)) if n_over > 0 else []

    ctx = _build_analysis_ctx(token, enriched, analysis, parsed_warnings, cut_candidates)
    return templates.TemplateResponse("decks/_import_analysis.html", {"request": request, **ctx})


@router.post("/import/add-card", response_class=HTMLResponse)
async def post_add_card(
    request: Request,
    token: str = Form(...),
    card_name: str = Form(...),
) -> HTMLResponse:
    """Add one copy of a card to an under-100 deck and re-render the analysis partial."""
    from ..services.deck_import_service import (  # noqa: PLC0415
        EnrichedCard,
        _get_all_cards,
        _parse_tags,
    )
    import dataclasses as _dc  # noqa: PLC0415

    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, analysis = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return RedirectResponse(url="/decks/import?expired=1", status_code=302)
        enriched, analysis, _ = temp_result

    parsed_warnings: list[str] = get_session_value(token, "import_parsed_warnings") or []

    df = _get_all_cards()
    if df is not None:
        matches = df[df["name"].str.lower() == card_name.strip().lower()]
        if not matches.empty:
            row = matches.iloc[0]
            tags = _parse_tags(row.get("themeTags"))
            new_card = EnrichedCard(
                name=str(row.get("name") or card_name),
                quantity=1,
                tags=tags,
                cmc=float(row.get("manaValue") or 0.0),
                type_line=str(row.get("type") or ""),
                is_new=bool(row.get("isNew") or False),
                price=float(row.get("price")) if row.get("price") is not None else None,
                edhrec_rank=int(row.get("edhrecRank")) if row.get("edhrecRank") is not None else None,
                section="Mainboard",
            )
            enriched = _dc.replace(enriched, cards=enriched.cards + [new_card])
            parsed_warnings.append(f"Added '{new_card.name}' to deck.")
        else:
            parsed_warnings.append(f"Card '{card_name}' not found in database — not added.")

    enriched, analysis, parsed_warnings = _reanalyse_and_store(token, enriched, parsed_warnings)

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_over = max(total - 100, 0)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_over + 15, total)) if n_over > 0 else []

    ctx = _build_analysis_ctx(token, enriched, analysis, parsed_warnings, cut_candidates)
    return templates.TemplateResponse("decks/_import_analysis.html", {"request": request, **ctx})


@router.post("/import/update-themes", response_class=HTMLResponse)
async def post_update_themes(
    request: Request,
    token: str = Form(...),
    themes: str = Form(""),
) -> HTMLResponse:
    """Re-run theme detection with user-supplied theme overrides and re-render analysis."""
    from ..services.deck_import_service import detect_themes  # noqa: PLC0415
    import dataclasses as _dc  # noqa: PLC0415

    session_result = _get_import_session(token)
    if session_result is not None:
        enriched, _ = session_result
    else:
        temp_result = load_temp_session(token)
        if temp_result is None:
            return RedirectResponse(url="/decks/import?expired=1", status_code=302)
        enriched, _, _ = temp_result

    parsed_warnings: list[str] = get_session_value(token, "import_parsed_warnings") or []

    # Parse user themes from comma-separated string
    user_themes = [t.strip() for t in themes.split(",") if t.strip()]

    # Re-analyse (uses stored enriched deck), then override themes with fresh detection
    enriched, analysis, parsed_warnings = _reanalyse_and_store(token, enriched, parsed_warnings)

    new_themes = detect_themes(enriched, user_themes=user_themes, auto_detect=True)
    analysis = _dc.replace(analysis, themes=new_themes)
    set_session_value(token, "import_analysis", analysis)
    write_temp_session(token, enriched, analysis, parsed_warnings)

    total = sum(c.quantity for c in enriched.cards if c.section != "Sideboard")
    n_over = max(total - 100, 0)
    cut_candidates = rank_cut_candidates(enriched, analysis, min(n_over + 15, total)) if n_over > 0 else []

    ctx = _build_analysis_ctx(token, enriched, analysis, parsed_warnings, cut_candidates)
    return templates.TemplateResponse("decks/_import_analysis.html", {"request": request, **ctx})
