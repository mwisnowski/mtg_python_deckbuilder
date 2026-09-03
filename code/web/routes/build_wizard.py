"""
Build Wizard Routes - Step-by-step deck building flow.

Handles the 5-step wizard interface for deck building:
- Step 1: Commander selection
- Step 2: Theme and partner selection
- Step 3: Ideal card count targets
- Step 4: Owned card preferences and review
- Step 5: Build execution and results

Extracted from build.py as part of Phase 3 modularization (Roadmap 9 M1).
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse
from typing import Any

from ..app import templates
from ..services.build_utils import (
    step5_base_ctx,
    step5_ctx_from_result,
    step5_error_ctx,
    step5_empty_ctx,
    start_ctx_from_session,
    apply_deck_view_redirect,
    owned_set as owned_set_helper,
    builder_present_names,
    builder_display_map,
    commander_hover_context,
)
from ..services import orchestrator as orch
from ..services.tasks import get_session, new_sid
from ..services.combo_utils import detect_all as _detect_all
from .build_multicopy import _rebuild_ctx_with_multicopy

router = APIRouter()


def _user_deck_dir(request: Request) -> str:
    """Return the scoped deck export directory string for the current user."""
    import os
    from pathlib import Path
    u = getattr(getattr(request, "state", None), "current_user", None)
    uid = str(u["id"]) if (u and not u.get("is_guest") and u.get("id")) else "guest"
    base = os.getenv("DECK_EXPORTS")
    if base:
        return str((Path(base) / uid).resolve())
    return str((Path.cwd() / "deck_files" / uid).resolve())


def _merge_hx_trigger(response: Any, payload: dict[str, Any]) -> None:
    """Merge HX-Trigger header data into response."""
    if not payload or response is None:
        return
    try:
        existing = response.headers.get("HX-Trigger") if hasattr(response, "headers") else None
    except Exception:
        existing = None
    try:
        import json
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
            import json
            response.headers["HX-Trigger"] = json.dumps(payload)
        except Exception:
            pass


def _step5_summary_placeholder_html(token: int, *, message: str | None = None) -> str:
    """Generate placeholder HTML for step 5 summary panel."""
    from html import escape as _esc
    text = message or "Deck summary will appear after the build completes."
    return (
        f'<div id="deck-summary" data-summary '
        f'hx-get="/build/step5/summary?token={token}" '
        'hx-trigger="step5:refresh from:body" hx-swap="outerHTML">'
        f'<div class="muted" style="margin-top:1rem;">{_esc(text)}</div>'
        '</div>'
    )


def _current_builder_summary(sess: dict) -> Any | None:
    """Get current builder's deck summary."""
    try:
        ctx = sess.get("build_ctx") or {}
        builder = ctx.get("builder") if isinstance(ctx, dict) else None
        if builder is None:
            return None
        summary_fn = getattr(builder, "build_deck_summary", None)
        if callable(summary_fn):
            summary_data = summary_fn()
            # Also save to session for consistency
            if summary_data:
                sess["summary"] = summary_data
            return summary_data
    except Exception:
        return None
    return None


def _get_current_deck_names(sess: dict) -> list[str]:
    """Get names of cards currently in the deck."""
    try:
        ctx = sess.get("build_ctx") or {}
        b = ctx.get("builder")
        lib = getattr(b, "card_library", {}) if b is not None else {}
        names = [str(n) for n in lib.keys()]
        return sorted(dict.fromkeys(names))
    except Exception:
        return []


