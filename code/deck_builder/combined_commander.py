"""Combine commander selections across partner/background modes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence, Tuple

from exceptions import CommanderPartnerError

from .partner_background_utils import analyze_partner_background
from .color_identity_utils import canon_color_code, color_label_from_code

_WUBRG_ORDER: Tuple[str, ...] = ("W", "U", "B", "R", "G", "C")
_COLOR_PRIORITY = {color: index for index, color in enumerate(_WUBRG_ORDER)}


class PartnerMode(str, Enum):
    """Enumerates supported partner mechanics."""

    NONE = "none"
    PARTNER = "partner"
    PARTNER_WITH = "partner_with"
    BACKGROUND = "background"
    DOCTOR_COMPANION = "doctor_companion"


@dataclass(frozen=True, slots=True)
class CombinedCommander:
    """Represents merged commander metadata for deck building."""

    primary_name: str
    secondary_name: str | None
    partner_mode: PartnerMode
    color_identity: Tuple[str, ...]
    theme_tags: Tuple[str, ...]
    raw_tags_primary: Tuple[str, ...]
    raw_tags_secondary: Tuple[str, ...]
    warnings: Tuple[str, ...]
    color_code: str = ""
    color_label: str = ""
    primary_color_identity: Tuple[str, ...] = ()
    secondary_color_identity: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _CommanderData:
    name: str
    display_name: str
    color_identity: Tuple[str, ...]
    themes: Tuple[str, ...]
    raw_tags: Tuple[str, ...]
    partner_with: Tuple[str, ...]
    is_partner: bool
    supports_backgrounds: bool
    is_background: bool
    is_doctor: bool
    is_doctors_companion: bool

    @classmethod
    def from_source(cls, source: object) -> "_CommanderData":
        name = _get_attr(source, "name") or _get_attr(source, "display_name") or ""
        display_name = _get_attr(source, "display_name") or name
        if not display_name:
            raise CommanderPartnerError("Commander is missing a display name", details={"source": repr(source)})

        color_identity = _normalize_colors(_get_attr(source, "color_identity") or _get_attr(source, "colorIdentity"))
        themes = _normalize_theme_tags(
            _get_attr(source, "themes")
            or _get_attr(source, "theme_tags")
            or _get_attr(source, "themeTags")
        )
        raw_tags = tuple(_ensure_sequence(_get_attr(source, "themes") or _get_attr(source, "theme_tags") or _get_attr(source, "themeTags")))

        partner_with: Tuple[str, ...] = tuple(_ensure_sequence(_get_attr(source, "partner_with") or ()))
        oracle_text = _get_attr(source, "oracle_text") or _get_attr(source, "text")
        type_line = _get_attr(source, "type_line") or _get_attr(source, "type")

        detection = analyze_partner_background(type_line, oracle_text, raw_tags or themes)
        if not partner_with:
            partner_with = detection.partner_with

        is_partner = bool(_get_attr(source, "is_partner")) or detection.has_partner
        supports_backgrounds = bool(_get_attr(source, "supports_backgrounds")) or detection.choose_background
        is_background = bool(_get_attr(source, "is_background")) or detection.is_background
        is_doctor = bool(_get_attr(source, "is_doctor")) or detection.is_doctor
        is_doctors_companion = bool(_get_attr(source, "is_doctors_companion")) or detection.is_doctors_companion

        return cls(
            name=name,
            display_name=display_name,
            color_identity=color_identity,
            themes=themes,
            raw_tags=tuple(raw_tags),
            partner_with=partner_with,
            is_partner=is_partner,
            supports_backgrounds=supports_backgrounds,
            is_background=is_background,
            is_doctor=is_doctor,
            is_doctors_companion=is_doctors_companion,
        )


def build_combined_commander(
    primary: object,
    secondary: object | None,
    mode: PartnerMode,
) -> CombinedCommander:
    """Merge commander metadata according to the selected partner mode."""

    primary_data = _CommanderData.from_source(primary)
    secondary_data = _CommanderData.from_source(secondary) if secondary is not None else None

    _validate_mode_inputs(primary_data, secondary_data, mode)
    warnings = _collect_warnings(primary_data, secondary_data)

    color_identity = _merge_colors(primary_data, secondary_data)
    theme_tags = _merge_theme_tags(primary_data.themes, secondary_data.themes if secondary_data else ())
    raw_secondary = secondary_data.raw_tags if secondary_data else tuple()

    secondary_name = secondary_data.display_name if secondary_data else None
    color_code = canon_color_code(color_identity)
    color_label = color_label_from_code(color_code)
    primary_colors = primary_data.color_identity
    secondary_colors = secondary_data.color_identity if secondary_data else tuple()

    return CombinedCommander(
        primary_name=primary_data.display_name,
        secondary_name=secondary_name,
        partner_mode=mode,
        color_identity=color_identity,
        theme_tags=theme_tags,
        raw_tags_primary=primary_data.raw_tags,
        raw_tags_secondary=raw_secondary,
        warnings=warnings,
        color_code=color_code,
        color_label=color_label,
        primary_color_identity=primary_colors,
        secondary_color_identity=secondary_colors,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_mode_inputs(
    primary: _CommanderData,
    secondary: _CommanderData | None,
    mode: PartnerMode,
) -> None:
    details = {
        "mode": mode.value,
        "primary": primary.display_name,
        "secondary": secondary.display_name if secondary else None,
    }

    if mode is PartnerMode.NONE:
        if secondary is not None:
            raise CommanderPartnerError("Secondary commander provided but partner mode is NONE", details=details)
        return

    if secondary is None:
        raise CommanderPartnerError("Secondary commander is required for selected partner mode", details=details)

    _ensure_distinct(primary, secondary, details)

    if mode is PartnerMode.PARTNER:
        if not primary.is_partner:
            raise CommanderPartnerError(f"{primary.display_name} does not have Partner", details=details)
        if not secondary.is_partner:
            raise CommanderPartnerError(f"{secondary.display_name} does not have Partner", details=details)
        if secondary.is_background:
            raise CommanderPartnerError("Selected secondary is a Background; choose partner mode BACKGROUND", details=details)
        return

    if mode is PartnerMode.PARTNER_WITH:
        _validate_partner_with(primary, secondary, details)
        return

    if mode is PartnerMode.BACKGROUND:
        _validate_background(primary, secondary, details)
        return

    if mode is PartnerMode.DOCTOR_COMPANION:
        _validate_doctor_companion(primary, secondary, details)
        return

    raise CommanderPartnerError("Unsupported partner mode", details=details)


def _ensure_distinct(primary: _CommanderData, secondary: _CommanderData, details: dict[str, object]) -> None:
    if primary.display_name.casefold() == secondary.display_name.casefold():
        raise CommanderPartnerError("Primary and secondary commanders must be different", details=details)


def _validate_partner_with(primary: _CommanderData, secondary: _CommanderData, details: dict[str, object]) -> None:
    if secondary.is_background:
        raise CommanderPartnerError("Background cannot be used in PARTNER_WITH mode", details=details)
    if not primary.partner_with:
        raise CommanderPartnerError(f"{primary.display_name} does not specify a Partner With target", details=details)
    if not secondary.partner_with:
        raise CommanderPartnerError(f"{secondary.display_name} does not specify a Partner With target", details=details)

    secondary_names = {_standardize_name(name) for name in secondary.partner_with}
    primary_names = {_standardize_name(name) for name in primary.partner_with}
    if _standardize_name(secondary.display_name) not in primary_names:
        raise CommanderPartnerError(
            f"{secondary.display_name} is not a legal Partner With target for {primary.display_name}",
            details=details,
        )
    if _standardize_name(primary.display_name) not in secondary_names:
        raise CommanderPartnerError(
            f"{primary.display_name} is not a legal Partner With target for {secondary.display_name}",
            details=details,
        )


def _validate_background(primary: _CommanderData, secondary: _CommanderData, details: dict[str, object]) -> None:
    if not secondary.is_background:
        raise CommanderPartnerError("Selected secondary commander is not a Background", details=details)
    if not primary.supports_backgrounds:
        raise CommanderPartnerError(f"{primary.display_name} cannot choose a Background", details=details)
    if primary.is_background:
        raise CommanderPartnerError("Background cannot be used as primary commander", details=details)

def _validate_doctor_companion(primary: _CommanderData, secondary: _CommanderData, details: dict[str, object]) -> None:
    primary_is_doctor = bool(primary.is_doctor)
    primary_is_companion = bool(primary.is_doctors_companion)
    secondary_is_doctor = bool(secondary.is_doctor)
    secondary_is_companion = bool(secondary.is_doctors_companion)

    if not (primary_is_doctor or primary_is_companion):
        raise CommanderPartnerError(f"{primary.display_name} is not a Doctor or Doctor's Companion", details=details)
    if not (secondary_is_doctor or secondary_is_companion):
        raise CommanderPartnerError(f"{secondary.display_name} is not a Doctor or Doctor's Companion", details=details)

    if primary_is_doctor and secondary_is_doctor:
        raise CommanderPartnerError("Doctor commanders must pair with a Doctor's Companion", details=details)
    if primary_is_companion and secondary_is_companion:
        raise CommanderPartnerError("Doctor's Companion must pair with a Doctor", details=details)

    # Ensure pairing is complementary doctor <-> companion
    if primary_is_doctor and not secondary_is_companion:
        raise CommanderPartnerError(f"{secondary.display_name} is not a legal Doctor's Companion", details=details)
    if primary_is_companion and not secondary_is_doctor:
        raise CommanderPartnerError(f"{secondary.display_name} is not a legal Doctor pairing", details=details)


def _collect_warnings(
    primary: _CommanderData,
    secondary: _CommanderData | None,
) -> Tuple[str, ...]:
    warnings: list[str] = []
    if primary.is_partner and primary.supports_backgrounds:
        warnings.append(
            f"{primary.display_name} has both Partner and Background abilities; ensure the selected mode is intentional."
        )
    if secondary and secondary.is_partner and secondary.supports_backgrounds:
        warnings.append(
            f"{secondary.display_name} has both Partner and Background abilities; ensure the selected mode is intentional."
        )
    return tuple(warnings)


def _merge_colors(primary: _CommanderData, secondary: _CommanderData | None) -> Tuple[str, ...]:
    colors = set(primary.color_identity)
    if secondary:
        colors.update(secondary.color_identity)
    if not colors:
        return tuple()
    return tuple(sorted(colors, key=lambda color: (_COLOR_PRIORITY.get(color, len(_COLOR_PRIORITY)), color)))


def _merge_theme_tags(*sources: Iterable[str]) -> Tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for source in sources:
        for tag in source:
            clean = tag.strip()
            if not clean:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(clean)
    return tuple(merged)


def _normalize_colors(colors: Sequence[str] | None) -> Tuple[str, ...]:
    if not colors:
        return tuple()
    normalized = [str(color).strip().upper() for color in colors]
    normalized = [color for color in normalized if color]
    return tuple(normalized)


def _normalize_theme_tags(tags: Sequence[str] | None) -> Tuple[str, ...]:
    if not tags:
        return tuple()
    return tuple(str(tag).strip() for tag in tags if str(tag).strip())


def _ensure_sequence(value: object) -> Sequence[str]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return (value,)


def _standardize_name(name: str) -> str:
    return name.strip().casefold()


def _get_attr(source: object, attr: str) -> object:
    return getattr(source, attr, None)


__all__ = [
    "CombinedCommander",
    "PartnerMode",
    "build_combined_commander",
]
