"""Shared text helpers to keep CLI and web copy in sync."""

from __future__ import annotations

from typing import Optional

__all__ = ["build_land_headline", "dfc_card_note"]


def build_land_headline(traditional: int, dfc_bonus: int, with_dfc: Optional[int] = None) -> str:
    """Return the consistent land summary headline.

    Args:
        traditional: Count of traditional land slots.
        dfc_bonus: Number of MDFC lands counted as additional slots.
        with_dfc: Optional total including MDFC lands. If omitted, the sum of
            ``traditional`` and ``dfc_bonus`` is used.
    """
    base = max(int(traditional), 0)
    bonus = max(int(dfc_bonus), 0)
    total = int(with_dfc) if with_dfc is not None else base + bonus
    headline = f"Lands: {base}"
    if bonus:
        headline += f" ({total} with DFC)"
    return headline


def dfc_card_note(counts_as_extra: bool) -> str:
    """Return the descriptive note for an MDFC land entry."""
    return "Adds extra land slot" if counts_as_extra else "Counts as land slot"
