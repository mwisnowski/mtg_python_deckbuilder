"""Bearer-token API key authentication for the `/api/v1` REST API.

Fully independent from the web UI's cookie-based session auth
(`code/web/services/auth.py`'s `mtg_session` cookie / `get_current_user()`).
The public API never reads that cookie -- see roadmap_28_public_api.md's
"Auth model" decision. Public (unauthenticated) endpoints simply don't
declare `get_api_user` as a dependency.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from code.type_definitions import User

from ...services.auth import check_and_record_rate_limit
from ...services.user_db import verify_api_key

# 60 req/min per API key, per the roadmap's Rate Limiting contract.
_RATE_LIMIT_MAX = 60
_RATE_LIMIT_WINDOW_S = 60

# auto_error=False so we control the error shape (our {ok:false,...} envelope
# via the sub-app's exception handler) instead of FastAPI's default 403.
# Declaring this as a dependency is also what makes Swagger UI (/api/v1/docs)
# show an "Authorize" padlock so the endpoints are testable from the browser.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_api_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> User:
    """Resolve the caller's User from the `Authorization: Bearer <key>` header.

    Raises 401 if the header is missing/malformed or the key is invalid or
    revoked, and 429 if the key has exceeded its rate limit.
    """
    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    key_plain = credentials.credentials.strip()

    user = verify_api_key(key_plain)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")

    # Rate limit by key, not by user -- a user with multiple keys/devices
    # gets independent budgets per key. Bucket on the key's hash (not the
    # plaintext) to avoid keeping plaintext keys resident in memory any
    # longer than the single request needs them for.
    bucket_key = f"apikey:{hashlib.sha256(key_plain.encode()).hexdigest()}"
    exceeded, remaining, reset_epoch = check_and_record_rate_limit(
        bucket_key, _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW_S
    )
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset_epoch
    if exceeded:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={
                "X-RateLimit-Limit": str(_RATE_LIMIT_MAX),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_epoch),
                "Retry-After": str(max(1, reset_epoch - int(time.time()))),
            },
        )
    return user
