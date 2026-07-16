"""Admin routes — user management (create, change password, delete).

Only accessible when logged in as the admin account (is_admin=True).
Admin credentials come from ADMIN_USERNAME / ADMIN_PASSWORD env vars —
they are never stored in the database.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from ..app import templates
from ..services.user_db import (
    create_user,
    list_all_users,
    delete_user,
    update_password,
    get_user_by_id,
    set_user_admin,
    set_user_active,
    set_reset_token_hash,
)
from ..services.auth import create_reset_token, _get_client_ip
from ..services.email import send_account_created_email
from ..services.audit_db import log_event as _audit

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _require_admin(request: Request):
    """Return current user or redirect. Raises nothing — callers check the return."""
    user = getattr(request.state, "current_user", None)
    return user if (user and user.get("is_admin")) else None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    users = list_all_users()
    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "users": users,
        "error": None,
        "success": None,
    })


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------

@router.post("/users/create", response_class=HTMLResponse)
async def admin_create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    current = _require_admin(request)
    ip = _get_client_ip(request)
    users = list_all_users()
    try:
        new_user = create_user(username.strip(), email.strip(), password)
        # Send set-password email so admin doesn't need to share credentials
        try:
            token = create_reset_token(email.strip())
            set_reset_token_hash(new_user["id"], _token_hash(token))
            set_pw_url = str(request.url_for("reset_page", token=token))
            await send_account_created_email(email.strip(), username.strip(), set_pw_url)
        except Exception:
            logger.error("account-created email failed for %s", username.strip())
        _audit("admin_create", user_id=current["id"], username=current["username"], ip=ip,
               detail=f"created user '{username.strip()}'")
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": None,
            "success": f"User '{username.strip()}' created.",
        })
    except ValueError as exc:
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": str(exc),
            "success": None,
        }, status_code=400)


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/password", response_class=HTMLResponse)
async def admin_change_password(
    request: Request,
    user_id: str,
    new_password: str = Form(...),
):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    users = list_all_users()
    user = get_user_by_id(user_id)
    if not user:
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": "User not found.",
            "success": None,
        }, status_code=404)
    if len(new_password) < 8:
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": "Password must be at least 8 characters.",
            "success": None,
        }, status_code=400)
    try:
        update_password(user_id, new_password)
        current = _require_admin(request)
        _audit("admin_change_password", user_id=current["id"], username=current["username"],
               ip=_get_client_ip(request), detail=f"changed password for '{user['username']}'")
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": None,
            "success": f"Password updated for '{user['username']}'.",
        })
    except ValueError as exc:
        return templates.TemplateResponse("admin/index.html", {
            "request": request,
            "users": users,
            "error": str(exc),
            "success": None,
        }, status_code=400)


# ---------------------------------------------------------------------------
# Grant / revoke admin
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/grant-admin", response_class=HTMLResponse)
async def admin_grant_admin(request: Request, user_id: str):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    try:
        set_user_admin(user_id, True)
        current = _require_admin(request)
        users = list_all_users()
        user = get_user_by_id(user_id)
        _audit("admin_grant_admin", user_id=current["id"], username=current["username"],
               ip=_get_client_ip(request), detail=f"granted admin to '{user['username'] if user else user_id}'")
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": None, "success": f"Admin granted to '{user['username'] if user else user_id}'.",
        })
    except ValueError as exc:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": str(exc), "success": None,
        }, status_code=400)


@router.post("/users/{user_id}/revoke-admin", response_class=HTMLResponse)
async def admin_revoke_admin(request: Request, user_id: str):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    current = _require_admin(request)
    if current["id"] == user_id:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": "You cannot revoke your own admin access.", "success": None,
        }, status_code=400)
    try:
        set_user_admin(user_id, False)
        current = _require_admin(request)
        users = list_all_users()
        user = get_user_by_id(user_id)
        _audit("admin_revoke_admin", user_id=current["id"], username=current["username"],
               ip=_get_client_ip(request), detail=f"revoked admin from '{user['username'] if user else user_id}'")
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": None, "success": f"Admin revoked from '{user['username'] if user else user_id}'.",
        })
    except ValueError as exc:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": str(exc), "success": None,
        }, status_code=400)


# ---------------------------------------------------------------------------
# Toggle active
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/toggle-active", response_class=HTMLResponse)
async def admin_toggle_active(request: Request, user_id: str):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    current = _require_admin(request)
    if current["id"] == user_id:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": "You cannot deactivate your own account.", "success": None,
        }, status_code=400)
    target = get_user_by_id(user_id)
    if not target:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": "User not found.", "success": None,
        }, status_code=404)
    try:
        new_state = not target["is_active"]
        set_user_active(user_id, new_state)
        _audit("admin_toggle_active", user_id=current["id"], username=current["username"],
               ip=_get_client_ip(request),
               detail=f"{'activated' if new_state else 'deactivated'} '{target['username']}'")
        users = list_all_users()
        label = "activated" if new_state else "deactivated"
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": None, "success": f"User '{target['username']}' {label}.",
        })
    except ValueError as exc:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": str(exc), "success": None,
        }, status_code=400)


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/delete", response_class=HTMLResponse)
async def admin_delete_user(
    request: Request,
    user_id: str,
):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    current = _require_admin(request)
    target = get_user_by_id(user_id)
    try:
        delete_user(user_id)
        _audit("admin_delete", user_id=current["id"], username=current["username"],
               ip=_get_client_ip(request), detail=f"deleted user '{target['username'] if target else user_id}'")
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": None, "success": "User deleted.",
        })
    except ValueError as exc:
        users = list_all_users()
        return templates.TemplateResponse("admin/index.html", {
            "request": request, "users": users,
            "error": str(exc), "success": None,
        }, status_code=400)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit", response_class=HTMLResponse)
async def admin_audit(request: Request):
    if not _require_admin(request):
        return RedirectResponse("/auth/login", status_code=303)
    from ..services.audit_db import get_recent_events
    import datetime as _dt
    events = get_recent_events(200)
    for e in events:
        e["created_at_fmt"] = _dt.datetime.fromtimestamp(e["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse("admin/audit.html", {
        "request": request,
        "events": events,
    })
