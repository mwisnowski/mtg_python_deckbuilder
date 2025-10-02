from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any, Dict, Iterable

__all__ = [
    "record_land_summary",
    "get_mdfc_metrics",
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
