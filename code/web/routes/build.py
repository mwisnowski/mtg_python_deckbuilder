from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Any
import json
from urllib.parse import urlparse
from html import escape as _esc
from ..app import templates
from ..services.tasks import get_session, new_sid
from ..services.telemetry import log_commander_create_deck


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


def _step5_summary_placeholder_html(token: int, *, message: str | None = None) -> str:
    text = message or "Deck summary will appear after the build completes."
    return (
        f'<div id="deck-summary" data-summary '
        f'hx-get="/build/step5/summary?token={token}" '
        'hx-trigger="step5:refresh from:body" hx-swap="outerHTML">'
        f'<div class="muted" style="margin-top:1rem;">{_esc(text)}</div>'
        '</div>'
    )


def _current_builder_summary(sess: dict) -> Any | None:
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


router = APIRouter(prefix="/build")


@router.get("/", response_class=HTMLResponse)
async def build_index(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Seed commander from query string when arriving from commander browser
    q_commander = None
    try:
        q_commander = request.query_params.get("commander")
        if q_commander:
            # Persist a human-friendly commander name into session for the wizard
            sess["commander"] = str(q_commander)
            # Set flag to indicate this is a quick-build scenario
            sess["quick_build"] = True
    except Exception:
        pass
    return_url = None
    try:
        raw_return = request.query_params.get("return")
        if raw_return:
            parsed = urlparse(raw_return)
            if not parsed.scheme and not parsed.netloc and parsed.path:
                safe_path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
                safe_return = safe_path
                if parsed.query:
                    safe_return += f"?{parsed.query}"
                if parsed.fragment:
                    safe_return += f"#{parsed.fragment}"
                return_url = safe_return
    except Exception:
        return_url = None
    if q_commander:
        try:
            log_commander_create_deck(
                request,
                commander=str(q_commander),
                return_url=return_url,
            )
        except Exception:
            pass
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
    # Only pass commander to template if coming from commander browser (?commander= query param)
    # This prevents stale commander from being pre-filled on subsequent builds
    # The query param only exists on initial navigation from commander browser
    should_auto_fill = q_commander is not None
    
    resp = templates.TemplateResponse(
        request,
        "build/index.html",
        {
            "sid": sid,
            "commander": sess.get("commander") if should_auto_fill else None,
            "tags": sess.get("tags", []),
            "name": sess.get("custom_export_base"),
            "last_step": last_step,
            "return_url": return_url,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


# Support /build without trailing slash
@router.get("", response_class=HTMLResponse)
async def build_index_alias(request: Request) -> HTMLResponse:
    return await build_index(request)


@router.get("/batch-progress")
def batch_build_progress(request: Request, batch_id: str = Query(...)):
    """Poll endpoint for Batch Build progress. Returns either progress indicator or redirect to comparison."""
    import logging
    logger = logging.getLogger(__name__)
    
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    
    from ..services.build_cache import BuildCache
    
    batch_status = BuildCache.get_batch_status(sess, batch_id)
    logger.info(f"[Batch Progress Poll] batch_id={batch_id}, status={batch_status}")
    
    if not batch_status:
        return HTMLResponse('<div class="error">Batch not found. Please refresh.</div>')
    
    if batch_status["status"] == "completed":
        # All builds complete - redirect to comparison page
        response = HTMLResponse(f'<script>window.location.href = "/compare/{batch_id}";</script>')
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
        return response
    
    # Get config to determine color count for time estimate
    config = BuildCache.get_batch_config(sess, batch_id)
    commander_name = config.get("commander", "") if config else ""
    
    # Estimate time based on color count (from testing data)
    time_estimate = "1-3 minutes"
    if commander_name and config:
        # Try to get commander's color identity
        try:
            from ..services import orchestrator as orch
            cmd_data = orch.load_commander(commander_name)
            if cmd_data and "colorIdentity" in cmd_data:
                color_count = len(cmd_data.get("colorIdentity", []))
                if color_count <= 2:
                    time_estimate = "1-3 minutes"
                elif color_count == 3:
                    time_estimate = "2-4 minutes"
                else:  # 4-5 colors
                    time_estimate = "3-5 minutes"
        except Exception:
            pass  # Default to 1-3 if we can't determine
    
    # Build still running - return progress content partial only
    ctx = {
        "request": request,
        "batch_id": batch_id,
        "build_count": batch_status["count"],
        "completed": batch_status["completed"],
        "progress_pct": batch_status["progress_pct"],
        "status": f"Building deck {batch_status['completed'] + 1} of {batch_status['count']}..." if batch_status['completed'] < batch_status['count'] else "Finalizing...",
        "has_errors": batch_status["has_errors"],
        "error_count": batch_status["error_count"],
        "time_estimate": time_estimate
    }
    response = templates.TemplateResponse("build/_batch_progress_content.html", ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


# ==============================================================================
# Phase 5 Routes Moved to Focused Modules (Roadmap 9 M1)
# ==============================================================================
# Permalinks and Lock Management → build_permalinks.py:
#   - POST /build/lock - Card lock toggle
#   - GET /build/permalink - State serialization
#   - GET /build/from - State restoration
#
# Alternatives → build_alternatives.py:
#   - GET /build/alternatives - Role-based card suggestions
#
# Compliance and Replacement → build_compliance.py:
#   - POST /build/replace - Inline card replacement
#   - POST /build/replace/undo - Undo replacement
#   - GET /build/compare - Batch comparison stub
#   - GET /build/compliance - Compliance panel
#   - POST /build/enforce/apply - Apply enforcement
#   - GET /build/enforcement - Full-page enforcement
# ==============================================================================


@router.get("/land-diagnostics")
async def land_diagnostics(request: Request) -> JSONResponse:
    """Return the smart-land analysis report for the active build session.

    Reads _land_report_data produced by LandAnalysisMixin (Roadmap 14).
    Returns 204 when ENABLE_SMART_LANDS is off or no build is in session.
    """
    sid = request.cookies.get("sid") or ""
    sess = get_session(sid)
    from ..services.land_optimization_service import LandOptimizationService
    svc = LandOptimizationService()
    report = svc.get_land_report(sess)
    if not report:
        return JSONResponse({}, status_code=204)
    return JSONResponse(svc.format_for_api(report))
