from __future__ import annotations

from typing import Dict, List

from deck_builder.combos import (
    detect_combos as _detect_combos,
    detect_synergies as _detect_synergies,
)
from tagging.combo_schema import (
    load_and_validate_combos as _load_combos,
    load_and_validate_synergies as _load_synergies,
)


DEFAULT_COMBOS_PATH = "config/card_lists/combos.json"
DEFAULT_SYNERGIES_PATH = "config/card_lists/synergies.json"


def detect_all(
    names: List[str],
    *,
    combos_path: str = DEFAULT_COMBOS_PATH,
    synergies_path: str = DEFAULT_SYNERGIES_PATH,
) -> Dict[str, object]:
    """Detect combos/synergies for a list of card names and return results with versions.

    Returns a dict with keys: combos, synergies, versions, combos_model, synergies_model.
    Models may be None if loading fails.
    """
    try:
        combos_model = _load_combos(combos_path)
    except Exception:
        combos_model = None
    try:
        synergies_model = _load_synergies(synergies_path)
    except Exception:
        synergies_model = None

    try:
        combos = _detect_combos(names, combos_path=combos_path)
    except Exception:
        combos = []
    try:
        synergies = _detect_synergies(names, synergies_path=synergies_path)
    except Exception:
        synergies = []

    versions = {
        "combos": getattr(combos_model, "list_version", None) if combos_model else None,
        "synergies": getattr(synergies_model, "list_version", None) if synergies_model else None,
    }
    return {
        "combos": combos,
        "synergies": synergies,
        "versions": versions,
        "combos_model": combos_model,
        "synergies_model": synergies_model,
    }


def _names_from_summary(summary: Dict[str, object]) -> List[str]:
    """Extract a best-effort set of card names from a build summary dict."""
    names_set: set[str] = set()
    try:
        tb = (summary or {}).get("type_breakdown", {})
        cards_by_type = tb.get("cards", {}) if isinstance(tb, dict) else {}
        for _typ, clist in (cards_by_type.items() if isinstance(cards_by_type, dict) else []):
            for c in (clist or []):
                n = str(c.get("name") if isinstance(c, dict) else getattr(c, "name", ""))
                if n:
                    names_set.add(n)
    except Exception:
        pass
    try:
        mc = (summary or {}).get("mana_curve", {})
        curve_cards = mc.get("cards", {}) if isinstance(mc, dict) else {}
        for _bucket, clist in (curve_cards.items() if isinstance(curve_cards, dict) else []):
            for c in (clist or []):
                n = str(c.get("name") if isinstance(c, dict) else getattr(c, "name", ""))
                if n:
                    names_set.add(n)
    except Exception:
        pass
    return sorted(names_set)


def detect_for_summary(
    summary: Dict[str, object] | None,
    commander_name: str | None = None,
    *,
    combos_path: str = DEFAULT_COMBOS_PATH,
    synergies_path: str = DEFAULT_SYNERGIES_PATH,
) -> Dict[str, object]:
    """Convenience helper: compute names from summary (+commander) and run detect_all."""
    names = _names_from_summary(summary or {})
    if commander_name:
        names = sorted(set(names) | {str(commander_name)})
    return detect_all(names, combos_path=combos_path, synergies_path=synergies_path)
