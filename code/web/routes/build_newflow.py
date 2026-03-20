"""New Build Flow Routes

Handles the New Deck modal, commander search/inspection, skip controls,
new deck submission, Quick Build automation, and batch builds.

Extracted in Phase 4 of Roadmap 9 M1 Backend Standardization.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Any, Dict
from ..app import (
    ALLOW_MUST_HAVES,
    ENABLE_CUSTOM_THEMES,
    SHOW_MUST_HAVE_BUTTONS,
    ENABLE_PARTNER_MECHANICS,
    WEB_IDEALS_UI,
    ENABLE_BATCH_BUILD,
    DEFAULT_THEME_MATCH_MODE,
    THEME_POOL_SECTIONS,
)
from ..services.build_utils import (
    step5_ctx_from_result,
    start_ctx_from_session,
)
from ..app import templates
from deck_builder import builder_constants as bc
from ..services import orchestrator as orch
from ..services.orchestrator import is_setup_ready as _is_setup_ready, is_setup_stale as _is_setup_stale
from ..services.tasks import get_session, new_sid
from deck_builder.builder import DeckBuilder
from commander_exclusions import lookup_commander_detail
from .build_themes import _custom_theme_context
from .build_partners import (
    _partner_ui_context,
    _resolve_partner_selection,
)
from .build_wizard import _prepare_step2_theme_data, _section_themes_by_pool_size  # R21: Pool size data
from ..services import custom_theme_manager as theme_mgr

router = APIRouter()


# ==============================================================================
# New Deck Modal and Commander Search
# ==============================================================================

@router.get("/new", response_class=HTMLResponse)
async def build_new_modal(request: Request) -> HTMLResponse:
    """Return the New Deck modal content (for an overlay)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    # Clear build context to allow skip controls to work
    # (Otherwise toggle endpoint thinks build is in progress)
    if "build_ctx" in sess:
        try:
            del sess["build_ctx"]
        except Exception:
            pass
    
    # M2: Clear all skip preferences for true "New Deck"
    skip_keys = [
        "skip_lands", "skip_to_misc", "skip_basics", "skip_staples", 
        "skip_kindred", "skip_fetches", "skip_duals", "skip_triomes",
        "skip_all_creatures", 
        "skip_creature_primary", "skip_creature_secondary", "skip_creature_fill",
        "skip_all_spells",
        "skip_ramp", "skip_removal", "skip_wipes", "skip_card_advantage", 
        "skip_protection", "skip_spell_fill",
        "skip_post_adjust"
    ]
    for key in skip_keys:
        sess.pop(key, None)
    
    # M2: Check if this is a quick-build scenario (from commander browser)
    # Use the quick_build flag set by /build route when ?commander= param present
    is_quick_build = sess.pop("quick_build", False)  # Pop to consume the flag
    
    # M2: Clear commander and form selections for fresh start (unless quick build)
    if not is_quick_build:
        commander_keys = [
            "commander", "partner", "background", "commander_mode",
            "themes", "bracket"
        ]
        for key in commander_keys:
            sess.pop(key, None)
    
    theme_context = _custom_theme_context(request, sess)
    ctx = {
        "request": request,
        "brackets": orch.bracket_options(),
        "labels": orch.ideal_labels(),
        "defaults": orch.ideal_defaults(),
        "allow_must_haves": ALLOW_MUST_HAVES,  # Add feature flag
        "show_must_have_buttons": SHOW_MUST_HAVE_BUTTONS,
        "enable_custom_themes": ENABLE_CUSTOM_THEMES,
        "enable_batch_build": ENABLE_BATCH_BUILD,
        "ideals_ui_mode": WEB_IDEALS_UI,  # 'input' or 'slider'
        "form": {
            "commander": sess.get("commander", ""),  # Pre-fill for quick-build
            "prefer_combos": bool(sess.get("prefer_combos")),
            "combo_count": sess.get("combo_target_count"),
            "combo_balance": sess.get("combo_balance"),
            "enable_multicopy": bool(sess.get("multi_copy")),
            "use_owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
            # Add ideal values from session (will be None on first load, triggering defaults)
            "ramp": sess.get("ideals", {}).get("ramp"),
            "lands": sess.get("ideals", {}).get("lands"),
            "basic_lands": sess.get("ideals", {}).get("basic_lands"),
            "creatures": sess.get("ideals", {}).get("creatures"),
            "removal": sess.get("ideals", {}).get("removal"),
            "wipes": sess.get("ideals", {}).get("wipes"),
            "card_advantage": sess.get("ideals", {}).get("card_advantage"),
            "protection": sess.get("ideals", {}).get("protection"),
        },
        "tag_slot_html": None,
    }
    for key, value in theme_context.items():
        if key == "request":
            continue
        ctx[key] = value
    resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/new/candidates", response_class=HTMLResponse)
