from __future__ import annotations

import time
import uuid
from typing import Dict, Any, Optional

# Extremely simple in-memory session/task store for MVP
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_TTL_SECONDS = 60 * 60 * 8  # 8 hours


def new_sid() -> str:
    return uuid.uuid4().hex


def touch_session(sid: str) -> Dict[str, Any]:
    now = time.time()
    s = _SESSIONS.get(sid)
    if not s:
        s = {"created": now, "updated": now}
        _SESSIONS[sid] = s
    else:
        s["updated"] = now
    return s


def get_session(sid: Optional[str]) -> Dict[str, Any]:
    if not sid:
        sid = new_sid()
    return touch_session(sid)


def set_session_value(sid: str, key: str, value: Any) -> None:
    touch_session(sid)[key] = value


def get_session_value(sid: str, key: str, default: Any = None) -> Any:
    return touch_session(sid).get(key, default)


def cleanup_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _SESSIONS.items() if now - s.get("updated", 0) > _TTL_SECONDS]
    for sid in expired:
        try:
            del _SESSIONS[sid]
        except Exception:
            pass
