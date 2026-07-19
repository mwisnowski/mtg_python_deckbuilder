"""In-memory build-progress store for the public REST API (R28 Milestone 3).

Keyed by `build_id` (a fresh UUID per build), not by cookie session id --
the public API is bearer-token only and never touches `mtg_session`. Mirrors
the TTL/cleanup pattern of `code/web/services/tasks.py`'s `SessionManager`.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from .base import StateService

# Builds are short-lived; 1 hour is generous for polling clients to finish.
BUILD_TTL_SECONDS = 60 * 60


class ApiBuildStore(StateService):
    """Thread-safe build-state store, one entry per `build_id`."""

    def __init__(self, ttl_seconds: int = BUILD_TTL_SECONDS) -> None:
        super().__init__()
        self._ttl_seconds = ttl_seconds

    def new_build_id(self) -> str:
        return uuid.uuid4().hex

    def create_build(self, build_id: str, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            state = self.get_state(build_id)
            state.update(
                {
                    "user_id": user_id,
                    "status": "queued",
                    "progress_pct": 0,
                    "stage_label": None,
                    "stage_idx": 0,
                    "stage_total": 0,
                    "config": config,
                    "result": None,
                    "error": None,
                }
            )
            return state

    def get_build(self, build_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._state.get(build_id)

    def update_progress(
        self,
        build_id: str,
        *,
        status: Optional[str] = None,
        stage_idx: Optional[int] = None,
        stage_total: Optional[int] = None,
        stage_label: Optional[str] = None,
    ) -> None:
        with self._lock:
            state = self._state.get(build_id)
            if state is None:
                return
            if status is not None:
                state["status"] = status
            if stage_idx is not None:
                state["stage_idx"] = stage_idx
            if stage_total is not None:
                state["stage_total"] = stage_total
            if stage_total or state.get("stage_total"):
                total = stage_total if stage_total is not None else state.get("stage_total")
                idx = stage_idx if stage_idx is not None else state.get("stage_idx", 0)
                state["progress_pct"] = int(min(100, (idx / total) * 100)) if total else 0
            if stage_label is not None:
                state["stage_label"] = stage_label
            state["updated"] = time.time()

    def mark_done(self, build_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            state = self._state.get(build_id)
            if state is None:
                return
            state["status"] = "done"
            state["progress_pct"] = 100
            state["result"] = result
            state["updated"] = time.time()

    def mark_error(self, build_id: str, message: str) -> None:
        with self._lock:
            state = self._state.get(build_id)
            if state is None:
                return
            state["status"] = "error"
            state["error"] = message
            state["updated"] = time.time()

    def delete_build(self, build_id: str) -> bool:
        with self._lock:
            if build_id in self._state:
                del self._state[build_id]
                return True
            return False

    def _initialize_state(self, key: str) -> Dict[str, Any]:
        now = time.time()
        return {"created": now, "updated": now, "status": "queued"}

    def _should_cleanup(self, key: str, state: Dict[str, Any]) -> bool:
        now = time.time()
        updated = state.get("updated", now)
        return (now - updated) > self._ttl_seconds


# Module-level singleton, mirroring tasks.py's _get_manager() pattern.
_store: Optional[ApiBuildStore] = None


def _get_store() -> ApiBuildStore:
    global _store
    if _store is None:
        _store = ApiBuildStore()
    return _store


def create_build(user_id: str, config: Dict[str, Any]) -> str:
    store = _get_store()
    build_id = store.new_build_id()
    store.create_build(build_id, user_id, config)
    return build_id


def get_build(build_id: str) -> Optional[Dict[str, Any]]:
    return _get_store().get_build(build_id)


def update_progress(build_id: str, **kwargs: Any) -> None:
    _get_store().update_progress(build_id, **kwargs)


def mark_done(build_id: str, result: Dict[str, Any]) -> None:
    _get_store().mark_done(build_id, result)


def mark_error(build_id: str, message: str) -> None:
    _get_store().mark_error(build_id, message)


def delete_build(build_id: str) -> bool:
    return _get_store().delete_build(build_id)


def cleanup_expired() -> int:
    return _get_store().cleanup_state()
