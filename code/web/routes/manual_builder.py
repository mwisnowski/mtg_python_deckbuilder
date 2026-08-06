"""Manual Deck Builder routes (Roadmap 25).

Milestone 1: modal entry point (mode flag only) + the manual builder view
stub. The submit branch that actually stores session state and redirects
here lives in build_newflow.py's build_new_submit (shared "Build Deck" /
"Quick Build" / "Build Manually" form).

Milestone 2: browseable card pool grid (`GET /{session_id}/pool`).
Milestone 3: add/remove/search (`POST /add`, `POST /remove`, `GET /search`).
Milestone 4: hover suggestions (`GET /hover-suggestions`).
Milestone 5: role health bar (folded into add/remove/view responses).
Milestone 6: export & save (`POST /save`, `POST /export/{format}`).
"""
from __future__ import annotations

from html import escape as _esc
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..app import templates
from ..services.tasks import get_session
from ..services import manual_builder_service
from ..services.price_service import get_price_service

router = APIRouter(prefix="/decks/manual", tags=["manual_builder"])


@router.get("/new", response_class=HTMLResponse)
async def manual_builder_new(request: Request) -> HTMLResponse:
    """Same New Deck modal as /build/new, flagged for the manual flow."""
    # Deferred import: build_newflow imports from ..app, and app.py imports
    # this module, so importing at module level would create a cycle.
    from .build_newflow import build_new_modal

    return await build_new_modal(request, mode="manual")


@router.post("/edit-existing")
async def manual_builder_edit_existing(request: Request, name: str = Form(...)) -> Response:
    """Load an existing saved deck (owned by the current user) into a fresh
    manual-builder session, so "Edit Deck" reuses the same pool/add/remove/
    save UI as building a deck from scratch. Saving overwrites the original
    file instead of creating a new one (see `save_manual_deck`).
    """
    # Deferred import: decks.py doesn't import this module, but keeping the
    # import lazy matches this file's existing cross-module import style.
    from .decks import _user_id, _deck_dir, _safe_within
    from ..services.tasks import new_sid

    user = getattr(request.state, "current_user", None)
    uid = _user_id(request)
    if uid == "guest" or not user or user.get("is_guest"):
        return Response("Forbidden", status_code=403)

    base = _deck_dir(uid)
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return Response("Deck not found", status_code=404)

    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    manual_builder_service.load_deck_for_edit(sess, str(p))
    resp = RedirectResponse(url=f"/decks/manual/{sid}", status_code=303)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


def _require_manual_session(request: Request, session_id: str):
    """Shared guard: cookie must match the path session_id, and the session
    must be in manual mode. Returns (sid, sess) or a RedirectResponse.
    """
    sid = request.cookies.get("sid")
    if sid != session_id:
        return None, RedirectResponse(url="/build", status_code=303)
    sess = get_session(sid)
    if sess.get("mode") != "manual":
        return None, RedirectResponse(url="/build", status_code=303)
    return sid, sess


@router.get("/{session_id}", response_class=HTMLResponse)
async def manual_builder_view(request: Request, session_id: str) -> HTMLResponse:
    """Manual builder page for a session started via mode=manual: role
    health bar, categorized pool (every category, capped, no pagination),
    and current deck panel.
    """
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    state = manual_builder_service.manual_session_state(sess)
    search = sess.get("_pool_search", "")
    categories = manual_builder_service.categorize_pool(sess, search=search)
    deck_panel = manual_builder_service.deck_panel_data(sess)
    role_bar = manual_builder_service.role_bar_data(sess)
    compliance = manual_builder_service.manual_compliance_report(sess)
    mana_overview = manual_builder_service.mana_overview_data(sess)
    ctx = {
        "request": request,
        "session_id": sid,
        "category_order": manual_builder_service.CATEGORY_KEYS,
        "categories": categories,
        "pool_search": search,
        "printings": sess.get("_manual_printings") or {},
        "foils": sess.get("_manual_foils") or {},
        **state,
        **deck_panel,
        **role_bar,
        **compliance,
        **mana_overview,
    }
    resp = templates.TemplateResponse("decks/manual_builder.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/{session_id}/pool/{category}", response_class=HTMLResponse)
