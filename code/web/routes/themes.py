from __future__ import annotations

import json
from datetime import datetime as _dt
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi import BackgroundTasks
from ..services.orchestrator import _ensure_setup_ready, _run_theme_metadata_enrichment
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from ..services.theme_catalog_loader import (
    load_index,
    project_detail,
    slugify,
    filter_slugs_fast,
    summaries_for_slugs,
)
from ..services.theme_preview import get_theme_preview
from ..services.theme_catalog_loader import catalog_metrics, prewarm_common_filters
from ..services.theme_preview import preview_metrics
from ..services import theme_preview as _theme_preview_mod  # for error counters
import os
from fastapi import Body

# In-memory client metrics & structured log counters (diagnostics only)
CLIENT_PERF: dict[str, list[float]] = {
    "list_render_ms": [],  # list_ready - list_render_start
    "preview_load_ms": [],  # optional future measure (not yet emitted)
}
LOG_COUNTS: dict[str, int] = {}
MAX_CLIENT_SAMPLES = 500  # cap to avoid unbounded growth

router = APIRouter(prefix="/themes", tags=["themes"])  # /themes/status

# Reuse the main app's template environment so nav globals stay consistent.
try:  # circular-safe import: app defines templates before importing this router
    from ..app import templates as _templates
except Exception:  # Fallback (tests/minimal contexts)
    _templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'templates'))

THEME_LIST_PATH = Path("config/themes/theme_list.json")
CATALOG_DIR = Path("config/themes/catalog")
STATUS_PATH = Path("csv_files/.setup_status.json")
TAG_FLAG_PATH = Path("csv_files/.tagging_complete.json")


def _iso(ts: float | int | None) -> Optional[str]:
    if ts is None or ts <= 0:
        return None
    try:
        return _dt.fromtimestamp(ts).isoformat(timespec="seconds")
    except Exception:
        return None


def _load_status() -> Dict[str, Any]:
    try:
        if STATUS_PATH.exists():
            return json.loads(STATUS_PATH.read_text(encoding="utf-8") or "{}") or {}
    except Exception:
        pass
    return {}


def _load_fast_theme_list() -> Optional[list[dict[str, Any]]]:
    """Load precomputed lightweight theme list JSON if available.

    Expected structure: {"themes": [{"id": str, "theme": str, "short_description": str, ...}, ...]}
    Returns list or None on failure.
    """
    try:
        if THEME_LIST_PATH.exists():
            raw = json.loads(THEME_LIST_PATH.read_text(encoding="utf-8") or "{}")
            if isinstance(raw, dict):
                arr = raw.get("themes")
                if isinstance(arr, list):
                    # Shallow copy to avoid mutating original reference
                    # NOTE: Regression fix (2025-09-20): theme_list.json produced by current
                    # build pipeline does NOT include an explicit 'id' per theme (only 'theme').
                    # Earlier implementation required e.get('id') causing the fast path to
                    # treat the catalog as empty and show "No themes found." even though
                    # hundreds of themes exist. We now derive the id via slugify(theme) when
                    # missing, and also opportunistically compute a short_description snippet
                    # if absent (trim description to ~110 chars mirroring project_summary logic).
                    out: list[dict[str, Any]] = []
                    for e in arr:
                        if not isinstance(e, dict):
                            continue
                        theme_name = e.get("theme")
                        if not theme_name or not isinstance(theme_name, str):
                            continue
                        _id = e.get("id") or slugify(theme_name)
                        short_desc = e.get("short_description")
                        if not short_desc:
                            desc = e.get("description")
                            if isinstance(desc, str) and desc.strip():
                                sd = desc.strip()
                                if len(sd) > 110:
                                    sd = sd[:107].rstrip() + "…"
                                short_desc = sd
                        out.append({
                            "id": _id,
                            "theme": theme_name,
                            "short_description": short_desc,
                        })
                    # If we ended up with zero items (unexpected) fall back to None so caller
                    # will use full index logic instead of rendering empty state incorrectly.
                    if not out:
                        return None
                    return out
    except Exception:
        return None
    return None


