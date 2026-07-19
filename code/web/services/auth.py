"""Session cookie + token auth helpers for MTG Deckbuilder.

Cookie design:
  - Name: ``mtg_session``
  - HTTP-only, SameSite=Lax, Secure when ``SESSION_SECURE_COOKIES=1``
  - Value: URLSafeTimedSerializer-signed payload containing ``user_id``
  - TTL: 8 hours (SESSION_TTL_SECONDS from tasks.py)

Password-reset tokens:
  - Separate salt ("pwd-reset")
  - Max age: 3600 s (1 hour)
  - One-time use enforced at the route level (see auth route handler)

Environment:
  ``SESSION_SECRET`` — required in production; if unset, a random key is
  generated at startup with a WARN log. Rotating it invalidates all sessions.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
import warnings
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request, Response, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired  # type: ignore[import]
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from code.type_definitions import User
from .tasks import SESSION_TTL_SECONDS
from .user_db import get_user_by_id, get_guest_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Login rate limiter (in-memory, per-IP)
# ---------------------------------------------------------------------------

_RATE_WINDOW = 600   # 10 minutes
_RATE_MAX = 5        # max failed attempts before IP lockout

# Per-username lockout (more lenient window to reduce intentional DoS risk)
_UNAME_RATE_WINDOW = 900   # 15 minutes
_UNAME_RATE_MAX = 10

_failed_attempts: dict[str, deque[float]] = defaultdict(deque)
_failed_by_username: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For if present."""
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str) -> bool:
    """Return True if this IP has exceeded the failed-login threshold."""
    now = time.monotonic()
    with _rate_lock:
        q = _failed_attempts[ip]
        while q and now - q[0] > _RATE_WINDOW:
            q.popleft()
        return len(q) >= _RATE_MAX


def record_failed_login(ip: str) -> None:
    """Record a failed login attempt for this IP."""
    with _rate_lock:
        _failed_attempts[ip].append(time.monotonic())


def clear_failed_logins(ip: str) -> None:
    """Clear the failure counter after a successful login."""
    with _rate_lock:
        _failed_attempts.pop(ip, None)


def check_username_rate_limit(username: str) -> bool:
    """Return True if this username has exceeded the failed-login threshold."""
    now = time.monotonic()
    key = username.strip().lower()
    with _rate_lock:
        q = _failed_by_username[key]
        while q and now - q[0] > _UNAME_RATE_WINDOW:
            q.popleft()
        return len(q) >= _UNAME_RATE_MAX


def record_failed_username(username: str) -> None:
    """Record a failed login attempt for this username."""
    with _rate_lock:
        _failed_by_username[username.strip().lower()].append(time.monotonic())


def clear_failed_username(username: str) -> None:
    """Clear the username failure counter after a successful login."""
    with _rate_lock:
        _failed_by_username.pop(username.strip().lower(), None)


# ---------------------------------------------------------------------------
# Generic keyed rate limiter (R28: reused by the /api/v1 bearer-token auth
# instead of adding a new dependency like slowapi/limits)
# ---------------------------------------------------------------------------

_generic_hits: dict[str, deque[float]] = defaultdict(deque)
_generic_lock = Lock()