@router.post("/reset-all", response_class=HTMLResponse)
async def build_reset_all(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess.clear()
    resp = HTMLResponse("", status_code=200)
    resp.headers["HX-Redirect"] = "/build"
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


# ============================================================================
# Step 5: Build Execution and Results
# ============================================================================

@router.get("/step5", response_class=HTMLResponse)
async def build_step5_get(request: Request) -> HTMLResponse:
    """Display step 5 initial state (empty/ready to start build)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 5
    # Default replace-mode to ON unless explicitly toggled off
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    base = step5_empty_ctx(request, sess)
    resp = templates.TemplateResponse("build/_step5.html", base)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": base.get("summary_token", 0)}})
    return resp


@router.post("/step5/start", response_class=HTMLResponse)
async def build_step5_start(request: Request) -> HTMLResponse:
    """(Re)start the build from step 4 review page."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    if not commander:
        err_ctx = step5_error_ctx(request, sess, "Please select a commander first.", include_name=False)
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    try:
        import time as _time
        sess["build_id"] = str(int(_time.time() * 1000))
        sess["deck_dir"] = _user_deck_dir(request)
        sess["build_ctx"] = start_ctx_from_session(sess)
        show_skipped = False
        try:
            form = await request.form()
            show_skipped = True if (form.get('show_skipped') == '1') else False
        except Exception:
            pass
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=show_skipped)
        if res.get("summary"):
            sess["summary"] = res["summary"]
        status = "Stage complete" if not res.get("done") else "Build complete"
        try:
            if res.get("label") == "Multi-Copy Package" and sess.get("multi_copy"):
                mc = sess.get("multi_copy")
                sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
        except Exception:
            pass
        sess["last_step"] = 5
        ctx = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
        resp = templates.TemplateResponse("build/_step5.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": ctx.get("summary_token", 0)}})
        apply_deck_view_redirect(resp, ctx)
        return resp
    except Exception as e:
        err_ctx = step5_error_ctx(request, sess, f"Failed to start build: {e}", include_name=False)
        err_ctx["commander"] = commander
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp


