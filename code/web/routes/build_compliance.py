"""Build Compliance and Card Replacement Routes

Phase 5 extraction from build.py:
- POST /build/replace - Inline card replacement with undo tracking
- POST /build/replace/undo - Undo last replacement
- GET /build/compare - Batch build comparison stub
- GET /build/compliance - Bracket compliance panel
- POST /build/enforce/apply - Apply bracket enforcement
- GET /build/enforcement - Full-page enforcement review

This module handles card replacement, bracket compliance checking, and enforcement.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Any
import json
from ..app import templates
from ..services.tasks import get_session, new_sid
from ..services.build_utils import (
    step5_ctx_from_result,
    step5_error_ctx,
    step5_empty_ctx,
    owned_set as owned_set_helper,
)
from ..services import orchestrator as orch
from deck_builder.builder import DeckBuilder
from html import escape as _esc
from urllib.parse import quote_plus


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


@router.post("/replace", response_class=HTMLResponse)
async def build_replace(request: Request, old: str = Form(...), new: str = Form(...), owned_only: str = Form("0")) -> HTMLResponse:
    """Inline replace: swap `old` with `new` in the current builder when possible, and suppress `old` from future alternatives.

    Falls back to lock-and-rerun guidance if no active builder is present.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    o_disp = str(old).strip()
    n_disp = str(new).strip()
    o = o_disp.lower()
    n = n_disp.lower()
    owned_only_flag = str(owned_only or "").strip().lower()
    owned_only_int = 1 if owned_only_flag in {"1", "true", "yes", "on"} else 0

    # Maintain locks to bias future picks and enforcement
    locks = set(sess.get("locks", []))
    locks.discard(o)
    locks.add(n)
    sess["locks"] = list(locks)
    # Track last replace for optional undo
    try:
        sess["last_replace"] = {"old": o, "new": n}
    except Exception:
        pass
    ctx = sess.get("build_ctx") or {}
    try:
        ctx["locks"] = {str(x) for x in locks}
    except Exception:
        pass
    # Record preferred replacements
    try:
        pref = ctx.get("preferred_replacements") if isinstance(ctx, dict) else None
        if not isinstance(pref, dict):
            pref = {}
            ctx["preferred_replacements"] = pref
        pref[o] = n
    except Exception:
        pass
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if b is not None:
        try:
            lib = getattr(b, "card_library", {}) or {}
            # Find the exact key for `old` in a case-insensitive manner
            old_key = None
            if o_disp in lib:
                old_key = o_disp
            else:
                for k in list(lib.keys()):
                    if str(k).strip().lower() == o:
                        old_key = k
                        break
            if old_key is None:
                raise KeyError("old card not in deck")
            old_info = dict(lib.get(old_key) or {})
            role = str(old_info.get("Role") or "").strip()
            subrole = str(old_info.get("SubRole") or "").strip()
            try:
                count = int(old_info.get("Count", 1))
            except Exception:
                count = 1
            # Remove old entry
            try:
                del lib[old_key]
            except Exception:
                pass
            # Resolve canonical name and info for new
            df = getattr(b, "_combined_cards_df", None)
            new_key = n_disp
            card_type = ""
            mana_cost = ""
            trigger_tag = str(old_info.get("TriggerTag") or "")
            if df is not None:
                try:
                    row = df[df["name"].astype(str).str.strip().str.lower() == n]
                    if not row.empty:
                        new_key = str(row.iloc[0]["name"]) or n_disp
                        card_type = str(row.iloc[0].get("type", row.iloc[0].get("type_line", "")) or "")
                        mana_cost = str(row.iloc[0].get("mana_cost", row.iloc[0].get("manaCost", "")) or "")
                except Exception:
                    pass
            lib[new_key] = {
                "Count": count,
                "Card Type": card_type,
                "Mana Cost": mana_cost,
                "Role": role,
                "SubRole": subrole,
                "AddedBy": "Replace",
                "TriggerTag": trigger_tag,
            }
            # Mirror preferred replacements onto the builder for enforcement
            try:
                cur = getattr(b, "preferred_replacements", {}) or {}
                cur[str(o)] = str(n)
                setattr(b, "preferred_replacements", cur)
            except Exception:
                pass
            # Update alternatives exclusion set and bump version to invalidate caches
            try:
                ex = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
                ex.add(o)
                sess["alts_exclude"] = list(ex)
                sess["alts_exclude_v"] = int(sess.get("alts_exclude_v") or 0) + 1
            except Exception:
                pass
            # Success panel and OOB updates (refresh compliance panel)
            # Compute ownership of the new card for UI badge update
            is_owned = (n in owned_set_helper())
            refresh = (
                '<div hx-get="/build/alternatives?name='
                + quote_plus(new_key)
                + f'&owned_only={owned_only_int}" hx-trigger="load delay:80ms" '
                'hx-target="closest .alts" hx-swap="outerHTML" aria-hidden="true"></div>'
            )
            html = (
                '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
                f'<div>Replaced <strong>{o_disp}</strong> with <strong>{new_key}</strong>.</div>'
                '<div class="muted" style="margin-top:.35rem;">Compliance panel will refresh.</div>'
                '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
                '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
                '</div>'
                + refresh +
                '</div>'
            )
            # Inline mutate the nearest card tile to reflect the new card without a rerun
            mutator = """
<script>
(function(){
    try{
        var panel = document.currentScript && document.currentScript.previousElementSibling && document.currentScript.previousElementSibling.classList && document.currentScript.previousElementSibling.classList.contains('alts') ? document.currentScript.previousElementSibling : null;
        if(!panel){ return; }
        var oldName = panel.getAttribute('data-old') || '';
        var newName = panel.getAttribute('data-new') || '';
        var isOwned = panel.getAttribute('data-owned') === '1';
        var isLocked = panel.getAttribute('data-locked') === '1';
        var tile = panel.closest('.card-tile');
        if(!tile) return;
        tile.setAttribute('data-card-name', newName);
        var img = tile.querySelector('img.card-thumb');
        if(img){
            var base = 'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=';
            img.src = base + 'normal';
            img.setAttribute('srcset',
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=small 160w, ' +
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=normal 488w, ' +
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=large 672w'
            );
            img.setAttribute('alt', newName + ' image');
            img.setAttribute('data-card-name', newName);
        }
        var nameEl = tile.querySelector('.name');
        if(nameEl){ nameEl.textContent = newName; }
        var own = tile.querySelector('.owned-badge');
        if(own){
            own.textContent = isOwned ? '✔' : '✖';
            own.title = isOwned ? 'Owned' : 'Not owned';
            tile.setAttribute('data-owned', isOwned ? '1' : '0');
        }
        tile.classList.toggle('locked', isLocked);
        var imgBtn = tile.querySelector('.img-btn');
        if(imgBtn){
            try{
                var valsAttr = imgBtn.getAttribute('hx-vals') || '{}';
                var obj = JSON.parse(valsAttr.replace(/&quot;/g, '"'));
                obj.name = newName;
                imgBtn.setAttribute('hx-vals', JSON.stringify(obj));
            }catch(e){}
        }
        var lockBtn = tile.querySelector('.lock-box .btn-lock');
        if(lockBtn){
            try{
                var v = lockBtn.getAttribute('hx-vals') || '{}';
                var o = JSON.parse(v.replace(/&quot;/g, '"'));
                o.name = newName;
                lockBtn.setAttribute('hx-vals', JSON.stringify(o));
            }catch(e){}
        }
    }catch(_){}
})();
</script>
"""
            chip = (
                f'<div id="last-action" hx-swap-oob="true">'
                f'<span class="chip" title="Click to dismiss">Replaced <strong>{o_disp}</strong> → <strong>{new_key}</strong></span>'
                f'</div>'
            )
            # OOB fetch to refresh compliance panel
            refresher = (
                '<div hx-get="/build/compliance" hx-target="#compliance-panel" hx-swap="outerHTML" '
                'hx-trigger="load" hx-swap-oob="true"></div>'
            )
            # Include data attributes on the panel div for the mutator script
            data_owned = '1' if is_owned else '0'
            data_locked = '1' if (n in locks) else '0'
            prefix = '<div class="alts"'
            replacement = (
                '<div class="alts" ' 
                + 'data-old="' + _esc(o_disp) + '" ' 
                + 'data-new="' + _esc(new_key) + '" '
                + 'data-owned="' + data_owned + '" '
                + 'data-locked="' + data_locked + '"'
            )
            html = html.replace(prefix, replacement, 1)
            return HTMLResponse(html + mutator + chip + refresher)
        except Exception:
            # Fall back to rerun guidance if inline swap fails
            pass
    # Fallback: advise rerun
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
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">Replaced <strong>{old}</strong> → <strong>{new}</strong></span>'
        f'</div>'
    )
    # Also add old to exclusions and bump version for future alt calls
    try:
        ex = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
        ex.add(o)
        sess["alts_exclude"] = list(ex)
        sess["alts_exclude_v"] = int(sess.get("alts_exclude_v") or 0) + 1
    except Exception:
        pass
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