@router.get("/suggest")
@router.get("/api/suggest")
async def theme_suggest(
    request: Request,
    q: str | None = None,
    limit: int | None = Query(10, ge=1, le=50),
):
    """Lightweight theme name suggestions for typeahead.

    Prefers the precomputed fast path (theme_list.json). Falls back to full index if unavailable.
    Returns a compact JSON: {"themes": ["<name>", ...]}.
    """
    try:
        # Optional rate limit using app helper if available
        rl_result = None
        try:
            from ..app import rate_limit_check
            rl_result = rate_limit_check(request, "suggest")
        except HTTPException as http_ex:  # propagate 429 with headers
            raise http_ex
        except Exception:
            rl_result = None
        lim = int(limit or 10)
        names: list[str] = []
        fast = _load_fast_theme_list()
        if fast is not None:
            try:
                items = fast
                if q:
                    ql = q.lower()
                    items = [e for e in items if isinstance(e.get("theme"), str) and ql in e["theme"].lower()]
                for e in items[: lim * 3]:  # pre-slice before unique
                    nm = e.get("theme")
                    if isinstance(nm, str):
                        names.append(nm)
            except Exception:
                names = []
        if not names:
            # Fallback to full index
            try:
                idx = load_index()
                slugs = filter_slugs_fast(idx, q=q)
                # summaries_for_slugs returns dicts including 'theme'
                infos = summaries_for_slugs(idx, slugs[: lim * 3])
                for inf in infos:
                    nm = inf.get("theme")
                    if isinstance(nm, str):
                        names.append(nm)
            except Exception:
                names = []
        # Deduplicate preserving order, then clamp
        seen: set[str] = set()
        out: list[str] = []
        for nm in names:
            if nm in seen:
                continue
            seen.add(nm)
            out.append(nm)
            if len(out) >= lim:
                break
        resp = JSONResponse({"themes": out})
        if rl_result:
            remaining, reset_epoch = rl_result
            try:
                resp.headers["X-RateLimit-Remaining"] = str(remaining)
                resp.headers["X-RateLimit-Reset"] = str(reset_epoch)
            except Exception:
                pass
        return resp
    except HTTPException as e:
        # Propagate FastAPI HTTPException (e.g., 429 with headers)
        raise e
    except Exception as e:
        return JSONResponse({"themes": [], "error": str(e)}, status_code=500)


def _load_tag_flag_time() -> Optional[float]:
    try:
        if TAG_FLAG_PATH.exists():
            data = json.loads(TAG_FLAG_PATH.read_text(encoding="utf-8") or "{}") or {}
            t = data.get("tagged_at")
            if isinstance(t, str) and t.strip():
                try:
                    return _dt.fromisoformat(t.strip()).timestamp()
                except Exception:
                    return None
    except Exception:
        return None
    return None


@router.get("/status")
async def theme_status():
    """Return current theme export status for the UI.

    Provides counts, mtimes, and freshness vs. tagging flag.
    """
    try:
        status = _load_status()
        theme_list_exists = THEME_LIST_PATH.exists()
        theme_list_mtime_s = THEME_LIST_PATH.stat().st_mtime if theme_list_exists else None
        theme_count: Optional[int] = None
        parse_error: Optional[str] = None
        if theme_list_exists:
            try:
                raw = json.loads(THEME_LIST_PATH.read_text(encoding="utf-8") or "{}") or {}
                if isinstance(raw, dict):
                    themes = raw.get("themes")
                    if isinstance(themes, list):
                        theme_count = len(themes)
            except Exception as e:  # pragma: no cover
                parse_error = f"parse_error: {e}"  # keep short
        yaml_catalog_exists = CATALOG_DIR.exists() and CATALOG_DIR.is_dir()
        yaml_file_count = 0
        if yaml_catalog_exists:
            try:
                yaml_file_count = len([p for p in CATALOG_DIR.iterdir() if p.suffix == ".yml"])
            except Exception:
                yaml_file_count = -1
        tagged_time = _load_tag_flag_time()
        stale = False
        if tagged_time and theme_list_mtime_s:
            # Stale if tagging flag is newer by > 1 second
            stale = tagged_time > (theme_list_mtime_s + 1)
        # Also stale if we expect a catalog (after any tagging) but have suspiciously few YAMLs (< 100)
        if yaml_catalog_exists and yaml_file_count >= 0 and yaml_file_count < 100:
            stale = True
        last_export_at = status.get("themes_last_export_at") or _iso(theme_list_mtime_s) or None
        resp = {
            "ok": True,
            "theme_list_exists": theme_list_exists,
            "theme_list_mtime": _iso(theme_list_mtime_s),
            "theme_count": theme_count,
            "yaml_catalog_exists": yaml_catalog_exists,
            "yaml_file_count": yaml_file_count,
            "stale": stale,
            "last_export_at": last_export_at,
            "last_export_fast_path": status.get("themes_last_export_fast_path"),
            "phase": status.get("phase"),
            "running": status.get("running"),
        }
        if parse_error:
            resp["parse_error"] = parse_error
        return JSONResponse(resp)
    except Exception as e:  # pragma: no cover
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/refresh")
async def theme_refresh(background: BackgroundTasks):
    """Force a theme export refresh without re-tagging if not needed.

    Runs setup readiness with force=False (fast-path export fallback will run). Returns immediately.
    """
    try:
        def _runner():
            try:
                _ensure_setup_ready(lambda _m: None, force=False)
            except Exception:
                pass
            try:
                _run_theme_metadata_enrichment()
            except Exception:
                pass
        background.add_task(_runner)
        return JSONResponse({"ok": True, "started": True})
    except Exception as e:  # pragma: no cover
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# --- Phase E Theme Catalog APIs ---

