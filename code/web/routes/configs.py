from __future__ import annotations

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from pathlib import Path
import os
import json
from ..app import templates
from ..services.build_utils import owned_set as owned_set_helper, owned_names as owned_names_helper
from ..services.summary_utils import summary_ctx
from ..services import orchestrator as orch


router = APIRouter(prefix="/configs")


def _user_id(request) -> str:
    """Return the scoped directory name for the current user."""
    u = getattr(getattr(request, "state", None), "current_user", None)
    if u and not u.get("is_guest") and u.get("id"):
        return str(u["id"])
    return "guest"


def _deck_dir(user_id: str = "guest") -> Path:
    p = os.getenv("DECK_EXPORTS")
    if p:
        return (Path(p) / user_id).resolve()
    return (Path.cwd() / "deck_files" / user_id).resolve()


def _config_dir(user_id: str = "guest") -> Path:
    # Prefer explicit env var if provided, else default to ./config/{user_id}
    p = os.getenv("DECK_CONFIG")
    if p:
        pp = Path(p)
        base = pp.parent if pp.suffix else pp
        return (base / user_id).resolve()
    return (Path.cwd() / "config" / user_id).resolve()


def _list_configs(user_id: str = "guest") -> list[dict]:
    d = _config_dir(user_id)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    items: list[dict] = []
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        meta = {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime}
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            meta["commander"] = data.get("commander")
            tags = [t for t in [data.get("primary_tag"), data.get("secondary_tag"), data.get("tertiary_tag")] if t]
            meta["tags"] = tags
            meta["bracket_level"] = data.get("bracket_level")
        except Exception:
            pass
        items.append(meta)
    return items


@router.get("/", response_class=HTMLResponse)
async def configs_index(request: Request) -> HTMLResponse:
    uid = _user_id(request)
    items = _list_configs(uid)
    # Load example deck.json from the config directory, if present
    example_json = None
    example_name = "deck.json"
    try:
        example_path = _config_dir(uid) / example_name
        if example_path.exists() and example_path.is_file():
            example_json = example_path.read_text(encoding="utf-8")
    except Exception:
        example_json = None
    return templates.TemplateResponse(
        "configs/index.html",
        {"request": request, "items": items, "example_json": example_json, "example_name": example_name},
    )


