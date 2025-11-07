"""Cache backend abstraction (Phase 2 extension) with Redis PoC.

The in-memory cache remains authoritative for adaptive eviction heuristics.
This backend layer provides optional read-through / write-through to Redis
for latency & CPU comparison. It is intentionally minimal:

Environment:
  THEME_PREVIEW_REDIS_URL=redis://host:port/db  -> enable PoC if redis-py importable
  THEME_PREVIEW_REDIS_DISABLE=1                 -> hard disable even if URL present

Behavior:
  - On store: serialize payload + metadata into JSON and SETEX with TTL.
  - On get (memory miss only): attempt Redis GET and rehydrate (respect TTL).
  - Failures are swallowed; metrics track attempts/hits/errors.

No eviction coordination is attempted; Redis TTL handles expiry. The goal is
purely observational at this stage.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, Tuple
import json
import os
import time

try:  # lazy optional dependency
    import redis
except Exception:  # pragma: no cover - absence path
    redis = None

_URL = os.getenv("THEME_PREVIEW_REDIS_URL")
_DISABLED = (os.getenv("THEME_PREVIEW_REDIS_DISABLE") or "").lower() in {"1","true","yes","on"}

_CLIENT = None
_INIT_ERR: str | None = None

def _init() -> None:
    global _CLIENT, _INIT_ERR
    if _CLIENT is not None or _INIT_ERR is not None:
        return
    if _DISABLED or not _URL or not redis:
        _INIT_ERR = "disabled_or_missing"
        return
    try:
        _CLIENT = redis.Redis.from_url(_URL, socket_timeout=0.25)
        # lightweight ping (non-fatal)
        try:
            _CLIENT.ping()
        except Exception:
            pass
    except Exception as e:  # pragma: no cover - network/dep issues
        _INIT_ERR = f"init_error:{e}"[:120]


def backend_info() -> Dict[str, Any]:
    return {
        "enabled": bool(_CLIENT),
        "init_error": _INIT_ERR,
        "url_present": bool(_URL),
    }

def _serialize(key: Tuple[str, int, str | None, str | None, str], payload: Dict[str, Any], build_cost_ms: float) -> str:
    return json.dumps({
        "k": list(key),
        "p": payload,
        "bc": build_cost_ms,
        "ts": time.time(),
    }, separators=(",", ":"))

def redis_store(key: Tuple[str, int, str | None, str | None, str], payload: Dict[str, Any], ttl_seconds: int, build_cost_ms: float) -> bool:
    _init()
    if not _CLIENT:
        return False
    try:
        data = _serialize(key, payload, build_cost_ms)
        # Compose a simple namespaced key; join tuple parts with '|'
        skey = "tpv:" + "|".join([str(part) for part in key])
        _CLIENT.setex(skey, ttl_seconds, data)
        return True
    except Exception:  # pragma: no cover
        return False

def redis_get(key: Tuple[str, int, str | None, str | None, str]) -> Optional[Dict[str, Any]]:
    _init()
    if not _CLIENT:
        return None
    try:
        skey = "tpv:" + "|".join([str(part) for part in key])
        raw: bytes | None = _CLIENT.get(skey)
        if not raw:
            return None
        obj = json.loads(raw.decode("utf-8"))
        # Expect shape from _serialize
        payload = obj.get("p")
        if not isinstance(payload, dict):
            return None
        return {
            "payload": payload,
            "_cached_at": float(obj.get("ts") or 0),
            "cached_at": float(obj.get("ts") or 0),
            "inserted_at": float(obj.get("ts") or 0),
            "last_access": float(obj.get("ts") or 0),
            "hit_count": 0,
            "build_cost_ms": float(obj.get("bc") or 0.0),
        }
    except Exception:  # pragma: no cover
        return None

__all__ = [
    "backend_info",
    "redis_store",
    "redis_get",
]