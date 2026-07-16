"""SQLite-backed user store for MTG Deckbuilder auth.

Uses WAL mode for light concurrent access. Passwords are bcrypt-hashed via
passlib; plain-text passwords are never stored.

The `data/` directory (and `users.db` inside it) are gitignored and
Docker-volume-mounted so they persist across container restarts.
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

import bcrypt as _bcrypt  # type: ignore[import]

from code.type_definitions import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_DB_PATH = _DATA_DIR / "users.db"

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_guest      INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    REAL    NOT NULL,
    updated_at    REAL    NOT NULL
);
"""

_GUEST_EMAIL = "guest@localhost"
_GUEST_USERNAME = "guest"


def init_db() -> None:
    """Create the data directory, users.db, and schema if they don't exist."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_USERS_TABLE)
        # Migration: add reset_token_hash column if not already present
        try:
            conn.execute("ALTER TABLE users ADD COLUMN reset_token_hash TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: add is_admin column if not already present
        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()
    logger.info("user_db: initialised at %s", _DB_PATH)


def ensure_guest_user() -> None:
    """Idempotently create the shared guest account."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (_GUEST_EMAIL,)
        ).fetchone()
        if existing:
            return
        now = time.time()
        conn.execute(
            "INSERT INTO users (id, username, email, password_hash, is_guest, is_active, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 1, 1, ?, ?)",
            (str(uuid.uuid4()), _GUEST_USERNAME, _GUEST_EMAIL, hash_password(str(uuid.uuid4())), now, now),
        )
        conn.commit()
    logger.info("user_db: guest account ensured")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _row_to_user(row: sqlite3.Row) -> User:
    keys = row.keys()
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        password_hash=row["password_hash"],
        is_guest=bool(row["is_guest"]),
        is_active=bool(row["is_active"]),
        is_admin=bool(row["is_admin"]) if "is_admin" in keys else False,
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def create_user(username: str, email: str, password: str) -> User:
    """Hash and persist a new user. Raises ValueError on duplicate username/email."""
    user_id = str(uuid.uuid4())
    now = time.time()
    pw_hash = hash_password(password)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, is_guest, is_active, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 0, 1, ?, ?)",
                (user_id, username.strip(), email.strip().lower(), pw_hash, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username or email already registered.") from exc
    return get_user_by_id(user_id)  # type: ignore[return-value]


def get_user_by_email(email: str) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(username: str) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_login(login: str) -> Optional[User]:
    """Look up a user by email or username (whichever matches)."""
    return get_user_by_email(login) or get_user_by_username(login)


def get_user_by_id(user_id: str) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_guest_user() -> Optional[User]:
    return get_user_by_email(_GUEST_EMAIL)


def list_all_users() -> list[User]:
    """Return all non-guest, non-admin DB users ordered by creation time."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_guest = 0 ORDER BY created_at ASC"
        ).fetchall()
    return [_row_to_user(r) for r in rows]


def set_user_admin(user_id: str, is_admin_flag: bool) -> None:
    """Grant or revoke admin role for a DB user. Raises ValueError for protected accounts."""
    with _connect() as conn:
        row = conn.execute("SELECT username, is_guest FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError("User not found.")
        if bool(row["is_guest"]):
            raise ValueError("Cannot grant admin to the guest account.")
        conn.execute(
            "UPDATE users SET is_admin = ?, updated_at = ? WHERE id = ?",
            (1 if is_admin_flag else 0, time.time(), user_id),
        )
        conn.commit()
    logger.info("user_db: set is_admin=%s for user %s", is_admin_flag, user_id)


def set_user_active(user_id: str, active: bool) -> None:
    """Activate or deactivate a DB user. Raises ValueError for protected accounts."""
    with _connect() as conn:
        row = conn.execute("SELECT username, is_guest FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError("User not found.")
        if bool(row["is_guest"]):
            raise ValueError("Cannot deactivate the guest account.")
        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if active else 0, time.time(), user_id),
        )
        conn.commit()
    logger.info("user_db: set is_active=%s for user %s", active, user_id)


def delete_user(user_id: str) -> None:
    import os as _os
    admin_username = _os.getenv("ADMIN_USERNAME", "").strip().lower()
    with _connect() as conn:
        row = conn.execute("SELECT username, is_guest FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError("User not found.")
        if bool(row["is_guest"]):
            raise ValueError("Cannot delete the guest account.")
        if admin_username and row["username"].lower() == admin_username:
            raise ValueError("Cannot delete the admin account.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    logger.info("user_db: deleted user %s", user_id)


def update_password(user_id: str, new_password: str) -> None:
    import os as _os
    if user_id == "__admin__":
        raise ValueError("Admin password cannot be changed through the application.")
    now = time.time()
    new_hash = hash_password(new_password)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, now, user_id),
        )
        conn.commit()


def set_reset_token_hash(user_id: str, token_hash: str) -> None:
    """Store a hashed reset token so it can be verified and consumed once."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET reset_token_hash = ?, updated_at = ? WHERE id = ?",
            (token_hash, now, user_id),
        )
        conn.commit()


def consume_reset_token(user_id: str, token_hash: str) -> bool:
    """Return True and clear the stored hash if it matches; False otherwise."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT reset_token_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row or row["reset_token_hash"] != token_hash:
            return False
        conn.execute(
            "UPDATE users SET reset_token_hash = NULL, updated_at = ? WHERE id = ?",
            (time.time(), user_id),
        )
        conn.commit()
    return True