@router.get("/view", response_class=HTMLResponse)
async def configs_view(request: Request, name: str) -> HTMLResponse:
    uid = _user_id(request)
    base = _config_dir(uid)
    p = (base / name).resolve()
    # Safety: ensure the resolved path is within config dir
    try:
        if base not in p.parents and p != base:
            raise ValueError("Access denied")
    except Exception:
        pass
    if not (p.exists() and p.is_file() and p.suffix.lower() == ".json"):
        return templates.TemplateResponse(
            "configs/index.html",
            {"request": request, "items": _list_configs(uid), "error": "Config not found."},
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return templates.TemplateResponse(
            "configs/index.html",
            {"request": request, "items": _list_configs(uid), "error": f"Failed to read JSON: {e}"},
        )
    return templates.TemplateResponse(
        "configs/view.html",
        {"request": request, "path": str(p), "name": p.name, "data": data},
    )


@router.post("/run", response_class=HTMLResponse)
async def configs_run(request: Request, name: str = Form(...), use_owned_only: str | None = Form(None)) -> HTMLResponse:
    uid = _user_id(request)
    base = _config_dir(uid)
    p = (base / name).resolve()
    try:
        if base not in p.parents and p != base:
            raise ValueError("Access denied")
    except Exception:
        pass
    if not (p.exists() and p.is_file() and p.suffix.lower() == ".json"):
        return templates.TemplateResponse(
            "configs/index.html",
            {"request": request, "items": _list_configs(uid), "error": "Config not found."},
        )
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return templates.TemplateResponse(
            "configs/index.html",
            {"request": request, "items": _list_configs(uid), "error": f"Failed to read JSON: {e}"},
        )

    commander = cfg.get("commander", "")
    tags = [t for t in [cfg.get("primary_tag"), cfg.get("secondary_tag"), cfg.get("tertiary_tag")] if t]
    bracket = int(cfg.get("bracket_level") or 0)
    ideals = cfg.get("ideal_counts", {}) or {}
    # Optional combine mode for tags (AND/OR); support a few aliases
    try:
        tag_mode = (str(cfg.get("tag_mode") or cfg.get("combine_mode") or cfg.get("mode") or "AND").upper())
        if tag_mode not in ("AND", "OR"):
            tag_mode = "AND"
    except Exception:
        tag_mode = "AND"

    # Optional owned-only for headless runs via JSON flag or form override
    owned_flag = False
    try:
        uo = cfg.get("use_owned_only")
        if isinstance(uo, bool):
            owned_flag = uo
        elif isinstance(uo, str):
            owned_flag = uo.strip().lower() in ("1","true","yes","on")
    except Exception:
        owned_flag = False

    # Form override takes precedence if provided
    if use_owned_only is not None:
        owned_flag = str(use_owned_only).strip().lower() in ("1","true","yes","on")

    owned_names = owned_names_helper() if owned_flag else None

    # Optional combos preferences
    prefer_combos = False
    try:
        pc = cfg.get("prefer_combos")
        if isinstance(pc, bool):
            prefer_combos = pc
        elif isinstance(pc, str):
            prefer_combos = pc.strip().lower() in ("1","true","yes","on")
    except Exception:
        prefer_combos = False
    combo_target_count = None
    try:
        ctc = cfg.get("combo_target_count")
        if isinstance(ctc, int):
            combo_target_count = ctc
        elif isinstance(ctc, str) and ctc.strip().isdigit():
            combo_target_count = int(ctc.strip())
    except Exception:
        combo_target_count = None
    combo_balance = None
    try:
        cb = cfg.get("combo_balance")
        if isinstance(cb, str) and cb.strip().lower() in ("early","late","mix"):
            combo_balance = cb.strip().lower()
    except Exception:
        combo_balance = None

    # Run build headlessly with orchestrator
    res = orch.run_build(
        commander=commander,
        tags=tags,
        bracket=bracket,
        ideals=ideals,
        tag_mode=tag_mode,
        use_owned_only=owned_flag,
        owned_names=owned_names,
        # Thread combo prefs through staged headless run
        prefer_combos=prefer_combos,
        combo_target_count=combo_target_count,
        combo_balance=combo_balance,
        deck_dir=str(_deck_dir(uid)),
    )

    if not res.get("ok"):
        return templates.TemplateResponse(
            "configs/run_result.html",
            {
                "request": request,
                "ok": False,
                "error": res.get("error") or "Build failed",
                "log": res.get("log", ""),
                "cfg_name": p.name,
                "commander": commander,
                "tag_mode": tag_mode,
                "use_owned_only": owned_flag,
                "owned_set": owned_set_helper(),
            },
        )
    ctx = {
        "request": request,
        "ok": True,
        "log": res.get("log", ""),
        "csv_path": res.get("csv_path"),
        "txt_path": res.get("txt_path"),
        "summary": res.get("summary"),
        "cfg_name": p.name,
        "commander": commander,
        "tag_mode": tag_mode,
        "use_owned_only": owned_flag,
    }
    ctx.update(summary_ctx(summary=res.get("summary"), commander=commander, tags=tags))
    return templates.TemplateResponse("configs/run_result.html", ctx)



@router.post("/upload", response_class=HTMLResponse)
async def configs_upload(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    # Optional helper: allow uploading a JSON config
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
        # Minimal validation
        if not data.get("commander"):
            raise ValueError("Missing 'commander'")
    except Exception as e:
        return templates.TemplateResponse(
            "configs/index.html",
            {"request": request, "items": _list_configs(_user_id(request)), "error": f"Invalid JSON: {e}"},
        )
    # Save to config dir with original filename (or unique)
    uid = _user_id(request)
    d = _config_dir(uid)
    d.mkdir(parents=True, exist_ok=True)
    fname = file.filename or "config.json"
    out = d / fname
    i = 1
    while out.exists():
        stem = out.stem
        out = d / f"{stem}_{i}.json"
        i += 1
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return templates.TemplateResponse(
        "configs/index.html",
        {"request": request, "items": _list_configs(uid), "notice": f"Uploaded {out.name}"},
    )