async def manual_builder_pool_category(
    request: Request,
    session_id: str,
    category: str,
    search: str = Query(""),
) -> HTMLResponse:
    """HTMX fragment: one Milestone 11 category's full (capped) card grid."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    q = search or sess.get("_pool_search", "")
    try:
        cat = manual_builder_service.query_category(sess, category, search=q)
    except ValueError:
        return HTMLResponse("Unknown category", status_code=404)
    ctx = {
        "request": request,
        "session_id": sid,
        "printings": sess.get("_manual_printings") or {},
        "foils": sess.get("_manual_foils") or {},
        **cat,
    }
    return templates.TemplateResponse("decks/_manual_pool_category_body.html", ctx)


@router.get("/{session_id}/search", response_class=HTMLResponse)
async def manual_builder_search(
    request: Request,
    session_id: str,
    q: str = Query(""),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """HTMX fragment: off-pool name search (color-identity legal cards)."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard

    # Matches the category grid's page size (manual_builder_service._CATEGORY_PAGE_SIZE)
    # so search results paginate the same as the rest of the pool.
    per_page = manual_builder_service._CATEGORY_PAGE_SIZE
    result = manual_builder_service.search_off_pool(sess, q, page=page, per_page=per_page)
    ctx = {"request": request, "session_id": sid, "query": q, **result}
    return templates.TemplateResponse("decks/_manual_search_results.html", ctx)


def _deck_update_response(request: Request, sid: str, warning: str | None = None) -> HTMLResponse:
    """Shared response builder for add/remove/land-package: deck panel, role
    bar, and every Milestone 11 category body (all oob, back to page 1 at
    the session's current search term), so an added/removed card's pool
    visibility updates immediately without the user re-touching any controls.
    """
    sess = get_session(sid)
    search = sess.get("_pool_search", "")
    categories = manual_builder_service.categorize_pool(sess, search=search)
    deck_panel = manual_builder_service.deck_panel_data(sess)
    role_bar = manual_builder_service.role_bar_data(sess)
    compliance = manual_builder_service.manual_compliance_report(sess)
    mana_overview = manual_builder_service.mana_overview_data(sess)
    ctx = {
        "request": request,
        "session_id": sid,
        "warning": warning,
        "category_order": manual_builder_service.CATEGORY_KEYS,
        "categories": categories,
        "printings": sess.get("_manual_printings") or {},
        "foils": sess.get("_manual_foils") or {},
        **deck_panel,
        **role_bar,
        **compliance,
        **mana_overview,
    }
    return templates.TemplateResponse("decks/_manual_deck_update.html", ctx)


@router.post("/{session_id}/add", response_class=HTMLResponse)
async def manual_builder_add(request: Request, session_id: str, name: str = Form(...)) -> HTMLResponse:
    """Add a card to the session deck; returns deck panel + role bar (oob)."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    result = manual_builder_service.add_card_to_deck(sess, name)
    warning = None
    if result["status"] == "duplicate":
        warning = f'"{result["name"]}" is already in the deck.'
    elif result["status"] == "not_found":
        warning = f'"{name}" could not be found.'
    elif result["status"] == "bracket_banned":
        warning = f'"{result["name"]}" is not allowed at this deck\'s bracket.'
    return _deck_update_response(request, sid, warning=warning)


@router.post("/{session_id}/remove", response_class=HTMLResponse)
async def manual_builder_remove(request: Request, session_id: str, name: str = Form(...)) -> HTMLResponse:
    """Remove a card from the session deck; returns deck panel + role bar (oob)."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    manual_builder_service.remove_card_from_deck(sess, name)
    return _deck_update_response(request, sid)


@router.post("/{session_id}/set-count", response_class=HTMLResponse)
async def manual_builder_set_count(request: Request, session_id: str, name: str = Form(...), count: int = Form(...)) -> HTMLResponse:
    """Set the exact copy count for a multi-copy-eligible card (basic lands,
    "any number of" cards); returns deck panel + role bar (oob).
    """
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    manual_builder_service.set_card_count(sess, name, count)
    return _deck_update_response(request, sid)


@router.post("/{session_id}/land-package", response_class=HTMLResponse)
async def manual_builder_land_package(request: Request, session_id: str) -> HTMLResponse:
    """Pre-add a starting land base: basics (split by color, per the ideal
    basic-land count) plus the generic staple lands (Command Tower,
    Reliquary Tower, etc.).
    """
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    result = manual_builder_service.add_land_package(sess)
    warning = None if result["count"] else "No lands were added (staples already present or basic-land target is 0)."
    return _deck_update_response(request, sid, warning=warning)


