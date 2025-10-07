from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Any, Iterable
from ..app import (
    ALLOW_MUST_HAVES,
    ENABLE_CUSTOM_THEMES,
    USER_THEME_LIMIT,
    DEFAULT_THEME_MATCH_MODE,
    _sanitize_theme,
    ENABLE_PARTNER_MECHANICS,
    ENABLE_PARTNER_SUGGESTIONS,
)
from ..services.build_utils import (
    step5_ctx_from_result,
    step5_error_ctx,
    step5_empty_ctx,
    start_ctx_from_session,
    owned_set as owned_set_helper,
    builder_present_names,
    builder_display_map,
)
from ..app import templates
from deck_builder import builder_constants as bc
from ..services import orchestrator as orch
from ..services.orchestrator import is_setup_ready as _is_setup_ready, is_setup_stale as _is_setup_stale  # type: ignore
from ..services.build_utils import owned_names as owned_names_helper
from ..services.tasks import get_session, new_sid
from html import escape as _esc
from deck_builder.builder import DeckBuilder
from deck_builder import builder_utils as bu
from ..services.combo_utils import detect_all as _detect_all
from ..services import custom_theme_manager as theme_mgr
from path_util import csv_dir as _csv_dir
from ..services.alts_utils import get_cached as _alts_get_cached, set_cached as _alts_set_cached
from ..services.telemetry import (
    log_commander_create_deck,
    log_partner_suggestion_selected,
)
from ..services.partner_suggestions import get_partner_suggestions
from urllib.parse import urlparse, quote_plus
from commander_exclusions import lookup_commander_detail
from ..services.commander_catalog_loader import (
    load_commander_catalog,
    find_commander_record,
    CommanderRecord,
    normalized_restricted_labels,
    shared_restricted_partner_label,
)
from deck_builder.background_loader import load_background_cards
from deck_builder.partner_selection import apply_partner_inputs
from exceptions import CommanderPartnerError
from code.logging_util import get_logger

LOGGER = get_logger(__name__)

# Cache for available card names used by validation endpoints
_AVAILABLE_CARDS_CACHE: set[str] | None = None
_AVAILABLE_CARDS_NORM_SET: set[str] | None = None
_AVAILABLE_CARDS_NORM_MAP: dict[str, str] | None = None

def _available_cards() -> set[str]:
    """Fast load of available card names using the csv module (no pandas).

    Reads only once and caches results in memory.
    """
    global _AVAILABLE_CARDS_CACHE
    if _AVAILABLE_CARDS_CACHE is not None:
        return _AVAILABLE_CARDS_CACHE
    try:
        import csv
        path = f"{_csv_dir()}/cards.csv"
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            name_col = None
            for col in ['name', 'Name', 'card_name', 'CardName']:
                if col in fields:
                    name_col = col
                    break
            if name_col is None and fields:
                # Heuristic: pick first field containing 'name'
                for col in fields:
                    if 'name' in col.lower():
                        name_col = col
                        break
            if name_col is None:
                raise ValueError(f"No name-like column found in {path}: {fields}")
            names: set[str] = set()
            for row in reader:
                try:
                    v = row.get(name_col)
                    if v:
                        names.add(str(v))
                except Exception:
                    continue
            _AVAILABLE_CARDS_CACHE = names
            return _AVAILABLE_CARDS_CACHE
    except Exception:
        _AVAILABLE_CARDS_CACHE = set()
        return _AVAILABLE_CARDS_CACHE

def _available_cards_normalized() -> tuple[set[str], dict[str, str]]:
    """Return cached normalized card names and mapping to originals."""
    global _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP
    if _AVAILABLE_CARDS_NORM_SET is not None and _AVAILABLE_CARDS_NORM_MAP is not None:
        return _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP
    # Build from available cards set
    names = _available_cards()
    try:
        from deck_builder.include_exclude_utils import normalize_punctuation
    except Exception:
        # Fallback: identity normalization
        def normalize_punctuation(x: str) -> str:  # type: ignore
            return str(x).strip().casefold()
    norm_map: dict[str, str] = {}
    for name in names:
        try:
            n = normalize_punctuation(name)
            if n not in norm_map:
                norm_map[n] = name
        except Exception:
            continue
    _AVAILABLE_CARDS_NORM_MAP = norm_map
    _AVAILABLE_CARDS_NORM_SET = set(norm_map.keys())
    return _AVAILABLE_CARDS_NORM_SET, _AVAILABLE_CARDS_NORM_MAP

def warm_validation_name_cache() -> None:
    """Pre-populate the available-cards caches to avoid first-call latency."""
    try:
        _ = _available_cards()
        _ = _available_cards_normalized()
    except Exception:
        # Best-effort warmup; proceed silently on failure
        pass


_COLOR_NAME_MAP = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}
_WUBRG_ORDER = ("W", "U", "B", "R", "G", "C")
_PARTNER_MODE_LABELS = {
    "partner": "Partner",
    "partner_restricted": "Partner (Restricted)",
    "partner_with": "Partner With",
    "background": "Choose a Background",
    "doctor_companion": "Doctor & Companion",
}


def _color_code(identity: Iterable[str]) -> str:
    colors = [str(c).strip().upper() for c in identity if str(c).strip()]
    if not colors:
        return "C"
    ordered: list[str] = [c for c in _WUBRG_ORDER if c in colors]
    for color in colors:
        if color not in ordered:
            ordered.append(color)
    return "".join(ordered) or "C"


def _format_color_label(identity: Iterable[str]) -> str:
    code = _color_code(identity)
    if code == "C":
        return "Colorless (C)"
    names = [_COLOR_NAME_MAP.get(ch, ch) for ch in code]
    return " / ".join(names) + f" ({code})"


def _partner_mode_label(mode: str | None) -> str:
    if not mode:
        return "Partner Mechanics"
    return _PARTNER_MODE_LABELS.get(mode, mode.title())


def _scryfall_image_url(card_name: str, version: str = "normal") -> str | None:
    name = str(card_name or "").strip()
    if not name:
        return None
    return f"https://api.scryfall.com/cards/named?fuzzy={quote_plus(name)}&format=image&version={version}"


def _scryfall_page_url(card_name: str) -> str | None:
    name = str(card_name or "").strip()
    if not name:
        return None
    return f"https://scryfall.com/search?q={quote_plus(name)}"


def _secondary_role_label(mode: str | None, secondary_name: str | None) -> str | None:
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
    try:
        catalog = load_commander_catalog()
    except Exception as exc:  # pragma: no cover - catalog load issues handled elsewhere
        LOGGER.warning("commander_catalog_background_fallback_failed", exc_info=exc)
        return []

    seen: set[str] = set()
    options: list[dict[str, Any]] = []
    for record in getattr(catalog, "entries", ()):  # type: ignore[attr-defined]
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

    suggestions_enabled = bool(ENABLE_PARTNER_MECHANICS and ENABLE_PARTNER_SUGGESTIONS)
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


router = APIRouter(prefix="/build")

# Alternatives cache moved to services/alts_utils


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


def _custom_theme_context(
    request: Request,
    sess: dict,
    *,
    message: str | None = None,
    level: str = "info",
) -> dict[str, Any]:
    """Assemble the Additional Themes section context for the modal."""

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


_INVALID_THEME_MESSAGE = (
    "Theme names can only include letters, numbers, spaces, hyphens, apostrophes, and underscores."
)


