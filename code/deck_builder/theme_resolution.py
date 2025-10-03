"""Shared theme resolution utilities for supplemental user themes.

This module centralizes the fuzzy resolution logic so both the headless
runner and the web UI can reuse a consistent implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from deck_builder.theme_catalog_loader import load_theme_catalog
from deck_builder.theme_matcher import (
	build_matcher,
	normalize_theme,
)

__all__ = [
	"ThemeResolutionInfo",
	"normalize_theme_match_mode",
	"clean_theme_inputs",
	"parse_theme_list",
	"resolve_additional_theme_inputs",
]


@dataclass
class ThemeResolutionInfo:
	"""Captures the outcome of resolving user-supplied supplemental themes."""

	requested: List[str]
	mode: str
	catalog_version: str
	resolved: List[str]
	matches: List[Dict[str, Any]]
	unresolved: List[Dict[str, Any]]
	fuzzy_corrections: Dict[str, str]


def normalize_theme_match_mode(value: str | None) -> str:
	"""Normalize theme match mode inputs to ``strict`` or ``permissive``."""

	if value is None:
		return "permissive"
	text = str(value).strip().lower()
	if text in {"strict", "s"}:
		return "strict"
	return "permissive"


def clean_theme_inputs(values: Sequence[Any]) -> List[str]:
	"""Normalize, deduplicate, and filter empty user-provided theme strings."""

	cleaned: List[str] = []
	seen: set[str] = set()
	for value in values or []:
		try:
			text = str(value).strip()
		except Exception:
			continue
		if not text:
			continue
		key = text.casefold()
		if key in seen:
			continue
		seen.add(key)
		cleaned.append(text)
	return cleaned


def parse_theme_list(raw: str | None) -> List[str]:
	"""Parse CLI/config style theme lists separated by comma or semicolon."""

	if raw is None:
		return []
	try:
		text = str(raw)
	except Exception:
		return []
	text = text.strip()
	if not text:
		return []
	delimiter = ";" if ";" in text else ","
	parts = [part.strip() for part in text.split(delimiter)]
	return clean_theme_inputs(parts)


def resolve_additional_theme_inputs(
	requested: Sequence[str],
	mode: str,
	*,
	commander_tags: Iterable[str] = (),
) -> ThemeResolutionInfo:
	"""Resolve user-provided additional themes against the catalog.

	Args:
		requested: Raw user inputs.
		mode: Strictness mode (``strict`` aborts on unresolved themes).
		commander_tags: Tags already supplied by the selected commander; these
			are used to deduplicate resolved results so we do not re-add themes
			already covered by the commander selection.

	Returns:
		:class:`ThemeResolutionInfo` describing resolved and unresolved themes.

	Raises:
		ValueError: When ``mode`` is strict and one or more inputs cannot be
			resolved with sufficient confidence.
	"""

	normalized_mode = normalize_theme_match_mode(mode)
	cleaned_inputs = clean_theme_inputs(requested)
	entries, version = load_theme_catalog(None)

	if not cleaned_inputs:
		return ThemeResolutionInfo(
			requested=[],
			mode=normalized_mode,
			catalog_version=version,
			resolved=[],
			matches=[],
			unresolved=[],
			fuzzy_corrections={},
		)

	if not entries:
		unresolved = [
			{"input": raw, "reason": "catalog_missing", "score": 0.0, "suggestions": []}
			for raw in cleaned_inputs
		]
		if normalized_mode == "strict":
			raise ValueError(
				"Unable to resolve additional themes in strict mode: catalog unavailable"
			)
		return ThemeResolutionInfo(
			requested=cleaned_inputs,
			mode=normalized_mode,
			catalog_version=version,
			resolved=[],
			matches=[],
			unresolved=unresolved,
			fuzzy_corrections={},
		)

	matcher = build_matcher(tuple(entries))
	matches: List[Dict[str, Any]] = []
	unresolved: List[Dict[str, Any]] = []
	fuzzy: Dict[str, str] = {}
	for raw in cleaned_inputs:
		result = matcher.resolve(raw)
		suggestions = [
			{"theme": suggestion.theme, "score": float(round(suggestion.score, 4))}
			for suggestion in result.suggestions
		]
		if result.matched_theme:
			matches.append(
				{
					"input": raw,
					"matched": result.matched_theme,
					"score": float(round(result.score, 4)),
					"reason": result.reason,
					"suggestions": suggestions,
				}
			)
			if normalize_theme(raw) != normalize_theme(result.matched_theme):
				fuzzy[raw] = result.matched_theme
		else:
			unresolved.append(
				{
					"input": raw,
					"reason": result.reason,
					"score": float(round(result.score, 4)),
					"suggestions": suggestions,
				}
			)

	commander_set = {
		normalize_theme(tag)
		for tag in commander_tags
		if isinstance(tag, str) and tag.strip()
	}
	resolved: List[str] = []
	seen_resolved: set[str] = set()
	for match in matches:
		norm = normalize_theme(match["matched"])
		if norm in seen_resolved:
			continue
		if commander_set and norm in commander_set:
			continue
		resolved.append(match["matched"])
		seen_resolved.add(norm)

	if normalized_mode == "strict" and unresolved:
		parts: List[str] = []
		for item in unresolved:
			suggestion_text = ", ".join(
				f"{s['theme']} ({s['score']:.1f})" for s in item.get("suggestions", [])
			)
			if suggestion_text:
				parts.append(f"{item['input']} (suggestions: {suggestion_text})")
			else:
				parts.append(item["input"])
		raise ValueError(
			"Unable to resolve additional themes in strict mode: " + "; ".join(parts)
		)

	return ThemeResolutionInfo(
		requested=cleaned_inputs,
		mode=normalized_mode,
		catalog_version=version,
		resolved=resolved,
		matches=matches,
		unresolved=unresolved,
		fuzzy_corrections=fuzzy,
	)

