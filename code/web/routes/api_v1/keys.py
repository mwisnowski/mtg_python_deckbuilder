"""API key management routes -- `GET/POST /api/v1/keys`, `DELETE /api/v1/keys/{id}`.

See Milestone 2 of roadmap_28_public_api.md.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from code.type_definitions import User

from ...services.user_db import create_api_key, list_api_keys, revoke_api_key
from ...utils.api_response import err, ok
from .auth import get_api_user

router = APIRouter(prefix="/keys", tags=["keys"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


@router.get("", summary="List API keys")
async def list_keys(request: Request, user: User = Depends(get_api_user)):
    """List the caller's active API keys. Never reveals the key itself."""
    keys = list_api_keys(user["id"])
    return ok([dict(k) for k in keys], _rid(request))


@router.post("", status_code=201, summary="Create an API key")
async def create_key(request: Request, user: User = Depends(get_api_user)):
    """Create a new API key. The plaintext key is returned once and never again."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    label = (body or {}).get("label") if isinstance(body, dict) else None
    if label is not None and not isinstance(label, str):
        return err("label must be a string.", "INVALID_LABEL", 400, _rid(request))
    key_plain, key = create_api_key(user["id"], label)
    data = dict(key)
    data["key"] = key_plain
    return ok(data, _rid(request), status_code=201)


@router.delete("/{key_id}", summary="Revoke an API key")
async def delete_key(key_id: str, request: Request, user: User = Depends(get_api_user)):
    """Revoke one of the caller's own API keys."""
    try:
        revoke_api_key(key_id, user["id"])
    except ValueError:
        return err("API key not found.", "KEY_NOT_FOUND", 404, _rid(request))
    return ok({"revoked": True}, _rid(request))