def _diag_enabled() -> bool:
    return (os.getenv("WEB_THEME_PICKER_DIAGNOSTICS") or "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/metrics")
async def theme_metrics():
    if not _diag_enabled():
        raise HTTPException(status_code=403, detail="diagnostics_disabled")
    try:
        idx = load_index()
        prewarm_common_filters()
        return JSONResponse({
            "ok": True,
            "etag": idx.etag,
            "catalog": catalog_metrics(),
            "preview": preview_metrics(),
            "client_perf": {
                "list_render_avg_ms": round(sum(CLIENT_PERF["list_render_ms"]) / len(CLIENT_PERF["list_render_ms"])) if CLIENT_PERF["list_render_ms"] else 0,
                "list_render_count": len(CLIENT_PERF["list_render_ms"]),
                "preview_load_avg_ms": round(sum(CLIENT_PERF["preview_load_ms"]) / len(CLIENT_PERF["preview_load_ms"])) if CLIENT_PERF["preview_load_ms"] else 0,
                "preview_load_batch_count": len(CLIENT_PERF["preview_load_ms"]),
            },
            "log_counts": LOG_COUNTS,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/", response_class=HTMLResponse)
async def theme_catalog_simple(request: Request):
    """Simplified catalog: list + search only (no per-row heavy data)."""
    return _templates.TemplateResponse("themes/catalog_simple.html", {"request": request})


@router.get("/{theme_id}", response_class=HTMLResponse)
async def theme_catalog_detail_page(theme_id: str, request: Request):
    """Full detail page for a single theme (standalone route)."""
    try:
        idx = load_index()
    except FileNotFoundError:
        return HTMLResponse("<div class='error'>Catalog unavailable.</div>", status_code=503)
    slug = slugify(theme_id)
    entry = idx.slug_to_entry.get(slug)
    if not entry:
        return HTMLResponse("<div class='error'>Not found.</div>", status_code=404)
    detail = project_detail(slug, entry, idx.slug_to_yaml, uncapped=False)
    # Strip diagnostics-only fields for public page
    detail.pop('has_fallback_description', None)
    detail.pop('editorial_quality', None)
    detail.pop('uncapped_synergies', None)
    # Build example + synergy commanders (reuse logic from preview)
    example_commanders = [c for c in (detail.get("example_commanders") or []) if isinstance(c, str)]
    synergy_commanders_raw = [c for c in (detail.get("synergy_commanders") or []) if isinstance(c, str)]
    seen = set(example_commanders)
    synergy_commanders: list[str] = []
    for c in synergy_commanders_raw:
        if c not in seen:
            synergy_commanders.append(c)
            seen.add(c)
    # Render via reuse of detail fragment inside a page shell
    return _templates.TemplateResponse(
        "themes/detail_page.html",
        {
            "request": request,
            "theme": detail,
            "diagnostics": False,
            "uncapped": False,
            "yaml_available": False,
            "example_commanders": example_commanders,
            "synergy_commanders": synergy_commanders,
            "standalone_page": True,
        },
    )


@router.get("/fragment/list", response_class=HTMLResponse)
async def theme_list_fragment(
    request: Request,
    q: str | None = None,
    archetype: str | None = None,
    bucket: str | None = None,
    colors: str | None = None,
    diagnostics: bool | None = None,
    synergy_mode: str | None = Query(None, description="Synergy display mode: 'capped' (default) or 'full'"),
    limit: int | None = Query(20, ge=1, le=100),
    offset: int | None = Query(0, ge=0),
):
    import time as _t
    t0 = _t.time()
    try:
        idx = load_index()
    except FileNotFoundError:
        return HTMLResponse("<div class='error'>Catalog unavailable.</div>", status_code=503)
    color_list = [c.strip() for c in colors.split(',')] if colors else None
    # Fast filtering (falls back only for legacy logic differences if needed)
    slugs = filter_slugs_fast(idx, q=q, archetype=archetype, bucket=bucket, colors=color_list)
    diag = _diag_enabled() and bool(diagnostics)
    lim = int(limit or 30)
    off = int(offset or 0)
    total = len(slugs)
    slice_slugs = slugs[off: off + lim]
    items = summaries_for_slugs(idx, slice_slugs)
    # Synergy display logic: default 'capped' mode (cap at 6) unless diagnostics & user explicitly requests full
    # synergy_mode can be 'full' to force uncapped in list (still diagnostics-gated to prevent layout spam in prod)
    mode = (synergy_mode or '').strip().lower()
    allow_full = (mode == 'full') and diag  # only diagnostics may request full
    SYNERGY_CAP = 6
    if not allow_full:
        for it in items:
            syns = it.get("synergies") or []
            if isinstance(syns, list) and len(syns) > SYNERGY_CAP:
                it["synergies_capped"] = True
                it["synergies_full"] = syns
                it["synergies"] = syns[:SYNERGY_CAP]
    if not diag:
        for it in items:
            it.pop('has_fallback_description', None)
            it.pop('editorial_quality', None)
    duration_ms = int(((_t.time() - t0) * 1000))
    resp = _templates.TemplateResponse(
        "themes/list_fragment.html",
        {
            "request": request,
            "items": items,
            "diagnostics": diag,
            "total": total,
            "limit": lim,
            "offset": off,
            "next_offset": off + lim if (off + lim) < total else None,
            "prev_offset": off - lim if off - lim >= 0 else None,
        },
    )
    resp.headers["X-ThemeCatalog-Filter-Duration-ms"] = str(duration_ms)
    resp.headers["X-ThemeCatalog-Index-ETag"] = idx.etag
    return resp


@router.get("/fragment/list_simple", response_class=HTMLResponse)
async def theme_list_simple_fragment(
    request: Request,
    q: str | None = None,
    limit: int | None = Query(100, ge=1, le=300),
    offset: int | None = Query(0, ge=0),
):
    """Lightweight list: only id, theme, short_description (for speed).

    Attempts fast path using precomputed theme_list.json; falls back to full index.
    """
    import time as _t
    t0 = _t.time()
    lim = int(limit or 100)
    off = int(offset or 0)
    fast_items = _load_fast_theme_list()
    fast_used = False
    items: list[dict[str, Any]] = []
    total = 0
    if fast_items is not None:
        fast_used = True
        # Filter (substring on theme only) if q provided
        if q:
            ql = q.lower()
            fast_items = [e for e in fast_items if isinstance(e.get("theme"), str) and ql in e["theme"].lower()]
        total = len(fast_items)
        slice_items = fast_items[off: off + lim]
        for e in slice_items:
            items.append({
                "id": e.get("id"),
                "theme": e.get("theme"),
                "short_description": e.get("short_description"),
            })
    else:
        # Fallback: load full index
        try:
            idx = load_index()
        except FileNotFoundError:
            return HTMLResponse("<div class='error'>Catalog unavailable.</div>", status_code=503)
        slugs = filter_slugs_fast(idx, q=q, archetype=None, bucket=None, colors=None)
        total = len(slugs)
        slice_slugs = slugs[off: off + lim]
        items_raw = summaries_for_slugs(idx, slice_slugs)
        for it in items_raw:
            items.append({
                "id": it.get("id"),
                "theme": it.get("theme"),
                "short_description": it.get("short_description"),
            })
    duration_ms = int(((_t.time() - t0) * 1000))
    resp = _templates.TemplateResponse(
        "themes/list_simple_fragment.html",
        {
            "request": request,
            "items": items,
            "total": total,
            "limit": lim,
            "offset": off,
            "next_offset": off + lim if (off + lim) < total else None,
            "prev_offset": off - lim if off - lim >= 0 else None,
        },
    )
    resp.headers['X-ThemeCatalog-Simple-Duration-ms'] = str(duration_ms)
    resp.headers['X-ThemeCatalog-Simple-Fast'] = '1' if fast_used else '0'
    # Consistency: expose same filter duration style header used by full list fragment so
    # tooling / DevTools inspection does not depend on which catalog view is active.
    resp.headers['X-ThemeCatalog-Filter-Duration-ms'] = str(duration_ms)
    return resp


@router.get("/fragment/detail/{theme_id}", response_class=HTMLResponse)
async def theme_detail_fragment(
    theme_id: str,
    diagnostics: bool | None = None,
    uncapped: bool | None = None,
    request: Request = None,
):
    try:
        idx = load_index()
    except FileNotFoundError:
        return HTMLResponse("<div class='error'>Catalog unavailable.</div>", status_code=503)
    slug = slugify(theme_id)
    entry = idx.slug_to_entry.get(slug)
    if not entry:
        return HTMLResponse("<div class='error'>Not found.</div>", status_code=404)
    diag = _diag_enabled() and bool(diagnostics)
    uncapped_enabled = bool(uncapped) and diag
    detail = project_detail(slug, entry, idx.slug_to_yaml, uncapped=uncapped_enabled)
    if not diag:
        detail.pop('has_fallback_description', None)
        detail.pop('editorial_quality', None)
        detail.pop('uncapped_synergies', None)
    return _templates.TemplateResponse(
        "themes/detail_fragment.html",
        {
            "request": request,
            "theme": detail,
            "diagnostics": diag,
            "uncapped": uncapped_enabled,
            "yaml_available": diag,  # gate by diagnostics flag
        },
    )


## (moved metrics route earlier to avoid collision with catch-all /{theme_id})


@router.get("/yaml/{theme_id}")
async def theme_yaml(theme_id: str):
    """Return raw YAML file for a theme (diagnostics/dev only)."""
    if not _diag_enabled():
        raise HTTPException(status_code=403, detail="diagnostics_disabled")
    try:
        idx = load_index()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="catalog_unavailable")
    slug = slugify(theme_id)
    # Attempt to locate via slug -> YAML map, fallback path guess
    y = idx.slug_to_yaml.get(slug)
    if not y:
        raise HTTPException(status_code=404, detail="yaml_not_found")
    # Reconstruct minimal YAML (we have dict already)
    import yaml as _yaml  # local import to keep top-level lean
    text = _yaml.safe_dump(y, sort_keys=False)
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    return HTMLResponse(text, headers=headers)


@router.get("/api/themes")
async def api_themes(
    request: Request,
    q: str | None = Query(None, description="Substring filter on theme or synergies"),
    archetype: str | None = Query(None, description="Filter by deck_archetype"),
    bucket: str | None = Query(None, description="Filter by popularity bucket"),
    colors: str | None = Query(None, description="Comma-separated color initials (e.g. G,W)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    diagnostics: bool | None = Query(None, description="Force diagnostics mode (allowed only if flag enabled)"),
):
    import time as _t
    t0 = _t.time()
    try:
        idx = load_index()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="catalog_unavailable")
    color_list = [c.strip() for c in colors.split(",") if c.strip()] if colors else None
    # Validate archetype quickly (fast path uses underlying entries anyway)
    if archetype:
        present_archetypes = {e.deck_archetype for e in idx.catalog.themes if e.deck_archetype}
        if archetype not in present_archetypes:
            slugs: list[str] = []
        else:
            slugs = filter_slugs_fast(idx, q=q, archetype=archetype, bucket=bucket, colors=color_list)
    else:
        slugs = filter_slugs_fast(idx, q=q, archetype=None, bucket=bucket, colors=color_list)
    total = len(slugs)
    slice_slugs = slugs[offset: offset + limit]
    items = summaries_for_slugs(idx, slice_slugs)
    diag = _diag_enabled() and bool(diagnostics)
    if not diag:
        # Strip diagnostics-only fields
        for it in items:
            # has_fallback_description is diagnostics-only
            it.pop("has_fallback_description", None)
            it.pop("editorial_quality", None)
    duration_ms = int(((_t.time() - t0) * 1000))
    headers = {
        "ETag": idx.etag,
        "Cache-Control": "no-cache",  # Clients may still conditional GET using ETag
        "X-ThemeCatalog-Filter-Duration-ms": str(duration_ms),
    }
    return JSONResponse({
        "ok": True,
        "count": total,
        "items": items,
        "next_offset": offset + limit if (offset + limit) < total else None,
        "stale": False,  # status already exposed elsewhere; keep placeholder for UI
        "generated_at": idx.catalog.metadata_info.generated_at if idx.catalog.metadata_info else None,
        "diagnostics": diag,
    }, headers=headers)


@router.get("/api/search")
async def api_theme_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(15, ge=1, le=50),
    include_synergies: bool = Query(False, description="Also match synergies (slower)"),
):
    """Lightweight search with tiered matching (exact > prefix > substring).

    Performance safeguards:
    - Stop scanning once we have >= limit and at least one exact/prefix.
    - Substring phase limited to first 250 themes unless still under limit.
    - Optional synergy search (off by default) to avoid wide fan-out of matches like 'aggro' in many synergy lists.
    """
    try:
        idx = load_index()
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "catalog_unavailable"}, status_code=503)
    qnorm = q.strip()
    if not qnorm:
        return JSONResponse({"ok": True, "items": []})
    qlower = qnorm.lower()
    exact: list[dict[str, Any]] = []
    prefix: list[dict[str, Any]] = []
    substr: list[dict[str, Any]] = []
    seen: set[str] = set()
    themes_iter = list(idx.catalog.themes)
    # Phase 1 + 2: exact / prefix
    for t in themes_iter:
        name = t.theme
        slug = slugify(name)
        lower_name = name.lower()
        if lower_name == qlower or slug == qlower:
            if slug not in seen:
                exact.append({"id": slug, "theme": name})
                seen.add(slug)
            continue
        if lower_name.startswith(qlower):
            if slug not in seen:
                prefix.append({"id": slug, "theme": name})
                seen.add(slug)
        if len(exact) + len(prefix) >= limit:
            break
    # Phase 3: substring (only if still room)
    if (len(exact) + len(prefix)) < limit:
        scan_limit = 250  # cap scan for responsiveness
        for t in themes_iter[:scan_limit]:
            name = t.theme
            slug = slugify(name)
            if slug in seen:
                continue
            if qlower in name.lower():
                substr.append({"id": slug, "theme": name})
                seen.add(slug)
            if (len(exact) + len(prefix) + len(substr)) >= limit:
                break
    ordered = exact + prefix + substr
    # Optional synergy search fill (lowest priority) if still space
    if include_synergies and len(ordered) < limit:
        remaining = limit - len(ordered)
        for t in themes_iter:
            if remaining <= 0:
                break
            slug = slugify(t.theme)
            if slug in seen:
                continue
            syns = getattr(t, 'synergies', None) or []
            try:
                # Only a quick any() scan to keep it cheap
                if any(qlower in s.lower() for s in syns):
                    ordered.append({"id": slug, "theme": t.theme})
                    seen.add(slug)
                    remaining -= 1
            except Exception:
                continue
    if len(ordered) > limit:
        ordered = ordered[:limit]
    return JSONResponse({"ok": True, "items": ordered})


