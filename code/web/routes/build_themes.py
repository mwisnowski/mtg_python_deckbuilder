"""
Custom theme management routes for deck building.

Handles user-defined custom themes including adding, removing, choosing
suggestions, and switching between permissive/strict matching modes.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from ..app import (
    ENABLE_CUSTOM_THEMES,
    USER_THEME_LIMIT,
    DEFAULT_THEME_MATCH_MODE,
    _sanitize_theme,
    templates,
)
from ..services.tasks import get_session, new_sid
from ..services import custom_theme_manager as theme_mgr
from ..services.theme_catalog_loader import load_index, slugify


router = APIRouter()


def _prepare_step2_theme_data(tags: list[str], recommended: list[str]) -> tuple[list[str], list[str], dict[str, int]]:
    """Load pool size data and sort themes for display.

    Returns:
        Tuple of (sorted_tags, sorted_recommended, pool_size_dict)
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        theme_index = load_index()
        pool_size_by_slug = theme_index.pool_size_by_slug
    except Exception as e:
        logger.warning(f"Failed to load theme index for pool sizes: {e}")
        pool_size_by_slug = {}

    def sort_by_pool_size(theme_list: list[str]) -> list[str]:
        return sorted(
            theme_list,
            key=lambda t: (-pool_size_by_slug.get(slugify(t), 0), t.lower())
        )

    return sort_by_pool_size(tags), sort_by_pool_size(recommended), pool_size_by_slug


def _section_themes_by_pool_size(themes: list[str], pool_size: dict[str, int]) -> list[dict[str, Any]]:
    """Group themes into sections by pool size.

    Thresholds: Vast ≥1000, Large 500-999, Moderate 200-499, Small 50-199, Tiny <50
    """
    sections = [
        {"label": "Vast",     "min": 1000, "max": 9999999, "themes": []},
        {"label": "Large",    "min": 500,  "max": 999,     "themes": []},
        {"label": "Moderate", "min": 200,  "max": 499,     "themes": []},
        {"label": "Small",    "min": 50,   "max": 199,     "themes": []},
        {"label": "Tiny",     "min": 0,    "max": 49,      "themes": []},
    ]
    for theme in themes:
        theme_pool = pool_size.get(slugify(theme), 0)
        for section in sections:
            if section["min"] <= theme_pool <= section["max"]:
                section["themes"].append(theme)
                break
    return [s for s in sections if s["themes"]]


_INVALID_THEME_MESSAGE = (
    "Theme names can only include letters, numbers, spaces, hyphens, apostrophes, and underscores."
)


def _custom_theme_context(
    request: Request,
    sess: dict,
    *,
    message: str | None = None,
    level: str = "info",
) -> dict[str, Any]:
    """
    Assemble the Additional Themes section context for the modal.

    Args:
        request: FastAPI request object
        sess: Session dictionary
        message: Optional status message to display
        level: Message level ("info", "success", "warning", "error")

    Returns:
        Context dictionary for rendering the additional themes template
    """
    if not ENABLE_CUSTOM_THEMES:
        return {
            "request": request,
            "theme_state": None,
            "theme_message": message,
            "theme_message_level": level,
            "theme_limit": USER_THEME_LIMIT,
            "enable_custom_themes": False,
        }
    theme_mgr.set_limit(sess, USER_THEME_LIMIT)
    state = theme_mgr.get_view_state(sess, default_mode=DEFAULT_THEME_MATCH_MODE)
    return {
        "request": request,
        "theme_state": state,
        "theme_message": message,
        "theme_message_level": level,
        "theme_limit": USER_THEME_LIMIT,
        "enable_custom_themes": ENABLE_CUSTOM_THEMES,
    }


