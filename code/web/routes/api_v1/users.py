"""User auth endpoints for the public REST API (R28 Milestone 10).

Reuses the same user store, password hashing, and rate-limiting helpers as
the HTML auth routes (`code/web/routes/auth.py`) instead of duplicating
them. `register`/`login`/`forgot` are unauthenticated; `logout`/`me`
require a valid API key.

Note: the admin synthetic login (`is_admin_login()` in `services/auth.py`)
is intentionally NOT supported here -- the admin account has no `users`
table row, and `api_keys.user_id` has a NOT NULL foreign key to
`users(id)`, so minting a key for it would fail.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from code.type_definitions import User

from ...services.auth import (
    _get_client_ip,
    check_rate_limit,
    check_username_rate_limit,
    clear_failed_logins,
    clear_failed_username,
    create_reset_token,
    record_failed_login,
    record_failed_username,
)
from ...services.email import send_password_reset, send_welcome_email
from ...services.user_db import (
    create_api_key,
    create_user,
    get_or_create_api_key,
    get_user_by_email,
    get_user_by_login,
    revoke_api_key_by_plain,
    set_reset_token_hash,
    verify_password,
)
from ...utils.api_response import err, ok
from .auth import _bearer_scheme, get_api_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RegisterBody(BaseModel):
    username: str
    email: str
    password: str = Field(min_length=8)


class LoginBody(BaseModel):
    login: str
    password: str
    device_label: Optional[str] = None


class ForgotBody(BaseModel):
    email: str


@router.post("/register", summary="Register a new user")
async def register(body: RegisterBody, request: Request):
    """Register a new user (mirrors the HTML `/auth/register` validation)."""
    import os

    admin_username = os.getenv("ADMIN_USERNAME", "").strip().lower()
    if admin_username and body.username.strip().lower() == admin_username:
        return err("That username is not available.", "USERNAME_UNAVAILABLE", 400, _rid(request))

    try:
        user = create_user(body.username.strip(), body.email.strip(), body.password)
    except ValueError as exc:
        return err(str(exc), "USER_EXISTS", 409, _rid(request))

    login_url = str(request.base_url).rstrip("/") + "/auth/login"
    try:
        await send_welcome_email(user["email"], user["username"], login_url)
    except Exception:
        pass

    return ok(
        {"id": user["id"], "username": user["username"], "email": user["email"]},
        _rid(request),
        status_code=201,
    )


@router.post("/login", summary="Log in and mint an API key")
async def login(body: LoginBody, request: Request):
    """Authenticate and mint (or reuse) an API key.

    Passing `device_label` reuses the existing active key for that label if
    one exists (avoids key sprawl across repeated logins from the same
    device); omitting it always mints a new key. The plaintext key is only
    ever returned once -- on creation (`api_key` is `null` when an existing
    labeled key was reused instead).
    """
    ip = _get_client_ip(request)
    if check_rate_limit(ip) or check_username_rate_limit(body.login):
        return err("Too many failed login attempts.", "RATE_LIMITED", 429, _rid(request))

    user = get_user_by_login(body.login)
    if not user or not verify_password(body.password, user["password_hash"]) or not user["is_active"]:
        record_failed_login(ip)
        record_failed_username(body.login)
        return err("Invalid username/email or password.", "INVALID_CREDENTIALS", 401, _rid(request))

    clear_failed_logins(ip)
    clear_failed_username(body.login)

    if body.device_label:
        key_plain, api_key = get_or_create_api_key(user["id"], body.device_label)
    else:
        key_plain, api_key = create_api_key(user["id"], body.device_label)

    return ok(
        {
            "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
            "api_key": key_plain,
            "key_id": api_key["id"],
            "label": api_key["label"],
        },
        _rid(request),
    )


@router.post("/logout", summary="Log out (revoke current key)")
async def logout(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    user: User = Depends(get_api_user),
):
    """Revoke the API key used to authenticate the current request."""
    if credentials is not None and credentials.credentials.strip():
        revoke_api_key_by_plain(credentials.credentials.strip())
    return ok({"loggedOut": True}, _rid(request))


@router.get("/me", summary="Get current user")
async def me(request: Request, user: User = Depends(get_api_user)):
    """Return the authenticated user's basic profile."""
    return ok(
        {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "is_admin": bool(user.get("is_admin", False)),
        },
        _rid(request),
    )


@router.post("/forgot", summary="Request a password reset")
async def forgot(body: ForgotBody, request: Request):
    """Trigger a password reset email. Always reports success (no email enumeration)."""
    user = get_user_by_email(body.email)
    if user and not user["is_guest"] and user["is_active"]:
        token = create_reset_token(body.email)
        set_reset_token_hash(user["id"], _token_hash(token))
        reset_url = str(request.base_url).rstrip("/") + f"/auth/reset/{token}"
        try:
            await send_password_reset(body.email, reset_url)
        except Exception:
            pass
    return ok({"submitted": True}, _rid(request))
