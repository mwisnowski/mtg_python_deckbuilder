"""Build Permalinks and Lock Management Routes

Phase 5 extraction from build.py:
- POST /build/lock - Card lock toggle with HTMX swap
- GET /build/permalink - State serialization (base64 JSON)
- GET /build/from - State restoration from permalink

This module handles build state persistence and card lock management.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from typing import Any
import json
import gzip
from urllib.parse import quote
from ..app import ALLOW_MUST_HAVES, templates
from ..services.tasks import get_session, new_sid
from ..services import orchestrator as orch
from .api import _image_cache
from code.deck_builder import builder_utils as bu
from html import escape as _esc


router = APIRouter(prefix="/build")


def _render_card_img_html(name: str, idx: str, scryfall_id: str, *, oob: bool = False) -> str:
    """Build the `<img class="card-thumb">` markup for a card tile.

    Always renders a single normal-resolution image with no responsive
    `srcset` -- a printing change is a deliberate user action, so we always
    want the higher-resolution art rather than letting the browser's
    responsive-image algorithm fall back to a small thumbnail candidate
    sized for the tile's on-page dimensions (which caused the low-res image
    to stick after a printing change even though it visually renders larger
    via CSS).

    For double-faced/split/flip/meld cards (`name` containing " // "), also
    re-emits the `data-front-src`/`data-back-src`/`data-current-face`
    attributes the card detail page's Transform button relies on (see
    `detail.html`), each pointed at the newly-selected printing -- otherwise
    this OOB swap would wipe those attributes and leave the back face stuck
    on the previous (default) printing's image.
    """
    display_name = name.split(" // ")[0].strip() if " // " in name else name
    q = quote(display_name)
    suffix = f"?printing={quote(scryfall_id)}" if scryfall_id else ""
    normal_url = f"/api/images/normal/{q}{suffix}"
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    dfc_attrs = ""
    if " // " in name:
        back_name = name.split(" // ")[1].strip()
        back_suffix = f"&printing={quote(scryfall_id)}" if scryfall_id else ""
        back_url = f"/api/images/normal/{quote(back_name)}?face=back{back_suffix}"
        dfc_attrs = (
            f' data-front-src="{_esc(normal_url)}" data-back-src="{_esc(back_url)}" '
            f'data-current-face="front"'
        )
    base_attrs = (
        f'class="card-thumb" id="card-img-{_esc(idx)}"{oob_attr} '
        f'alt="{_esc(name)} image" data-card-name="{_esc(name)}" '
        f'data-printing-id="{_esc(scryfall_id)}" '
        f'loading="lazy" decoding="async" data-lqip="1"{dfc_attrs}'
    )
    return f'<img {base_attrs} src="{_esc(normal_url)}" />'


def _merge_hx_trigger(response: Any, payload: dict[str, Any]) -> None:
    if not payload or response is None:
        return
    try:
        existing = response.headers.get("HX-Trigger") if hasattr(response, "headers") else None
    except Exception:
        existing = None
    try:
        if existing:
            try:
                data = json.loads(existing)
            except Exception:
                data = {}
            if isinstance(data, dict):
                data.update(payload)
                response.headers["HX-Trigger"] = json.dumps(data)
                return
        response.headers["HX-Trigger"] = json.dumps(payload)
    except Exception:
        try:
            response.headers["HX-Trigger"] = json.dumps(payload)
        except Exception:
            pass


@router.post("/lock")
async def build_lock(request: Request, name: str = Form(...), locked: int = Form(...), from_list: str = Form(None)) -> HTMLResponse:
    """Toggle card lock for a given card name (HTMX-based).

    Maintains an in-session locks set and reflects changes in the build context.
    Returns an updated HTML button with HTMX attributes for easy swapping.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    name_l = str(name).strip().lower()
    locks = set(sess.get("locks", []))
    is_locked = bool(int(locked or 0))
    if is_locked:
        locks.add(name_l)
    else:
        locks.discard(name_l)
    sess["locks"] = list(locks)
    # Update build context if it exists
    try:
        ctx = sess.get("build_ctx") or {}
        if ctx and isinstance(ctx, dict):
            ctx["locks"] = {str(x) for x in locks}
    except Exception:
        pass
    # Build lock button HTML
    if is_locked:
        label = "🔒"
        title = f"Unlock {name}"
        next_state = 0
    else:
        label = "🔓"
        title = f"Lock {name}"
        next_state = 1
    html = (
        f'<button class="btn btn-lock" type="button" title="{_esc(title)}" '
        f'hx-post="/build/lock" hx-target="this" hx-swap="outerHTML" '
        f'hx-vals=\'{{"name":"{_esc(name)}","locked":{next_state}}}\'>{label}</button>'
    )
    # OOB chip and lock count update
    lock_count = len(locks)
    chip = (
        f'<div id="locks-chip" hx-swap-oob="true">'
        f'<span class="chip">🔒 {lock_count}</span>'
        f'</div>'
    )
    # If coming from locked-cards list, remove the row on unlock
    if from_list and not is_locked:
        # Return empty content to remove the <li> parent of the button
        html = ""
    return HTMLResponse(html + chip)