async def build_new_candidates(request: Request, commander: str = Query("")) -> HTMLResponse:
    """Return a small list of commander candidates for the modal live search."""
    q = (commander or "").strip()
    items = orch.commander_candidates(q, limit=8) if q else []
    candidates: list[dict[str, Any]] = []
    for name, score, colors in items:
        detail = lookup_commander_detail(name)
        preferred = name
        warning = None
        if detail:
            eligible_raw = detail.get("eligible_faces")
            eligible = [str(face).strip() for face in eligible_raw or [] if str(face).strip()] if isinstance(eligible_raw, list) else []
            norm_name = str(name).strip().casefold()
            eligible_norms = [face.casefold() for face in eligible]
            if eligible and norm_name not in eligible_norms:
                preferred = eligible[0]
                primary = str(detail.get("primary_face") or detail.get("name") or name).strip()
                if len(eligible) == 1:
                    warning = (
                        f"Use the back face '{preferred}' when building. Front face '{primary}' can't lead a deck."
                    )
                else:
                    faces = ", ".join(f"'{face}'" for face in eligible)
                    warning = (
                        f"This commander only works from specific faces: {faces}."
                    )
        candidates.append(
            {
                "display": name,
                "value": preferred,
                "score": score,
                "colors": colors,
                "warning": warning,
            }
        )
    ctx = {"request": request, "query": q, "candidates": candidates}
    return templates.TemplateResponse("build/_new_deck_candidates.html", ctx)


