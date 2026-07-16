"""Auth tests — grows across milestones.

M1 coverage: user_db CRUD, password hashing, guest account.
M2 coverage: session cookie signing, get_current_user / get_required_user, reset tokens.
M3 coverage: auth routes (login, register, logout, forgot, reset) via TestClient.
M4 coverage: email service — graceful degradation + SMTP send path.
Uses a temp SQLite DB so no real data/ file is created or modified.
"""
from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Redirect user_db to a temp directory so tests never touch data/users.db."""
    import code.web.services.user_db as user_db
    monkeypatch.setattr(user_db, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    user_db.init_db()
    yield


# ---------------------------------------------------------------------------
# M1: user_db
# ---------------------------------------------------------------------------

def test_create_user_hashes_password():
    from code.web.services.user_db import create_user

    user = create_user("alice", "alice@example.com", "hunter2")
    assert user["password_hash"] != "hunter2"
    assert user["password_hash"].startswith("$2b$")


def test_verify_password_correct():
    from code.web.services.user_db import create_user, verify_password

    user = create_user("bob", "bob@example.com", "correcthorse")
    assert verify_password("correcthorse", user["password_hash"]) is True


def test_verify_password_wrong():
    from code.web.services.user_db import create_user, verify_password

    user = create_user("carol", "carol@example.com", "mypass")
    assert verify_password("wrongpass", user["password_hash"]) is False


def test_get_user_by_email_found():
    from code.web.services.user_db import create_user, get_user_by_email

    create_user("dave", "dave@example.com", "pw")
    found = get_user_by_email("dave@example.com")
    assert found is not None
    assert found["username"] == "dave"


def test_get_user_by_email_not_found():
    from code.web.services.user_db import get_user_by_email

    assert get_user_by_email("nobody@example.com") is None


def test_get_user_by_id():
    from code.web.services.user_db import create_user, get_user_by_id

    user = create_user("eve", "eve@example.com", "pw")
    found = get_user_by_id(user["id"])
    assert found is not None
    assert found["email"] == "eve@example.com"


def test_duplicate_email_raises():
    from code.web.services.user_db import create_user

    create_user("frank", "dup@example.com", "pw1")
    with pytest.raises(ValueError, match="already registered"):
        create_user("frank2", "dup@example.com", "pw2")


def test_duplicate_username_raises():
    from code.web.services.user_db import create_user

    create_user("grace", "grace@example.com", "pw1")
    with pytest.raises(ValueError, match="already registered"):
        create_user("grace", "grace2@example.com", "pw2")


def test_ensure_guest_user_idempotent():
    from code.web.services.user_db import ensure_guest_user, get_guest_user

    ensure_guest_user()
    ensure_guest_user()  # second call must not raise or duplicate
    guest = get_guest_user()
    assert guest is not None
    assert guest["is_guest"] is True
    assert guest["username"] == "guest"


def test_update_password():
    from code.web.services.user_db import create_user, update_password, verify_password

    user = create_user("henry", "henry@example.com", "oldpass")
    update_password(user["id"], "newpass")
    # re-fetch
    from code.web.services.user_db import get_user_by_id
    updated = get_user_by_id(user["id"])
    assert verify_password("newpass", updated["password_hash"]) is True
    assert verify_password("oldpass", updated["password_hash"]) is False


def test_user_is_active_by_default():
    from code.web.services.user_db import create_user

    user = create_user("iris", "iris@example.com", "pw")
    assert user["is_active"] is True
    assert user["is_guest"] is False


def test_email_normalised_to_lowercase():
    from code.web.services.user_db import create_user, get_user_by_email

    create_user("jake", "JAKE@EXAMPLE.COM", "pw")
    found = get_user_by_email("jake@example.com")
    assert found is not None


# ---------------------------------------------------------------------------
# M2: auth — session cookies & reset tokens
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import MagicMock


def _mock_request(cookie_value: str | None = None) -> MagicMock:
    req = MagicMock()
    req.cookies = {
        "mtg_session": cookie_value
    } if cookie_value else {}
    return req


def _mock_response() -> MagicMock:
    resp = MagicMock()
    resp.set_cookie = MagicMock()
    resp.delete_cookie = MagicMock()
    return resp


def test_create_and_decode_session_cookie():
    from code.web.services.auth import create_session_cookie, _decode_session_token

    resp = _mock_response()
    create_session_cookie(resp, "user-uuid-123")
    resp.set_cookie.assert_called_once()
    _, kwargs = resp.set_cookie.call_args
    token = kwargs["value"]
    assert _decode_session_token(token) == "user-uuid-123"


def test_clear_session_cookie():
    from code.web.services.auth import clear_session_cookie

    resp = _mock_response()
    clear_session_cookie(resp)
    resp.delete_cookie.assert_called_once_with(
        key="mtg_session", httponly=True, samesite="lax"
    )


def test_decode_tampered_token_returns_none():
    from code.web.services.auth import _decode_session_token

    assert _decode_session_token("tampered.garbage.token") is None


def test_get_current_user_with_valid_cookie():
    from code.web.services.auth import create_session_cookie, _decode_session_token, get_current_user
    from code.web.services.user_db import create_user, ensure_guest_user

    ensure_guest_user()
    user = create_user("session_user", "sess@example.com", "pw")
    resp = _mock_response()
    create_session_cookie(resp, user["id"])
    _, kwargs = resp.set_cookie.call_args
    token = kwargs["value"]

    req = _mock_request(token)
    result = asyncio.run(get_current_user(req))
    assert result["id"] == user["id"]
    assert result["username"] == "session_user"


def test_get_current_user_no_cookie_returns_guest():
    from code.web.services.auth import get_current_user
    from code.web.services.user_db import ensure_guest_user

    ensure_guest_user()
    req = _mock_request()
    result = asyncio.run(get_current_user(req))
    assert result["is_guest"] is True


def test_get_current_user_bad_cookie_returns_guest():
    from code.web.services.auth import get_current_user
    from code.web.services.user_db import ensure_guest_user

    ensure_guest_user()
    req = _mock_request("totally.invalid.cookie")
    result = asyncio.run(get_current_user(req))
    assert result["is_guest"] is True


def test_get_required_user_raises_for_guest():
    from fastapi import HTTPException
    from code.web.services.auth import get_required_user
    from code.web.services.user_db import ensure_guest_user

    ensure_guest_user()
    req = _mock_request()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_required_user(req))
    assert exc_info.value.status_code == 401


def test_get_required_user_passes_for_authenticated():
    from code.web.services.auth import create_session_cookie, get_required_user
    from code.web.services.user_db import create_user, ensure_guest_user

    ensure_guest_user()
    user = create_user("req_user", "req@example.com", "pw")
    resp = _mock_response()
    create_session_cookie(resp, user["id"])
    _, kwargs = resp.set_cookie.call_args
    token = kwargs["value"]

    req = _mock_request(token)
    result = asyncio.run(get_required_user(req))
    assert result["username"] == "req_user"


def test_reset_token_roundtrip():
    from code.web.services.auth import create_reset_token, verify_reset_token

    token = create_reset_token("user@example.com")
    assert verify_reset_token(token) == "user@example.com"


def test_reset_token_tampered_returns_none():
    from code.web.services.auth import verify_reset_token

    assert verify_reset_token("bad.token.value") is None


def test_reset_token_email_lowercased():
    from code.web.services.auth import create_reset_token, verify_reset_token

    token = create_reset_token("USER@EXAMPLE.COM")
    assert verify_reset_token(token) == "user@example.com"


# ---------------------------------------------------------------------------
# M3: auth routes via TestClient
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient


@pytest.fixture()
def client(_isolated_db):
    """TestClient wired to the real FastAPI app with an isolated DB."""
    from code.web.services.user_db import ensure_guest_user
    ensure_guest_user()
    from code.web.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_login_page_renders(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert "Log In" in resp.text


def test_register_page_renders(client):
    resp = client.get("/auth/register")
    assert resp.status_code == 200
    assert "Sign Up" in resp.text or "Create Account" in resp.text


def test_register_and_login_flow(client):
    # Register
    resp = client.post("/auth/register", data={
        "username": "flowuser", "email": "flow@example.com",
        "password": "password123", "confirm": "password123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert "mtg_session" in resp.cookies

    # Logout
    resp2 = client.post("/auth/logout", follow_redirects=False)
    assert resp2.status_code == 303

    # Login
    resp3 = client.post("/auth/login", data={
        "login": "flow@example.com", "password": "password123",
    }, follow_redirects=False)
    assert resp3.status_code == 303
    assert "mtg_session" in resp3.cookies


def test_login_bad_password_returns_400(client):
    from code.web.services.user_db import create_user
    create_user("badpw", "badpw@example.com", "rightpassword")
    resp = client.post("/auth/login", data={
        "login": "badpw@example.com", "password": "wrongpassword",
    })
    assert resp.status_code == 400
    assert "Invalid username/email or password" in resp.text


def test_register_password_mismatch_returns_400(client):
    resp = client.post("/auth/register", data={
        "username": "x", "email": "x@x.com",
        "password": "password1", "confirm": "password2",
    })
    assert resp.status_code == 400
    assert "do not match" in resp.text


def test_register_duplicate_email_returns_400(client):
    client.post("/auth/register", data={
        "username": "dup1", "email": "dup@example.com",
        "password": "password1", "confirm": "password1",
    })
    resp = client.post("/auth/register", data={
        "username": "dup2", "email": "dup@example.com",
        "password": "password2", "confirm": "password2",
    })
    assert resp.status_code == 400
    assert "already registered" in resp.text


def test_forgot_page_renders(client):
    resp = client.get("/auth/forgot")
    assert resp.status_code == 200
    assert "Forgot Password" in resp.text


def test_forgot_post_always_shows_submitted(client):
    # Non-existent email should still show submitted (no enumeration)
    resp = client.post("/auth/forgot", data={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert "reset link" in resp.text.lower() or "inbox" in resp.text.lower()


def test_reset_token_expired_returns_error(client):
    resp = client.get("/auth/reset/bad.token.value")
    assert resp.status_code == 200
    assert "invalid or has expired" in resp.text.lower()


def test_reset_flow(client):
    from code.web.services.user_db import create_user, verify_password, get_user_by_email
    from code.web.services.auth import create_reset_token
    from code.web.routes.auth import _token_hash
    from code.web.services.user_db import set_reset_token_hash

    create_user("resetme", "resetme@example.com", "oldpassword")
    user = get_user_by_email("resetme@example.com")
    token = create_reset_token("resetme@example.com")
    set_reset_token_hash(user["id"], _token_hash(token))

    resp = client.post(f"/auth/reset/{token}", data={
        "password": "newpassword", "confirm": "newpassword",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers["location"]

    # Old password no longer works
    updated = get_user_by_email("resetme@example.com")
    assert verify_password("newpassword", updated["password_hash"])
    assert not verify_password("oldpassword", updated["password_hash"])


def test_reset_token_reuse_rejected(client):
    from code.web.services.user_db import create_user, get_user_by_email
    from code.web.services.auth import create_reset_token
    from code.web.routes.auth import _token_hash
    from code.web.services.user_db import set_reset_token_hash

    create_user("onetime", "onetime@example.com", "oldpassword")
    user = get_user_by_email("onetime@example.com")
    token = create_reset_token("onetime@example.com")
    set_reset_token_hash(user["id"], _token_hash(token))

    # First use succeeds
    client.post(f"/auth/reset/{token}", data={
        "password": "newpassword", "confirm": "newpassword",
    }, follow_redirects=False)

    # Second use is rejected
    resp = client.post(f"/auth/reset/{token}", data={
        "password": "anotherpass", "confirm": "anotherpass",
    })
    assert "already been used" in resp.text


# ---------------------------------------------------------------------------
# M4: email service
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


def test_send_password_reset_no_smtp_logs_url(caplog):
    """When SMTP_HOST is unset, log the URL and return without raising."""
    import logging
    from code.web.services import email as email_mod

    original = email_mod._SMTP_HOST
    try:
        email_mod._SMTP_HOST = ""
        with caplog.at_level(logging.WARNING, logger="code.web.services.email"):
            asyncio.run(email_mod.send_password_reset("user@example.com", "http://localhost/reset/tok"))
        assert any("http://localhost/reset/tok" in r.message for r in caplog.records)
    finally:
        email_mod._SMTP_HOST = original


def test_send_password_reset_builds_correct_message():
    """Email message has the right subject, to, and reset URL in body."""
    from code.web.services.email import _build_reset_email

    msg = _build_reset_email("user@example.com", "http://example.com/reset/abc")
    assert msg["Subject"] == "MTG Deckbuilder \u2014 Reset your password"
    assert msg["To"] == "user@example.com"
    # Both plain-text and HTML parts contain the URL
    payloads = [p.get_payload() for p in msg.get_payload()]
    combined = " ".join(payloads)
    assert "http://example.com/reset/abc" in combined


def test_send_password_reset_calls_smtp(monkeypatch):
    """When SMTP_HOST is set, aiosmtplib.SMTP is invoked correctly."""
    from code.web.services import email as email_mod

    mock_smtp = MagicMock()
    mock_smtp.connect = AsyncMock()
    mock_smtp.starttls = AsyncMock()
    mock_smtp.login = AsyncMock()
    mock_smtp.send_message = AsyncMock()
    mock_smtp.quit = AsyncMock()

    monkeypatch.setattr(email_mod, "_SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_mod, "_SMTP_PORT", 587)
    monkeypatch.setattr(email_mod, "_SMTP_USERNAME", "user")
    monkeypatch.setattr(email_mod, "_SMTP_PASSWORD", "pass")
    monkeypatch.setattr(email_mod, "_SMTP_TLS", True)
    monkeypatch.setattr(email_mod, "_SMTP_SSL", False)
    monkeypatch.setattr(email_mod.aiosmtplib, "SMTP", lambda **_: mock_smtp)

    asyncio.run(email_mod.send_password_reset("to@example.com", "http://x.com/reset/t"))

    mock_smtp.connect.assert_awaited_once()
    mock_smtp.starttls.assert_awaited_once()
    mock_smtp.login.assert_awaited_once_with("user", "pass")
    mock_smtp.send_message.assert_awaited_once()
    mock_smtp.quit.assert_awaited_once()


# ---------------------------------------------------------------------------
# M5+M6: per-user file path scoping
# ---------------------------------------------------------------------------

def test_deck_dir_scoped_by_user(tmp_path, monkeypatch):
    """Authenticated users get deck_files/{user_id}/ not deck_files/."""
    import code.web.routes.decks as decks_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECK_CONFIG", raising=False)

    result = decks_mod._deck_dir("abc-123")
    assert result == (tmp_path / "deck_files" / "abc-123").resolve()


def test_deck_dir_guest(tmp_path, monkeypatch):
    """Guest users get deck_files/guest/."""
    import code.web.routes.decks as decks_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECK_CONFIG", raising=False)

    result = decks_mod._deck_dir("guest")
    assert result == (tmp_path / "deck_files" / "guest").resolve()


def test_config_dir_scoped_by_user(tmp_path, monkeypatch):
    """Authenticated users get config/{user_id}/."""
    import code.web.routes.configs as configs_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECK_CONFIG", raising=False)

    result = configs_mod._config_dir("user-xyz")
    assert result == (tmp_path / "config" / "user-xyz").resolve()


def test_owned_store_user_isolation(tmp_path, monkeypatch):
    """Two different users have separate owned card stores."""
    import code.web.services.owned_store as store
    monkeypatch.setenv("OWNED_CARDS_DIR", str(tmp_path / "owned_cards"))

    store.add_names(["Black Lotus"], "user-a")
    store.add_names(["Sol Ring"], "user-b")

    names_a = {n.lower() for n in store.get_names("user-a")}
    names_b = {n.lower() for n in store.get_names("user-b")}
    assert "black lotus" in names_a
    assert "sol ring" in names_b
    # No cross-contamination
    assert "sol ring" not in names_a
    assert "black lotus" not in names_b


def test_forgot_route_shows_submitted_without_smtp(client, caplog):
    """Forgot POST still shows success page when SMTP is unconfigured."""
    import logging
    from code.web.services.user_db import create_user
    from code.web.services import email as email_mod

    create_user("smtptest", "smtptest@example.com", "password1")

    original = email_mod._SMTP_HOST
    try:
        email_mod._SMTP_HOST = ""
        with caplog.at_level(logging.WARNING, logger="code.web.services.email"):
            resp = client.post("/auth/forgot", data={"email": "smtptest@example.com"})
        assert resp.status_code == 200
        assert "reset link" in resp.text.lower() or "inbox" in resp.text.lower()
        assert any("smtptest" not in r.message for r in caplog.records)  # URL logged, not email
    finally:
        email_mod._SMTP_HOST = original

