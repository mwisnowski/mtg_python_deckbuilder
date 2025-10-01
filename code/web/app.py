from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import json as _json
import time
import uuid
import logging
import math
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from typing import Any, Optional, Dict, Iterable, Mapping
from contextlib import asynccontextmanager
from .services.combo_utils import detect_all as _detect_all
from .services.theme_catalog_loader import prewarm_common_filters  # type: ignore
from .services.tasks import get_session, new_sid, set_session_value  # type: ignore

# Resolve template/static dirs relative to this file
_THIS_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _THIS_DIR / "templates"
_STATIC_DIR = _THIS_DIR / "static"

@asynccontextmanager
async def _lifespan(app: FastAPI):  # pragma: no cover - simple infra glue
    """FastAPI lifespan context replacing deprecated on_event startup hooks.

    Consolidates previous startup tasks:
      - prewarm_common_filters (optional fast filter cache priming)
      - theme preview card index warm (CSV parse avoidance for first preview)

    Failures in warm tasks are intentionally swallowed to avoid blocking app start.
    """
    # Prewarm theme filter cache (guarded internally by env flag)
    try:
        prewarm_common_filters()
    except Exception:
        pass
    # Warm preview card index once (updated Phase A: moved to card_index module)
    try:  # local import to avoid cost if preview unused
        from .services.card_index import maybe_build_index  # type: ignore
        maybe_build_index()
    except Exception:
        pass
    yield  # (no shutdown tasks currently)


app = FastAPI(title="MTG Deckbuilder Web UI", lifespan=_lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)

# Mount static if present
if _STATIC_DIR.exists():
    class CacheStatic(StaticFiles):
        async def get_response(self, path, scope):  # type: ignore[override]
            resp = await super().get_response(path, scope)
            try:
                # Add basic cache headers for static assets
                resp.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
            except Exception:
                pass
            return resp
    app.mount("/static", CacheStatic(directory=str(_STATIC_DIR)), name="static")

# Jinja templates
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Compatibility shim: accept legacy TemplateResponse(name, {"request": request, ...})
# and reorder to the new signature TemplateResponse(request, name, {...}).
# Prevents DeprecationWarning noise in tests without touching all call sites.
_orig_template_response = templates.TemplateResponse

def _compat_template_response(*args, **kwargs):  # type: ignore[override]
    try:
        if args and isinstance(args[0], str):
            name = args[0]
            ctx = args[1] if len(args) > 1 else {}
            req = None
            try:
                if isinstance(ctx, dict):
                    req = ctx.get("request")
            except Exception:
                req = None
            if req is not None:
                return _orig_template_response(req, name, ctx, **kwargs)
    except Exception:
        # Fall through to original behavior on any unexpected error
        pass
    return _orig_template_response(*args, **kwargs)

templates.TemplateResponse = _compat_template_response  # type: ignore[assignment]

# (Startup prewarm moved to lifespan handler _lifespan)

# Global template flags (env-driven)
def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

SHOW_LOGS = _as_bool(os.getenv("SHOW_LOGS"), False)
SHOW_SETUP = _as_bool(os.getenv("SHOW_SETUP"), True)
SHOW_DIAGNOSTICS = _as_bool(os.getenv("SHOW_DIAGNOSTICS"), False)
SHOW_COMMANDERS = _as_bool(os.getenv("SHOW_COMMANDERS"), True)
SHOW_VIRTUALIZE = _as_bool(os.getenv("WEB_VIRTUALIZE"), False)
ENABLE_THEMES = _as_bool(os.getenv("ENABLE_THEMES"), True)
ENABLE_PWA = _as_bool(os.getenv("ENABLE_PWA"), False)
ENABLE_PRESETS = _as_bool(os.getenv("ENABLE_PRESETS"), False)
ALLOW_MUST_HAVES = _as_bool(os.getenv("ALLOW_MUST_HAVES"), True)
RANDOM_MODES = _as_bool(os.getenv("RANDOM_MODES"), True)  # initial snapshot (legacy)
RANDOM_UI = _as_bool(os.getenv("RANDOM_UI"), True)
THEME_PICKER_DIAGNOSTICS = _as_bool(os.getenv("WEB_THEME_PICKER_DIAGNOSTICS"), False)
def _as_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None and str(val).strip() != "" else default
    except Exception:
        return default
RANDOM_MAX_ATTEMPTS = _as_int(os.getenv("RANDOM_MAX_ATTEMPTS"), 5)
RANDOM_TIMEOUT_MS = _as_int(os.getenv("RANDOM_TIMEOUT_MS"), 5000)
RANDOM_TELEMETRY = _as_bool(os.getenv("RANDOM_TELEMETRY"), False)
RATE_LIMIT_ENABLED = _as_bool(os.getenv("RANDOM_RATE_LIMIT"), False)
RATE_LIMIT_WINDOW_S = _as_int(os.getenv("RATE_LIMIT_WINDOW_S"), 10)
RATE_LIMIT_RANDOM = _as_int(os.getenv("RANDOM_RATE_LIMIT_RANDOM"), 10)
RATE_LIMIT_BUILD = _as_int(os.getenv("RANDOM_RATE_LIMIT_BUILD"), 10)
RATE_LIMIT_SUGGEST = _as_int(os.getenv("RANDOM_RATE_LIMIT_SUGGEST"), 30)
RANDOM_STRUCTURED_LOGS = _as_bool(os.getenv("RANDOM_STRUCTURED_LOGS"), False)
RANDOM_REROLL_THROTTLE_MS = _as_int(os.getenv("RANDOM_REROLL_THROTTLE_MS"), 350)

# Simple theme input validation constraints
_THEME_MAX_LEN = 60
_THEME_ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -'_")

def _sanitize_theme(raw: Optional[str]) -> Optional[str]:
    """Return a sanitized theme string or None if invalid.

    Rules (minimal by design):
      - Strip leading/trailing whitespace
      - Reject if empty after strip
      - Reject if length > _THEME_MAX_LEN
      - Reject if any disallowed character present
    """
    if raw is None:
        return None
    try:
        s = str(raw).strip()
    except Exception:
        return None
    if not s:
        return None
    if len(s) > _THEME_MAX_LEN:
        return None
    for ch in s:
        if ch not in _THEME_ALLOWED_CHARS:
            return None
    return s


def _sanitize_bool(raw: Any, *, default: Optional[bool] = None) -> Optional[bool]:
    """Coerce assorted truthy/falsey payloads into booleans.

    Accepts booleans, ints, and common string forms ("1", "0", "true", "false", "on", "off").
    Returns `default` when the value is None or cannot be interpreted.
    """

    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 0:
            return False
        if raw == 1:
            return True
    try:
        text = str(raw).strip().lower()
    except Exception:
        return default
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n", ""}:
        return False
    return default


def _parse_auto_fill_flags(
    source: Mapping[str, Any] | None,
    *,
    default_enabled: Optional[bool] = None,
    default_secondary: Optional[bool] = None,
    default_tertiary: Optional[bool] = None,
) -> tuple[bool, bool, bool]:
    """Resolve auto-fill booleans from payload with graceful fallbacks."""

    data: Mapping[str, Any] = source or {}
    enabled_raw = _sanitize_bool(data.get("auto_fill_enabled"), default=default_enabled)
    secondary_raw = _sanitize_bool(data.get("auto_fill_secondary_enabled"), default=None)
    tertiary_raw = _sanitize_bool(data.get("auto_fill_tertiary_enabled"), default=None)

    def _resolve(value: Optional[bool], fallback: Optional[bool]) -> bool:
        if value is None:
            if enabled_raw is not None:
                return bool(enabled_raw)
            if fallback is not None:
                return bool(fallback)
            return False
        return bool(value)

    secondary = _resolve(secondary_raw, default_secondary)
    tertiary = _resolve(tertiary_raw, default_tertiary)

    if tertiary and not secondary:
        secondary = True
    if not secondary:
        tertiary = False

    if enabled_raw is None:
        enabled = bool(secondary or tertiary)
    else:
        enabled = bool(enabled_raw)
    return enabled, secondary, tertiary

# Theme default from environment: THEME=light|dark|system (case-insensitive). Defaults to system.
_THEME_ENV = (os.getenv("THEME") or "").strip().lower()
DEFAULT_THEME = "system"
if _THEME_ENV in {"light", "dark", "system"}:
    DEFAULT_THEME = _THEME_ENV

# Expose as Jinja globals so all templates can reference without passing per-view
templates.env.globals.update({
    "show_logs": SHOW_LOGS,
    "show_setup": SHOW_SETUP,
    "show_diagnostics": SHOW_DIAGNOSTICS,
    "show_commanders": SHOW_COMMANDERS,
    "virtualize": SHOW_VIRTUALIZE,
    "enable_themes": ENABLE_THEMES,
    "enable_pwa": ENABLE_PWA,
    "enable_presets": ENABLE_PRESETS,
    "allow_must_haves": ALLOW_MUST_HAVES,
    "default_theme": DEFAULT_THEME,
    "random_modes": RANDOM_MODES,
    "random_ui": RANDOM_UI,
    "random_max_attempts": RANDOM_MAX_ATTEMPTS,
    "random_timeout_ms": RANDOM_TIMEOUT_MS,
    "random_reroll_throttle_ms": int(RANDOM_REROLL_THROTTLE_MS),
    "theme_picker_diagnostics": THEME_PICKER_DIAGNOSTICS,
})

# Expose catalog hash (for cache versioning / service worker) – best-effort, fallback to 'dev'
def _load_catalog_hash() -> str:
    try:  # local import to avoid circular on early load
        from .services.theme_catalog_loader import CATALOG_JSON  # type: ignore
        if CATALOG_JSON.exists():
            raw = _json.loads(CATALOG_JSON.read_text(encoding="utf-8") or "{}")
            meta = raw.get("metadata_info") or {}
            ch = meta.get("catalog_hash") or "dev"
            if isinstance(ch, str) and ch:
                return ch[:64]
    except Exception:
        pass
    return "dev"

templates.env.globals["catalog_hash"] = _load_catalog_hash()

# --- Optional in-memory telemetry for Random Modes ---
_RANDOM_METRICS: dict[str, dict[str, int]] = {
    "build": {"success": 0, "constraints_impossible": 0, "error": 0},
    "full_build": {"success": 0, "fallback": 0, "constraints_impossible": 0, "error": 0},
    "reroll": {"success": 0, "fallback": 0, "constraints_impossible": 0, "error": 0},
}

_REROLL_THROTTLE_SECONDS = max(0.0, max(0, int(RANDOM_REROLL_THROTTLE_MS)) / 1000.0)
_RANDOM_USAGE_METRICS: dict[str, int] = {
    "surprise": 0,
    "theme": 0,
    "reroll": 0,
    "reroll_same_commander": 0,
}
_RANDOM_FALLBACK_METRICS: dict[str, int] = {
    "none": 0,
    "combo": 0,
    "synergy": 0,
    "combo_and_synergy": 0,
}
_RANDOM_FALLBACK_REASONS: dict[str, int] = {}


def _record_random_usage_event(mode: str, combo_fallback: bool, synergy_fallback: bool, fallback_reason: Any) -> None:
    if not RANDOM_TELEMETRY:
        return
    try:
        key = mode or "unknown"
        _RANDOM_USAGE_METRICS[key] = int(_RANDOM_USAGE_METRICS.get(key, 0)) + 1
        fallback_key = "none"
        if combo_fallback and synergy_fallback:
            fallback_key = "combo_and_synergy"
        elif combo_fallback:
            fallback_key = "combo"
        elif synergy_fallback:
            fallback_key = "synergy"
        _RANDOM_FALLBACK_METRICS[fallback_key] = int(_RANDOM_FALLBACK_METRICS.get(fallback_key, 0)) + 1
        if fallback_reason:
            reason = str(fallback_reason)
            if len(reason) > 80:
                reason = reason[:80]
            _RANDOM_FALLBACK_REASONS[reason] = int(_RANDOM_FALLBACK_REASONS.get(reason, 0)) + 1
    except Exception:
        pass


