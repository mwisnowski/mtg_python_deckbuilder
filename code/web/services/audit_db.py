"""Audit log for auth/admin events — stored in the same users.db as the user table.

Events are append-only. The table is pruned to a rolling 10 000-row cap
on each insert to prevent unbounded growth.
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_DB_PATH = _DATA_DIR / "users.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS auth_events (
    id          TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    user_id     TEXT,
    username    TEXT,
    ip          TEXT,
    detail      TEXT,
    created_at  REAL NOT NULL
);
"""
_MAX_ROWS = 10_000


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_db() -> None:
    """Create the auth_events table if it doesn't exist."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()
    logger.info("audit_db: initialised at %s", _DB_PATH)


def log_event(
    event_type: str,
    *,
    user_id: str | None = None,
    username: str | None = None,
    ip: str | None = None,
    detail: str | None = None,
) -> None:
    """Append an audit event. Silently swallows errors so callers are never blocked."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO auth_events (id, event_type, user_id, username, ip, detail, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), event_type, user_id, username, ip, detail, time.time()),
            )
            # Prune oldest rows if over cap
            conn.execute(
                "DELETE FROM auth_events WHERE id IN ("
                "  SELECT id FROM auth_events ORDER BY created_at ASC"
                f"  LIMIT MAX(0, (SELECT COUNT(*) FROM auth_events) - {_MAX_ROWS})"
                ")"
            )
            conn.commit()
    except Exception:
        logger.exception("audit_db: failed to log event %s", event_type)


def get_recent_events(limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent *limit* events, newest first."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM auth_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("audit_db: failed to fetch events")
        return []
