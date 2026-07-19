"""Headless config management endpoints for the public REST API (R28 Milestone 9).

Reuses `code/web/routes/configs.py`'s `_config_dir`/`_list_configs` helpers
(the same per-user JSON config directory backing the HTML Configs page)
instead of duplicating them. Auth required for every endpoint here; configs
are always scoped to the calling API user's own directory
(`config/{user_id}/`).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from code.type_definitions import User

from ...utils.api_response import err, ok
from ..configs import _config_dir, _list_configs
from .auth import get_api_user

router = APIRouter(prefix="/configs", tags=["configs"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _resolve_config_path(user_id: str, name: str):
    """Return the resolved config path if it's a valid, existing JSON file
    within the user's config dir, else None. Guards against path traversal.
    """
    base = _config_dir(user_id)
    target = (base / name).resolve()
    try:
        if base != target and base not in target.parents:
            return None
    except Exception:
        return None
    if not (target.exists() and target.is_file() and target.suffix.lower() == ".json"):
        return None
    return target


@router.get("", summary="List saved configs")
async def list_configs(request: Request, user: User = Depends(get_api_user)):
    """List the caller's saved headless configs."""
    items = _list_configs(str(user["id"]))
    return ok({"configs": items}, _rid(request))


@router.get("/{name}", summary="Get a config")
async def get_config(name: str, request: Request, user: User = Depends(get_api_user)):
    """Return the raw JSON content of a saved config."""
    p = _resolve_config_path(str(user["id"]), name)
    if p is None:
        return err("Config not found.", "CONFIG_NOT_FOUND", 404, _rid(request))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return err(f"Failed to read config: {e}", "CONFIG_INVALID", 400, _rid(request))
    return ok({"name": p.name, "config": data}, _rid(request))


@router.post("/{name}", summary="Save or overwrite a config")
async def save_config(name: str, request: Request, user: User = Depends(get_api_user)):
    """Save/overwrite a config with the given name (JSON request body)."""
    if not name.lower().endswith(".json"):
        return err("Config name must end with .json", "INVALID_NAME", 400, _rid(request))
    try:
        payload: Dict[str, Any] = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object")
    except Exception as e:
        return err(f"Invalid JSON body: {e}", "INVALID_BODY", 400, _rid(request))

    uid = str(user["id"])
    base = _config_dir(uid)
    target = (base / name).resolve()
    if base != target and base not in target.parents:
        return err("Invalid config name.", "INVALID_NAME", 400, _rid(request))

    base.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ok({"name": target.name, "saved": True}, _rid(request))


@router.delete("/{name}", summary="Delete a config")
async def delete_config(name: str, request: Request, user: User = Depends(get_api_user)):
    """Delete a saved config."""
    p = _resolve_config_path(str(user["id"]), name)
    if p is None:
        return err("Config not found.", "CONFIG_NOT_FOUND", 404, _rid(request))
    try:
        p.unlink()
    except Exception as e:
        return err(f"Failed to delete config: {e}", "DELETE_FAILED", 500, _rid(request))
    return ok({"deleted": True}, _rid(request))
