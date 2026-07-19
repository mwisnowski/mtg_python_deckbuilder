"""Owned cards endpoints for the public REST API (R28 Milestone 7).

Reuses `owned_store.py` (the same per-user JSON-backed store as the HTML
Owned Library page) instead of duplicating parsing/persistence logic.
Auth required for every endpoint -- scoped to the caller's own directory
(`owned_cards/{user_id}/`).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from code.type_definitions import User

from ...services import owned_store as store
from ...utils.api_response import ok
from .auth import get_api_user

router = APIRouter(prefix="/owned", tags=["owned"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


@router.get("", summary="Get owned card list")
async def get_owned(request: Request, user: User = Depends(get_api_user)):
    """Return the caller's owned card list."""
    names = store.get_names(str(user["id"]))
    return ok({"names": names, "count": len(names)}, _rid(request))


@router.post("", summary="Replace owned card list")
async def upload_owned(request: Request, user: User = Depends(get_api_user)):
    """Replace the caller's owned card list.

    Body: plain text, one card name per line (optional leading count, e.g.
    "1x Sol Ring", is stripped -- same parsing as the HTML upload form).
    """
    body = await request.body()
    names = store.parse_txt_bytes(body)
    uid = str(user["id"])
    store.clear(uid)
    added, total = store.add_and_enrich(names, uid)
    return ok({"added": added, "total": total}, _rid(request))


@router.delete("", summary="Clear owned card list")
async def clear_owned(request: Request, user: User = Depends(get_api_user)):
    """Clear the caller's owned card list."""
    store.clear(str(user["id"]))
    return ok({"cleared": True}, _rid(request))