@router.get("/{session_id}/hover-suggestions", response_class=HTMLResponse)
async def manual_builder_hover_suggestions(request: Request, session_id: str, card: str = Query(...)) -> HTMLResponse:
    """HTMX fragment: "Other Good Options" alternatives for a hovered card."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    suggestions = manual_builder_service.hover_suggestions(sess, card)
    ctx = {"request": request, "session_id": sid, "card": card, "suggestions": suggestions}
    return templates.TemplateResponse("decks/_manual_hover_suggestions.html", ctx)


@router.post("/{session_id}/save", response_class=HTMLResponse)
async def manual_builder_save(request: Request, session_id: str) -> RedirectResponse:
    """Save the manual deck as a permanent CSV + TXT + `.summary.json`."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard

    from .build_newflow import _user_deck_dir

    deck_dir = _user_deck_dir(request)
    try:
        csv_name, _txt_name, _summary_name = manual_builder_service.save_manual_deck(sess, deck_dir)
    except RuntimeError as exc:
        ctx = {"request": request, "session_id": sid, "warning": f"Save failed: {exc}",
               **manual_builder_service.deck_panel_data(sess), **manual_builder_service.role_bar_data(sess),
               **manual_builder_service.manual_compliance_report(sess)}
        return templates.TemplateResponse("decks/_manual_deck_update.html", ctx, status_code=500)

    card_count = sum(manual_builder_service.deck_card_counts(sess).values()) + (1 if sess.get("commander") else 0)
    url = f"/decks/view?name={csv_name}"
    if card_count != 100:
        from urllib.parse import quote

        url += f"&notice={quote(f'Deck has {card_count} cards (expected 100).')}"
    return RedirectResponse(url=url, status_code=303)


