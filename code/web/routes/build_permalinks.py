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
from ..app import ALLOW_MUST_HAVES, templates
from ..services.tasks import get_session, new_sid
from ..services import orchestrator as orch
from html import escape as _esc


router = APIRouter(prefix="/build")


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
