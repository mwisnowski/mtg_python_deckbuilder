from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from ..services.build_utils import (
    step5_ctx_from_result,
    step5_error_ctx,
    step5_empty_ctx,
    start_ctx_from_session,
    owned_set as owned_set_helper,
    builder_present_names,
    builder_display_map,
)
from ..app import templates
from deck_builder import builder_constants as bc
from ..services import orchestrator as orch
from ..services.orchestrator import is_setup_ready as _is_setup_ready, is_setup_stale as _is_setup_stale  # type: ignore
from ..services.build_utils import owned_names as owned_names_helper
from ..services.tasks import get_session, new_sid
from html import escape as _esc
from deck_builder.builder import DeckBuilder
from deck_builder import builder_utils as bu
from ..services.combo_utils import detect_all as _detect_all
from ..services.alts_utils import get_cached as _alts_get_cached, set_cached as _alts_set_cached

router = APIRouter(prefix="/build")

# Alternatives cache moved to services/alts_utils


def _rebuild_ctx_with_multicopy(sess: dict) -> None:
    """Rebuild the staged context so Multi-Copy runs first, avoiding overfill.

    This ensures the added cards are accounted for before lands and later phases,
    which keeps totals near targets and shows the multi-copy additions ahead of basics.
    """
    try:
        if not sess or not sess.get("commander"):
            return
        # Build fresh ctx with the same options, threading multi_copy explicitly
        opts = orch.bracket_options()
        default_bracket = (opts[0]["level"] if opts else 1)
        bracket_val = sess.get("bracket")
        try:
            safe_bracket = int(bracket_val) if bracket_val is not None else default_bracket
        except Exception:
            safe_bracket = int(default_bracket)
        ideals_val = sess.get("ideals") or orch.ideal_defaults()
        use_owned = bool(sess.get("use_owned_only"))
        prefer = bool(sess.get("prefer_owned"))
        owned_names = owned_names_helper() if (use_owned or prefer) else None
        locks = list(sess.get("locks", []))
        sess["build_ctx"] = orch.start_build_ctx(
            commander=sess.get("commander"),
            tags=sess.get("tags", []),
            bracket=safe_bracket,
            ideals=ideals_val,
            tag_mode=sess.get("tag_mode", "AND"),
            use_owned_only=use_owned,
            prefer_owned=prefer,
            owned_names=owned_names,
            locks=locks,
            custom_export_base=sess.get("custom_export_base"),
            multi_copy=sess.get("multi_copy"),
            prefer_combos=bool(sess.get("prefer_combos")),
            combo_target_count=int(sess.get("combo_target_count", 2)),
            combo_balance=str(sess.get("combo_balance", "mix")),
        )
    except Exception:
        # If rebuild fails (e.g., commander not found in test), fall back to injecting
        # a minimal Multi-Copy stage on the existing builder so the UI can render additions.
        try:
            ctx = sess.get("build_ctx")
            if not isinstance(ctx, dict):
                return
            b = ctx.get("builder")
            if b is None:
                return
            # Thread selection onto the builder; runner will be resilient without full DFs
            try:
                setattr(b, "_web_multi_copy", sess.get("multi_copy") or None)
            except Exception:
                pass
            # Ensure minimal structures exist
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
            # Inject a single Multi-Copy stage
            ctx["stages"] = [{"key": "multi_copy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}]
            ctx["idx"] = 0
            ctx["last_visible_idx"] = 0
        except Exception:
            # Leave existing context untouched on unexpected failure
            pass


@router.get("/", response_class=HTMLResponse)
async def build_index(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Determine last step (fallback heuristics if not set)
    last_step = sess.get("last_step")
    if not last_step:
        if sess.get("build_ctx"):
            last_step = 5
        elif sess.get("ideals"):
            last_step = 4
        elif sess.get("bracket"):
            last_step = 3
        elif sess.get("commander"):
            last_step = 2
        else:
            last_step = 1
    resp = templates.TemplateResponse(
        "build/index.html",
        {
            "request": request,
            "sid": sid,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "name": sess.get("custom_export_base"),
            "last_step": last_step,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


# --- Multi-copy archetype suggestion modal (Web-first flow) ---

@router.get("/multicopy/check", response_class=HTMLResponse)
async def multicopy_check(request: Request) -> HTMLResponse:
    """If current commander/tags suggest a multi-copy archetype, render a choose-one modal.

    Returns empty content when not applicable to avoid flashing a modal unnecessarily.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = str(sess.get("commander") or "").strip()
    tags = list(sess.get("tags") or [])
    if not commander:
        return HTMLResponse("")
    # Avoid re-prompting repeatedly for the same selection context
    key = commander + "||" + ",".join(sorted([str(t).strip().lower() for t in tags if str(t).strip()]))
    seen = set(sess.get("mc_seen_keys", []) or [])
    if key in seen:
        return HTMLResponse("")
    # Build a light DeckBuilder seeded with commander + tags (no heavy data load required)
    try:
        tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
        df = tmp.load_commander_data()
        row = df[df["name"].astype(str) == commander]
        if row.empty:
            return HTMLResponse("")
        tmp._apply_commander_selection(row.iloc[0])
        tmp.selected_tags = list(tags or [])
        try:
            tmp.primary_tag = tmp.selected_tags[0] if len(tmp.selected_tags) > 0 else None
            tmp.secondary_tag = tmp.selected_tags[1] if len(tmp.selected_tags) > 1 else None
            tmp.tertiary_tag = tmp.selected_tags[2] if len(tmp.selected_tags) > 2 else None
        except Exception:
            pass
        # Establish color identity from the selected commander
        try:
            tmp.determine_color_identity()
        except Exception:
            pass
        # Detect viable archetypes
        results = bu.detect_viable_multi_copy_archetypes(tmp) or []
        if not results:
            # Remember this key to avoid re-checking until tags/commander change
            try:
                seen.add(key)
                sess["mc_seen_keys"] = list(seen)
            except Exception:
                pass
            return HTMLResponse("")
        # Render modal template with top N (cap small for UX)
        items = results[:5]
        ctx = {
            "request": request,
            "items": items,
            "commander": commander,
            "tags": tags,
        }
        return templates.TemplateResponse("build/_multi_copy_modal.html", ctx)
    except Exception:
        return HTMLResponse("")


@router.post("/multicopy/save", response_class=HTMLResponse)
async def multicopy_save(
    request: Request,
    choice_id: str = Form(None),
    count: int = Form(None),
    thrumming: str | None = Form(None),
    skip: str | None = Form(None),
) -> HTMLResponse:
    """Persist user selection (or skip) for multi-copy archetype in session and close modal.

    Returns a tiny confirmation chip via OOB swap (optional) and removes the modal.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = str(sess.get("commander") or "").strip()
    tags = list(sess.get("tags") or [])
    key = commander + "||" + ",".join(sorted([str(t).strip().lower() for t in tags if str(t).strip()]))
    # Update seen set to avoid re-prompt next load
    seen = set(sess.get("mc_seen_keys", []) or [])
    seen.add(key)
    sess["mc_seen_keys"] = list(seen)
    # Handle skip explicitly
    if skip and str(skip).strip() in ("1","true","on","yes"):
        # Clear any prior choice for this run
        try:
            if sess.get("multi_copy"):
                del sess["multi_copy"]
            if sess.get("mc_applied_key"):
                del sess["mc_applied_key"]
        except Exception:
            pass
        # Return nothing (modal will be removed client-side)
        # Also emit an OOB chip indicating skip
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            '<span class="chip" title="Click to dismiss">Dismissed multi-copy suggestions</span>'
            '</div>'
        )
        return HTMLResponse(chip)
    # Persist selection when provided
    payload = None
    try:
        meta = bc.MULTI_COPY_ARCHETYPES.get(str(choice_id), {})
        name = meta.get("name") or str(choice_id)
        printed_cap = meta.get("printed_cap")
        # Coerce count with bounds: default -> rec_window[0], cap by printed_cap when present
        if count is None:
            count = int(meta.get("default_count", 25))
        try:
            count = int(count)
        except Exception:
            count = int(meta.get("default_count", 25))
        if isinstance(printed_cap, int) and printed_cap > 0:
            count = max(1, min(printed_cap, count))
        payload = {
            "id": str(choice_id),
            "name": name,
            "count": int(count),
            "thrumming": True if (thrumming and str(thrumming).strip() in ("1","true","on","yes")) else False,
        }
        sess["multi_copy"] = payload
        # Mark as not yet applied so the next build start/continue can account for it once
        try:
            if sess.get("mc_applied_key"):
                del sess["mc_applied_key"]
        except Exception:
            pass
        # If there's an active build context, rebuild it so Multi-Copy runs first
        if sess.get("build_ctx"):
            _rebuild_ctx_with_multicopy(sess)
    except Exception:
        payload = None
    # Return OOB chip summarizing the selection
    if payload:
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            f'<span class="chip" title="Click to dismiss">Selected multi-copy: '
            f"<strong>{_esc(payload.get('name',''))}</strong> x{int(payload.get('count',0))}"
            f"{' + Thrumming Stone' if payload.get('thrumming') else ''}</span>"
            '</div>'
        )
    else:
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            '<span class="chip" title="Click to dismiss">Saved</span>'
            '</div>'
        )
    return HTMLResponse(chip)




# Unified "New Deck" modal (steps 1–3 condensed)
@router.get("/new", response_class=HTMLResponse)
async def build_new_modal(request: Request) -> HTMLResponse:
    """Return the New Deck modal content (for an overlay)."""
    sid = request.cookies.get("sid") or new_sid()
    ctx = {
        "request": request,
        "brackets": orch.bracket_options(),
        "labels": orch.ideal_labels(),
        "defaults": orch.ideal_defaults(),
    }
    resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/new/candidates", response_class=HTMLResponse)
async def build_new_candidates(request: Request, commander: str = Query("")) -> HTMLResponse:
    """Return a small list of commander candidates for the modal live search."""
    q = (commander or "").strip()
    items = orch.commander_candidates(q, limit=8) if q else []
    ctx = {"request": request, "query": q, "candidates": items}
    return templates.TemplateResponse("build/_new_deck_candidates.html", ctx)


@router.get("/new/inspect", response_class=HTMLResponse)
async def build_new_inspect(request: Request, name: str = Query(...)) -> HTMLResponse:
    """When a candidate is chosen in the modal, show the commander preview and tag chips (OOB updates)."""
    info = orch.commander_select(name)
    if not info.get("ok"):
        return HTMLResponse(f'<div class="muted">Commander not found: {name}</div>')
    tags = orch.tags_for_commander(info["name"]) or []
    recommended = orch.recommended_tags_for_commander(info["name"]) if tags else []
    recommended_reasons = orch.recommended_tag_reasons_for_commander(info["name"]) if tags else {}
    # Render tags slot content and OOB commander preview simultaneously
    ctx = {
        "request": request,
        "commander": {"name": info["name"]},
        "tags": tags,
        "recommended": recommended,
        "recommended_reasons": recommended_reasons,
    }
    return templates.TemplateResponse("build/_new_deck_tags.html", ctx)


@router.post("/new", response_class=HTMLResponse)
async def build_new_submit(
    request: Request,
    name: str = Form("") ,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    bracket: int = Form(...),
    ramp: int = Form(None),
    lands: int = Form(None),
    basic_lands: int = Form(None),
    creatures: int = Form(None),
    removal: int = Form(None),
    wipes: int = Form(None),
    card_advantage: int = Form(None),
    protection: int = Form(None),
    prefer_combos: bool = Form(False),
    combo_count: int | None = Form(None),
    combo_balance: str | None = Form(None),
) -> HTMLResponse:
    """Handle New Deck modal submit and immediately start the build (skip separate review page)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Normalize and validate commander selection (best-effort via orchestrator)
    sel = orch.commander_select(commander)
    if not sel.get("ok"):
        # Re-render modal with error
        ctx = {
            "request": request,
            "error": sel.get("error", "Commander not found"),
            "brackets": orch.bracket_options(),
            "labels": orch.ideal_labels(),
            "defaults": orch.ideal_defaults(),
            "form": {
                "name": name,
                "commander": commander,
                "primary_tag": primary_tag or "",
                "secondary_tag": secondary_tag or "",
                "tertiary_tag": tertiary_tag or "",
                "tag_mode": tag_mode or "AND",
                "bracket": bracket,
                "combo_count": combo_count,
                "combo_balance": (combo_balance or "mix"),
                "prefer_combos": bool(prefer_combos),
            }
        }
        resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Save to session
    sess["commander"] = sel.get("name") or commander
    tags = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    # If commander has a tag list and primary missing, set first recommended as default
    if not tags:
        try:
            rec = orch.recommended_tags_for_commander(sess["commander"]) or []
            if rec:
                tags = [rec[0]]
        except Exception:
            pass
    sess["tags"] = tags
    sess["tag_mode"] = (tag_mode or "AND").upper()
    try:
        # Default to bracket 3 (Upgraded) when not provided
        sess["bracket"] = int(bracket) if (bracket is not None) else 3
    except Exception:
        try:
            sess["bracket"] = int(bracket)
        except Exception:
            sess["bracket"] = 3
    # Ideals: use provided values if any, else defaults
    ideals = orch.ideal_defaults()
    overrides = {k: v for k, v in {
        "ramp": ramp,
        "lands": lands,
        "basic_lands": basic_lands,
        "creatures": creatures,
        "removal": removal,
        "wipes": wipes,
        "card_advantage": card_advantage,
        "protection": protection,
    }.items() if v is not None}
    for k, v in overrides.items():
        try:
            ideals[k] = int(v)
        except Exception:
            pass
    sess["ideals"] = ideals
    # Persist preferences
    try:
        sess["prefer_combos"] = bool(prefer_combos)
    except Exception:
        sess["prefer_combos"] = False
    # Combos config from modal
    try:
        if combo_count is not None:
            sess["combo_target_count"] = max(0, min(10, int(combo_count)))
    except Exception:
        pass
    try:
        if combo_balance:
            bval = str(combo_balance).strip().lower()
            if bval in ("early","late","mix"):
                sess["combo_balance"] = bval
    except Exception:
        pass
    # Clear any old staged build context
    for k in ["build_ctx", "locks", "replace_mode"]:
        if k in sess:
            try:
                del sess[k]
            except Exception:
                pass
    # Reset multi-copy suggestion debounce and selection for a fresh run
    for k in ["mc_seen_keys", "multi_copy"]:
        if k in sess:
            try:
                del sess[k]
            except Exception:
                pass
    # Persist optional custom export base name
    if isinstance(name, str) and name.strip():
        sess["custom_export_base"] = name.strip()
    else:
        if "custom_export_base" in sess:
            try:
                del sess["custom_export_base"]
            except Exception:
                pass
    # If setup/tagging is not ready or stale, show a modal prompt instead of auto-running.
    try:
        if not _is_setup_ready():
            return templates.TemplateResponse(
                "build/_setup_prompt_modal.html",
                {
                    "request": request,
                    "title": "Setup required",
                    "message": "The card database and tags need to be prepared before building a deck.",
                    "action_url": "/setup/running?start=1&next=/build",
                    "action_label": "Run Setup",
                },
            )
        if _is_setup_stale():
            return templates.TemplateResponse(
                "build/_setup_prompt_modal.html",
                {
                    "request": request,
                    "title": "Data refresh recommended",
                    "message": "Your card database is stale. Refreshing ensures up-to-date results.",
                    "action_url": "/setup/running?start=1&force=1&next=/build",
                    "action_label": "Refresh Now",
                },
            )
    except Exception:
        # If readiness check fails, continue and let downstream handling surface errors
        pass
    # Immediately initialize a build context and run the first stage, like hitting Build Deck on review
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Centralized staged context creation
    sess["build_ctx"] = start_ctx_from_session(sess)
    res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=False)
    status = "Build complete" if res.get("done") else "Stage complete"
    sess["last_step"] = 5
    ctx = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=False)
    resp = templates.TemplateResponse("build/_step5.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step1", response_class=HTMLResponse)
async def build_step1(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1", response_class=HTMLResponse)
async def build_step1_search(
    request: Request,
    query: str = Form(""),
    auto: str | None = Form(None),
    active: str | None = Form(None),
) -> HTMLResponse:
    query = (query or "").strip()
    auto_enabled = True if (auto == "1") else False
    candidates = []
    if query:
        candidates = orch.commander_candidates(query, limit=10)
        # Optional auto-select at a stricter threshold
        if auto_enabled and candidates and len(candidates[0]) >= 2 and int(candidates[0][1]) >= 98:
            top_name = candidates[0][0]
            res = orch.commander_select(top_name)
            if res.get("ok"):
                sid = request.cookies.get("sid") or new_sid()
                sess = get_session(sid)
                sess["last_step"] = 2
                resp = templates.TemplateResponse(
                    "build/_step2.html",
                    {
                        "request": request,
                        "commander": res,
                        "tags": orch.tags_for_commander(res["name"]),
                        "recommended": orch.recommended_tags_for_commander(res["name"]),
                        "recommended_reasons": orch.recommended_tag_reasons_for_commander(res["name"]),
                        "brackets": orch.bracket_options(),
                        "clear_persisted": True,
                    },
                )
                resp.set_cookie("sid", sid, httponly=True, samesite="lax")
                return resp
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    resp = templates.TemplateResponse(
        "build/_step1.html",
        {
            "request": request,
            "query": query,
            "candidates": candidates,
            "auto": auto_enabled,
            "active": active,
            "count": len(candidates) if candidates else 0,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1/inspect", response_class=HTMLResponse)
async def build_step1_inspect(request: Request, name: str = Form(...)) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    info = orch.commander_inspect(name)
    resp = templates.TemplateResponse(
        "build/_step1.html",
        {"request": request, "inspect": info, "selected": name, "tags": orch.tags_for_commander(name)},
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1/confirm", response_class=HTMLResponse)
async def build_step1_confirm(request: Request, name: str = Form(...)) -> HTMLResponse:
    res = orch.commander_select(name)
    if not res.get("ok"):
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        sess["last_step"] = 1
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "error": res.get("error"), "selected": name})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Proceed to step2 placeholder and reset any prior build/session selections
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Reset sticky selections from previous runs
    for k in ["tags", "ideals", "bracket", "build_ctx", "last_step", "tag_mode", "mc_seen_keys", "multi_copy"]:
        try:
            if k in sess:
                del sess[k]
        except Exception:
            pass
    sess["last_step"] = 2
    resp = templates.TemplateResponse(
        "build/_step2.html",
        {
            "request": request,
            "commander": res,
            "tags": orch.tags_for_commander(res["name"]),
            "recommended": orch.recommended_tags_for_commander(res["name"]),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(res["name"]),
            "brackets": orch.bracket_options(),
            # Signal that this navigation came from a fresh commander confirmation,
            # so the Step 2 UI should clear any localStorage theme persistence.
            "clear_persisted": True,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/reset-all", response_class=HTMLResponse)
async def build_reset_all(request: Request) -> HTMLResponse:
    """Clear all build-related session state and return Step 1."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    keys = [
        "commander","tags","tag_mode","bracket","ideals","build_ctx","last_step",
        "locks","replace_mode"
    ]
    for k in keys:
        try:
            if k in sess:
                del sess[k]
        except Exception:
            pass
    sess["last_step"] = 1
    resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
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
            orch._restore_builder(ctx["builder"], snap)  # type: ignore[attr-defined]
            ctx["idx"] = int(target_i) - 1
            ctx["last_visible_idx"] = int(target_i) - 1
    except Exception:
        # As a fallback, restart ctx and run forward until target
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
    return resp


@router.get("/step2", response_class=HTMLResponse)
async def build_step2_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 2
    commander = sess.get("commander")
    if not commander:
        # Fallback to step1 if no commander in session
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    tags = orch.tags_for_commander(commander)
    selected = sess.get("tags", [])
    resp = templates.TemplateResponse(
        "build/_step2.html",
        {
            "request": request,
            "commander": {"name": commander},
            "tags": tags,
            "recommended": orch.recommended_tags_for_commander(commander),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
            "brackets": orch.bracket_options(),
            "primary_tag": selected[0] if len(selected) > 0 else "",
            "secondary_tag": selected[1] if len(selected) > 1 else "",
            "tertiary_tag": selected[2] if len(selected) > 2 else "",
            "selected_bracket": sess.get("bracket"),
            "tag_mode": sess.get("tag_mode", "AND"),
            # If there are no server-side tags for this commander, let the client clear any persisted ones
            # to avoid themes sticking between fresh runs.
            "clear_persisted": False if selected else True,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step2", response_class=HTMLResponse)
async def build_step2_submit(
    request: Request,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    bracket: int = Form(...),
) -> HTMLResponse:
    # Validate primary tag selection if tags are available
    available_tags = orch.tags_for_commander(commander)
    if available_tags and not (primary_tag and primary_tag.strip()):
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        sess["last_step"] = 2
        resp = templates.TemplateResponse(
            "build/_step2.html",
            {
                "request": request,
                "commander": {"name": commander},
                "tags": available_tags,
                "recommended": orch.recommended_tags_for_commander(commander),
                "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
                "brackets": orch.bracket_options(),
                "error": "Please choose a primary theme.",
                "primary_tag": primary_tag or "",
                "secondary_tag": secondary_tag or "",
                "tertiary_tag": tertiary_tag or "",
                "selected_bracket": int(bracket) if bracket is not None else None,
                "tag_mode": (tag_mode or "AND"),
            },
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    # Save selection to session (basic MVP; real build will use this later)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["commander"] = commander
    sess["tags"] = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    sess["tag_mode"] = (tag_mode or "AND").upper()
    sess["bracket"] = int(bracket)
    # Clear multi-copy seen/selection to re-evaluate on Step 3
    try:
        if "mc_seen_keys" in sess:
            del sess["mc_seen_keys"]
        if "multi_copy" in sess:
            del sess["multi_copy"]
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass
    # Proceed to Step 3 placeholder for now
    sess["last_step"] = 3
    resp = templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "commander": commander,
            "tags": sess["tags"],
            "bracket": sess["bracket"],
            "defaults": orch.ideal_defaults(),
            "labels": orch.ideal_labels(),
            "values": orch.ideal_defaults(),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step3", response_class=HTMLResponse)
async def build_step3_submit(
    request: Request,
    ramp: int = Form(...),
    lands: int = Form(...),
    basic_lands: int = Form(...),
    creatures: int = Form(...),
    removal: int = Form(...),
    wipes: int = Form(...),
    card_advantage: int = Form(...),
    protection: int = Form(...),
) -> HTMLResponse:
    labels = orch.ideal_labels()
    submitted = {
        "ramp": ramp,
        "lands": lands,
        "basic_lands": basic_lands,
        "creatures": creatures,
        "removal": removal,
        "wipes": wipes,
        "card_advantage": card_advantage,
        "protection": protection,
    }

    errors: list[str] = []
    for k, v in submitted.items():
        try:
            iv = int(v)
        except Exception:
            errors.append(f"{labels.get(k, k)} must be a number.")
            continue
        if iv < 0:
            errors.append(f"{labels.get(k, k)} cannot be negative.")
        submitted[k] = iv
    # Cross-field validation: basic lands should not exceed total lands
    if isinstance(submitted.get("basic_lands"), int) and isinstance(submitted.get("lands"), int):
        if submitted["basic_lands"] > submitted["lands"]:
            errors.append("Basic Lands cannot exceed Total Lands.")

    if errors:
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        sess["last_step"] = 3
        resp = templates.TemplateResponse(
            "build/_step3.html",
            {
                "request": request,
                "defaults": orch.ideal_defaults(),
                "labels": labels,
                "values": submitted,
                "error": " ".join(errors),
                "commander": sess.get("commander"),
                "tags": sess.get("tags", []),
                "bracket": sess.get("bracket"),
            },
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    # Save to session
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["ideals"] = submitted
    # Any change to ideals should clear the applied marker, we may want to re-stage
    try:
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass

    # Proceed to review (Step 4)
    sess["last_step"] = 4
    resp = templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": submitted,
            "commander": sess.get("commander"),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step3", response_class=HTMLResponse)
async def build_step3_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 3
    defaults = orch.ideal_defaults()
    values = sess.get("ideals") or defaults
    resp = templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "defaults": defaults,
            "labels": orch.ideal_labels(),
            "values": values,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step4", response_class=HTMLResponse)
async def build_step4_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 4
    labels = orch.ideal_labels()
    values = sess.get("ideals") or orch.ideal_defaults()
    commander = sess.get("commander")
    return templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": values,
            "commander": commander,
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
        },
    )


# --- Combos & Synergies panel (M3) ---
def _get_current_deck_names(sess: dict) -> list[str]:
    try:
        ctx = sess.get("build_ctx") or {}
        b = ctx.get("builder")
        lib = getattr(b, "card_library", {}) if b is not None else {}
        names = [str(n) for n in lib.keys()]
        return sorted(dict.fromkeys(names))
    except Exception:
        return []


@router.get("/combos", response_class=HTMLResponse)
async def build_combos_panel(request: Request) -> HTMLResponse:
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
                        "counters": 1.8, "equipment": 1.7, "tribal": 1.6, "lifegain": 1.5, "mill": 1.4,
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


@router.post("/toggle-owned-review", response_class=HTMLResponse)
async def build_toggle_owned_review(
    request: Request,
    use_owned_only: str | None = Form(None),
    prefer_owned: str | None = Form(None),
) -> HTMLResponse:
    """Toggle 'use owned only' and/or 'prefer owned' flags from the Review step and re-render Step 4."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 4
    only_val = True if (use_owned_only and str(use_owned_only).strip() in ("1","true","on","yes")) else False
    pref_val = True if (prefer_owned and str(prefer_owned).strip() in ("1","true","on","yes")) else False
    sess["use_owned_only"] = only_val
    sess["prefer_owned"] = pref_val
    # Do not touch build_ctx here; user hasn't started the build yet from review
    labels = orch.ideal_labels()
    values = sess.get("ideals") or orch.ideal_defaults()
    commander = sess.get("commander")
    resp = templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": values,
            "commander": commander,
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step5", response_class=HTMLResponse)
async def build_step5_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 5
    # Default replace-mode to ON unless explicitly toggled off
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    base = step5_empty_ctx(request, sess)
    resp = templates.TemplateResponse("build/_step5.html", base)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
    
@router.post("/step5/continue", response_class=HTMLResponse)
async def build_step5_continue(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Validate commander; redirect to step1 if missing
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Ensure build context exists; if not, start it first
    if not sess.get("build_ctx"):
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
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to continue: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    stage_label = res.get("label")
    # If we just applied Multi-Copy, stamp the applied key so we don't rebuild again
    try:
        if stage_label == "Multi-Copy Package" and sess.get("multi_copy"):
            mc = sess.get("multi_copy")
            sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
    except Exception:
        pass
    sess["last_step"] = 5
    ctx2 = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
    resp = templates.TemplateResponse("build/_step5.html", ctx2)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/step5/rerun", response_class=HTMLResponse)
async def build_step5_rerun(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Rerun requires an existing context; if missing, create it and run first stage as rerun
    if not sess.get("build_ctx"):
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
        status = "Stage rerun complete" if not res.get("done") else "Build complete"
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to rerun stage: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
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
    return resp


@router.post("/step5/start", response_class=HTMLResponse)
async def build_step5_start(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Validate commander exists before starting
    commander = sess.get("commander")
    if not commander:
        resp = templates.TemplateResponse(
            "build/_step1.html",
            {"request": request, "candidates": [], "error": "Please select a commander first."},
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    try:
        # Initialize step-by-step build context and run first stage
        sess["build_ctx"] = start_ctx_from_session(sess)
        show_skipped = False
        try:
            form = await request.form()
            show_skipped = True if (form.get('show_skipped') == '1') else False
        except Exception:
            pass
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=show_skipped)
        status = "Stage complete" if not res.get("done") else "Build complete"
        # If Multi-Copy ran first, mark applied to prevent redundant rebuilds on Continue
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
        return resp
    except Exception as e:
        # Surface a friendly error on the step 5 screen with normalized context
        err_ctx = step5_error_ctx(
            request,
            sess,
            f"Failed to start build: {e}",
            include_name=False,
        )
        # Ensure commander stays visible if set
        err_ctx["commander"] = commander
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

@router.get("/step5/start", response_class=HTMLResponse)
async def build_step5_start_get(request: Request) -> HTMLResponse:
    # Allow GET as a fallback to start the build (delegates to POST handler)
    return await build_step5_start(request)


@router.get("/banner", response_class=HTMLResponse)
async def build_banner(request: Request, step: str = "", i: int | None = None, n: int | None = None) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    tags = sess.get("tags", [])
    # Render only the inner text for the subtitle
    return templates.TemplateResponse(
        "build/_banner_subtitle.html",
        {"request": request, "commander": commander, "tags": tags, "name": sess.get("custom_export_base")},
    )


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
        orch._restore_builder(ctx["builder"], ctx["snapshot"])  # type: ignore[attr-defined]
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
    return resp

# --- Phase 8: Lock/Replace/Compare/Permalink minimal API ---

@router.post("/lock")
async def build_lock_toggle(request: Request, name: str = Form(...), locked: str = Form("1"), from_list: str | None = Form(None)):
    """Toggle lock for a card name in the current session; return an HTML button to swap in-place."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    locks = set(sess.get("locks", []))
    key = str(name).strip().lower()
    want_lock = True if str(locked).strip() in ("1","true","on","yes") else False
    if want_lock:
        locks.add(key)
    else:
        locks.discard(key)
    sess["locks"] = list(locks)
    # If a build context exists, update it too
    if sess.get("build_ctx"):
        try:
            sess["build_ctx"]["locks"] = {str(n) for n in locks}
        except Exception:
            pass
    # Return a compact button HTML that flips state on next click, and an OOB last-action chip
    next_state = "0" if want_lock else "1"
    label = "Unlock" if want_lock else "Lock"
    title = ("Click to unlock" if want_lock else "Click to lock")
    icon = ("🔒" if want_lock else "🔓")
    # Include data-locked to reflect the current state for client-side handler
    btn = f'''<button type="button" class="btn-lock" title="{title}" data-locked="{'1' if want_lock else '0'}"
                 hx-post="/build/lock" hx-target="closest .lock-box" hx-swap="innerHTML"
                 hx-vals='{{"name": "{name}", "locked": "{next_state}"}}'>{icon} {label}</button>'''
    # Compute locks count for chip
    locks_count = len(locks)
    if locks_count > 0:
        chip_html = f'<span id="locks-chip" hx-swap-oob="true"><span class="chip" title="Locked cards">🔒 {locks_count} locked</span></span>'
    else:
        chip_html = '<span id="locks-chip" hx-swap-oob="true"></span>'
    # Last action chip for feedback (use hx-swap-oob)
    try:
        disp = (name or '').strip()
    except Exception:
        disp = str(name)
    action = "Locked" if want_lock else "Unlocked"
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">{action} <strong>{disp}</strong></span>'
        f'</div>'
    )
    # If this request came from the locked-cards list and it's an unlock, remove the row inline
    try:
        if (from_list is not None) and (not want_lock):
            # Also update the locks-count chip, and if no locks remain, remove the whole section
            extra = chip_html
            if locks_count == 0:
                extra += '<details id="locked-section" hx-swap-oob="true"></details>'
            # Return empty body to delete the <li> via hx-swap=outerHTML, plus OOB updates
            return HTMLResponse('' + extra)
    except Exception:
        pass
    return HTMLResponse(btn + chip + chip_html)


@router.get("/alternatives", response_class=HTMLResponse)
async def build_alternatives(request: Request, name: str, stage: str | None = None, owned_only: int = Query(0)) -> HTMLResponse:
    """Suggest alternative cards for a given card name using tag overlap and availability.

    Returns a small HTML snippet listing up to ~10 alternatives with Replace buttons.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b = ctx.get("builder") if isinstance(ctx, dict) else None
    # Owned library
    owned_set = owned_set_helper()
    require_owned = bool(int(owned_only or 0)) or bool(sess.get("use_owned_only"))
    # If builder context missing, show a guidance message
    if not b:
        html = '<div class="alts"><div class="muted">Start the build to see alternatives.</div></div>'
        return HTMLResponse(html)
    try:
        name_l = str(name).strip().lower()
        commander_l = str((sess.get("commander") or "")).strip().lower()
        locked_set = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        # Check cache: key = (seed, commander, require_owned)
        cache_key = (name_l, commander_l, require_owned)
        cached = _alts_get_cached(cache_key)
        if cached is not None:
            return HTMLResponse(cached)
        # Tags index provides quick similarity candidates
        tags_idx = getattr(b, "_card_name_tags_index", {}) or {}
        seed_tags = set(tags_idx.get(name_l) or [])
        # Fallback: use the card's role/sub-role from current library if available
        lib = getattr(b, "card_library", {}) or {}
        lib_entry = lib.get(name) or lib.get(name_l)
        # Best-effort set of names currently in the deck to avoid duplicates
        in_deck: set[str] = builder_present_names(b)
        # Build candidate pool from tags overlap
        all_names = set(tags_idx.keys())
        candidates: list[tuple[str, int]] = []  # (name, score)
        for nm in all_names:
            if nm == name_l:
                continue
            # Exclude commander and any names we believe are already in the current deck
            if commander_l and nm == commander_l:
                continue
            if in_deck and nm in in_deck:
                continue
            # Also exclude any card currently locked (these are intended to be kept)
            if locked_set and nm in locked_set:
                continue
            tgs = set(tags_idx.get(nm) or [])
            score = len(seed_tags & tgs)
            if score <= 0:
                continue
            candidates.append((nm, score))
        # If no tag-based candidates, try using same trigger tag if present
        if not candidates and isinstance(lib_entry, dict):
            try:
                trig = str(lib_entry.get("TriggerTag") or "").strip().lower()
            except Exception:
                trig = ""
            if trig:
                for nm, tglist in tags_idx.items():
                    if nm == name_l:
                        continue
                    if nm in {str(k).strip().lower() for k in lib.keys()}:
                        continue
                    if trig in {str(t).strip().lower() for t in (tglist or [])}:
                        candidates.append((nm, 1))
        # Sort by score desc, then owned-first, then name asc
        def _owned(nm: str) -> bool:
            return nm in owned_set
        candidates.sort(key=lambda x: (-x[1], 0 if _owned(x[0]) else 1, x[0]))
        # Map back to display names using combined DF when possible for proper casing
        pool_lower = {nm for (nm, _s) in candidates}
        display_map: dict[str, str] = builder_display_map(b, pool_lower)
        # Build structured items for the partial
        items: list[dict] = []
        seen = set()
        for nm, score in candidates:
            if nm in seen:
                continue
            seen.add(nm)
            is_owned = (nm in owned_set)
            if require_owned and not is_owned:
                continue
            disp = display_map.get(nm, nm)
            items.append({
                "name": disp,
                "name_lower": nm,
                "owned": is_owned,
                "tags": list(tags_idx.get(nm) or []),
            })
            if len(items) >= 10:
                break
        # Render partial via Jinja template and cache it
        ctx2 = {"request": request, "name": name, "require_owned": require_owned, "items": items}
        html_str = templates.get_template("build/_alternatives.html").render(ctx2)
        _alts_set_cached(cache_key, html_str)
        return HTMLResponse(html_str)
    except Exception as e:
        return HTMLResponse(f'<div class="alts"><div class="muted">No alternatives: {e}</div></div>')


@router.post("/replace", response_class=HTMLResponse)
async def build_replace(request: Request, old: str = Form(...), new: str = Form(...)) -> HTMLResponse:
    """Update locks to prefer `new` over `old` and prompt the user to rerun the stage with Replace enabled.

    This does not immediately mutate the builder; users should click Rerun Stage (Replace: On) to apply.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    locks = set(sess.get("locks", []))
    o = str(old).strip().lower()
    n = str(new).strip().lower()
    # Always ensure new is locked and old is unlocked
    locks.discard(o)
    locks.add(n)
    sess["locks"] = list(locks)
    # Track last replace for optional undo
    try:
        sess["last_replace"] = {"old": o, "new": n}
    except Exception:
        pass
    if sess.get("build_ctx"):
        try:
            sess["build_ctx"]["locks"] = {str(x) for x in locks}
        except Exception:
            pass
    # Return a small confirmation with a shortcut to rerun
    hint = (
        '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
        f'<div>Locked <strong>{new}</strong> and unlocked <strong>{old}</strong>.</div>'
    '<div class="muted" style="margin-top:.35rem;">Now click <em>Rerun Stage</em> with Replace: On to apply this change.</div>'
        '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
        '<form hx-post="/build/step5/rerun" hx-target="#wizard" hx-swap="innerHTML" style="display:inline;">'
        '<input type="hidden" name="show_skipped" value="1" />'
        '<button type="submit" class="btn-rerun">Rerun stage</button>'
        '</form>'
    '<form hx-post="/build/replace/undo" hx-target="closest .alts" hx-swap="outerHTML" style="display:inline; margin:0;">'
    f'<input type="hidden" name="old" value="{old}" />'
    f'<input type="hidden" name="new" value="{new}" />'
    '<button type="submit" class="btn" title="Undo this replace">Undo</button>'
    '</form>'
        '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
        '</div>'
        '</div>'
    )
    # Also emit an OOB last-action chip
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">Replaced <strong>{old}</strong> → <strong>{new}</strong></span>'
        f'</div>'
    )
    return HTMLResponse(hint + chip)


@router.post("/replace/undo", response_class=HTMLResponse)
async def build_replace_undo(request: Request, old: str = Form(None), new: str = Form(None)) -> HTMLResponse:
    """Undo the last replace by restoring the previous lock state (best-effort)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    last = sess.get("last_replace") or {}
    try:
        # Prefer provided args, else fallback to last recorded
        o = (str(old).strip().lower() if old else str(last.get("old") or "")).strip()
        n = (str(new).strip().lower() if new else str(last.get("new") or "")).strip()
    except Exception:
        o, n = "", ""
    locks = set(sess.get("locks", []))
    changed = False
    if n and n in locks:
        locks.discard(n)
        changed = True
    if o:
        locks.add(o)
        changed = True
    sess["locks"] = list(locks)
    if sess.get("build_ctx"):
        try:
            sess["build_ctx"]["locks"] = {str(x) for x in locks}
        except Exception:
            pass
    # Clear last_replace after undo
    try:
        if sess.get("last_replace"):
            del sess["last_replace"]
    except Exception:
        pass
    # Return confirmation panel and OOB chip
    msg = 'Undid replace' if changed else 'No changes to undo'
    html = (
        '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
        f'<div>{msg}.</div>'
        '<div class="muted" style="margin-top:.35rem;">Rerun the stage to recompute picks if needed.</div>'
        '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
        '<form hx-post="/build/step5/rerun" hx-target="#wizard" hx-swap="innerHTML" style="display:inline;">'
        '<input type="hidden" name="show_skipped" value="1" />'
        '<button type="submit" class="btn-rerun">Rerun stage</button>'
        '</form>'
        '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
        '</div>'
        '</div>'
    )
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">{msg}</span>'
        f'</div>'
    )
    return HTMLResponse(html + chip)


@router.get("/compare")
async def build_compare(runA: str, runB: str):
    """Stub: return empty diffs; later we can diff summary files under deck_files."""
    return JSONResponse({"ok": True, "added": [], "removed": [], "changed": []})


@router.get("/permalink")
async def build_permalink(request: Request):
    """Return a URL-safe JSON payload representing current run config (basic)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    payload = {
        "commander": sess.get("commander"),
        "tags": sess.get("tags", []),
        "bracket": sess.get("bracket"),
        "ideals": sess.get("ideals"),
        "tag_mode": sess.get("tag_mode", "AND"),
        "flags": {
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
        },
        "locks": list(sess.get("locks", [])),
    }
    try:
        import base64
        import json as _json
        raw = _json.dumps(payload, separators=(",", ":"))
        token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        # Also include decoded state for convenience/testing
        return JSONResponse({"ok": True, "permalink": f"/build/from?state={token}", "state": payload})
    except Exception:
        return JSONResponse({"ok": True, "state": payload})


@router.get("/from", response_class=HTMLResponse)
async def build_from(request: Request, state: str | None = None) -> HTMLResponse:
    """Load a run from a permalink token."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if state:
        try:
            import base64
            import json as _json
            pad = '=' * (-len(state) % 4)
            raw = base64.urlsafe_b64decode((state + pad).encode("ascii")).decode("utf-8")
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
            sess["locks"] = list(data.get("locks", []))
            sess["last_step"] = 4
        except Exception:
            pass
    locks_restored = 0
    try:
        locks_restored = len(sess.get("locks", []) or [])
    except Exception:
        locks_restored = 0
    resp = templates.TemplateResponse("build/_step4.html", {
        "request": request,
        "labels": orch.ideal_labels(),
        "values": sess.get("ideals") or orch.ideal_defaults(),
        "commander": sess.get("commander"),
        "owned_only": bool(sess.get("use_owned_only")),
        "prefer_owned": bool(sess.get("prefer_owned")),
        "locks_restored": locks_restored,
    })
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
