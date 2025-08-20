from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
"""Phase 0: Core primitives & shared definitions extracted from monolithic builder.

This phase lifts out lightweight, low‑risk items that have no external
side effects and are broadly reused across the deck building pipeline:

Contents:
  * Fuzzy matching backend selection & helpers (_full_ratio, _top_matches)
  * Basic scoring thresholds (EXACT_NAME_THRESHOLD, FIRST_WORD_THRESHOLD, MAX_PRESENTED_CHOICES)
  * BracketDefinition dataclass and BRACKET_DEFINITIONS list (power bracket taxonomy)

The original imports and symbol names are preserved so existing code in
builder.py can import:
    from .phases.phase0_core import (
        _full_ratio, _top_matches,
        EXACT_NAME_THRESHOLD, FIRST_WORD_THRESHOLD, MAX_PRESENTED_CHOICES,
        BracketDefinition, BRACKET_DEFINITIONS
    )

No behavior change intended.
"""

# Attempt to use a fast fuzzy library; fall back gracefully
try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz  # type: ignore
    _FUZZ_BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover - environment dependent
    try:
        from fuzzywuzzy import process as fw_process, fuzz as fw_fuzz  # type: ignore
        _FUZZ_BACKEND = "fuzzywuzzy"
    except ImportError:  # pragma: no cover
        _FUZZ_BACKEND = "difflib"

if _FUZZ_BACKEND == "rapidfuzz":
    def _full_ratio(a: str, b: str) -> float:
        return rf_fuzz.ratio(a, b)
    def _top_matches(query: str, choices: List[str], limit: int):
        return [(name, int(score)) for name, score, _ in rf_process.extract(query, choices, limit=limit)]
elif _FUZZ_BACKEND == "fuzzywuzzy":
    def _full_ratio(a: str, b: str) -> float:
        return fw_fuzz.ratio(a, b)
    def _top_matches(query: str, choices: List[str], limit: int):
        return fw_process.extract(query, choices, limit=limit)
else:
    from difflib import SequenceMatcher, get_close_matches
    def _full_ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    def _top_matches(query: str, choices: List[str], limit: int):
        close = get_close_matches(query, choices, n=limit, cutoff=0.0)
        scored = [(c, int(_full_ratio(query, c))) for c in close]
        if len(scored) < limit:
            remaining = [c for c in choices if c not in close]
            extra = sorted(
                ((c, int(_full_ratio(query, c))) for c in remaining),
                key=lambda x: x[1],
                reverse=True
            )[: limit - len(scored)]
            scored.extend(extra)
        return scored

EXACT_NAME_THRESHOLD = 80
FIRST_WORD_THRESHOLD = 75
MAX_PRESENTED_CHOICES = 5

@dataclass(frozen=True)
class BracketDefinition:
    level: int
    name: str
    short_desc: str
    long_desc: str
    limits: Dict[str, Optional[int]]  # None = unlimited

BRACKET_DEFINITIONS: List[BracketDefinition] = [
    BracketDefinition(
        1,
        "Exhibition",
        "Ultra-casual / novelty; long games; focus on fun.",
        ("Throw down with your ultra‑casual deck. Winning isn't primary—show off something unusual. "
         "Games go long and end slowly."),
        {
            "game_changers": 0,
            "mass_land_denial": 0,
            "extra_turns": 0,
            "tutors_nonland": 3,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        2,
        "Core",
        "Precon baseline; splashy turns; 9+ turn games.",
        ("Average modern precon: tuned engines & splashy turns, some pet/theme cards, usually longer games."),
        {
            "game_changers": 0,
            "mass_land_denial": 0,
            "extra_turns": 3,
            "tutors_nonland": 3,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        3,
        "Upgraded",
        "Refined beyond precon; faster; selective power.",
        ("Carefully selected cards; may include up to three Game Changers. Avoids cheap fast infinite two‑card combos."),
        {
            "game_changers": 3,
            "mass_land_denial": 0,
            "extra_turns": 3,
            "tutors_nonland": None,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        4,
        "Optimized",
        "High power, explosive, not meta-focused.",
        ("Strong, explosive builds; any number of powerful effects, tutors, combos, and denial."),
        {
            "game_changers": None,
            "mass_land_denial": None,
            "extra_turns": None,
            "tutors_nonland": None,
            "two_card_combos": None
        }
    ),
    BracketDefinition(
        5,
        "cEDH",
        "Competitive, meta-driven mindset.",
        ("Metagame/tournament mindset; precision choices; winning prioritized over expression."),
        {
            "game_changers": None,
            "mass_land_denial": None,
            "extra_turns": None,
            "tutors_nonland": None,
            "two_card_combos": None
        }
    ),
]

__all__ = [
    '_full_ratio', '_top_matches',
    'EXACT_NAME_THRESHOLD', 'FIRST_WORD_THRESHOLD', 'MAX_PRESENTED_CHOICES',
    'BracketDefinition', 'BRACKET_DEFINITIONS'
]