@router.post("/step5/continue", response_class=HTMLResponse)
async def build_step5_continue(request: Request) -> HTMLResponse:
    """Continue to next stage of the build."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Validate commander; render an inline error if missing
    if not sess.get("commander"):
        err_ctx = step5_error_ctx(request, sess, "Please select a commander first.", include_name=False)
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    # Ensure build context exists; if not, start it first
    if not sess.get("build_ctx"):
        sess["deck_dir"] = _user_deck_dir(request)
        sess["build_ctx"] = start_ctx_from_session(sess)
    else:
        # If context exists already, rebuild ONLY when the multi-copy selection changed or hasn't been applied yet
        try:
            mc = sess.get("multi_copy") or None
            selkey = None
            if mc:
                selkey = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
            applied = sess.get("mc_applied_key") if mc else None
            if mc and (not applied or applied != selkey):
                _rebuild_ctx_with_multicopy(sess)
            # If we still have no stages (e.g., minimal test context), inject a minimal multi-copy stage inline
            try:
                ctx = sess.get("build_ctx") or {}
                stages = ctx.get("stages") if isinstance(ctx, dict) else None
                if (not stages or len(stages) == 0) and mc:
                    b = ctx.get("builder") if isinstance(ctx, dict) else None
                    if b is not None:
                        try:
                            setattr(b, "_web_multi_copy", mc)
                        except Exception:
                            pass
                        try:
                            if not isinstance(getattr(b, "card_library", None), dict):
                                b.card_library = {}
                        except Exception:
                            pass
                        try:
                            if not isinstance(getattr(b, "ideal_counts", None), dict):
                                b.ideal_counts = {}
                        except Exception:
                            pass
                        ctx["stages"] = [{"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}]
                        ctx["idx"] = 0
                        ctx["last_visible_idx"] = 0
            except Exception:
                pass
        except Exception:
            pass
    # Read show_skipped from either query or form safely
    show_skipped = True if (request.query_params.get('show_skipped') == '1') else False
    try:
        form = await request.form()
        if form and form.get('show_skipped') == '1':
            show_skipped = True
    except Exception:
        pass
    try:
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=show_skipped)
        status = "Build complete" if res.get("done") else "Stage complete"
        # Save summary to session for deck_summary partial to access
        if res.get("summary"):
            sess["summary"] = res["summary"]
        # Keep commander in session for Step 5 display (will be overwritten on next build)
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to continue: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    stage_label = res.get("label")
    # If we just applied Multi-Copy, stamp the applied key so we don't rebuild again
    try:
        if stage_label == "Multi-Copy Package" and sess.get("multi_copy"):
            mc = sess.get("multi_copy")
            sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
    except Exception:
        pass
    # Note: no redirect; the inline compliance panel will render inside Step 5
    sess["last_step"] = 5
    ctx2 = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
    resp = templates.TemplateResponse("build/_step5.html", ctx2)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": ctx2.get("summary_token", 0)}})
    apply_deck_view_redirect(resp, ctx2)
    return resp


@router.post("/step5/rerun", response_class=HTMLResponse)
async def build_step5_rerun(request: Request) -> HTMLResponse:
    """Rerun current stage with modifications."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    if not sess.get("commander"):
        err_ctx = step5_error_ctx(request, sess, "Please select a commander first.", include_name=False)
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    # Rerun requires an existing context; if missing, create it and run first stage as rerun
    if not sess.get("build_ctx"):
        sess["deck_dir"] = _user_deck_dir(request)
        sess["build_ctx"] = start_ctx_from_session(sess)
    else:
        # Ensure latest locks are reflected in the existing context
        try:
            sess["build_ctx"]["locks"] = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        except Exception:
            pass
    show_skipped = False
    try:
        form = await request.form()
        show_skipped = True if (form.get('show_skipped') == '1') else False
    except Exception:
        pass
    # If replace-mode is OFF, keep the stage visible even if no new cards were added
    if not bool(sess.get("replace_mode", True)):
        show_skipped = True
    try:
        res = orch.run_stage(sess["build_ctx"], rerun=True, show_skipped=show_skipped, replace=bool(sess.get("replace_mode", True)))
        # Save summary to session for deck_summary partial to access
        if res.get("summary"):
            sess["summary"] = res["summary"]
        status = "Stage rerun complete" if not res.get("done") else "Build complete"
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to rerun stage: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    sess["last_step"] = 5
    # Build locked cards list with ownership and in-deck presence
    locked_cards = []
    try:
        ctx = sess.get("build_ctx") or {}
        b = ctx.get("builder") if isinstance(ctx, dict) else None
        present: set[str] = builder_present_names(b) if b is not None else set()
        # Display-map via combined df when available
        lock_lower = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        display_map: dict[str, str] = builder_display_map(b, lock_lower) if b is not None else {}
        owned_lower = owned_set_helper()
        for nm in (sess.get("locks", []) or []):
            key = str(nm).strip().lower()
            disp = display_map.get(key, nm)
            locked_cards.append({
                "name": disp,
                "owned": key in owned_lower,
                "in_deck": key in present,
            })
    except Exception:
        locked_cards = []
    ctx3 = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
    ctx3["locked_cards"] = locked_cards
    resp = templates.TemplateResponse("build/_step5.html", ctx3)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": ctx3.get("summary_token", 0)}})
    apply_deck_view_redirect(resp, ctx3)
    return resp


