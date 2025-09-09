from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import json as _json
import time
import uuid
import logging
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from typing import Any
from .services.combo_utils import detect_all as _detect_all

# Resolve template/static dirs relative to this file
_THIS_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _THIS_DIR / "templates"
_STATIC_DIR = _THIS_DIR / "static"

app = FastAPI(title="MTG Deckbuilder Web UI")
app.add_middleware(GZipMiddleware, minimum_size=500)

# Mount static if present
if _STATIC_DIR.exists():
    class CacheStatic(StaticFiles):
        async def get_response(self, path, scope):  # type: ignore[override]
            resp = await super().get_response(path, scope)
            try:
                # Add basic cache headers for static assets
                resp.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
            except Exception:
                pass
            return resp
    app.mount("/static", CacheStatic(directory=str(_STATIC_DIR)), name="static")

# Jinja templates
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Global template flags (env-driven)
def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

SHOW_LOGS = _as_bool(os.getenv("SHOW_LOGS"), False)
SHOW_SETUP = _as_bool(os.getenv("SHOW_SETUP"), True)
SHOW_DIAGNOSTICS = _as_bool(os.getenv("SHOW_DIAGNOSTICS"), False)
SHOW_VIRTUALIZE = _as_bool(os.getenv("WEB_VIRTUALIZE"), False)
ENABLE_THEMES = _as_bool(os.getenv("ENABLE_THEMES"), False)
ENABLE_PWA = _as_bool(os.getenv("ENABLE_PWA"), False)
ENABLE_PRESETS = _as_bool(os.getenv("ENABLE_PRESETS"), False)
ALLOW_MUST_HAVES = _as_bool(os.getenv("ALLOW_MUST_HAVES"), False)

# Theme default from environment: THEME=light|dark|system (case-insensitive). Defaults to system.
_THEME_ENV = (os.getenv("THEME") or "").strip().lower()
DEFAULT_THEME = "system"
if _THEME_ENV in {"light", "dark", "system"}:
    DEFAULT_THEME = _THEME_ENV

# Expose as Jinja globals so all templates can reference without passing per-view
templates.env.globals.update({
    "show_logs": SHOW_LOGS,
    "show_setup": SHOW_SETUP,
    "show_diagnostics": SHOW_DIAGNOSTICS,
    "virtualize": SHOW_VIRTUALIZE,
    "enable_themes": ENABLE_THEMES,
    "enable_pwa": ENABLE_PWA,
    "enable_presets": ENABLE_PRESETS,
    "allow_must_haves": ALLOW_MUST_HAVES,
    "default_theme": DEFAULT_THEME,
})

# --- Simple fragment cache for template partials (low-risk, TTL-based) ---
_FRAGMENT_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_FRAGMENT_TTL_SECONDS = 60.0

def render_cached(template_name: str, cache_key: str | None, /, **ctx: Any) -> str:
    """Render a template fragment with an optional cache key and short TTL.

    Intended for finished/immutable views (e.g., saved deck summaries). On error,
    falls back to direct rendering without cache interaction.
    """
    try:
        if cache_key:
            now = time.time()
            k = (template_name, str(cache_key))
            hit = _FRAGMENT_CACHE.get(k)
            if hit and (now - hit[0]) < _FRAGMENT_TTL_SECONDS:
                return hit[1]
            html = templates.get_template(template_name).render(**ctx)
            _FRAGMENT_CACHE[k] = (now, html)
            return html
        return templates.get_template(template_name).render(**ctx)
    except Exception:
        return templates.get_template(template_name).render(**ctx)

templates.env.globals["render_cached"] = render_cached

# --- Diagnostics: request-id and uptime ---
_APP_START_TIME = time.time()

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign or propagate a request id and attach to response headers."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception as ex:
        # Log and re-raise so FastAPI exception handlers can format the response.
        logging.getLogger("web").error(f"Unhandled error [rid={rid}]: {ex}", exc_info=True)
        raise
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request, "version": os.getenv("APP_VERSION", "dev")})


# Simple health check (hardened)
@app.get("/healthz")
async def healthz():
    try:
        version = os.getenv("APP_VERSION", "dev")
        uptime_s = int(time.time() - _APP_START_TIME)
        return {"status": "ok", "version": version, "uptime_seconds": uptime_s}
    except Exception:
        # Avoid throwing from health
        return {"status": "degraded"}

# System summary endpoint for diagnostics
@app.get("/status/sys")
async def status_sys():
    try:
        version = os.getenv("APP_VERSION", "dev")
        uptime_s = int(time.time() - _APP_START_TIME)
        server_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {
            "version": version,
            "uptime_seconds": uptime_s,
            "server_time_utc": server_time,
            "flags": {
                "SHOW_LOGS": bool(SHOW_LOGS),
                "SHOW_SETUP": bool(SHOW_SETUP),
                "SHOW_DIAGNOSTICS": bool(SHOW_DIAGNOSTICS),
                "ENABLE_THEMES": bool(ENABLE_THEMES),
                "ENABLE_PWA": bool(ENABLE_PWA),
                "ENABLE_PRESETS": bool(ENABLE_PRESETS),
                "ALLOW_MUST_HAVES": bool(ALLOW_MUST_HAVES),
                "DEFAULT_THEME": DEFAULT_THEME,
            },
        }
    except Exception:
        return {"version": "unknown", "uptime_seconds": 0, "flags": {}}

