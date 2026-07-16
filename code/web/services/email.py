"""Async SMTP email service for transactional auth emails.

Configuration via environment variables:
  SMTP_HOST      — SMTP server hostname (required; if unset, logs URL at WARN)
  SMTP_PORT      — port (default 587)
  SMTP_USERNAME  — SMTP auth username (optional)
  SMTP_PASSWORD  — SMTP auth password (optional)
  SMTP_FROM      — From address (default noreply@localhost)
  SMTP_TLS       — set to 1 to use STARTTLS on connect (default: 1)
  SMTP_SSL       — set to 1 for implicit TLS on port 465 (overrides SMTP_TLS)
"""
from __future__ import annotations

import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib  # type: ignore[import]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

_SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
_SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
_SMTP_FROM = os.getenv("SMTP_FROM", "noreply@localhost").strip()
_SMTP_TLS = os.getenv("SMTP_TLS", "1").strip().lower() in {"1", "true", "yes"}
_SMTP_SSL = os.getenv("SMTP_SSL", "").strip().lower() in {"1", "true", "yes"}
_SMTP_ENABLED = os.getenv("ENABLE_SMTP", "1").strip().lower() not in {"0", "false", "no", "off"}


def is_smtp_configured() -> bool:
    """Return True if SMTP is enabled and SMTP_HOST is set."""
    return bool(_SMTP_HOST) and _SMTP_ENABLED


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