@router.get("/api/theme/{theme_id}")
async def api_theme_detail(
    theme_id: str,
    uncapped: bool | None = Query(False, description="Return uncapped synergy set (diagnostics mode only)"),
    diagnostics: bool | None = Query(None, description="Diagnostics mode gating extra fields"),
):
    try:
        idx = load_index()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="catalog_unavailable")
    slug = slugify(theme_id)
    entry = idx.slug_to_entry.get(slug)
    if not entry:
        raise HTTPException(status_code=404, detail="theme_not_found")
    diag = _diag_enabled() and bool(diagnostics)
    detail = project_detail(slug, entry, idx.slug_to_yaml, uncapped=bool(uncapped) and diag)
    if not diag:
        # Remove diagnostics-only fields
        detail.pop("has_fallback_description", None)
        detail.pop("editorial_quality", None)
        detail.pop("uncapped_synergies", None)
    headers = {"ETag": idx.etag, "Cache-Control": "no-cache"}
    return JSONResponse({"ok": True, "theme": detail, "diagnostics": diag}, headers=headers)


@router.get("/api/theme/{theme_id}/preview")
async def api_theme_preview(
    theme_id: str,
    limit: int = Query(12, ge=1, le=30),
    colors: str | None = Query(None, description="Comma separated color filter (currently placeholder)"),
    commander: str | None = Query(None, description="Commander name to bias sampling (future)"),
):
    try:
        payload = get_theme_preview(theme_id, limit=limit, colors=colors, commander=commander)
    except KeyError:
        raise HTTPException(status_code=404, detail="theme_not_found")
    return JSONResponse({"ok": True, "preview": payload})