@router.get("/new/inspect", response_class=HTMLResponse)
async def build_new_inspect(request: Request, name: str = Query(...)) -> HTMLResponse:
    """When a candidate is chosen in the modal, show the commander preview and tag chips (OOB updates)."""
    info = orch.commander_select(name)
    if not info.get("ok"):
        return HTMLResponse(f'<div class="muted">Commander not found: {name}</div>')
    tags_raw = orch.tags_for_commander(info["name"]) or []
    recommended_raw = orch.recommended_tags_for_commander(info["name"]) if tags_raw else []
    recommended_reasons = orch.recommended_tag_reasons_for_commander(info["name"]) if tags_raw else {}
    
    # R21: Load pool size data and sort themes
    tags, recommended, pool_size = _prepare_step2_theme_data(tags_raw, recommended_raw)
    
    # R21: Section themes by pool size if enabled
    tag_sections = []
    recommended_sections = []
    if THEME_POOL_SECTIONS:
        tag_sections = _section_themes_by_pool_size(tags, pool_size)
        recommended_sections = _section_themes_by_pool_size(recommended, pool_size)
    
    exclusion_detail = lookup_commander_detail(info["name"])
    # Render tags slot content and OOB commander preview simultaneously
    # Game Changer flag for this commander (affects bracket UI in modal via tags partial consumer)
    is_gc = False
    try:
        is_gc = bool(info["name"] in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    ctx = {
        "request": request,
        "commander": {"name": info["name"], "exclusion": exclusion_detail},
        "tags": tags,
        "recommended": recommended,
        "pool_size": pool_size,  # R21: Pool size data for badges
        "use_sections": THEME_POOL_SECTIONS,  # R21: Flag for template
        "tag_sections": tag_sections,  # R21: Sectioned themes
        "recommended_sections": recommended_sections,  # R21: Sectioned recommendations
        "recommended_reasons": recommended_reasons,
        "gc_commander": is_gc,
        "brackets": orch.bracket_options(),
    }
    
    ctx.update(
        _partner_ui_context(
            info["name"],
            partner_enabled=False,
            secondary_selection=None,
            background_selection=None,
            combined_preview=None,
            warnings=None,
            partner_error=None,
            auto_note=None,
        )
    )
    partner_tags = ctx.get("partner_theme_tags") or []
    if partner_tags:
        merged_tags: list[str] = []
        seen: set[str] = set()
        for source in (partner_tags, tags):
            for tag in source:
                token = str(tag).strip()
                if not token:
                    continue
                key = token.casefold()
                if key in seen:
                    continue
                seen.add(key)
                merged_tags.append(token)
        ctx["tags"] = merged_tags
        
        # R21: Re-section merged tags if sectioning enabled
        if THEME_POOL_SECTIONS:
            ctx["tag_sections"] = _section_themes_by_pool_size(merged_tags, pool_size)

        # Deduplicate recommended: remove any that are already in partner_tags
        partner_tags_lower = {str(tag).strip().casefold() for tag in partner_tags}
        existing_recommended = ctx.get("recommended") or []
        deduplicated_recommended = [
            tag for tag in existing_recommended
            if str(tag).strip().casefold() not in partner_tags_lower
        ]
        ctx["recommended"] = deduplicated_recommended

        reason_map = dict(ctx.get("recommended_reasons") or {})
        for tag in partner_tags:
            if tag not in reason_map:
                reason_map[tag] = "Synergizes with partner pairing"
        ctx["recommended_reasons"] = reason_map
    return templates.TemplateResponse("build/_new_deck_tags.html", ctx)


# ==============================================================================
# Skip Controls
# ==============================================================================

@router.post("/new/toggle-skip", response_class=JSONResponse)
async def build_new_toggle_skip(
    request: Request,
    skip_key: str = Form(...),
    enabled: str = Form(...),
) -> JSONResponse:
    """Toggle a skip configuration flag (wizard-only, before build starts).
    
    Enforces mutual exclusivity:
    - skip_lands and skip_to_misc are mutually exclusive with individual land flags
    - Individual land flags are mutually exclusive with each other
    """
    sid = request.cookies.get("sid") or request.headers.get("X-Session-ID")
    if not sid:
        return JSONResponse({"error": "No session ID"}, status_code=400)
    
    sess = get_session(sid)
    
    # Wizard-only: reject if build has started
    if "build_ctx" in sess:
        return JSONResponse({"error": "Cannot modify skip settings after build has started"}, status_code=400)
    
    # Validate skip_key
    valid_keys = {
        "skip_lands", "skip_to_misc", "skip_basics", "skip_staples", 
        "skip_kindred", "skip_fetches", "skip_duals", "skip_triomes",
        "skip_all_creatures", 
        "skip_creature_primary", "skip_creature_secondary", "skip_creature_fill",
        "skip_all_spells",
        "skip_ramp", "skip_removal", "skip_wipes", "skip_card_advantage", 
        "skip_protection", "skip_spell_fill",
        "skip_post_adjust"
    }
    
    if skip_key not in valid_keys:
        return JSONResponse({"error": f"Invalid skip key: {skip_key}"}, status_code=400)
    
    # Parse enabled flag
    enabled_flag = str(enabled).strip().lower() in {"1", "true", "yes", "on"}
    
    # Mutual exclusivity rules
    land_group_flags = {"skip_lands", "skip_to_misc"}
    individual_land_flags = {"skip_basics", "skip_staples", "skip_kindred", "skip_fetches", "skip_duals", "skip_triomes"}
    creature_specific_flags = {"skip_creature_primary", "skip_creature_secondary", "skip_creature_fill"}
    spell_specific_flags = {"skip_ramp", "skip_removal", "skip_wipes", "skip_card_advantage", "skip_protection", "skip_spell_fill"}
    
    # If enabling a flag, check for conflicts
    if enabled_flag:
        # Rule 1: skip_lands/skip_to_misc disables all individual land flags
        if skip_key in land_group_flags:
            for key in individual_land_flags:
                sess[key] = False
        
        # Rule 2: Individual land flags disable skip_lands/skip_to_misc
        elif skip_key in individual_land_flags:
            for key in land_group_flags:
                sess[key] = False
        
        # Rule 3: skip_all_creatures disables specific creature flags
        elif skip_key == "skip_all_creatures":
            for key in creature_specific_flags:
                sess[key] = False
        
        # Rule 4: Specific creature flags disable skip_all_creatures
        elif skip_key in creature_specific_flags:
            sess["skip_all_creatures"] = False
        
        # Rule 5: skip_all_spells disables specific spell flags
        elif skip_key == "skip_all_spells":
            for key in spell_specific_flags:
                sess[key] = False
        
        # Rule 6: Specific spell flags disable skip_all_spells
        elif skip_key in spell_specific_flags:
            sess["skip_all_spells"] = False
    
    # Set the requested flag
    sess[skip_key] = enabled_flag
    
    # Auto-enable skip_post_adjust when any other skip is enabled
    if enabled_flag and skip_key != "skip_post_adjust":
        sess["skip_post_adjust"] = True
    
    # Auto-disable skip_post_adjust when all other skips are disabled
    if not enabled_flag:
        any_other_skip = any(
            sess.get(k, False) for k in valid_keys 
            if k != "skip_post_adjust" and k != skip_key
        )
        if not any_other_skip:
            sess["skip_post_adjust"] = False
    
    return JSONResponse({
        "success": True,
        "skip_key": skip_key,
        "enabled": enabled_flag,
        "skip_post_adjust": bool(sess.get("skip_post_adjust", False))
    })


# ==============================================================================
# New Deck Submission (Main Handler)
# ==============================================================================

@router.post("/new", response_class=HTMLResponse)
async def build_new_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form("") ,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    partner_enabled: str | None = Form(None),
    secondary_commander: str | None = Form(None),
    background: str | None = Form(None),
    partner_auto_opt_out: str | None = Form(None),
    partner_selection_source: str | None = Form(None),
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
    enable_multicopy: bool = Form(False),
    use_owned_only: bool = Form(False),
    prefer_owned: bool = Form(False),
    swap_mdfc_basics: bool = Form(False),
    # Integrated Multi-Copy (optional)
    multi_choice_id: str | None = Form(None),
    multi_count: int | None = Form(None),
    multi_thrumming: str | None = Form(None),
    # Must-haves/excludes (optional)
    include_cards: str = Form(""),
    exclude_cards: str = Form(""),
    enforcement_mode: str = Form("warn"),
    allow_illegal: bool = Form(False),
    fuzzy_matching: bool = Form(True),
    # Build count for multi-build
    build_count: int = Form(1),
    # Quick Build flag
    quick_build: str | None = Form(None),
) -> HTMLResponse:
    """Handle New Deck modal submit and immediately start the build (skip separate review page)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    partner_feature_enabled = ENABLE_PARTNER_MECHANICS
    raw_partner_flag = (partner_enabled or "").strip().lower()
    partner_checkbox = partner_feature_enabled and raw_partner_flag in {"1", "true", "on", "yes"}
    initial_secondary = (secondary_commander or "").strip()
    initial_background = (background or "").strip()
    auto_opt_out_flag = (partner_auto_opt_out or "").strip().lower() in {"1", "true", "on", "yes"}
    partner_form_state: dict[str, Any] = {
        "partner_enabled": bool(partner_checkbox),
        "secondary_commander": initial_secondary,
        "background": initial_background,
        "partner_mode": None,
        "partner_auto_note": None,
        "partner_warnings": [],
        "combined_preview": None,
        "partner_auto_assigned": False,
    }

    def _form_state(commander_value: str) -> dict[str, Any]:
        return {
            "name": name,
            "commander": commander_value,
            "primary_tag": primary_tag or "",
            "secondary_tag": secondary_tag or "",
            "tertiary_tag": tertiary_tag or "",
            "tag_mode": tag_mode or "AND",
            "bracket": bracket,
            "combo_count": combo_count,
            "combo_balance": (combo_balance or "mix"),
            "prefer_combos": bool(prefer_combos),
            "enable_multicopy": bool(enable_multicopy),
            "use_owned_only": bool(use_owned_only),
            "prefer_owned": bool(prefer_owned),
            "swap_mdfc_basics": bool(swap_mdfc_basics),
            "include_cards": include_cards or "",
            "exclude_cards": exclude_cards or "",
            "enforcement_mode": enforcement_mode or "warn",
            "allow_illegal": bool(allow_illegal),
            "fuzzy_matching": bool(fuzzy_matching),
            "partner_enabled": partner_form_state["partner_enabled"],
            "secondary_commander": partner_form_state["secondary_commander"],
            "background": partner_form_state["background"],
        }

    commander_detail = lookup_commander_detail(commander)
    if commander_detail:
        eligible_raw = commander_detail.get("eligible_faces")
        eligible_faces = [str(face).strip() for face in eligible_raw or [] if str(face).strip()] if isinstance(eligible_raw, list) else []
        if eligible_faces:
            norm_input = str(commander).strip().casefold()
            eligible_norms = [face.casefold() for face in eligible_faces]
            if norm_input not in eligible_norms:
                suggested = eligible_faces[0]
                primary_face = str(commander_detail.get("primary_face") or commander_detail.get("name") or commander).strip()
                faces_str = ", ".join(f"'{face}'" for face in eligible_faces)
                error_msg = (
                    f"'{primary_face or commander}' can't lead a deck. Use {faces_str} as the commander instead. "
                    "We've updated the commander field for you."
                )
                ctx = {
                    "request": request,
                    "error": error_msg,
                    "brackets": orch.bracket_options(),
                    "labels": orch.ideal_labels(),
                    "defaults": orch.ideal_defaults(),
                    "allow_must_haves": ALLOW_MUST_HAVES,
                    "show_must_have_buttons": SHOW_MUST_HAVE_BUTTONS,
                    "enable_custom_themes": ENABLE_CUSTOM_THEMES,
                    "enable_batch_build": ENABLE_BATCH_BUILD,
                    "form": _form_state(suggested),
                    "tag_slot_html": None,
                }
                theme_ctx = _custom_theme_context(request, sess, message=error_msg, level="error")
                for key, value in theme_ctx.items():
                    if key == "request":
                        continue
                    ctx[key] = value
                resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
                resp.set_cookie("sid", sid, httponly=True, samesite="lax")
                return resp
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
            "allow_must_haves": ALLOW_MUST_HAVES,  # Add feature flag
            "show_must_have_buttons": SHOW_MUST_HAVE_BUTTONS,
            "enable_custom_themes": ENABLE_CUSTOM_THEMES,
            "enable_batch_build": ENABLE_BATCH_BUILD,
            "form": _form_state(commander),
            "tag_slot_html": None,
        }
        theme_ctx = _custom_theme_context(request, sess, message=ctx["error"], level="error")
        for key, value in theme_ctx.items():
            if key == "request":
                continue
            ctx[key] = value
        resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    primary_commander_name = sel.get("name") or commander
    # Enforce GC bracket restriction before saving session (silently coerce to 3)
    try:
        is_gc = bool(primary_commander_name in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    if is_gc:
        try:
            if int(bracket) < 3:
                bracket = 3
        except Exception:
            bracket = 3
    # Save to session
    sess["commander"] = primary_commander_name
    (
        partner_error,
        combined_payload,
        partner_warnings,
        partner_auto_note,
        resolved_secondary,
        resolved_background,
        partner_mode,
        partner_auto_assigned_flag,
    ) = _resolve_partner_selection(
        primary_commander_name,
        feature_enabled=partner_feature_enabled,
        partner_enabled=partner_checkbox,
        secondary_candidate=secondary_commander,
        background_candidate=background,
        auto_opt_out=auto_opt_out_flag,
        selection_source=partner_selection_source,
    )

    partner_form_state["partner_mode"] = partner_mode
    partner_form_state["partner_auto_note"] = partner_auto_note
    partner_form_state["partner_warnings"] = partner_warnings
    partner_form_state["combined_preview"] = combined_payload
    if resolved_secondary:
        partner_form_state["secondary_commander"] = resolved_secondary
    if resolved_background:
        partner_form_state["background"] = resolved_background
    partner_form_state["partner_auto_assigned"] = bool(partner_auto_assigned_flag)

    combined_theme_pool: list[str] = []
    if isinstance(combined_payload, dict):
        raw_tags = combined_payload.get("theme_tags") or []
        for tag in raw_tags:
            token = str(tag).strip()
            if not token:
                continue
            if token not in combined_theme_pool:
                combined_theme_pool.append(token)

    if partner_error:
        available_tags = orch.tags_for_commander(primary_commander_name)
        recommended_tags = orch.recommended_tags_for_commander(primary_commander_name)
        recommended_reasons = orch.recommended_tag_reasons_for_commander(primary_commander_name)
        inspect_ctx: dict[str, Any] = {
            "request": request,
            "commander": {"name": primary_commander_name, "exclusion": lookup_commander_detail(primary_commander_name)},
            "tags": available_tags,
            "recommended": recommended_tags,
            "recommended_reasons": recommended_reasons,
            "gc_commander": is_gc,
            "brackets": orch.bracket_options(),
        }
        inspect_ctx.update(
            _partner_ui_context(
                primary_commander_name,
                partner_enabled=partner_checkbox,
                secondary_selection=partner_form_state["secondary_commander"] or None,
                background_selection=partner_form_state["background"] or None,
                combined_preview=combined_payload,
                warnings=partner_warnings,
                partner_error=partner_error,
                auto_note=partner_auto_note,
                auto_assigned=partner_form_state["partner_auto_assigned"],
                auto_prefill_allowed=not auto_opt_out_flag,
            )
        )
        partner_tags = inspect_ctx.pop("partner_theme_tags", None)
        if partner_tags:
            inspect_ctx["tags"] = partner_tags
        tag_slot_html = templates.get_template("build/_new_deck_tags.html").render(inspect_ctx)
        ctx = {
            "request": request,
            "error": partner_error,
            "brackets": orch.bracket_options(),
            "labels": orch.ideal_labels(),
            "defaults": orch.ideal_defaults(),
            "allow_must_haves": ALLOW_MUST_HAVES,
            "show_must_have_buttons": SHOW_MUST_HAVE_BUTTONS,
            "enable_custom_themes": ENABLE_CUSTOM_THEMES,
            "enable_batch_build": ENABLE_BATCH_BUILD,
            "form": _form_state(primary_commander_name),
            "tag_slot_html": tag_slot_html,
        }
        theme_ctx = _custom_theme_context(request, sess, message=partner_error, level="error")
        for key, value in theme_ctx.items():
            if key == "request":
                continue
            ctx[key] = value
        resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    if partner_checkbox and combined_payload:
        sess["partner_enabled"] = True
        if resolved_secondary:
            sess["secondary_commander"] = resolved_secondary
        else:
            sess.pop("secondary_commander", None)
        if resolved_background:
            sess["background"] = resolved_background
        else:
            sess.pop("background", None)
        if partner_mode:
            sess["partner_mode"] = partner_mode
        else:
            sess.pop("partner_mode", None)
        sess["combined_commander"] = combined_payload
        sess["partner_warnings"] = partner_warnings
        if partner_auto_note:
            sess["partner_auto_note"] = partner_auto_note
        else:
            sess.pop("partner_auto_note", None)
        sess["partner_auto_assigned"] = bool(partner_auto_assigned_flag)
        sess["partner_auto_opt_out"] = bool(auto_opt_out_flag)
    else:
        sess["partner_enabled"] = False
        for key in [
            "secondary_commander",
            "background",
            "partner_mode",
            "partner_warnings",
            "combined_commander",
            "partner_auto_note",
        ]:
            try:
                sess.pop(key)
            except KeyError:
                pass
        for key in ["partner_auto_assigned", "partner_auto_opt_out"]:
            try:
                sess.pop(key)
            except KeyError:
                pass

    # 1) Start from explicitly selected tags (order preserved)
    tags = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    user_explicit = bool(tags)  # whether the user set any theme in the form
    # 2) Consider user-added supplemental themes from the Additional Themes UI
    additional_from_session = []
    try:
        # custom_theme_manager stores resolved list here on add/resolve; present before submit
        additional_from_session = [
            str(x) for x in (sess.get("additional_themes") or []) if isinstance(x, str) and x.strip()
        ]
    except Exception:
        additional_from_session = []
    # 3) If no explicit themes were selected, prefer additional themes as primary/secondary/tertiary
    if not user_explicit and additional_from_session:
        # Cap to three and preserve order
        tags = list(additional_from_session[:3])
    # 4) If user selected some themes, fill remaining slots with additional themes (deduping)
    elif user_explicit and additional_from_session:
        seen = {str(t).strip().casefold() for t in tags}
        for name in additional_from_session:
            key = name.strip().casefold()
            if key in seen:
                continue
            tags.append(name)
            seen.add(key)
            if len(tags) >= 3:
                break
    # 5) If still empty (no explicit and no additional), fall back to commander-recommended default
    if not tags:
        if combined_theme_pool:
            tags = combined_theme_pool[:3]
        else:
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
    if ENABLE_CUSTOM_THEMES:
        try:
            theme_mgr.refresh_resolution(
                sess,
                commander_tags=tags,
                mode=sess.get("theme_match_mode", DEFAULT_THEME_MATCH_MODE),
            )
        except ValueError as exc:
            error_msg = str(exc)
            ctx = {
                "request": request,
                "error": error_msg,
                "brackets": orch.bracket_options(),
                "labels": orch.ideal_labels(),
                "defaults": orch.ideal_defaults(),
                "allow_must_haves": ALLOW_MUST_HAVES,
                "show_must_have_buttons": SHOW_MUST_HAVE_BUTTONS,
                "enable_custom_themes": ENABLE_CUSTOM_THEMES,
                "enable_batch_build": ENABLE_BATCH_BUILD,
                "form": _form_state(sess.get("commander", "")),
                "tag_slot_html": None,
            }
            theme_ctx = _custom_theme_context(request, sess, message=error_msg, level="error")
            for key, value in theme_ctx.items():
                if key == "request":
                    continue
                ctx[key] = value
            resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
            resp.set_cookie("sid", sid, httponly=True, samesite="lax")
            return resp
    # Persist preferences
    try:
        sess["prefer_combos"] = bool(prefer_combos)
    except Exception:
        sess["prefer_combos"] = False
    try:
        sess["use_owned_only"] = bool(use_owned_only)
    except Exception:
        sess["use_owned_only"] = False
    try:
        sess["prefer_owned"] = bool(prefer_owned)
    except Exception:
        sess["prefer_owned"] = False
    try:
        sess["swap_mdfc_basics"] = bool(swap_mdfc_basics)
    except Exception:
        sess["swap_mdfc_basics"] = False
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
    # Multi-Copy selection from modal (opt-in)
    try:
        # Clear any prior selection first; this flow should define it explicitly when present
        if "multi_copy" in sess:
            del sess["multi_copy"]
        if enable_multicopy and multi_choice_id and str(multi_choice_id).strip():
            meta = bc.MULTI_COPY_ARCHETYPES.get(str(multi_choice_id), {})
            printed_cap = meta.get("printed_cap")
            cnt: int
            if multi_count is None:
                cnt = int(meta.get("default_count", 25))
            else:
                try:
                    cnt = int(multi_count)
                except Exception:
                    cnt = int(meta.get("default_count", 25))
            if isinstance(printed_cap, int) and printed_cap > 0:
                cnt = max(1, min(printed_cap, cnt))
            sess["multi_copy"] = {
                "id": str(multi_choice_id),
                "name": meta.get("name") or str(multi_choice_id),
                "count": int(cnt),
                "thrumming": True if (multi_thrumming and str(multi_thrumming).strip() in ("1","true","on","yes")) else False,
            }
        else:
            # Ensure disabled when not opted-in
            if "multi_copy" in sess:
                del sess["multi_copy"]
        # Reset the applied marker so the run can account for the new selection
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass
    
    # Process include/exclude cards (M3: Phase 2 - Full Include/Exclude)
    try:
        from deck_builder.include_exclude_utils import parse_card_list_input, IncludeExcludeDiagnostics
        
        # Clear any old include/exclude data
        for k in ["include_cards", "exclude_cards", "include_exclude_diagnostics", "enforcement_mode", "allow_illegal", "fuzzy_matching"]:
            if k in sess:
                del sess[k]
        
        # Process include cards
        if include_cards and include_cards.strip():
            print(f"DEBUG: Raw include_cards input: '{include_cards}'")
            include_list = parse_card_list_input(include_cards.strip())
            print(f"DEBUG: Parsed include_list: {include_list}")
            sess["include_cards"] = include_list
        else:
            print(f"DEBUG: include_cards is empty or None: '{include_cards}'")
        
        # Process exclude cards
        if exclude_cards and exclude_cards.strip():
            print(f"DEBUG: Raw exclude_cards input: '{exclude_cards}'")
            exclude_list = parse_card_list_input(exclude_cards.strip())
            print(f"DEBUG: Parsed exclude_list: {exclude_list}")
            sess["exclude_cards"] = exclude_list
        else:
            print(f"DEBUG: exclude_cards is empty or None: '{exclude_cards}'")
        
        # Store advanced options
        sess["enforcement_mode"] = enforcement_mode
        sess["allow_illegal"] = allow_illegal
        sess["fuzzy_matching"] = fuzzy_matching
        
        # Create basic diagnostics for status tracking
        if (include_cards and include_cards.strip()) or (exclude_cards and exclude_cards.strip()):
            diagnostics = IncludeExcludeDiagnostics(
                missing_includes=[],
                ignored_color_identity=[],
                illegal_dropped=[],
                illegal_allowed=[],
                excluded_removed=sess.get("exclude_cards", []),
                duplicates_collapsed={},
                include_added=[],
                include_over_ideal={},
                fuzzy_corrections={},
                confirmation_needed=[],
                list_size_warnings={
                    "includes_count": len(sess.get("include_cards", [])),
                    "excludes_count": len(sess.get("exclude_cards", [])),
                    "includes_limit": 10,
                    "excludes_limit": 15
                }
            )
            sess["include_exclude_diagnostics"] = diagnostics.__dict__
    except Exception as e:
        # If exclude parsing fails, log but don't block the build
        import logging
        logging.warning(f"Failed to parse exclude cards: {e}")
        
    # Clear any old staged build context
    for k in ["build_ctx", "locks", "replace_mode"]:
        if k in sess:
            try:
                del sess[k]
            except Exception:
                pass
    # Reset multi-copy suggestion debounce for a fresh run (keep selected choice)
    if "mc_seen_keys" in sess:
        try:
            del sess["mc_seen_keys"]
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
    
    # Validate and normalize build_count
    try:
        build_count = max(1, min(10, int(build_count)))
    except Exception:
        build_count = 1
    
    # Check if this is a multi-build request (build_count > 1)
    if build_count > 1:
        # Multi-Build: Queue parallel builds and return batch progress page
        from ..services.multi_build_orchestrator import queue_builds, run_batch_async
        
        # Create config dict from session for batch builds
        batch_config = {
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "tag_mode": sess.get("tag_mode", "AND"),
            "bracket": sess.get("bracket", 3),
            "ideals": sess.get("ideals", {}),
            "prefer_combos": sess.get("prefer_combos", False),
            "combo_target_count": sess.get("combo_target_count"),
            "combo_balance": sess.get("combo_balance"),
            "multi_copy": sess.get("multi_copy"),
            "use_owned_only": sess.get("use_owned_only", False),
            "prefer_owned": sess.get("prefer_owned", False),
            "swap_mdfc_basics": sess.get("swap_mdfc_basics", False),
            "include_cards": sess.get("include_cards", []),
            "exclude_cards": sess.get("exclude_cards", []),
            "enforcement_mode": sess.get("enforcement_mode", "warn"),
            "allow_illegal": sess.get("allow_illegal", False),
            "fuzzy_matching": sess.get("fuzzy_matching", True),
            "locks": list(sess.get("locks", [])),
        }
        
        # Handle partner mechanics if present
        if sess.get("partner_enabled"):
            batch_config["partner_enabled"] = True
            if sess.get("secondary_commander"):
                batch_config["secondary_commander"] = sess["secondary_commander"]
            if sess.get("background"):
                batch_config["background"] = sess["background"]
            if sess.get("partner_mode"):
                batch_config["partner_mode"] = sess["partner_mode"]
            if sess.get("combined_commander"):
                batch_config["combined_commander"] = sess["combined_commander"]
        
        # Add color identity for synergy builder (needed for basic land allocation)
        try:
            tmp_builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
            
            # Handle partner mechanics if present
            if sess.get("partner_enabled") and sess.get("secondary_commander"):
                from deck_builder.partner_selection import apply_partner_inputs
                combined_obj = apply_partner_inputs(
                    tmp_builder,
                    primary_name=sess["commander"],
                    secondary_name=sess.get("secondary_commander"),
                    background_name=sess.get("background"),
                    feature_enabled=True,
                )
                if combined_obj and hasattr(combined_obj, "color_identity"):
                    batch_config["colors"] = list(combined_obj.color_identity)
            else:
                # Single commander
                df = tmp_builder.load_commander_data()
                row = df[df["name"] == sess["commander"]]
                if not row.empty:
                    # Get colorIdentity from dataframe (it's a string like "RG" or "G")
                    color_str = row.iloc[0].get("colorIdentity", "")
                    if color_str:
                        batch_config["colors"] = list(color_str)  # Convert "RG" to ['R', 'G']
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Batch] Failed to load color identity for {sess.get('commander')}: {e}")
            pass  # Not critical, synergy builder will skip basics if missing
        
        # Queue the batch
        batch_id = queue_builds(batch_config, build_count, sid)
        
        # Start background task for parallel builds
        background_tasks.add_task(run_batch_async, batch_id, sid)
        
        # Return batch progress template
        progress_ctx = {
            "request": request,
            "batch_id": batch_id,
            "build_count": build_count,
            "completed": 0,
            "current_build": 1,
            "status": "Starting builds..."
        }
        resp = templates.TemplateResponse("build/_batch_progress.html", progress_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    
    # Check if Quick Build was requested (single build only)
    is_quick_build = (quick_build or "").strip() == "1"
    
    if is_quick_build:
        # Quick Build: Start background task and return progress template immediately
        ctx = sess["build_ctx"]
        
        # Initialize progress tracking with dynamic counting (total starts at 0)
        sess["quick_build_progress"] = {
            "running": True,
            "total": 0,
            "completed": 0,
            "current_stage": "Starting build..."
        }
        
        # Start background task to run all stages
        background_tasks.add_task(_run_quick_build_stages, sid)
        
        # Return progress template immediately
        progress_ctx = {
            "request": request,
            "progress_pct": 0,
            "completed": 0,
            "total": 0,
            "current_stage": "Starting build..."
        }
        resp = templates.TemplateResponse("build/_quick_build_progress.html", progress_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    else:
        # Normal build: Run first stage and wait for user input
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=False)
        # If Multi-Copy ran first, mark applied to prevent redundant rebuilds on Continue
        try:
            if res.get("label") == "Multi-Copy Package" and sess.get("multi_copy"):
                mc = sess.get("multi_copy")
                sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
        except Exception:
            pass
        status = "Build complete" if res.get("done") else "Stage complete"
        sess["last_step"] = 5
        ctx = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=False)
        resp = templates.TemplateResponse("build/_step5.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp


# ==============================================================================
# Quick Build Progress Polling
# ==============================================================================

def _get_descriptive_stage_label(stage: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Generate a more descriptive label for Quick Build progress display."""
    key = stage.get("key", "")
    base_label = stage.get("label", "")
    
    # Land stages - show what type of lands
    land_types = {
        "land1": "Basics",
        "land2": "Staples", 
        "land3": "Fetches",
        "land4": "Duals",
        "land5": "Triomes",
        "land6": "Kindred",
        "land7": "Misc Utility",
        "land8": "Final Lands"
    }
    if key in land_types:
        return f"Lands: {land_types[key]}"
    
    # Creature stages - show associated theme
    if "creatures" in key:
        tags = ctx.get("tags", [])
        if key == "creatures_all_theme":
            if tags:
                all_tags = " + ".join(tags[:3])  # Show up to 3 tags
                return f"Creatures: All Themes ({all_tags})"
            return "Creatures: All Themes"
        elif key == "creatures_primary" and len(tags) >= 1:
            return f"Creatures: {tags[0]}"
        elif key == "creatures_secondary" and len(tags) >= 2:
            return f"Creatures: {tags[1]}"
        elif key == "creatures_tertiary" and len(tags) >= 3:
            return f"Creatures: {tags[2]}"
        # Let creatures_fill use default "Creatures: Fill" label
    
    # Theme spell fill stage - adds any card type (artifacts, enchantments, instants, etc.) that fits theme
    if key == "spells_fill":
        return "Theme Spell Fill"
    
    # Default: return original label
    return base_label


