from __future__ import annotations

from typing import Any, Dict
from deck_builder import builder_constants as bc
from .build_utils import owned_set as owned_set_helper
from .combo_utils import detect_for_summary as _detect_for_summary


def summary_ctx(
    *,
    summary: dict | None,
    commander: str | None = None,
    tags: list[str] | None = None,
    include_versions: bool = True,
) -> Dict[str, Any]:
    """Build a unified context payload for deck summary panels.

    Provides owned_set, game_changers, combos/synergies, and detector versions.
    """
    det = _detect_for_summary(summary, commander_name=commander or "") if summary else {"combos": [], "synergies": [], "versions": {}}
    combos = det.get("combos", [])
    synergies = det.get("synergies", [])
    versions = det.get("versions", {} if include_versions else None)
    return {
        "owned_set": owned_set_helper(),
        "game_changers": bc.GAME_CHANGERS,
        "combos": combos,
        "synergies": synergies,
        "versions": versions,
        "commander": commander,
        "tags": tags or [],
    }