@router.get("/fragment/list", response_class=HTMLResponse)


# --- Preview Export Endpoints (CSV / JSON) ---
@router.get("/preview/{theme_id}/export.json")
async def export_preview_json(
    theme_id: str,
    limit: int = Query(12, ge=1, le=60),
    colors: str | None = None,
    commander: str | None = None,
    curated_only: bool | None = Query(False, description="If true, only curated example + curated synergy entries returned"),
):
    try:
        payload = get_theme_preview(theme_id, limit=limit, colors=colors, commander=commander)
    except KeyError:
        raise HTTPException(status_code=404, detail="theme_not_found")
    items = payload.get("sample", [])
    if curated_only:
        items = [i for i in items if any(r in {"example", "curated_synergy", "synthetic"} for r in (i.get("roles") or []))]
    return JSONResponse({
        "ok": True,
        "theme": payload.get("theme"),
        "theme_id": payload.get("theme_id"),
        "curated_only": bool(curated_only),
        "generated_at": payload.get("generated_at"),
        "limit": limit,
        "count": len(items),
        "items": items,
    })


@router.get("/preview/{theme_id}/export.csv")
async def export_preview_csv(
    theme_id: str,
    limit: int = Query(12, ge=1, le=60),
    colors: str | None = None,
    commander: str | None = None,
    curated_only: bool | None = Query(False, description="If true, only curated example + curated synergy entries returned"),
):
    import csv as _csv
    import io as _io
    try:
        payload = get_theme_preview(theme_id, limit=limit, colors=colors, commander=commander)
    except KeyError:
        raise HTTPException(status_code=404, detail="theme_not_found")
    rows = payload.get("sample", [])
    if curated_only:
        rows = [r for r in rows if any(role in {"example", "curated_synergy", "synthetic"} for role in (r.get("roles") or []))]
    buf = _io.StringIO()
    fieldnames = ["name", "roles", "score", "rarity", "mana_cost", "color_identity_list", "pip_colors", "reasons", "tags"]
    w = _csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({
            "name": r.get("name"),
            "roles": ";".join(r.get("roles") or []),
            "score": r.get("score"),
            "rarity": r.get("rarity"),
            "mana_cost": r.get("mana_cost"),
            "color_identity_list": ";".join(r.get("color_identity_list") or []),
            "pip_colors": ";".join(r.get("pip_colors") or []),
            "reasons": ";".join(r.get("reasons") or []),
            "tags": ";".join(r.get("tags") or []),
        })
    csv_text = buf.getvalue()
    from fastapi.responses import Response
    filename = f"preview_{theme_id}.csv"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "text/csv; charset=utf-8",
    }
    return Response(content=csv_text, media_type="text/csv", headers=headers)


