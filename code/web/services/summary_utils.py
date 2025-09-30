from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from deck_builder import builder_constants as bc
from .build_utils import owned_set as owned_set_helper
from .combo_utils import detect_for_summary as _detect_for_summary


def _sanitize_tag_list(values: Iterable[Any]) -> List[str]:
    cleaned: List[str] = []
    for raw in values or []:  # type: ignore[arg-type]
        text = str(raw or "").strip()
        if not text:
            continue
        if text.startswith("['"):
            text = text[2:]
        if text.endswith("']") and len(text) >= 2:
            text = text[:-2]
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1]
        if text.startswith("'") and text.endswith("'") and len(text) >= 2:
            text = text[1:-1]
        text = text.strip(" []\t\n\r")
        if not text:
            continue
        cleaned.append(text)
    return cleaned


def _normalize_summary_tags(summary: dict[str, Any] | None) -> None:
    if not summary:
        return
    try:
        type_breakdown = summary.get("type_breakdown") or {}
        cards_by_type = type_breakdown.get("cards") or {}
        for clist in cards_by_type.values():
            if not isinstance(clist, list):
                continue
            for card in clist:
                if not isinstance(card, dict):
                    continue
                tags = card.get("tags") or []
                if tags:
                    card["tags"] = _sanitize_tag_list(tags)
    except Exception:
        pass


def format_theme_label(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("_", " ")
    words = []
    for part in text.split():
        if not part:
            continue
        if part.isupper():
            words.append(part)
        else:
            words.append(part[0].upper() + part[1:].lower() if len(part) > 1 else part.upper())
    return " ".join(words)


def format_theme_list(values: Iterable[Any]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for raw in values or []:  # type: ignore[arg-type]
        label = format_theme_label(raw)
        if not label:
            continue
        if len(label) <= 1:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(label)
    return result


def summary_ctx(
    *,
    summary: dict | None,
    commander: str | None = None,
    tags: list[str] | None = None,
    meta: Optional[dict[str, Any]] = None,
    include_versions: bool = True,
) -> Dict[str, Any]:
    """Build a unified context payload for deck summary panels.

    Provides owned_set, game_changers, combos/synergies, and detector versions.
    """
    _normalize_summary_tags(summary)

    det = _detect_for_summary(summary, commander_name=commander or "") if summary else {"combos": [], "synergies": [], "versions": {}}
    combos = det.get("combos", [])
    synergies_raw = det.get("synergies", []) or []
    # Flatten synergy tag names while preserving appearance order and collapsing duplicates case-insensitively
    synergy_tags: list[str] = []
    seen: set[str] = set()
    for entry in synergies_raw:
        if entry is None:
            continue
        if isinstance(entry, dict):
            tags = entry.get("tags", []) or []
        else:
            tags = getattr(entry, "tags", None) or []
        for tag in tags:
            text = str(tag).strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            synergy_tags.append(text)
    if not synergy_tags:
        fallback_sources: list[str] = []
        for collection in (tags or []):
            fallback_sources.append(str(collection))
        meta_obj = meta or {}
        meta_keys = [
            "display_themes",
            "resolved_themes",
            "auto_filled_themes",
            "random_display_themes",
            "random_resolved_themes",
            "random_auto_filled_themes",
            "primary_theme",
            "secondary_theme",
            "tertiary_theme",
        ]
        for key in meta_keys:
            value = meta_obj.get(key) if isinstance(meta_obj, dict) else None
            if isinstance(value, list):
                fallback_sources.extend(str(v) for v in value)
            elif isinstance(value, str):
                fallback_sources.append(value)
        for raw in fallback_sources:
            label = format_theme_label(raw)
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            synergy_tags.append(label)
    versions = det.get("versions", {} if include_versions else None)
    return {
        "owned_set": owned_set_helper(),
        "game_changers": bc.GAME_CHANGERS,
        "combos": combos,
        "synergies": synergy_tags,
        "synergy_pairs": synergies_raw,
        "versions": versions,
        "commander": commander,
        "tags": tags or [],
    }