@router.post("/{session_id}/export/{fmt}")
async def manual_builder_export(request: Request, session_id: str, fmt: str) -> Response:
    """Ad hoc CSV/TXT download of the in-progress deck (not saved to disk)."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard

    commander = sess.get("commander") or "manual_deck"
    slug = manual_builder_service._safe_slug(commander)
    if fmt == "csv":
        content = manual_builder_service.build_deck_csv_text(sess)
        media_type = "text/csv"
        filename = f"{slug}.csv"
    elif fmt == "txt":
        content = manual_builder_service.build_deck_txt_text(sess)
        media_type = "text/plain; charset=utf-8"
        filename = f"{slug}.txt"
    else:
        return Response(content="Unsupported format", status_code=400)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pool_img_html(name: str, tile_id: str, scryfall_id: str, *, oob: bool = False) -> str:
    """`<img>` markup for a pool card tile, mirroring
    `build_permalinks._render_card_img_html` but addressed by `tile_id`
    (a `{category}-{index}` string set on render, see `_manual_pool_card.html`)
    instead of a build-wizard card_library index.
    """
    display_name = name.split(" // ")[0].strip() if " // " in name else name
    q = quote(display_name)
    suffix = f"?printing={quote(scryfall_id)}" if scryfall_id else ""
    normal_url = f"/api/images/normal/{q}{suffix}"
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    return (
        f'<img class="card-thumb" id="pool-img-{_esc(tile_id)}"{oob_attr} '
        f'alt="{_esc(name)}" data-card-name="{_esc(name)}" '
        f'data-printing-id="{_esc(scryfall_id)}" '
        f'onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'flex\';" '
        f'loading="lazy" decoding="async" src="{_esc(normal_url)}" />'
    )


@router.get("/{session_id}/printing-picker", response_class=HTMLResponse)
async def manual_builder_printing_picker(
    request: Request,
    session_id: str,
    name: str = Query(...),
    idx: str = Query(...),
) -> HTMLResponse:
    """Render the printing-selection grid for a pool card tile.

    Mirrors `/build/printing-picker` (see `build_permalinks.py`) but is
    session-keyed by `_manual_printings` (pool cards aren't part of an
    indexed build-wizard card list, so there's no `card_library` entry to
    bake the choice into - the selection only affects which printing's
    art/price is shown while browsing).
    """
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    name_l = str(name).strip().lower()
    selected = str((sess.get("_manual_printings") or {}).get(name_l, ""))

    from .api import _image_cache

    face_name = name.split(" // ")[0].strip() if " // " in name else name
    printings = _image_cache.get_printings(face_name)
    if not printings:
        return HTMLResponse('<div class="printing-panel-empty">No alternate printings found for this card.</div>')

    try:
        printings = sorted(printings, key=lambda p: str(p.get("released_at") or ""), reverse=True)
    except Exception:
        pass

    price_svc = get_price_service()
    post_target = f"/decks/manual/{sid}/printing"

    parts = [
        '<div class="printing-picker-header">'
        '<span class="printing-picker-title">Choose a printing</span>'
        '<button type="button" class="printing-picker-close" title="Close" '
        'onclick="this.closest(\'.printing-panel\').innerHTML=\'\';">&times;</button>'
        "</div>",
        '<div class="printing-picker-grid">'
        f'<button type="button" class="printing-option printing-option-default{" selected" if not selected else ""}" '
        f'title="Use the default printing" hx-post="{post_target}" hx-swap="none" '
        f'hx-vals=\'{{"name":"{_esc(name)}","scryfall_id":"","idx":"{_esc(idx)}"}}\'>Default</button>'
    ]
    for p in printings:
        sfid = str(p.get("scryfall_id") or "")
        if not sfid:
            continue
        set_code = str(p.get("set") or "").upper()
        set_name = str(p.get("set_name") or "")
        collector_number = str(p.get("collector_number") or "")
        label = f"{set_code} #{collector_number}".strip()
        thumb = f"/api/images/normal/{quote(face_name)}?printing={quote(sfid)}"
        is_sel = " selected" if sfid == selected else ""
        title = f"{set_name} — {label}" if set_name else label

        finishes = {str(f).lower() for f in (p.get("finishes") or [])}
        has_foil = "foil" in finishes or "etched" in finishes
        has_nonfoil = "nonfoil" in finishes or not finishes
        foil_only = has_foil and not has_nonfoil

        try:
            nonfoil_price = price_svc.get_price(face_name, scryfall_id=sfid) if has_nonfoil else None
        except Exception:
            nonfoil_price = None
        foil_price = None
        if has_foil:
            try:
                foil_price = price_svc.get_price(face_name, foil=True, scryfall_id=sfid)
            except Exception:
                foil_price = None

        price_bits = []
        if nonfoil_price is not None:
            price_bits.append(f'<span class="printing-option-price">${nonfoil_price:.2f}</span>')
        if foil_price is not None and (nonfoil_price is None or foil_price != nonfoil_price):
            price_bits.append(
                f'<span class="printing-option-price-foil" title="Foil price">&#10024; ${foil_price:.2f}</span>'
            )
        price_html = "".join(price_bits)
        foil_badge = '<span class="printing-option-foil-badge">FOIL</span>' if foil_only else ""
        parts.append(
            f'<button type="button" class="printing-option{is_sel}" title="{_esc(title)}" '
            f'hx-post="{post_target}" hx-swap="none" '
            f'hx-vals=\'{{"name":"{_esc(name)}","scryfall_id":"{_esc(sfid)}","idx":"{_esc(idx)}"}}\'>'
            f'<span class="printing-option-thumb-wrap">'
            f'<img src="{_esc(thumb)}" alt="{_esc(title)}" loading="lazy" width="110" />'
            f"{foil_badge}"
            f"</span>"
            f'<span class="printing-option-label">{_esc(label)}</span>'
            f"{price_html}"
            f"</button>"
        )
    parts.append("</div>")
    return HTMLResponse("".join(parts))


@router.post("/{session_id}/printing", response_class=HTMLResponse)
async def manual_builder_printing(
    request: Request,
    session_id: str,
    name: str = Form(...),
    scryfall_id: str = Form(""),
    idx: str = Form(...),
) -> HTMLResponse:
    """Set (or clear) the previewed printing for a pool card tile."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    name_l = str(name).strip().lower()
    scryfall_id = (scryfall_id or "").strip()
    printings = dict(sess.get("_manual_printings") or {})
    if scryfall_id:
        printings[name_l] = scryfall_id
    else:
        printings.pop(name_l, None)
    sess["_manual_printings"] = printings

    img_html = _pool_img_html(name, idx, scryfall_id, oob=True)
    is_foil = bool((sess.get("_manual_foils") or {}).get(name_l))
    price_oob = (
        f'<div id="pool-price-{_esc(idx)}" class="card-price-overlay" hx-swap-oob="true" '
        f'data-price-for="{_esc(name)}" data-printing-id="{_esc(scryfall_id)}" '
        f'data-foil="{"1" if is_foil else "0"}" aria-hidden="true"></div>'
    )
    panel_oob = '<div id="printing-modal-root" class="printing-panel" hx-swap-oob="true"></div>'
    return HTMLResponse(img_html + price_oob + panel_oob)


@router.post("/{session_id}/foil", response_class=HTMLResponse)
async def manual_builder_foil(
    request: Request,
    session_id: str,
    name: str = Form(...),
    idx: str = Form(...),
    foil: int = Form(...),
    compact: str = Form("0"),
) -> HTMLResponse:
    """Toggle the previewed foil finish for a pool card tile."""
    sid, guard = _require_manual_session(request, session_id)
    if sid is None:
        return guard
    sess = guard
    name_l = str(name).strip().lower()
    is_foil = bool(foil)
    foils = dict(sess.get("_manual_foils") or {})
    if is_foil:
        foils[name_l] = True
    else:
        foils.pop(name_l, None)
    sess["_manual_foils"] = foils

    ctx = {
        "request": request,
        "session_id": sid,
        "name": name,
        "idx": idx,
        "is_foil": is_foil,
        "compact": compact == "1",
    }
    return templates.TemplateResponse("decks/_manual_foil_button.html", ctx)

