"""Deck visibility helpers.

Visibility is stored in the ``meta.visibility`` key of a deck's
``.summary.json`` sidecar. Missing or invalid values are treated as
``"private"`` so existing decks (saved before this feature existed) stay
private by default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

VALID_VISIBILITIES = ("public", "unlisted", "private")
DEFAULT_VISIBILITY = "private"

_PathLike = Union[str, Path]


def _sidecar_path(csv_path: _PathLike) -> Path:
    return Path(csv_path).with_suffix(".summary.json")


def resolve_visibility_for_write(
    csv_path: _PathLike,
    fallback: str = DEFAULT_VISIBILITY,
    *,
    deck_dir: "_PathLike | None" = None,
    override: "str | None" = None,
) -> str:
    """Return the visibility to persist when (re)writing a deck's sidecar.

    Resolution order:
      1. ``override`` (Milestone 7 per-build wizard choice) if it's a valid value
      2. an existing sidecar's visibility, preserved as-is (rebuilds/re-exports
         within the same build should keep reapplying the same override anyway)
      3. the owning user's profile default visibility preference (Milestone 6),
         derived from ``deck_dir``'s final path segment as the user id
      4. ``fallback``

    ``deck_dir`` (when given) is used to look up the owning user's profile
    default visibility preference; the directory's final path segment is
    treated as the user id.
    """
    if override in VALID_VISIBILITIES:
        return override
    existing = get_deck_visibility(csv_path)
    sidecar = _sidecar_path(csv_path)
    if sidecar.exists():
        return existing
    if deck_dir is not None:
        try:
            from .user_db import get_default_visibility
            user_id = Path(deck_dir).name
            return get_default_visibility(user_id)
        except Exception:
            pass
    return fallback if fallback in VALID_VISIBILITIES else DEFAULT_VISIBILITY


def get_deck_visibility(csv_path: _PathLike) -> str:
    """Read a deck's visibility from its sidecar. Missing/invalid -> ``"private"``."""
    sidecar = _sidecar_path(csv_path)
    try:
        if not sidecar.exists():
            return DEFAULT_VISIBILITY
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        meta = payload.get("meta") if isinstance(payload, dict) else None
        visibility = meta.get("visibility") if isinstance(meta, dict) else None
        return visibility if visibility in VALID_VISIBILITIES else DEFAULT_VISIBILITY
    except Exception:
        return DEFAULT_VISIBILITY


def set_deck_visibility(csv_path: _PathLike, visibility: str) -> None:
    """Rewrite only the ``visibility`` key in a deck's sidecar summary JSON.

    Raises:
        ValueError: ``visibility`` is not one of `VALID_VISIBILITIES`.
        FileNotFoundError: the sidecar does not exist for this deck.
    """
    if visibility not in VALID_VISIBILITIES:
        raise ValueError(f"Invalid visibility: {visibility!r}")
    sidecar = _sidecar_path(csv_path)
    if not sidecar.exists():
        raise FileNotFoundError(str(sidecar))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {}
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        payload["meta"] = meta
    meta["visibility"] = visibility
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