# Logs tail endpoint (read-only)
@app.get("/status/logs")
async def status_logs(
    tail: int = Query(200, ge=1, le=500),
    q: str | None = None,
    level: str | None = Query(None, description="Optional level filter: error|warning|info|debug"),
):
    try:
        if not SHOW_LOGS:
            # Hide when logs are disabled
            return JSONResponse({"error": True, "status": 403, "detail": "Logs disabled"}, status_code=403)
        log_path = Path('logs/deck_builder.log')
        if not log_path.exists():
            return JSONResponse({"lines": [], "count": 0})
        from collections import deque
        with log_path.open('r', encoding='utf-8', errors='ignore') as lf:
            lines = list(deque(lf, maxlen=tail))
        if q:
            ql = q.lower()
            lines = [ln for ln in lines if ql in ln.lower()]
        # Optional level filter (simple substring match)
        if level:
            lv = level.strip().lower()
            # accept warn as alias for warning
            if lv == "warn":
                lv = "warning"
            if lv in {"error", "warning", "info", "debug"}:
                lines = [ln for ln in lines if lv in ln.lower()]
        return JSONResponse({"lines": lines, "count": len(lines)})
    except Exception:
        return JSONResponse({"lines": [], "count": 0})

# Lightweight setup/tagging status endpoint
@app.get("/status/setup")
async def setup_status():
    try:
        p = Path("csv_files/.setup_status.json")
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = _json.load(f)
            # Attach a small log tail if available
            try:
                log_path = Path('logs/deck_builder.log')
                if log_path.exists():
                    tail_lines = []
                    with log_path.open('r', encoding='utf-8', errors='ignore') as lf:
                        # Read last ~100 lines efficiently
                        from collections import deque
                        tail = deque(lf, maxlen=100)
                        tail_lines = list(tail)
                    # Reduce noise: keep lines related to setup/tagging; fallback to last 30 if too few remain
                    try:
                        lowered = [ln for ln in tail_lines]
                        keywords = ["setup", "tag", "color", "csv", "initial setup", "tagging", "load_dataframe"]
                        filtered = [ln for ln in lowered if any(kw in ln.lower() for kw in keywords)]
                        if len(filtered) >= 5:
                            use_lines = filtered[-60:]
                        else:
                            use_lines = tail_lines[-30:]
                        data["log_tail"] = "".join(use_lines).strip()
                    except Exception:
                        data["log_tail"] = "".join(tail_lines).strip()
            except Exception:
                pass
            return JSONResponse(data)
        return JSONResponse({"running": False, "phase": "idle"})
    except Exception:
        return JSONResponse({"running": False, "phase": "error"})

# Routers
from .routes import build as build_routes  # noqa: E402
from .routes import configs as config_routes  # noqa: E402
from .routes import decks as decks_routes  # noqa: E402
from .routes import setup as setup_routes  # noqa: E402
from .routes import owned as owned_routes  # noqa: E402
app.include_router(build_routes.router)
app.include_router(config_routes.router)
app.include_router(decks_routes.router)
app.include_router(setup_routes.router)
app.include_router(owned_routes.router)

# --- Exception handling ---
def _wants_html(request: Request) -> bool:
    try:
        accept = request.headers.get('accept', '')
        is_htmx = request.headers.get('hx-request') == 'true'
        return ("text/html" in accept) and not is_htmx
    except Exception:
        return False


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").warning(
        f"HTTPException [rid={rid}] {exc.status_code} {request.method} {request.url.path}: {exc.detail}"
    )
    if _wants_html(request):
        # Friendly HTML page
        template = "errors/404.html" if exc.status_code == 404 else "errors/4xx.html"
        try:
            return templates.TemplateResponse(template, {"request": request, "status": exc.status_code, "detail": exc.detail, "request_id": rid}, status_code=exc.status_code, headers={"X-Request-ID": rid})
        except Exception:
            # Fallback plain text
            return PlainTextResponse(f"Error {exc.status_code}: {exc.detail}\nRequest-ID: {rid}", status_code=exc.status_code, headers={"X-Request-ID": rid})
    # JSON structure for HTMX/API
    return JSONResponse(status_code=exc.status_code, content={
        "error": True,
        "status": exc.status_code,
        "detail": exc.detail,
        "request_id": rid,
        "path": str(request.url.path),
    }, headers={"X-Request-ID": rid})


