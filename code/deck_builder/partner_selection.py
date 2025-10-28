"""Helpers for applying partner/background inputs to a deck build."""
from __future__ import annotations

import ast
from types import SimpleNamespace
from typing import Any

from exceptions import CommanderPartnerError
from deck_builder.background_loader import load_background_cards
from deck_builder.combined_commander import (
    CombinedCommander,
    PartnerMode,
    build_combined_commander,
)
from logging_util import get_logger

logger = get_logger(__name__)

try:  # Optional pandas import for type checking without heavy dependency at runtime.
    import pandas as _pd  # type: ignore
except Exception:  # pragma: no cover - tests provide DataFrame-like objects.
    _pd = None  # type: ignore

__all__ = ["apply_partner_inputs", "normalize_lookup_name"]


def normalize_lookup_name(value: str | None) -> str:
    """Normalize a commander/background name for case-insensitive lookups."""

    return str(value or "").strip().casefold()


def apply_partner_inputs(
    builder: Any,
    *,
    primary_name: str,
    secondary_name: str | None = None,
    background_name: str | None = None,
    feature_enabled: bool = False,
    background_catalog: Any | None = None,
    selection_source: str | None = None,
) -> CombinedCommander | None:
    """Apply partner/background inputs to a builder if the feature is enabled.

    Args:
        builder: Deck builder instance exposing ``load_commander_data``.
        primary_name: The selected primary commander name.
        secondary_name: Optional partner/partner-with commander name.
        background_name: Optional background name.
        feature_enabled: Whether partner mechanics are enabled for this run.
    background_catalog: Optional override for background catalog (testing).
    selection_source: Optional tag describing how the selection was made (e.g., "suggestion").

    Returns:
        CombinedCommander when a partner/background pairing is produced; ``None``
        when the feature is disabled or no secondary/background inputs are given.

    Raises:
        CommanderPartnerError: If inputs are invalid or commanders cannot be
            combined under rules constraints.
    """

    if not feature_enabled:
        return None

    secondary_name = _coerce_name(secondary_name)
    background_name = _coerce_name(background_name)

    if not primary_name:
        return None

    clean_selection_source = (selection_source or "").strip().lower() or None

    if secondary_name and background_name:
        raise CommanderPartnerError(
            "Provide either 'secondary_commander' or 'background', not both.",
            details={
                "primary": primary_name,
                "secondary_commander": secondary_name,
                "background": background_name,
            },
        )

    if not secondary_name and not background_name:
        return None

    commander_df = builder.load_commander_data()
    primary_row = _find_commander_row(commander_df, primary_name)
    if primary_row is None:
        raise CommanderPartnerError(
            f"Primary commander not found: {primary_name}",
            details={"commander": primary_name},
        )

    primary_source = _row_to_commander_source(primary_row)

    if background_name:
        catalog = background_catalog or load_background_cards()
        background_card = _lookup_background_card(catalog, background_name)
        if background_card is None:
            raise CommanderPartnerError(
                f"Background not found: {background_name}",
                details={"background": background_name},
            )
        combined = build_combined_commander(primary_source, background_card, PartnerMode.BACKGROUND)
        _log_partner_selection(
            combined,
            primary_source=primary_source,
            secondary_source=None,
            background_source=background_card,
            selection_source=clean_selection_source,
        )
        return combined

    # Partner/Partner With flow
    secondary_row = _find_commander_row(commander_df, secondary_name)
    if secondary_row is None:
        raise CommanderPartnerError(
            f"Secondary commander not found: {secondary_name}",
            details={"secondary_commander": secondary_name},
        )

    secondary_source = _row_to_commander_source(secondary_row)
    errors: list[CommanderPartnerError] = []
    combined: CombinedCommander | None = None
    for mode in (PartnerMode.PARTNER_WITH, PartnerMode.DOCTOR_COMPANION, PartnerMode.PARTNER):
        try:
            combined = build_combined_commander(primary_source, secondary_source, mode)
            break
        except CommanderPartnerError as exc:
            errors.append(exc)

    if combined is not None:
        _log_partner_selection(
            combined,
            primary_source=primary_source,
            secondary_source=secondary_source,
            background_source=None,
            selection_source=clean_selection_source,
        )
        return combined

    if errors:
        raise errors[-1]
    raise CommanderPartnerError("Unable to combine commanders with provided inputs.")


