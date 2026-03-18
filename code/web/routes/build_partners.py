"""
Partner mechanics routes and utilities for deck building.

Handles partner commanders, backgrounds, Doctor/Companion pairings,
and partner preview/validation functionality.
"""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote_plus
from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse

from ..app import (
    ENABLE_PARTNER_MECHANICS,
)
from ..services.telemetry import log_partner_suggestion_selected
from ..services.partner_suggestions import get_partner_suggestions
from ..services.commander_catalog_loader import (
    load_commander_catalog,
    find_commander_record,
    CommanderRecord,
    normalized_restricted_labels,
    shared_restricted_partner_label,
)
from deck_builder.background_loader import load_background_cards
from deck_builder.partner_selection import apply_partner_inputs
from deck_builder.builder import DeckBuilder
from exceptions import CommanderPartnerError
from code.logging_util import get_logger


LOGGER = get_logger(__name__)
router = APIRouter()


_PARTNER_MODE_LABELS = {
    "partner": "Partner",
    "partner_restricted": "Partner (Restricted)",
    "partner_with": "Partner With",
    "background": "Choose a Background",
    "doctor_companion": "Doctor & Companion",
}


_WUBRG_ORDER = ["W", "U", "B", "R", "G"]
_COLOR_NAME_MAP = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}


def _color_code(identity: Iterable[str]) -> str:
    """Convert color identity to standard WUBRG-ordered code."""
    colors = [str(c).strip().upper() for c in identity if str(c).strip()]
    if not colors:
        return "C"
    ordered: list[str] = [c for c in _WUBRG_ORDER if c in colors]
    for color in colors:
        if color not in ordered:
            ordered.append(color)
    return "".join(ordered) or "C"


def _format_color_label(identity: Iterable[str]) -> str:
    """Format color identity as human-readable label with code."""
    code = _color_code(identity)
    if code == "C":
        return "Colorless (C)"
    names = [_COLOR_NAME_MAP.get(ch, ch) for ch in code]
    return " / ".join(names) + f" ({code})"


def _partner_mode_label(mode: str | None) -> str:
    """Convert partner mode to display label."""
    if not mode:
        return "Partner Mechanics"
    return _PARTNER_MODE_LABELS.get(mode, mode.title())


def _scryfall_image_url(card_name: str, version: str = "normal") -> str | None:
    """Generate Scryfall image URL for card."""
    name = str(card_name or "").strip()
    if not name:
        return None
    return f"https://api.scryfall.com/cards/named?fuzzy={quote_plus(name)}&format=image&version={version}"


def _scryfall_page_url(card_name: str) -> str | None:
    """Generate Scryfall search URL for card."""
    name = str(card_name or "").strip()
    if not name:
        return None
    return f"https://scryfall.com/search?q={quote_plus(name)}"


def _secondary_role_label(mode: str | None, secondary_name: str | None) -> str | None:
    """Determine the role label for the secondary commander based on pairing mode."""
    if not mode:
        return None
    mode_lower = mode.lower()
    if mode_lower == "background":
        return "Background"
    if mode_lower == "partner_with":
        return "Partner With"
    if mode_lower == "doctor_companion":
        record = find_commander_record(secondary_name or "") if secondary_name else None
        if record and getattr(record, "is_doctor", False):
            return "Doctor"
        if record and getattr(record, "is_doctors_companion", False):
            return "Doctor's Companion"
        return "Doctor pairing"
    return "Partner commander"


def _combined_to_payload(combined: Any) -> dict[str, Any]:
    """Convert CombinedCommander object to JSON-serializable payload."""
    color_identity = tuple(getattr(combined, "color_identity", ()) or ())
    warnings = list(getattr(combined, "warnings", []) or [])
    mode_obj = getattr(combined, "partner_mode", None)
    mode_value = getattr(mode_obj, "value", None) if mode_obj is not None else None
    secondary = getattr(combined, "secondary_name", None)
    secondary_image = _scryfall_image_url(secondary)
    secondary_url = _scryfall_page_url(secondary)
    secondary_role = _secondary_role_label(mode_value, secondary)
    return {
        "primary_name": getattr(combined, "primary_name", None),
        "secondary_name": secondary,
        "partner_mode": mode_value,
        "partner_mode_label": _partner_mode_label(mode_value),
        "color_identity": list(color_identity),
        "color_code": _color_code(color_identity),
        "color_label": _format_color_label(color_identity),
        "theme_tags": list(getattr(combined, "theme_tags", []) or []),
        "warnings": warnings,
        "secondary_image_url": secondary_image,
        "secondary_scryfall_url": secondary_url,
        "secondary_role_label": secondary_role,
    }


