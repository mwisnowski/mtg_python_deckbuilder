"""Fuzzy matching utilities for supplemental theme selection."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, List, Sequence

from code.deck_builder.theme_catalog_loader import ThemeCatalogEntry

__all__ = [
    "normalize_theme",
    "ThemeScore",
    "ResolutionResult",
    "ThemeMatcher",
    "HIGH_MATCH_THRESHOLD",
    "ACCEPT_MATCH_THRESHOLD",
    "SUGGEST_MATCH_THRESHOLD",
]

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")

HIGH_MATCH_THRESHOLD = 90.0
ACCEPT_MATCH_THRESHOLD = 80.0
SUGGEST_MATCH_THRESHOLD = 60.0
MIN_QUERY_LENGTH = 3
MAX_SUGGESTIONS = 5


def normalize_theme(value: str) -> str:
    text = (value or "").strip()
    text = _SPACE_RE.sub(" ", text)
    return text.casefold()


@dataclass(frozen=True)
class _IndexedTheme:
    display: str
    normalized: str
    tokens: tuple[str, ...]
    trigrams: tuple[str, ...]


@dataclass(frozen=True)
class ThemeScore:
    theme: str
    score: float

    def rounded(self) -> float:
        return round(self.score, 4)


@dataclass(frozen=True)
class ResolutionResult:
    matched_theme: str | None
    score: float
    reason: str
    suggestions: List[ThemeScore]


def _tokenize(text: str) -> tuple[str, ...]:
    cleaned = _NON_ALNUM_RE.sub(" ", text)
    parts = [p for p in cleaned.split() if p]
    return tuple(parts)


def _trigrams(text: str) -> tuple[str, ...]:
    text = text.replace(" ", "_")
    if len(text) < 3:
        return tuple(text)
    extended = f"__{text}__"
    grams = [extended[i : i + 3] for i in range(len(extended) - 2)]
    return tuple(sorted(set(grams)))


def _build_index(entries: Sequence[ThemeCatalogEntry]) -> tuple[tuple[_IndexedTheme, ...], dict[str, set[int]]]:
    indexed: list[_IndexedTheme] = []
    trigram_map: dict[str, set[int]] = {}
    for idx, entry in enumerate(entries):
        norm = normalize_theme(entry.theme)
        tokens = _tokenize(norm)
        trigrams = _trigrams(norm)
        indexed.append(
            _IndexedTheme(
                display=entry.theme,
                normalized=norm,
                tokens=tokens,
                trigrams=trigrams,
            )
        )
        for gram in trigrams:
            trigram_map.setdefault(gram, set()).add(idx)
    return tuple(indexed), trigram_map


@dataclass
class _QueryInfo:
    normalized: str
    tokens: tuple[str, ...]
    trigrams: tuple[str, ...]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _similarity(query: _QueryInfo, candidate: _IndexedTheme) -> float:
    if not candidate.trigrams:
        return 0.0
    if query.normalized == candidate.normalized:
        return 100.0

    query_tokens = set(query.tokens)
    candidate_tokens = set(candidate.tokens)
    shared_tokens = len(query_tokens & candidate_tokens)
    token_base = max(len(query_tokens), len(candidate_tokens), 1)
    token_score = 100.0 * shared_tokens / token_base

    query_trigrams = set(query.trigrams)
    candidate_trigrams = set(candidate.trigrams)
    if not query_trigrams:
        trigram_score = 0.0
    else:
        intersection = len(query_trigrams & candidate_trigrams)
        union = len(query_trigrams | candidate_trigrams)
        trigram_score = 100.0 * intersection / union if union else 0.0

    seq_score = 100.0 * difflib.SequenceMatcher(None, query.normalized, candidate.normalized).ratio()
    distance = _levenshtein(query.normalized, candidate.normalized)
    max_len = max(len(query.normalized), len(candidate.normalized))
    distance_score = 100.0 * (1.0 - distance / max_len) if max_len else 0.0

    prefix_bonus = 5.0 if candidate.normalized.startswith(query.normalized) else 0.0
    token_prefix_bonus = 5.0 if candidate.tokens and query.tokens and candidate.tokens[0].startswith(query.tokens[0]) else 0.0
    token_similarity_bonus = 0.0
    if query.tokens and candidate.tokens:
        token_similarity_bonus = 5.0 * difflib.SequenceMatcher(None, query.tokens[0], candidate.tokens[0]).ratio()
    distance_bonus = 0.0
    if distance <= 2:
        distance_bonus = 10.0 - (3.0 * distance)

    score = (
        0.3 * trigram_score
        + 0.2 * token_score
        + 0.3 * seq_score
        + 0.2 * distance_score
        + prefix_bonus
        + token_prefix_bonus
        + distance_bonus
        + token_similarity_bonus
    )
    if distance <= 2:
        score = max(score, 85.0 - 5.0 * distance)
    return min(score, 100.0)


class ThemeMatcher:
    """Fuzzy matcher backed by a trigram index.

    On dev hardware (2025-10-02) resolving 20 queries against a 400-theme
    catalog completes in ≈0.65s (~0.03s per query) including Levenshtein
    scoring.
    """

    def __init__(self, entries: Sequence[ThemeCatalogEntry]):
        self._entries: tuple[_IndexedTheme, ...]
        self._trigram_index: dict[str, set[int]]
        self._entries, self._trigram_index = _build_index(entries)

    @classmethod
    def from_entries(cls, entries: Iterable[ThemeCatalogEntry]) -> "ThemeMatcher":
        return cls(list(entries))

    def resolve(self, raw_query: str, *, limit: int = MAX_SUGGESTIONS) -> ResolutionResult:
        normalized = normalize_theme(raw_query)
        if not normalized:
            return ResolutionResult(matched_theme=None, score=0.0, reason="empty_input", suggestions=[])

        query = _QueryInfo(
            normalized=normalized,
            tokens=_tokenize(normalized),
            trigrams=_trigrams(normalized),
        )

        if len(normalized.replace(" ", "")) < MIN_QUERY_LENGTH:
            exact = next((entry for entry in self._entries if entry.normalized == normalized), None)
            if exact:
                return ResolutionResult(
                    matched_theme=exact.display,
                    score=100.0,
                    reason="short_exact",
                    suggestions=[ThemeScore(theme=exact.display, score=100.0)],
                )
            return ResolutionResult(matched_theme=None, score=0.0, reason="input_too_short", suggestions=[])

        candidates = self._candidate_indexes(query)
        if not candidates:
            return ResolutionResult(matched_theme=None, score=0.0, reason="no_candidates", suggestions=[])

        scored: list[ThemeScore] = []
        seen: set[str] = set()
        for idx in candidates:
            entry = self._entries[idx]
            score = _similarity(query, entry)
            if score <= 0 or score < 20.0:
                continue
            if entry.display in seen:
                continue
            scored.append(ThemeScore(theme=entry.display, score=score))
            seen.add(entry.display)

        scored.sort(key=lambda item: (-item.score, item.theme.casefold(), item.theme))
        suggestions = scored[:limit]

        if not suggestions:
            return ResolutionResult(matched_theme=None, score=0.0, reason="no_match", suggestions=[])

        top = suggestions[0]
        if top.score >= HIGH_MATCH_THRESHOLD:
            return ResolutionResult(matched_theme=top.theme, score=top.score, reason="high_confidence", suggestions=suggestions)
        if top.score >= ACCEPT_MATCH_THRESHOLD:
            return ResolutionResult(matched_theme=top.theme, score=top.score, reason="accepted_confidence", suggestions=suggestions)
        if top.score >= SUGGEST_MATCH_THRESHOLD:
            return ResolutionResult(matched_theme=None, score=top.score, reason="suggestions", suggestions=suggestions)
        return ResolutionResult(matched_theme=None, score=top.score, reason="no_match", suggestions=suggestions)

    def _candidate_indexes(self, query: _QueryInfo) -> set[int]:
        if not query.trigrams:
            return set(range(len(self._entries)))
        candidates: set[int] = set()
        for gram in query.trigrams:
            candidates.update(self._trigram_index.get(gram, ()))
        return candidates or set(range(len(self._entries)))


@lru_cache(maxsize=128)
def build_matcher(entries: tuple[ThemeCatalogEntry, ...]) -> ThemeMatcher:
    return ThemeMatcher(entries)