def _rebuild_ctx_with_multicopy(sess: dict) -> None:
    """Rebuild the staged context so Multi-Copy runs first, avoiding overfill.

    This ensures the added cards are accounted for before lands and later phases,
    which keeps totals near targets and shows the multi-copy additions ahead of basics.
    """
    try:
        if not sess or not sess.get("commander"):
            return
        # Build fresh ctx with the same options, threading multi_copy explicitly
        opts = orch.bracket_options()
        default_bracket = (opts[0]["level"] if opts else 1)
        bracket_val = sess.get("bracket")
        try:
            safe_bracket = int(bracket_val) if bracket_val is not None else default_bracket
        except Exception:
            safe_bracket = int(default_bracket)
        ideals_val = sess.get("ideals") or orch.ideal_defaults()
        use_owned = bool(sess.get("use_owned_only"))
        prefer = bool(sess.get("prefer_owned"))
        owned_names = owned_names_helper() if (use_owned or prefer) else None
        locks = list(sess.get("locks", []))
        sess["build_ctx"] = orch.start_build_ctx(
            commander=sess.get("commander"),
            tags=sess.get("tags", []),
            bracket=safe_bracket,
            ideals=ideals_val,
            tag_mode=sess.get("tag_mode", "AND"),
            use_owned_only=use_owned,
            prefer_owned=prefer,
            owned_names=owned_names,
            locks=locks,
            custom_export_base=sess.get("custom_export_base"),
            multi_copy=sess.get("multi_copy"),
            prefer_combos=bool(sess.get("prefer_combos")),
            combo_target_count=int(sess.get("combo_target_count", 2)),
            combo_balance=str(sess.get("combo_balance", "mix")),
            swap_mdfc_basics=bool(sess.get("swap_mdfc_basics")),
        )
    except Exception:
        # If rebuild fails (e.g., commander not found in test), fall back to injecting
        # a minimal Multi-Copy stage on the existing builder so the UI can render additions.
        try:
            ctx = sess.get("build_ctx")
            if not isinstance(ctx, dict):
                return
            b = ctx.get("builder")
            if b is None:
                return
            # Thread selection onto the builder; runner will be resilient without full DFs
            try:
                setattr(b, "_web_multi_copy", sess.get("multi_copy") or None)
            except Exception:
                pass
            # Ensure minimal structures exist
            try:
                if not isinstance(getattr(b, "card_library", None), dict):
                    b.card_library = {}
            except Exception:
                pass
            try:
                if not isinstance(getattr(b, "ideal_counts", None), dict):
                    b.ideal_counts = {}
            except Exception:
                pass
            # Inject a single Multi-Copy stage
            ctx["stages"] = [{"key": "multi_copy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}]
            ctx["idx"] = 0
            ctx["last_visible_idx"] = 0
        except Exception:
            # Leave existing context untouched on unexpected failure
            pass


@router.get("/", response_class=HTMLResponse)
async def build_index(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Seed commander from query string when arriving from commander browser
    q_commander = None
    try:
        q_commander = request.query_params.get("commander")
        if q_commander:
            # Persist a human-friendly commander name into session for the wizard
            sess["commander"] = str(q_commander)
    except Exception:
        pass
    return_url = None
    try:
        raw_return = request.query_params.get("return")
        if raw_return:
            parsed = urlparse(raw_return)
            if not parsed.scheme and not parsed.netloc and parsed.path:
                safe_path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
                safe_return = safe_path
                if parsed.query:
                    safe_return += f"?{parsed.query}"
                if parsed.fragment:
                    safe_return += f"#{parsed.fragment}"
                return_url = safe_return
    except Exception:
        return_url = None
    if q_commander:
        try:
            log_commander_create_deck(
                request,
                commander=str(q_commander),
                return_url=return_url,
            )
        except Exception:
            pass
    # Determine last step (fallback heuristics if not set)
    last_step = sess.get("last_step")
    if not last_step:
        if sess.get("build_ctx"):
            last_step = 5
        elif sess.get("ideals"):
            last_step = 4
        elif sess.get("bracket"):
            last_step = 3
        elif sess.get("commander"):
            last_step = 2
        else:
            last_step = 1
    resp = templates.TemplateResponse(
        request,
        "build/index.html",
        {
            "sid": sid,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "name": sess.get("custom_export_base"),
            "last_step": last_step,
            "return_url": return_url,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


# Support /build without trailing slash
@router.get("", response_class=HTMLResponse)
async def build_index_alias(request: Request) -> HTMLResponse:
    return await build_index(request)


@router.get("/multicopy/check", response_class=HTMLResponse)
async def multicopy_check(request: Request) -> HTMLResponse:
    """If current commander/tags suggest a multi-copy archetype, render a choose-one modal.

    Returns empty content when not applicable to avoid flashing a modal unnecessarily.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = str(sess.get("commander") or "").strip()
    tags = list(sess.get("tags") or [])
    if not commander:
        return HTMLResponse("")
    # Avoid re-prompting repeatedly for the same selection context
    key = commander + "||" + ",".join(sorted([str(t).strip().lower() for t in tags if str(t).strip()]))
    seen = set(sess.get("mc_seen_keys", []) or [])
    if key in seen:
        return HTMLResponse("")
    # Build a light DeckBuilder seeded with commander + tags (no heavy data load required)
    try:
        tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
        df = tmp.load_commander_data()
        row = df[df["name"].astype(str) == commander]
        if row.empty:
            return HTMLResponse("")
        tmp._apply_commander_selection(row.iloc[0])
        tmp.selected_tags = list(tags or [])
        try:
            tmp.primary_tag = tmp.selected_tags[0] if len(tmp.selected_tags) > 0 else None
            tmp.secondary_tag = tmp.selected_tags[1] if len(tmp.selected_tags) > 1 else None
            tmp.tertiary_tag = tmp.selected_tags[2] if len(tmp.selected_tags) > 2 else None
        except Exception:
            pass
        # Establish color identity from the selected commander
        try:
            tmp.determine_color_identity()
        except Exception:
            pass
        # Detect viable archetypes
        results = bu.detect_viable_multi_copy_archetypes(tmp) or []
        if not results:
            # Remember this key to avoid re-checking until tags/commander change
            try:
                seen.add(key)
                sess["mc_seen_keys"] = list(seen)
            except Exception:
                pass
            return HTMLResponse("")
        # Render modal template with top N (cap small for UX)
        items = results[:5]
        ctx = {
            "request": request,
            "items": items,
            "commander": commander,
            "tags": tags,
        }
        return templates.TemplateResponse("build/_multi_copy_modal.html", ctx)
    except Exception:
        return HTMLResponse("")


@router.post("/multicopy/save", response_class=HTMLResponse)
async def multicopy_save(
    request: Request,
    choice_id: str = Form(None),
    count: int = Form(None),
    thrumming: str | None = Form(None),
    skip: str | None = Form(None),
) -> HTMLResponse:
    """Persist user selection (or skip) for multi-copy archetype in session and close modal.

    Returns a tiny confirmation chip via OOB swap (optional) and removes the modal.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = str(sess.get("commander") or "").strip()
    tags = list(sess.get("tags") or [])
    key = commander + "||" + ",".join(sorted([str(t).strip().lower() for t in tags if str(t).strip()]))
    # Update seen set to avoid re-prompt next load
    seen = set(sess.get("mc_seen_keys", []) or [])
    seen.add(key)
    sess["mc_seen_keys"] = list(seen)
    # Handle skip explicitly
    if skip and str(skip).strip() in ("1","true","on","yes"):
        # Clear any prior choice for this run
        try:
            if sess.get("multi_copy"):
                del sess["multi_copy"]
            if sess.get("mc_applied_key"):
                del sess["mc_applied_key"]
        except Exception:
            pass
        # Return nothing (modal will be removed client-side)
        # Also emit an OOB chip indicating skip
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            '<span class="chip" title="Click to dismiss">Dismissed multi-copy suggestions</span>'
            '</div>'
        )
        return HTMLResponse(chip)
    # Persist selection when provided
    payload = None
    try:
        meta = bc.MULTI_COPY_ARCHETYPES.get(str(choice_id), {})
        name = meta.get("name") or str(choice_id)
        printed_cap = meta.get("printed_cap")
        # Coerce count with bounds: default -> rec_window[0], cap by printed_cap when present
        if count is None:
            count = int(meta.get("default_count", 25))
        try:
            count = int(count)
        except Exception:
            count = int(meta.get("default_count", 25))
        if isinstance(printed_cap, int) and printed_cap > 0:
            count = max(1, min(printed_cap, count))
        payload = {
            "id": str(choice_id),
            "name": name,
            "count": int(count),
            "thrumming": True if (thrumming and str(thrumming).strip() in ("1","true","on","yes")) else False,
        }
        sess["multi_copy"] = payload
        # Mark as not yet applied so the next build start/continue can account for it once
        try:
            if sess.get("mc_applied_key"):
                del sess["mc_applied_key"]
        except Exception:
            pass
        # If there's an active build context, rebuild it so Multi-Copy runs first
        if sess.get("build_ctx"):
            _rebuild_ctx_with_multicopy(sess)
    except Exception:
        payload = None
    # Return OOB chip summarizing the selection
    if payload:
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            f'<span class="chip" title="Click to dismiss">Selected multi-copy: '
            f"<strong>{_esc(payload.get('name',''))}</strong> x{int(payload.get('count',0))}"
            f"{' + Thrumming Stone' if payload.get('thrumming') else ''}</span>"
            '</div>'
        )
    else:
        chip = (
            '<div id="last-action" hx-swap-oob="true">'
            '<span class="chip" title="Click to dismiss">Saved</span>'
            '</div>'
        )
    return HTMLResponse(chip)




# Unified "New Deck" modal (steps 1–3 condensed)
@router.get("/new", response_class=HTMLResponse)
async def build_new_modal(request: Request) -> HTMLResponse:
    """Return the New Deck modal content (for an overlay)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    theme_context = _custom_theme_context(request, sess)
    ctx = {
        "request": request,
        "brackets": orch.bracket_options(),
        "labels": orch.ideal_labels(),
        "defaults": orch.ideal_defaults(),
        "allow_must_haves": ALLOW_MUST_HAVES,  # Add feature flag
        "enable_custom_themes": ENABLE_CUSTOM_THEMES,
        "form": {
            "prefer_combos": bool(sess.get("prefer_combos")),
            "combo_count": sess.get("combo_target_count"),
            "combo_balance": sess.get("combo_balance"),
            "enable_multicopy": bool(sess.get("multi_copy")),
            "use_owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
        "tag_slot_html": None,
    }
    for key, value in theme_context.items():
        if key == "request":
            continue
        ctx[key] = value
    resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/new/candidates", response_class=HTMLResponse)
async def build_new_candidates(request: Request, commander: str = Query("")) -> HTMLResponse:
    """Return a small list of commander candidates for the modal live search."""
    q = (commander or "").strip()
    items = orch.commander_candidates(q, limit=8) if q else []
    candidates: list[dict[str, Any]] = []
    for name, score, colors in items:
        detail = lookup_commander_detail(name)
        preferred = name
        warning = None
        if detail:
            eligible_raw = detail.get("eligible_faces")
            eligible = [str(face).strip() for face in eligible_raw or [] if str(face).strip()] if isinstance(eligible_raw, list) else []
            norm_name = str(name).strip().casefold()
            eligible_norms = [face.casefold() for face in eligible]
            if eligible and norm_name not in eligible_norms:
                preferred = eligible[0]
                primary = str(detail.get("primary_face") or detail.get("name") or name).strip()
                if len(eligible) == 1:
                    warning = (
                        f"Use the back face '{preferred}' when building. Front face '{primary}' can't lead a deck."
                    )
                else:
                    faces = ", ".join(f"'{face}'" for face in eligible)
                    warning = (
                        f"This commander only works from specific faces: {faces}."
                    )
        candidates.append(
            {
                "display": name,
                "value": preferred,
                "score": score,
                "colors": colors,
                "warning": warning,
            }
        )
    ctx = {"request": request, "query": q, "candidates": candidates}
    return templates.TemplateResponse("build/_new_deck_candidates.html", ctx)


@router.get("/new/inspect", response_class=HTMLResponse)
async def build_new_inspect(request: Request, name: str = Query(...)) -> HTMLResponse:
    """When a candidate is chosen in the modal, show the commander preview and tag chips (OOB updates)."""
    info = orch.commander_select(name)
    if not info.get("ok"):
        return HTMLResponse(f'<div class="muted">Commander not found: {name}</div>')
    tags = orch.tags_for_commander(info["name"]) or []
    recommended = orch.recommended_tags_for_commander(info["name"]) if tags else []
    recommended_reasons = orch.recommended_tag_reasons_for_commander(info["name"]) if tags else {}
    exclusion_detail = lookup_commander_detail(info["name"])
    # Render tags slot content and OOB commander preview simultaneously
    # Game Changer flag for this commander (affects bracket UI in modal via tags partial consumer)
    is_gc = False
    try:
        is_gc = bool(info["name"] in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    ctx = {
        "request": request,
        "commander": {"name": info["name"], "exclusion": exclusion_detail},
        "tags": tags,
        "recommended": recommended,
        "recommended_reasons": recommended_reasons,
        "gc_commander": is_gc,
        "brackets": orch.bracket_options(),
    }
    ctx.update(
        _partner_ui_context(
            info["name"],
            partner_enabled=False,
            secondary_selection=None,
            background_selection=None,
            combined_preview=None,
            warnings=None,
            partner_error=None,
            auto_note=None,
        )
    )
    partner_tags = ctx.get("partner_theme_tags") or []
    if partner_tags:
        merged_tags: list[str] = []
        seen: set[str] = set()
        for source in (partner_tags, tags):
            for tag in source:
                token = str(tag).strip()
                if not token:
                    continue
                key = token.casefold()
                if key in seen:
                    continue
                seen.add(key)
                merged_tags.append(token)
        ctx["tags"] = merged_tags

        existing_recommended = ctx.get("recommended") or []
        merged_recommended: list[str] = []
        rec_seen: set[str] = set()
        for source in (partner_tags, existing_recommended):
            for tag in source:
                token = str(tag).strip()
                if not token:
                    continue
                key = token.casefold()
                if key in rec_seen:
                    continue
                rec_seen.add(key)
                merged_recommended.append(token)
        ctx["recommended"] = merged_recommended

        reason_map = dict(ctx.get("recommended_reasons") or {})
        for tag in partner_tags:
            if tag not in reason_map:
                reason_map[tag] = "Synergizes with partner pairing"
        ctx["recommended_reasons"] = reason_map
    return templates.TemplateResponse("build/_new_deck_tags.html", ctx)


@router.get("/new/multicopy", response_class=HTMLResponse)
async def build_new_multicopy(
    request: Request,
    commander: str = Query(""),
    primary_tag: str | None = Query(None),
    secondary_tag: str | None = Query(None),
    tertiary_tag: str | None = Query(None),
    tag_mode: str | None = Query("AND"),
) -> HTMLResponse:
    """Return multi-copy suggestions for the New Deck modal based on commander + selected tags.

    This does not mutate the session; it simply renders a form snippet that posts with the main modal.
    """
    name = (commander or "").strip()
    if not name:
        return HTMLResponse("")
    try:
        tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
        df = tmp.load_commander_data()
        row = df[df["name"].astype(str) == name]
        if row.empty:
            return HTMLResponse("")
        tmp._apply_commander_selection(row.iloc[0])
        tags = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
        tmp.selected_tags = list(tags or [])
        try:
            tmp.primary_tag = tmp.selected_tags[0] if len(tmp.selected_tags) > 0 else None
            tmp.secondary_tag = tmp.selected_tags[1] if len(tmp.selected_tags) > 1 else None
            tmp.tertiary_tag = tmp.selected_tags[2] if len(tmp.selected_tags) > 2 else None
        except Exception:
            pass
        try:
            tmp.determine_color_identity()
        except Exception:
            pass
        results = bu.detect_viable_multi_copy_archetypes(tmp) or []
        # For the New Deck modal, only show suggestions where the matched tags intersect
        # the explicitly selected tags (ignore commander-default themes).
        sel_tags = {str(t).strip().lower() for t in (tags or []) if str(t).strip()}
        def _matched_reason_tags(item: dict) -> set[str]:
            out = set()
            try:
                for r in item.get('reasons', []) or []:
                    if not isinstance(r, str):
                        continue
                    rl = r.strip().lower()
                    if rl.startswith('tags:'):
                        body = rl.split('tags:', 1)[1].strip()
                        parts = [p.strip() for p in body.split(',') if p.strip()]
                        out.update(parts)
            except Exception:
                return set()
            return out
        if sel_tags:
            results = [it for it in results if (_matched_reason_tags(it) & sel_tags)]
        else:
            # If no selected tags, do not show any multi-copy suggestions in the modal
            results = []
        if not results:
            return HTMLResponse("")
        items = results[:5]
        ctx = {"request": request, "items": items}
        return templates.TemplateResponse("build/_new_deck_multicopy.html", ctx)
    except Exception:
        return HTMLResponse("")


@router.post("/themes/add", response_class=HTMLResponse)
async def build_theme_add(request: Request, theme: str = Form("")) -> HTMLResponse:
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


@router.post("/new", response_class=HTMLResponse)
async def build_new_submit(
    request: Request,
    name: str = Form("") ,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    partner_enabled: str | None = Form(None),
    secondary_commander: str | None = Form(None),
    background: str | None = Form(None),
    partner_auto_opt_out: str | None = Form(None),
    partner_selection_source: str | None = Form(None),
    bracket: int = Form(...),
    ramp: int = Form(None),
    lands: int = Form(None),
    basic_lands: int = Form(None),
    creatures: int = Form(None),
    removal: int = Form(None),
    wipes: int = Form(None),
    card_advantage: int = Form(None),
    protection: int = Form(None),
    prefer_combos: bool = Form(False),
    combo_count: int | None = Form(None),
    combo_balance: str | None = Form(None),
    enable_multicopy: bool = Form(False),
    use_owned_only: bool = Form(False),
    prefer_owned: bool = Form(False),
    swap_mdfc_basics: bool = Form(False),
    # Integrated Multi-Copy (optional)
    multi_choice_id: str | None = Form(None),
    multi_count: int | None = Form(None),
    multi_thrumming: str | None = Form(None),
    # Must-haves/excludes (optional)
    include_cards: str = Form(""),
    exclude_cards: str = Form(""),
    enforcement_mode: str = Form("warn"),
    allow_illegal: bool = Form(False),
    fuzzy_matching: bool = Form(True),
) -> HTMLResponse:
    """Handle New Deck modal submit and immediately start the build (skip separate review page)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    partner_feature_enabled = ENABLE_PARTNER_MECHANICS
    raw_partner_flag = (partner_enabled or "").strip().lower()
    partner_checkbox = partner_feature_enabled and raw_partner_flag in {"1", "true", "on", "yes"}
    initial_secondary = (secondary_commander or "").strip()
    initial_background = (background or "").strip()
    auto_opt_out_flag = (partner_auto_opt_out or "").strip().lower() in {"1", "true", "on", "yes"}
    partner_form_state: dict[str, Any] = {
        "partner_enabled": bool(partner_checkbox),
        "secondary_commander": initial_secondary,
        "background": initial_background,
        "partner_mode": None,
        "partner_auto_note": None,
        "partner_warnings": [],
        "combined_preview": None,
        "partner_auto_assigned": False,
    }

    def _form_state(commander_value: str) -> dict[str, Any]:
        return {
            "name": name,
            "commander": commander_value,
            "primary_tag": primary_tag or "",
            "secondary_tag": secondary_tag or "",
            "tertiary_tag": tertiary_tag or "",
            "tag_mode": tag_mode or "AND",
            "bracket": bracket,
            "combo_count": combo_count,
            "combo_balance": (combo_balance or "mix"),
            "prefer_combos": bool(prefer_combos),
            "enable_multicopy": bool(enable_multicopy),
            "use_owned_only": bool(use_owned_only),
            "prefer_owned": bool(prefer_owned),
            "swap_mdfc_basics": bool(swap_mdfc_basics),
            "include_cards": include_cards or "",
            "exclude_cards": exclude_cards or "",
            "enforcement_mode": enforcement_mode or "warn",
            "allow_illegal": bool(allow_illegal),
            "fuzzy_matching": bool(fuzzy_matching),
            "partner_enabled": partner_form_state["partner_enabled"],
            "secondary_commander": partner_form_state["secondary_commander"],
            "background": partner_form_state["background"],
        }

    commander_detail = lookup_commander_detail(commander)
    if commander_detail:
        eligible_raw = commander_detail.get("eligible_faces")
        eligible_faces = [str(face).strip() for face in eligible_raw or [] if str(face).strip()] if isinstance(eligible_raw, list) else []
        if eligible_faces:
            norm_input = str(commander).strip().casefold()
            eligible_norms = [face.casefold() for face in eligible_faces]
            if norm_input not in eligible_norms:
                suggested = eligible_faces[0]
                primary_face = str(commander_detail.get("primary_face") or commander_detail.get("name") or commander).strip()
                faces_str = ", ".join(f"'{face}'" for face in eligible_faces)
                error_msg = (
                    f"'{primary_face or commander}' can't lead a deck. Use {faces_str} as the commander instead. "
                    "We've updated the commander field for you."
                )
                ctx = {
                    "request": request,
                    "error": error_msg,
                    "brackets": orch.bracket_options(),
                    "labels": orch.ideal_labels(),
                    "defaults": orch.ideal_defaults(),
                    "allow_must_haves": ALLOW_MUST_HAVES,
                    "enable_custom_themes": ENABLE_CUSTOM_THEMES,
                    "form": _form_state(suggested),
                    "tag_slot_html": None,
                }
                theme_ctx = _custom_theme_context(request, sess, message=error_msg, level="error")
                for key, value in theme_ctx.items():
                    if key == "request":
                        continue
                    ctx[key] = value
                resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
                resp.set_cookie("sid", sid, httponly=True, samesite="lax")
                return resp
    # Normalize and validate commander selection (best-effort via orchestrator)
    sel = orch.commander_select(commander)
    if not sel.get("ok"):
        # Re-render modal with error
        ctx = {
            "request": request,
            "error": sel.get("error", "Commander not found"),
            "brackets": orch.bracket_options(),
            "labels": orch.ideal_labels(),
            "defaults": orch.ideal_defaults(),
            "allow_must_haves": ALLOW_MUST_HAVES,  # Add feature flag
            "enable_custom_themes": ENABLE_CUSTOM_THEMES,
            "form": _form_state(commander),
            "tag_slot_html": None,
        }
        theme_ctx = _custom_theme_context(request, sess, message=ctx["error"], level="error")
        for key, value in theme_ctx.items():
            if key == "request":
                continue
            ctx[key] = value
        resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    primary_commander_name = sel.get("name") or commander
    # Enforce GC bracket restriction before saving session (silently coerce to 3)
    try:
        is_gc = bool(primary_commander_name in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    if is_gc:
        try:
            if int(bracket) < 3:
                bracket = 3
        except Exception:
            bracket = 3
    # Save to session
    sess["commander"] = primary_commander_name
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
        primary_commander_name,
        feature_enabled=partner_feature_enabled,
        partner_enabled=partner_checkbox,
        secondary_candidate=secondary_commander,
        background_candidate=background,
        auto_opt_out=auto_opt_out_flag,
        selection_source=partner_selection_source,
    )

    partner_form_state["partner_mode"] = partner_mode
    partner_form_state["partner_auto_note"] = partner_auto_note
    partner_form_state["partner_warnings"] = partner_warnings
    partner_form_state["combined_preview"] = combined_payload
    if resolved_secondary:
        partner_form_state["secondary_commander"] = resolved_secondary
    if resolved_background:
        partner_form_state["background"] = resolved_background
    partner_form_state["partner_auto_assigned"] = bool(partner_auto_assigned_flag)

    combined_theme_pool: list[str] = []
    if isinstance(combined_payload, dict):
        raw_tags = combined_payload.get("theme_tags") or []
        for tag in raw_tags:
            token = str(tag).strip()
            if not token:
                continue
            if token not in combined_theme_pool:
                combined_theme_pool.append(token)

    if partner_error:
        available_tags = orch.tags_for_commander(primary_commander_name)
        recommended_tags = orch.recommended_tags_for_commander(primary_commander_name)
        recommended_reasons = orch.recommended_tag_reasons_for_commander(primary_commander_name)
        inspect_ctx: dict[str, Any] = {
            "request": request,
            "commander": {"name": primary_commander_name, "exclusion": lookup_commander_detail(primary_commander_name)},
            "tags": available_tags,
            "recommended": recommended_tags,
            "recommended_reasons": recommended_reasons,
            "gc_commander": is_gc,
            "brackets": orch.bracket_options(),
        }
        inspect_ctx.update(
            _partner_ui_context(
                primary_commander_name,
                partner_enabled=partner_checkbox,
                secondary_selection=partner_form_state["secondary_commander"] or None,
                background_selection=partner_form_state["background"] or None,
                combined_preview=combined_payload,
                warnings=partner_warnings,
                partner_error=partner_error,
                auto_note=partner_auto_note,
                auto_assigned=partner_form_state["partner_auto_assigned"],
                auto_prefill_allowed=not auto_opt_out_flag,
            )
        )
        partner_tags = inspect_ctx.pop("partner_theme_tags", None)
        if partner_tags:
            inspect_ctx["tags"] = partner_tags
        tag_slot_html = templates.get_template("build/_new_deck_tags.html").render(inspect_ctx)
        ctx = {
            "request": request,
            "error": partner_error,
            "brackets": orch.bracket_options(),
            "labels": orch.ideal_labels(),
            "defaults": orch.ideal_defaults(),
            "allow_must_haves": ALLOW_MUST_HAVES,
            "enable_custom_themes": ENABLE_CUSTOM_THEMES,
            "form": _form_state(primary_commander_name),
            "tag_slot_html": tag_slot_html,
        }
        theme_ctx = _custom_theme_context(request, sess, message=partner_error, level="error")
        for key, value in theme_ctx.items():
            if key == "request":
                continue
            ctx[key] = value
        resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    if partner_checkbox and combined_payload:
        sess["partner_enabled"] = True
        if resolved_secondary:
            sess["secondary_commander"] = resolved_secondary
        else:
            sess.pop("secondary_commander", None)
        if resolved_background:
            sess["background"] = resolved_background
        else:
            sess.pop("background", None)
        if partner_mode:
            sess["partner_mode"] = partner_mode
        else:
            sess.pop("partner_mode", None)
        sess["combined_commander"] = combined_payload
        sess["partner_warnings"] = partner_warnings
        if partner_auto_note:
            sess["partner_auto_note"] = partner_auto_note
        else:
            sess.pop("partner_auto_note", None)
        sess["partner_auto_assigned"] = bool(partner_auto_assigned_flag)
        sess["partner_auto_opt_out"] = bool(auto_opt_out_flag)
    else:
        sess["partner_enabled"] = False
        for key in [
            "secondary_commander",
            "background",
            "partner_mode",
            "partner_warnings",
            "combined_commander",
            "partner_auto_note",
        ]:
            try:
                sess.pop(key)
            except KeyError:
                pass
        for key in ["partner_auto_assigned", "partner_auto_opt_out"]:
            try:
                sess.pop(key)
            except KeyError:
                pass

    # 1) Start from explicitly selected tags (order preserved)
    tags = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    user_explicit = bool(tags)  # whether the user set any theme in the form
    # 2) Consider user-added supplemental themes from the Additional Themes UI
    additional_from_session = []
    try:
        # custom_theme_manager stores resolved list here on add/resolve; present before submit
        additional_from_session = [
            str(x) for x in (sess.get("additional_themes") or []) if isinstance(x, str) and x.strip()
        ]
    except Exception:
        additional_from_session = []
    # 3) If no explicit themes were selected, prefer additional themes as primary/secondary/tertiary
    if not user_explicit and additional_from_session:
        # Cap to three and preserve order
        tags = list(additional_from_session[:3])
    # 4) If user selected some themes, fill remaining slots with additional themes (deduping)
    elif user_explicit and additional_from_session:
        seen = {str(t).strip().casefold() for t in tags}
        for name in additional_from_session:
            key = name.strip().casefold()
            if key in seen:
                continue
            tags.append(name)
            seen.add(key)
            if len(tags) >= 3:
                break
    # 5) If still empty (no explicit and no additional), fall back to commander-recommended default
    if not tags:
        if combined_theme_pool:
            tags = combined_theme_pool[:3]
        else:
            try:
                rec = orch.recommended_tags_for_commander(sess["commander"]) or []
                if rec:
                    tags = [rec[0]]
            except Exception:
                pass
    sess["tags"] = tags
    sess["tag_mode"] = (tag_mode or "AND").upper()
    try:
        # Default to bracket 3 (Upgraded) when not provided
        sess["bracket"] = int(bracket) if (bracket is not None) else 3
    except Exception:
        try:
            sess["bracket"] = int(bracket)
        except Exception:
            sess["bracket"] = 3
    # Ideals: use provided values if any, else defaults
    ideals = orch.ideal_defaults()
    overrides = {k: v for k, v in {
        "ramp": ramp,
        "lands": lands,
        "basic_lands": basic_lands,
        "creatures": creatures,
        "removal": removal,
        "wipes": wipes,
        "card_advantage": card_advantage,
        "protection": protection,
    }.items() if v is not None}
    for k, v in overrides.items():
        try:
            ideals[k] = int(v)
        except Exception:
            pass
    sess["ideals"] = ideals
    if ENABLE_CUSTOM_THEMES:
        try:
            theme_mgr.refresh_resolution(
                sess,
                commander_tags=tags,
                mode=sess.get("theme_match_mode", DEFAULT_THEME_MATCH_MODE),
            )
        except ValueError as exc:
            error_msg = str(exc)
            ctx = {
                "request": request,
                "error": error_msg,
                "brackets": orch.bracket_options(),
                "labels": orch.ideal_labels(),
                "defaults": orch.ideal_defaults(),
                "allow_must_haves": ALLOW_MUST_HAVES,
                "enable_custom_themes": ENABLE_CUSTOM_THEMES,
                "form": _form_state(sess.get("commander", "")),
                "tag_slot_html": None,
            }
            theme_ctx = _custom_theme_context(request, sess, message=error_msg, level="error")
            for key, value in theme_ctx.items():
                if key == "request":
                    continue
                ctx[key] = value
            resp = templates.TemplateResponse("build/_new_deck_modal.html", ctx)
            resp.set_cookie("sid", sid, httponly=True, samesite="lax")
            return resp
    # Persist preferences
    try:
        sess["prefer_combos"] = bool(prefer_combos)
    except Exception:
        sess["prefer_combos"] = False
    try:
        sess["use_owned_only"] = bool(use_owned_only)
    except Exception:
        sess["use_owned_only"] = False
    try:
        sess["prefer_owned"] = bool(prefer_owned)
    except Exception:
        sess["prefer_owned"] = False
    try:
        sess["swap_mdfc_basics"] = bool(swap_mdfc_basics)
    except Exception:
        sess["swap_mdfc_basics"] = False
    # Combos config from modal
    try:
        if combo_count is not None:
            sess["combo_target_count"] = max(0, min(10, int(combo_count)))
    except Exception:
        pass
    try:
        if combo_balance:
            bval = str(combo_balance).strip().lower()
            if bval in ("early","late","mix"):
                sess["combo_balance"] = bval
    except Exception:
        pass
    # Multi-Copy selection from modal (opt-in)
    try:
        # Clear any prior selection first; this flow should define it explicitly when present
        if "multi_copy" in sess:
            del sess["multi_copy"]
        if enable_multicopy and multi_choice_id and str(multi_choice_id).strip():
            meta = bc.MULTI_COPY_ARCHETYPES.get(str(multi_choice_id), {})
            printed_cap = meta.get("printed_cap")
            cnt: int
            if multi_count is None:
                cnt = int(meta.get("default_count", 25))
            else:
                try:
                    cnt = int(multi_count)
                except Exception:
                    cnt = int(meta.get("default_count", 25))
            if isinstance(printed_cap, int) and printed_cap > 0:
                cnt = max(1, min(printed_cap, cnt))
            sess["multi_copy"] = {
                "id": str(multi_choice_id),
                "name": meta.get("name") or str(multi_choice_id),
                "count": int(cnt),
                "thrumming": True if (multi_thrumming and str(multi_thrumming).strip() in ("1","true","on","yes")) else False,
            }
        else:
            # Ensure disabled when not opted-in
            if "multi_copy" in sess:
                del sess["multi_copy"]
        # Reset the applied marker so the run can account for the new selection
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass
    
    # Process include/exclude cards (M3: Phase 2 - Full Include/Exclude)
    try:
        from deck_builder.include_exclude_utils import parse_card_list_input, IncludeExcludeDiagnostics
        
        # Clear any old include/exclude data
        for k in ["include_cards", "exclude_cards", "include_exclude_diagnostics", "enforcement_mode", "allow_illegal", "fuzzy_matching"]:
            if k in sess:
                del sess[k]
        
        # Process include cards
        if include_cards and include_cards.strip():
            print(f"DEBUG: Raw include_cards input: '{include_cards}'")
            include_list = parse_card_list_input(include_cards.strip())
            print(f"DEBUG: Parsed include_list: {include_list}")
            sess["include_cards"] = include_list
        else:
            print(f"DEBUG: include_cards is empty or None: '{include_cards}'")
        
        # Process exclude cards
        if exclude_cards and exclude_cards.strip():
            print(f"DEBUG: Raw exclude_cards input: '{exclude_cards}'")
            exclude_list = parse_card_list_input(exclude_cards.strip())
            print(f"DEBUG: Parsed exclude_list: {exclude_list}")
            sess["exclude_cards"] = exclude_list
        else:
            print(f"DEBUG: exclude_cards is empty or None: '{exclude_cards}'")
        
        # Store advanced options
        sess["enforcement_mode"] = enforcement_mode
        sess["allow_illegal"] = allow_illegal
        sess["fuzzy_matching"] = fuzzy_matching
        
        # Create basic diagnostics for status tracking
        if (include_cards and include_cards.strip()) or (exclude_cards and exclude_cards.strip()):
            diagnostics = IncludeExcludeDiagnostics(
                missing_includes=[],
                ignored_color_identity=[],
                illegal_dropped=[],
                illegal_allowed=[],
                excluded_removed=sess.get("exclude_cards", []),
                duplicates_collapsed={},
                include_added=[],
                include_over_ideal={},
                fuzzy_corrections={},
                confirmation_needed=[],
                list_size_warnings={
                    "includes_count": len(sess.get("include_cards", [])),
                    "excludes_count": len(sess.get("exclude_cards", [])),
                    "includes_limit": 10,
                    "excludes_limit": 15
                }
            )
            sess["include_exclude_diagnostics"] = diagnostics.__dict__
    except Exception as e:
        # If exclude parsing fails, log but don't block the build
        import logging
        logging.warning(f"Failed to parse exclude cards: {e}")
        
    # Clear any old staged build context
    for k in ["build_ctx", "locks", "replace_mode"]:
        if k in sess:
            try:
                del sess[k]
            except Exception:
                pass
    # Reset multi-copy suggestion debounce for a fresh run (keep selected choice)
    if "mc_seen_keys" in sess:
        try:
            del sess["mc_seen_keys"]
        except Exception:
            pass
    # Persist optional custom export base name
    if isinstance(name, str) and name.strip():
        sess["custom_export_base"] = name.strip()
    else:
        if "custom_export_base" in sess:
            try:
                del sess["custom_export_base"]
            except Exception:
                pass
    # If setup/tagging is not ready or stale, show a modal prompt instead of auto-running.
    try:
        if not _is_setup_ready():
            return templates.TemplateResponse(
                "build/_setup_prompt_modal.html",
                {
                    "request": request,
                    "title": "Setup required",
                    "message": "The card database and tags need to be prepared before building a deck.",
                    "action_url": "/setup/running?start=1&next=/build",
                    "action_label": "Run Setup",
                },
            )
        if _is_setup_stale():
            return templates.TemplateResponse(
                "build/_setup_prompt_modal.html",
                {
                    "request": request,
                    "title": "Data refresh recommended",
                    "message": "Your card database is stale. Refreshing ensures up-to-date results.",
                    "action_url": "/setup/running?start=1&force=1&next=/build",
                    "action_label": "Refresh Now",
                },
            )
    except Exception:
        # If readiness check fails, continue and let downstream handling surface errors
        pass
    # Immediately initialize a build context and run the first stage, like hitting Build Deck on review
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Centralized staged context creation
    sess["build_ctx"] = start_ctx_from_session(sess)
    res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=False)
    # If Multi-Copy ran first, mark applied to prevent redundant rebuilds on Continue
    try:
        if res.get("label") == "Multi-Copy Package" and sess.get("multi_copy"):
            mc = sess.get("multi_copy")
            sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
    except Exception:
        pass
    status = "Build complete" if res.get("done") else "Stage complete"
    sess["last_step"] = 5
    ctx = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=False)
    resp = templates.TemplateResponse("build/_step5.html", ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step1", response_class=HTMLResponse)
async def build_step1(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1", response_class=HTMLResponse)
async def build_step1_search(
    request: Request,
    query: str = Form(""),
    auto: str | None = Form(None),
    active: str | None = Form(None),
) -> HTMLResponse:
    query = (query or "").strip()
    auto_enabled = True if (auto == "1") else False
    candidates = []
    if query:
        candidates = orch.commander_candidates(query, limit=10)
        # Optional auto-select at a stricter threshold
        if auto_enabled and candidates and len(candidates[0]) >= 2 and int(candidates[0][1]) >= 98:
            top_name = candidates[0][0]
            res = orch.commander_select(top_name)
            if res.get("ok"):
                sid = request.cookies.get("sid") or new_sid()
                sess = get_session(sid)
                sess["last_step"] = 2
                commander_name = res.get("name")
                gc_flag = commander_name in getattr(bc, 'GAME_CHANGERS', [])
                context = {
                    "request": request,
                    "commander": res,
                    "tags": orch.tags_for_commander(commander_name),
                    "recommended": orch.recommended_tags_for_commander(commander_name),
                    "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander_name),
                    "brackets": orch.bracket_options(),
                    "gc_commander": gc_flag,
                    "selected_bracket": (3 if gc_flag else None),
                    "clear_persisted": True,
                }
                context.update(
                    _partner_ui_context(
                        commander_name,
                        partner_enabled=False,
                        secondary_selection=None,
                        background_selection=None,
                        combined_preview=None,
                        warnings=None,
                        partner_error=None,
                        auto_note=None,
                    )
                )
                resp = templates.TemplateResponse("build/_step2.html", context)
                resp.set_cookie("sid", sid, httponly=True, samesite="lax")
                return resp
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    resp = templates.TemplateResponse(
        "build/_step1.html",
        {
            "request": request,
            "query": query,
            "candidates": candidates,
            "auto": auto_enabled,
            "active": active,
            "count": len(candidates) if candidates else 0,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1/inspect", response_class=HTMLResponse)
async def build_step1_inspect(request: Request, name: str = Form(...)) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 1
    info = orch.commander_inspect(name)
    resp = templates.TemplateResponse(
        "build/_step1.html",
        {"request": request, "inspect": info, "selected": name, "tags": orch.tags_for_commander(name)},
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step1/confirm", response_class=HTMLResponse)
async def build_step1_confirm(request: Request, name: str = Form(...)) -> HTMLResponse:
    res = orch.commander_select(name)
    if not res.get("ok"):
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        sess["last_step"] = 1
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "error": res.get("error"), "selected": name})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Proceed to step2 placeholder and reset any prior build/session selections
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Reset sticky selections from previous runs
    for k in [
        "tags",
        "ideals",
        "bracket",
        "build_ctx",
        "last_step",
        "tag_mode",
        "mc_seen_keys",
        "multi_copy",
        "partner_enabled",
        "secondary_commander",
        "background",
        "partner_mode",
        "partner_warnings",
        "combined_commander",
        "partner_auto_note",
    ]:
        try:
            if k in sess:
                del sess[k]
        except Exception:
            pass
    sess["last_step"] = 2
    # Determine if commander is a Game Changer to drive bracket UI hiding
    is_gc = False
    try:
        is_gc = bool(res.get("name") in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    context = {
        "request": request,
        "commander": res,
        "tags": orch.tags_for_commander(res["name"]),
        "recommended": orch.recommended_tags_for_commander(res["name"]),
        "recommended_reasons": orch.recommended_tag_reasons_for_commander(res["name"]),
        "brackets": orch.bracket_options(),
        "gc_commander": is_gc,
        "selected_bracket": (3 if is_gc else None),
        # Signal that this navigation came from a fresh commander confirmation,
        # so the Step 2 UI should clear any localStorage theme persistence.
        "clear_persisted": True,
    }
    context.update(
        _partner_ui_context(
            res["name"],
            partner_enabled=False,
            secondary_selection=None,
            background_selection=None,
            combined_preview=None,
            warnings=None,
            partner_error=None,
            auto_note=None,
        )
    )
    resp = templates.TemplateResponse("build/_step2.html", context)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/reset-all", response_class=HTMLResponse)
async def build_reset_all(request: Request) -> HTMLResponse:
    """Clear all build-related session state and return Step 1."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    keys = [
        "commander","tags","tag_mode","bracket","ideals","build_ctx","last_step",
        "locks","replace_mode"
    ]
    for k in keys:
        try:
            if k in sess:
                del sess[k]
        except Exception:
            pass
    sess["last_step"] = 1
    resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/step5/rewind", response_class=HTMLResponse)
async def build_step5_rewind(request: Request, to: str = Form(...)) -> HTMLResponse:
    """Rewind the staged build to a previous visible stage by index or key and show that stage.

    Param `to` can be an integer index (1-based stage index) or a stage key string.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx")
    if not ctx:
        return await build_step5_get(request)
    target_i: int | None = None
    # Resolve by numeric index first
    try:
        idx_val = int(str(to).strip())
        target_i = idx_val
    except Exception:
        target_i = None
    if target_i is None:
        # attempt by key
        key = str(to).strip()
        try:
            for h in ctx.get("history", []) or []:
                if str(h.get("key")) == key or str(h.get("label")) == key:
                    target_i = int(h.get("i"))
                    break
        except Exception:
            target_i = None
    if not target_i:
        return await build_step5_get(request)
    # Try to restore snapshot stored for that history entry
    try:
        hist = ctx.get("history", []) or []
        snap = None
        for h in hist:
            if int(h.get("i")) == int(target_i):
                snap = h.get("snapshot")
                break
        if snap is not None:
            orch._restore_builder(ctx["builder"], snap)  # type: ignore[attr-defined]
            ctx["idx"] = int(target_i) - 1
            ctx["last_visible_idx"] = int(target_i) - 1
    except Exception:
        # As a fallback, restart ctx and run forward until target
        sess["build_ctx"] = start_ctx_from_session(sess)
        ctx = sess["build_ctx"]
        # Run forward until reaching target
        while True:
            res = orch.run_stage(ctx, rerun=False, show_skipped=False)
            if int(res.get("idx", 0)) >= int(target_i):
                break
            if res.get("done"):
                break
    # Finally show the target stage by running it with show_skipped True to get a view
    try:
        res = orch.run_stage(ctx, rerun=False, show_skipped=True)
        status = "Stage (rewound)" if not res.get("done") else "Build complete"
        ctx_resp = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=True, extras={
            "history": ctx.get("history", []),
        })
    except Exception as e:
        sess["last_step"] = 5
        ctx_resp = step5_error_ctx(request, sess, f"Failed to rewind: {e}")
    resp = templates.TemplateResponse("build/_step5.html", ctx_resp)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step2", response_class=HTMLResponse)
async def build_step2_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 2
    commander = sess.get("commander")
    if not commander:
        # Fallback to step1 if no commander in session
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    tags = orch.tags_for_commander(commander)
    selected = sess.get("tags", [])
    # Determine if the selected commander is considered a Game Changer (affects bracket choices)
    is_gc = False
    try:
        is_gc = bool(commander in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    # Selected bracket: if GC commander and bracket < 3 or missing, default to 3
    sel_br = sess.get("bracket")
    try:
        sel_br = int(sel_br) if sel_br is not None else None
    except Exception:
        sel_br = None
    if is_gc and (sel_br is None or int(sel_br) < 3):
        sel_br = 3
    partner_enabled = bool(sess.get("partner_enabled") and ENABLE_PARTNER_MECHANICS)
    context = {
        "request": request,
        "commander": {"name": commander},
        "tags": tags,
        "recommended": orch.recommended_tags_for_commander(commander),
        "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
        "brackets": orch.bracket_options(),
        "primary_tag": selected[0] if len(selected) > 0 else "",
        "secondary_tag": selected[1] if len(selected) > 1 else "",
        "tertiary_tag": selected[2] if len(selected) > 2 else "",
        "selected_bracket": sel_br,
        "tag_mode": sess.get("tag_mode", "AND"),
        "gc_commander": is_gc,
        # If there are no server-side tags for this commander, let the client clear any persisted ones
        # to avoid themes sticking between fresh runs.
        "clear_persisted": False if selected else True,
    }
    context.update(
        _partner_ui_context(
            commander,
            partner_enabled=partner_enabled,
            secondary_selection=sess.get("secondary_commander") if partner_enabled else None,
            background_selection=sess.get("background") if partner_enabled else None,
            combined_preview=sess.get("combined_commander") if partner_enabled else None,
            warnings=sess.get("partner_warnings") if partner_enabled else None,
            partner_error=None,
            auto_note=sess.get("partner_auto_note") if partner_enabled else None,
            auto_assigned=sess.get("partner_auto_assigned") if partner_enabled else None,
            auto_prefill_allowed=not bool(sess.get("partner_auto_opt_out")) if partner_enabled else True,
        )
    )
    partner_tags = context.pop("partner_theme_tags", None)
    if partner_tags:
        context["tags"] = partner_tags
    resp = templates.TemplateResponse("build/_step2.html", context)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step2", response_class=HTMLResponse)
async def build_step2_submit(
    request: Request,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    bracket: int = Form(...),
    partner_enabled: str | None = Form(None),
    secondary_commander: str | None = Form(None),
    background: str | None = Form(None),
    partner_selection_source: str | None = Form(None),
    partner_auto_opt_out: str | None = Form(None),
) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 2

    partner_feature_enabled = ENABLE_PARTNER_MECHANICS
    partner_flag = False
    if partner_feature_enabled:
        raw_partner_enabled = (partner_enabled or "").strip().lower()
        partner_flag = raw_partner_enabled in {"1", "true", "on", "yes"}
    auto_opt_out_flag = (partner_auto_opt_out or "").strip().lower() in {"1", "true", "on", "yes"}

    # Validate primary tag selection if tags are available
    available_tags = orch.tags_for_commander(commander)
    if available_tags and not (primary_tag and primary_tag.strip()):
        # Compute GC flag to hide disallowed brackets on error
        is_gc = False
        try:
            is_gc = bool(commander in getattr(bc, 'GAME_CHANGERS', []))
        except Exception:
            is_gc = False
        try:
            sel_br = int(bracket) if bracket is not None else None
        except Exception:
            sel_br = None
        if is_gc and (sel_br is None or sel_br < 3):
            sel_br = 3
        context = {
            "request": request,
            "commander": {"name": commander},
            "tags": available_tags,
            "recommended": orch.recommended_tags_for_commander(commander),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
            "brackets": orch.bracket_options(),
            "error": "Please choose a primary theme.",
            "primary_tag": primary_tag or "",
            "secondary_tag": secondary_tag or "",
            "tertiary_tag": tertiary_tag or "",
            "selected_bracket": sel_br,
            "tag_mode": (tag_mode or "AND"),
            "gc_commander": is_gc,
        }
        context.update(
            _partner_ui_context(
                commander,
                partner_enabled=partner_flag,
                secondary_selection=secondary_commander if partner_flag else None,
                background_selection=background if partner_flag else None,
                combined_preview=None,
                warnings=[],
                partner_error=None,
                auto_note=None,
                auto_assigned=None,
                auto_prefill_allowed=not auto_opt_out_flag,
            )
        )
        partner_tags = context.pop("partner_theme_tags", None)
        if partner_tags:
            context["tags"] = partner_tags
        resp = templates.TemplateResponse("build/_step2.html", context)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    # Enforce bracket restrictions for Game Changer commanders (silently coerce to 3 if needed)
    try:
        is_gc = bool(commander in getattr(bc, 'GAME_CHANGERS', []))
    except Exception:
        is_gc = False
    if is_gc:
        try:
            if int(bracket) < 3:
                bracket = 3  # coerce silently
        except Exception:
            bracket = 3

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
        selection_source=partner_selection_source,
    )

    if partner_error:
        try:
            sel_br = int(bracket)
        except Exception:
            sel_br = None
        context: dict[str, Any] = {
            "request": request,
            "commander": {"name": commander},
            "tags": available_tags,
            "recommended": orch.recommended_tags_for_commander(commander),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
            "brackets": orch.bracket_options(),
            "primary_tag": primary_tag or "",
            "secondary_tag": secondary_tag or "",
            "tertiary_tag": tertiary_tag or "",
            "selected_bracket": sel_br,
            "tag_mode": (tag_mode or "AND"),
            "gc_commander": is_gc,
            "error": None,
        }
        context.update(
            _partner_ui_context(
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
        )
        partner_tags = context.pop("partner_theme_tags", None)
        if partner_tags:
            context["tags"] = partner_tags
        resp = templates.TemplateResponse("build/_step2.html", context)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    # Save selection to session (basic MVP; real build will use this later)
    sess["commander"] = commander
    sess["tags"] = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    sess["tag_mode"] = (tag_mode or "AND").upper()
    sess["bracket"] = int(bracket)

    if partner_flag and combined_payload:
        sess["partner_enabled"] = True
        if resolved_secondary:
            sess["secondary_commander"] = resolved_secondary
        else:
            sess.pop("secondary_commander", None)
        if resolved_background:
            sess["background"] = resolved_background
        else:
            sess.pop("background", None)
        if partner_mode:
            sess["partner_mode"] = partner_mode
        else:
            sess.pop("partner_mode", None)
        sess["combined_commander"] = combined_payload
        sess["partner_warnings"] = partner_warnings
        if partner_auto_note:
            sess["partner_auto_note"] = partner_auto_note
        else:
            sess.pop("partner_auto_note", None)
        sess["partner_auto_assigned"] = bool(partner_auto_assigned_flag)
        sess["partner_auto_opt_out"] = bool(auto_opt_out_flag)
    else:
        sess["partner_enabled"] = False
        for key in [
            "secondary_commander",
            "background",
            "partner_mode",
            "partner_warnings",
            "combined_commander",
            "partner_auto_note",
        ]:
            try:
                sess.pop(key)
            except KeyError:
                pass
        for key in ["partner_auto_assigned", "partner_auto_opt_out"]:
            try:
                sess.pop(key)
            except KeyError:
                pass

    # Clear multi-copy seen/selection to re-evaluate on Step 3
    try:
        if "mc_seen_keys" in sess:
            del sess["mc_seen_keys"]
        if "multi_copy" in sess:
            del sess["multi_copy"]
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass
    # Proceed to Step 3 placeholder for now
    sess["last_step"] = 3
    resp = templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "commander": commander,
            "tags": sess["tags"],
            "bracket": sess["bracket"],
            "defaults": orch.ideal_defaults(),
            "labels": orch.ideal_labels(),
            "values": orch.ideal_defaults(),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step3", response_class=HTMLResponse)
async def build_step3_submit(
    request: Request,
    ramp: int = Form(...),
    lands: int = Form(...),
    basic_lands: int = Form(...),
    creatures: int = Form(...),
    removal: int = Form(...),
    wipes: int = Form(...),
    card_advantage: int = Form(...),
    protection: int = Form(...),
) -> HTMLResponse:
    labels = orch.ideal_labels()
    submitted = {
        "ramp": ramp,
        "lands": lands,
        "basic_lands": basic_lands,
        "creatures": creatures,
        "removal": removal,
        "wipes": wipes,
        "card_advantage": card_advantage,
        "protection": protection,
    }

    errors: list[str] = []
    for k, v in submitted.items():
        try:
            iv = int(v)
        except Exception:
            errors.append(f"{labels.get(k, k)} must be a number.")
            continue
        if iv < 0:
            errors.append(f"{labels.get(k, k)} cannot be negative.")
        submitted[k] = iv
    # Cross-field validation: basic lands should not exceed total lands
    if isinstance(submitted.get("basic_lands"), int) and isinstance(submitted.get("lands"), int):
        if submitted["basic_lands"] > submitted["lands"]:
            errors.append("Basic Lands cannot exceed Total Lands.")

    if errors:
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        sess["last_step"] = 3
        resp = templates.TemplateResponse(
            "build/_step3.html",
            {
                "request": request,
                "defaults": orch.ideal_defaults(),
                "labels": labels,
                "values": submitted,
                "error": " ".join(errors),
                "commander": sess.get("commander"),
                "tags": sess.get("tags", []),
                "bracket": sess.get("bracket"),
            },
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

    # Save to session
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["ideals"] = submitted
    # Any change to ideals should clear the applied marker, we may want to re-stage
    try:
        if "mc_applied_key" in sess:
            del sess["mc_applied_key"]
    except Exception:
        pass

    # Proceed to review (Step 4)
    sess["last_step"] = 4
    resp = templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": submitted,
            "commander": sess.get("commander"),
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step3", response_class=HTMLResponse)
async def build_step3_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 3
    defaults = orch.ideal_defaults()
    values = sess.get("ideals") or defaults
    resp = templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "defaults": defaults,
            "labels": orch.ideal_labels(),
            "values": values,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step4", response_class=HTMLResponse)
async def build_step4_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 4
    labels = orch.ideal_labels()
    values = sess.get("ideals") or orch.ideal_defaults()
    commander = sess.get("commander")
    return templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": values,
            "commander": commander,
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
    )


# --- Combos & Synergies panel (M3) ---
def _get_current_deck_names(sess: dict) -> list[str]:
    try:
        ctx = sess.get("build_ctx") or {}
        b = ctx.get("builder")
        lib = getattr(b, "card_library", {}) if b is not None else {}
        names = [str(n) for n in lib.keys()]
        return sorted(dict.fromkeys(names))
    except Exception:
        return []


@router.get("/combos", response_class=HTMLResponse)
async def build_combos_panel(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    names = _get_current_deck_names(sess)
    if not names:
        # No active build; render nothing to avoid UI clutter
        return HTMLResponse("")

    # Preferences (persisted in session)
    policy = (sess.get("combos_policy") or "neutral").lower()
    if policy not in {"avoid", "neutral", "prefer"}:
        policy = "neutral"
    try:
        target = int(sess.get("combos_target") or 0)
    except Exception:
        target = 0
    if target < 0:
        target = 0

    # Load lists and run detection
    _det = _detect_all(names)
    combos = _det.get("combos", [])
    synergies = _det.get("synergies", [])
    combos_model = _det.get("combos_model")
    synergies_model = _det.get("synergies_model")

    # Suggestions
    suggestions: list[dict] = []
    present = {s.strip().lower() for s in names}
    suggested_names: set[str] = set()
    if combos_model is not None:
        # Prefer policy: suggest adding a missing partner to hit target count
        if policy == "prefer":
            try:
                for p in combos_model.pairs:
                    a = str(p.a).strip()
                    b = str(p.b).strip()
                    a_in = a.lower() in present
                    b_in = b.lower() in present
                    if a_in ^ b_in:  # exactly one present
                        missing = b if a_in else a
                        have = a if a_in else b
                        item = {
                            "kind": "add",
                            "have": have,
                            "name": missing,
                            "cheap_early": bool(getattr(p, "cheap_early", False)),
                            "setup_dependent": bool(getattr(p, "setup_dependent", False)),
                        }
                        key = str(missing).strip().lower()
                        if key not in present and key not in suggested_names:
                            suggestions.append(item)
                            suggested_names.add(key)
                # Rank: cheap/early first, then setup-dependent, then name
                suggestions.sort(key=lambda s: (0 if s.get("cheap_early") else 1, 0 if s.get("setup_dependent") else 1, str(s.get("name")).lower()))
                # If we still have room below target, add synergy-based suggestions
                rem = (max(0, int(target)) if target > 0 else 8) - len(suggestions)
                if rem > 0 and synergies_model is not None:
                    # lightweight tag weights to bias common engines
                    weights = {
                        "treasure": 3.0, "tokens": 2.8, "landfall": 2.6, "card draw": 2.5, "ramp": 2.3,
                        "engine": 2.2, "value": 2.1, "artifacts": 2.0, "enchantress": 2.0, "spellslinger": 1.9,
                        "counters": 1.8, "equipment matters": 1.7, "tribal": 1.6, "lifegain": 1.5, "mill": 1.4,
                        "damage": 1.3, "stax": 1.2
                    }
                    syn_sugs: list[dict] = []
                    for p in synergies_model.pairs:
                        a = str(p.a).strip()
                        b = str(p.b).strip()
                        a_in = a.lower() in present
                        b_in = b.lower() in present
                        if a_in ^ b_in:
                            missing = b if a_in else a
                            have = a if a_in else b
                            mkey = missing.strip().lower()
                            if mkey in present or mkey in suggested_names:
                                continue
                            tags = list(getattr(p, "tags", []) or [])
                            score = 1.0 + sum(weights.get(str(t).lower(), 1.0) for t in tags) / max(1, len(tags) or 1)
                            syn_sugs.append({
                                "kind": "add",
                                "have": have,
                                "name": missing,
                                "cheap_early": False,
                                "setup_dependent": False,
                                "tags": tags,
                                "_score": score,
                            })
                            suggested_names.add(mkey)
                    # rank by score desc then name
                    syn_sugs.sort(key=lambda s: (-float(s.get("_score", 0.0)), str(s.get("name")).lower()))
                    if rem > 0:
                        suggestions.extend(syn_sugs[:rem])
                # Finally trim to target or default cap
                cap = (int(target) if target > 0 else 8)
                suggestions = suggestions[:cap]
            except Exception:
                suggestions = []
        elif policy == "avoid":
            # Avoid policy: suggest cutting one piece from detected combos
            try:
                for c in combos:
                    # pick the second card as default cut to vary suggestions
                    suggestions.append({
                        "kind": "cut",
                        "name": c.b,
                        "partner": c.a,
                        "cheap_early": bool(getattr(c, "cheap_early", False)),
                        "setup_dependent": bool(getattr(c, "setup_dependent", False)),
                    })
                # Rank: cheap/early first
                suggestions.sort(key=lambda s: (0 if s.get("cheap_early") else 1, 0 if s.get("setup_dependent") else 1, str(s.get("name")).lower()))
                if target > 0:
                    suggestions = suggestions[: target]
                else:
                    suggestions = suggestions[: 8]
            except Exception:
                suggestions = []

    ctx = {
        "request": request,
        "policy": policy,
        "target": target,
        "combos": combos,
        "synergies": synergies,
        "versions": _det.get("versions", {}),
        "suggestions": suggestions,
    }
    return templates.TemplateResponse("build/_combos_panel.html", ctx)


@router.post("/combos/prefs", response_class=HTMLResponse)
async def build_combos_save_prefs(request: Request, policy: str = Form("neutral"), target: int = Form(0)) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    pol = (policy or "neutral").strip().lower()
    if pol not in {"avoid", "neutral", "prefer"}:
        pol = "neutral"
    try:
        tgt = int(target)
    except Exception:
        tgt = 0
    if tgt < 0:
        tgt = 0
    sess["combos_policy"] = pol
    sess["combos_target"] = tgt
    # Re-render the panel
    return await build_combos_panel(request)


@router.post("/toggle-owned-review", response_class=HTMLResponse)
async def build_toggle_owned_review(
    request: Request,
    use_owned_only: str | None = Form(None),
    prefer_owned: str | None = Form(None),
    swap_mdfc_basics: str | None = Form(None),
) -> HTMLResponse:
    """Toggle 'use owned only' and/or 'prefer owned' flags from the Review step and re-render Step 4."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 4
    only_val = True if (use_owned_only and str(use_owned_only).strip() in ("1","true","on","yes")) else False
    pref_val = True if (prefer_owned and str(prefer_owned).strip() in ("1","true","on","yes")) else False
    swap_val = True if (swap_mdfc_basics and str(swap_mdfc_basics).strip() in ("1","true","on","yes")) else False
    sess["use_owned_only"] = only_val
    sess["prefer_owned"] = pref_val
    sess["swap_mdfc_basics"] = swap_val
    # Do not touch build_ctx here; user hasn't started the build yet from review
    labels = orch.ideal_labels()
    values = sess.get("ideals") or orch.ideal_defaults()
    commander = sess.get("commander")
    resp = templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": values,
            "commander": commander,
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step5", response_class=HTMLResponse)
async def build_step5_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["last_step"] = 5
    # Default replace-mode to ON unless explicitly toggled off
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    base = step5_empty_ctx(request, sess)
    resp = templates.TemplateResponse("build/_step5.html", base)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
    
@router.post("/step5/continue", response_class=HTMLResponse)
async def build_step5_continue(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Validate commander; redirect to step1 if missing
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Ensure build context exists; if not, start it first
    if not sess.get("build_ctx"):
        sess["build_ctx"] = start_ctx_from_session(sess)
    else:
        # If context exists already, rebuild ONLY when the multi-copy selection changed or hasn't been applied yet
        try:
            mc = sess.get("multi_copy") or None
            selkey = None
            if mc:
                selkey = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
            applied = sess.get("mc_applied_key") if mc else None
            if mc and (not applied or applied != selkey):
                _rebuild_ctx_with_multicopy(sess)
            # If we still have no stages (e.g., minimal test context), inject a minimal multi-copy stage inline
            try:
                ctx = sess.get("build_ctx") or {}
                stages = ctx.get("stages") if isinstance(ctx, dict) else None
                if (not stages or len(stages) == 0) and mc:
                    b = ctx.get("builder") if isinstance(ctx, dict) else None
                    if b is not None:
                        try:
                            setattr(b, "_web_multi_copy", mc)
                        except Exception:
                            pass
                        try:
                            if not isinstance(getattr(b, "card_library", None), dict):
                                b.card_library = {}
                        except Exception:
                            pass
                        try:
                            if not isinstance(getattr(b, "ideal_counts", None), dict):
                                b.ideal_counts = {}
                        except Exception:
                            pass
                        ctx["stages"] = [{"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"}]
                        ctx["idx"] = 0
                        ctx["last_visible_idx"] = 0
            except Exception:
                pass
        except Exception:
            pass
    # Read show_skipped from either query or form safely
    show_skipped = True if (request.query_params.get('show_skipped') == '1') else False
    try:
        form = await request.form()
        if form and form.get('show_skipped') == '1':
            show_skipped = True
    except Exception:
        pass
    try:
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=show_skipped)
        status = "Build complete" if res.get("done") else "Stage complete"
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to continue: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    stage_label = res.get("label")
    # If we just applied Multi-Copy, stamp the applied key so we don't rebuild again
    try:
        if stage_label == "Multi-Copy Package" and sess.get("multi_copy"):
            mc = sess.get("multi_copy")
            sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
    except Exception:
        pass
    # Note: no redirect; the inline compliance panel will render inside Step 5
    sess["last_step"] = 5
    ctx2 = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
    resp = templates.TemplateResponse("build/_step5.html", ctx2)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/step5/rerun", response_class=HTMLResponse)
async def build_step5_rerun(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Rerun requires an existing context; if missing, create it and run first stage as rerun
    if not sess.get("build_ctx"):
        sess["build_ctx"] = start_ctx_from_session(sess)
    else:
        # Ensure latest locks are reflected in the existing context
        try:
            sess["build_ctx"]["locks"] = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        except Exception:
            pass
    show_skipped = False
    try:
        form = await request.form()
        show_skipped = True if (form.get('show_skipped') == '1') else False
    except Exception:
        pass
    # If replace-mode is OFF, keep the stage visible even if no new cards were added
    if not bool(sess.get("replace_mode", True)):
        show_skipped = True
    try:
        res = orch.run_stage(sess["build_ctx"], rerun=True, show_skipped=show_skipped, replace=bool(sess.get("replace_mode", True)))
        status = "Stage rerun complete" if not res.get("done") else "Build complete"
    except Exception as e:
        sess["last_step"] = 5
        err_ctx = step5_error_ctx(request, sess, f"Failed to rerun stage: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    sess["last_step"] = 5
    # Build locked cards list with ownership and in-deck presence
    locked_cards = []
    try:
        ctx = sess.get("build_ctx") or {}
        b = ctx.get("builder") if isinstance(ctx, dict) else None
        present: set[str] = builder_present_names(b) if b is not None else set()
        # Display-map via combined df when available
        lock_lower = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        display_map: dict[str, str] = builder_display_map(b, lock_lower) if b is not None else {}
        owned_lower = owned_set_helper()
        for nm in (sess.get("locks", []) or []):
            key = str(nm).strip().lower()
            disp = display_map.get(key, nm)
            locked_cards.append({
                "name": disp,
                "owned": key in owned_lower,
                "in_deck": key in present,
            })
    except Exception:
        locked_cards = []
    ctx3 = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
    ctx3["locked_cards"] = locked_cards
    resp = templates.TemplateResponse("build/_step5.html", ctx3)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step5/start", response_class=HTMLResponse)
async def build_step5_start(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if "replace_mode" not in sess:
        sess["replace_mode"] = True
    # Validate commander exists before starting
    commander = sess.get("commander")
    if not commander:
        resp = templates.TemplateResponse(
            "build/_step1.html",
            {"request": request, "candidates": [], "error": "Please select a commander first."},
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    try:
        # Initialize step-by-step build context and run first stage
        sess["build_ctx"] = start_ctx_from_session(sess)
        show_skipped = False
        try:
            form = await request.form()
            show_skipped = True if (form.get('show_skipped') == '1') else False
        except Exception:
            pass
        res = orch.run_stage(sess["build_ctx"], rerun=False, show_skipped=show_skipped)
        status = "Stage complete" if not res.get("done") else "Build complete"
        # If Multi-Copy ran first, mark applied to prevent redundant rebuilds on Continue
        try:
            if res.get("label") == "Multi-Copy Package" and sess.get("multi_copy"):
                mc = sess.get("multi_copy")
                sess["mc_applied_key"] = f"{mc.get('id','')}|{int(mc.get('count',0))}|{1 if mc.get('thrumming') else 0}"
        except Exception:
            pass
    # Note: no redirect; the inline compliance panel will render inside Step 5
        sess["last_step"] = 5
        ctx = step5_ctx_from_result(request, sess, res, status_text=status, show_skipped=show_skipped)
        resp = templates.TemplateResponse("build/_step5.html", ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    except Exception as e:
        # Surface a friendly error on the step 5 screen with normalized context
        err_ctx = step5_error_ctx(
            request,
            sess,
            f"Failed to start build: {e}",
            include_name=False,
        )
        # Ensure commander stays visible if set
        err_ctx["commander"] = commander
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

@router.get("/step5/start", response_class=HTMLResponse)
async def build_step5_start_get(request: Request) -> HTMLResponse:
    # Allow GET as a fallback to start the build (delegates to POST handler)
    return await build_step5_start(request)


@router.get("/banner", response_class=HTMLResponse)
async def build_banner(request: Request, step: str = "", i: int | None = None, n: int | None = None) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    tags = sess.get("tags", [])
    # Render only the inner text for the subtitle
    return templates.TemplateResponse(
        "build/_banner_subtitle.html",
        {"request": request, "commander": commander, "tags": tags, "name": sess.get("custom_export_base")},
    )


@router.post("/step5/toggle-replace")
async def build_step5_toggle_replace(request: Request, replace: str = Form("0")):
    """Toggle replace-mode for reruns and return an updated button HTML."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    enabled = True if str(replace).strip() in ("1","true","on","yes") else False
    sess["replace_mode"] = enabled
    # Return the checkbox control snippet (same as template)
    checked = 'checked' if enabled else ''
    html = (
        '<div class="replace-toggle" role="group" aria-label="Replace toggle">'
        '<form hx-post="/build/step5/toggle-replace" hx-target="closest .replace-toggle" hx-swap="outerHTML" onsubmit="return false;" style="display:inline;">'
        f'<input type="hidden" name="replace" value="{"1" if enabled else "0"}" />'
        '<label class="muted" style="display:flex; align-items:center; gap:.35rem;">'
        f'<input type="checkbox" name="replace_chk" value="1" {checked} '
        'onchange="try{ const f=this.form; const h=f.querySelector(\'input[name=replace]\'); if(h){ h.value=this.checked?\'1\':\'0\'; } f.requestSubmit(); }catch(_){ }" />'
        'Replace stage picks'
        '</label>'
        '</form>'
        '</div>'
    )
    return HTMLResponse(html)


@router.post("/step5/reset-stage", response_class=HTMLResponse)
async def build_step5_reset_stage(request: Request) -> HTMLResponse:
    """Reset current visible stage to the pre-stage snapshot (if available) without running it."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx")
    if not ctx or not ctx.get("snapshot"):
        return await build_step5_get(request)
    try:
        orch._restore_builder(ctx["builder"], ctx["snapshot"])  # type: ignore[attr-defined]
    except Exception:
        return await build_step5_get(request)
    # Re-render step 5 with cleared added list
    base = step5_empty_ctx(request, sess, extras={
        "status": "Stage reset",
        "i": ctx.get("idx"),
        "n": len(ctx.get("stages", [])),
    })
    resp = templates.TemplateResponse("build/_step5.html", base)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

# --- Phase 8: Lock/Replace/Compare/Permalink minimal API ---

@router.post("/lock")
async def build_lock_toggle(request: Request, name: str = Form(...), locked: str = Form("1"), from_list: str | None = Form(None)):
    """Toggle lock for a card name in the current session; return an HTML button to swap in-place."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    locks = set(sess.get("locks", []))
    key = str(name).strip().lower()
    want_lock = True if str(locked).strip() in ("1","true","on","yes") else False
    if want_lock:
        locks.add(key)
    else:
        locks.discard(key)
    sess["locks"] = list(locks)
    # If a build context exists, update it too
    if sess.get("build_ctx"):
        try:
            sess["build_ctx"]["locks"] = {str(n) for n in locks}
        except Exception:
            pass
    # Return a compact button HTML that flips state on next click, and an OOB last-action chip
    next_state = "0" if want_lock else "1"
    label = "Unlock" if want_lock else "Lock"
    title = ("Click to unlock" if want_lock else "Click to lock")
    icon = ("🔒" if want_lock else "🔓")
    # Include data-locked to reflect the current state for client-side handler
    btn = f'''<button type="button" class="btn-lock" title="{title}" data-locked="{'1' if want_lock else '0'}"
                 hx-post="/build/lock" hx-target="closest .lock-box" hx-swap="innerHTML"
                 hx-vals='{{"name": "{name}", "locked": "{next_state}"}}'>{icon} {label}</button>'''
    # Compute locks count for chip
    locks_count = len(locks)
    if locks_count > 0:
        chip_html = f'<span id="locks-chip" hx-swap-oob="true"><span class="chip" title="Locked cards">🔒 {locks_count} locked</span></span>'
    else:
        chip_html = '<span id="locks-chip" hx-swap-oob="true"></span>'
    # Last action chip for feedback (use hx-swap-oob)
    try:
        disp = (name or '').strip()
    except Exception:
        disp = str(name)
    action = "Locked" if want_lock else "Unlocked"
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">{action} <strong>{disp}</strong></span>'
        f'</div>'
    )
    # If this request came from the locked-cards list and it's an unlock, remove the row inline
    try:
        if (from_list is not None) and (not want_lock):
            # Also update the locks-count chip, and if no locks remain, remove the whole section
            extra = chip_html
            if locks_count == 0:
                extra += '<details id="locked-section" hx-swap-oob="true"></details>'
            # Return empty body to delete the <li> via hx-swap=outerHTML, plus OOB updates
            return HTMLResponse('' + extra)
    except Exception:
        pass
    return HTMLResponse(btn + chip + chip_html)


@router.get("/alternatives", response_class=HTMLResponse)
async def build_alternatives(
    request: Request,
    name: str,
    stage: str | None = None,
    owned_only: int = Query(0),
    refresh: int = Query(0),
) -> HTMLResponse:
    """Suggest alternative cards for a given card name, preferring role-specific pools.

    Strategy:
    1) Determine the seed card's role from the current deck (Role field) or optional `stage` hint.
    2) Build a candidate pool from the combined DataFrame using the same filters as the build phase
       for that role (ramp/removal/wipes/card_advantage/protection).
    3) Exclude commander, lands (where applicable), in-deck, locked, and the seed itself; then sort
       by edhrecRank/manaValue. Apply owned-only filter if requested.
    4) Fall back to tag-overlap similarity when role cannot be determined or data is missing.

    Returns an HTML partial listing up to ~10 alternatives with Replace buttons.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b = ctx.get("builder") if isinstance(ctx, dict) else None
    # Owned library
    owned_set = owned_set_helper()
    require_owned = bool(int(owned_only or 0)) or bool(sess.get("use_owned_only"))
    refresh_requested = bool(int(refresh or 0))
    # If builder context missing, show a guidance message
    if not b:
        html = '<div class="alts"><div class="muted">Start the build to see alternatives.</div></div>'
        return HTMLResponse(html)
    try:
        name_disp = str(name).strip()
        name_l = name_disp.lower()
        commander_l = str((sess.get("commander") or "")).strip().lower()
        locked_set = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        # Exclusions from prior inline replacements
        alts_exclude = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
        alts_exclude_v = int(sess.get("alts_exclude_v") or 0)

        # Resolve role from stage hint or current library entry
        stage_hint = (stage or "").strip().lower()
        stage_map = {
            "ramp": "ramp",
            "removal": "removal",
            "wipes": "wipe",
            "wipe": "wipe",
            "board_wipe": "wipe",
            "card_advantage": "card_advantage",
            "draw": "card_advantage",
            "protection": "protection",
            # Additional mappings for creature stages
            "creature": "creature",
            "creatures": "creature",
            "primary": "creature",
            "secondary": "creature",
            # Land-related hints
            "land": "land",
            "lands": "land",
            "utility": "land",
            "misc": "land",
            "fetch": "land",
            "dual": "land",
        }
        hinted_role = stage_map.get(stage_hint) if stage_hint else None
        lib = getattr(b, "card_library", {}) or {}
        # Case-insensitive lookup in deck library
        lib_key = None
        try:
            if name_disp in lib:
                lib_key = name_disp
            else:
                lm = {str(k).strip().lower(): k for k in lib.keys()}
                lib_key = lm.get(name_l)
        except Exception:
            lib_key = None
        entry = lib.get(lib_key) if lib_key else None
        role = hinted_role or (entry.get("Role") if isinstance(entry, dict) else None)
        if isinstance(role, str):
            role = role.strip().lower()

        # Build role-specific pool from combined DataFrame
        items: list[dict] = []

        def _clean(value: Any) -> str:
            try:
                if value is None:
                    return ""
                if isinstance(value, float) and value != value:
                    return ""
                text = str(value)
                return text.strip()
            except Exception:
                return ""

        def _normalize_tags(raw: Any) -> list[str]:
            if not raw:
                return []
            if isinstance(raw, (list, tuple, set)):
                return [str(t).strip() for t in raw if str(t).strip()]
            if isinstance(raw, str):
                txt = raw.strip()
                if not txt:
                    return []
                if txt.startswith("[") and txt.endswith("]"):
                    try:
                        import json as _json
                        parsed = _json.loads(txt)
                        if isinstance(parsed, list):
                            return [str(t).strip() for t in parsed if str(t).strip()]
                    except Exception:
                        pass
                return [s.strip() for s in txt.split(',') if s.strip()]
            return []

        def _meta_from_row(row_obj: Any) -> dict[str, Any]:
            meta = {
                "mana": "",
                "rarity": "",
                "role": "",
                "tags": [],
                "hover_simple": True,
            }
            if row_obj is None:
                meta["role"] = _clean(used_role or "")
                return meta

            def _pull(*keys: str) -> Any:
                for key in keys:
                    try:
                        if isinstance(row_obj, dict):
                            val = row_obj.get(key)
                        elif hasattr(row_obj, "get"):
                            val = row_obj.get(key)
                        else:
                            val = getattr(row_obj, key, None)
                    except Exception:
                        val = None
                    if val not in (None, ""):
                        if isinstance(val, float) and val != val:
                            continue
                        return val
                return None

            meta["mana"] = _clean(_pull("mana_cost", "manaCost", "mana", "manaValue", "cmc", "mv"))
            meta["rarity"] = _clean(_pull("rarity"))
            role_val = _pull("role", "primaryRole", "subRole")
            if not role_val:
                role_val = used_role or ""
            meta["role"] = _clean(role_val)
            tags_val = _pull("themeTags", "_ltags", "tags")
            meta_tags = _normalize_tags(tags_val)
            meta["tags"] = meta_tags
            meta["hover_simple"] = not (meta["mana"] or meta["rarity"] or (meta_tags and len(meta_tags) > 0))
            return meta

        def _build_meta_map(df_obj) -> dict[str, dict[str, Any]]:
            mapping: dict[str, dict[str, Any]] = {}
            try:
                if df_obj is None or not hasattr(df_obj, "iterrows"):
                    return mapping
                for _, row in df_obj.iterrows():
                    try:
                        nm_val = str(row.get("name") or "").strip()
                    except Exception:
                        nm_val = ""
                    if not nm_val:
                        continue
                    key = nm_val.lower()
                    if key in mapping:
                        continue
                    mapping[key] = _meta_from_row(row)
            except Exception:
                return mapping
            return mapping

        def _sampler(seq: list[str], limit: int) -> list[str]:
            if limit <= 0:
                return []
            if len(seq) <= limit:
                return list(seq)
            rng = getattr(b, "rng", None)
            try:
                if rng is not None:
                    return rng.sample(seq, limit) if len(seq) >= limit else list(seq)
                import random as _rnd  # type: ignore
                return _rnd.sample(seq, limit) if len(seq) >= limit else list(seq)
            except Exception:
                return list(seq[:limit])
        used_role = role if isinstance(role, str) and role else None
        # Promote to 'land' role when the seed card is a land (regardless of stored role)
        try:
            if entry and isinstance(entry, dict):
                ctype = str(entry.get("Card Type") or entry.get("Type") or "").lower()
                if "land" in ctype:
                    used_role = "land"
        except Exception:
            pass
        df = getattr(b, "_combined_cards_df", None)

        # Compute current deck fingerprint to avoid stale cached alternatives after stage changes
        in_deck: set[str] = builder_present_names(b)
        try:
            import hashlib as _hl
            deck_fp = _hl.md5(
                ("|".join(sorted(in_deck)) if in_deck else "").encode("utf-8")
            ).hexdigest()[:8]
        except Exception:
            deck_fp = str(len(in_deck))

        # Use a cache key that includes the exclusions version and deck fingerprint
        cache_key = (name_l, commander_l, used_role or "_fallback_", require_owned, alts_exclude_v, deck_fp)
        cached = None
        if used_role != 'land' and not refresh_requested:
            cached = _alts_get_cached(cache_key)
        if cached is not None:
            return HTMLResponse(cached)

        def _render_and_cache(_items: list[dict]):
            html_str = templates.get_template("build/_alternatives.html").render({
                "request": request,
                "name": name_disp,
                "require_owned": require_owned,
                "items": _items,
            })
            # Skip caching when used_role == land or refresh requested for per-call randomness
            if used_role != 'land' and not refresh_requested:
                try:
                    _alts_set_cached(cache_key, html_str)
                except Exception:
                    pass
            return HTMLResponse(html_str)

        # Helper: map display names
        def _display_map_for(lower_pool: set[str]) -> dict[str, str]:
            try:
                return builder_display_map(b, lower_pool)  # type: ignore[arg-type]
            except Exception:
                return {nm: nm for nm in lower_pool}

        # Common exclusions
    # in_deck already computed above

        def _exclude(df0):
            out = df0.copy()
            if "name" in out.columns:
                out["_lname"] = out["name"].astype(str).str.strip().str.lower()
                mask = ~out["_lname"].isin({name_l} | in_deck | locked_set | alts_exclude | ({commander_l} if commander_l else set()))
                out = out[mask]
            return out

        # If we have data and a recognized role, mirror the phase logic
        if df is not None and hasattr(df, "copy") and (used_role in {"ramp","removal","wipe","card_advantage","protection","creature","land"}):
            pool = df.copy()
            try:
                pool["_ltags"] = pool.get("themeTags", []).apply(bu.normalize_tag_cell)
            except Exception:
                # best-effort normalize
                pool["_ltags"] = pool.get("themeTags", []).apply(lambda x: [str(t).strip().lower() for t in (x or [])] if isinstance(x, list) else [])
            # Role-specific base filtering
            if used_role != "land":
                # Exclude lands for non-land roles
                if "type" in pool.columns:
                    pool = pool[~pool["type"].fillna("").str.contains("Land", case=False, na=False)]
            else:
                # Keep only lands
                if "type" in pool.columns:
                    pool = pool[pool["type"].fillna("").str.contains("Land", case=False, na=False)]
                # Seed info to guide filtering
                seed_is_basic = False
                try:
                    seed_is_basic = bool(name_l in {b.strip().lower() for b in getattr(bc, 'BASIC_LANDS', [])})
                except Exception:
                    seed_is_basic = False
                if seed_is_basic:
                    # For basics: show other basics (different colors) to allow quick swaps
                    try:
                        pool = pool[pool['name'].astype(str).str.strip().str.lower().isin({x.lower() for x in getattr(bc, 'BASIC_LANDS', [])})]
                    except Exception:
                        pass
                else:
                    # For non-basics: prefer other non-basics
                    try:
                        pool = pool[~pool['name'].astype(str).str.strip().str.lower().isin({x.lower() for x in getattr(bc, 'BASIC_LANDS', [])})]
                    except Exception:
                        pass
                # Apply mono-color misc land filters (no debug CSV dependency)
                try:
                    colors = list(getattr(b, 'color_identity', []) or [])
                    mono = len(colors) <= 1
                    mono_exclude = {n.lower() for n in getattr(bc, 'MONO_COLOR_MISC_LAND_EXCLUDE', [])}
                    mono_keep = {n.lower() for n in getattr(bc, 'MONO_COLOR_MISC_LAND_KEEP_ALWAYS', [])}
                    kindred_all = {n.lower() for n in getattr(bc, 'KINDRED_ALL_LAND_NAMES', [])}
                    any_color_phrases = [s.lower() for s in getattr(bc, 'ANY_COLOR_MANA_PHRASES', [])]
                    extra_rainbow_terms = [s.lower() for s in getattr(bc, 'MONO_COLOR_RAINBOW_TEXT_EXTRA', [])]
                    fetch_names = set()
                    for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
                        for nm in seq:
                            fetch_names.add(nm.lower())
                    for nm in getattr(bc, 'GENERIC_FETCH_LANDS', []):
                        fetch_names.add(nm.lower())
                    # World Tree check needs all five colors
                    need_all_colors = {'w','u','b','r','g'}
                    def _illegal_world_tree(nm: str) -> bool:
                        return nm == 'the world tree' and set(c.lower() for c in colors) != need_all_colors
                    # Text column fallback
                    text_col = 'text'
                    if text_col not in pool.columns:
                        for c in pool.columns:
                            if 'text' in c.lower():
                                text_col = c
                                break
                    def _exclude_row(row) -> bool:
                        nm_l = str(row['name']).strip().lower()
                        if mono and nm_l in mono_exclude and nm_l not in mono_keep and nm_l not in kindred_all:
                            return True
                        if mono and nm_l not in mono_keep and nm_l not in kindred_all:
                            try:
                                txt = str(row.get(text_col, '') or '').lower()
                                if any(p in txt for p in any_color_phrases + extra_rainbow_terms):
                                    return True
                            except Exception:
                                pass
                        if nm_l in fetch_names:
                            return True
                        if _illegal_world_tree(nm_l):
                            return True
                        return False
                    pool = pool[~pool.apply(_exclude_row, axis=1)]
                except Exception:
                    pass
                # Optional sub-role filtering (only if enough depth)
                try:
                    subrole = str((entry or {}).get('SubRole') or '').strip().lower()
                    if subrole:
                        # Heuristic categories for grouping
                        cat_map = {
                            'fetch': 'fetch',
                            'dual': 'dual',
                            'triple': 'triple',
                            'misc': 'misc',
                            'utility': 'misc',
                            'basic': 'basic'
                        }
                        target_cat = None
                        for key, val in cat_map.items():
                            if key in subrole:
                                target_cat = val
                                break
                        if target_cat and len(pool) > 25:
                            # Lightweight textual filter using known markers
                            def _cat_row(rname: str, rtype: str) -> str:
                                rl = rname.lower()
                                rt = rtype.lower()
                                if any(k in rl for k in ('vista','strand','delta','mire','heath','rainforest','mesa','foothills','catacombs','tarn','flat','expanse','wilds','landscape','tunnel','terrace','vista')):
                                    return 'fetch'
                                if 'triple' in rt or 'three' in rt:
                                    return 'triple'
                                if any(t in rt for t in ('forest','plains','island','swamp','mountain')) and any(sym in rt for sym in ('forest','plains','island','swamp','mountain')) and 'land' in rt:
                                    # Basic-check crude
                                    return 'basic'
                                return 'misc'
                            try:
                                tmp = pool.copy()
                                tmp['_cat'] = tmp.apply(lambda r: _cat_row(str(r.get('name','')), str(r.get('type',''))), axis=1)
                                sub_pool = tmp[tmp['_cat'] == target_cat]
                                if len(sub_pool) >= 10:
                                    pool = sub_pool.drop(columns=['_cat'])
                            except Exception:
                                pass
                except Exception:
                    pass
            # Exclude commander explicitly
            if "name" in pool.columns and commander_l:
                pool = pool[pool["name"].astype(str).str.strip().str.lower() != commander_l]
            # Role-specific filter
            def _is_wipe(tags: list[str]) -> bool:
                return any(("board wipe" in t) or ("mass removal" in t) for t in tags)
            def _is_removal(tags: list[str]) -> bool:
                return any(("removal" in t) or ("spot removal" in t) for t in tags)
            def _is_draw(tags: list[str]) -> bool:
                return any(("draw" in t) or ("card advantage" in t) for t in tags)
            def _matches_selected(tags: list[str]) -> bool:
                try:
                    sel = [str(t).strip().lower() for t in (sess.get("tags") or []) if str(t).strip()]
                    if not sel:
                        return True
                    st = set(sel)
                    return any(any(s in t for s in st) for t in tags)
                except Exception:
                    return True
            if used_role == "ramp":
                pool = pool[pool["_ltags"].apply(lambda tags: any("ramp" in t for t in tags))]
            elif used_role == "removal":
                pool = pool[pool["_ltags"].apply(_is_removal) & ~pool["_ltags"].apply(_is_wipe)]
            elif used_role == "wipe":
                pool = pool[pool["_ltags"].apply(_is_wipe)]
            elif used_role == "card_advantage":
                pool = pool[pool["_ltags"].apply(_is_draw)]
            elif used_role == "protection":
                pool = pool[pool["_ltags"].apply(lambda tags: any("protection" in t for t in tags))]
            elif used_role == "creature":
                # Keep only creatures; bias toward selected theme tags when available
                if "type" in pool.columns:
                    pool = pool[pool["type"].fillna("").str.contains("Creature", case=False, na=False)]
                try:
                    pool = pool[pool["_ltags"].apply(_matches_selected)]
                except Exception:
                    pass
            elif used_role == "land":
                # Already constrained to lands; no additional tag filter needed
                pass
            # Sort by priority like the builder
            try:
                pool = bu.sort_by_priority(pool, ["edhrecRank","manaValue"])  # type: ignore[arg-type]
            except Exception:
                pass
            # Exclusions and ownership (for non-random roles this stays before slicing)
            pool = _exclude(pool)
            try:
                if bool(sess.get("prefer_owned")) and getattr(b, "owned_card_names", None):
                    pool = bu.prefer_owned_first(pool, {str(n).lower() for n in getattr(b, "owned_card_names", set())})
            except Exception:
                pass
            row_meta = _build_meta_map(pool)
            # Land role: random 12 from top 60-100 window
            if used_role == 'land':
                import random as _rnd
                total = len(pool)
                if total == 0:
                    pass
                else:
                    cap = min(100, total)
                    floor = min(60, cap)  # if fewer than 60 just use all
                    if cap <= 12:
                        window_size = cap
                    else:
                        if cap == floor:
                            window_size = cap
                        else:
                            rng_obj = getattr(b, 'rng', None)
                            if rng_obj:
                                window_size = rng_obj.randint(floor, cap)
                            else:
                                window_size = _rnd.randint(floor, cap)
                    window_df = pool.head(window_size)
                    names = window_df['name'].astype(str).str.strip().tolist()
                    # Random sample up to 12 distinct names
                    sample_n = min(12, len(names))
                    if sample_n > 0:
                        if getattr(b, 'rng', None):
                            chosen = getattr(b,'rng').sample(names, sample_n) if len(names) >= sample_n else names
                        else:
                            chosen = _rnd.sample(names, sample_n) if len(names) >= sample_n else names
                        lower_map = {n.strip().lower(): n for n in chosen}
                        display_map = _display_map_for(set(k for k in lower_map.keys()))
                        for nm_lc, orig in lower_map.items():
                            is_owned = (nm_lc in owned_set)
                            if require_owned and not is_owned:
                                continue
                            if nm_lc == name_l or (in_deck and nm_lc in in_deck):
                                continue
                            meta = row_meta.get(nm_lc) or _meta_from_row(None)
                            items.append({
                                'name': display_map.get(nm_lc, orig),
                                'name_lower': nm_lc,
                                'owned': is_owned,
                                'tags': meta.get('tags') or [],
                                'role': meta.get('role', ''),
                                'mana': meta.get('mana', ''),
                                'rarity': meta.get('rarity', ''),
                                'hover_simple': bool(meta.get('hover_simple', True)),
                            })
                if items:
                    return _render_and_cache(items)
            else:
                # Default deterministic top-N (increase to 12 for parity)
                lower_pool: list[str] = []
                try:
                    lower_pool = pool["name"].astype(str).str.strip().str.lower().tolist()
                except Exception:
                    lower_pool = []
                display_map = _display_map_for(set(lower_pool))
                iteration_order = lower_pool
                if refresh_requested and len(lower_pool) > 12:
                    window_size = min(len(lower_pool), 30)
                    window = lower_pool[:window_size]
                    sampled = _sampler(window, min(window_size, 12))
                    seen_sampled = set(sampled)
                    iteration_order = sampled + [nm for nm in lower_pool if nm not in seen_sampled]
                for nm_l in iteration_order:
                    is_owned = (nm_l in owned_set)
                    if require_owned and not is_owned:
                        continue
                    if nm_l == name_l or (in_deck and nm_l in in_deck):
                        continue
                    meta = row_meta.get(nm_l) or _meta_from_row(None)
                    items.append({
                        "name": display_map.get(nm_l, nm_l),
                        "name_lower": nm_l,
                        "owned": is_owned,
                        "tags": meta.get("tags") or [],
                        "role": meta.get("role", ""),
                        "mana": meta.get("mana", ""),
                        "rarity": meta.get("rarity", ""),
                        "hover_simple": bool(meta.get("hover_simple", True)),
                    })
                    if len(items) >= 12:
                        break
                if items:
                    return _render_and_cache(items)

        # Fallback: tag-similarity suggestions (previous behavior)
        tags_idx = getattr(b, "_card_name_tags_index", {}) or {}
        seed_tags = set(tags_idx.get(name_l) or [])
        all_names = set(tags_idx.keys())
        candidates: list[tuple[str, int]] = []  # (name, score)
        for nm in all_names:
            if nm == name_l:
                continue
            if commander_l and nm == commander_l:
                continue
            if in_deck and nm in in_deck:
                continue
            if locked_set and nm in locked_set:
                continue
            if nm in alts_exclude:
                continue
            tgs = set(tags_idx.get(nm) or [])
            score = len(seed_tags & tgs)
            if score <= 0:
                continue
            candidates.append((nm, score))
        # If no tag-based candidates, try shared trigger tag from library entry
        if not candidates and isinstance(entry, dict):
            try:
                trig = str(entry.get("TriggerTag") or "").strip().lower()
            except Exception:
                trig = ""
            if trig:
                for nm, tglist in tags_idx.items():
                    if nm == name_l:
                        continue
                    if nm in {str(k).strip().lower() for k in lib.keys()}:
                        continue
                    if trig in {str(t).strip().lower() for t in (tglist or [])}:
                        candidates.append((nm, 1))
        def _owned(nm: str) -> bool:
            return nm in owned_set
        candidates.sort(key=lambda x: (-x[1], 0 if _owned(x[0]) else 1, x[0]))
        if refresh_requested and len(candidates) > 1:
            name_sequence = [nm for nm, _score in candidates]
            sampled_names = _sampler(name_sequence, min(len(name_sequence), 10))
            sampled_set = set(sampled_names)
            reordered: list[tuple[str, int]] = []
            for nm in sampled_names:
                for cand_nm, cand_score in candidates:
                    if cand_nm == nm:
                        reordered.append((cand_nm, cand_score))
                        break
            for cand_nm, cand_score in candidates:
                if cand_nm not in sampled_set:
                    reordered.append((cand_nm, cand_score))
            candidates = reordered
        pool_lower = {nm for (nm, _s) in candidates}
        display_map = _display_map_for(pool_lower)
        seen = set()
        for nm, score in candidates:
            if nm in seen:
                continue
            seen.add(nm)
            is_owned = (nm in owned_set)
            if require_owned and not is_owned:
                continue
            items.append({
                "name": display_map.get(nm, nm),
                "name_lower": nm,
                "owned": is_owned,
                "tags": list(tags_idx.get(nm) or []),
                "role": "",
                "mana": "",
                "rarity": "",
                "hover_simple": True,
            })
            if len(items) >= 10:
                break
        return _render_and_cache(items)
    except Exception as e:
        return HTMLResponse(f'<div class="alts"><div class="muted">No alternatives: {e}</div></div>')


@router.post("/replace", response_class=HTMLResponse)
async def build_replace(request: Request, old: str = Form(...), new: str = Form(...), owned_only: str = Form("0")) -> HTMLResponse:
    """Inline replace: swap `old` with `new` in the current builder when possible, and suppress `old` from future alternatives.

    Falls back to lock-and-rerun guidance if no active builder is present.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    o_disp = str(old).strip()
    n_disp = str(new).strip()
    o = o_disp.lower()
    n = n_disp.lower()
    owned_only_flag = str(owned_only or "").strip().lower()
    owned_only_int = 1 if owned_only_flag in {"1", "true", "yes", "on"} else 0

    # Maintain locks to bias future picks and enforcement
    locks = set(sess.get("locks", []))
    locks.discard(o)
    locks.add(n)
    sess["locks"] = list(locks)
    # Track last replace for optional undo
    try:
        sess["last_replace"] = {"old": o, "new": n}
    except Exception:
        pass
    ctx = sess.get("build_ctx") or {}
    try:
        ctx["locks"] = {str(x) for x in locks}
    except Exception:
        pass
    # Record preferred replacements
    try:
        pref = ctx.get("preferred_replacements") if isinstance(ctx, dict) else None
        if not isinstance(pref, dict):
            pref = {}
            ctx["preferred_replacements"] = pref
        pref[o] = n
    except Exception:
        pass
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if b is not None:
        try:
            lib = getattr(b, "card_library", {}) or {}
            # Find the exact key for `old` in a case-insensitive manner
            old_key = None
            if o_disp in lib:
                old_key = o_disp
            else:
                for k in list(lib.keys()):
                    if str(k).strip().lower() == o:
                        old_key = k
                        break
            if old_key is None:
                raise KeyError("old card not in deck")
            old_info = dict(lib.get(old_key) or {})
            role = str(old_info.get("Role") or "").strip()
            subrole = str(old_info.get("SubRole") or "").strip()
            try:
                count = int(old_info.get("Count", 1))
            except Exception:
                count = 1
            # Remove old entry
            try:
                del lib[old_key]
            except Exception:
                pass
            # Resolve canonical name and info for new
            df = getattr(b, "_combined_cards_df", None)
            new_key = n_disp
            card_type = ""
            mana_cost = ""
            trigger_tag = str(old_info.get("TriggerTag") or "")
            if df is not None:
                try:
                    row = df[df["name"].astype(str).str.strip().str.lower() == n]
                    if not row.empty:
                        new_key = str(row.iloc[0]["name"]) or n_disp
                        card_type = str(row.iloc[0].get("type", row.iloc[0].get("type_line", "")) or "")
                        mana_cost = str(row.iloc[0].get("mana_cost", row.iloc[0].get("manaCost", "")) or "")
                except Exception:
                    pass
            lib[new_key] = {
                "Count": count,
                "Card Type": card_type,
                "Mana Cost": mana_cost,
                "Role": role,
                "SubRole": subrole,
                "AddedBy": "Replace",
                "TriggerTag": trigger_tag,
            }
            # Mirror preferred replacements onto the builder for enforcement
            try:
                cur = getattr(b, "preferred_replacements", {}) or {}
                cur[str(o)] = str(n)
                setattr(b, "preferred_replacements", cur)
            except Exception:
                pass
            # Update alternatives exclusion set and bump version to invalidate caches
            try:
                ex = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
                ex.add(o)
                sess["alts_exclude"] = list(ex)
                sess["alts_exclude_v"] = int(sess.get("alts_exclude_v") or 0) + 1
            except Exception:
                pass
            # Success panel and OOB updates (refresh compliance panel)
            # Compute ownership of the new card for UI badge update
            is_owned = (n in owned_set_helper())
            refresh = (
                '<div hx-get="/build/alternatives?name='
                + quote_plus(new_key)
                + f'&owned_only={owned_only_int}" hx-trigger="load delay:80ms" '
                'hx-target="closest .alts" hx-swap="outerHTML" aria-hidden="true"></div>'
            )
            html = (
                '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
                f'<div>Replaced <strong>{o_disp}</strong> with <strong>{new_key}</strong>.</div>'
                '<div class="muted" style="margin-top:.35rem;">Compliance panel will refresh.</div>'
                '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
                '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
                '</div>'
                + refresh +
                '</div>'
            )
            # Inline mutate the nearest card tile to reflect the new card without a rerun
            mutator = """
<script>
(function(){
    try{
        var panel = document.currentScript && document.currentScript.previousElementSibling && document.currentScript.previousElementSibling.classList && document.currentScript.previousElementSibling.classList.contains('alts') ? document.currentScript.previousElementSibling : null;
        if(!panel){ return; }
        var oldName = panel.getAttribute('data-old') || '';
        var newName = panel.getAttribute('data-new') || '';
        var isOwned = panel.getAttribute('data-owned') === '1';
        var isLocked = panel.getAttribute('data-locked') === '1';
        var tile = panel.closest('.card-tile');
        if(!tile) return;
        tile.setAttribute('data-card-name', newName);
        var img = tile.querySelector('img.card-thumb');
        if(img){
            var base = 'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=';
            img.src = base + 'normal';
            img.setAttribute('srcset',
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=small 160w, ' +
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=normal 488w, ' +
                'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(newName) + '&format=image&version=large 672w'
            );
            img.setAttribute('alt', newName + ' image');
            img.setAttribute('data-card-name', newName);
        }
        var nameEl = tile.querySelector('.name');
        if(nameEl){ nameEl.textContent = newName; }
        var own = tile.querySelector('.owned-badge');
        if(own){
            own.textContent = isOwned ? '✔' : '✖';
            own.title = isOwned ? 'Owned' : 'Not owned';
            tile.setAttribute('data-owned', isOwned ? '1' : '0');
        }
        tile.classList.toggle('locked', isLocked);
        var imgBtn = tile.querySelector('.img-btn');
        if(imgBtn){
            try{
                var valsAttr = imgBtn.getAttribute('hx-vals') || '{}';
                var obj = JSON.parse(valsAttr.replace(/&quot;/g, '"'));
                obj.name = newName;
                imgBtn.setAttribute('hx-vals', JSON.stringify(obj));
            }catch(e){}
        }
        var lockBtn = tile.querySelector('.lock-box .btn-lock');
        if(lockBtn){
            try{
                var v = lockBtn.getAttribute('hx-vals') || '{}';
                var o = JSON.parse(v.replace(/&quot;/g, '"'));
                o.name = newName;
                lockBtn.setAttribute('hx-vals', JSON.stringify(o));
            }catch(e){}
        }
    }catch(_){}
})();
</script>
"""
            chip = (
                f'<div id="last-action" hx-swap-oob="true">'
                f'<span class="chip" title="Click to dismiss">Replaced <strong>{o_disp}</strong> → <strong>{new_key}</strong></span>'
                f'</div>'
            )
            # OOB fetch to refresh compliance panel
            refresher = (
                '<div hx-get="/build/compliance" hx-target="#compliance-panel" hx-swap="outerHTML" '
                'hx-trigger="load" hx-swap-oob="true"></div>'
            )
            # Include data attributes on the panel div for the mutator script
            data_owned = '1' if is_owned else '0'
            data_locked = '1' if (n in locks) else '0'
            prefix = '<div class="alts"'
            replacement = (
                '<div class="alts" ' 
                + 'data-old="' + _esc(o_disp) + '" ' 
                + 'data-new="' + _esc(new_key) + '" '
                + 'data-owned="' + data_owned + '" '
                + 'data-locked="' + data_locked + '"'
            )
            html = html.replace(prefix, replacement, 1)
            return HTMLResponse(html + mutator + chip + refresher)
        except Exception:
            # Fall back to rerun guidance if inline swap fails
            pass
    # Fallback: advise rerun
    hint = (
        '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
        f'<div>Locked <strong>{new}</strong> and unlocked <strong>{old}</strong>.</div>'
        '<div class="muted" style="margin-top:.35rem;">Now click <em>Rerun Stage</em> with Replace: On to apply this change.</div>'
        '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
        '<form hx-post="/build/step5/rerun" hx-target="#wizard" hx-swap="innerHTML" style="display:inline;">'
        '<input type="hidden" name="show_skipped" value="1" />'
        '<button type="submit" class="btn-rerun">Rerun stage</button>'
        '</form>'
        '<form hx-post="/build/replace/undo" hx-target="closest .alts" hx-swap="outerHTML" style="display:inline; margin:0;">'
        f'<input type="hidden" name="old" value="{old}" />'
        f'<input type="hidden" name="new" value="{new}" />'
        '<button type="submit" class="btn" title="Undo this replace">Undo</button>'
        '</form>'
        '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
        '</div>'
        '</div>'
    )
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">Replaced <strong>{old}</strong> → <strong>{new}</strong></span>'
        f'</div>'
    )
    # Also add old to exclusions and bump version for future alt calls
    try:
        ex = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
        ex.add(o)
        sess["alts_exclude"] = list(ex)
        sess["alts_exclude_v"] = int(sess.get("alts_exclude_v") or 0) + 1
    except Exception:
        pass
    return HTMLResponse(hint + chip)


@router.post("/replace/undo", response_class=HTMLResponse)
async def build_replace_undo(request: Request, old: str = Form(None), new: str = Form(None)) -> HTMLResponse:
    """Undo the last replace by restoring the previous lock state (best-effort)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    last = sess.get("last_replace") or {}
    try:
        # Prefer provided args, else fallback to last recorded
        o = (str(old).strip().lower() if old else str(last.get("old") or "")).strip()
        n = (str(new).strip().lower() if new else str(last.get("new") or "")).strip()
    except Exception:
        o, n = "", ""
    locks = set(sess.get("locks", []))
    changed = False
    if n and n in locks:
        locks.discard(n)
        changed = True
    if o:
        locks.add(o)
        changed = True
    sess["locks"] = list(locks)
    if sess.get("build_ctx"):
        try:
            sess["build_ctx"]["locks"] = {str(x) for x in locks}
        except Exception:
            pass
    # Clear last_replace after undo
    try:
        if sess.get("last_replace"):
            del sess["last_replace"]
    except Exception:
        pass
    # Return confirmation panel and OOB chip
    msg = 'Undid replace' if changed else 'No changes to undo'
    html = (
        '<div class="alts" style="margin-top:.35rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; background:#0f1115;">'
        f'<div>{msg}.</div>'
        '<div class="muted" style="margin-top:.35rem;">Rerun the stage to recompute picks if needed.</div>'
        '<div style="margin-top:.35rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">'
        '<form hx-post="/build/step5/rerun" hx-target="#wizard" hx-swap="innerHTML" style="display:inline;">'
        '<input type="hidden" name="show_skipped" value="1" />'
        '<button type="submit" class="btn-rerun">Rerun stage</button>'
        '</form>'
        '<button type="button" class="btn" onclick="try{this.closest(\'.alts\').remove();}catch(_){}">Close</button>'
        '</div>'
        '</div>'
    )
    chip = (
        f'<div id="last-action" hx-swap-oob="true">'
        f'<span class="chip" title="Click to dismiss">{msg}</span>'
        f'</div>'
    )
    return HTMLResponse(html + chip)


@router.get("/compare")
async def build_compare(runA: str, runB: str):
    """Stub: return empty diffs; later we can diff summary files under deck_files."""
    return JSONResponse({"ok": True, "added": [], "removed": [], "changed": []})


@router.get("/compliance", response_class=HTMLResponse)
async def build_compliance_panel(request: Request) -> HTMLResponse:
    """Render a live Bracket compliance panel with manual enforcement controls.

    Computes compliance against the current builder state without exporting, attaches a non-destructive
    enforcement plan (swaps with added=None) when FAIL, and returns a reusable HTML partial.
    Returns empty content when no active build context exists.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        return HTMLResponse("")
    # Compute compliance snapshot in-memory and attach planning preview
    comp = None
    try:
        if hasattr(b, 'compute_and_print_compliance'):
            comp = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
    except Exception:
        comp = None
    try:
        if comp:
            from ..services import orchestrator as orch
            comp = orch._attach_enforcement_plan(b, comp)  # type: ignore[attr-defined]
    except Exception:
        pass
    if not comp:
        return HTMLResponse("")
    # Build flagged metadata (role, owned) for visual tiles and role-aware alternatives
    # For combo violations, expand pairs into individual cards (exclude commander) so each can be replaced.
    flagged_meta: list[dict] = []
    try:
        cats = comp.get('categories') or {}
        owned_lower = owned_set_helper()
        lib = getattr(b, 'card_library', {}) or {}
        commander_l = str((sess.get('commander') or '')).strip().lower()
        # map category key -> display label
        labels = {
            'game_changers': 'Game Changers',
            'extra_turns': 'Extra Turns',
            'mass_land_denial': 'Mass Land Denial',
            'tutors_nonland': 'Nonland Tutors',
            'two_card_combos': 'Two-Card Combos',
        }
        seen_lower: set[str] = set()
        for key, cat in cats.items():
            try:
                status = str(cat.get('status') or '').upper()
                # Only surface tiles for WARN and FAIL
                if status not in {"WARN", "FAIL"}:
                    continue
                # For two-card combos, split pairs into individual cards and skip commander
                if key == 'two_card_combos' and status == 'FAIL':
                    # Prefer the structured combos list to ensure we only expand counted pairs
                    pairs = []
                    try:
                        for p in (comp.get('combos') or []):
                            if p.get('cheap_early'):
                                pairs.append((str(p.get('a') or '').strip(), str(p.get('b') or '').strip()))
                    except Exception:
                        pairs = []
                    # Fallback to parsing flagged strings like "A + B"
                    if not pairs:
                        try:
                            for s in (cat.get('flagged') or []):
                                if not isinstance(s, str):
                                    continue
                                parts = [x.strip() for x in s.split('+') if x and x.strip()]
                                if len(parts) == 2:
                                    pairs.append((parts[0], parts[1]))
                        except Exception:
                            pass
                    for a, bname in pairs:
                        for nm in (a, bname):
                            if not nm:
                                continue
                            nm_l = nm.strip().lower()
                            if nm_l == commander_l:
                                # Don't prompt replacing the commander
                                continue
                            if nm_l in seen_lower:
                                continue
                            seen_lower.add(nm_l)
                            entry = lib.get(nm) or lib.get(nm_l) or lib.get(str(nm).strip()) or {}
                            role = entry.get('Role') or ''
                            flagged_meta.append({
                                'name': nm,
                                'category': labels.get(key, key.replace('_',' ').title()),
                                'role': role,
                                'owned': (nm_l in owned_lower),
                                'severity': status,
                            })
                    continue
                # Default handling for list/tag categories
                names = [n for n in (cat.get('flagged') or []) if isinstance(n, str)]
                for nm in names:
                    nm_l = str(nm).strip().lower()
                    if nm_l in seen_lower:
                        continue
                    seen_lower.add(nm_l)
                    entry = lib.get(nm) or lib.get(str(nm).strip()) or lib.get(nm_l) or {}
                    role = entry.get('Role') or ''
                    flagged_meta.append({
                        'name': nm,
                        'category': labels.get(key, key.replace('_',' ').title()),
                        'role': role,
                        'owned': (nm_l in owned_lower),
                        'severity': status,
                    })
            except Exception:
                continue
    except Exception:
        flagged_meta = []
    # Render partial
    ctx2 = {"request": request, "compliance": comp, "flagged_meta": flagged_meta}
    return templates.TemplateResponse("build/_compliance_panel.html", ctx2)


@router.post("/enforce/apply", response_class=HTMLResponse)
async def build_enforce_apply(request: Request) -> HTMLResponse:
    """Apply bracket enforcement now using current locks as user guidance.

    This adds lock placeholders if needed, runs enforcement + re-export, reloads compliance, and re-renders Step 5.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Ensure build context exists
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        # No active build: show Step 5 with an error
        err_ctx = step5_error_ctx(request, sess, "No active build context to enforce.")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Ensure we have a CSV base stem for consistent re-exports
    base_stem = None
    try:
        csv_path = ctx.get("csv_path")
        if isinstance(csv_path, str) and csv_path:
            import os as _os
            base_stem = _os.path.splitext(_os.path.basename(csv_path))[0]
    except Exception:
        base_stem = None
    # If missing, export once to establish base
    if not base_stem:
        try:
            ctx["csv_path"] = b.export_decklist_csv()  # type: ignore[attr-defined]
            import os as _os
            base_stem = _os.path.splitext(_os.path.basename(ctx["csv_path"]))[0]
            # Also produce a text export for completeness
            ctx["txt_path"] = b.export_decklist_text(filename=base_stem + '.txt')  # type: ignore[attr-defined]
        except Exception:
            base_stem = None
    # Add lock placeholders into the library before enforcement so user choices are present
    try:
        locks = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        if locks:
            df = getattr(b, "_combined_cards_df", None)
            lib_l = {str(n).strip().lower() for n in getattr(b, 'card_library', {}).keys()}
            for lname in locks:
                if lname in lib_l:
                    continue
                target_name = None
                card_type = ''
                mana_cost = ''
                try:
                    if df is not None and not df.empty:
                        row = df[df['name'].astype(str).str.lower() == lname]
                        if not row.empty:
                            target_name = str(row.iloc[0]['name'])
                            card_type = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                            mana_cost = str(row.iloc[0].get('mana_cost', row.iloc[0].get('manaCost', '')) or '')
                except Exception:
                    target_name = None
                if target_name:
                    b.card_library[target_name] = {
                        'Count': 1,
                        'Card Type': card_type,
                        'Mana Cost': mana_cost,
                        'Role': 'Locked',
                        'SubRole': '',
                        'AddedBy': 'Lock',
                        'TriggerTag': '',
                    }
    except Exception:
        pass
    # Thread preferred replacements from context onto builder so enforcement can honor them
    try:
        pref = ctx.get("preferred_replacements") if isinstance(ctx, dict) else None
        if isinstance(pref, dict):
            setattr(b, 'preferred_replacements', dict(pref))
    except Exception:
        pass
    # Run enforcement + re-exports (tops up to 100 internally)
    try:
        rep = b.enforce_and_reexport(base_stem=base_stem, mode='auto')  # type: ignore[attr-defined]
    except Exception as e:
        err_ctx = step5_error_ctx(request, sess, f"Enforcement failed: {e}")
        resp = templates.TemplateResponse("build/_step5.html", err_ctx)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Reload compliance JSON and summary
    compliance = None
    try:
        if base_stem:
            import os as _os
            import json as _json
            comp_path = _os.path.join('deck_files', f"{base_stem}_compliance.json")
            if _os.path.exists(comp_path):
                with open(comp_path, 'r', encoding='utf-8') as _cf:
                    compliance = _json.load(_cf)
    except Exception:
        compliance = None
    # Rebuild Step 5 context (done state)
    # Ensure csv/txt paths on ctx reflect current base
    try:
        import os as _os
        ctx["csv_path"] = _os.path.join('deck_files', f"{base_stem}.csv") if base_stem else ctx.get("csv_path")
        ctx["txt_path"] = _os.path.join('deck_files', f"{base_stem}.txt") if base_stem else ctx.get("txt_path")
    except Exception:
        pass
    # Compute total_cards
    try:
        total_cards = 0
        for _n, _e in getattr(b, 'card_library', {}).items():
            try:
                total_cards += int(_e.get('Count', 1))
            except Exception:
                total_cards += 1
    except Exception:
        total_cards = None
    res = {
        "done": True,
        "label": "Complete",
        "log_delta": "",
        "idx": len(ctx.get("stages", []) or []),
        "total": len(ctx.get("stages", []) or []),
        "csv_path": ctx.get("csv_path"),
        "txt_path": ctx.get("txt_path"),
        "summary": getattr(b, 'build_deck_summary', lambda: None)(),
        "total_cards": total_cards,
        "added_total": 0,
        "compliance": compliance or rep,
    }
    page_ctx = step5_ctx_from_result(request, sess, res, status_text="Build complete", show_skipped=True)
    resp = templates.TemplateResponse(request, "build/_step5.html", page_ctx)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/enforcement", response_class=HTMLResponse)
async def build_enforcement_fullpage(request: Request) -> HTMLResponse:
    """Full-page enforcement review: show compliance panel with swaps and controls."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b: DeckBuilder | None = ctx.get("builder") if isinstance(ctx, dict) else None
    if not b:
        # No active build
        base = step5_empty_ctx(request, sess)
        resp = templates.TemplateResponse("build/_step5.html", base)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Compute compliance snapshot and attach planning preview
    comp = None
    try:
        if hasattr(b, 'compute_and_print_compliance'):
            comp = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
    except Exception:
        comp = None
    try:
        if comp:
            from ..services import orchestrator as orch
            comp = orch._attach_enforcement_plan(b, comp)  # type: ignore[attr-defined]
    except Exception:
        pass
    ctx2 = {"request": request, "compliance": comp}
    resp = templates.TemplateResponse(request, "build/enforcement.html", ctx2)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/permalink")
async def build_permalink(request: Request):
    """Return a URL-safe JSON payload representing current run config (basic)."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    payload = {
        "commander": sess.get("commander"),
        "tags": sess.get("tags", []),
        "bracket": sess.get("bracket"),
        "ideals": sess.get("ideals"),
        "tag_mode": sess.get("tag_mode", "AND"),
        "flags": {
            "owned_only": bool(sess.get("use_owned_only")),
            "prefer_owned": bool(sess.get("prefer_owned")),
            "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        },
        "locks": list(sess.get("locks", [])),
    }
    # Optional: random build fields (if present in session)
    try:
        rb = sess.get("random_build") or {}
        if rb:
            # Only include known keys to avoid leaking unrelated session data
            inc: dict[str, Any] = {}
            for key in ("seed", "theme", "constraints", "primary_theme", "secondary_theme", "tertiary_theme"):
                if rb.get(key) is not None:
                    inc[key] = rb.get(key)
            resolved_list = rb.get("resolved_themes")
            if isinstance(resolved_list, list):
                inc["resolved_themes"] = list(resolved_list)
            resolved_info = rb.get("resolved_theme_info")
            if isinstance(resolved_info, dict):
                inc["resolved_theme_info"] = dict(resolved_info)
            if rb.get("combo_fallback") is not None:
                inc["combo_fallback"] = bool(rb.get("combo_fallback"))
            if rb.get("synergy_fallback") is not None:
                inc["synergy_fallback"] = bool(rb.get("synergy_fallback"))
            if rb.get("fallback_reason") is not None:
                inc["fallback_reason"] = rb.get("fallback_reason")
            requested = rb.get("requested_themes")
            if isinstance(requested, dict):
                inc["requested_themes"] = dict(requested)
            if rb.get("auto_fill_enabled") is not None:
                inc["auto_fill_enabled"] = bool(rb.get("auto_fill_enabled"))
            if rb.get("auto_fill_applied") is not None:
                inc["auto_fill_applied"] = bool(rb.get("auto_fill_applied"))
            auto_filled = rb.get("auto_filled_themes")
            if isinstance(auto_filled, list):
                inc["auto_filled_themes"] = list(auto_filled)
            display = rb.get("display_themes")
            if isinstance(display, list):
                inc["display_themes"] = list(display)
            if inc:
                payload["random"] = inc
    except Exception:
        pass
    
    # Add include/exclude cards and advanced options if feature is enabled
    if ALLOW_MUST_HAVES:
        if sess.get("include_cards"):

            
            payload["include_cards"] = sess.get("include_cards")
        if sess.get("exclude_cards"):
            payload["exclude_cards"] = sess.get("exclude_cards")
        if sess.get("enforcement_mode"):
            payload["enforcement_mode"] = sess.get("enforcement_mode")
        if sess.get("allow_illegal") is not None:
            payload["allow_illegal"] = sess.get("allow_illegal")
        if sess.get("fuzzy_matching") is not None:
            payload["fuzzy_matching"] = sess.get("fuzzy_matching")
    try:
        import base64
        import json as _json
        raw = _json.dumps(payload, separators=(",", ":"))
        token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        # Also include decoded state for convenience/testing
        return JSONResponse({"ok": True, "permalink": f"/build/from?state={token}", "state": payload})
    except Exception:
        return JSONResponse({"ok": True, "state": payload})


@router.get("/from", response_class=HTMLResponse)
async def build_from(request: Request, state: str | None = None) -> HTMLResponse:
    """Load a run from a permalink token."""
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if state:
        try:
            import base64
            import json as _json
            pad = '=' * (-len(state) % 4)
            raw = base64.urlsafe_b64decode((state + pad).encode("ascii")).decode("utf-8")
            data = _json.loads(raw)
            sess["commander"] = data.get("commander")
            sess["tags"] = data.get("tags", [])
            sess["bracket"] = data.get("bracket")
            if data.get("ideals"):
                sess["ideals"] = data.get("ideals")
            sess["tag_mode"] = data.get("tag_mode", "AND")
            flags = data.get("flags") or {}
            sess["use_owned_only"] = bool(flags.get("owned_only"))
            sess["prefer_owned"] = bool(flags.get("prefer_owned"))
            sess["swap_mdfc_basics"] = bool(flags.get("swap_mdfc_basics"))
            sess["locks"] = list(data.get("locks", []))
            # Optional random build rehydration
            try:
                r = data.get("random") or {}
                if r:
                    rb_payload: dict[str, Any] = {}
                    for key in ("seed", "theme", "constraints", "primary_theme", "secondary_theme", "tertiary_theme"):
                        if r.get(key) is not None:
                            rb_payload[key] = r.get(key)
                    if isinstance(r.get("resolved_themes"), list):
                        rb_payload["resolved_themes"] = list(r.get("resolved_themes") or [])
                    if isinstance(r.get("resolved_theme_info"), dict):
                        rb_payload["resolved_theme_info"] = dict(r.get("resolved_theme_info"))
                    if r.get("combo_fallback") is not None:
                        rb_payload["combo_fallback"] = bool(r.get("combo_fallback"))
                    if r.get("synergy_fallback") is not None:
                        rb_payload["synergy_fallback"] = bool(r.get("synergy_fallback"))
                    if r.get("fallback_reason") is not None:
                        rb_payload["fallback_reason"] = r.get("fallback_reason")
                    if isinstance(r.get("requested_themes"), dict):
                        requested_payload = dict(r.get("requested_themes"))
                        if "auto_fill_enabled" in requested_payload:
                            requested_payload["auto_fill_enabled"] = bool(requested_payload.get("auto_fill_enabled"))
                        rb_payload["requested_themes"] = requested_payload
                    if r.get("auto_fill_enabled") is not None:
                        rb_payload["auto_fill_enabled"] = bool(r.get("auto_fill_enabled"))
                    if r.get("auto_fill_applied") is not None:
                        rb_payload["auto_fill_applied"] = bool(r.get("auto_fill_applied"))
                    auto_filled = r.get("auto_filled_themes")
                    if isinstance(auto_filled, list):
                        rb_payload["auto_filled_themes"] = list(auto_filled)
                    display = r.get("display_themes")
                    if isinstance(display, list):
                        rb_payload["display_themes"] = list(display)
                    if "seed" in rb_payload:
                        try:
                            seed_int = int(rb_payload["seed"])
                            rb_payload["seed"] = seed_int
                            rb_payload.setdefault("recent_seeds", [seed_int])
                        except Exception:
                            rb_payload.setdefault("recent_seeds", [])
                    sess["random_build"] = rb_payload
            except Exception:
                pass
            
            # Import exclude_cards if feature is enabled and present
            if ALLOW_MUST_HAVES and data.get("exclude_cards"):
                sess["exclude_cards"] = data.get("exclude_cards")
                
            sess["last_step"] = 4
        except Exception:
            pass
    locks_restored = 0
    try:
        locks_restored = len(sess.get("locks", []) or [])
    except Exception:
        locks_restored = 0
    resp = templates.TemplateResponse(request, "build/_step4.html", {
        "labels": orch.ideal_labels(),
        "values": sess.get("ideals") or orch.ideal_defaults(),
        "commander": sess.get("commander"),
        "owned_only": bool(sess.get("use_owned_only")),
        "prefer_owned": bool(sess.get("prefer_owned")),
        "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        "locks_restored": locks_restored,
    })
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/validate/exclude_cards")
async def validate_exclude_cards(
    request: Request,
    exclude_cards: str = Form(default=""),
    commander: str = Form(default="")
):
    """Legacy exclude cards validation endpoint - redirect to new unified endpoint."""
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Feature not enabled"}, status_code=404)
    
    # Call new unified endpoint
    result = await validate_include_exclude_cards(
        request=request,
        include_cards="",
        exclude_cards=exclude_cards,
        commander=commander,
        enforcement_mode="warn",
        allow_illegal=False,
        fuzzy_matching=True
    )
    
    # Transform to legacy format for backward compatibility
    if hasattr(result, 'body'):
        import json
        data = json.loads(result.body)
        if 'excludes' in data:
            excludes = data['excludes']
            return JSONResponse({
                "count": excludes.get("count", 0),
                "limit": excludes.get("limit", 15),
                "over_limit": excludes.get("over_limit", False),
                "cards": excludes.get("cards", []),
                "duplicates": excludes.get("duplicates", {}),
                "warnings": excludes.get("warnings", [])
            })
    
    return result


@router.post("/validate/include_exclude")
async def validate_include_exclude_cards(
    request: Request,
    include_cards: str = Form(default=""),
    exclude_cards: str = Form(default=""),
    commander: str = Form(default=""),
    enforcement_mode: str = Form(default="warn"),
    allow_illegal: bool = Form(default=False),
    fuzzy_matching: bool = Form(default=True)
):
    """Validate include/exclude card lists with comprehensive diagnostics."""
    if not ALLOW_MUST_HAVES:
        return JSONResponse({"error": "Feature not enabled"}, status_code=404)
    
    try:
        from deck_builder.include_exclude_utils import (
            parse_card_list_input, collapse_duplicates,
            fuzzy_match_card_name, MAX_INCLUDES, MAX_EXCLUDES
        )
        from deck_builder.builder import DeckBuilder
        
        # Parse inputs
        include_list = parse_card_list_input(include_cards) if include_cards.strip() else []
        exclude_list = parse_card_list_input(exclude_cards) if exclude_cards.strip() else []
        
        # Collapse duplicates
        include_unique, include_dupes = collapse_duplicates(include_list)
        exclude_unique, exclude_dupes = collapse_duplicates(exclude_list)
        
        # Initialize result structure
        result = {
            "includes": {
                "count": len(include_unique),
                "limit": MAX_INCLUDES,
                "over_limit": len(include_unique) > MAX_INCLUDES,
                "duplicates": include_dupes,
                "cards": include_unique[:10] if len(include_unique) <= 10 else include_unique[:7] + ["..."],
                "warnings": [],
                "legal": [],
                "illegal": [],
                "color_mismatched": [],
                "fuzzy_matches": {}
            },
            "excludes": {
                "count": len(exclude_unique),
                "limit": MAX_EXCLUDES,
                "over_limit": len(exclude_unique) > MAX_EXCLUDES,
                "duplicates": exclude_dupes,
                "cards": exclude_unique[:10] if len(exclude_unique) <= 10 else exclude_unique[:7] + ["..."],
                "warnings": [],
                "legal": [],
                "illegal": [],
                "fuzzy_matches": {}
            },
            "conflicts": [],  # Cards that appear in both lists
            "confirmation_needed": [],  # Cards needing fuzzy match confirmation
            "overall_warnings": []
        }
        
        # Check for conflicts (cards in both lists)
        conflicts = set(include_unique) & set(exclude_unique)
        if conflicts:
            result["conflicts"] = list(conflicts)
            result["overall_warnings"].append(f"Cards appear in both lists: {', '.join(list(conflicts)[:3])}{'...' if len(conflicts) > 3 else ''}")
        
        # Size warnings based on actual counts
        if result["includes"]["over_limit"]:
            result["includes"]["warnings"].append(f"Too many includes: {len(include_unique)}/{MAX_INCLUDES}")
        elif len(include_unique) > MAX_INCLUDES * 0.8:  # 80% capacity warning
            result["includes"]["warnings"].append(f"Approaching limit: {len(include_unique)}/{MAX_INCLUDES}")
            
        if result["excludes"]["over_limit"]:
            result["excludes"]["warnings"].append(f"Too many excludes: {len(exclude_unique)}/{MAX_EXCLUDES}")
        elif len(exclude_unique) > MAX_EXCLUDES * 0.8:  # 80% capacity warning
            result["excludes"]["warnings"].append(f"Approaching limit: {len(exclude_unique)}/{MAX_EXCLUDES}")
        
        # If we have a commander, do advanced validation (color identity, etc.)
        if commander and commander.strip():
            try:
                # Create a temporary builder
                builder = DeckBuilder()
                
                # Set up commander FIRST (before setup_dataframes)
                df = builder.load_commander_data()
                commander_rows = df[df["name"] == commander.strip()]
                
                if not commander_rows.empty:
                    # Apply commander selection (this sets commander_row properly)
                    builder._apply_commander_selection(commander_rows.iloc[0])
                
                # Now setup dataframes (this will use the commander info)
                builder.setup_dataframes()
                
                # Get available card names for fuzzy matching
                name_col = 'name' if 'name' in builder._full_cards_df.columns else 'Name'
                available_cards = set(builder._full_cards_df[name_col].tolist())
                
                # Validate includes with fuzzy matching
                for card_name in include_unique:
                    if fuzzy_matching:
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["includes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["includes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "include"
                                })
                        else:
                            result["includes"]["illegal"].append(card_name)
                    else:
                        # Exact match only
                        if card_name in available_cards:
                            result["includes"]["legal"].append(card_name)
                        else:
                            result["includes"]["illegal"].append(card_name)
                
                # Validate excludes with fuzzy matching
                for card_name in exclude_unique:
                    if fuzzy_matching:
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["excludes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["excludes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "exclude"
                                })
                        else:
                            result["excludes"]["illegal"].append(card_name)
                    else:
                        # Exact match only
                        if card_name in available_cards:
                            result["excludes"]["legal"].append(card_name)
                        else:
                            result["excludes"]["illegal"].append(card_name)
                
                # Color identity validation for includes (only if we have a valid commander with colors)
                commander_colors = getattr(builder, 'color_identity', [])
                if commander_colors:
                    color_validated_includes = []
                    for card_name in result["includes"]["legal"]:
                        if builder._validate_card_color_identity(card_name):
                            color_validated_includes.append(card_name)
                        else:
                            # Add color-mismatched cards to illegal instead of separate category
                            result["includes"]["illegal"].append(card_name)
                    
                    # Update legal includes to only those that pass color identity
                    result["includes"]["legal"] = color_validated_includes
                            
            except Exception as validation_error:
                # Advanced validation failed, but return basic validation
                result["overall_warnings"].append(f"Advanced validation unavailable: {str(validation_error)}")
        else:
            # No commander provided, do basic fuzzy matching only
            if fuzzy_matching and (include_unique or exclude_unique):
                try:
                    # Use cached available cards set (1st call populates cache)
                    available_cards = _available_cards()
                    
                    # Fast path: normalized exact matches via cached sets
                    norm_set, norm_map = _available_cards_normalized()
                    # Validate includes with fuzzy matching
                    for card_name in include_unique:
                        from deck_builder.include_exclude_utils import normalize_punctuation
                        n = normalize_punctuation(card_name)
                        if n in norm_set:
                            result["includes"]["fuzzy_matches"][card_name] = norm_map[n]
                            result["includes"]["legal"].append(norm_map[n])
                            continue
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        
                        if match_result.matched_name and match_result.auto_accepted:
                            # Exact or high-confidence match
                            result["includes"]["fuzzy_matches"][card_name] = match_result.matched_name
                            result["includes"]["legal"].append(match_result.matched_name)
                        elif not match_result.auto_accepted and match_result.suggestions:
                            # Needs confirmation - has suggestions but low confidence
                            result["confirmation_needed"].append({
                                "input": card_name,
                                "suggestions": match_result.suggestions,
                                "confidence": match_result.confidence,
                                "type": "include"
                            })
                        else:
                            # No match found at all, add to illegal
                            result["includes"]["illegal"].append(card_name)
                    # Validate excludes with fuzzy matching
                    for card_name in exclude_unique:
                        from deck_builder.include_exclude_utils import normalize_punctuation
                        n = normalize_punctuation(card_name)
                        if n in norm_set:
                            result["excludes"]["fuzzy_matches"][card_name] = norm_map[n]
                            result["excludes"]["legal"].append(norm_map[n])
                            continue
                        match_result = fuzzy_match_card_name(card_name, available_cards)
                        if match_result.matched_name:
                            if match_result.auto_accepted:
                                result["excludes"]["fuzzy_matches"][card_name] = match_result.matched_name
                                result["excludes"]["legal"].append(match_result.matched_name)
                            else:
                                # Needs confirmation
                                result["confirmation_needed"].append({
                                    "input": card_name,
                                    "suggestions": match_result.suggestions,
                                    "confidence": match_result.confidence,
                                    "type": "exclude"
                                })
                        else:
                            # No match found, add to illegal
                            result["excludes"]["illegal"].append(card_name)
                            
                except Exception as fuzzy_error:
                    result["overall_warnings"].append(f"Fuzzy matching unavailable: {str(fuzzy_error)}")
        
        return JSONResponse(result)
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