# --- Export preview as deck seed (lightweight) ---
@router.get("/preview/{theme_id}/export_seed.json")
async def export_preview_seed(
    theme_id: str,
    limit: int = Query(12, ge=1, le=60),
    colors: str | None = None,
    commander: str | None = None,
    curated_only: bool | None = Query(False, description="If true, only curated example + curated synergy entries influence seed list"),
):
    """Return a minimal structure usable to bootstrap a deck build flow.

    Output:
      theme_id, theme, commander (if any), cards (list of names), curated (subset), generated_at.
    """
    try:
        payload = get_theme_preview(theme_id, limit=limit, colors=colors, commander=commander)
    except KeyError:
        raise HTTPException(status_code=404, detail="theme_not_found")
    items = payload.get("sample", [])
    def _is_curated(it: dict) -> bool:
        roles = it.get("roles") or []
        return any(r in {"example","curated_synergy"} for r in roles)
    if curated_only:
        items = [i for i in items if _is_curated(i)]
    card_names = [i.get("name") for i in items if i.get("name") and not i.get("name").startswith("[")]
    curated_names = [i.get("name") for i in items if _is_curated(i) and i.get("name")]  # exclude synthetic placeholders
    return JSONResponse({
        "ok": True,
        "theme": payload.get("theme"),
        "theme_id": payload.get("theme_id"),
        "commander": commander,
        "limit": limit,
        "curated_only": bool(curated_only),
        "generated_at": payload.get("generated_at"),
        "count": len(card_names),
        "cards": card_names,
        "curated": curated_names,
    })