def _run_quick_build_stages(sid: str):
    """Background task: Run all stages for Quick Build and update progress in session."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[Quick Build] Starting background task for sid={sid}")
    
    sess = get_session(sid)
    logger.info(f"[Quick Build] Retrieved session: {sess is not None}")
    
    ctx = sess.get("build_ctx")
    if not ctx:
        logger.error("[Quick Build] No build_ctx found in session")
        sess["quick_build_progress"] = {
            "running": False,
            "current_stage": "Error: No build context",
            "completed_stages": []
        }
        return
    
    logger.info(f"[Quick Build] build_ctx found with {len(ctx.get('stages', []))} stages")
    
    # CRITICAL: Inject session reference into context so skip config can be read
    ctx["session"] = sess
    logger.info("[Quick Build] Injected session reference into context")
    
    stages = ctx.get("stages", [])
    res = None
    
    # Initialize progress tracking
    sess["quick_build_progress"] = {
        "running": True,
        "current_stage": "Starting build..."
    }
    
    try:
        logger.info("[Quick Build] Starting stage loop")
        
        # Track which phase we're in for simplified progress display
        current_phase = None
        
        while True:
            current_idx = ctx.get("idx", 0)
            if current_idx >= len(stages):
                logger.info(f"[Quick Build] Reached end of stages (idx={current_idx})")
                break
            
            current_stage = stages[current_idx]
            stage_key = current_stage.get("key", "")
            logger.info(f"[Quick Build] Stage {current_idx} key: {stage_key}")
            
            # Determine simplified phase label
            if stage_key.startswith("creatures"):
                new_phase = "Adding Creatures"
            elif stage_key.startswith("spells") or stage_key in ["spells_ramp", "spells_removal", "spells_wipes", "spells_card_advantage", "spells_protection", "spells_fill"]:
                new_phase = "Adding Spells"
            elif stage_key.startswith("land"):
                new_phase = "Adding Lands"
            elif stage_key in ["post_spell_land_adjust", "reporting"]:
                new_phase = "Doing Some Final Touches"
            else:
                new_phase = "Building Deck"
            
            # Only update progress if phase changed
            if new_phase != current_phase:
                current_phase = new_phase
                sess["quick_build_progress"]["current_stage"] = current_phase
                logger.info(f"[Quick Build] Phase: {current_phase}")
            
            # Run stage with show_skipped=False
            res = orch.run_stage(ctx, rerun=False, show_skipped=False)
            logger.info(f"[Quick Build] Stage {stage_key} completed, done={res.get('done')}")
            
            # Handle Multi-Copy package marking
            try:
                if res.get("label") == "Multi-Copy Package" and sess.get("multi_copy"):
                    mc = sess.get("multi_copy")
                    sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
            except Exception:
                pass
            
            # Check if build is done (reporting stage marks done=True)
            if res.get("done"):
                break
            
            # run_stage() advances ctx["idx"] internally when stage completes successfully
            # If stage is gated, it also advances the index, so we just continue the loop
        
        # Show summary generation message (stay here for a moment)
        sess["quick_build_progress"]["current_stage"] = "Generating Summary"
        import time
        time.sleep(2)  # Pause briefly so user sees this stage
        
        # Store final result for polling endpoint
        sess["last_result"] = res or {}
        sess["last_step"] = 5
        
        # CRITICAL: Persist summary to session (bug fix from Phase 3)
        if res and res.get("summary"):
            sess["summary"] = res["summary"]
        
        # Small delay to show finishing message
        time.sleep(1.5)
        
    except Exception as e:
        # Store error state
        logger.exception(f"[Quick Build] Error during stage execution: {e}")
        sess["quick_build_progress"]["current_stage"] = f"Error: {str(e)}"
    finally:
        # Mark build as complete
        logger.info("[Quick Build] Background task completed")
        sess["quick_build_progress"]["running"] = False
        sess["quick_build_progress"]["current_stage"] = "Complete"


@router.get("/quick-progress")
def quick_build_progress(request: Request):
    """Poll endpoint for Quick Build progress. Returns either progress indicator or final Step 5."""
    import logging
    logger = logging.getLogger(__name__)
    
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    progress = sess.get("quick_build_progress")
    logger.info(f"[Progress Poll] sid={sid}, progress={progress is not None}, running={progress.get('running') if progress else None}")
    
    if not progress or not progress.get("running"):
        # Build complete - return Step 5 content that replaces the entire wizard container
        res = sess.get("last_result")
        if res and res.get("done"):
            ctx = step5_ctx_from_result(request, sess, res)
            # Return Step 5 which will replace the whole wizard div
            response = templates.TemplateResponse("build/_step5.html", ctx)
            response.set_cookie("sid", sid, httponly=True, samesite="lax")
            # Tell HTMX to target #wizard and swap outerHTML to replace the container
            response.headers["HX-Retarget"] = "#wizard"
            response.headers["HX-Reswap"] = "outerHTML"
            return response
        # Fallback if no result yet
        return HTMLResponse('Build complete. Please refresh.')
    
    # Build still running - return progress content partial only (innerHTML swap)
    current_stage = progress.get("current_stage", "Processing...")
    
    ctx = {
        "request": request,
        "current_stage": current_stage
    }
    response = templates.TemplateResponse("build/_quick_build_progress_content.html", ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response