@router.get("/printing-picker")
async def build_printing_picker(
    request: Request,
    name: str = Query(...),
    idx: str = Query(...),
    deck: str = Query(None),
) -> HTMLResponse:
    """Render the printing-selection grid for a single card tile (HTMX-based).

    Loads known printings from the printings index (see `ImageCache.get_printings`)
    and marks the currently selected one. Normally session-scoped (mirrors the
    lock pattern) for the build wizard; when `deck` is supplied (the saved-deck
    view, for its owner) the "currently selected" printing and each option's
    POST target instead come from/go to that deck's on-disk CSV, so the choice
    is persisted rather than living only in the session.
    Rendered as a centered modal (see `.printing-panel` CSS + base.html), with
    normal-resolution art thumbnails and each printing's price.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    name_l = str(name).strip().lower()

    deck_p = None
    if deck:
        from .decks import _deck_dir, _safe_within, _user_id
        uid = _user_id(request)
        base = _deck_dir(uid)
        candidate = (base / deck).resolve()
        if uid != "guest" and _safe_within(base, candidate) and candidate.exists() and candidate.is_file():
            deck_p = candidate

    if deck_p is not None:
        selected = bu.read_printing_overrides_from_csv(deck_p).get(name_l, "")
    else:
        selected = str((sess.get("printings") or {}).get(name_l, ""))

    face_name = name.split(" // ")[0].strip() if " // " in name else name
    printings = _image_cache.get_printings(face_name)
    if not printings:
        return HTMLResponse('<div class="printing-panel-empty">No alternate printings found for this card.</div>')

    try:
        printings = sorted(printings, key=lambda p: str(p.get("released_at") or ""), reverse=True)
    except Exception:
        pass

    from ..services.price_service import get_price_service
    price_svc = get_price_service()

    post_target = "/decks/printing" if deck_p is not None else "/build/printing"
    deck_val = f',"deck":"{_esc(deck)}"' if deck_p is not None else ""

    parts = [
        '<div class="printing-picker-header">'
        '<span class="printing-picker-title">Choose a printing</span>'
        '<button type="button" class="printing-picker-close" title="Close" '
        'onclick="this.closest(\'.printing-panel\').innerHTML=\'\';">&times;</button>'
        "</div>",
        f'<div class="printing-picker-grid">'
        f'<button type="button" class="printing-option printing-option-default{" selected" if not selected else ""}" '
        f'title="Use the default printing" hx-post="{post_target}" hx-swap="none" '
        f'hx-vals=\'{{"name":"{_esc(name)}","scryfall_id":"","idx":"{_esc(idx)}"{deck_val}}}\'>Default</button>'
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
        # Older printings index entries (or unusual Scryfall data) may have
        # an empty finishes list -- treat that as "nonfoil, unknown" rather
        # than "foil-only" so existing behavior for those is unchanged.
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
            f'hx-vals=\'{{"name":"{_esc(name)}","scryfall_id":"{_esc(sfid)}","idx":"{_esc(idx)}"{deck_val}}}\'>'
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


@router.post("/printing")
async def build_printing(
    request: Request,
    name: str = Form(...),
    scryfall_id: str = Form(""),
    idx: str = Form(...),
) -> HTMLResponse:
    """Set (or clear) the selected printing for a card.

    Persists to two places: the session-scoped `printings` map (used while
    the wizard is still open, e.g. to restore the picker's "current"
    selection), and -- if a build is in progress -- directly onto the
    matching `card_library` entry via `set_card_printing()`, so the choice
    is baked into the deck itself (CSV `ScryfallID` column / deck summary)
    at export time instead of only living in the ephemeral session.

    Returns the new `<img>` for the tile, plus OOB updates for the price
    overlay's `data-printing-id` and clearing the picker panel -- mirroring
    the lock endpoint's OOB-update pattern.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    name_l = str(name).strip().lower()
    scryfall_id = (scryfall_id or "").strip()
    printings = dict(sess.get("printings") or {})
    if scryfall_id:
        printings[name_l] = scryfall_id
    else:
        printings.pop(name_l, None)
    sess["printings"] = printings

    try:
        ctx = sess.get("build_ctx") or {}
        builder = ctx.get("builder") if isinstance(ctx, dict) else None
        if builder is not None:
            bu.set_card_printing(builder.card_library, name, scryfall_id)
    except Exception:
        pass

    img_html = _render_card_img_html(name, idx, scryfall_id, oob=True)
    is_foil = bool((sess.get("foils") or {}).get(name_l))
    price_oob = (
        f'<div id="price-overlay-{_esc(idx)}" class="card-price-overlay" hx-swap-oob="true" '
        f'data-price-for="{_esc(name)}" data-printing-id="{_esc(scryfall_id)}" '
        f'data-foil="{"1" if is_foil else "0"}" aria-hidden="true"></div>'
    )
    panel_oob = '<div id="printing-modal-root" class="printing-panel" hx-swap-oob="true"></div>'
    return HTMLResponse(img_html + price_oob + panel_oob)


