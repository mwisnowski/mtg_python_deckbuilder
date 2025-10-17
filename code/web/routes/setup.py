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
    """Start setup/tagging in a background thread.

    Previously we passed a no-op output function, which hid downstream steps (e.g., theme export).
    Using print provides visibility in container logs and helps diagnose export issues.
    """
    def runner():
        try:
            _ensure_setup_ready(print, force=force)  # type: ignore[arg-type]
        except Exception as e:  # pragma: no cover - background best effort
            try:
                print(f"Setup thread failed: {e}")
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


@router.post("/rebuild-cards")
async def rebuild_cards():
    """Manually trigger card aggregation (all_cards.parquet, commander_cards.parquet, background_cards.parquet)."""
    def runner():
        try:
            print("Starting manual card aggregation...")
            from file_setup.card_aggregator import CardAggregator  # type: ignore
            import pandas as pd  # type: ignore
            import os
            
            aggregator = CardAggregator()
            
            # Aggregate all_cards.parquet
            stats = aggregator.aggregate_all('csv_files', 'card_files/all_cards.parquet')
            print(f"Aggregated {stats['total_cards']} cards into all_cards.parquet ({stats['file_size_mb']} MB)")
            
            # Convert commander_cards.csv to Parquet
            commander_csv = 'csv_files/commander_cards.csv'
            commander_parquet = 'card_files/commander_cards.parquet'
            if os.path.exists(commander_csv):
                df_cmd = pd.read_csv(commander_csv, comment='#', low_memory=False)
                for col in ["power", "toughness", "keywords"]:
                    if col in df_cmd.columns:
                        df_cmd[col] = df_cmd[col].astype(str)
                df_cmd.to_parquet(commander_parquet, engine="pyarrow", compression="snappy", index=False)
                print(f"Converted commander_cards.csv to Parquet ({len(df_cmd)} commanders)")
            
            # Convert background_cards.csv to Parquet
            background_csv = 'csv_files/background_cards.csv'
            background_parquet = 'card_files/background_cards.parquet'
            if os.path.exists(background_csv):
                df_bg = pd.read_csv(background_csv, comment='#', low_memory=False)
                for col in ["power", "toughness", "keywords"]:
                    if col in df_bg.columns:
                        df_bg[col] = df_bg[col].astype(str)
                df_bg.to_parquet(background_parquet, engine="pyarrow", compression="snappy", index=False)
                print(f"Converted background_cards.csv to Parquet ({len(df_bg)} backgrounds)")
            
            print("Card aggregation complete!")
        except Exception as e:
            print(f"Card aggregation failed: {e}")
    
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return JSONResponse({"ok": True, "message": "Card aggregation started"}, status_code=202)


@router.get("/", response_class=HTMLResponse)
async def setup_index(request: Request) -> HTMLResponse:
    import code.settings as settings
    return templates.TemplateResponse("setup/index.html", {
        "request": request,
        "similarity_enabled": settings.ENABLE_CARD_SIMILARITIES
    })
