from __future__ import annotations

import threading
from typing import Optional
from fastapi import APIRouter, Request
from fastapi import Body
from pathlib import Path
import json as _json
from fastapi.responses import HTMLResponse, JSONResponse
from ..app import templates
from ..services.orchestrator import _ensure_setup_ready  # type: ignore

router = APIRouter(prefix="/setup")


def _kickoff_setup_async(force: bool = False):
    def runner():
        try:
            _ensure_setup_ready(lambda _m: None, force=force)  # type: ignore[arg-type]
        except Exception:
            pass
    t = threading.Thread(target=runner, daemon=True)
    t.start()


@router.get("/running", response_class=HTMLResponse)
async def setup_running(request: Request, start: Optional[int] = 0, next: Optional[str] = None, force: Optional[bool] = None) -> HTMLResponse:  # type: ignore[override]
    # Optionally start the setup/tagging in the background if requested
    try:
        if start and int(start) != 0:
            # honor optional force flag from query
            f = False
            try:
                if force is not None:
                    f = bool(force)
                else:
                    q_force = request.query_params.get('force')
                    if q_force is not None:
                        f = q_force.strip().lower() in {"1", "true", "yes", "on"}
            except Exception:
                f = False
            _kickoff_setup_async(force=f)
    except Exception:
        pass
    return templates.TemplateResponse("setup/running.html", {"request": request, "next_url": next})


@router.post("/start")
async def setup_start(request: Request, force: bool = Body(False)):  # accept JSON body {"force": true}
    try:
        # Allow query string override as well (?force=1)
        try:
            q_force = request.query_params.get('force')
            if q_force is not None:
                force = q_force.strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            pass
        # Write immediate status so UI reflects the start
        try:
            p = Path("csv_files")
            p.mkdir(parents=True, exist_ok=True)
            status = {"running": True, "phase": "setup", "message": "Starting setup/tagging...", "color": None}
            with (p / ".setup_status.json").open('w', encoding='utf-8') as f:
                _json.dump(status, f)
        except Exception:
            pass
        _kickoff_setup_async(force=bool(force))
        return JSONResponse({"ok": True, "started": True, "force": bool(force)}, status_code=202)
    except Exception:
        return JSONResponse({"ok": False}, status_code=500)


@router.get("/start")
async def setup_start_get(request: Request):
    """GET alias to start setup/tagging via query string (?force=1).

    Useful as a fallback from clients that cannot POST JSON.
    """
    try:
        # Determine force from query params
        force = False
        try:
            q_force = request.query_params.get('force')
            if q_force is not None:
                force = q_force.strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            pass
        # Write immediate status so UI reflects the start
        try:
            p = Path("csv_files")
            p.mkdir(parents=True, exist_ok=True)
            status = {"running": True, "phase": "setup", "message": "Starting setup/tagging...", "color": None}
            with (p / ".setup_status.json").open('w', encoding='utf-8') as f:
                _json.dump(status, f)
        except Exception:
            pass
        _kickoff_setup_async(force=bool(force))
        return JSONResponse({"ok": True, "started": True, "force": bool(force)}, status_code=202)
    except Exception:
        return JSONResponse({"ok": False}, status_code=500)


@router.get("/", response_class=HTMLResponse)
async def setup_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("setup/index.html", {"request": request})