def _coerce_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _log_partner_selection(
    combined: CombinedCommander,
    *,
    primary_source: Any,
    secondary_source: Any | None,
    background_source: Any | None,
    selection_source: str | None = None,
) -> None:
    mode_value = combined.partner_mode.value if isinstance(combined.partner_mode, PartnerMode) else str(combined.partner_mode)
    secondary_role = _secondary_role_for_mode(combined.partner_mode)

    combined_colors = list(combined.color_identity or ())
    primary_colors = list(combined.primary_color_identity or _safe_colors_from_source(primary_source))
    if secondary_source is not None:
        secondary_colors = list(combined.secondary_color_identity or _safe_colors_from_source(secondary_source))
    else:
        secondary_colors = list(_safe_colors_from_source(background_source))

    color_delta = {
        "added": [color for color in combined_colors if color not in primary_colors],
        "removed": [color for color in primary_colors if color not in combined_colors],
        "primary": primary_colors,
        "secondary": secondary_colors,
    }

    primary_description = _describe_source(primary_source)
    secondary_description = _describe_source(secondary_source)
    background_description = _describe_source(background_source)

    commanders = {
        "primary": combined.primary_name,
        "secondary": combined.secondary_name,
        "background": (background_description or {}).get("display_name"),
    }
    sources = {
        "primary": primary_description,
        "secondary": secondary_description,
        "background": background_description,
    }

    payload = {
        "mode": mode_value,
        "secondary_role": secondary_role,
        "primary_name": commanders["primary"],
        "secondary_name": commanders["secondary"],
        "background_name": commanders["background"],
        "commanders": commanders,
        "color_identity": combined_colors,
        "colors_after": combined_colors,
        "colors_before": primary_colors,
        "color_code": combined.color_code,
        "color_label": combined.color_label,
        "color_delta": color_delta,
        "primary_source": sources["primary"],
        "secondary_source": sources["secondary"],
        "background_source": sources["background"],
        "sources": sources,
    }

    if selection_source:
        payload["selection_source"] = selection_source

    logger.info(
        "partner_mode_selected",
        extra={
            "event": "partner_mode_selected",
            "payload": payload,
        },
    )


def _secondary_role_for_mode(mode: PartnerMode) -> str:
    if mode is PartnerMode.BACKGROUND:
        return "background"
    if mode is PartnerMode.DOCTOR_COMPANION:
        return "companion"
    if mode is PartnerMode.PARTNER_WITH:
        return "partner_with"
    if mode is PartnerMode.PARTNER:
        return "partner"
    return "secondary"


def _safe_colors_from_source(source: Any | None) -> list[str]:
    if source is None:
        return []
    value = getattr(source, "color_identity", None) or getattr(source, "colors", None)
    return list(_normalize_color_identity(value))


def _describe_source(source: Any | None) -> dict[str, object] | None:
    if source is None:
        return None
    name = getattr(source, "name", None) or getattr(source, "display_name", None)
    display_name = getattr(source, "display_name", None) or name
    partner_with = getattr(source, "partner_with", None)
    if partner_with is None:
        partner_with = getattr(source, "partnerWith", None)

    return {
        "name": name,
        "display_name": display_name,
        "color_identity": _safe_colors_from_source(source),
        "themes": list(getattr(source, "themes", ()) or getattr(source, "theme_tags", ()) or []),
        "partner_with": list(partner_with or ()),
    }


def _find_commander_row(df: Any, name: str | None):
    if name is None:
        return None
    target = normalize_lookup_name(name)
    if not target:
        return None

    if _pd is not None and isinstance(df, _pd.DataFrame):  # type: ignore
        columns = [col for col in ("name", "faceName") if col in df.columns]
        for col in columns:
            series = df[col].astype(str).str.casefold()
            matches = df[series == target]
            if not matches.empty:
                return matches.iloc[0]
        return None

    # Fallback for DataFrame-like sequences
    for row in getattr(df, "itertuples", lambda index=False: [])():  # pragma: no cover - defensive
        for attr in ("name", "faceName"):
            value = getattr(row, attr, None)
            if normalize_lookup_name(value) == target:
                return getattr(df, "loc", lambda *_: row)(row.Index) if hasattr(row, "Index") else row
    return None


