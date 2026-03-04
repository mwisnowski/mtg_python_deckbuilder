"""Multi-copy archetype routes for deck building.

Handles multi-copy package detection, selection, and integration with the deck builder.
Multi-copy archetypes allow multiple copies of specific cards (e.g., Hare Apparent, Dragon's Approach).

Routes:
    GET /multicopy/check - Check if commander/tags suggest multi-copy archetype  
    POST /multicopy/save - Save or skip multi-copy selection
    GET /new/multicopy - Get multi-copy suggestions for New Deck modal (inline)

Created: 2026-02-20
Roadmap: R9 M1 Phase 2
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse
from html import escape as _esc

from deck_builder.builder import DeckBuilder
from deck_builder import builder_utils as bu, builder_constants as bc
from ..app import templates
from ..services.tasks import get_session, new_sid
from ..services import orchestrator as orch
from ..services.build_utils import owned_names as owned_names_helper

router = APIRouter()


def _rebuild_ctx_with_multicopy(sess: dict) -> None:
    """Rebuild the staged context so Multi-Copy runs first, avoiding overfill.

    This ensures the added cards are accounted for before lands and later phases,
    which keeps totals near targets and shows the multi-copy additions ahead of basics.
    
    Args:
        sess: Session dictionary containing build state
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
            swap_mdfc_basics=bool(sess.get("swap_mdfc_basics")),
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


@router.get("/multicopy/check", response_class=HTMLResponse)
async def multicopy_check(request: Request) -> HTMLResponse:
    """If current commander/tags suggest a multi-copy archetype, render a choose-one modal.

    Returns empty content when not applicable to avoid flashing a modal unnecessarily.
    
    Args:
        request: FastAPI request object
        
    Returns:
        HTMLResponse with multi-copy modal or empty string
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
    
    Args:
        request: FastAPI request object
        choice_id: Multi-copy archetype ID (e.g., 'hare_apparent')
        count: Number of copies to include
        thrumming: Whether to include Thrumming Stone
        skip: Whether to skip multi-copy for this build
        
    Returns:
        HTMLResponse with confirmation chip (OOB swap)
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


@router.get("/new/multicopy", response_class=HTMLResponse)
async def build_new_multicopy(
    request: Request,
    commander: str = Query(""),
    primary_tag: str | None = Query(None),
    secondary_tag: str | None = Query(None),
    tertiary_tag: str | None = Query(None),
    tag_mode: str | None = Query("AND"),
) -> HTMLResponse:
    """Return multi-copy suggestions for the New Deck modal based on commander + selected tags.

    This does not mutate the session; it simply renders a form snippet that posts with the main modal.
    
    Args:
        request: FastAPI request object
        commander: Commander name
        primary_tag: Primary theme tag
        secondary_tag: Secondary theme tag  
        tertiary_tag: Tertiary theme tag
        tag_mode: Tag matching mode (AND/OR)
        
    Returns:
        HTMLResponse with multi-copy suggestions or empty string
    """
    name = (commander or "").strip()
    if not name:
        return HTMLResponse("")
    try:
        tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
        df = tmp.load_commander_data()
        row = df[df["name"].astype(str) == name]
        if row.empty:
            return HTMLResponse("")
        tmp._apply_commander_selection(row.iloc[0])
        tags = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
        tmp.selected_tags = list(tags or [])
        try:
            tmp.primary_tag = tmp.selected_tags[0] if len(tmp.selected_tags) > 0 else None
            tmp.secondary_tag = tmp.selected_tags[1] if len(tmp.selected_tags) > 1 else None
            tmp.tertiary_tag = tmp.selected_tags[2] if len(tmp.selected_tags) > 2 else None
        except Exception:
            pass
        try:
            tmp.determine_color_identity()
        except Exception:
            pass
        results = bu.detect_viable_multi_copy_archetypes(tmp) or []
        # For the New Deck modal, only show suggestions where the matched tags intersect
        # the explicitly selected tags (ignore commander-default themes).
        sel_tags = {str(t).strip().lower() for t in (tags or []) if str(t).strip()}
        def _matched_reason_tags(item: dict) -> set[str]:
            out = set()
            try:
                for r in item.get('reasons', []) or []:
                    if not isinstance(r, str):
                        continue
                    rl = r.strip().lower()
                    if rl.startswith('tags:'):
                        body = rl.split('tags:', 1)[1].strip()
                        parts = [p.strip() for p in body.split(',') if p.strip()]
                        out.update(parts)
            except Exception:
                return set()
            return out
        if sel_tags:
            results = [it for it in results if (_matched_reason_tags(it) & sel_tags)]
        else:
            # If no selected tags, do not show any multi-copy suggestions in the modal
            results = []
        if not results:
            return HTMLResponse("")
        items = results[:5]
        ctx = {"request": request, "items": items}
        return templates.TemplateResponse("build/_new_deck_multicopy.html", ctx)
    except Exception:
        return HTMLResponse("")
