"""Auth routes: login, register, logout, forgot password, reset password."""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from ..app import templates
from ..services.auth import (
    create_session_cookie,
    clear_session_cookie,
    create_reset_token,
    verify_reset_token,
    is_admin_login,
    _ADMIN_ID,
    _get_client_ip,
    check_rate_limit,
    record_failed_login,
    clear_failed_logins,
    check_username_rate_limit,
    record_failed_username,
    clear_failed_username,
)
from ..services.user_db import (
    create_user,
    get_user_by_email,
    get_user_by_login,
    verify_password,
    update_password,
    set_reset_token_hash,
    consume_reset_token,
)
from ..services.email import send_password_reset, send_welcome_email
from ..services.audit_db import log_event as _audit

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _current_user(request: Request):
    return getattr(request.state, "current_user", None)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, reset: str = ""):
    if _current_user(request) and not _current_user(request).get("is_guest"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error": None,
        "reset_success": reset == "1",
    })


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    ip = _get_client_ip(request)
    if check_rate_limit(ip):
        _audit("rate_limited_ip", ip=ip, username=login)
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Too many failed login attempts. Please wait 10 minutes and try again.",
            "reset_success": False,
        }, status_code=429)
    if check_username_rate_limit(login):
        _audit("rate_limited_username", ip=ip, username=login)
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Too many failed login attempts. Please wait 15 minutes and try again.",
            "reset_success": False,
        }, status_code=429)
    # Check admin credentials first (bypasses DB entirely)
    if is_admin_login(login, password):
        clear_failed_logins(ip)
        clear_failed_username(login)
        _audit("login", username=login, ip=ip)
        resp = RedirectResponse("/", status_code=303)
        create_session_cookie(resp, _ADMIN_ID)
        return resp
    user = get_user_by_login(login)
    if not user or not verify_password(password, user["password_hash"]) or not user["is_active"]:
        record_failed_login(ip)
        record_failed_username(login)
        _audit("login_failed", ip=ip, username=login)
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Invalid username/email or password.",
            "reset_success": False,
        }, status_code=400)
    clear_failed_logins(ip)
    clear_failed_username(login)
    _audit("login", user_id=user["id"], username=user["username"], ip=ip)
    resp = RedirectResponse("/", status_code=303)
    create_session_cookie(resp, user["id"])
    return resp


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if _current_user(request) and not _current_user(request).get("is_guest"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "error": None,
    })


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    import os as _os
    admin_username = _os.getenv("ADMIN_USERNAME", "").strip().lower()
    if admin_username and username.strip().lower() == admin_username:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "That username is not available.",
        }, status_code=400)
    if password != confirm:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Passwords do not match.",
        }, status_code=400)
    if len(password) < 8:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Password must be at least 8 characters.",
        }, status_code=400)
    try:
        user = create_user(username.strip(), email.strip(), password)
    except ValueError as exc:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": str(exc),
        }, status_code=400)
    login_url = str(request.url_for("login_page"))
    try:
        await send_welcome_email(email.strip(), username.strip(), login_url)
    except Exception:
        logger.error("Welcome email failed for new user %s", username.strip())
    _audit("register", user_id=user["id"], username=user["username"], ip=_get_client_ip(request))
    resp = RedirectResponse("/", status_code=303)
    create_session_cookie(resp, user["id"])
    return resp


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(request: Request):
    user = _current_user(request)
    if user and not user.get("is_guest"):
        _audit("logout", user_id=user["id"], username=user["username"], ip=_get_client_ip(request))
    resp = RedirectResponse("/", status_code=303)
    clear_session_cookie(resp)
    return resp


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

@router.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request):
    return templates.TemplateResponse("auth/forgot.html", {
        "request": request,
        "submitted": False,
        "error": None,
    })


@router.post("/forgot", response_class=HTMLResponse)
async def forgot_post(request: Request, email: str = Form(...)):
    user = get_user_by_email(email)
    if user and not user["is_guest"] and user["is_active"]:
        token = create_reset_token(email)
        set_reset_token_hash(user["id"], _token_hash(token))
        reset_url = str(request.url_for("reset_page", token=token))
        try:
            await send_password_reset(email, reset_url)
        except Exception:
            logger.error("Failed to send reset email to %s", email)
    # Always show "submitted" to avoid email enumeration
    return templates.TemplateResponse("auth/forgot.html", {
        "request": request,
        "submitted": True,
        "error": None,
    })


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

@router.get("/reset/{token}", response_class=HTMLResponse, name="reset_page")
async def reset_page(request: Request, token: str):
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "This link is invalid or has expired.",
            "expired": True,
        })
    return templates.TemplateResponse("auth/reset.html", {
        "request": request,
        "token": token,
        "error": None,
        "expired": False,
    })


@router.post("/reset/{token}", response_class=HTMLResponse)
async def reset_post(
    request: Request,
    token: str,
    password: str = Form(...),
    confirm: str = Form(...),
):
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "This link is invalid or has expired.",
            "expired": True,
        })
    if password != confirm:
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "Passwords do not match.",
            "expired": False,
        }, status_code=400)
    if len(password) < 8:
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "Password must be at least 8 characters.",
            "expired": False,
        }, status_code=400)
    user = get_user_by_email(email)
    if not user:
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "Account not found.",
            "expired": True,
        })
    if not consume_reset_token(user["id"], _token_hash(token)):
        return templates.TemplateResponse("auth/reset.html", {
            "request": request,
            "token": token,
            "error": "This link has already been used.",
            "expired": True,
        })
    update_password(user["id"], password)
    _audit("password_reset_complete", user_id=user["id"], username=user["username"], ip=_get_client_ip(request))
    return RedirectResponse("/auth/login?reset=1", status_code=303)


# ---------------------------------------------------------------------------
# Profile (self-service password change)
# ---------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse, name="profile_page")
async def profile_page(request: Request):
    user = _current_user(request)
    if not user or user.get("is_guest"):
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("auth/profile.html", {
        "request": request,
        "error": None,
        "success": None,
    })


@router.post("/profile/password", response_class=HTMLResponse)
async def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm: str = Form(...),
):
    user = _current_user(request)
    if not user or user.get("is_guest"):
        return RedirectResponse("/auth/login", status_code=303)

    def _err(msg: str):
        return templates.TemplateResponse("auth/profile.html", {
            "request": request, "error": msg, "success": None,
        }, status_code=400)

    if user["id"] == _ADMIN_ID:
        return _err("The admin password is managed via environment variables and cannot be changed here.")
    if not verify_password(current_password, user["password_hash"]):
        return _err("Current password is incorrect.")
    if new_password != confirm:
        return _err("New passwords do not match.")
    if len(new_password) < 8:
        return _err("New password must be at least 8 characters.")
    update_password(user["id"], new_password)
    _audit("password_change", user_id=user["id"], username=user["username"], ip=_get_client_ip(request))
    return templates.TemplateResponse("auth/profile.html", {
        "request": request,
        "error": None,
        "success": "Password updated successfully.",
    })