def _build_partner_options(primary: CommanderRecord | None) -> tuple[list[dict[str, Any]], str | None]:
    """
    Build list of valid partner options for a given primary commander.

    Returns:
        Tuple of (partner_options_list, variant_type) where variant is
        "partner", "doctor_companion", or None
    """
    if not ENABLE_PARTNER_MECHANICS:
        return [], None
    try:
        catalog = load_commander_catalog()
    except Exception:
        return [], None

    if primary is None:
        return [], None

    primary_name = primary.display_name.casefold()
    primary_partner_targets = {target.casefold() for target in (primary.partner_with or ())}
    primary_is_partner = bool(primary.is_partner or primary_partner_targets)
    primary_restricted_labels = normalized_restricted_labels(primary)
    primary_is_doctor = bool(primary.is_doctor)
    primary_is_companion = bool(primary.is_doctors_companion)

    variant: str | None = None
    if primary_is_doctor or primary_is_companion:
        variant = "doctor_companion"
    elif primary_is_partner:
        variant = "partner"

    options: list[dict[str, Any]] = []
    if variant is None:
        return [], None

    for record in catalog.entries:
        if record.display_name.casefold() == primary_name:
            continue

        pairing_mode: str | None = None
        role_label: str | None = None
        restriction_label: str | None = None
        record_name_cf = record.display_name.casefold()
        is_direct_pair = bool(primary_partner_targets and record_name_cf in primary_partner_targets)

        if variant == "doctor_companion":
            if is_direct_pair:
                pairing_mode = "partner_with"
                role_label = "Partner With"
            elif primary_is_doctor and record.is_doctors_companion:
                pairing_mode = "doctor_companion"
                role_label = "Doctor's Companion"
            elif primary_is_companion and record.is_doctor:
                pairing_mode = "doctor_companion"
                role_label = "Doctor"
        else:
            if not record.is_partner or record.is_background:
                continue
            if primary_partner_targets:
                if not is_direct_pair:
                    continue
                pairing_mode = "partner_with"
                role_label = "Partner With"
            elif primary_restricted_labels:
                restriction = shared_restricted_partner_label(primary, record)
                if not restriction:
                    continue
                pairing_mode = "partner_restricted"
                restriction_label = restriction
            else:
                if record.partner_with:
                    continue
                if not getattr(record, "has_plain_partner", False):
                    continue
                if record.is_doctors_companion:
                    continue
                pairing_mode = "partner"

        if not pairing_mode:
            continue

        options.append(
            {
                "name": record.display_name,
                "color_code": _color_code(record.color_identity),
                "color_label": _format_color_label(record.color_identity),
                "partner_with": list(record.partner_with or ()),
                "pairing_mode": pairing_mode,
                "role_label": role_label,
                "restriction_label": restriction_label,
                "mode_label": _partner_mode_label(pairing_mode),
                "image_url": _scryfall_image_url(record.display_name),
                "scryfall_url": _scryfall_page_url(record.display_name),
            }
        )

    options.sort(key=lambda item: item["name"].casefold())
    return options, variant


def _build_background_options() -> list[dict[str, Any]]:
    """Build list of available background cards for Choose a Background commanders."""
    if not ENABLE_PARTNER_MECHANICS:
        return []

    options: list[dict[str, Any]] = []
    try:
        catalog = load_background_cards()
    except FileNotFoundError as exc:
        LOGGER.warning("background_cards_missing fallback_to_commander_catalog", extra={"error": str(exc)})
        catalog = None
    except Exception as exc:  # pragma: no cover - unexpected loader failure
        LOGGER.warning("background_cards_failed fallback_to_commander_catalog", exc_info=exc)
        catalog = None

    if catalog and getattr(catalog, "entries", None):
        seen: set[str] = set()
        for card in catalog.entries:
            name_key = card.display_name.casefold()
            if name_key in seen:
                continue
            seen.add(name_key)
            options.append(
                {
                    "name": card.display_name,
                    "color_code": _color_code(card.color_identity),
                    "color_label": _format_color_label(card.color_identity),
                    "image_url": _scryfall_image_url(card.display_name),
                    "scryfall_url": _scryfall_page_url(card.display_name),
                    "role_label": "Background",
                }
            )
        if options:
            options.sort(key=lambda item: item["name"].casefold())
            return options

    fallback_options = _background_options_from_commander_catalog()
    if fallback_options:
        return fallback_options
    return options


