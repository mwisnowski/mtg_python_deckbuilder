from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import json as _json
import time
import uuid
import logging

# Resolve template/static dirs relative to this file
_THIS_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _THIS_DIR / "templates"
_STATIC_DIR = _THIS_DIR / "static"

app = FastAPI(title="MTG Deckbuilder Web UI")

# Mount static if present
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Jinja templates
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Global template flags (env-driven)
def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

SHOW_LOGS = _as_bool(os.getenv("SHOW_LOGS"), False)
SHOW_SETUP = _as_bool(os.getenv("SHOW_SETUP"), True)

# Expose as Jinja globals so all templates can reference without passing per-view
templates.env.globals.update({
    "show_logs": SHOW_LOGS,
    "show_setup": SHOW_SETUP,
})

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
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").warning(
        f"HTTPException [rid={rid}] {exc.status_code} {request.method} {request.url.path}: {exc.detail}"
    )
    # Return JSON structure suitable for HTMX or API consumers
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status": exc.status_code,
            "detail": exc.detail,
            "request_id": rid,
            "path": str(request.url.path),
        },
        headers={"X-Request-ID": rid},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").error(
        f"Unhandled exception [rid={rid}] {request.method} {request.url.path}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status": 500,
            "detail": "Internal Server Error",
            "request_id": rid,
            "path": str(request.url.path),
        },
        headers={"X-Request-ID": rid},
    )

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