# Also handle Starlette's HTTPException (e.g., 404 route not found)
@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").warning(
        f"HTTPException* [rid={rid}] {exc.status_code} {request.method} {request.url.path}: {exc.detail}"
    )
    if _wants_html(request):
        template = "errors/404.html" if exc.status_code == 404 else "errors/4xx.html"
        try:
            return templates.TemplateResponse(template, {"request": request, "status": exc.status_code, "detail": exc.detail, "request_id": rid}, status_code=exc.status_code, headers={"X-Request-ID": rid})
        except Exception:
            return PlainTextResponse(f"Error {exc.status_code}: {exc.detail}\nRequest-ID: {rid}", status_code=exc.status_code, headers={"X-Request-ID": rid})
    return JSONResponse(status_code=exc.status_code, content={
        "error": True,
        "status": exc.status_code,
        "detail": exc.detail,
        "request_id": rid,
        "path": str(request.url.path),
    }, headers={"X-Request-ID": rid})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").error(
        f"Unhandled exception [rid={rid}] {request.method} {request.url.path}", exc_info=True
    )
    if _wants_html(request):
        try:
            return templates.TemplateResponse("errors/500.html", {"request": request, "request_id": rid}, status_code=500, headers={"X-Request-ID": rid})
        except Exception:
            return PlainTextResponse(f"Internal Server Error\nRequest-ID: {rid}", status_code=500, headers={"X-Request-ID": rid})
    return JSONResponse(status_code=500, content={
        "error": True,
        "status": 500,
        "detail": "Internal Server Error",
        "request_id": rid,
        "path": str(request.url.path),
    }, headers={"X-Request-ID": rid})

# Lightweight file download endpoint for exports
@app.get("/files")
async def get_file(path: str):
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return PlainTextResponse("File not found", status_code=404)
        # Only allow returning files within the workspace directory for safety
        # (best-effort: require relative to current working directory)
        try:
            cwd = Path.cwd().resolve()
            if cwd not in p.resolve().parents and p.resolve() != cwd:
                # Still allow if under deck_files or config
                allowed = any(seg in ("deck_files", "config", "logs") for seg in p.parts)
                if not allowed:
                    return PlainTextResponse("Access denied", status_code=403)
        except Exception:
            pass
        return FileResponse(path)
    except Exception:
        return PlainTextResponse("Error serving file", status_code=500)

# Serve /favicon.ico from static (prefer .ico, fallback to .png)
@app.get("/favicon.ico")
async def favicon():
    try:
        ico = _STATIC_DIR / "favicon.ico"
        png = _STATIC_DIR / "favicon.png"
        target = ico if ico.exists() else (png if png.exists() else None)
        if target is None:
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(str(target))
    except Exception:
        return PlainTextResponse("Error", status_code=500)


# Simple Logs page (optional, controlled by SHOW_LOGS)
@app.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    tail: int = Query(200, ge=1, le=500),
    q: str | None = None,
    level: str | None = Query(None),
) -> Response:
    if not SHOW_LOGS:
        # Respect feature flag
        raise HTTPException(status_code=404, detail="Not Found")
    # Reuse status_logs logic
    data = await status_logs(tail=tail, q=q, level=level)  # type: ignore[arg-type]
    lines: list[str]
    if isinstance(data, JSONResponse):
        payload = data.body
        try:
            parsed = _json.loads(payload)
            lines = parsed.get("lines", [])
        except Exception:
            lines = []
    else:
        lines = []
    return templates.TemplateResponse(
        "diagnostics/logs.html",
        {"request": request, "lines": lines, "tail": tail, "q": q or "", "level": (level or "all")},
    )


# Error trigger route for demoing HTMX/global error handling (feature-flagged)
@app.get("/diagnostics/trigger-error")
async def trigger_error(kind: str = Query("http")):
    if kind == "http":
        raise HTTPException(status_code=418, detail="Teapot: example error for testing")
    raise RuntimeError("Example unhandled error for testing")


@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_home(request: Request) -> HTMLResponse:
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse("diagnostics/index.html", {"request": request})


@app.get("/diagnostics/perf", response_class=HTMLResponse)
async def diagnostics_perf(request: Request) -> HTMLResponse:
    """Synthetic scroll performance page (diagnostics only)."""
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse("diagnostics/perf.html", {"request": request})

# --- Diagnostics: combos & synergies ---
@app.post("/diagnostics/combos")
async def diagnostics_combos(request: Request) -> JSONResponse:
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Diagnostics disabled")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    names = payload.get("names") or []
    combos_path = payload.get("combos_path") or "config/card_lists/combos.json"
    synergies_path = payload.get("synergies_path") or "config/card_lists/synergies.json"

    det = _detect_all(names, combos_path=combos_path, synergies_path=synergies_path)
    combos = det.get("combos", [])
    synergies = det.get("synergies", [])
    versions = det.get("versions", {"combos": None, "synergies": None})

    def as_dict_combo(c):
        return {
            "a": c.a,
            "b": c.b,
            "cheap_early": bool(c.cheap_early),
            "setup_dependent": bool(c.setup_dependent),
            "tags": list(c.tags or []),
        }

    def as_dict_syn(s):
        return {"a": s.a, "b": s.b, "tags": list(s.tags or [])}

    return JSONResponse(
        {
            "counts": {"combos": len(combos), "synergies": len(synergies)},
            "versions": {"combos": versions.get("combos"), "synergies": versions.get("synergies")},
            "combos": [as_dict_combo(c) for c in combos],
            "synergies": [as_dict_syn(s) for s in synergies],
        }
    )
