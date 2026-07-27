"""Utilities for working with Magic color identity tuples and labels."""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List

__all__ = [
    "canon_color_code",
    "format_color_label",
    "color_label_from_code",
    "normalize_colors",
    "color_identity_badges",
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


def color_identity_badges(identity: Iterable[str] | str | None) -> dict:
    """Return clickable guild/shard/wedge/N-color name(s) and WUBRG pip dots
    for a color identity, for card browser/owned library tile badges.

    Returns a dict with:
      - "dots": WUBRG-ordered list of individual color letters present
        (empty for colorless/no colors)
      - "primary": {"name": str, "filter": str} for 2+ colors (guild name for
        2, shard/wedge name for 3, nephilim name for 4, "Five-Color" for 5),
        else None
      - "subs": list of {"name": str, "filter": str} pairwise guild names,
        populated only for exactly 3 colors (e.g. Bant -> Selesnya, Azorius,
        Simic), so a shard/wedge card also exposes its component guilds

    Each "filter" value is a WUBRG-canonical color code (e.g. "WUG") suitable
    for the card browser's `color` or owned library's `filter_color` params.
    """
    colors = normalize_colors(identity)
    result: dict = {"dots": colors, "primary": None, "subs": []}
    if len(colors) < 2:
        return result
    code = canon_color_code(colors)
    name: str | None = None
    if len(colors) == 2:
        name = _TWO_COLOR_LABELS.get(code)
    elif len(colors) == 3:
        name = _THREE_COLOR_LABELS.get(code)
    elif len(colors) == 4:
        name = _FOUR_COLOR_LABELS.get(code)
    elif code == "WUBRG":
        name = "Five-Color"
    if name:
        result["primary"] = {"name": name, "filter": code}
    if len(colors) == 3:
        subs = []
        for a, b in combinations(colors, 2):
            pair_code = canon_color_code([a, b])
            pair_name = _TWO_COLOR_LABELS.get(pair_code)
            if pair_name:
                subs.append({"name": pair_name, "filter": pair_code})
        result["subs"] = subs
    return result