def _row_to_commander_source(row: Any) -> SimpleNamespace:
    themes = _normalize_string_sequence(row.get("themeTags"))
    partner_with = _normalize_string_sequence(
        row.get("partnerWith")
        or row.get("partner_with")
        or row.get("partnerNames")
        or row.get("partner_names")
    )

    return SimpleNamespace(
        name=_safe_str(row.get("name")),
        display_name=_safe_str(row.get("faceName")) or _safe_str(row.get("name")),
        color_identity=_normalize_color_identity(row.get("colorIdentity")),
        colors=_normalize_color_identity(row.get("colors")),
        themes=themes,
        theme_tags=themes,
        raw_tags=themes,
        partner_with=partner_with,
        oracle_text=_safe_str(row.get("text") or row.get("oracleText")),
        type_line=_safe_str(row.get("type") or row.get("type_line")),
        supports_backgrounds=_normalize_bool(row.get("supportsBackgrounds") or row.get("supports_backgrounds")),
        is_partner=_normalize_bool(row.get("isPartner") or row.get("is_partner")),
        is_background=_normalize_bool(row.get("isBackground") or row.get("is_background")),
        is_doctor=_normalize_bool(row.get("isDoctor") or row.get("is_doctor")),
        is_doctors_companion=_normalize_bool(row.get("isDoctorsCompanion") or row.get("is_doctors_companion")),
    )


def _lookup_background_card(catalog: Any, name: str) -> Any | None:
    lowered = normalize_lookup_name(name)

    getter = getattr(catalog, "get", None)
    if callable(getter):
        result = getter(name)
        if result is None:
            result = getter(lowered)
        if result is not None:
            return result

    entries = getattr(catalog, "entries", None)
    if entries is not None:
        for entry in entries:
            display = normalize_lookup_name(getattr(entry, "display_name", None))
            if display == lowered:
                return entry
            raw = normalize_lookup_name(getattr(entry, "name", None))
            if raw == lowered:
                return entry
            slug = normalize_lookup_name(getattr(entry, "slug", None))
            if slug == lowered:
                return entry

    return None


def _normalize_color_identity(value: Any) -> tuple[str, ...]:
    tokens = _normalize_string_sequence(value)
    result: list[str] = []
    for token in tokens:
        if len(token) > 1 and "," not in token and " " not in token:
            if all(ch in "WUBRGC" for ch in token):
                result.extend(ch for ch in token)
            else:
                result.append(token)
        else:
            result.append(token)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in result:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def _normalize_string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return tuple()
    # Handle numpy arrays, lists, tuples, sets, and other sequences
    try:
        import numpy as np
        is_numpy = isinstance(value, np.ndarray)
    except ImportError:
        is_numpy = False
    
    if isinstance(value, (list, tuple, set)) or is_numpy:
        items = list(value)
    else:
        text = _safe_str(value)
        if not text:
            return tuple()
        try:
            parsed = ast.literal_eval(text)
        except Exception:  # pragma: no cover - non literal values handled below
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            items = list(parsed)
        elif ";" in text:
            items = [part.strip() for part in text.split(";")]
        elif "," in text:
            items = [part.strip() for part in text.split(",")]
        else:
            items = [text]
    collected: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = _safe_str(item)
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        collected.append(token)
    return tuple(collected)


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    text = _safe_str(value).casefold()
    if not text:
        return False
    if text in {"1", "true", "t", "yes", "on"}:
        return True
    if text in {"0", "false", "f", "no", "off"}:
        return False
    return False


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN check
        return ""
    text = str(value)
    if "\\r\\n" in text or "\\n" in text or "\\r" in text:
        text = (
            text.replace("\\r\\n", "\n")
            .replace("\\r", "\n")
            .replace("\\n", "\n")
        )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()
