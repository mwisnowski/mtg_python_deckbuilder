from __future__ import annotations

import threading
from typing import Optional
from fastapi import APIRouter, Request
from pathlib import Path
import json as _json
from fastapi.responses import HTMLResponse, JSONResponse
from ..app import templates
from ..services.orchestrator import _ensure_setup_ready

router = APIRouter(prefix="/setup")


def _kickoff_setup_async(force: bool = False):
    """Start setup/tagging in a background thread.

    Previously we passed a no-op output function, which hid downstream steps (e.g., theme export).
    Using print provides visibility in container logs and helps diagnose export issues.
    """
    def runner():
        try:
            print(f"[SETUP THREAD] Starting setup/tagging (force={force})...")
            _ensure_setup_ready(print, force=force)
            print("[SETUP THREAD] Setup/tagging completed successfully")
        except Exception as e:  # pragma: no cover - background best effort
            try:
                import traceback
                print(f"[SETUP THREAD] Setup thread failed: {e}")
                print(f"[SETUP THREAD] Traceback:\n{traceback.format_exc()}")
            except Exception:
                pass
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    print(f"[SETUP] Background thread started (force={force})")


@router.get("/running", response_class=HTMLResponse)
async def setup_running(request: Request, start: Optional[int] = 0, next: Optional[str] = None, force: Optional[bool] = None) -> HTMLResponse:
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
async def setup_start(request: Request):
    """POST endpoint for setup/tagging. Accepts JSON body {"force": true/false} or query string ?force=1"""
    force = False
    try:
        # Try to parse JSON body first
        try:
            body = await request.json()
            force = bool(body.get('force', False))
        except Exception:
            pass
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


@router.post("/download-github")
async def download_github():
    """Download pre-tagged database from GitHub similarity-cache-data branch."""
    import urllib.request
    import urllib.error
    import shutil
    from pathlib import Path
    
    try:
        # GitHub raw URLs for the similarity-cache-data branch
        base_url = "https://raw.githubusercontent.com/mwisnowski/mtg_python_deckbuilder/similarity-cache-data"
        
        files_to_download = [
            ("card_files/processed/all_cards.parquet", "card_files/processed/all_cards.parquet"),
            ("card_files/processed/commander_cards.parquet", "card_files/processed/commander_cards.parquet"),
            ("card_files/processed/.tagging_complete.json", "card_files/processed/.tagging_complete.json"),
            ("card_files/similarity_cache.parquet", "card_files/similarity_cache.parquet"),
            ("card_files/similarity_cache_metadata.json", "card_files/similarity_cache_metadata.json"),
        ]
        
        downloaded = []
        failed = []
        
        for remote_path, local_path in files_to_download:
            url = f"{base_url}/{remote_path}"
            dest = Path(local_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                print(f"[DOWNLOAD] Fetching {url}...")
                with urllib.request.urlopen(url, timeout=60) as response:
                    with dest.open('wb') as out_file:
                        shutil.copyfileobj(response, out_file)
                downloaded.append(local_path)
                print(f"[DOWNLOAD] Saved to {local_path}")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    print(f"[DOWNLOAD] File not found (404): {remote_path}")
                    failed.append(f"{remote_path} (not yet available)")
                else:
                    print(f"[DOWNLOAD] HTTP error {e.code}: {remote_path}")
                    failed.append(f"{remote_path} (HTTP {e.code})")
            except Exception as e:
                print(f"[DOWNLOAD] Failed to download {remote_path}: {e}")
                failed.append(f"{remote_path} ({str(e)[:50]})")
        
        if downloaded:
            msg = f"Downloaded {len(downloaded)} file(s) from GitHub"
            if failed:
                msg += f" ({len(failed)} unavailable)"
            return JSONResponse({
                "ok": True,
                "message": msg,
                "files": downloaded,
                "failed": failed
            })
        else:
            # No files downloaded - likely the branch doesn't exist yet
            return JSONResponse({
                "ok": False,
                "message": "Files not available yet. Run the 'Build Similarity Cache' workflow on GitHub first, or use 'Run Setup/Tagging' to build locally.",
                "failed": failed
            }, status_code=404)
            
    except Exception as e:
        print(f"[DOWNLOAD] Error: {e}")
        return JSONResponse({
            "ok": False,
            "message": f"Download failed: {str(e)}"
        }, status_code=500)


@router.get("/", response_class=HTMLResponse)
async def setup_index(request: Request) -> HTMLResponse:
    import code.settings as settings
    from code.file_setup.image_cache import ImageCache
    
    image_cache = ImageCache()
    return templates.TemplateResponse("setup/index.html", {
        "request": request,
        "similarity_enabled": settings.ENABLE_CARD_SIMILARITIES,
        "image_cache_enabled": image_cache.is_enabled()
    })
