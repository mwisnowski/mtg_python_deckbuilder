from __future__ import annotations

from typing import Dict, Tuple
import time as _t

# Lightweight in-memory TTL cache for alternatives fragments
_ALTS_CACHE: Dict[Tuple[str, str, bool], Tuple[float, str]] = {}
_ALTS_TTL_SECONDS = 60.0


def get_cached(key: tuple[str, str, bool]) -> str | None:
    try:
        ts, html = _ALTS_CACHE.get(key, (0.0, ""))
        if ts and (_t.time() - ts) < _ALTS_TTL_SECONDS:
            return html
    except Exception:
        return None
    return None


def set_cached(key: tuple[str, str, bool], html: str) -> None:
    try:
        _ALTS_CACHE[key] = (_t.time(), html)
    except Exception:
        pass