@router.get("/compliance", response_class=HTMLResponse)
async def build_compliance_panel(request: Request) -> HTMLResponse:
    """Render a live Bracket compliance panel with manual enforcement controls.

    Computes compliance against the current builder state without exporting, attaches a non-destructive
    enforcement plan (swaps with added=None) when FAIL, and returns a reusable HTML partial.
    Returns empty content when no active build context exists.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        return HTMLResponse("")
    # Compute compliance snapshot in-memory and attach planning preview
    comp = None
    try:
        if hasattr(b, 'compute_and_print_compliance'):
            comp = b.compute_and_print_compliance(base_stem=None)
    except Exception:
        comp = None
    try:
        if comp:
            from ..services import orchestrator as orch
            comp = orch._attach_enforcement_plan(b, comp)
    except Exception:
        pass
    if not comp:
        return HTMLResponse("")
    # Build flagged metadata (role, owned) for visual tiles and role-aware alternatives
    # For combo violations, expand pairs into individual cards (exclude commander) so each can be replaced.
    flagged_meta: list[dict] = []
    try:
        cats = comp.get('categories') or {}
        owned_lower = owned_set_helper()
        lib = getattr(b, 'card_library', {}) or {}
        commander_l = str((sess.get('commander') or '')).strip().lower()
        # map category key -> display label
        labels = {
            'game_changers': 'Game Changers',
            'extra_turns': 'Extra Turns',
            'mass_land_denial': 'Mass Land Denial',
            'tutors_nonland': 'Nonland Tutors',
            'two_card_combos': 'Two-Card Combos',
        }
        seen_lower: set[str] = set()
        for key, cat in cats.items():
            try:
                status = str(cat.get('status') or '').upper()
                # Only surface tiles for WARN and FAIL
                if status not in {"WARN", "FAIL"}:
                    continue
                # For two-card combos, split pairs into individual cards and skip commander
                if key == 'two_card_combos' and status == 'FAIL':
                    # Prefer the structured combos list to ensure we only expand counted pairs
                    pairs = []
                    try:
                        for p in (comp.get('combos') or []):
                            if p.get('cheap_early'):
                                pairs.append((str(p.get('a') or '').strip(), str(p.get('b') or '').strip()))
                    except Exception:
                        pairs = []
                    # Fallback to parsing flagged strings like "A + B"
                    if not pairs:
                        try:
                            for s in (cat.get('flagged') or []):
                                if not isinstance(s, str):
                                    continue
                                parts = [x.strip() for x in s.split('+') if x and x.strip()]
                                if len(parts) == 2:
                                    pairs.append((parts[0], parts[1]))
                        except Exception:
                            pass
                    for a, bname in pairs:
                        for nm in (a, bname):
                            if not nm:
                                continue
                            nm_l = nm.strip().lower()
                            if nm_l == commander_l:
                                # Don't prompt replacing the commander
                                continue
                            if nm_l in seen_lower:
                                continue
                            seen_lower.add(nm_l)
                            entry = lib.get(nm) or lib.get(nm_l) or lib.get(str(nm).strip()) or {}
                            role = entry.get('Role') or ''
                            flagged_meta.append({
                                'name': nm,
                                'category': labels.get(key, key.replace('_',' ').title()),
                                'role': role,
                                'owned': (nm_l in owned_lower),
                                'severity': status,
                            })
                    continue
                # Default handling for list/tag categories
                names = [n for n in (cat.get('flagged') or []) if isinstance(n, str)]
                for nm in names:
                    nm_l = str(nm).strip().lower()
                    if nm_l in seen_lower:
                        continue
                    seen_lower.add(nm_l)
                    entry = lib.get(nm) or lib.get(str(nm).strip()) or lib.get(nm_l) or {}
                    role = entry.get('Role') or ''
                    flagged_meta.append({
                        'name': nm,
                        'category': labels.get(key, key.replace('_',' ').title()),
                        'role': role,
                        'owned': (nm_l in owned_lower),
                        'severity': status,
                    })
            except Exception:
                continue
    except Exception:
        flagged_meta = []
    # Render partial
    ctx2 = {"request": request, "compliance": comp, "flagged_meta": flagged_meta}
    return templates.TemplateResponse("build/_compliance_panel.html", ctx2)


@router.post("/enforce/apply", response_class=HTMLResponse)
async def build_enforce_apply(request: Request) -> HTMLResponse:
    """Apply bracket enforcement now using current locks as user guidance.

    This adds lock placeholders if needed, runs enforcement + re-export, reloads compliance, and re-renders Step 5.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Ensure build context exists
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        # No active build: show Step 5 with an error
        err_ctx = step5_error_ctx(request, sess, "No active build context to enforce.")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    # Ensure we have a CSV base stem for consistent re-exports
    base_stem = None
    try:
        csv_path = ctx.get("csv_path")
        if isinstance(csv_path, str) and csv_path:
            import os as _os
            base_stem = _os.path.splitext(_os.path.basename(csv_path))[0]
    except Exception:
        base_stem = None
    # If missing, export once to establish base
    if not base_stem:
        try:
            ctx["csv_path"] = b.export_decklist_csv()
            import os as _os
            base_stem = _os.path.splitext(_os.path.basename(ctx["csv_path"]))[0]
            # Also produce a text export for completeness
            ctx["txt_path"] = b.export_decklist_text(filename=base_stem + '.txt')
        except Exception:
            base_stem = None
    # Add lock placeholders into the library before enforcement so user choices are present
    try:
        locks = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        if locks:
            df = getattr(b, "_combined_cards_df", None)
            lib_l = {str(n).strip().lower() for n in getattr(b, 'card_library', {}).keys()}
            for lname in locks:
                if lname in lib_l:
                    continue
                target_name = None
                card_type = ''
                mana_cost = ''
                try:
                    if df is not None and not df.empty:
                        row = df[df['name'].astype(str).str.lower() == lname]
                        if not row.empty:
                            target_name = str(row.iloc[0]['name'])
                            card_type = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                            mana_cost = str(row.iloc[0].get('mana_cost', row.iloc[0].get('manaCost', '')) or '')
                except Exception:
                    target_name = None
                if target_name:
                    b.card_library[target_name] = {
                        'Count': 1,
                        'Card Type': card_type,
                        'Mana Cost': mana_cost,
                        'Role': 'Locked',
                        'SubRole': '',
                        'AddedBy': 'Lock',
                        'TriggerTag': '',
                    }
    except Exception:
        pass
    # Thread preferred replacements from context onto builder so enforcement can honor them
    try:
        pref = ctx.get("preferred_replacements") if isinstance(ctx, dict) else None
        if isinstance(pref, dict):
            setattr(b, 'preferred_replacements', dict(pref))
    except Exception:
        pass
    # Run enforcement + re-exports (tops up to 100 internally)
    try:
        rep = b.enforce_and_reexport(base_stem=base_stem, mode='auto')
    except Exception as e:
        err_ctx = step5_error_ctx(request, sess, f"Enforcement failed: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        _merge_hx_trigger(resp, {"step5:refresh": {"token": err_ctx.get("summary_token", 0)}})
        return resp
    # Reload compliance JSON and summary
    compliance = None
    try:
        if base_stem:
            import os as _os
            import json as _json
            comp_path = _os.path.join('deck_files', f"{base_stem}_compliance.json")
            if _os.path.exists(comp_path):
                with open(comp_path, 'r', encoding='utf-8') as _cf:
                    compliance = _json.load(_cf)
    except Exception:
        compliance = None
    # Rebuild Step 5 context (done state)
    # Ensure csv/txt paths on ctx reflect current base
    try:
        import os as _os
        ctx["csv_path"] = _os.path.join('deck_files', f"{base_stem}.csv") if base_stem else ctx.get("csv_path")
        ctx["txt_path"] = _os.path.join('deck_files', f"{base_stem}.txt") if base_stem else ctx.get("txt_path")
    except Exception:
        pass
    # Compute total_cards
    try:
        total_cards = 0
        for _n, _e in getattr(b, 'card_library', {}).items():
            try:
                total_cards += int(_e.get('Count', 1))
            except Exception:
                total_cards += 1
    except Exception:
        total_cards = None
    res = {
        "done": True,
        "label": "Complete",
        "log_delta": "",
        "idx": len(ctx.get("stages", []) or []),
        "total": len(ctx.get("stages", []) or []),
        "csv_path": ctx.get("csv_path"),
        "txt_path": ctx.get("txt_path"),
        "summary": getattr(b, 'build_deck_summary', lambda: None)(),
        "total_cards": total_cards,
        "added_total": 0,
        "compliance": compliance or rep,
    }
    page_ctx = step5_ctx_from_result(request, sess, res, status_text="Build complete", show_skipped=True)
    resp = templates.TemplateResponse(request, "build/_step5.html", page_ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": page_ctx.get("summary_token", 0)}})
    return resp


@router.get("/enforcement", response_class=HTMLResponse)
async def build_enforcement_fullpage(request: Request) -> HTMLResponse:
    """Full-page enforcement review: show compliance panel with swaps and controls."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        # No active build
        base = step5_empty_ctx(request, sess)
        resp = templates.TemplateResponse("build/_step5.html", base)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Compute compliance snapshot and attach planning preview
    comp = None
    try:
        if hasattr(b, 'compute_and_print_compliance'):
            comp = b.compute_and_print_compliance(base_stem=None)
    except Exception:
        comp = None
    try:
        if comp:
            from ..services import orchestrator as orch
            comp = orch._attach_enforcement_plan(b, comp)
    except Exception:
        pass
    try:
        summary_token = int(sess.get("step5_summary_token", 0))
    except Exception:
        summary_token = 0
    ctx2 = {"request": request, "compliance": comp, "summary_token": summary_token}
    resp = templates.TemplateResponse(request, "build/enforcement.html", ctx2)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    _merge_hx_trigger(resp, {"step5:refresh": {"token": ctx2.get("summary_token", 0)}})
    return resp
