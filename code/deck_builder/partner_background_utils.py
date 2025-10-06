"""Utilities for detecting partner and background mechanics from card data."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, Tuple, List

__all__ = [
    "PartnerBackgroundInfo",
    "analyze_partner_background",
    "extract_partner_with_names",
]

_PARTNER_PATTERN = re.compile(r"\bPartner\b(?!\s+with)", re.IGNORECASE)
_PARTNER_WITH_PATTERN = re.compile(r"\bPartner with ([^.;\n]+)", re.IGNORECASE)
_CHOOSE_BACKGROUND_PATTERN = re.compile(r"\bChoose a Background\b", re.IGNORECASE)
_BACKGROUND_KEYWORD_PATTERN = re.compile(r"\bBackground\b", re.IGNORECASE)
_FRIENDS_FOREVER_PATTERN = re.compile(r"\bFriends forever\b", re.IGNORECASE)
_DOCTORS_COMPANION_PATTERN = re.compile(r"Doctor's companion", re.IGNORECASE)
_PARTNER_RESTRICTION_PATTERN = re.compile(r"\bPartner\b\s*(?:—|-|–|:)", re.IGNORECASE)
_PARTNER_RESTRICTION_CAPTURE = re.compile(
    r"\bPartner\b\s*(?:—|-|–|:)\s*([^.;\n\r(]+)",
    re.IGNORECASE,
)
_PLAIN_PARTNER_THEME_TOKENS = {
    "partner",
    "partners",
}
_PARTNER_THEME_TOKENS = {
    "partner",
    "partners",
    "friends forever",
    "doctor's companion",
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, float):
        if math.isnan(value):
            return ""
        text = str(value)
    else:
        text = str(value)
    stripped = text.strip()
    if stripped.casefold() == "nan":
        return ""
    return text


def _is_background_theme_tag(tag: str) -> bool:
    text = (tag or "").strip().casefold()
    if not text:
        return False
    if "background" not in text:
        return False
    if "choose a background" in text:
        return False
    if "backgrounds matter" in text:
        return False
    normalized = text.replace("—", "-").replace("–", "-")
    if normalized in {"background", "backgrounds", "background card", "background (card type)"}:
        return True
    if normalized.startswith("background -") or normalized.startswith("background:"):
        return True
    if normalized.endswith(" background"):
        return True
    return False


@dataclass(frozen=True)
class PartnerBackgroundInfo:
    """Aggregated partner/background detection result."""

    has_partner: bool
    partner_with: Tuple[str, ...]
    choose_background: bool
    is_background: bool
    is_doctor: bool
    is_doctors_companion: bool
    has_plain_partner: bool
    has_restricted_partner: bool
    restricted_partner_labels: Tuple[str, ...]


def _normalize_theme_tags(tags: Iterable[str]) -> Tuple[str, ...]:
    return tuple(tag.strip().lower() for tag in tags if str(tag).strip())


def extract_partner_with_names(oracle_text: str) -> Tuple[str, ...]:
    """Extract partner-with names from oracle text.

    Handles mixed separators ("and", "or", "&", "/") while preserving card
    names that include commas (e.g., "Pir, Imaginative Rascal"). Reminder text in
    parentheses is stripped and results are deduplicated while preserving order.
    """

    text = _normalize_text(oracle_text)
    if not text:
        return tuple()

    names: list[str] = []
    seen: set[str] = set()
    for match in _PARTNER_WITH_PATTERN.finditer(text):
        raw_targets = match.group(1)
        # Remove reminder text and trailing punctuation
        until_paren = raw_targets.split("(", 1)[0]
        base_text = until_paren.strip().strip(". ")
        if not base_text:
            continue

        segments = re.split(r"\s*(?:\band\b|\bor\b|\bplus\b|&|/|\+)\s*", base_text, flags=re.IGNORECASE)
        buffer: List[str] = []
        for token in segments:
            buffer.extend(_split_partner_token(token))

        for item in buffer:
            cleaned = item.strip().strip("., ")
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            names.append(cleaned)
    return tuple(names)


_SIMPLE_NAME_TOKEN = re.compile(r"^[A-Za-z0-9'’\-]+$")


def _split_partner_token(token: str) -> List[str]:
    cleaned = (token or "").strip()
    if not cleaned:
        return []
    cleaned = cleaned.strip(",.; ")
    if not cleaned:
        return []

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) <= 1:
        return parts

    if all(_SIMPLE_NAME_TOKEN.fullmatch(part) for part in parts):
        return parts

    return [cleaned]


def _has_plain_partner_keyword(oracle_text: str) -> bool:
    oracle_text = _normalize_text(oracle_text)
    if not oracle_text:
        return False
    for raw_line in oracle_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        ability = line.split("(", 1)[0].strip()
        if not ability:
            continue
        lowered = ability.casefold()
        if lowered.startswith("partner with"):
            continue
        if lowered.startswith("partner"):
            suffix = ability[7:].strip()
            if suffix and suffix[0] in {"-", "—", "–", ":"}:
                continue
            if suffix:
                # Contains additional text beyond plain Partner keyword
                continue
            return True
    return False


def _has_partner_restriction(oracle_text: str) -> bool:
    oracle_text = _normalize_text(oracle_text)
    if not oracle_text:
        return False
    return bool(_PARTNER_RESTRICTION_PATTERN.search(oracle_text))


def analyze_partner_background(
    type_line: str | None,
    oracle_text: str | None,
    theme_tags: Iterable[str] | None = None,
) -> PartnerBackgroundInfo:
    """Detect partner/background mechanics using text and theme tags."""

    normalized_tags = _normalize_theme_tags(theme_tags or ())
    partner_with = extract_partner_with_names(oracle_text or "")
    type_line_text = _normalize_text(type_line)
    oracle_text_value = _normalize_text(oracle_text)
    choose_background = bool(_CHOOSE_BACKGROUND_PATTERN.search(oracle_text_value))
    theme_partner = any(tag in _PARTNER_THEME_TOKENS for tag in normalized_tags)
    theme_plain_partner = any(tag in _PLAIN_PARTNER_THEME_TOKENS for tag in normalized_tags)
    theme_choose_background = any("choose a background" in tag for tag in normalized_tags)
    theme_is_background = any(_is_background_theme_tag(tag) for tag in normalized_tags)
    friends_forever = bool(_FRIENDS_FOREVER_PATTERN.search(oracle_text_value))
    theme_friends_forever = any(tag == "friends forever" for tag in normalized_tags)
    plain_partner_keyword = _has_plain_partner_keyword(oracle_text_value)
    has_plain_partner = bool(plain_partner_keyword or theme_plain_partner)
    partner_restriction_keyword = _has_partner_restriction(oracle_text_value)
    restricted_labels = _collect_restricted_partner_labels(oracle_text_value, theme_tags)
    has_restricted_partner = bool(
        partner_with
        or partner_restriction_keyword
        or friends_forever
        or theme_friends_forever
        or restricted_labels
    )

    creature_segment = ""
    if type_line_text:
        if "—" in type_line_text:
            creature_segment = type_line_text.split("—", 1)[1]
        elif "-" in type_line_text:
            creature_segment = type_line_text.split("-", 1)[1]
        else:
            creature_segment = type_line_text
    type_tokens = {part.strip().lower() for part in creature_segment.split() if part.strip()}
    has_time_lord_doctor = {"time", "lord", "doctor"}.issubset(type_tokens)
    is_doctor = bool(has_time_lord_doctor)
    is_doctors_companion = bool(_DOCTORS_COMPANION_PATTERN.search(oracle_text_value))
    if not is_doctors_companion:
        is_doctors_companion = any("doctor" in tag and "companion" in tag for tag in normalized_tags)

    has_partner = bool(has_plain_partner or has_restricted_partner or theme_partner)
    choose_background = choose_background or theme_choose_background
    is_background = bool(_BACKGROUND_KEYWORD_PATTERN.search(type_line_text)) or theme_is_background

    return PartnerBackgroundInfo(
        has_partner=has_partner,
        partner_with=partner_with,
        choose_background=choose_background,
        is_background=is_background,
        is_doctor=is_doctor,
        is_doctors_companion=is_doctors_companion,
        has_plain_partner=has_plain_partner,
        has_restricted_partner=has_restricted_partner,
        restricted_partner_labels=restricted_labels,
    )


def _collect_restricted_partner_labels(
    oracle_text: str,
    theme_tags: Iterable[str] | None,
) -> Tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()

    def _maybe_add(raw: str | None) -> None:
        if not raw:
            return
        cleaned = raw.strip().strip("-—–: ")
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        labels.append(cleaned)

    oracle_text = _normalize_text(oracle_text)
    for match in _PARTNER_RESTRICTION_CAPTURE.finditer(oracle_text):
        value = match.group(1)
        value = value.split("(", 1)[0]
        value = value.strip().rstrip(".,;:—-– ")
        _maybe_add(value)

    if theme_tags:
        for tag in theme_tags:
            text = _normalize_text(tag).strip()
            if not text:
                continue
            lowered = text.casefold()
            if not lowered.startswith("partner"):
                continue
            parts = re.split(r"[—\-–:]", text, maxsplit=1)
            if len(parts) < 2:
                continue
            _maybe_add(parts[1])

    return tuple(labels)
