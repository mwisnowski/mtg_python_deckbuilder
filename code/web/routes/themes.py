from __future__ import annotations

import json
from datetime import datetime as _dt
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter
from fastapi import BackgroundTasks
from ..services.orchestrator import _ensure_setup_ready, _run_theme_metadata_enrichment  # type: ignore
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/themes", tags=["themes"])  # /themes/status

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
                yaml_file_count = len([p for p in CATALOG_DIR.iterdir() if p.suffix == ".yml"])  # type: ignore[arg-type]
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
