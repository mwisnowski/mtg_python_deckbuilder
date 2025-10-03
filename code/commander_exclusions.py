from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from settings import CSV_DIRECTORY


def _normalize(value: Any) -> str:
    return str(value or "").strip().casefold()


def _exclusions_path() -> Path:
    return Path(CSV_DIRECTORY) / ".commander_exclusions.json"


@lru_cache(maxsize=8)
def _load_index_cached(path_str: str, mtime: float) -> Dict[str, Dict[str, Any]]:
    path = Path(path_str)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    entries = data.get("secondary_face_only")
    if not isinstance(entries, list):
        return {}
    index: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        aliases = []
        for key in (entry.get("name"), entry.get("primary_face")):
            if key:
                aliases.append(str(key))
        faces = entry.get("faces")
        if isinstance(faces, list):
            aliases.extend(str(face) for face in faces if face)
        eligible = entry.get("eligible_faces")
        if isinstance(eligible, list):
            aliases.extend(str(face) for face in eligible if face)
        for alias in aliases:
            norm = _normalize(alias)
            if not norm:
                continue
            index[norm] = entry
    return index


def _load_index() -> Dict[str, Dict[str, Any]]:
    path = _exclusions_path()
    if not path.is_file():
        return {}
    try:
        stat = path.stat()
        mtime = float(f"{stat.st_mtime:.6f}")
    except Exception:
        mtime = 0.0
    return _load_index_cached(str(path.resolve()), mtime)


def lookup_commander(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    index = _load_index()
    return index.get(_normalize(name))


def lookup_commander_detail(name: str) -> Optional[Dict[str, Any]]:
    entry = lookup_commander(name)
    if entry is None:
        return None
    data = dict(entry)
    data.setdefault("primary_face", entry.get("primary_face") or entry.get("name"))
    data.setdefault("eligible_faces", entry.get("eligible_faces") or [])
    data.setdefault("reason", "secondary_face_only")
    return data


def exclusions_summary() -> Dict[str, Any]:
    index = _load_index()
    return {
        "count": len(index),
        "entries": sorted(
            [
                {
                    "name": entry.get("name") or entry.get("primary_face") or key,
                    "primary_face": entry.get("primary_face") or entry.get("name") or key,
                    "eligible_faces": entry.get("eligible_faces") or [],
                }
                for key, entry in index.items()
            ],
            key=lambda x: x["name"],
        ),
    }
