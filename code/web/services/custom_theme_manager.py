"""Session helpers for managing supplemental user themes in the web UI."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Tuple

from deck_builder.theme_resolution import (
	ThemeResolutionInfo,
	clean_theme_inputs,
	normalize_theme_match_mode,
	resolve_additional_theme_inputs,
)

DEFAULT_THEME_LIMIT = 8
ADDITION_COOLDOWN_SECONDS = 0.75

_INPUTS_KEY = "custom_theme_inputs"
_RESOLUTION_KEY = "user_theme_resolution"
_MODE_KEY = "theme_match_mode"
_LAST_ADD_KEY = "custom_theme_last_add_ts"
_CATALOG_VERSION_KEY = "theme_catalog_version"


def _sanitize_single(value: str | None) -> str | None:
	for item in clean_theme_inputs([value] if value is not None else []):
		return item
	return None


def _store_inputs(sess: Dict[str, Any], inputs: List[str]) -> None:
	sess[_INPUTS_KEY] = list(inputs)


def _current_inputs(sess: Dict[str, Any]) -> List[str]:
	values = sess.get(_INPUTS_KEY)
	if isinstance(values, list):
		return [str(v) for v in values if isinstance(v, str)]
	return []


def _store_resolution(sess: Dict[str, Any], info: ThemeResolutionInfo) -> None:
	info_dict = asdict(info)
	sess[_RESOLUTION_KEY] = info_dict
	sess[_CATALOG_VERSION_KEY] = info.catalog_version
	sess[_MODE_KEY] = info.mode
	sess["additional_themes"] = list(info.resolved)


def _default_resolution(mode: str) -> Dict[str, Any]:
	return {
		"requested": [],
		"mode": normalize_theme_match_mode(mode),
		"catalog_version": "unknown",
		"resolved": [],
		"matches": [],
		"unresolved": [],
		"fuzzy_corrections": {},
	}


def _resolve_and_store(
	sess: Dict[str, Any],
	inputs: List[str],
	mode: str,
	commander_tags: Iterable[str],
) -> ThemeResolutionInfo:
	info = resolve_additional_theme_inputs(inputs, mode, commander_tags=commander_tags)
	_store_inputs(sess, inputs)
	_store_resolution(sess, info)
	return info


def get_view_state(sess: Dict[str, Any], *, default_mode: str) -> Dict[str, Any]:
	inputs = _current_inputs(sess)
	mode = sess.get(_MODE_KEY, default_mode)
	resolution = sess.get(_RESOLUTION_KEY)
	if not isinstance(resolution, dict):
		resolution = _default_resolution(mode)
	remaining = max(0, int(sess.get("custom_theme_limit", DEFAULT_THEME_LIMIT)) - len(inputs))
	return {
		"inputs": inputs,
		"mode": normalize_theme_match_mode(mode),
		"resolution": resolution,
		"limit": int(sess.get("custom_theme_limit", DEFAULT_THEME_LIMIT)),
		"remaining": remaining,
	}


def set_limit(sess: Dict[str, Any], limit: int) -> None:
	sess["custom_theme_limit"] = max(1, int(limit))


def add_theme(
	sess: Dict[str, Any],
	value: str | None,
	*,
	commander_tags: Iterable[str],
	mode: str | None,
	limit: int = DEFAULT_THEME_LIMIT,
) -> Tuple[ThemeResolutionInfo | None, str, str]:
	normalized_mode = normalize_theme_match_mode(mode)
	inputs = _current_inputs(sess)
	sanitized = _sanitize_single(value)
	if not sanitized:
		return None, "Enter a theme to add.", "error"
	lower_inputs = {item.casefold() for item in inputs}
	if sanitized.casefold() in lower_inputs:
		return None, "That theme is already listed.", "info"
	if len(inputs) >= limit:
		return None, f"You can only add up to {limit} themes.", "warning"
	last_ts = float(sess.get(_LAST_ADD_KEY, 0.0) or 0.0)
	now = time.time()
	if now - last_ts < ADDITION_COOLDOWN_SECONDS:
		return None, "Please wait a moment before adding another theme.", "warning"
	proposed = inputs + [sanitized]
	try:
		info = _resolve_and_store(sess, proposed, normalized_mode, commander_tags)
		sess[_LAST_ADD_KEY] = now
		return info, f"Added theme '{sanitized}'.", "success"
	except ValueError as exc:
		# Revert when strict mode rejects unresolved entries.
		_resolve_and_store(sess, inputs, normalized_mode, commander_tags)
		return None, str(exc), "error"


def remove_theme(
	sess: Dict[str, Any],
	value: str | None,
	*,
	commander_tags: Iterable[str],
	mode: str | None,
) -> Tuple[ThemeResolutionInfo | None, str, str]:
	normalized_mode = normalize_theme_match_mode(mode)
	inputs = _current_inputs(sess)
	if not inputs:
		return None, "No themes to remove.", "info"
	key = (value or "").strip().casefold()
	if not key:
		return None, "Select a theme to remove.", "error"
	filtered = [item for item in inputs if item.casefold() != key]
	if len(filtered) == len(inputs):
		return None, "Theme not found in your list.", "warning"
	info = _resolve_and_store(sess, filtered, normalized_mode, commander_tags)
	return info, "Theme removed.", "success"


def choose_suggestion(
	sess: Dict[str, Any],
	original: str,
	selection: str,
	*,
	commander_tags: Iterable[str],
	mode: str | None,
) -> Tuple[ThemeResolutionInfo | None, str, str]:
	normalized_mode = normalize_theme_match_mode(mode)
	inputs = _current_inputs(sess)
	orig_key = (original or "").strip().casefold()
	if not orig_key:
		return None, "Original theme missing.", "error"
	sanitized = _sanitize_single(selection)
	if not sanitized:
		return None, "Select a suggestion to apply.", "error"
	try:
		index = next(i for i, item in enumerate(inputs) if item.casefold() == orig_key)
	except StopIteration:
		return None, "Original theme not found.", "warning"
	replacement_key = sanitized.casefold()
	if replacement_key in {item.casefold() for i, item in enumerate(inputs) if i != index}:
		# Duplicate suggestion: simply drop the original.
		updated = [item for i, item in enumerate(inputs) if i != index]
		message = f"Removed duplicate theme '{original}'."
	else:
		updated = list(inputs)
		updated[index] = sanitized
		message = f"Updated '{original}' to '{sanitized}'."
	info = _resolve_and_store(sess, updated, normalized_mode, commander_tags)
	return info, message, "success"


def set_mode(
	sess: Dict[str, Any],
	mode: str,
	*,
	commander_tags: Iterable[str],
) -> Tuple[ThemeResolutionInfo | None, str, str]:
	new_mode = normalize_theme_match_mode(mode)
	current_inputs = _current_inputs(sess)
	previous_mode = sess.get(_MODE_KEY)
	try:
		info = _resolve_and_store(sess, current_inputs, new_mode, commander_tags)
		return info, f"Theme matching set to {new_mode} mode.", "success"
	except ValueError as exc:
		if previous_mode is not None:
			sess[_MODE_KEY] = previous_mode
		return None, str(exc), "error"


def clear_all(sess: Dict[str, Any]) -> None:
	for key in (_INPUTS_KEY, _RESOLUTION_KEY, "additional_themes", _LAST_ADD_KEY):
		if key in sess:
			del sess[key]


def refresh_resolution(
	sess: Dict[str, Any],
	*,
	commander_tags: Iterable[str],
	mode: str | None = None,
) -> ThemeResolutionInfo | None:
	inputs = _current_inputs(sess)
	normalized_mode = normalize_theme_match_mode(mode or sess.get(_MODE_KEY))
	if not inputs:
		empty = ThemeResolutionInfo(
			requested=[],
			mode=normalized_mode,
			catalog_version=sess.get(_CATALOG_VERSION_KEY, "unknown"),
			resolved=[],
			matches=[],
			unresolved=[],
			fuzzy_corrections={},
		)
		_store_inputs(sess, [])
		_store_resolution(sess, empty)
		return empty
	info = _resolve_and_store(sess, inputs, normalized_mode, commander_tags)
	return info

