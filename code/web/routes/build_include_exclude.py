"""
Include/Exclude card list management routes.

Handles user-defined include (must-have) and exclude (forbidden) card lists
for deck building, including the card toggle endpoint and summary rendering.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from deck_builder import builder_constants as bc
from ..app import ALLOW_MUST_HAVES, templates
from ..services.build_utils import step5_base_ctx
from ..services.tasks import get_session, new_sid
from ..services.telemetry import log_include_exclude_toggle
from .build import _merge_hx_trigger


router = APIRouter()


def _is_multi_copy_archetype(card_name: str) -> dict | None:
    """Return archetype dict if card_name exactly matches a known multi-copy archetype, else None."""
    normalized = card_name.strip().lower()
    for archetype in bc.MULTI_COPY_ARCHETYPES.values():
        if str(archetype.get("name", "")).strip().lower() == normalized:
            return archetype
    return None


def _must_have_state(sess: dict) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Extract include/exclude card lists and enforcement settings from session.

    Args:
        sess: Session dictionary containing user state

    Returns:
        Tuple of (state_dict, includes_list, excludes_list) where:
        - state_dict contains enforcement mode, fuzzy matching, and list contents
        - includes_list contains card names to include
        - excludes_list contains card names to exclude
    """
    includes = list(sess.get("include_cards") or [])
    excludes = list(sess.get("exclude_cards") or [])
    state = {
        "includes": includes,
        "excludes": excludes,
        "enforcement_mode": (sess.get("enforcement_mode") or "warn"),
        "allow_illegal": bool(sess.get("allow_illegal")),
        "fuzzy_matching": bool(sess.get("fuzzy_matching", True)),
    }
    return state, includes, excludes