def _background_options_from_commander_catalog() -> list[dict[str, Any]]:
    """Fallback: load backgrounds from commander catalog when background_cards.json is unavailable."""
    try:
        catalog = load_commander_catalog()
    except Exception as exc:  # pragma: no cover - catalog load issues handled elsewhere
        LOGGER.warning("commander_catalog_background_fallback_failed", exc_info=exc)
        return []

    seen: set[str] = set()
    options: list[dict[str, Any]] = []
    for record in getattr(catalog, "entries", ()):
        if not getattr(record, "is_background", False):
            continue
        name = getattr(record, "display_name", None)
        if not name:
            continue
        key = str(name).casefold()
        if key in seen:
            continue
        seen.add(key)
        color_identity = getattr(record, "color_identity", tuple())
        options.append(
            {
                "name": name,
                "color_code": _color_code(color_identity),
                "color_label": _format_color_label(color_identity),
                "image_url": _scryfall_image_url(name),
                "scryfall_url": _scryfall_page_url(name),
                "role_label": "Background",
            }
        )

    options.sort(key=lambda item: item["name"].casefold())
    return options


def _partner_ui_context(
    commander_name: str,
    *,
    partner_enabled: bool,
    secondary_selection: str | None,
    background_selection: str | None,
    combined_preview: dict[str, Any] | None,
    warnings: Iterable[str] | None,
    partner_error: str | None,
    auto_note: str | None,
    auto_assigned: bool | None = None,
    auto_prefill_allowed: bool = True,
) -> dict[str, Any]:
    """
    Build complete partner UI context for rendering partner selection components.

    This includes partner options, background options, preview payload,
    suggestions, warnings, and all necessary state for the partner UI.
    """
    record = find_commander_record(commander_name)
    partner_options, partner_variant = _build_partner_options(record)
    supports_backgrounds = bool(record.supports_backgrounds) if record else False
    background_options = _build_background_options() if supports_backgrounds else []

    selected_secondary = (secondary_selection or "").strip()
    selected_background = (background_selection or "").strip()
    warnings_list = list(warnings or [])
    preview_payload: dict[str, Any] | None = combined_preview if isinstance(combined_preview, dict) else None
    preview_error: str | None = None

    auto_prefill_applied = False
    auto_default_name: str | None = None
    auto_note_value = auto_note

    # Auto-prefill Partner With targets
    if (
        ENABLE_PARTNER_MECHANICS
        and partner_variant == "partner"
        and record
        and record.partner_with
        and not selected_secondary
        and not selected_background
        and auto_prefill_allowed
    ):
        target_names = [name.strip() for name in record.partner_with if str(name).strip()]
        for target in target_names:
            for option in partner_options:
                if option["name"].casefold() == target.casefold():
                    selected_secondary = option["name"]
                    auto_default_name = option["name"]
                    auto_prefill_applied = True
                    if not auto_note_value:
                        auto_note_value = f"Automatically paired with {option['name']} (Partner With)."
                    break
            if auto_prefill_applied:
                break

    partner_active = bool((selected_secondary or selected_background) and ENABLE_PARTNER_MECHANICS)
    partner_capable = bool(ENABLE_PARTNER_MECHANICS and (partner_options or background_options))

    # Dynamic labels based on variant
    placeholder = "Select a partner"
    select_label = "Partner commander"
    role_hint: str | None = None
    if partner_variant == "doctor_companion" and record:
        has_partner_with_option = any(option.get("pairing_mode") == "partner_with" for option in partner_options)
        if record.is_doctor:
            if has_partner_with_option:
                placeholder = "Select a companion or Partner With match"
                select_label = "Companion or Partner"
                role_hint = "Choose a Doctor's Companion or Partner With match for this Doctor."
            else:
                placeholder = "Select a companion"
                select_label = "Companion"
                role_hint = "Choose a Doctor's Companion to pair with this Doctor."
        elif record.is_doctors_companion:
            if has_partner_with_option:
                placeholder = "Select a Doctor or Partner With match"
                select_label = "Doctor or Partner"
                role_hint = "Choose a Doctor or Partner With pairing for this companion."
            else:
                placeholder = "Select a Doctor"
                select_label = "Doctor partner"
                role_hint = "Choose a Doctor to accompany this companion."

    # Partner suggestions
    suggestions_enabled = bool(ENABLE_PARTNER_MECHANICS)
    suggestions_visible: list[dict[str, Any]] = []
    suggestions_hidden: list[dict[str, Any]] = []
    suggestions_total = 0
    suggestions_metadata: dict[str, Any] = {}
    suggestions_error: str | None = None
    suggestions_loaded = False

    if suggestions_enabled and record:
        try:
            suggestion_result = get_partner_suggestions(record.display_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("partner suggestions failed", exc_info=exc)
            suggestion_result = None
        if suggestion_result is None:
            suggestions_error = "Partner suggestions dataset is unavailable."
        else:
            suggestions_loaded = True
            partner_names = [opt.get("name") for opt in (partner_options or []) if opt.get("name")]
            background_names = [opt.get("name") for opt in (background_options or []) if opt.get("name")]
            try:
                visible, hidden = suggestion_result.flatten(partner_names, background_names, visible_limit=3)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("partner suggestions flatten failed", exc_info=exc)
                visible = []
                hidden = []
            suggestions_visible = visible
            suggestions_hidden = hidden
            suggestions_total = suggestion_result.total
            if isinstance(suggestion_result.metadata, dict):
                suggestions_metadata = dict(suggestion_result.metadata)

    context = {
        "partner_feature_available": ENABLE_PARTNER_MECHANICS,
        "partner_capable": partner_capable,
        "partner_enabled": partner_active,
        "selected_secondary_commander": selected_secondary,
        "selected_background": selected_background if supports_backgrounds else "",
        "partner_options": partner_options if partner_options else [],
        "background_options": background_options if background_options else [],
        "primary_partner_with": list(record.partner_with) if record else [],
        "primary_supports_backgrounds": supports_backgrounds,
        "primary_is_partner": bool(record.is_partner) if record else False,
        "primary_commander_display": record.display_name if record else commander_name,
        "partner_preview": preview_payload,
        "partner_warnings": warnings_list,
        "partner_error": partner_error,
        "partner_auto_note": auto_note_value,
        "partner_auto_assigned": bool(auto_prefill_applied or auto_assigned),
        "partner_auto_default": auto_default_name,
        "partner_select_variant": partner_variant,
        "partner_select_label": select_label,
        "partner_select_placeholder": placeholder,
        "partner_role_hint": role_hint,
        "partner_suggestions_enabled": suggestions_enabled,
        "partner_suggestions": suggestions_visible,
        "partner_suggestions_hidden": suggestions_hidden,
        "partner_suggestions_total": suggestions_total,
        "partner_suggestions_metadata": suggestions_metadata,
        "partner_suggestions_loaded": suggestions_loaded,
        "partner_suggestions_error": suggestions_error,
        "partner_suggestions_available": bool(suggestions_visible or suggestions_hidden),
        "partner_suggestions_has_hidden": bool(suggestions_hidden),
        "partner_suggestions_endpoint": "/api/partner/suggestions",
    }
    context["has_partner_options"] = bool(partner_options)
    context["has_background_options"] = bool(background_options)
    context["partner_hidden_value"] = "1" if partner_capable else "0"
    context["partner_auto_opt_out"] = not bool(auto_prefill_allowed)
    context["partner_prefill_available"] = bool(partner_variant == "partner" and partner_options)

    # Generate preview if not provided
    if preview_payload is None and ENABLE_PARTNER_MECHANICS and (selected_secondary or selected_background):
        try:
            builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
            combined_obj = apply_partner_inputs(
                builder,
                primary_name=commander_name,
                secondary_name=selected_secondary or None,
                background_name=selected_background or None,
                feature_enabled=True,
            )
        except CommanderPartnerError as exc:
            preview_error = str(exc) or "Invalid partner selection."
        except Exception as exc:
            preview_error = f"Partner preview failed: {exc}"
        else:
            if combined_obj is not None:
                preview_payload = _combined_to_payload(combined_obj)
                if combined_obj.warnings:
                    for warn in combined_obj.warnings:
                        if warn not in warnings_list:
                            warnings_list.append(warn)
    if preview_payload:
        context["partner_preview"] = preview_payload
        preview_tags = preview_payload.get("theme_tags")
        if preview_tags:
            context["partner_theme_tags"] = list(preview_tags)
    if preview_error and not partner_error:
        context["partner_error"] = preview_error
        partner_error = preview_error
    context["partner_warnings"] = warnings_list
    return context


def _resolve_partner_selection(
    commander_name: str,
    *,
    feature_enabled: bool,
    partner_enabled: bool,
    secondary_candidate: str | None,
    background_candidate: str | None,
    auto_opt_out: bool = False,
    selection_source: str | None = None,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    list[str],
    str | None,
    str | None,
    str | None,
    str | None,
    bool,
]:
    """
    Resolve and validate partner selection, applying auto-pairing when appropriate.

    Returns:
        Tuple of (error, preview_payload, warnings, auto_note, resolved_secondary,
        resolved_background, partner_mode, auto_assigned_flag)
    """
    if not (feature_enabled and ENABLE_PARTNER_MECHANICS):
        return None, None, [], None, None, None, None, False

    secondary = (secondary_candidate or "").strip()
    background = (background_candidate or "").strip()
    auto_note: str | None = None
    auto_assigned = False
    selection_source_clean = (selection_source or "").strip().lower() or None

    record = find_commander_record(commander_name)
    partner_options, partner_variant = _build_partner_options(record)
    supports_backgrounds = bool(record and record.supports_backgrounds)
    background_options = _build_background_options() if supports_backgrounds else []

    if not partner_enabled and not secondary and not background:
        return None, None, [], None, None, None, None, False

    if not supports_backgrounds:
        background = ""
    if not partner_options:
        secondary = ""

    if secondary and background:
        return "Provide either a secondary commander or a background, not both.", None, [], auto_note, secondary, background, None, False

    option_lookup = {opt["name"].casefold(): opt for opt in partner_options}
    if secondary:
        key = secondary.casefold()
        if key not in option_lookup:
            return "Selected partner is not valid for this commander.", None, [], auto_note, secondary, background or None, None, False

    if background:
        normalized_backgrounds = {opt["name"].casefold() for opt in background_options}
        if background.casefold() not in normalized_backgrounds:
            return "Selected background is not available.", None, [], auto_note, secondary or None, background, None, False

    # Auto-assign Partner With targets
    if not secondary and not background and not auto_opt_out and partner_variant == "partner" and record and record.partner_with:
        target_names = [name.strip() for name in record.partner_with if str(name).strip()]
        for target in target_names:
            opt = option_lookup.get(target.casefold())
            if opt:
                secondary = opt["name"]
                auto_note = f"Automatically paired with {secondary} (Partner With)."
                auto_assigned = True
                break

    if not secondary and not background:
        return None, None, [], auto_note, None, None, None, auto_assigned

    builder = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    try:
        combined = apply_partner_inputs(
            builder,
            primary_name=commander_name,
            secondary_name=secondary or None,
            background_name=background or None,
            feature_enabled=True,
            selection_source=selection_source_clean,
        )
    except CommanderPartnerError as exc:
        message = str(exc) or "Invalid partner selection."
        return message, None, [], auto_note, secondary or None, background or None, None, auto_assigned
    except Exception as exc:
        return f"Partner selection failed: {exc}", None, [], auto_note, secondary or None, background or None, None, auto_assigned

    if combined is None:
        return "Unable to resolve partner selection.", None, [], auto_note, secondary or None, background or None, None, auto_assigned

    payload = _combined_to_payload(combined)
    warnings = payload.get("warnings", []) or []
    mode = payload.get("partner_mode")
    if mode == "background":
        resolved_background = payload.get("secondary_name")
        return None, payload, warnings, auto_note, None, resolved_background, mode, auto_assigned
    return None, payload, warnings, auto_note, payload.get("secondary_name"), None, mode, auto_assigned


@router.post("/partner/preview", response_class=JSONResponse)
async def build_partner_preview(
    request: Request,
    commander: str = Form(...),
    partner_enabled: str | None = Form(None),
    secondary_commander: str | None = Form(None),
    background: str | None = Form(None),
    partner_auto_opt_out: str | None = Form(None),
    scope: str | None = Form(None),
    selection_source: str | None = Form(None),
) -> JSONResponse:
    """
    Preview a partner pairing and return combined commander details.

    This endpoint validates partner selections and returns:
    - Combined color identity and theme tags
    - Partner preview payload with images and metadata
    - Warnings about legality or capability mismatches
    - Auto-pairing information for Partner With targets

    Args:
        request: FastAPI request
        commander: Primary commander name
        partner_enabled: Whether partner mechanics are enabled ("1"/"true"/etc.)
        secondary_commander: Secondary partner commander name
        background: Background card name (for Choose a Background commanders)
        partner_auto_opt_out: Opt-out of auto-pairing for Partner With
        scope: Request scope identifier
        selection_source: Source of selection (e.g., "suggestion", "manual")

    Returns:
        JSONResponse with partner preview data and validation results
    """
    partner_feature_enabled = ENABLE_PARTNER_MECHANICS
    raw_partner_enabled = (partner_enabled or "").strip().lower()
    partner_flag = partner_feature_enabled and raw_partner_enabled in {"1", "true", "on", "yes"}
    auto_opt_out_flag = (partner_auto_opt_out or "").strip().lower() in {"1", "true", "on", "yes"}
    selection_source_value = (selection_source or "").strip().lower() or None

    try:
        (
            partner_error,
            combined_payload,
            partner_warnings,
            partner_auto_note,
            resolved_secondary,
            resolved_background,
            partner_mode,
            partner_auto_assigned_flag,
        ) = _resolve_partner_selection(
            commander,
            feature_enabled=partner_feature_enabled,
            partner_enabled=partner_flag,
            secondary_candidate=secondary_commander,
            background_candidate=background,
            auto_opt_out=auto_opt_out_flag,
            selection_source=selection_source_value,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            {
                "ok": False,
                "error": f"Partner preview failed: {exc}",
                "scope": scope or "",
            }
        )

    partner_ctx = _partner_ui_context(
        commander,
        partner_enabled=partner_flag,
        secondary_selection=resolved_secondary or secondary_commander,
        background_selection=resolved_background or background,
        combined_preview=combined_payload,
        warnings=partner_warnings,
        partner_error=partner_error,
        auto_note=partner_auto_note,
        auto_assigned=partner_auto_assigned_flag,
        auto_prefill_allowed=not auto_opt_out_flag,
    )

    preview_payload = partner_ctx.get("partner_preview")
    theme_tags = partner_ctx.get("partner_theme_tags") or []
    warnings_list = partner_ctx.get("partner_warnings") or partner_warnings or []

    response = {
        "ok": True,
        "scope": scope or "",
        "preview": preview_payload,
        "theme_tags": theme_tags,
        "warnings": warnings_list,
        "auto_note": partner_auto_note,
        "resolved_secondary": resolved_secondary,
        "resolved_background": resolved_background,
        "partner_mode": partner_mode,
        "auto_assigned": bool(partner_auto_assigned_flag),
    }
    if partner_error:
        response["error"] = partner_error
    try:
        log_partner_suggestion_selected(
            request,
            commander=commander,
            scope=scope,
            partner_enabled=partner_flag,
            auto_opt_out=auto_opt_out_flag,
            auto_assigned=bool(partner_auto_assigned_flag),
            selection_source=selection_source_value,
            secondary_candidate=secondary_commander,
            background_candidate=background,
            resolved_secondary=resolved_secondary,
            resolved_background=resolved_background,
            partner_mode=partner_mode,
            has_preview=bool(preview_payload),
            warnings=warnings_list,
            error=response.get("error"),
        )
    except Exception:  # pragma: no cover - telemetry should not break responses
        pass
    return JSONResponse(response)