@router.post("/step5/rewind", response_class=HTMLResponse)
async def build_step5_rewind(request: Request, to: str = Form(...)) -> HTMLResponse:
    """Rewind the staged build to a previous visible stage by index or key and show that stage.

    Param `to` can be an integer index (1-based stage index) or a stage key string.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx")
    if not ctx:
        return await build_step5_get(request)
    target_i: int | None = None
    # Resolve by numeric index first
    try:
        idx_val = int(str(to).strip())
        target_i = idx_val
    except Exception:
        target_i = None
    if target_i is None:
        # attempt by key
        key = str(to).strip()
        try:
            for h in ctx.get("history", []) or []:
                if str(h.get("key")) == key or str(h.get("label")) == key:
                    target_i = int(h.get("i"))
                    break
        except Exception:
            target_i = None
    if not target_i:
        return await build_step5_get(request)
    # Try to restore snapshot stored for that history entry
    try:
        hist = ctx.get("history", []) or []
        snap = None
        for h in hist:
            if int(h.get("i")) == int(target_i):
                snap = h.get("snapshot")
                break
        if snap is not None:
            orch._restore_builder(ctx["builder"], snap)
            ctx["idx"] = int(target_i) - 1
            ctx["last_visible_idx"] = int(target_i) - 1
    except Exception:
        # As a fallback, restart ctx and run forward until target
        sess["deck_dir"] = _user_deck_dir(request)
        sess["build_ctx"] = start_ctx_from_session(sess)
        ctx = sess["build_ctx"]
        # Run forward until reaching target
        while True:
            res = orch.run_stage(ctx, rerun=False, show_skipped=False)
            if int(res.get("idx", 0)) >= int(target_i):
                break
            if res.get("done"):
                break
    # Finally show the target stage by running it with show_skipped True to get a view
    try:
        res = orch.run_stage(ctx, rerun=False, show_skipped=True)
        status = "Stage (rewound)" if not res.get("done") else "Build complete"
        ctx_resp = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=True, extras={
            "history": ctx.get("history", []),
        })
    except Exception as e:
        sess["last_step"] = 5
        ctx_resp = step5_error_ctx(request, sess, f"Failed to rewind: {e}")
    resp = templates.TemplateResponse("build/_step5.html", ctx_resp)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": ctx_resp.get("summary_token", 0)}})
    return resp


@router.post("/step5/toggle-replace")
async def build_step5_toggle_replace(request: Request, replace: str = Form("0")):
    """Toggle replace-mode for reruns and return an updated button HTML."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    enabled = True if str(replace).strip() in ("1","true","on","yes") else False
    sess["replace_mode"] = enabled
    # Return the checkbox control snippet (same as template)
    checked = 'checked' if enabled else ''
    html = (
        '<div class="replace-toggle" role="group" aria-label="Replace toggle">'
        '<form hx-post="/build/step5/toggle-replace" hx-target="closest .replace-toggle" hx-swap="outerHTML" onsubmit="return false;" style="display:inline;">'
        f'<input type="hidden" name="replace" value="{"1" if enabled else "0"}" />'
        '<label class="muted" style="display:flex; align-items:center; gap:.35rem;">'
        f'<input type="checkbox" name="replace_chk" value="1" {checked} '
        'onchange="try{ const f=this.form; const h=f.querySelector(\'input[name=replace]\'); if(h){ h.value=this.checked?\'1\':\'0\'; } f.requestSubmit(); }catch(_){ }" />'
        'Replace stage picks'
        '</label>'
        '</form>'
        '</div>'
    )
    return HTMLResponse(html)