def check_and_record_rate_limit(bucket_key: str, max_count: int, window_seconds: int) -> tuple[bool, int, int]:
    """Increment the hit counter for *bucket_key* and report limit status.

    *bucket_key* should already encode whatever the limit is scoped to, e.g.
    ``f"apikey:{api_key_id}"`` or ``f"apikey-anon:{ip}"``.

    Returns ``(exceeded, remaining, reset_epoch)``. ``remaining`` is clamped
    to 0 when exceeded; ``reset_epoch`` is an approximate unix timestamp when
    the oldest hit in the window will fall out of it.
    """
    now = time.monotonic()
    with _generic_lock:
        q = _generic_hits[bucket_key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        q.append(now)
        count = len(q)
        oldest = q[0]
    exceeded = count > max_count
    remaining = max(0, max_count - count)
    reset_epoch = int(time.time() + max(0.0, window_seconds - (now - oldest)))
    return exceeded, remaining, reset_epoch


# ---------------------------------------------------------------------------
# Admin synthetic user
# ---------------------------------------------------------------------------

_ADMIN_ID = "__admin__"


def get_admin_synthetic_user() -> Optional[User]:
    """Build a synthetic admin User from env vars. Returns None if not configured."""
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return None
    return User(
        id=_ADMIN_ID,
        username=username,
        email="",
        password_hash="",
        is_guest=False,
        is_active=True,
        is_admin=True,
        created_at=0.0,
        updated_at=0.0,
    )


def is_admin_login(login: str, password: str) -> bool:
    """Return True if the supplied credentials match the configured admin account.

    Returns False immediately if ADMIN_ENABLED=0 (allows disabling the default
    env-based admin once a DB admin account has been created).
    """
    if os.getenv("ADMIN_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    admin_username = os.getenv("ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_username or not admin_password:
        return False
    return login.strip().lower() == admin_username.lower() and password == admin_password

# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------

_SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
if not _SESSION_SECRET:
    _SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET is not set — using a random key. "
        "All sessions will be invalidated on restart. "
        "Set SESSION_SECRET in production."
    )

_COOKIE_NAME = "mtg_session"
_SESSION_SALT = "mtg-session"
_RESET_SALT = "pwd-reset"
_RESET_MAX_AGE = 3600  # 1 hour

_USE_SECURE = os.getenv("SESSION_SECURE_COOKIES", "").strip().lower() in {"1", "true", "yes"}

_serializer = URLSafeTimedSerializer(_SESSION_SECRET)


# ---------------------------------------------------------------------------
# Session cookie helpers
# ---------------------------------------------------------------------------

def create_session_cookie(response: Response, user_id: str) -> None:
    """Sign and set the session cookie on *response*."""
    token = _serializer.dumps(user_id, salt=_SESSION_SALT)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_USE_SECURE,
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the session cookie."""
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")


def _decode_session_token(token: str) -> Optional[str]:
    """Return user_id from a valid, unexpired token; else None."""
    try:
        user_id: str = _serializer.loads(
            token, salt=_SESSION_SALT, max_age=SESSION_TTL_SECONDS
        )
        return user_id
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> User:
    """FastAPI dependency — returns authenticated User or falls back to guest.

    Never raises; always returns a User object.
    """
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        user_id = _decode_session_token(token)
        if user_id:
            if user_id == _ADMIN_ID:
                admin = get_admin_synthetic_user()
                if admin:
                    return admin
            else:
                user = get_user_by_id(user_id)
                if user and user["is_active"]:
                    return user
    # Fall back to guest
    guest = get_guest_user()
    if guest:
        return guest
    # Last resort: anonymous stub (should never happen post-init_db)
    raise HTTPException(status_code=503, detail="Auth service not initialised.")


async def get_required_user(request: Request) -> User:
    """FastAPI dependency — raises 401 if the user is not authenticated (guest counts as unauthenticated)."""
    user = await get_current_user(request)
    if user["is_guest"]:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


# ---------------------------------------------------------------------------
# Password-reset tokens
# ---------------------------------------------------------------------------

def create_reset_token(email: str) -> str:
    """Return a signed, time-limited reset token encoding *email*."""
    return _serializer.dumps(email.strip().lower(), salt=_RESET_SALT)


def verify_reset_token(token: str) -> Optional[str]:
    """Return the email from a valid, unexpired reset token; else None."""
    try:
        email: str = _serializer.loads(token, salt=_RESET_SALT, max_age=_RESET_MAX_AGE)
        return email
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AuthMiddleware(BaseHTTPMiddleware):
    """Inject ``request.state.current_user`` on every request.

    Falls back to guest (or None on error) so templates always have a user
    object to render the nav without crashing.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            request.state.current_user = await get_current_user(request)
        except Exception:
            request.state.current_user = None
        return await call_next(request)