def _render_include_exclude_summary(
    request: Request,
    sess: dict,
    sid: str,
    *,
    state: dict[str, Any] | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> HTMLResponse:
    """
    Render the include/exclude summary template.

    Args:
        request: FastAPI request object
        sess: Session dictionary
        sid: Session ID for cookie
        state: Optional pre-computed state dict
        includes: Optional pre-computed includes list
        excludes: Optional pre-computed excludes list

    Returns:
        HTMLResponse with rendered include/exclude summary
    """
    ctx = step5_base_ctx(request, sess, include_name=False, include_locks=False)
    if state is None or includes is None or excludes is None:
        state, includes, excludes = _must_have_state(sess)
    ctx["must_have_state"] = state
    ctx["summary"] = sess.get("step5_summary") if sess.get("step5_summary_ready") else None
    ctx["include_cards"] = includes
    ctx["exclude_cards"] = excludes
    response = templates.TemplateResponse("partials/include_exclude_summary.html", ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@router.post("/must-haves/toggle", response_class=HTMLResponse)
async def toggle_must_haves(
    request: Request,
    card_name: str = Form(...),
    list_type: str = Form(...),
    enabled: str = Form("1"),
):
    """
    Toggle a card's inclusion in the include or exclude list.

    This endpoint handles:
    - Adding/removing cards from include (must-have) lists
    - Adding/removing cards from exclude (forbidden) lists
    - Mutual exclusivity (card can't be in both lists)
    - List size limits (10 includes, 15 excludes)
    - Case-insensitive duplicate detection

    Args:
        request: FastAPI request object
        card_name: Name of the card to toggle
        list_type: Either "include" or "exclude"
        enabled: "1"/"true"/"yes"/"on" to add, anything else to remove

    Returns:
        HTMLResponse with updated include/exclude summary, or
        JSONResponse with error if validation fails

    HX-Trigger Events:
        must-haves:toggle: Payload with card, list, enabled status, and counts
    """
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Must-have lists are disabled"}, status_code=403)

    name = str(card_name or "").strip()
    if not name:
        return JSONResponse({"error": "Card name is required"}, status_code=400)

    list_key = str(list_type or "").strip().lower()
    if list_key not in {"include", "exclude"}:
        return JSONResponse({"error": "Unsupported toggle type"}, status_code=400)

    enabled_flag = str(enabled).strip().lower() in {"1", "true", "yes", "on"}

    sid = request.cookies.get("sid") or request.headers.get("X-Session-ID")
    if not sid:
        sid = new_sid()
    sess = get_session(sid)

    # R13: Multi-copy archetype conflict detection
    if enabled_flag and ALLOW_MUST_HAVES:
        archetype = _is_multi_copy_archetype(name)
        if list_key == "include" and archetype:
            ctx = {"request": request, "archetype": archetype, "card_name": name}
            resp = templates.TemplateResponse("partials/multicopy_include_dialog.html", ctx)
            resp.set_cookie("sid", sid, httponly=True, samesite="lax")
            return resp
        if list_key == "exclude":
            active_mc = sess.get("multi_copy") or {}
            if active_mc and str(active_mc.get("name", "")).strip().lower() == name.lower():
                ctx = {"request": request, "archetype": active_mc, "card_name": name}
                resp = templates.TemplateResponse("partials/multicopy_exclude_warning.html", ctx)
                resp.set_cookie("sid", sid, httponly=True, samesite="lax")
                return resp

    includes = list(sess.get("include_cards") or [])
    excludes = list(sess.get("exclude_cards") or [])
    include_lookup = {str(v).strip().lower(): str(v) for v in includes if str(v).strip()}
    exclude_lookup = {str(v).strip().lower(): str(v) for v in excludes if str(v).strip()}
    key = name.lower()
    display_name = include_lookup.get(key) or exclude_lookup.get(key) or name

    changed = False
    include_limit = 10
    exclude_limit = 15

    def _remove_casefold(items: list[str], item_key: str) -> list[str]:
        """Remove items matching the given key (case-insensitive)."""
        return [c for c in items if str(c).strip().lower() != item_key]

    if list_key == "include":
        if enabled_flag:
            if key not in include_lookup:
                if len(include_lookup) >= include_limit:
                    return JSONResponse({"error": f"Include limit reached ({include_limit})."}, status_code=400)
                includes.append(name)
                include_lookup[key] = name
                changed = True
            if key in exclude_lookup:
                excludes = _remove_casefold(excludes, key)
                exclude_lookup.pop(key, None)
                changed = True
        else:
            if key in include_lookup:
                includes = _remove_casefold(includes, key)
                include_lookup.pop(key, None)
                changed = True
    else:  # exclude
        if enabled_flag:
            if key not in exclude_lookup:
                if len(exclude_lookup) >= exclude_limit:
                    return JSONResponse({"error": f"Exclude limit reached ({exclude_limit})."}, status_code=400)
                excludes.append(name)
                exclude_lookup[key] = name
                changed = True
            if key in include_lookup:
                includes = _remove_casefold(includes, key)
                include_lookup.pop(key, None)
                changed = True
        else:
            if key in exclude_lookup:
                excludes = _remove_casefold(excludes, key)
                exclude_lookup.pop(key, None)
                changed = True

    if changed:
        sess["include_cards"] = includes
        sess["exclude_cards"] = excludes
        if "include_exclude_diagnostics" in sess:
            try:
                del sess["include_exclude_diagnostics"]
            except Exception:
                pass

    response = _render_include_exclude_summary(request, sess, sid)

    try:
        log_include_exclude_toggle(
            request,
            card_name=display_name,
            action=list_key,
            enabled=enabled_flag,
            include_count=len(includes),
            exclude_count=len(excludes),
        )
    except Exception:
        pass

    trigger_payload = {
        "card": display_name,
        "list": list_key,
        "enabled": enabled_flag,
        "include_count": len(includes),
        "exclude_count": len(excludes),
    }
    try:
        _merge_hx_trigger(response, {"must-haves:toggle": trigger_payload})
    except Exception:
        pass
    return response


@router.get("/must-haves/summary", response_class=HTMLResponse)
async def must_haves_summary(request: Request) -> HTMLResponse:
    """Return the current include/exclude summary fragment (used by dialog cancel actions)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    return _render_include_exclude_summary(request, sess, sid)


@router.get("/must-haves/multicopy-dialog", response_class=HTMLResponse)
async def multicopy_include_dialog_view(
    request: Request,
    card_name: str = Query(...),
) -> HTMLResponse:
    """Return the count-picker dialog fragment for a multi-copy archetype card."""
    archetype = _is_multi_copy_archetype(card_name)
    if not archetype:
        return HTMLResponse("", status_code=200)
    ctx = {"request": request, "archetype": archetype, "card_name": card_name}
    return templates.TemplateResponse("partials/multicopy_include_dialog.html", ctx)


@router.get("/must-haves/exclude-archetype-warning", response_class=HTMLResponse)
async def exclude_archetype_warning_view(
    request: Request,
    card_name: str = Query(...),
) -> HTMLResponse:
    """Return the warning dialog fragment for excluding the currently-active archetype."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    active_mc = sess.get("multi_copy") or {}
    ctx = {"request": request, "archetype": active_mc, "card_name": card_name}
    return templates.TemplateResponse("partials/multicopy_exclude_warning.html", ctx)


@router.post("/must-haves/save-archetype-include", response_class=HTMLResponse)
async def save_archetype_include(
    request: Request,
    card_name: str = Form(...),
    choice_id: str = Form(...),
    count: int = Form(None),
    thrumming: str | None = Form(None),
) -> HTMLResponse:
    """Save multi-copy archetype selection and add card to the must-include list.

    Combines the archetype save (multicopy/save) and include toggle into a single
    action, called from the multicopy_include_dialog when the user confirms.
    """
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Must-have lists are disabled"}, status_code=403)

    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)

    # Persist archetype selection (mirrors multicopy/save logic)
    meta = bc.MULTI_COPY_ARCHETYPES.get(str(choice_id), {})
    archetype_name = meta.get("name") or card_name.strip()
    if count is None:
        count = int(meta.get("default_count", 25))
    try:
        count = int(count)
    except Exception:
        count = int(meta.get("default_count", 25))
    printed_cap = meta.get("printed_cap")
    if isinstance(printed_cap, int) and printed_cap > 0:
        count = max(1, min(printed_cap, count))
    sess["multi_copy"] = {
        "id": str(choice_id),
        "name": archetype_name,
        "count": count,
        "thrumming": str(thrumming or "").strip().lower() in {"1", "true", "on", "yes"},
    }
    try:
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass

    # Add card to include list
    name = card_name.strip()
    key = name.lower()
    includes = list(sess.get("include_cards") or [])
    include_lookup = {str(v).strip().lower(): str(v) for v in includes}
    if key not in include_lookup:
        includes.append(name)
    # Remove from excludes if present
    excludes = [c for c in (sess.get("exclude_cards") or []) if str(c).strip().lower() != key]
    sess["include_cards"] = includes
    sess["exclude_cards"] = excludes

    return _render_include_exclude_summary(request, sess, sid)


@router.post("/must-haves/clear-archetype", response_class=HTMLResponse)
async def clear_archetype(
    request: Request,
    card_name: str | None = Form(None),
) -> HTMLResponse:
    """Clear the active multi-copy archetype and optionally add card to the exclude list.

    Called when user confirms the exclude-archetype-warning dialog.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)

    for k in ("multi_copy", "mc_applied_key", "mc_seen_keys"):
        try:
            if k in sess:
                del sess[k]
        except Exception:
            pass

    if card_name:
        name = str(card_name).strip()
        key = name.lower()
        excludes = list(sess.get("exclude_cards") or [])
        exclude_lookup = {str(v).strip().lower(): str(v) for v in excludes}
        if key not in exclude_lookup:
            excludes.append(name)
        # Remove from includes if present
        includes = [c for c in (sess.get("include_cards") or []) if str(c).strip().lower() != key]
        sess["include_cards"] = includes
        sess["exclude_cards"] = excludes

    return _render_include_exclude_summary(request, sess, sid)