@router.post("/step5/reset-stage", response_class=HTMLResponse)
async def build_step5_reset_stage(request: Request) -> HTMLResponse:
    """Reset current visible stage to the pre-stage snapshot (if available) without running it."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx")
    if not ctx or not ctx.get("snapshot"):
        return await build_step5_get(request)
    try:
        orch._restore_builder(ctx["builder"], ctx["snapshot"])
    except Exception:
        return await build_step5_get(request)
    # Re-render step 5 with cleared added list
    base = step5_empty_ctx(request, sess, extras={
        "status": "Stage reset",
        "i": ctx.get("idx"),
        "n": len(ctx.get("stages", [])),
    })
    resp = templates.TemplateResponse("build/_step5.html", base)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": base.get("summary_token", 0)}})
    return resp


@router.get("/step5/summary", response_class=HTMLResponse)
async def build_step5_summary(request: Request, token: int = Query(0)) -> HTMLResponse:
    """Render deck summary panel for step 5 if build is ready."""
    sid = request.cookies.get("sid") or request.headers.get("X-Session-ID")
    if not sid:
        sid = new_sid()
    sess = get_session(sid)

    try:
        session_token = int(sess.get("step5_summary_token", 0))
    except Exception:
        session_token = 0
    try:
        requested_token = int(token)
    except Exception:
        requested_token = 0
    ready = bool(sess.get("step5_summary_ready"))
    summary_data = sess.get("step5_summary") if ready else None
    if summary_data is None and ready:
        summary_data = _current_builder_summary(sess)
        if summary_data is not None:
            try:
                sess["step5_summary"] = summary_data
            except Exception:
                pass

    synergies: list[str] = []
    try:
        raw_synergies = sess.get("step5_synergies")
        if isinstance(raw_synergies, (list, tuple, set)):
            synergies = [str(item) for item in raw_synergies if str(item).strip()]
    except Exception:
        synergies = []

    active_token = session_token if session_token >= requested_token else requested_token

    if not ready or summary_data is None:
        message = "Deck summary will appear after the build completes." if not ready else "Deck summary is not available yet. Try rerunning the current stage."
        placeholder = _step5_summary_placeholder_html(active_token, message=message)
        response = HTMLResponse(placeholder)
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
        return response

    ctx = step5_base_ctx(request, sess)
    ctx["summary"] = summary_data
    ctx["synergies"] = synergies
    ctx["summary_ready"] = True
    ctx["summary_token"] = active_token
    
    # Add commander hover context for color identity and theme tags
    hover_meta = commander_hover_context(
        commander_name=ctx.get("commander"),
        deck_tags=sess.get("tags"),
        summary=summary_data,
        combined=ctx.get("combined_commander"),
    )
    ctx.update(hover_meta)
    
    # Add hover_tags_joined for template if missing
    if "hover_tags_joined" not in ctx:
        hover_tags_source = ctx.get("deck_theme_tags") if ctx.get("deck_theme_tags") else ctx.get("commander_combined_tags")
        if hover_tags_source:
            ctx["hover_tags_joined"] = ", ".join(str(t) for t in hover_tags_source)
    
    response = templates.TemplateResponse("partials/deck_summary.html", ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


# ============================================================================
# Utility Routes
# ============================================================================

@router.get("/banner", response_class=HTMLResponse)
async def build_banner(request: Request, step: str = "", i: int | None = None, n: int | None = None) -> HTMLResponse:
    """Render dynamic wizard banner subtitle."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    tags = sess.get("tags", [])
    # Render only the inner text for the subtitle
    return templates.TemplateResponse(
        "build/_banner_subtitle.html",
        {"request": request, "commander": commander, "tags": tags, "name": sess.get("custom_export_base")},
    )


# ============================================================================
# Combo & Synergy Panel
# ============================================================================