# --- New: Client performance marks ingestion (Section E) ---
@router.post("/metrics/client")
async def ingest_client_metrics(request: Request, payload: dict[str, Any] = Body(...)):
    if not _diag_enabled():
        raise HTTPException(status_code=403, detail="diagnostics_disabled")
    try:
        events = payload.get("events")
        if not isinstance(events, list):
            return JSONResponse({"ok": False, "error": "invalid_events"}, status_code=400)
        for ev in events:
            if not isinstance(ev, dict):
                continue
            name = ev.get("name")
            dur = ev.get("duration_ms")
            if name == "list_render" and isinstance(dur, (int, float)) and dur >= 0:
                CLIENT_PERF["list_render_ms"].append(float(dur))
                if len(CLIENT_PERF["list_render_ms"]) > MAX_CLIENT_SAMPLES:
                    # Drop oldest half to keep memory bounded
                    CLIENT_PERF["list_render_ms"] = CLIENT_PERF["list_render_ms"][len(CLIENT_PERF["list_render_ms"])//2:]
            elif name == "preview_load_batch":
                # Aggregate average into samples list (store avg redundantly for now)
                avg_ms = ev.get("avg_ms")
                if isinstance(avg_ms, (int, float)) and avg_ms >= 0:
                    CLIENT_PERF["preview_load_ms"].append(float(avg_ms))
                    if len(CLIENT_PERF["preview_load_ms"]) > MAX_CLIENT_SAMPLES:
                        CLIENT_PERF["preview_load_ms"] = CLIENT_PERF["preview_load_ms"][len(CLIENT_PERF["preview_load_ms"])//2:]
        return JSONResponse({"ok": True, "ingested": len(events)})
    except Exception as e:  # pragma: no cover
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# --- New: Structured logging ingestion for cache/prefetch events (Section E) ---
@router.post("/log")
async def ingest_structured_log(request: Request, payload: dict[str, Any] = Body(...)):
    if not _diag_enabled():
        raise HTTPException(status_code=403, detail="diagnostics_disabled")
    try:
        event = payload.get("event")
        if not isinstance(event, str) or not event:
            return JSONResponse({"ok": False, "error": "missing_event"}, status_code=400)
        LOG_COUNTS[event] = LOG_COUNTS.get(event, 0) + 1
        if event == "preview_fetch_error":  # client-side fetch failure
            try:
                _theme_preview_mod._PREVIEW_REQUEST_ERROR_COUNT += 1  # type: ignore[attr-defined]
            except Exception:
                pass
        # Lightweight echo back
        return JSONResponse({"ok": True, "count": LOG_COUNTS[event]})
    except Exception as e:  # pragma: no cover
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
