"""Utilities for working with Magic color identity tuples and labels."""
from __future__ import annotations

from typing import Iterable, List

__all__ = [
    "canon_color_code",
    "format_color_label",
    "color_label_from_code",
    "normalize_colors",
]

_WUBRG_ORDER: tuple[str, ...] = ("W", "U", "B", "R", "G")
_VALID_COLORS: frozenset[str] = frozenset((*_WUBRG_ORDER, "C"))
_COLOR_NAMES: dict[str, str] = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}
_TWO_COLOR_LABELS: dict[str, str] = {
    "WU": "Azorius",
    "UB": "Dimir",
    "BR": "Rakdos",
    "RG": "Gruul",
    "WG": "Selesnya",
    "WB": "Orzhov",
    "UR": "Izzet",
    "BG": "Golgari",
    "WR": "Boros",
    "UG": "Simic",
}
_THREE_COLOR_LABELS: dict[str, str] = {
    "WUB": "Esper",
    "UBR": "Grixis",
    "BRG": "Jund",
    "WRG": "Naya",
    "WUG": "Bant",
    "WBR": "Mardu",
    "WUR": "Jeskai",
    "UBG": "Sultai",
    "URG": "Temur",
    "WBG": "Abzan",
}
_FOUR_COLOR_LABELS: dict[str, str] = {
    "WUBR": "Yore-Tiller",
    "WUBG": "Witch-Maw",
    "WURG": "Ink-Treader",
    "WBRG": "Dune-Brood",
    "UBRG": "Glint-Eye",
}


def _extract_tokens(identity: Iterable[str] | str | None) -> List[str]:
    if identity is None:
        return []
    tokens: list[str] = []
    if isinstance(identity, str):
        identity_iter: Iterable[str] = (identity,)
    else:
        identity_iter = identity
    for item in identity_iter:
        if item is None:
            continue
        text = str(item).strip().upper()
        if not text:
            continue
        if len(text) > 1 and text.isalpha():
            for ch in text:
                if ch in _VALID_COLORS:
                    tokens.append(ch)
        else:
            for ch in text:
                if ch in _VALID_COLORS:
                    tokens.append(ch)
    return tokens


def normalize_colors(identity: Iterable[str] | str | None) -> list[str]:
    tokens = _extract_tokens(identity)
    if not tokens:
        return []
    seen: set[str] = set()
    collected: list[str] = []
    for token in tokens:
        if token in _WUBRG_ORDER and token not in seen:
            seen.add(token)
            collected.append(token)
    return [color for color in _WUBRG_ORDER if color in seen]


def canon_color_code(identity: Iterable[str] | str | None) -> str:
    tokens = _extract_tokens(identity)
    if not tokens:
        return "C"
    ordered = [color for color in _WUBRG_ORDER if color in tokens]
    if ordered:
        return "".join(ordered)
    if "C" in tokens:
        return "C"
    return "C"


def color_label_from_code(code: str) -> str:
    if not code:
        return ""
    if code == "C":
        return "Colorless (C)"
    if len(code) == 1:
        base = _COLOR_NAMES.get(code, code)
        return f"{base} ({code})"
    if len(code) == 2:
        label = _TWO_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if len(code) == 3:
        label = _THREE_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if len(code) == 4:
        label = _FOUR_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if code == "WUBRG":
        return "Five-Color (WUBRG)"
    parts = [_COLOR_NAMES.get(ch, ch) for ch in code]
    pretty = " / ".join(parts)
    return f"{pretty} ({code})"


def format_color_label(identity: Iterable[str] | str | None) -> str:
    return color_label_from_code(canon_color_code(identity))