@router.get("/combos", response_class=HTMLResponse)
async def build_combos_panel(request: Request) -> HTMLResponse:
    """Display combo and synergy detection panel."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    names = _get_current_deck_names(sess)
    if not names:
        # No active build; render nothing to avoid UI clutter
        return HTMLResponse("")

    # Preferences (persisted in session)
    policy = (sess.get("combos_policy") or "neutral").lower()
    if policy not in {"avoid", "neutral", "prefer"}:
        policy = "neutral"
    try:
        target = int(sess.get("combos_target") or 0)
    except Exception:
        target = 0
    if target < 0:
        target = 0

    # Load lists and run detection
    _det = _detect_all(names)
    combos = _det.get("combos", [])
    synergies = _det.get("synergies", [])
    combos_model = _det.get("combos_model")
    synergies_model = _det.get("synergies_model")

    # Suggestions
    suggestions: list[dict] = []
    present = {s.strip().lower() for s in names}
    suggested_names: set[str] = set()
    if combos_model is not None:
        # Prefer policy: suggest adding a missing partner to hit target count
        if policy == "prefer":
            try:
                for p in combos_model.pairs:
                    a = str(p.a).strip()
                    b = str(p.b).strip()
                    a_in = a.lower() in present
                    b_in = b.lower() in present
                    if a_in ^ b_in:  # exactly one present
                        missing = b if a_in else a
                        have = a if a_in else b
                        item = {
                            "kind": "add",
                            "have": have,
                            "name": missing,
                            "cheap_early": bool(getattr(p, "cheap_early", False)),
                            "setup_dependent": bool(getattr(p, "setup_dependent", False)),
                        }
                        key = str(missing).strip().lower()
                        if key not in present and key not in suggested_names:
                            suggestions.append(item)
                            suggested_names.add(key)
                # Rank: cheap/early first, then setup-dependent, then name
                suggestions.sort(key=lambda s: (0 if s.get("cheap_early") else 1, 0 if s.get("setup_dependent") else 1, str(s.get("name")).lower()))
                # If we still have room below target, add synergy-based suggestions
                rem = (max(0, int(target)) if target > 0 else 8) - len(suggestions)
                if rem > 0 and synergies_model is not None:
                    # lightweight tag weights to bias common engines
                    weights = {
                        "treasure": 3.0, "tokens": 2.8, "landfall": 2.6, "card draw": 2.5, "ramp": 2.3,
                        "engine": 2.2, "value": 2.1, "artifacts": 2.0, "enchantress": 2.0, "spellslinger": 1.9,
                        "counters": 1.8, "equipment matters": 1.7, "tribal": 1.6, "lifegain": 1.5, "mill": 1.4,
                        "damage": 1.3, "stax": 1.2
                    }
                    syn_sugs: list[dict] = []
                    for p in synergies_model.pairs:
                        a = str(p.a).strip()
                        b = str(p.b).strip()
                        a_in = a.lower() in present
                        b_in = b.lower() in present
                        if a_in ^ b_in:
                            missing = b if a_in else a
                            have = a if a_in else b
                            mkey = missing.strip().lower()
                            if mkey in present or mkey in suggested_names:
                                continue
                            tags = list(getattr(p, "tags", []) or [])
                            score = 1.0 + sum(weights.get(str(t).lower(), 1.0) for t in tags) / max(1, len(tags) or 1)
                            syn_sugs.append({
                                "kind": "add",
                                "have": have,
                                "name": missing,
                                "cheap_early": False,
                                "setup_dependent": False,
                                "tags": tags,
                                "_score": score,
                            })
                            suggested_names.add(mkey)
                    # rank by score desc then name
                    syn_sugs.sort(key=lambda s: (-float(s.get("_score", 0.0)), str(s.get("name")).lower()))
                    if rem > 0:
                        suggestions.extend(syn_sugs[:rem])
                # Finally trim to target or default cap
                cap = (int(target) if target > 0 else 8)
                suggestions = suggestions[:cap]
            except Exception:
                suggestions = []
        elif policy == "avoid":
            # Avoid policy: suggest cutting one piece from detected combos
            try:
                for c in combos:
                    # pick the second card as default cut to vary suggestions
                    suggestions.append({
                        "kind": "cut",
                        "name": c.b,
                        "partner": c.a,
                        "cheap_early": bool(getattr(c, "cheap_early", False)),
                        "setup_dependent": bool(getattr(c, "setup_dependent", False)),
                    })
                # Rank: cheap/early first
                suggestions.sort(key=lambda s: (0 if s.get("cheap_early") else 1, 0 if s.get("setup_dependent") else 1, str(s.get("name")).lower()))
                if target > 0:
                    suggestions = suggestions[: target]
                else:
                    suggestions = suggestions[: 8]
            except Exception:
                suggestions = []

    ctx = {
        "request": request,
        "policy": policy,
        "target": target,
        "combos": combos,
        "synergies": synergies,
        "versions": _det.get("versions", {}),
        "suggestions": suggestions,
    }
    return templates.TemplateResponse("build/_combos_panel.html", ctx)


@router.post("/combos/prefs", response_class=HTMLResponse)
async def build_combos_save_prefs(request: Request, policy: str = Form("neutral"), target: int = Form(0)) -> HTMLResponse:
    """Save combo preferences and re-render panel."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    pol = (policy or "neutral").strip().lower()
    if pol not in {"avoid", "neutral", "prefer"}:
        pol = "neutral"
    try:
        tgt = int(target)
    except Exception:
        tgt = 0
    if tgt < 0:
        tgt = 0
    sess["combos_policy"] = pol
    sess["combos_target"] = tgt
    # Re-render the panel
    return await build_combos_panel(request)
