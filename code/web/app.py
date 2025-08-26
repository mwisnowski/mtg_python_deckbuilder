from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import json as _json

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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request, "version": os.getenv("APP_VERSION", "dev")})


# Simple health check
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

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