def _build_reset_email(to_email: str, reset_url: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "MTG Deckbuilder — Reset your password"
    msg["From"] = _SMTP_FROM
    msg["To"] = to_email

    plain = (
        "You requested a password reset for your MTG Deckbuilder account.\n\n"
        f"Reset your password here (link expires in 1 hour):\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email.\n"
        "Your password will not change.\n"
    )

    html = (
        "<!DOCTYPE html><html><body"
        ' style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:1rem;">\n'
        "  <h2 style=\"margin-bottom:.5rem;\">Reset your password</h2>\n"
        "  <p>You requested a password reset for your <strong>MTG Deckbuilder</strong> account.</p>\n"
        '  <p style="margin:1.5rem 0;">\n'
        f'    <a href="{reset_url}"\n'
        '       style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;'
        'padding:.65rem 1.25rem;border-radius:6px;font-weight:500;">\n'
        "      Reset Password\n"
        "    </a>\n"
        "  </p>\n"
        '  <p style="font-size:.85rem;color:#6b7280;">\n'
        "    This link expires in <strong>1 hour</strong>. "
        "If you did not request this, you can safely ignore this email.\n"
        "  </p>\n"
        '  <hr style="border:none;border-top:1px solid #e5e7eb;margin:1.5rem 0;">\n'
        '  <p style="font-size:.75rem;color:#9ca3af;">\n'
        "    If the button above does not work, copy and paste this URL into your browser:<br>\n"
        f'    <a href="{reset_url}" style="color:#6b7280;">{reset_url}</a>\n'
        "  </p>\n"
        "</body></html>\n"
    )

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def _build_welcome_email(to_email: str, username: str, login_url: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Welcome to MTG Deckbuilder, {username}!"
    msg["From"] = _SMTP_FROM
    msg["To"] = to_email

    plain = (
        f"Hi {username},\n\n"
        "Your MTG Deckbuilder account has been created successfully.\n\n"
        f"Log in here:\n{login_url}\n\n"
        "If you ever need to reset your password, use the \"Forgot password?\" "
        "link on the login page.\n\n"
        "Happy deck building!\n"
    )

    html = (
        "<!DOCTYPE html><html><body"
        ' style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:1rem;">\n'
        f"  <h2 style=\"margin-bottom:.5rem;\">Welcome, {username}!</h2>\n"
        "  <p>Your <strong>MTG Deckbuilder</strong> account has been created successfully.</p>\n"
        '  <p style="margin:1.5rem 0;">\n'
        f'    <a href="{login_url}"\n'
        '       style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;'
        'padding:.65rem 1.25rem;border-radius:6px;font-weight:500;">\n'
        "      Log In\n"
        "    </a>\n"
        "  </p>\n"
        '  <p style="font-size:.85rem;color:#6b7280;">\n'
        "    If you ever need to reset your password, use the "
        '    <a href="' + login_url.rstrip('/').rsplit('/', 1)[0] + '/auth/forgot" style="color:#2563eb;">Forgot password?</a>'
        " link on the login page.\n"
        "  </p>\n"
        '</body></html>\n'
    )

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_welcome_email(to_email: str, username: str, login_url: str) -> None:
    """Send a welcome email after successful registration.

    Silently skips (with an INFO log) if SMTP is not configured.
    Logs errors but never raises — registration must not fail due to email.
    """
    if not is_smtp_configured():
        logger.info("SMTP not configured — skipping welcome email for %s", username)
        return

    msg = _build_welcome_email(to_email, username, login_url)
    smtp = aiosmtplib.SMTP(
        hostname=_SMTP_HOST,
        port=_SMTP_PORT,
        use_tls=_SMTP_SSL,
    )
    try:
        await smtp.connect()
        if _SMTP_TLS and not _SMTP_SSL:
            await smtp.starttls()
        if _SMTP_USERNAME and _SMTP_PASSWORD:
            await smtp.login(_SMTP_USERNAME, _SMTP_PASSWORD)
        await smtp.send_message(msg)
        logger.info("Welcome email sent to %s", to_email)
    except Exception:
        logger.exception("Failed to send welcome email to %s", to_email)
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass


async def send_account_created_email(to_email: str, username: str, set_password_url: str) -> None:
    """Send an 'account created by admin' email with a one-time set-password link.

    Silently skips if SMTP is not configured.
    Logs errors but never raises.
    """
    if not is_smtp_configured():
        logger.info("SMTP not configured — skipping account-created email for %s", username)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your MTG Deckbuilder account is ready"
    msg["From"] = _SMTP_FROM
    msg["To"] = to_email

    plain = (
        f"Hi {username},\n\n"
        "An administrator has created an MTG Deckbuilder account for you.\n\n"
        f"Set your password here (link expires in 1 hour):\n{set_password_url}\n\n"
        "If you were not expecting this, you can safely ignore this email.\n"
    )
    html = (
        "<!DOCTYPE html><html><body"
        ' style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:1rem;">\n'
        f"  <h2 style=\"margin-bottom:.5rem;\">Welcome, {username}!</h2>\n"
        "  <p>An administrator has created an <strong>MTG Deckbuilder</strong> account for you.</p>\n"
        '  <p style="margin:1.5rem 0;">\n'
        f'    <a href="{set_password_url}"\n'
        '       style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;'
        'padding:.65rem 1.25rem;border-radius:6px;font-weight:500;">\n'
        "      Set Your Password\n"
        "    </a>\n"
        "  </p>\n"
        '  <p style="font-size:.85rem;color:#6b7280;">This link expires in <strong>1 hour</strong>.</p>\n'
        '  <hr style="border:none;border-top:1px solid #e5e7eb;margin:1.5rem 0;">\n'
        '  <p style="font-size:.75rem;color:#9ca3af;">\n'
        "    If you were not expecting this, you can safely ignore this email.\n"
        "  </p>\n"
        "</body></html>\n"
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    smtp = aiosmtplib.SMTP(hostname=_SMTP_HOST, port=_SMTP_PORT, use_tls=_SMTP_SSL)
    try:
        await smtp.connect()
        if _SMTP_TLS and not _SMTP_SSL:
            await smtp.starttls()
        if _SMTP_USERNAME and _SMTP_PASSWORD:
            await smtp.login(_SMTP_USERNAME, _SMTP_PASSWORD)
        await smtp.send_message(msg)
        logger.info("Account-created email sent to %s", to_email)
    except Exception:
        logger.exception("Failed to send account-created email to %s", to_email)
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass


async def send_password_reset(to_email: str, reset_url: str) -> None:
    """Send a password-reset email to *to_email*.

    If ``SMTP_HOST`` is not configured, the reset URL is logged at WARN level
    so development environments work without an SMTP server. No exception is
    raised in that case.

    Raises on SMTP delivery failure so callers can decide whether to surface
    the error or swallow it.
    """
    if not _SMTP_HOST:
        logger.warning(
            "SMTP_HOST not configured — password reset URL (dev only): %s", reset_url
        )
        return

    msg = _build_reset_email(to_email, reset_url)
    smtp = aiosmtplib.SMTP(
        hostname=_SMTP_HOST,
        port=_SMTP_PORT,
        use_tls=_SMTP_SSL,
    )
    await smtp.connect()
    try:
        if _SMTP_TLS and not _SMTP_SSL:
            await smtp.starttls()
        if _SMTP_USERNAME and _SMTP_PASSWORD:
            await smtp.login(_SMTP_USERNAME, _SMTP_PASSWORD)
        await smtp.send_message(msg)
        logger.info("password reset email sent to %s", to_email)
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass
