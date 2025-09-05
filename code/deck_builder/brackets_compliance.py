from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import yaml

from deck_builder.combos import detect_combos
from .phases.phase0_core import BRACKET_DEFINITIONS
from type_definitions import ComplianceReport, CategoryFinding


POLICY_TAGS = {
    "game_changers": "Bracket:GameChanger",
    "extra_turns": "Bracket:ExtraTurn",
    "mass_land_denial": "Bracket:MassLandDenial",
    "tutors_nonland": "Bracket:TutorNonland",
}

# Local policy file mapping (mirrors tagging.bracket_policy_applier)
POLICY_FILES: Dict[str, str] = {
    "game_changers": "config/card_lists/game_changers.json",
    "extra_turns": "config/card_lists/extra_turns.json",
    "mass_land_denial": "config/card_lists/mass_land_denial.json",
    "tutors_nonland": "config/card_lists/tutors_nonland.json",
}


def _load_json_cards(path: str | Path) -> Tuple[List[str], Optional[str]]:
    p = Path(path)
    if not p.exists():
        return [], None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cards = [str(x).strip() for x in data.get("cards", []) if str(x).strip()]
        version = str(data.get("list_version")) if data.get("list_version") else None
        return cards, version
    except Exception:
        return [], None


def _load_brackets_yaml(path: str | Path = "config/brackets.yml") -> Dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _find_bracket_def(bracket_key: str) -> Tuple[str, int, Dict[str, Optional[int]]]:
    key = (bracket_key or "core").strip().lower()
    # Prefer YAML if available
    y = _load_brackets_yaml()
    if key in y:
        meta = y[key]
        name = str(meta.get("name", key.title()))
        level = int(meta.get("level", 2))
        limits = dict(meta.get("limits", {}))
        return name, level, limits
    # Fallback to in-code defaults
    for bd in BRACKET_DEFINITIONS:
        if bd.name.strip().lower() == key or str(bd.level) == key:
            return bd.name, bd.level, dict(bd.limits)
        # map common aliases
        alias = bd.name.strip().lower()
        if key in (alias, {1:"exhibition",2:"core",3:"upgraded",4:"optimized",5:"cedh"}.get(bd.level, "")):
            return bd.name, bd.level, dict(bd.limits)
    # Default to Core
    core = next(b for b in BRACKET_DEFINITIONS if b.level == 2)
    return core.name, core.level, dict(core.limits)


def _collect_tag_counts(card_library: Dict[str, Dict]) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    counts: Dict[str, int] = {v: 0 for v in POLICY_TAGS.values()}
    flagged_names: Dict[str, List[str]] = {k: [] for k in POLICY_TAGS.keys()}
    for name, info in (card_library or {}).items():
        tags = [t for t in (info.get("Tags") or []) if isinstance(t, str)]
        for key, tag in POLICY_TAGS.items():
            if tag in tags:
                counts[tag] += 1
                flagged_names[key].append(name)
    return counts, flagged_names


def _canonicalize(name: str | None) -> str:
    """Match normalization similar to the tag applier.

    - casefold
    - normalize curly apostrophes to straight
    - strip A- prefix (Arena/Alchemy variants)
    - trim
    """
    if not name:
        return ""
    s = str(name).strip().replace("\u2019", "'")
    if s.startswith("A-") and len(s) > 2:
        s = s[2:]
    return s.casefold()


def _status_for(count: int, limit: Optional[int], warn: Optional[int] = None) -> str:
    # Unlimited hard limit -> always PASS (no WARN semantics without a cap)
    if limit is None:
        return "PASS"
    if count > int(limit):
        return "FAIL"
    # Soft guidance: if warn threshold provided and met, surface WARN
    try:
        if warn is not None and int(warn) > 0 and count >= int(warn):
            return "WARN"
    except Exception:
        pass
    return "PASS"


def evaluate_deck(
    deck_cards: Dict[str, Dict],
    commander_name: Optional[str],
    bracket: str,
    enforcement: str = "validate",
    combos_path: str | Path = "config/card_lists/combos.json",
) -> ComplianceReport:
    name, level, limits = _find_bracket_def(bracket)
    counts_by_tag, names_by_key = _collect_tag_counts(deck_cards)

    categories: Dict[str, CategoryFinding] = {}
    messages: List[str] = []

    # Prepare a canonicalized deck name map to support list-based matching
    deck_canon_to_display: Dict[str, str] = {}
    for n in (deck_cards or {}).keys():
        cn = _canonicalize(n)
        if cn and cn not in deck_canon_to_display:
            deck_canon_to_display[cn] = n

    # Map categories by combining tag-based counts with direct list matches by name
    for key, tag in POLICY_TAGS.items():
        # Start with any names found via tags
        flagged_set: set[str] = set()
        for nm in names_by_key.get(key, []) or []:
            ckey = _canonicalize(nm)
            if ckey:
                flagged_set.add(ckey)
        # Merge in list-based matches (by canonicalized name)
        try:
            file_path = POLICY_FILES.get(key)
            if file_path:
                names_list, _ver = _load_json_cards(file_path)
                # Fallback for game_changers when file is empty: use in-code constants
                if key == 'game_changers' and not names_list:
                    try:
                        from deck_builder import builder_constants as _bc
                        names_list = list(getattr(_bc, 'GAME_CHANGERS', []) or [])
                    except Exception:
                        names_list = []
                listed = {_canonicalize(x) for x in names_list}
                present = set(deck_canon_to_display.keys())
                flagged_set |= (listed & present)
        except Exception:
            pass
        # Build final flagged display names from the canonical set
        flagged_names_disp = sorted({deck_canon_to_display.get(cn, cn) for cn in flagged_set})
        c = len(flagged_set)
        lim = limits.get(key)
        # Optional warn thresholds live alongside limits as "<key>_warn"
        try:
            warn_key = f"{key}_warn"
            warn_val = limits.get(warn_key)
        except Exception:
            warn_val = None
        status = _status_for(c, lim, warn=warn_val)
        cat: CategoryFinding = {
            "count": c,
            "limit": lim,
            "flagged": flagged_names_disp,
            "status": status,
            "notes": [],
        }
        categories[key] = cat
        if status == "FAIL":
            messages.append(f"{key.replace('_',' ').title()}: {c} exceeds limit {lim}")
        elif status == "WARN":
            try:
                if warn_val is not None:
                    messages.append(f"{key.replace('_',' ').title()}: {c} present (discouraged for this bracket)")
            except Exception:
                pass
        # Conservative fallback: for low brackets (levels 1–2), tutors/extra-turns should WARN when present
        # even if a warn threshold was not provided in YAML.
        if status == "PASS" and level in (1, 2) and key in ("tutors_nonland", "extra_turns"):
            try:
                if (warn_val is None) and (lim is not None) and c > 0 and c <= int(lim):
                    categories[key]["status"] = "WARN"
                    messages.append(f"{key.replace('_',' ').title()}: {c} present (discouraged for this bracket)")
            except Exception:
                pass

    # Two-card combos detection
    combos = detect_combos(deck_cards.keys(), combos_path=combos_path)
    cheap_early_pairs = [p for p in combos if p.cheap_early]
    c_limit = limits.get("two_card_combos")
    combos_status = _status_for(len(cheap_early_pairs), c_limit, warn=None)
    categories["two_card_combos"] = {
        "count": len(cheap_early_pairs),
        "limit": c_limit,
        "flagged": [f"{p.a} + {p.b}" for p in cheap_early_pairs],
        "status": combos_status,
        "notes": ["Only counting cheap/early combos per policy"],
    }
    if combos_status == "FAIL":
        messages.append("Two-card combos present beyond allowed bracket")

    commander_flagged = False
    if commander_name:
        gch_cards, _ = _load_json_cards("config/card_lists/game_changers.json")
        if any(commander_name.strip().lower() == x.lower() for x in gch_cards):
            commander_flagged = True
            # Exhibition/Core treat this as automatic fail; Upgraded counts toward limit
            if level in (1, 2):
                messages.append("Commander is on Game Changers list (not allowed for this bracket)")
                categories["game_changers"]["status"] = "FAIL"
                categories["game_changers"]["flagged"].append(commander_name)

    # Build list_versions metadata
    _, extra_ver = _load_json_cards("config/card_lists/extra_turns.json")
    _, mld_ver = _load_json_cards("config/card_lists/mass_land_denial.json")
    _, tutor_ver = _load_json_cards("config/card_lists/tutors_nonland.json")
    _, gch_ver = _load_json_cards("config/card_lists/game_changers.json")
    list_versions = {
        "extra_turns": extra_ver,
        "mass_land_denial": mld_ver,
        "tutors_nonland": tutor_ver,
        "game_changers": gch_ver,
    }

    # Overall verdict
    overall = "PASS"
    if any(cat.get("status") == "FAIL" for cat in categories.values()):
        overall = "FAIL"
    elif any(cat.get("status") == "WARN" for cat in categories.values()):
        overall = "WARN"

    report: ComplianceReport = {
        "bracket": name.lower(),
        "level": level,
        "enforcement": enforcement,
        "overall": overall,
        "commander_flagged": commander_flagged,
        "categories": categories,
        "combos": [{"a": p.a, "b": p.b, "cheap_early": p.cheap_early, "setup_dependent": p.setup_dependent} for p in combos],
        "list_versions": list_versions,
        "messages": messages,
    }
    return report