@router.post("/foil")
async def build_foil(
    request: Request,
    name: str = Form(...),
    idx: str = Form(...),
    foil: int = Form(...),
    compact: str = Form("0"),
) -> HTMLResponse:
    """Toggle whether a card should use its foil price/finish (HTMX-based).

    Mirrors `/build/printing`'s persistence pattern: a session-scoped
    `foils` map (`{name_lower: True}`, restores the toggle's state while the
    wizard is still open) and, if a build is in progress, directly onto the
    matching `card_library` entry via `set_card_foil()`, so the choice is
    baked into the deck itself (CSV `Foil` column) at export time instead of
    only living in the ephemeral session.

    Returns the new toggle `<button>` (this element is the hx-target, via
    `hx-swap="outerHTML"`) plus an OOB update for the price overlay's
    `data-foil` attribute -- the existing `data-price-for`/`data-printing-id`
    on that overlay are preserved so an already-chosen printing isn't lost.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    name_l = str(name).strip().lower()
    is_foil = bool(int(foil or 0))
    foils = dict(sess.get("foils") or {})
    if is_foil:
        foils[name_l] = True
    else:
        foils.pop(name_l, None)
    sess["foils"] = foils

    try:
        ctx = sess.get("build_ctx") or {}
        builder = ctx.get("builder") if isinstance(ctx, dict) else None
        if builder is not None:
            bu.set_card_foil(builder.card_library, name, is_foil)
    except Exception:
        pass

    scryfall_id = str((sess.get("printings") or {}).get(name_l, ""))
    macros = templates.env.get_template("partials/_macros.html").module
    btn_html = macros.foil_toggle_button(name, idx, is_foil, compact == "1")
    price_oob = (
        f'<div id="price-overlay-{_esc(idx)}" class="card-price-overlay" hx-swap-oob="true" '
        f'data-price-for="{_esc(name)}" data-printing-id="{_esc(scryfall_id)}" '
        f'data-foil="{"1" if is_foil else "0"}" aria-hidden="true"></div>'
    )
    return HTMLResponse(str(btn_html) + price_oob)


@router.get("/permalink")
async def build_permalink(request: Request):
    """Return a URL-safe JSON payload representing current run config (basic)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    payload: dict[str, Any] = {
        "commander": sess.get("commander"),
        "tags": sess.get("tags", []),
        "bracket": sess.get("bracket"),
        "ideals": sess.get("ideals"),
        "locks": list(sess.get("locks", []) or []),
        "printings": dict(sess.get("printings") or {}),
        "tag_mode": sess.get("tag_mode", "AND"),
        "flags": {
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
    }
    # Include random build fields if present
    try:
        rb = sess.get("random_build")
        if isinstance(rb, dict) and rb:
            random_payload: dict[str, Any] = {}
            for key in ("seed", "theme", "constraints", "primary_theme", "secondary_theme", "tertiary_theme"):
                if rb.get(key) is not None:
                    random_payload[key] = rb.get(key)
            if isinstance(rb.get("resolved_themes"), list):
                random_payload["resolved_themes"] = list(rb.get("resolved_themes") or [])
            if isinstance(rb.get("resolved_theme_info"), dict):
                random_payload["resolved_theme_info"] = dict(rb.get("resolved_theme_info"))
            if rb.get("combo_fallback") is not None:
                random_payload["combo_fallback"] = bool(rb.get("combo_fallback"))
            if rb.get("synergy_fallback") is not None:
                random_payload["synergy_fallback"] = bool(rb.get("synergy_fallback"))
            if rb.get("fallback_reason") is not None:
                random_payload["fallback_reason"] = rb.get("fallback_reason")
            if isinstance(rb.get("requested_themes"), dict):
                requested_payload = dict(rb.get("requested_themes"))
                if "auto_fill_enabled" in requested_payload:
                    requested_payload["auto_fill_enabled"] = bool(requested_payload.get("auto_fill_enabled"))
                random_payload["requested_themes"] = requested_payload
            if rb.get("auto_fill_enabled") is not None:
                random_payload["auto_fill_enabled"] = bool(rb.get("auto_fill_enabled"))
            if rb.get("auto_fill_applied") is not None:
                random_payload["auto_fill_applied"] = bool(rb.get("auto_fill_applied"))
            auto_filled = rb.get("auto_filled_themes")
            if isinstance(auto_filled, list):
                random_payload["auto_filled_themes"] = list(auto_filled)
            display = rb.get("display_themes")
            if isinstance(display, list):
                random_payload["display_themes"] = list(display)
            if random_payload:
                payload["random"] = random_payload
    except Exception:
        pass
    # Include exclude_cards if feature is enabled and present
    if ALLOW_MUST_HAVES and sess.get("exclude_cards"):
        payload["exclude_cards"] = sess.get("exclude_cards")
    # Compress and base64 encode the JSON payload for shorter URLs
    try:
        import base64
        raw = json.dumps(payload, separators=(',', ':')).encode("utf-8")
        # Use gzip compression to significantly reduce permalink length
        compressed = gzip.compress(raw, compresslevel=9)
        token = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    except Exception:
        return JSONResponse({"error": "Failed to generate permalink"}, status_code=500)
    link = f"/build/from?state={token}"
    return JSONResponse({
        "permalink": link,
        "state": payload,
    })


@router.get("/from")
async def build_from(request: Request, state: str | None = None) -> RedirectResponse:
    """Load a run from a permalink token and redirect to main build page."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if state:
        try:
            import base64
            import json as _json
            pad = '=' * (-len(state) % 4)
            compressed = base64.urlsafe_b64decode((state + pad).encode("ascii"))
            # Decompress the state data
            raw = gzip.decompress(compressed).decode("utf-8")
            data = _json.loads(raw)
            sess["commander"] = data.get("commander")
            sess["tags"] = data.get("tags", [])
            sess["bracket"] = data.get("bracket")
            if data.get("ideals"):
                sess["ideals"] = data.get("ideals")
            sess["tag_mode"] = data.get("tag_mode", "AND")
            flags = data.get("flags") or {}
            sess["use_owned_only"] = bool(flags.get("owned_only"))
            sess["prefer_owned"] = bool(flags.get("prefer_owned"))
            sess["swap_mdfc_basics"] = bool(flags.get("swap_mdfc_basics"))
            sess["locks"] = list(data.get("locks", []))
            sess["printings"] = dict(data.get("printings") or {})
            # Optional random build rehydration
            try:
                r = data.get("random") or {}
                if r:
                    rb_payload: dict[str, Any] = {}
                    for key in ("seed", "theme", "constraints", "primary_theme", "secondary_theme", "tertiary_theme"):
                        if r.get(key) is not None:
                            rb_payload[key] = r.get(key)
                    if isinstance(r.get("resolved_themes"), list):
                        rb_payload["resolved_themes"] = list(r.get("resolved_themes") or [])
                    if isinstance(r.get("resolved_theme_info"), dict):
                        rb_payload["resolved_theme_info"] = dict(r.get("resolved_theme_info"))
                    if r.get("combo_fallback") is not None:
                        rb_payload["combo_fallback"] = bool(r.get("combo_fallback"))
                    if r.get("synergy_fallback") is not None:
                        rb_payload["synergy_fallback"] = bool(r.get("synergy_fallback"))
                    if r.get("fallback_reason") is not None:
                        rb_payload["fallback_reason"] = r.get("fallback_reason")
                    if isinstance(r.get("requested_themes"), dict):
                        requested_payload = dict(r.get("requested_themes"))
                        if "auto_fill_enabled" in requested_payload:
                            requested_payload["auto_fill_enabled"] = bool(requested_payload.get("auto_fill_enabled"))
                        rb_payload["requested_themes"] = requested_payload
                    if r.get("auto_fill_enabled") is not None:
                        rb_payload["auto_fill_enabled"] = bool(r.get("auto_fill_enabled"))
                    if r.get("auto_fill_applied") is not None:
                        rb_payload["auto_fill_applied"] = bool(r.get("auto_fill_applied"))
                    auto_filled = r.get("auto_filled_themes")
                    if isinstance(auto_filled, list):
                        rb_payload["auto_filled_themes"] = list(auto_filled)
                    display = r.get("display_themes")
                    if isinstance(display, list):
                        rb_payload["display_themes"] = list(display)
                    if "seed" in rb_payload:
                        try:
                            seed_int = int(rb_payload["seed"])
                            rb_payload["seed"] = seed_int
                            rb_payload.setdefault("recent_seeds", [seed_int])
                        except Exception:
                            rb_payload.setdefault("recent_seeds", [])
                    sess["random_build"] = rb_payload
            except Exception:
                pass
            
            # Import exclude_cards if feature is enabled and present
            if ALLOW_MUST_HAVES and data.get("exclude_cards"):
                sess["exclude_cards"] = data.get("exclude_cards")
                
            sess["last_step"] = 4
        except Exception:
            pass
    
    # Redirect to main build page which will render the proper layout
    resp = RedirectResponse(url="/build/", status_code=303)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
