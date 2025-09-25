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
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from typing import Any, Optional, Dict
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
SHOW_VIRTUALIZE = _as_bool(os.getenv("WEB_VIRTUALIZE"), False)
ENABLE_THEMES = _as_bool(os.getenv("ENABLE_THEMES"), False)
ENABLE_PWA = _as_bool(os.getenv("ENABLE_PWA"), False)
ENABLE_PRESETS = _as_bool(os.getenv("ENABLE_PRESETS"), False)
ALLOW_MUST_HAVES = _as_bool(os.getenv("ALLOW_MUST_HAVES"), False)
RANDOM_MODES = _as_bool(os.getenv("RANDOM_MODES"), False)  # initial snapshot (legacy)
RANDOM_UI = _as_bool(os.getenv("RANDOM_UI"), False)
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


def _update_random_session(request: Request, *, seed: int, theme: Any, constraints: Any) -> tuple[str, bool]:
    """Update session with latest random build seed/theme/constraints and maintain a bounded recent list."""
    sid, sess, had_cookie = _ensure_session(request)
    rb = dict(sess.get("random_build") or {})
    rb["seed"] = int(seed)
    if theme is not None:
        rb["theme"] = theme
    if constraints is not None:
        rb["constraints"] = constraints
    recent = list(rb.get("recent_seeds") or [])
    # Append and keep last 10 unique (most-recent-first)
    recent.append(int(seed))
    # Dedupe while preserving order from the right (most recent)
    seen = set()
    dedup_rev: list[int] = []
    for s in reversed(recent):
        if s in seen:
            continue
        seen.add(s)
        dedup_rev.append(s)
    dedup = list(reversed(dedup_rev))
    rb["recent_seeds"] = dedup[-10:]
    set_session_value(sid, "random_build", rb)
    return sid, had_cookie

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
        return JSONResponse({"ok": True, "metrics": out})
    except Exception:
        return JSONResponse({"ok": False, "metrics": {}}, status_code=500)

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
        body = {}
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
        theme = body.get("theme")
        theme = _sanitize_theme(theme)
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
        res = build_random_deck(
            theme=theme,
            constraints=constraints,
            seed=seed,
            attempts=int(attempts),
            timeout_s=float(timeout_s),
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
        theme = body.get("theme")
        theme = _sanitize_theme(theme)
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
        )

        # Create a permalink token reusing the existing format from /build/permalink
        payload = {
            "commander": res.commander,
            # Note: tags/bracket/ideals omitted; random modes focuses on seed replay
            "random": {
                "seed": int(res.seed),
                "theme": res.theme,
                "constraints": res.constraints or {},
            },
        }
        try:
            import base64
            raw = _json.dumps(payload, separators=(",", ":"))
            token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
            permalink = f"/build/from?state={token}"
        except Exception:
            permalink = None

        # Persist to session (so recent seeds includes initial seed)
        sid, had_cookie = _update_random_session(request, seed=int(res.seed), theme=res.theme, constraints=res.constraints or {})
        rid = getattr(request.state, "request_id", None)
        _record_random_event("full_build", success=True, fallback=bool(getattr(res, "theme_fallback", False)))
        elapsed_ms = int(round((time.time() - t0) * 1000))
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
            "constraints": res.constraints or {},
            "permalink": permalink,
            "attempts": int(attempts),
            "timeout_ms": int(timeout_ms),
            "diagnostics": res.diagnostics or {},
            "fallback": bool(getattr(res, "theme_fallback", False)),
            "original_theme": getattr(res, "original_theme", None),
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
    try:
        t0 = time.time()
        rl = rate_limit_check(request, "random")
        body = {}
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
        theme = body.get("theme")
        theme = _sanitize_theme(theme)
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
        )

        payload = {
            "commander": res.commander,
            "random": {
                "seed": int(res.seed),
                "theme": res.theme,
                "constraints": res.constraints or {},
            },
        }
        try:
            import base64
            raw = _json.dumps(payload, separators=(",", ":"))
            token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
            permalink = f"/build/from?state={token}"
        except Exception:
            permalink = None

        # Persist in session and set sid cookie if we just created it
        sid, had_cookie = _update_random_session(request, seed=int(res.seed), theme=res.theme, constraints=res.constraints or {})
        rid = getattr(request.state, "request_id", None)
        _record_random_event("reroll", success=True, fallback=bool(getattr(res, "theme_fallback", False)))
        elapsed_ms = int(round((time.time() - t0) * 1000))
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
            "constraints": res.constraints or {},
            "permalink": permalink,
            "attempts": int(attempts),
            "timeout_ms": int(timeout_ms),
            "diagnostics": res.diagnostics or {},
            "summary": getattr(res, "summary", None),
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
    last_seed = body.get("seed")
    mode = body.get("mode")  # "surprise" (default) vs "reroll_same_commander"
    locked_commander = body.get("commander") if mode == "reroll_same_commander" else None
    theme = body.get("theme")
    theme = _sanitize_theme(theme)
    constraints = body.get("constraints")
    attempts_override = body.get("attempts")
    timeout_ms_override = body.get("timeout_ms")
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
        if locked_commander:
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
                import json as _json
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
                                compliance = _json.load(_cf)
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
                                "random_constraints": constraints or {},
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
                                    _json.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
            except Exception:
                compliance = None
            class _Res:  # minimal object with expected attrs
                pass
            res = _Res()
            res.seed = int(new_seed)
            res.commander = locked_commander
            res.theme = theme
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
            )
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

    # Persist to session
    sid, had_cookie = _update_random_session(request, seed=int(res.seed), theme=res.theme, constraints=res.constraints or {})

    # Render minimal fragment via Jinja2
    try:
        elapsed_ms = int(round((time.time() - t0) * 1000))
        _log_random_event(
            "reroll",
            request,
            "success",
            seed=int(res.seed),
            theme=(res.theme or None),
            attempts=int(RANDOM_MAX_ATTEMPTS),
            timeout_ms=int(RANDOM_TIMEOUT_MS),
            elapsed_ms=elapsed_ms,
        )
        # Build permalink token for fragment copy button
        try:
            import base64 as _b64
            _raw = _json.dumps({
                "commander": res.commander,
                "random": {"seed": int(res.seed), "theme": res.theme, "constraints": res.constraints or {}},
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
                "constraints": res.constraints or {},
                "diagnostics": res.diagnostics or {},
                "permalink": _permalink,
                "show_diagnostics": SHOW_DIAGNOSTICS,
                "fallback": bool(getattr(res, "theme_fallback", False)),
                "summary": getattr(res, "summary", None),
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
                "constraints": res.constraints or {},
                "diagnostics": res.diagnostics or {},
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
app.include_router(build_routes.router)
app.include_router(config_routes.router)
app.include_router(decks_routes.router)
app.include_router(setup_routes.router)
app.include_router(owned_routes.router)
app.include_router(themes_routes.router)

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
    return templates.TemplateResponse("random/index.html", {"request": request, "random_ui": bool(RANDOM_UI)})

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
