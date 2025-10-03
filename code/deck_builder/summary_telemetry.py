from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any, Dict, Iterable

__all__ = [
    "record_land_summary",
    "get_mdfc_metrics",
    "record_theme_summary",
    "get_theme_metrics",
]


_lock = threading.Lock()
_metrics: Dict[str, Any] = {
    "total_builds": 0,
    "builds_with_mdfc": 0,
    "total_mdfc_lands": 0,
    "last_updated": None,
    "last_updated_iso": None,
    "last_summary": None,
}
_top_cards: Counter[str] = Counter()

_theme_metrics: Dict[str, Any] = {
    "total_builds": 0,
    "with_user_themes": 0,
    "last_updated": None,
    "last_updated_iso": None,
    "last_summary": None,
}
_user_theme_counter: Counter[str] = Counter()
_user_theme_labels: Dict[str, str] = {}


def _to_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _sanitize_cards(cards: Iterable[Dict[str, Any]] | None) -> list[Dict[str, Any]]:
    if not cards:
        return []
    sanitized: list[Dict[str, Any]] = []
    for entry in cards:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        count = _to_int(entry.get("count", 1)) or 1
        colors = entry.get("colors")
        if isinstance(colors, (list, tuple)):
            color_list = [str(c) for c in colors if str(c)]
        else:
            color_list = []
        sanitized.append(
            {
                "name": name,
                "count": count,
                "colors": color_list,
                "counts_as_land": bool(entry.get("counts_as_land")),
                "adds_extra_land": bool(entry.get("adds_extra_land")),
            }
        )
    return sanitized


def record_land_summary(land_summary: Dict[str, Any] | None) -> None:
    if not isinstance(land_summary, dict):
        return

    dfc_lands = _to_int(land_summary.get("dfc_lands"))
    with_dfc = _to_int(land_summary.get("with_dfc"))
    timestamp = time.time()
    cards = _sanitize_cards(land_summary.get("dfc_cards"))

    with _lock:
        _metrics["total_builds"] = int(_metrics.get("total_builds", 0)) + 1
        if dfc_lands > 0:
            _metrics["builds_with_mdfc"] = int(_metrics.get("builds_with_mdfc", 0)) + 1
            _metrics["total_mdfc_lands"] = int(_metrics.get("total_mdfc_lands", 0)) + dfc_lands
            for entry in cards:
                _top_cards[entry["name"]] += entry["count"]
        _metrics["last_summary"] = {
            "dfc_lands": dfc_lands,
            "with_dfc": with_dfc,
            "cards": cards,
        }
        _metrics["last_updated"] = timestamp
        _metrics["last_updated_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def get_mdfc_metrics() -> Dict[str, Any]:
    with _lock:
        builds = int(_metrics.get("total_builds", 0) or 0)
        builds_with = int(_metrics.get("builds_with_mdfc", 0) or 0)
        total_lands = int(_metrics.get("total_mdfc_lands", 0) or 0)
        ratio = (builds_with / builds) if builds else 0.0
        avg_lands = (total_lands / builds_with) if builds_with else 0.0
        top_cards = dict(_top_cards.most_common(10))
        return {
            "total_builds": builds,
            "builds_with_mdfc": builds_with,
            "build_share": ratio,
            "total_mdfc_lands": total_lands,
            "avg_mdfc_lands": avg_lands,
            "top_cards": top_cards,
            "last_summary": _metrics.get("last_summary"),
            "last_updated": _metrics.get("last_updated_iso"),
        }


def _reset_metrics_for_test() -> None:
    with _lock:
        _metrics.update(
            {
                "total_builds": 0,
                "builds_with_mdfc": 0,
                "total_mdfc_lands": 0,
                "last_updated": None,
                "last_updated_iso": None,
                "last_summary": None,
            }
        )
        _top_cards.clear()
        _theme_metrics.update(
            {
                "total_builds": 0,
                "with_user_themes": 0,
                "last_updated": None,
                "last_updated_iso": None,
                "last_summary": None,
            }
        )
        _user_theme_counter.clear()
        _user_theme_labels.clear()


def _sanitize_theme_list(values: Iterable[Any]) -> list[str]:
    sanitized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:  # type: ignore[arg-type]
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(text)
    return sanitized


def record_theme_summary(theme_summary: Dict[str, Any] | None) -> None:
    if not isinstance(theme_summary, dict):
        return

    commander_themes = _sanitize_theme_list(theme_summary.get("commanderThemes") or [])
    user_themes = _sanitize_theme_list(theme_summary.get("userThemes") or [])
    requested = _sanitize_theme_list(theme_summary.get("requested") or [])
    resolved = _sanitize_theme_list(theme_summary.get("resolved") or [])
    unresolved_raw = theme_summary.get("unresolved") or []
    if isinstance(unresolved_raw, (list, tuple)):
        unresolved = [str(item).strip() for item in unresolved_raw if str(item).strip()]
    else:
        unresolved = []
    mode = str(theme_summary.get("mode") or "AND")
    try:
        weight = float(theme_summary.get("weight", 1.0) or 1.0)
    except Exception:
        weight = 1.0
    catalog_version = theme_summary.get("themeCatalogVersion")
    matches = theme_summary.get("matches") if isinstance(theme_summary.get("matches"), list) else []
    fuzzy = theme_summary.get("fuzzyCorrections") if isinstance(theme_summary.get("fuzzyCorrections"), dict) else {}

    merged: list[str] = []
    seen_merge: set[str] = set()
    for collection in (commander_themes, user_themes):
        for item in collection:
            key = item.casefold()
            if key in seen_merge:
                continue
            seen_merge.add(key)
            merged.append(item)

    timestamp = time.time()
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

    with _lock:
        _theme_metrics["total_builds"] = int(_theme_metrics.get("total_builds", 0) or 0) + 1
        if user_themes:
            _theme_metrics["with_user_themes"] = int(_theme_metrics.get("with_user_themes", 0) or 0) + 1
            for label in user_themes:
                key = label.casefold()
                _user_theme_counter[key] += 1
                if key not in _user_theme_labels:
                    _user_theme_labels[key] = label
        _theme_metrics["last_summary"] = {
            "commanderThemes": commander_themes,
            "userThemes": user_themes,
            "mergedThemes": merged,
            "requested": requested,
            "resolved": resolved,
            "unresolved": unresolved,
            "unresolvedCount": len(unresolved),
            "mode": mode,
            "weight": weight,
            "matches": matches,
            "fuzzyCorrections": fuzzy,
            "themeCatalogVersion": catalog_version,
        }
        _theme_metrics["last_updated"] = timestamp
        _theme_metrics["last_updated_iso"] = iso


def get_theme_metrics() -> Dict[str, Any]:
    with _lock:
        total = int(_theme_metrics.get("total_builds", 0) or 0)
        with_user = int(_theme_metrics.get("with_user_themes", 0) or 0)
        share = (with_user / total) if total else 0.0
        top_user: list[Dict[str, Any]] = []
        for key, count in _user_theme_counter.most_common(10):
            label = _user_theme_labels.get(key, key)
            top_user.append({"theme": label, "count": int(count)})
        return {
            "total_builds": total,
            "with_user_themes": with_user,
            "user_theme_share": share,
            "last_summary": _theme_metrics.get("last_summary"),
            "last_updated": _theme_metrics.get("last_updated_iso"),
            "top_user_themes": top_user,
        }