def _classify_usage_mode(mode: Optional[str], theme_values: Iterable[Optional[str]], locked_commander: Optional[str]) -> str:
    has_theme = False
    try:
        has_theme = any(bool((val or "").strip()) for val in theme_values)
    except Exception:
        has_theme = False
    normalized_mode = (mode or "").strip().lower()
    if locked_commander:
        return "reroll_same_commander"
    if has_theme:
        return "theme"
    if normalized_mode.startswith("reroll"):
        return "reroll"
    if normalized_mode == "theme":
        return "theme"
    return "surprise"

def _record_random_event(kind: str, *, success: bool = False, fallback: bool = False, constraints_impossible: bool = False, error: bool = False) -> None:
    if not RANDOM_TELEMETRY:
        return
    try:
        k = _RANDOM_METRICS.get(kind)
        if not k:
            return
        if success:
            k["success"] = int(k.get("success", 0)) + 1
        if fallback:
            k["fallback"] = int(k.get("fallback", 0)) + 1
        if constraints_impossible:
            k["constraints_impossible"] = int(k.get("constraints_impossible", 0)) + 1
        if error:
            k["error"] = int(k.get("error", 0)) + 1
    except Exception:
        pass

# --- Optional structured logging for Random Modes ---
def _log_random_event(kind: str, request: Request, status: str, **fields: Any) -> None:
    if not RANDOM_STRUCTURED_LOGS:
        return
    try:
        rid = getattr(request.state, "request_id", None)
        payload = {
            "event": "random_mode",
            "kind": kind,
            "status": status,
            "request_id": rid,
            "path": str(request.url.path),
            "ip": _client_ip(request),
        }
        for k, v in (fields or {}).items():
            # keep payload concise
            if isinstance(v, (str, int, float, bool)) or v is None:
                payload[k] = v
        logging.getLogger("web.random").info(_json.dumps(payload, separators=(",", ":")))
    except Exception:
        # Never break a request due to logging
        pass

# --- Optional in-memory rate limiting (best-effort, per-IP, per-group) ---
_RL_COUNTS: dict[tuple[str, str, int], int] = {}

def _client_ip(request: Request) -> str:
    try:
        ip = getattr(getattr(request, "client", None), "host", None) or request.headers.get("X-Forwarded-For")
        if isinstance(ip, str) and ip.strip():
            # If XFF has multiple, use first
            return ip.split(",")[0].strip()
    except Exception:
        pass
    return "unknown"


def _enforce_random_session_throttle(request: Request) -> None:
    if _REROLL_THROTTLE_SECONDS <= 0:
        return
    sid = request.cookies.get("sid")
    if not sid:
        return
    try:
        sess = get_session(sid)
    except Exception:
        return
    rb = sess.get("random_build") if isinstance(sess, dict) else None
    if not isinstance(rb, dict):
        return
    last_ts = rb.get("last_random_request_ts")
    if last_ts is None:
        return
    try:
        last_time = float(last_ts)
    except Exception:
        return
    now = time.time()
    delta = now - last_time
    if delta < _REROLL_THROTTLE_SECONDS:
        retry_after = max(1, int(math.ceil(_REROLL_THROTTLE_SECONDS - delta)))
        raise HTTPException(status_code=429, detail="random_mode_throttled", headers={
            "Retry-After": str(retry_after),
        })

def rate_limit_check(request: Request, group: str) -> tuple[int, int] | None:
    """Check and increment rate limit for (ip, group).

    Returns (remaining, reset_epoch) if enabled, else None.
    Raises HTTPException(429) when exceeded.
    """
    if not RATE_LIMIT_ENABLED:
        return None
    limit = 0
    if group == "random":
        limit = int(RATE_LIMIT_RANDOM)
    elif group == "build":
        limit = int(RATE_LIMIT_BUILD)
    elif group == "suggest":
        limit = int(RATE_LIMIT_SUGGEST)
    if limit <= 0:
        return None
    win = max(1, int(RATE_LIMIT_WINDOW_S))
    now = int(time.time())
    window_id = now // win
    reset_epoch = (window_id + 1) * win
    key = (_client_ip(request), group, window_id)
    count = int(_RL_COUNTS.get(key, 0)) + 1
    _RL_COUNTS[key] = count
    remaining = max(0, limit - count)
    if count > limit:
        # Too many
        retry_after = max(0, reset_epoch - now)
        raise HTTPException(status_code=429, detail="rate_limited", headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_epoch),
        })
    return (remaining, reset_epoch)

# --- Simple fragment cache for template partials (low-risk, TTL-based) ---
_FRAGMENT_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_FRAGMENT_TTL_SECONDS = 60.0

def render_cached(template_name: str, cache_key: str | None, /, **ctx: Any) -> str:
    """Render a template fragment with an optional cache key and short TTL.

    Intended for finished/immutable views (e.g., saved deck summaries). On error,
    falls back to direct rendering without cache interaction.
    """
    try:
        if cache_key:
            now = time.time()
            k = (template_name, str(cache_key))
            hit = _FRAGMENT_CACHE.get(k)
            if hit and (now - hit[0]) < _FRAGMENT_TTL_SECONDS:
                return hit[1]
            html = templates.get_template(template_name).render(**ctx)
            _FRAGMENT_CACHE[k] = (now, html)
            return html
        return templates.get_template(template_name).render(**ctx)
    except Exception:
        return templates.get_template(template_name).render(**ctx)


# --- Session helpers for Random Modes ---
def _ensure_session(request: Request) -> tuple[str, dict[str, Any], bool]:
    """Get or create a session for the incoming request.

    Returns (sid, session_dict, had_existing_cookie)
    """
    sid = request.cookies.get("sid")
    had_cookie = bool(sid)
    if not sid:
        sid = new_sid()
    sess = get_session(sid)
    return sid, sess, had_cookie