@router.post("/themes/add", response_class=HTMLResponse)
async def build_theme_add(request: Request, theme: str = Form("")) -> HTMLResponse:
    """
    Add a custom theme to the user's theme list.

    Validates theme name format and enforces theme count limits.

    Args:
        request: FastAPI request object
        theme: Theme name to add (will be trimmed and sanitized)

    Returns:
        HTMLResponse with updated themes list and status message
    """
    if not ENABLE_CUSTOM_THEMES:
        return HTMLResponse("", status_code=204)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    trimmed = theme.strip()
    sanitized = _sanitize_theme(trimmed) if trimmed else ""
    if trimmed and not sanitized:
        ctx = _custom_theme_context(request, sess, message=_INVALID_THEME_MESSAGE, level="error")
    else:
        value = sanitized if sanitized is not None else trimmed
        _, message, level = theme_mgr.add_theme(
            sess,
            value,
            commander_tags=list(sess.get("tags", [])),
            mode=sess.get("theme_match_mode", DEFAULT_THEME_MATCH_MODE),
            limit=USER_THEME_LIMIT,
        )
        ctx = _custom_theme_context(request, sess, message=message, level=level)
    resp = templates.TemplateResponse("build/_new_deck_additional_themes.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/themes/remove", response_class=HTMLResponse)
async def build_theme_remove(request: Request, theme: str = Form("")) -> HTMLResponse:
    """
    Remove a custom theme from the user's theme list.

    Args:
        request: FastAPI request object
        theme: Theme name to remove

    Returns:
        HTMLResponse with updated themes list and status message
    """
    if not ENABLE_CUSTOM_THEMES:
        return HTMLResponse("", status_code=204)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    value = _sanitize_theme(theme) or theme
    _, message, level = theme_mgr.remove_theme(
        sess,
        value,
        commander_tags=list(sess.get("tags", [])),
        mode=sess.get("theme_match_mode", DEFAULT_THEME_MATCH_MODE),
    )
    ctx = _custom_theme_context(request, sess, message=message, level=level)
    resp = templates.TemplateResponse("build/_new_deck_additional_themes.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/themes/choose", response_class=HTMLResponse)
async def build_theme_choose(
    request: Request,
    original: str = Form(""),
    choice: str = Form(""),
) -> HTMLResponse:
    """
    Replace an invalid theme with a suggested alternative.

    When a user's custom theme doesn't perfectly match commander tags,
    the system suggests alternatives. This route accepts the user's
    choice from those suggestions.

    Args:
        request: FastAPI request object
        original: The original (invalid) theme name
        choice: The selected suggestion to use instead

    Returns:
        HTMLResponse with updated themes list and status message
    """
    if not ENABLE_CUSTOM_THEMES:
        return HTMLResponse("", status_code=204)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    selection = _sanitize_theme(choice) or choice
    _, message, level = theme_mgr.choose_suggestion(
        sess,
        original,
        selection,
        commander_tags=list(sess.get("tags", [])),
        mode=sess.get("theme_match_mode", DEFAULT_THEME_MATCH_MODE),
    )
    ctx = _custom_theme_context(request, sess, message=message, level=level)
    resp = templates.TemplateResponse("build/_new_deck_additional_themes.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/themes/mode", response_class=HTMLResponse)
async def build_theme_mode(request: Request, mode: str = Form("permissive")) -> HTMLResponse:
    """
    Switch theme matching mode between permissive and strict.

    - Permissive: Suggests alternatives for invalid themes
    - Strict: Rejects invalid themes outright

    Args:
        request: FastAPI request object
        mode: Either "permissive" or "strict"

    Returns:
        HTMLResponse with updated themes list and status message
    """
    if not ENABLE_CUSTOM_THEMES:
        return HTMLResponse("", status_code=204)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    _, message, level = theme_mgr.set_mode(
        sess,
        mode,
        commander_tags=list(sess.get("tags", [])),
    )
    ctx = _custom_theme_context(request, sess, message=message, level=level)
    resp = templates.TemplateResponse("build/_new_deck_additional_themes.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