def _update_random_session(
    request: Request,
    *,
    seed: int,
    theme: Any,
    constraints: Any,
    requested_themes: dict[str, Any] | None = None,
    resolved_themes: Any = None,
    auto_fill_enabled: Optional[bool] = None,
    auto_fill_secondary_enabled: Optional[bool] = None,
    auto_fill_tertiary_enabled: Optional[bool] = None,
    strict_theme_match: Optional[bool] = None,
    auto_fill_applied: Optional[bool] = None,
    auto_filled_themes: Optional[Iterable[Any]] = None,
    display_themes: Optional[Iterable[Any]] = None,
    request_timestamp: Optional[float] = None,
) -> tuple[str, bool]:
    """Update session with latest random build context and maintain a bounded recent list."""

    sid, sess, had_cookie = _ensure_session(request)
    rb = dict(sess.get("random_build") or {})

    rb["seed"] = int(seed)
    if theme is not None:
        rb["theme"] = theme
    if constraints is not None:
        rb["constraints"] = constraints
    if strict_theme_match is not None:
        rb["strict_theme_match"] = bool(strict_theme_match)

    def _coerce_str_list(values: Iterable[Any]) -> list[str]:
        cleaned: list[str] = []
        for item in values:
            if item is None:
                continue
            try:
                text = str(item).strip()
            except Exception:
                continue
            if text:
                cleaned.append(text)
        return cleaned

    requested_copy: dict[str, Any] = {}
    if requested_themes is not None and isinstance(requested_themes, dict):
        requested_copy = dict(requested_themes)
    elif isinstance(rb.get("requested_themes"), dict):
        requested_copy = dict(rb.get("requested_themes"))  # type: ignore[arg-type]

    if "auto_fill_enabled" in requested_copy:
        afe = _sanitize_bool(requested_copy.get("auto_fill_enabled"), default=None)
        if afe is None:
            requested_copy.pop("auto_fill_enabled", None)
        else:
            requested_copy["auto_fill_enabled"] = bool(afe)
    if auto_fill_enabled is not None:
        requested_copy["auto_fill_enabled"] = bool(auto_fill_enabled)

    if "strict_theme_match" in requested_copy:
        stm = _sanitize_bool(requested_copy.get("strict_theme_match"), default=None)
        if stm is None:
            requested_copy.pop("strict_theme_match", None)
        else:
            requested_copy["strict_theme_match"] = bool(stm)
    if strict_theme_match is not None:
        requested_copy["strict_theme_match"] = bool(strict_theme_match)

    if "auto_fill_secondary_enabled" in requested_copy:
        afs = _sanitize_bool(requested_copy.get("auto_fill_secondary_enabled"), default=None)
        if afs is None:
            requested_copy.pop("auto_fill_secondary_enabled", None)
        else:
            requested_copy["auto_fill_secondary_enabled"] = bool(afs)
    if auto_fill_secondary_enabled is not None:
        requested_copy["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)

    if "auto_fill_tertiary_enabled" in requested_copy:
        aft = _sanitize_bool(requested_copy.get("auto_fill_tertiary_enabled"), default=None)
        if aft is None:
            requested_copy.pop("auto_fill_tertiary_enabled", None)
        else:
            requested_copy["auto_fill_tertiary_enabled"] = bool(aft)
    if auto_fill_tertiary_enabled is not None:
        requested_copy["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)

    if requested_copy:
        rb["requested_themes"] = requested_copy

    req_primary = requested_copy.get("primary") if requested_copy else None
    req_secondary = requested_copy.get("secondary") if requested_copy else None
    req_tertiary = requested_copy.get("tertiary") if requested_copy else None
    if req_primary:
        rb.setdefault("primary_theme", req_primary)
    if req_secondary:
        rb.setdefault("secondary_theme", req_secondary)
    if req_tertiary:
        rb.setdefault("tertiary_theme", req_tertiary)

    resolved_info: dict[str, Any] | None = None
    if resolved_themes is not None:
        if isinstance(resolved_themes, dict):
            resolved_info = dict(resolved_themes)
        elif isinstance(resolved_themes, list):
            resolved_info = {"resolved_list": list(resolved_themes)}
        else:
            resolved_info = {"resolved_list": [resolved_themes] if resolved_themes else []}
    elif isinstance(rb.get("resolved_theme_info"), dict):
        resolved_info = dict(rb.get("resolved_theme_info"))  # type: ignore[arg-type]

    if resolved_info is None:
        resolved_info = {}

    if auto_fill_enabled is not None:
        resolved_info["auto_fill_enabled"] = bool(auto_fill_enabled)
    if auto_fill_secondary_enabled is not None:
        resolved_info["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
    if auto_fill_tertiary_enabled is not None:
        resolved_info["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
    if auto_fill_applied is not None:
        resolved_info["auto_fill_applied"] = bool(auto_fill_applied)
    if auto_filled_themes is not None:
        resolved_info["auto_filled_themes"] = _coerce_str_list(auto_filled_themes)
    if display_themes is not None:
        resolved_info["display_list"] = _coerce_str_list(display_themes)

    rb["resolved_theme_info"] = resolved_info

    resolved_list = resolved_info.get("resolved_list")
    if isinstance(resolved_list, list):
        rb["resolved_themes"] = list(resolved_list)
    primary_resolved = resolved_info.get("primary")
    secondary_resolved = resolved_info.get("secondary")
    tertiary_resolved = resolved_info.get("tertiary")
    if primary_resolved:
        rb["primary_theme"] = primary_resolved
    if secondary_resolved:
        rb["secondary_theme"] = secondary_resolved
    if tertiary_resolved:
        rb["tertiary_theme"] = tertiary_resolved
    if "combo_fallback" in resolved_info:
        rb["combo_fallback"] = bool(resolved_info.get("combo_fallback"))
    if "synergy_fallback" in resolved_info:
        rb["synergy_fallback"] = bool(resolved_info.get("synergy_fallback"))
    if "fallback_reason" in resolved_info and resolved_info.get("fallback_reason") is not None:
        rb["fallback_reason"] = resolved_info.get("fallback_reason")
    if "display_list" in resolved_info and isinstance(resolved_info.get("display_list"), list):
        rb["display_themes"] = list(resolved_info.get("display_list") or [])
    if "auto_fill_enabled" in resolved_info and resolved_info.get("auto_fill_enabled") is not None:
        rb["auto_fill_enabled"] = bool(resolved_info.get("auto_fill_enabled"))
    if "auto_fill_secondary_enabled" in resolved_info and resolved_info.get("auto_fill_secondary_enabled") is not None:
        rb["auto_fill_secondary_enabled"] = bool(resolved_info.get("auto_fill_secondary_enabled"))
    if "auto_fill_tertiary_enabled" in resolved_info and resolved_info.get("auto_fill_tertiary_enabled") is not None:
        rb["auto_fill_tertiary_enabled"] = bool(resolved_info.get("auto_fill_tertiary_enabled"))
    if "auto_fill_enabled" not in rb:
        rb["auto_fill_enabled"] = bool(rb.get("auto_fill_secondary_enabled") or rb.get("auto_fill_tertiary_enabled"))
    if "auto_fill_applied" in resolved_info and resolved_info.get("auto_fill_applied") is not None:
        rb["auto_fill_applied"] = bool(resolved_info.get("auto_fill_applied"))
    if "auto_filled_themes" in resolved_info and resolved_info.get("auto_filled_themes") is not None:
        rb["auto_filled_themes"] = list(resolved_info.get("auto_filled_themes") or [])

    if display_themes is not None:
        rb["display_themes"] = _coerce_str_list(display_themes)
    if auto_fill_applied is not None:
        rb["auto_fill_applied"] = bool(auto_fill_applied)
    if auto_filled_themes is not None:
        rb["auto_filled_themes"] = _coerce_str_list(auto_filled_themes)

    recent = list(rb.get("recent_seeds") or [])
    recent.append(int(seed))
    seen: set[int] = set()
    dedup_rev: list[int] = []
    for s in reversed(recent):
        if s in seen:
            continue
        seen.add(s)
        dedup_rev.append(s)
    rb["recent_seeds"] = list(reversed(dedup_rev))[-10:]

    if request_timestamp is not None:
        try:
            rb["last_random_request_ts"] = float(request_timestamp)
        except Exception:
            pass

    set_session_value(sid, "random_build", rb)
    return sid, had_cookie


def _get_random_session_themes(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retrieve previously requested and resolved theme data without mutating the session state."""
    sid = request.cookies.get("sid")
    if not sid:
        return {}, {}
    try:
        sess = get_session(sid)
    except Exception:
        return {}, {}
    rb = sess.get("random_build") or {}
    requested = dict(rb.get("requested_themes") or {})
    if "auto_fill_enabled" in requested:
        requested["auto_fill_enabled"] = bool(_sanitize_bool(requested.get("auto_fill_enabled"), default=False))
    elif rb.get("auto_fill_enabled") is not None:
        requested["auto_fill_enabled"] = bool(rb.get("auto_fill_enabled"))

    if "auto_fill_secondary_enabled" in requested:
        requested["auto_fill_secondary_enabled"] = bool(_sanitize_bool(requested.get("auto_fill_secondary_enabled"), default=requested.get("auto_fill_enabled", False)))
    elif rb.get("auto_fill_secondary_enabled") is not None:
        requested["auto_fill_secondary_enabled"] = bool(rb.get("auto_fill_secondary_enabled"))

    if "auto_fill_tertiary_enabled" in requested:
        requested["auto_fill_tertiary_enabled"] = bool(_sanitize_bool(requested.get("auto_fill_tertiary_enabled"), default=requested.get("auto_fill_enabled", False)))
    elif rb.get("auto_fill_tertiary_enabled") is not None:
        requested["auto_fill_tertiary_enabled"] = bool(rb.get("auto_fill_tertiary_enabled"))

    if "strict_theme_match" in requested:
        requested["strict_theme_match"] = bool(_sanitize_bool(requested.get("strict_theme_match"), default=False))
    elif rb.get("strict_theme_match") is not None:
        requested["strict_theme_match"] = bool(rb.get("strict_theme_match"))

    resolved: dict[str, Any] = {}
    raw_resolved = rb.get("resolved_theme_info")
    if isinstance(raw_resolved, dict):
        resolved = dict(raw_resolved)
    else:
        legacy_resolved = rb.get("resolved_themes")
        if isinstance(legacy_resolved, dict):
            resolved = dict(legacy_resolved)
        elif isinstance(legacy_resolved, list):
            resolved = {"resolved_list": list(legacy_resolved)}
        else:
            resolved = {}

    if "resolved_list" not in resolved or not isinstance(resolved.get("resolved_list"), list):
        candidates = [requested.get("primary"), requested.get("secondary"), requested.get("tertiary")]
        resolved["resolved_list"] = [t for t in candidates if t]
    if "primary" not in resolved and rb.get("primary_theme"):
        resolved["primary"] = rb.get("primary_theme")
    if "secondary" not in resolved and rb.get("secondary_theme"):
        resolved["secondary"] = rb.get("secondary_theme")
    if "tertiary" not in resolved and rb.get("tertiary_theme"):
        resolved["tertiary"] = rb.get("tertiary_theme")
    if "combo_fallback" not in resolved and rb.get("combo_fallback") is not None:
        resolved["combo_fallback"] = bool(rb.get("combo_fallback"))
    if "synergy_fallback" not in resolved and rb.get("synergy_fallback") is not None:
        resolved["synergy_fallback"] = bool(rb.get("synergy_fallback"))
    if "fallback_reason" not in resolved and rb.get("fallback_reason") is not None:
        resolved["fallback_reason"] = rb.get("fallback_reason")
    if "display_list" not in resolved and isinstance(rb.get("display_themes"), list):
        resolved["display_list"] = list(rb.get("display_themes") or [])
    if "auto_fill_enabled" in resolved:
        resolved["auto_fill_enabled"] = bool(_sanitize_bool(resolved.get("auto_fill_enabled"), default=False))
    elif rb.get("auto_fill_enabled") is not None:
        resolved["auto_fill_enabled"] = bool(rb.get("auto_fill_enabled"))
    if "auto_fill_secondary_enabled" in resolved:
        resolved["auto_fill_secondary_enabled"] = bool(_sanitize_bool(resolved.get("auto_fill_secondary_enabled"), default=resolved.get("auto_fill_enabled", False)))
    elif rb.get("auto_fill_secondary_enabled") is not None:
        resolved["auto_fill_secondary_enabled"] = bool(rb.get("auto_fill_secondary_enabled"))
    if "auto_fill_tertiary_enabled" in resolved:
        resolved["auto_fill_tertiary_enabled"] = bool(_sanitize_bool(resolved.get("auto_fill_tertiary_enabled"), default=resolved.get("auto_fill_enabled", False)))
    elif rb.get("auto_fill_tertiary_enabled") is not None:
        resolved["auto_fill_tertiary_enabled"] = bool(rb.get("auto_fill_tertiary_enabled"))
    if "auto_fill_applied" in resolved:
        resolved["auto_fill_applied"] = bool(_sanitize_bool(resolved.get("auto_fill_applied"), default=False))
    elif rb.get("auto_fill_applied") is not None:
        resolved["auto_fill_applied"] = bool(rb.get("auto_fill_applied"))
    if "auto_filled_themes" not in resolved and isinstance(rb.get("auto_filled_themes"), list):
        resolved["auto_filled_themes"] = list(rb.get("auto_filled_themes") or [])
    return requested, resolved

def _toggle_seed_favorite(sid: str, seed: int) -> list[int]:
    """Toggle a seed in the favorites list and persist. Returns updated favorites."""
    sess = get_session(sid)
    rb = dict(sess.get("random_build") or {})
    favs = list(rb.get("favorite_seeds") or [])
    if seed in favs:
        favs = [s for s in favs if s != seed]
    else:
        favs.append(seed)
    # Keep stable ordering (insertion order) and cap to last 50
    favs = favs[-50:]
    rb["favorite_seeds"] = favs
    set_session_value(sid, "random_build", rb)
    return favs

templates.env.globals["render_cached"] = render_cached

# --- Diagnostics: request-id and uptime ---
_APP_START_TIME = time.time()

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign or propagate a request id and attach to response headers."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception as ex:
        # Log and re-raise so FastAPI exception handlers can format the response.
        logging.getLogger("web").error(f"Unhandled error [rid={rid}]: {ex}", exc_info=True)
        raise
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request, "version": os.getenv("APP_VERSION", "dev")})


# Simple health check (hardened)
@app.get("/healthz")
async def healthz():
    try:
        version = os.getenv("APP_VERSION", "dev")
        uptime_s = int(time.time() - _APP_START_TIME)
        return {"status": "ok", "version": version, "uptime_seconds": uptime_s}
    except Exception:
        # Avoid throwing from health
        return {"status": "degraded"}

# System summary endpoint for diagnostics
@app.get("/status/sys")
async def status_sys():
    try:
        version = os.getenv("APP_VERSION", "dev")
        uptime_s = int(time.time() - _APP_START_TIME)
        server_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {
            "version": version,
            "uptime_seconds": uptime_s,
            "server_time_utc": server_time,
            "flags": {
                "SHOW_LOGS": bool(SHOW_LOGS),
                "SHOW_SETUP": bool(SHOW_SETUP),
                "SHOW_COMMANDERS": bool(SHOW_COMMANDERS),
                "SHOW_DIAGNOSTICS": bool(SHOW_DIAGNOSTICS),
                "ENABLE_THEMES": bool(ENABLE_THEMES),
                "ENABLE_PWA": bool(ENABLE_PWA),
                "ENABLE_PRESETS": bool(ENABLE_PRESETS),
                "ALLOW_MUST_HAVES": bool(ALLOW_MUST_HAVES),
                "DEFAULT_THEME": DEFAULT_THEME,
                "RANDOM_MODES": bool(RANDOM_MODES),
                "RANDOM_UI": bool(RANDOM_UI),
                "RANDOM_MAX_ATTEMPTS": int(RANDOM_MAX_ATTEMPTS),
                "RANDOM_TIMEOUT_MS": int(RANDOM_TIMEOUT_MS),
                "RANDOM_TELEMETRY": bool(RANDOM_TELEMETRY),
                "RANDOM_STRUCTURED_LOGS": bool(RANDOM_STRUCTURED_LOGS),
                "RANDOM_RATE_LIMIT": bool(RATE_LIMIT_ENABLED),
                "RATE_LIMIT_WINDOW_S": int(RATE_LIMIT_WINDOW_S),
                "RANDOM_RATE_LIMIT_RANDOM": int(RATE_LIMIT_RANDOM),
                "RANDOM_RATE_LIMIT_BUILD": int(RATE_LIMIT_BUILD),
                "RANDOM_RATE_LIMIT_SUGGEST": int(RATE_LIMIT_SUGGEST),
                "RANDOM_REROLL_THROTTLE_MS": int(RANDOM_REROLL_THROTTLE_MS),
            },
        }
    except Exception:
        return {"version": "unknown", "uptime_seconds": 0, "flags": {}}

@app.get("/status/random_metrics")
async def status_random_metrics():
    try:
        if not RANDOM_TELEMETRY:
            return JSONResponse({"ok": False, "error": "telemetry_disabled"}, status_code=403)
        # Return a shallow copy to avoid mutation from clients
        out = {k: dict(v) for k, v in _RANDOM_METRICS.items()}
        usage = {
            "modes": dict(_RANDOM_USAGE_METRICS),
            "fallbacks": dict(_RANDOM_FALLBACK_METRICS),
            "fallback_reasons": dict(_RANDOM_FALLBACK_REASONS),
        }
        return JSONResponse({"ok": True, "metrics": out, "usage": usage})
    except Exception:
        return JSONResponse({"ok": False, "metrics": {}}, status_code=500)

@app.get("/status/random_theme_stats")
async def status_random_theme_stats():
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        from deck_builder.random_entrypoint import get_theme_tag_stats  # type: ignore

        stats = get_theme_tag_stats()
        return JSONResponse({"ok": True, "stats": stats})
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive log
        logging.getLogger("web").warning("Failed to build random theme stats: %s", exc, exc_info=True)
        return JSONResponse({"ok": False, "error": "internal_error"}, status_code=500)


def random_modes_enabled() -> bool:
    """Dynamic check so tests that set env after import still work.

    Keeps legacy global for template snapshot while allowing runtime override."""
    return _as_bool(os.getenv("RANDOM_MODES"), bool(RANDOM_MODES))

# --- Random Modes API ---
@app.post("/api/random_build")
async def api_random_build(request: Request):
    # Gate behind feature flag
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    try:
        t0 = time.time()
        # Optional rate limiting (count this request per-IP)
        rl = rate_limit_check(request, "build")
        _enforce_random_session_throttle(request)
        body = {}
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
        legacy_theme = _sanitize_theme(body.get("theme"))
        primary_theme = _sanitize_theme(body.get("primary_theme"))
        secondary_theme = _sanitize_theme(body.get("secondary_theme"))
        tertiary_theme = _sanitize_theme(body.get("tertiary_theme"))
        auto_fill_enabled, auto_fill_secondary_enabled, auto_fill_tertiary_enabled = _parse_auto_fill_flags(body)
        strict_theme_match = bool(_sanitize_bool(body.get("strict_theme_match"), default=False))
        if primary_theme is None:
            primary_theme = legacy_theme
        theme = primary_theme or legacy_theme
        constraints = body.get("constraints")
        seed = body.get("seed")
        attempts = body.get("attempts", int(RANDOM_MAX_ATTEMPTS))
        timeout_ms = body.get("timeout_ms", int(RANDOM_TIMEOUT_MS))
        # Convert ms -> seconds, clamp minimal
        try:
            timeout_s = max(0.1, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = max(0.1, float(RANDOM_TIMEOUT_MS) / 1000.0)
        # Import on-demand to avoid heavy costs at module import time
        from deck_builder.random_entrypoint import build_random_deck, RandomConstraintsImpossibleError  # type: ignore
        from deck_builder.random_entrypoint import RandomThemeNoMatchError  # type: ignore

        res = build_random_deck(
            theme=theme,
            constraints=constraints,
            seed=seed,
            attempts=int(attempts),
            timeout_s=float(timeout_s),
            primary_theme=primary_theme,
            secondary_theme=secondary_theme,
            tertiary_theme=tertiary_theme,
            auto_fill_missing=bool(auto_fill_enabled),
            auto_fill_secondary=auto_fill_secondary_enabled,
            auto_fill_tertiary=auto_fill_tertiary_enabled,
            strict_theme_match=strict_theme_match,
        )
        rid = getattr(request.state, "request_id", None)
        _record_random_event("build", success=True)
        elapsed_ms = int(round((time.time() - t0) * 1000))
        _log_random_event(
            "build",
            request,
            "success",
            seed=int(res.seed),
            theme=(res.theme or None),
            attempts=int(attempts),
            timeout_ms=int(timeout_ms),
            elapsed_ms=elapsed_ms,
        )
        payload = {
            "seed": int(res.seed),
            "commander": res.commander,
            "theme": res.theme,
            "primary_theme": getattr(res, "primary_theme", None),
            "secondary_theme": getattr(res, "secondary_theme", None),
            "tertiary_theme": getattr(res, "tertiary_theme", None),
            "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
            "display_themes": list(getattr(res, "display_themes", []) or []),
            "combo_fallback": bool(getattr(res, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
            "fallback_reason": getattr(res, "fallback_reason", None),
            "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
            "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
            "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
            "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
            "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
            "strict_theme_match": bool(getattr(res, "strict_theme_match", False)),
            "constraints": res.constraints or {},
            "attempts": int(attempts),
            "timeout_ms": int(timeout_ms),
            "request_id": rid,
        }
        resp = JSONResponse(payload)
        if rl:
            remaining, reset_epoch = rl
            try:
                resp.headers["X-RateLimit-Remaining"] = str(remaining)
                resp.headers["X-RateLimit-Reset"] = str(reset_epoch)
            except Exception:
                pass
        return resp
    except RandomThemeNoMatchError as ex:
        _record_random_event("build", error=True)
        _log_random_event("build", request, "strict_no_match", reason=str(ex))
        raise HTTPException(status_code=422, detail={
            "error": "strict_theme_no_match",
            "message": str(ex),
            "strict": True,
        })
    except HTTPException:
        raise
    except RandomConstraintsImpossibleError as ex:
        _record_random_event("build", constraints_impossible=True)
        _log_random_event("build", request, "constraints_impossible")
        raise HTTPException(status_code=422, detail={"error": "constraints_impossible", "message": str(ex), "constraints": ex.constraints, "pool_size": ex.pool_size})
    except Exception as ex:
        logging.getLogger("web").error(f"random_build failed: {ex}")
        _record_random_event("build", error=True)
        _log_random_event("build", request, "error")
        raise HTTPException(status_code=500, detail="random_build failed")


@app.post("/api/random_full_build")
async def api_random_full_build(request: Request):
    # Gate behind feature flag
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    try:
        t0 = time.time()
        rl = rate_limit_check(request, "build")
        body = {}
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
        cached_requested, _cached_resolved = _get_random_session_themes(request)
        legacy_theme = _sanitize_theme(body.get("theme"))
        primary_theme = _sanitize_theme(body.get("primary_theme"))
        secondary_theme = _sanitize_theme(body.get("secondary_theme"))
        tertiary_theme = _sanitize_theme(body.get("tertiary_theme"))
        cached_enabled = _sanitize_bool(cached_requested.get("auto_fill_enabled"), default=False)
        cached_secondary = _sanitize_bool(cached_requested.get("auto_fill_secondary_enabled"), default=cached_enabled)
        cached_tertiary = _sanitize_bool(cached_requested.get("auto_fill_tertiary_enabled"), default=cached_enabled)
        auto_fill_enabled, auto_fill_secondary_enabled, auto_fill_tertiary_enabled = _parse_auto_fill_flags(
            body,
            default_enabled=cached_enabled,
            default_secondary=cached_secondary,
            default_tertiary=cached_tertiary,
        )
        cached_strict = _sanitize_bool(cached_requested.get("strict_theme_match"), default=False)
        strict_sanitized = _sanitize_bool(body.get("strict_theme_match"), default=cached_strict)
        strict_theme_match = bool(strict_sanitized) if strict_sanitized is not None else bool(cached_strict)
        cached_strict = _sanitize_bool(cached_requested.get("strict_theme_match"), default=False)
        strict_theme_match_raw = _sanitize_bool(body.get("strict_theme_match"), default=cached_strict)
        strict_theme_match = bool(strict_theme_match_raw) if strict_theme_match_raw is not None else False
        if primary_theme is None:
            primary_theme = legacy_theme
        theme = primary_theme or legacy_theme
        constraints = body.get("constraints")
        seed = body.get("seed")
        attempts = body.get("attempts", int(RANDOM_MAX_ATTEMPTS))
        timeout_ms = body.get("timeout_ms", int(RANDOM_TIMEOUT_MS))
        # Convert ms -> seconds, clamp minimal
        try:
            timeout_s = max(0.1, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = max(0.1, float(RANDOM_TIMEOUT_MS) / 1000.0)

        # Build a full deck deterministically
        from deck_builder.random_entrypoint import build_random_full_deck, RandomConstraintsImpossibleError  # type: ignore
        res = build_random_full_deck(
            theme=theme,
            constraints=constraints,
            seed=seed,
            attempts=int(attempts),
            timeout_s=float(timeout_s),
            primary_theme=primary_theme,
            secondary_theme=secondary_theme,
            tertiary_theme=tertiary_theme,
            auto_fill_missing=bool(auto_fill_enabled),
            auto_fill_secondary=auto_fill_secondary_enabled,
            auto_fill_tertiary=auto_fill_tertiary_enabled,
            strict_theme_match=strict_theme_match,
        )

        requested_themes = {
            "primary": primary_theme,
            "secondary": secondary_theme,
            "tertiary": tertiary_theme,
            "legacy": legacy_theme,
        }
        requested_themes["auto_fill_enabled"] = bool(auto_fill_enabled)
        requested_themes["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
        requested_themes["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
        requested_themes["strict_theme_match"] = bool(strict_theme_match)
        resolved_theme_info = {
            "primary": getattr(res, "primary_theme", None),
            "secondary": getattr(res, "secondary_theme", None),
            "tertiary": getattr(res, "tertiary_theme", None),
            "resolved_list": list(getattr(res, "resolved_themes", []) or []),
            "combo_fallback": bool(getattr(res, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
            "fallback_reason": getattr(res, "fallback_reason", None),
            "display_list": list(getattr(res, "display_themes", []) or []),
            "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
            "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
            "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
            "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
            "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
        }
        resolved_theme_info["strict_theme_match"] = bool(getattr(res, "strict_theme_match", False))

        # Create a permalink token reusing the existing format from /build/permalink
        payload = {
            "commander": res.commander,
            # Note: tags/bracket/ideals omitted; random modes focuses on seed replay
            "random": {
                "seed": int(res.seed),
                "theme": res.theme,
                "constraints": res.constraints or {},
                "primary_theme": getattr(res, "primary_theme", None),
                "secondary_theme": getattr(res, "secondary_theme", None),
                "tertiary_theme": getattr(res, "tertiary_theme", None),
                "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
                "display_themes": list(getattr(res, "display_themes", []) or []),
                "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                "fallback_reason": getattr(res, "fallback_reason", None),
                "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                "strict_theme_match": bool(getattr(res, "strict_theme_match", False)),
                "requested_themes": requested_themes,
            },
        }
        try:
            import base64
            raw = _json.dumps(payload, separators=(",", ":"))
            token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
            permalink = f"/build/from?state={token}"
        except Exception:
            permalink = None

        usage_mode = _classify_usage_mode("full_build", [primary_theme, secondary_theme, tertiary_theme, legacy_theme], None)
        combo_flag = bool(getattr(res, "combo_fallback", False))
        synergy_flag = bool(getattr(res, "synergy_fallback", False))
        _record_random_usage_event(usage_mode, combo_flag, synergy_flag, getattr(res, "fallback_reason", None))

        # Persist to session (so recent seeds includes initial seed)
        request_timestamp = time.time()
        sid, had_cookie = _update_random_session(
            request,
            seed=int(res.seed),
            theme=res.theme,
            constraints=res.constraints or {},
            requested_themes=requested_themes,
            resolved_themes=resolved_theme_info,
            auto_fill_enabled=auto_fill_enabled,
            auto_fill_secondary_enabled=auto_fill_secondary_enabled,
            auto_fill_tertiary_enabled=auto_fill_tertiary_enabled,
            strict_theme_match=strict_theme_match,
            auto_fill_applied=bool(getattr(res, "auto_fill_applied", False)),
            auto_filled_themes=getattr(res, "auto_filled_themes", None),
            display_themes=getattr(res, "display_themes", None),
            request_timestamp=request_timestamp,
        )
        rid = getattr(request.state, "request_id", None)
        _record_random_event("full_build", success=True, fallback=bool(getattr(res, "theme_fallback", False)))
        elapsed_ms = int(round((request_timestamp - t0) * 1000))
        _log_random_event(
            "full_build",
            request,
            "success",
            seed=int(res.seed),
            theme=(res.theme or None),
            attempts=int(attempts),
            timeout_ms=int(timeout_ms),
            elapsed_ms=elapsed_ms,
            fallback=bool(getattr(res, "theme_fallback", False)),
        )
        resp = JSONResponse({
            "seed": int(res.seed),
            "commander": res.commander,
            "decklist": res.decklist or [],
            "theme": res.theme,
            "primary_theme": getattr(res, "primary_theme", None),
            "secondary_theme": getattr(res, "secondary_theme", None),
            "tertiary_theme": getattr(res, "tertiary_theme", None),
            "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
            "display_themes": list(getattr(res, "display_themes", []) or []),
            "combo_fallback": bool(getattr(res, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
            "fallback_reason": getattr(res, "fallback_reason", None),
            "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
            "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
            "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
            "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
            "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
            "strict_theme_match": bool(getattr(res, "strict_theme_match", False)),
            "constraints": res.constraints or {},
            "permalink": permalink,
            "attempts": int(attempts),
            "timeout_ms": int(timeout_ms),
            "diagnostics": res.diagnostics or {},
            "fallback": bool(getattr(res, "theme_fallback", False)),
            "original_theme": getattr(res, "original_theme", None),
            "requested_themes": requested_themes,
            "resolved_theme_info": resolved_theme_info,
            "summary": getattr(res, "summary", None),
            "csv_path": getattr(res, "csv_path", None),
            "txt_path": getattr(res, "txt_path", None),
            "compliance": getattr(res, "compliance", None),
            "request_id": rid,
        })
        if rl:
            remaining, reset_epoch = rl
            try:
                resp.headers["X-RateLimit-Remaining"] = str(remaining)
                resp.headers["X-RateLimit-Reset"] = str(reset_epoch)
            except Exception:
                pass
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60*60*8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
    except HTTPException:
        raise
    except RandomConstraintsImpossibleError as ex:
        _record_random_event("full_build", constraints_impossible=True)
        _log_random_event("full_build", request, "constraints_impossible")
        raise HTTPException(status_code=422, detail={"error": "constraints_impossible", "message": str(ex), "constraints": ex.constraints, "pool_size": ex.pool_size})
    except Exception as ex:
        logging.getLogger("web").error(f"random_full_build failed: {ex}")
        _record_random_event("full_build", error=True)
        _log_random_event("full_build", request, "error")
        raise HTTPException(status_code=500, detail="random_full_build failed")

@app.post("/api/random_reroll")
async def api_random_reroll(request: Request):
    # Gate behind feature flag
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    strict_theme_match = False
    try:
        t0 = time.time()
        rl = rate_limit_check(request, "random")
        _enforce_random_session_throttle(request)
        body = {}
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
        cached_requested, _cached_resolved = _get_random_session_themes(request)
        legacy_theme = _sanitize_theme(body.get("theme"))
        primary_theme = _sanitize_theme(body.get("primary_theme"))
        secondary_theme = _sanitize_theme(body.get("secondary_theme"))
        tertiary_theme = _sanitize_theme(body.get("tertiary_theme"))
        cached_enabled = _sanitize_bool(cached_requested.get("auto_fill_enabled"), default=False)
        cached_secondary = _sanitize_bool(cached_requested.get("auto_fill_secondary_enabled"), default=cached_enabled)
        cached_tertiary = _sanitize_bool(cached_requested.get("auto_fill_tertiary_enabled"), default=cached_enabled)
        auto_fill_enabled, auto_fill_secondary_enabled, auto_fill_tertiary_enabled = _parse_auto_fill_flags(
            body,
            default_enabled=cached_enabled,
            default_secondary=cached_secondary,
            default_tertiary=cached_tertiary,
        )
        if primary_theme is None:
            primary_theme = legacy_theme
        # Fallback to cached session preferences when no themes provided
        if primary_theme is None and secondary_theme is None and tertiary_theme is None:
            if not primary_theme:
                primary_theme = _sanitize_theme(cached_requested.get("primary"))
            if not secondary_theme:
                secondary_theme = _sanitize_theme(cached_requested.get("secondary"))
            if not tertiary_theme:
                tertiary_theme = _sanitize_theme(cached_requested.get("tertiary"))
            if not legacy_theme:
                legacy_theme = _sanitize_theme(cached_requested.get("legacy"))
        theme = primary_theme or legacy_theme
        constraints = body.get("constraints")
        last_seed = body.get("seed")
        # Simple deterministic reroll policy: increment prior seed when provided; else generate fresh
        try:
            new_seed = int(last_seed) + 1 if last_seed is not None else None
        except Exception:
            new_seed = None
        if new_seed is None:
            from random_util import generate_seed  # type: ignore
            new_seed = int(generate_seed())

        # Build with the new seed
        timeout_ms = body.get("timeout_ms", int(RANDOM_TIMEOUT_MS))
        try:
            timeout_s = max(0.1, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = max(0.1, float(RANDOM_TIMEOUT_MS) / 1000.0)
        attempts = body.get("attempts", int(RANDOM_MAX_ATTEMPTS))

        from deck_builder.random_entrypoint import build_random_full_deck  # type: ignore
        res = build_random_full_deck(
            theme=theme,
            constraints=constraints,
            seed=new_seed,
            attempts=int(attempts),
            timeout_s=float(timeout_s),
            primary_theme=primary_theme,
            secondary_theme=secondary_theme,
            tertiary_theme=tertiary_theme,
            auto_fill_missing=bool(auto_fill_enabled),
            auto_fill_secondary=auto_fill_secondary_enabled,
            auto_fill_tertiary=auto_fill_tertiary_enabled,
            strict_theme_match=strict_theme_match,
        )

        requested_themes = {
            "primary": primary_theme,
            "secondary": secondary_theme,
            "tertiary": tertiary_theme,
            "legacy": legacy_theme,
        }
        requested_themes["auto_fill_enabled"] = bool(auto_fill_enabled)
        requested_themes["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
        requested_themes["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
        requested_themes["strict_theme_match"] = bool(strict_theme_match)
        resolved_theme_info = {
            "primary": getattr(res, "primary_theme", None),
            "secondary": getattr(res, "secondary_theme", None),
            "tertiary": getattr(res, "tertiary_theme", None),
            "resolved_list": list(getattr(res, "resolved_themes", []) or []),
            "combo_fallback": bool(getattr(res, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
            "fallback_reason": getattr(res, "fallback_reason", None),
            "display_list": list(getattr(res, "display_themes", []) or []),
            "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
            "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
            "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
            "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
            "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
            "strict_theme_match": bool(getattr(res, "strict_theme_match", strict_theme_match)),
        }

        payload = {
            "commander": res.commander,
            "random": {
                "seed": int(res.seed),
                "theme": res.theme,
                "constraints": res.constraints or {},
                "primary_theme": getattr(res, "primary_theme", None),
                "secondary_theme": getattr(res, "secondary_theme", None),
                "tertiary_theme": getattr(res, "tertiary_theme", None),
                "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
                "display_themes": list(getattr(res, "display_themes", []) or []),
                "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                "fallback_reason": getattr(res, "fallback_reason", None),
                "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                "strict_theme_match": bool(getattr(res, "strict_theme_match", strict_theme_match)),
                "requested_themes": requested_themes,
            },
        }
        try:
            import base64
            raw = _json.dumps(payload, separators=(",", ":"))
            token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
            permalink = f"/build/from?state={token}"
        except Exception:
            permalink = None

        usage_mode = _classify_usage_mode("reroll", [primary_theme, secondary_theme, tertiary_theme, legacy_theme], None)
        combo_flag = bool(getattr(res, "combo_fallback", False))
        synergy_flag = bool(getattr(res, "synergy_fallback", False))
        _record_random_usage_event(usage_mode, combo_flag, synergy_flag, getattr(res, "fallback_reason", None))

        # Persist in session and set sid cookie if we just created it
        request_timestamp = time.time()
        sid, had_cookie = _update_random_session(
            request,
            seed=int(res.seed),
            theme=res.theme,
            constraints=res.constraints or {},
            requested_themes=requested_themes,
            resolved_themes=resolved_theme_info,
            auto_fill_enabled=auto_fill_enabled,
            auto_fill_secondary_enabled=auto_fill_secondary_enabled,
            auto_fill_tertiary_enabled=auto_fill_tertiary_enabled,
            strict_theme_match=bool(getattr(res, "strict_theme_match", strict_theme_match)),
            auto_fill_applied=bool(getattr(res, "auto_fill_applied", False)),
            auto_filled_themes=getattr(res, "auto_filled_themes", None),
            display_themes=getattr(res, "display_themes", None),
            request_timestamp=request_timestamp,
        )
        rid = getattr(request.state, "request_id", None)
        _record_random_event("reroll", success=True, fallback=bool(getattr(res, "theme_fallback", False)))
        elapsed_ms = int(round((request_timestamp - t0) * 1000))
        _log_random_event(
            "reroll",
            request,
            "success",
            seed=int(res.seed),
            theme=(res.theme or None),
            attempts=int(attempts),
            timeout_ms=int(timeout_ms),
            elapsed_ms=elapsed_ms,
            prev_seed=(int(last_seed) if isinstance(last_seed, int) or (isinstance(last_seed, str) and str(last_seed).isdigit()) else None),
            fallback=bool(getattr(res, "theme_fallback", False)),
        )
        resp = JSONResponse({
            "previous_seed": (int(last_seed) if isinstance(last_seed, int) or (isinstance(last_seed, str) and str(last_seed).isdigit()) else None),
            "seed": int(res.seed),
            "commander": res.commander,
            "decklist": res.decklist or [],
            "theme": res.theme,
            "primary_theme": getattr(res, "primary_theme", None),
            "secondary_theme": getattr(res, "secondary_theme", None),
            "tertiary_theme": getattr(res, "tertiary_theme", None),
            "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
            "display_themes": list(getattr(res, "display_themes", []) or []),
            "combo_fallback": bool(getattr(res, "combo_fallback", False)),
            "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
            "fallback_reason": getattr(res, "fallback_reason", None),
            "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
            "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
            "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
            "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
            "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
            "strict_theme_match": bool(getattr(res, "strict_theme_match", strict_theme_match)),
            "constraints": res.constraints or {},
            "permalink": permalink,
            "attempts": int(attempts),
            "timeout_ms": int(timeout_ms),
            "diagnostics": res.diagnostics or {},
            "summary": getattr(res, "summary", None),
            "requested_themes": requested_themes,
            "resolved_theme_info": resolved_theme_info,
            "request_id": rid,
        })
        if rl:
            remaining, reset_epoch = rl
            try:
                resp.headers["X-RateLimit-Remaining"] = str(remaining)
                resp.headers["X-RateLimit-Reset"] = str(reset_epoch)
            except Exception:
                pass
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60*60*8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
    except HTTPException:
        raise
    except Exception as ex:
        logging.getLogger("web").error(f"random_reroll failed: {ex}")
        _record_random_event("reroll", error=True)
        _log_random_event("reroll", request, "error")
        raise HTTPException(status_code=500, detail="random_reroll failed")


@app.post("/hx/random_reroll")
async def hx_random_reroll(request: Request):
    # Small HTMX endpoint returning a partial HTML fragment for in-page updates
    if not RANDOM_UI or not RANDOM_MODES:
        raise HTTPException(status_code=404, detail="Random UI disabled")
    rl = rate_limit_check(request, "random")
    _enforce_random_session_throttle(request)
    body: Dict[str, Any] = {}
    raw_text = ""
    # Primary: attempt JSON
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    # Fallback: form/urlencoded (htmx default) or stray query-like payload
    if not body:
        try:
            raw_bytes = await request.body()
            raw_text = raw_bytes.decode("utf-8", errors="ignore")
            from urllib.parse import parse_qs
            parsed = parse_qs(raw_text, keep_blank_values=True)
            flat: Dict[str, Any] = {}
            for k, v in parsed.items():
                if not v:
                    continue
                flat[k] = v[0] if len(v) == 1 else v
            body = flat or {}
        except Exception:
            body = {}
    def _first_value(val: Any) -> Any:
        if isinstance(val, list):
            return val[0] if val else None
        return val

    def _extract_theme_field(field: str) -> tuple[Optional[str], bool]:
        present = field in body
        val = body.get(field)
        if isinstance(val, list):
            for item in val:
                sanitized = _sanitize_theme(item)
                if sanitized is not None:
                    return sanitized, True
            return None, present
        return _sanitize_theme(val), present

    def _extract_resolved_list(val: Any) -> list[str]:
        items: list[str] = []
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, str):
                    parts = [seg.strip() for seg in entry.split("||") if seg.strip()]
                    if parts:
                        items.extend(parts)
        elif isinstance(val, str):
            items = [seg.strip() for seg in val.split("||") if seg.strip()]
        return items

    last_seed = _first_value(body.get("seed"))
    raw_mode = _first_value(body.get("mode"))
    mode = "surprise"
    if raw_mode is not None:
        if isinstance(raw_mode, str):
            raw_mode_str = raw_mode.strip()
            if raw_mode_str.startswith("{") and raw_mode_str.endswith("}"):
                try:
                    parsed_mode = _json.loads(raw_mode_str)
                    candidate = parsed_mode.get("mode") if isinstance(parsed_mode, dict) else None
                    if isinstance(candidate, str) and candidate.strip():
                        mode = candidate.strip().lower()
                    else:
                        mode = raw_mode_str.lower()
                except Exception:
                    mode = raw_mode_str.lower()
            else:
                mode = raw_mode_str.lower()
        else:
            mode = str(raw_mode).strip().lower() or "surprise"
    if not mode:
        mode = "surprise"
    raw_commander = _first_value(body.get("commander"))
    locked_commander: Optional[str] = None
    if isinstance(raw_commander, str):
        candidate = raw_commander.strip()
        locked_commander = candidate if candidate else None
    elif raw_commander is not None:
        candidate = str(raw_commander).strip()
        locked_commander = candidate if candidate else None
    cached_requested, cached_resolved = _get_random_session_themes(request)
    cached_enabled = _sanitize_bool(cached_requested.get("auto_fill_enabled"), default=False)
    cached_secondary = _sanitize_bool(cached_requested.get("auto_fill_secondary_enabled"), default=cached_enabled)
    cached_tertiary = _sanitize_bool(cached_requested.get("auto_fill_tertiary_enabled"), default=cached_enabled)
    flag_source = {
        "auto_fill_enabled": _first_value(body.get("auto_fill_enabled")),
        "auto_fill_secondary_enabled": _first_value(body.get("auto_fill_secondary_enabled")),
        "auto_fill_tertiary_enabled": _first_value(body.get("auto_fill_tertiary_enabled")),
    }
    auto_fill_enabled, auto_fill_secondary_enabled, auto_fill_tertiary_enabled = _parse_auto_fill_flags(
        flag_source,
        default_enabled=cached_enabled,
        default_secondary=cached_secondary,
        default_tertiary=cached_tertiary,
    )
    cached_strict = _sanitize_bool(cached_requested.get("strict_theme_match"), default=False)
    strict_raw = _first_value(body.get("strict_theme_match"))
    strict_sanitized = _sanitize_bool(strict_raw, default=cached_strict)
    strict_theme_match = bool(strict_sanitized) if strict_sanitized is not None else bool(cached_strict)
    legacy_theme, legacy_provided = _extract_theme_field("theme")
    primary_theme, primary_provided = _extract_theme_field("primary_theme")
    secondary_theme, secondary_provided = _extract_theme_field("secondary_theme")
    tertiary_theme, tertiary_provided = _extract_theme_field("tertiary_theme")
    resolved_list_from_request = _extract_resolved_list(body.get("resolved_themes"))
    if primary_theme is None and legacy_theme is not None:
        primary_theme = legacy_theme
    if not primary_provided and not secondary_provided and not tertiary_provided:
        cached_primary = _sanitize_theme(cached_requested.get("primary"))
        cached_secondary = _sanitize_theme(cached_requested.get("secondary"))
        cached_tertiary = _sanitize_theme(cached_requested.get("tertiary"))
        cached_legacy = _sanitize_theme(cached_requested.get("legacy"))
        if primary_theme is None and cached_primary:
            primary_theme = cached_primary
        if secondary_theme is None and cached_secondary:
            secondary_theme = cached_secondary
        if tertiary_theme is None and cached_tertiary:
            tertiary_theme = cached_tertiary
        if legacy_theme is None and not legacy_provided and cached_legacy:
            legacy_theme = cached_legacy
    theme = primary_theme or legacy_theme
    is_reroll_same = bool(locked_commander)
    if not theme and is_reroll_same:
        theme = _sanitize_theme(cached_resolved.get("primary")) or _sanitize_theme(cached_requested.get("primary"))
    constraints = body.get("constraints")
    if isinstance(constraints, list):
        constraints = constraints[0]
    requested_themes: Optional[Dict[str, Any]]
    if is_reroll_same:
        requested_themes = dict(cached_requested) if cached_requested else None
        if not requested_themes:
            candidate_requested = {
                "primary": primary_theme,
                "secondary": secondary_theme,
                "tertiary": tertiary_theme,
                "legacy": legacy_theme,
            }
            if any(candidate_requested.values()):
                requested_themes = candidate_requested
    else:
        requested_themes = {
            "primary": primary_theme,
            "secondary": secondary_theme,
            "tertiary": tertiary_theme,
            "legacy": legacy_theme,
        }
    if requested_themes is not None:
        requested_themes["auto_fill_enabled"] = bool(auto_fill_enabled)
        requested_themes["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
        requested_themes["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
        requested_themes["strict_theme_match"] = bool(strict_theme_match)
    raw_cached_resolved_list = cached_resolved.get("resolved_list")
    if isinstance(raw_cached_resolved_list, list):
        cached_resolved_list = list(raw_cached_resolved_list)
    elif isinstance(raw_cached_resolved_list, str):
        cached_resolved_list = [seg.strip() for seg in raw_cached_resolved_list.split("||") if seg.strip()]
    else:
        cached_resolved_list = []
    cached_display_list = cached_resolved.get("display_list")
    if isinstance(cached_display_list, list):
        cached_display = list(cached_display_list)
    elif isinstance(cached_display_list, str):
        cached_display = [seg.strip() for seg in cached_display_list.split("||") if seg.strip()]
    else:
        cached_display = []
    cached_auto_filled = cached_resolved.get("auto_filled_themes")
    if isinstance(cached_auto_filled, list):
        cached_auto_filled_list = list(cached_auto_filled)
    else:
        cached_auto_filled_list = []
    resolved_theme_info: Dict[str, Any] = {
        "primary": cached_resolved.get("primary"),
        "secondary": cached_resolved.get("secondary"),
        "tertiary": cached_resolved.get("tertiary"),
        "resolved_list": cached_resolved_list,
        "combo_fallback": bool(cached_resolved.get("combo_fallback")),
        "synergy_fallback": bool(cached_resolved.get("synergy_fallback")),
        "fallback_reason": cached_resolved.get("fallback_reason"),
        "display_list": cached_display,
        "auto_fill_secondary_enabled": bool(_sanitize_bool(cached_resolved.get("auto_fill_secondary_enabled"), default=auto_fill_secondary_enabled)),
        "auto_fill_tertiary_enabled": bool(_sanitize_bool(cached_resolved.get("auto_fill_tertiary_enabled"), default=auto_fill_tertiary_enabled)),
        "auto_fill_enabled": bool(_sanitize_bool(cached_resolved.get("auto_fill_enabled"), default=auto_fill_enabled)),
        "auto_fill_applied": bool(_sanitize_bool(cached_resolved.get("auto_fill_applied"), default=False)),
        "auto_filled_themes": cached_auto_filled_list,
        "strict_theme_match": bool(_sanitize_bool(cached_resolved.get("strict_theme_match"), default=strict_theme_match)),
    }
    if not resolved_theme_info["primary"] and primary_theme:
        resolved_theme_info["primary"] = primary_theme
    if not resolved_theme_info["secondary"] and secondary_theme:
        resolved_theme_info["secondary"] = secondary_theme
    if not resolved_theme_info["tertiary"] and tertiary_theme:
        resolved_theme_info["tertiary"] = tertiary_theme
    if not resolved_theme_info["resolved_list"]:
        if resolved_list_from_request:
            resolved_theme_info["resolved_list"] = resolved_list_from_request
        else:
            resolved_theme_info["resolved_list"] = [t for t in [primary_theme, secondary_theme, tertiary_theme] if t]
    if not resolved_theme_info.get("display_list"):
        resolved_theme_info["display_list"] = list(resolved_theme_info.get("resolved_list") or [])
    resolved_theme_info["auto_fill_enabled"] = bool(auto_fill_enabled)
    resolved_theme_info["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
    resolved_theme_info["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
    attempts_override = _first_value(body.get("attempts"))
    timeout_ms_override = _first_value(body.get("timeout_ms"))
    try:
        new_seed = int(last_seed) + 1 if last_seed is not None else None
    except Exception:
        new_seed = None
    if new_seed is None:
        from random_util import generate_seed  # type: ignore
        new_seed = int(generate_seed())
    # Import outside conditional to avoid UnboundLocalError when branch not taken
    from deck_builder.random_entrypoint import build_random_full_deck  # type: ignore
    try:
        t0 = time.time()
        _attempts = int(attempts_override) if attempts_override is not None else int(RANDOM_MAX_ATTEMPTS)
        try:
            _timeout_ms = int(timeout_ms_override) if timeout_ms_override is not None else int(RANDOM_TIMEOUT_MS)
        except Exception:
            _timeout_ms = int(RANDOM_TIMEOUT_MS)
        _timeout_s = max(0.1, float(_timeout_ms) / 1000.0)
        if is_reroll_same:
            build_t0 = time.time()
            from headless_runner import run as _run  # type: ignore
            # Suppress builder's internal initial export to control artifact generation (matches full random path logic)
            try:
                import os as _os
                if _os.getenv('RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT') is None:
                    _os.environ['RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT'] = '1'
            except Exception:
                pass
            builder = _run(command_name=str(locked_commander), seed=new_seed)
            elapsed_ms = int(round((time.time() - build_t0) * 1000))
            summary = None
            try:
                if hasattr(builder, 'build_deck_summary'):
                    summary = builder.build_deck_summary()  # type: ignore[attr-defined]
            except Exception:
                summary = None
            decklist = []
            try:
                if hasattr(builder, 'deck_list_final'):
                    decklist = getattr(builder, 'deck_list_final')  # type: ignore[attr-defined]
            except Exception:
                decklist = []
            # Controlled artifact export (single pass)
            csv_path = getattr(builder, 'last_csv_path', None)  # type: ignore[attr-defined]
            txt_path = getattr(builder, 'last_txt_path', None)  # type: ignore[attr-defined]
            compliance = None
            try:
                import os as _os
                import json as _json_mod
                # Perform exactly one export sequence now
                if not csv_path and hasattr(builder, 'export_decklist_csv'):
                    try:
                        csv_path = builder.export_decklist_csv()  # type: ignore[attr-defined]
                    except Exception:
                        csv_path = None
                if csv_path and isinstance(csv_path, str):
                    base_path, _ = _os.path.splitext(csv_path)
                    # Ensure txt exists (create if missing)
                    if (not txt_path or not _os.path.isfile(str(txt_path))):
                        try:
                            base_name = _os.path.basename(base_path) + '.txt'
                            if hasattr(builder, 'export_decklist_text'):
                                txt_path = builder.export_decklist_text(filename=base_name)  # type: ignore[attr-defined]
                        except Exception:
                            # Fallback: if a txt already exists from a prior build reuse it
                            if _os.path.isfile(base_path + '.txt'):
                                txt_path = base_path + '.txt'
                    comp_path = base_path + '_compliance.json'
                    if _os.path.isfile(comp_path):
                        try:
                            with open(comp_path, 'r', encoding='utf-8') as _cf:
                                compliance = _json_mod.load(_cf)
                        except Exception:
                            compliance = None
                    else:
                        try:
                            if hasattr(builder, 'compute_and_print_compliance'):
                                compliance = builder.compute_and_print_compliance(base_stem=_os.path.basename(base_path))  # type: ignore[attr-defined]
                        except Exception:
                            compliance = None
                    if summary:
                        sidecar = base_path + '.summary.json'
                        if not _os.path.isfile(sidecar):
                            meta = {
                                "commander": getattr(builder, 'commander_name', '') or getattr(builder, 'commander', ''),
                                "tags": list(getattr(builder, 'selected_tags', []) or []) or [t for t in [getattr(builder, 'primary_tag', None), getattr(builder, 'secondary_tag', None), getattr(builder, 'tertiary_tag', None)] if t],
                                "bracket_level": getattr(builder, 'bracket_level', None),
                                "csv": csv_path,
                                "txt": txt_path,
                                "random_seed": int(new_seed),
                                "random_theme": theme,
                                "random_primary_theme": primary_theme,
                                "random_secondary_theme": secondary_theme,
                                "random_tertiary_theme": tertiary_theme,
                                "random_resolved_themes": list(resolved_theme_info.get("resolved_list") or []),
                                "random_combo_fallback": bool(resolved_theme_info.get("combo_fallback")),
                                "random_synergy_fallback": bool(resolved_theme_info.get("synergy_fallback")),
                                "random_fallback_reason": resolved_theme_info.get("fallback_reason"),
                                "random_auto_fill_enabled": bool(auto_fill_enabled),
                                "random_auto_fill_secondary_enabled": bool(auto_fill_secondary_enabled),
                                "random_auto_fill_tertiary_enabled": bool(auto_fill_tertiary_enabled),
                                "random_auto_fill_applied": bool(resolved_theme_info.get("auto_fill_applied")),
                                "random_auto_filled_themes": list(resolved_theme_info.get("auto_filled_themes") or []),
                                "random_constraints": constraints or {},
                                "random_strict_theme_match": bool(strict_theme_match),
                                "locked_commander": True,
                            }
                            try:
                                custom_base = getattr(builder, 'custom_export_base', None)
                            except Exception:
                                custom_base = None
                            if isinstance(custom_base, str) and custom_base.strip():
                                meta["name"] = custom_base.strip()
                            try:
                                with open(sidecar, 'w', encoding='utf-8') as f:
                                    _json_mod.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
            except Exception:
                compliance = None
            if "auto_fill_applied" not in resolved_theme_info:
                resolved_theme_info["auto_fill_applied"] = bool(resolved_theme_info.get("auto_filled_themes"))
            class _Res:  # minimal object with expected attrs
                pass
            res = _Res()
            res.seed = int(new_seed)
            res.commander = locked_commander
            res.theme = theme
            res.primary_theme = primary_theme
            res.secondary_theme = secondary_theme
            res.tertiary_theme = tertiary_theme
            res.strict_theme_match = bool(strict_theme_match)
            if not resolved_theme_info.get("resolved_list"):
                resolved_theme_info["resolved_list"] = [t for t in [primary_theme, secondary_theme, tertiary_theme] if t]
            res.resolved_themes = list(resolved_theme_info.get("resolved_list") or [])
            res.display_themes = list(resolved_theme_info.get("display_list") or res.resolved_themes)
            res.auto_fill_enabled = bool(auto_fill_enabled)
            res.auto_fill_secondary_enabled = bool(auto_fill_secondary_enabled)
            res.auto_fill_tertiary_enabled = bool(auto_fill_tertiary_enabled)
            res.auto_fill_applied = bool(resolved_theme_info.get("auto_fill_applied"))
            res.auto_filled_themes = list(resolved_theme_info.get("auto_filled_themes") or [])
            res.combo_fallback = bool(resolved_theme_info.get("combo_fallback"))
            res.synergy_fallback = bool(resolved_theme_info.get("synergy_fallback"))
            res.fallback_reason = resolved_theme_info.get("fallback_reason")
            res.theme_fallback = bool(res.combo_fallback) or bool(res.synergy_fallback)
            res.constraints = constraints or {}
            res.diagnostics = {"locked_commander": True, "attempts": 1, "elapsed_ms": elapsed_ms}
            res.summary = summary
            res.decklist = decklist
            res.csv_path = csv_path
            res.txt_path = txt_path
            res.compliance = compliance
        else:
            res = build_random_full_deck(
                theme=theme,
                constraints=constraints,
                seed=new_seed,
                attempts=int(_attempts),
                timeout_s=float(_timeout_s),
                primary_theme=primary_theme,
                secondary_theme=secondary_theme,
                tertiary_theme=tertiary_theme,
                auto_fill_missing=bool(auto_fill_enabled),
                auto_fill_secondary=auto_fill_secondary_enabled,
                auto_fill_tertiary=auto_fill_tertiary_enabled,
                strict_theme_match=strict_theme_match,
            )
            resolved_theme_info = {
                "primary": getattr(res, "primary_theme", None),
                "secondary": getattr(res, "secondary_theme", None),
                "tertiary": getattr(res, "tertiary_theme", None),
                "resolved_list": list(getattr(res, "resolved_themes", []) or []),
                "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                "fallback_reason": getattr(res, "fallback_reason", None),
                "display_list": list(getattr(res, "display_themes", []) or []),
                "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                "strict_theme_match": bool(getattr(res, "strict_theme_match", strict_theme_match)),
            }
            resolved_theme_info["auto_fill_enabled"] = bool(auto_fill_enabled)
            resolved_theme_info["auto_fill_secondary_enabled"] = bool(auto_fill_secondary_enabled)
            resolved_theme_info["auto_fill_tertiary_enabled"] = bool(auto_fill_tertiary_enabled)
    except Exception as ex:
        # Map constraints-impossible to a friendly fragment; other errors to a plain note
        msg = ""
        if ex.__class__.__name__ == "RandomConstraintsImpossibleError":
            _record_random_event("reroll", constraints_impossible=True)
            _log_random_event("reroll", request, "constraints_impossible")
            msg = "<div class=\"error\">Constraints impossible — try loosening filters.</div>"
        else:
            _record_random_event("reroll", error=True)
            _log_random_event("reroll", request, "error")
            msg = "<div class=\"error\">Reroll failed. Please try again.</div>"
        return HTMLResponse(msg, status_code=200)

    strict_theme_result = bool(getattr(res, "strict_theme_match", strict_theme_match))
    resolved_theme_info["strict_theme_match"] = strict_theme_result

    usage_mode = _classify_usage_mode(mode, [primary_theme, secondary_theme, tertiary_theme, legacy_theme], locked_commander)
    combo_flag = bool(getattr(res, "combo_fallback", False))
    synergy_flag = bool(getattr(res, "synergy_fallback", False))
    _record_random_usage_event(usage_mode, combo_flag, synergy_flag, getattr(res, "fallback_reason", None))

    # Persist to session
    request_timestamp = time.time()
    sid, had_cookie = _update_random_session(
        request,
        seed=int(res.seed),
        theme=res.theme,
        constraints=res.constraints or {},
        requested_themes=requested_themes,
        resolved_themes=resolved_theme_info,
        auto_fill_enabled=auto_fill_enabled,
        auto_fill_secondary_enabled=auto_fill_secondary_enabled,
        auto_fill_tertiary_enabled=auto_fill_tertiary_enabled,
        strict_theme_match=strict_theme_result,
        auto_fill_applied=bool(getattr(res, "auto_fill_applied", False)),
        auto_filled_themes=getattr(res, "auto_filled_themes", None),
        display_themes=getattr(res, "display_themes", None),
        request_timestamp=request_timestamp,
    )

    # Render minimal fragment via Jinja2
    try:
        elapsed_ms = int(round((request_timestamp - t0) * 1000))
        _log_random_event(
            "reroll",
            request,
            "success",
            seed=int(res.seed),
            theme=(res.theme or None),
            attempts=int(RANDOM_MAX_ATTEMPTS),
            timeout_ms=int(RANDOM_TIMEOUT_MS),
            elapsed_ms=elapsed_ms,
            fallback=bool(getattr(res, "combo_fallback", False) or getattr(res, "synergy_fallback", False) or getattr(res, "theme_fallback", False)),
        )
        # Build permalink token for fragment copy button
        try:
            import base64 as _b64
            _raw = _json.dumps({
                "commander": res.commander,
                "random": {
                    "seed": int(res.seed),
                    "theme": res.theme,
                    "constraints": res.constraints or {},
                    "primary_theme": getattr(res, "primary_theme", None),
                    "secondary_theme": getattr(res, "secondary_theme", None),
                    "tertiary_theme": getattr(res, "tertiary_theme", None),
                    "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
                    "display_themes": list(getattr(res, "display_themes", []) or []),
                    "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                    "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                    "fallback_reason": getattr(res, "fallback_reason", None),
                    "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                    "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                    "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                    "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                    "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                    "strict_theme_match": strict_theme_result,
                    "requested_themes": requested_themes,
                },
            }, separators=(",", ":"))
            _token = _b64.urlsafe_b64encode(_raw.encode("utf-8")).decode("ascii").rstrip("=")
            _permalink = f"/build/from?state={_token}"
        except Exception:
            _permalink = None
        resp = templates.TemplateResponse(
            "partials/random_result.html",  # type: ignore
            {
                "request": request,
                "seed": int(res.seed),
                "commander": res.commander,
                "decklist": res.decklist or [],
                "theme": res.theme,
                "primary_theme": getattr(res, "primary_theme", None),
                "secondary_theme": getattr(res, "secondary_theme", None),
                "tertiary_theme": getattr(res, "tertiary_theme", None),
                "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
                "display_themes": list(getattr(res, "display_themes", []) or []),
                "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                "fallback_reason": getattr(res, "fallback_reason", None),
                "requested_themes": requested_themes,
                "resolved_theme_info": resolved_theme_info,
                "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                "constraints": res.constraints or {},
                "diagnostics": res.diagnostics or {},
                "permalink": _permalink,
                "show_diagnostics": SHOW_DIAGNOSTICS,
                "fallback": bool(getattr(res, "theme_fallback", False) or getattr(res, "combo_fallback", False) or getattr(res, "synergy_fallback", False)),
                "summary": getattr(res, "summary", None),
                "strict_theme_match": strict_theme_result,
            },
        )
        if rl:
            remaining, reset_epoch = rl
            try:
                resp.headers["X-RateLimit-Remaining"] = str(remaining)
                resp.headers["X-RateLimit-Reset"] = str(reset_epoch)
            except Exception:
                pass
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60*60*8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp
    except Exception as ex:
        logging.getLogger("web").error(f"hx_random_reroll template error: {ex}")
        # Fallback to JSON to avoid total failure
        resp = JSONResponse(
            {
                "seed": int(res.seed),
                "commander": res.commander,
                "decklist": res.decklist or [],
                "theme": res.theme,
                "primary_theme": getattr(res, "primary_theme", None),
                "secondary_theme": getattr(res, "secondary_theme", None),
                "tertiary_theme": getattr(res, "tertiary_theme", None),
                "resolved_themes": list(getattr(res, "resolved_themes", []) or []),
                "display_themes": list(getattr(res, "display_themes", []) or []),
                "combo_fallback": bool(getattr(res, "combo_fallback", False)),
                "synergy_fallback": bool(getattr(res, "synergy_fallback", False)),
                "fallback_reason": getattr(res, "fallback_reason", None),
                "requested_themes": requested_themes,
                "resolved_theme_info": resolved_theme_info,
                "auto_fill_enabled": bool(getattr(res, "auto_fill_enabled", False)),
                "auto_fill_secondary_enabled": bool(getattr(res, "auto_fill_secondary_enabled", False)),
                "auto_fill_tertiary_enabled": bool(getattr(res, "auto_fill_tertiary_enabled", False)),
                "auto_fill_applied": bool(getattr(res, "auto_fill_applied", False)),
                "auto_filled_themes": list(getattr(res, "auto_filled_themes", []) or []),
                "constraints": res.constraints or {},
                "diagnostics": res.diagnostics or {},
                "strict_theme_match": strict_theme_result,
            }
        )
        if not had_cookie:
            try:
                resp.set_cookie("sid", sid, max_age=60*60*8, httponly=True, samesite="lax")
            except Exception:
                pass
        return resp

@app.get("/api/random/seeds")
async def api_random_recent_seeds(request: Request):
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    sid, sess, _ = _ensure_session(request)
    rb = sess.get("random_build") or {}
    seeds = list(rb.get("recent_seeds") or [])
    last = rb.get("seed")
    favorites = list(rb.get("favorite_seeds") or [])
    rid = getattr(request.state, "request_id", None)
    return {"seeds": seeds, "last": last, "favorites": favorites, "request_id": rid}

@app.post("/api/random/seed_favorite")
async def api_random_seed_favorite(request: Request):
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    sid, sess, _ = _ensure_session(request)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    seed = body.get("seed")
    try:
        seed_int = int(seed)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid seed")
    favs = _toggle_seed_favorite(sid, seed_int)
    rid = getattr(request.state, "request_id", None)
    return {"ok": True, "favorites": favs, "request_id": rid}

@app.get("/status/random_metrics_ndjson")
async def status_random_metrics_ndjson():
    if not RANDOM_TELEMETRY:
        return PlainTextResponse("{}\n", media_type="application/x-ndjson")
    lines = []
    try:
        for kind, buckets in _RANDOM_METRICS.items():
            rec = {"kind": kind}
            rec.update(buckets)
            lines.append(_json.dumps(rec, separators=(",", ":")))
    except Exception:
        lines.append(_json.dumps({"error": True}))
    return PlainTextResponse("\n".join(lines) + "\n", media_type="application/x-ndjson")

# Logs tail endpoint (read-only)
@app.get("/status/logs")
async def status_logs(
    tail: int = Query(200, ge=1, le=500),
    q: str | None = None,
    level: str | None = Query(None, description="Optional level filter: error|warning|info|debug"),
):
    try:
        if not SHOW_LOGS:
            # Hide when logs are disabled
            return JSONResponse({"error": True, "status": 403, "detail": "Logs disabled"}, status_code=403)
        log_path = Path('logs/deck_builder.log')
        if not log_path.exists():
            return JSONResponse({"lines": [], "count": 0})
        from collections import deque
        with log_path.open('r', encoding='utf-8', errors='ignore') as lf:
            lines = list(deque(lf, maxlen=tail))
        if q:
            ql = q.lower()
            lines = [ln for ln in lines if ql in ln.lower()]
        # Optional level filter (simple substring match)
        if level:
            lv = level.strip().lower()
            # accept warn as alias for warning
            if lv == "warn":
                lv = "warning"
            if lv in {"error", "warning", "info", "debug"}:
                lines = [ln for ln in lines if lv in ln.lower()]
        return JSONResponse({"lines": lines, "count": len(lines)})
    except Exception:
        return JSONResponse({"lines": [], "count": 0})

# Lightweight setup/tagging status endpoint
@app.get("/status/setup")
async def setup_status():
    try:
        p = Path("csv_files/.setup_status.json")
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = _json.load(f)
            # Attach a small log tail if available
            try:
                log_path = Path('logs/deck_builder.log')
                if log_path.exists():
                    tail_lines = []
                    with log_path.open('r', encoding='utf-8', errors='ignore') as lf:
                        # Read last ~100 lines efficiently
                        from collections import deque
                        tail = deque(lf, maxlen=100)
                        tail_lines = list(tail)
                    # Reduce noise: keep lines related to setup/tagging; fallback to last 30 if too few remain
                    try:
                        lowered = [ln for ln in tail_lines]
                        keywords = ["setup", "tag", "color", "csv", "initial setup", "tagging", "load_dataframe"]
                        filtered = [ln for ln in lowered if any(kw in ln.lower() for kw in keywords)]
                        if len(filtered) >= 5:
                            use_lines = filtered[-60:]
                        else:
                            use_lines = tail_lines[-30:]
                        data["log_tail"] = "".join(use_lines).strip()
                    except Exception:
                        data["log_tail"] = "".join(tail_lines).strip()
            except Exception:
                pass
            return JSONResponse(data)
        return JSONResponse({"running": False, "phase": "idle"})
    except Exception:
        return JSONResponse({"running": False, "phase": "error"})

# Routers
from .routes import build as build_routes  # noqa: E402
from .routes import configs as config_routes  # noqa: E402
from .routes import decks as decks_routes  # noqa: E402
from .routes import setup as setup_routes  # noqa: E402
from .routes import owned as owned_routes  # noqa: E402
from .routes import themes as themes_routes  # noqa: E402
from .routes import commanders as commanders_routes  # noqa: E402
app.include_router(build_routes.router)
app.include_router(config_routes.router)
app.include_router(decks_routes.router)
app.include_router(setup_routes.router)
app.include_router(owned_routes.router)
app.include_router(themes_routes.router)
app.include_router(commanders_routes.router)

# Warm validation cache early to reduce first-call latency in tests and dev
try:
    build_routes.warm_validation_name_cache()
except Exception:
    pass

## (Additional startup warmers consolidated into lifespan handler)

# --- Exception handling ---
def _wants_html(request: Request) -> bool:
    try:
        accept = request.headers.get('accept', '')
        is_htmx = request.headers.get('hx-request') == 'true'
        return ("text/html" in accept) and not is_htmx
    except Exception:
        return False


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").warning(
        f"HTTPException [rid={rid}] {exc.status_code} {request.method} {request.url.path}: {exc.detail}"
    )
    if _wants_html(request):
        # Friendly HTML page
        template = "errors/404.html" if exc.status_code == 404 else "errors/4xx.html"
        try:
            headers = {"X-Request-ID": rid}
            try:
                if getattr(exc, "headers", None):
                    headers.update(exc.headers)  # type: ignore[arg-type]
            except Exception:
                pass
            return templates.TemplateResponse(template, {"request": request, "status": exc.status_code, "detail": exc.detail, "request_id": rid}, status_code=exc.status_code, headers=headers)
        except Exception:
            # Fallback plain text
            headers = {"X-Request-ID": rid}
            try:
                if getattr(exc, "headers", None):
                    headers.update(exc.headers)  # type: ignore[arg-type]
            except Exception:
                pass
            return PlainTextResponse(f"Error {exc.status_code}: {exc.detail}\nRequest-ID: {rid}", status_code=exc.status_code, headers=headers)
    # JSON structure for HTMX/API
    headers = {"X-Request-ID": rid}
    try:
        if getattr(exc, "headers", None):
            headers.update(exc.headers)  # type: ignore[arg-type]
    except Exception:
        pass
    return JSONResponse(status_code=exc.status_code, content={
        "error": True,
        "status": exc.status_code,
        "detail": exc.detail,
        "request_id": rid,
        "path": str(request.url.path),
    }, headers=headers)


# Also handle Starlette's HTTPException (e.g., 404 route not found)
@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").warning(
        f"HTTPException* [rid={rid}] {exc.status_code} {request.method} {request.url.path}: {exc.detail}"
    )
    if _wants_html(request):
        template = "errors/404.html" if exc.status_code == 404 else "errors/4xx.html"
        try:
            headers = {"X-Request-ID": rid}
            try:
                if getattr(exc, "headers", None):
                    headers.update(exc.headers)  # type: ignore[arg-type]
            except Exception:
                pass
            return templates.TemplateResponse(template, {"request": request, "status": exc.status_code, "detail": exc.detail, "request_id": rid}, status_code=exc.status_code, headers=headers)
        except Exception:
            headers = {"X-Request-ID": rid}
            try:
                if getattr(exc, "headers", None):
                    headers.update(exc.headers)  # type: ignore[arg-type]
            except Exception:
                pass
            return PlainTextResponse(f"Error {exc.status_code}: {exc.detail}\nRequest-ID: {rid}", status_code=exc.status_code, headers=headers)
    headers = {"X-Request-ID": rid}
    try:
        if getattr(exc, "headers", None):
            headers.update(exc.headers)  # type: ignore[arg-type]
    except Exception:
        pass
    return JSONResponse(status_code=exc.status_code, content={
        "error": True,
        "status": exc.status_code,
        "detail": exc.detail,
        "request_id": rid,
        "path": str(request.url.path),
    }, headers=headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    logging.getLogger("web").error(
        f"Unhandled exception [rid={rid}] {request.method} {request.url.path}", exc_info=True
    )
    if _wants_html(request):
        try:
            return templates.TemplateResponse("errors/500.html", {"request": request, "request_id": rid}, status_code=500, headers={"X-Request-ID": rid})
        except Exception:
            return PlainTextResponse(f"Internal Server Error\nRequest-ID: {rid}", status_code=500, headers={"X-Request-ID": rid})
    return JSONResponse(status_code=500, content={
        "error": True,
        "status": 500,
        "detail": "Internal Server Error",
        "request_id": rid,
        "path": str(request.url.path),
    }, headers={"X-Request-ID": rid})

# --- Random Modes page (minimal shell) ---
@app.get("/random", response_class=HTMLResponse)
async def random_modes_page(request: Request) -> HTMLResponse:
    if not random_modes_enabled():
        raise HTTPException(status_code=404, detail="Random Modes disabled")
    cached_requested, _cached_resolved = _get_random_session_themes(request)
    strict_pref = bool(_sanitize_bool(cached_requested.get("strict_theme_match"), default=False))
    return templates.TemplateResponse(
        "random/index.html",
        {
            "request": request,
            "random_ui": bool(RANDOM_UI),
            "strict_theme_match": strict_pref,
        },
    )

# Lightweight file download endpoint for exports
@app.get("/files")
async def get_file(path: str):
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return PlainTextResponse("File not found", status_code=404)
        # Only allow returning files within the workspace directory for safety
        # (best-effort: require relative to current working directory)
        try:
            cwd = Path.cwd().resolve()
            if cwd not in p.resolve().parents and p.resolve() != cwd:
                # Still allow if under deck_files or config
                allowed = any(seg in ("deck_files", "config", "logs") for seg in p.parts)
                if not allowed:
                    return PlainTextResponse("Access denied", status_code=403)
        except Exception:
            pass
        return FileResponse(path)
    except Exception:
        return PlainTextResponse("Error serving file", status_code=500)

# Serve /favicon.ico from static (prefer .ico, fallback to .png)
@app.get("/favicon.ico")
async def favicon():
    try:
        ico = _STATIC_DIR / "favicon.ico"
        png = _STATIC_DIR / "favicon.png"
        target = ico if ico.exists() else (png if png.exists() else None)
        if target is None:
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(str(target))
    except Exception:
        return PlainTextResponse("Error", status_code=500)


# Simple Logs page (optional, controlled by SHOW_LOGS)
@app.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    tail: int = Query(200, ge=1, le=500),
    q: str | None = None,
    level: str | None = Query(None),
) -> Response:
    if not SHOW_LOGS:
        # Respect feature flag
        raise HTTPException(status_code=404, detail="Not Found")
    # Reuse status_logs logic
    data = await status_logs(tail=tail, q=q, level=level)  # type: ignore[arg-type]
    lines: list[str]
    if isinstance(data, JSONResponse):
        payload = data.body
        try:
            parsed = _json.loads(payload)
            lines = parsed.get("lines", [])
        except Exception:
            lines = []
    else:
        lines = []
    return templates.TemplateResponse(
        "diagnostics/logs.html",
        {"request": request, "lines": lines, "tail": tail, "q": q or "", "level": (level or "all")},
    )


# Error trigger route for demoing HTMX/global error handling (feature-flagged)
@app.get("/diagnostics/trigger-error")
async def trigger_error(kind: str = Query("http")):
    if kind == "http":
        raise HTTPException(status_code=418, detail="Teapot: example error for testing")
    raise RuntimeError("Example unhandled error for testing")


@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_home(request: Request) -> HTMLResponse:
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse("diagnostics/index.html", {"request": request})


@app.get("/diagnostics/perf", response_class=HTMLResponse)
async def diagnostics_perf(request: Request) -> HTMLResponse:
    """Synthetic scroll performance page (diagnostics only)."""
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse("diagnostics/perf.html", {"request": request})

# --- Diagnostics: combos & synergies ---
@app.post("/diagnostics/combos")
async def diagnostics_combos(request: Request) -> JSONResponse:
    if not SHOW_DIAGNOSTICS:
        raise HTTPException(status_code=404, detail="Diagnostics disabled")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    names = payload.get("names") or []
    combos_path = payload.get("combos_path") or "config/card_lists/combos.json"
    synergies_path = payload.get("synergies_path") or "config/card_lists/synergies.json"

    det = _detect_all(names, combos_path=combos_path, synergies_path=synergies_path)
    combos = det.get("combos", [])
    synergies = det.get("synergies", [])
    versions = det.get("versions", {"combos": None, "synergies": None})

    def as_dict_combo(c):
        return {
            "a": c.a,
            "b": c.b,
            "cheap_early": bool(c.cheap_early),
            "setup_dependent": bool(c.setup_dependent),
            "tags": list(c.tags or []),
        }

    def as_dict_syn(s):
        return {"a": s.a, "b": s.b, "tags": list(s.tags or [])}

    return JSONResponse(
        {
            "counts": {"combos": len(combos), "synergies": len(synergies)},
            "versions": {"combos": versions.get("combos"), "synergies": versions.get("synergies")},
            "combos": [as_dict_combo(c) for c in combos],
            "synergies": [as_dict_syn(s) for s in synergies],
        }
    )
