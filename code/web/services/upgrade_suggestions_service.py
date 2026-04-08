"""Upgrade suggestions service — surfaces new-card upgrade candidates.

M1: new-card detection service.  Reads ``isNew`` from ``all_cards.parquet``
and cross-references set metadata from the local Scryfall bulk-data file so
callers get a fully-populated list of ``UpgradeCandidate`` objects.

M2: swap candidate scorer.  Given an upgrade candidate and the current deck
card list, returns the deck cards most worth swapping out, with scoring
based on role overlap, CMC, and role breadth.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from code.path_util import card_files_raw_dir, get_processed_cards_path
from code import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

_BULK_DATA_FILENAME = "scryfall_bulk_data.json"
_SET_META_TTL_SECONDS = 3600  # 1 hour


@dataclass
class UpgradeCandidate:
    """A card from the new-card window that could upgrade the current deck.

    Attributes:
        name: Card name (or face name for double-faced cards).
        roles: Theme-tag labels from all_cards.parquet (may be empty for
               brand-new sets not yet tagged by the pipeline).
        cmc: Converted mana cost from the parquet.
        set_code: Scryfall set code (uppercase, e.g. ``"TLA"``).
        set_name: Human-readable set name (e.g. ``"The Lost Aisle"``).
        released_at: ISO date string when the set was released (``"YYYY-MM-DD"``).
        is_new_card: Always ``True`` for candidates returned by this service.
    """

    name: str
    roles: list[str]
    cmc: float
    set_code: str
    set_name: str
    released_at: str
    is_new_card: bool = field(default=True)
    matched_tags: list[str] = field(default_factory=list)
    swap_candidates: list[SwapCandidate] = field(default_factory=list)
    fit_score: float = 0.0


@dataclass
class DeckCard:
    """A card currently in the deck, used as input to swap scoring.

    Attributes:
        name: Card name.
        roles: Theme-tag labels (may be empty).
        cmc: Converted mana cost.
        is_commander: If ``True`` this card is never a swap candidate.
        is_locked: If ``True`` this card is never a swap candidate.
        card_type: Raw type line (used to detect lands).
    """

    name: str
    roles: list[str]
    cmc: float
    is_commander: bool = field(default=False)
    is_locked: bool = field(default=False)
    card_type: str = field(default="")


@dataclass
class SwapCandidate:
    """A deck card scored as a swap target for an upgrade candidate.

    Attributes:
        name: Card name.
        roles: Theme-tag labels.
        cmc: Converted mana cost.
        swap_score: Higher = better swap target.
        reason: Human-readable explanation, e.g.
                ``"Fills same Ramp role; high CMC (5)"``.
    """

    name: str
    roles: list[str]
    cmc: float
    swap_score: float
    reason: str


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

_ROLE_OVERLAP_WEIGHT = 3.0
_CMC_WEIGHT = 0.5
_CMC_IMPROVEMENT_WEIGHT = 1.5   # bonus per CMC saved by the replacement
_ROLE_BREADTH_PENALTY = 1.0
_QUALITY_BONUS = 0.3
DEFAULT_TOP_N = 3
_DFC_CMC_BUMP = 1.5             # effective CMC reduction for DFC deck cards in swap scoring

# Ideal role categories: maps deck-config keys to the parquet themeTags they represent.
# "lands", "basic_lands", and "fetch_lands" are intentionally omitted — land cards are
# never returned as upgrade candidates.
_IDEAL_KEY_TO_TAGS: dict[str, frozenset[str]] = {
    "ramp":           frozenset({"Ramp", "Mana Dork", "Mana Rock"}),
    "removal":        frozenset({"Removal", "Spot Removal", "Interaction"}),
    "wipes":          frozenset({"Board Wipes"}),
    "card_advantage": frozenset({"Card Draw", "Unconditional Draw", "Card Advantage"}),
    "protection":     frozenset({"Protective Effects"}),
}
_DEFAULT_IDEAL_ROLE_TAGS: frozenset[str] = frozenset(
    t for tags in _IDEAL_KEY_TO_TAGS.values() for t in tags
)


def _str_val(v: object) -> str:
    """Convert a value (including pandas NaN) to a non-'nan' string."""
    if v is None:
        return ""
    s = str(v)
    return "" if s == "nan" else s


def _parse_tags(tags_raw: object) -> list[str]:
    """Parse themeTags from any storage format into a clean list of strings.

    Handles:
    - numpy arrays / array-like objects with a ``tolist()`` method
    - plain Python list/tuple
    - comma-separated string (legacy CSV format)
    - anything else: returns []
    """
    # numpy array or similar
    if hasattr(tags_raw, "tolist"):
        tags_raw = tags_raw.tolist()
    if isinstance(tags_raw, (list, tuple)):
        return [str(t) for t in tags_raw if t is not None and str(t) not in ("", "nan")]
    s = _str_val(tags_raw)
    if s:
        return [t.strip() for t in s.split(",") if t.strip()]
    return []


def _is_land_type(type_val: object) -> bool:
    """Return True if the card's type line identifies it as a land.

    Checks the primary type part (before the em-dash), so basic lands
    ("Basic Land — Forest"), legendary lands, and artifact lands all match.
    Non-land MDFC back faces are excluded by their own row in the parquet
    having a non-Land primary type.
    """
    s = _str_val(type_val).lower()
    primary = s.split("—")[0].strip()
    return "land" in primary


class UpgradeSuggestionsService:
    """Service for generating card upgrade suggestions from the new-card window.

    Reads ``isNew`` from ``all_cards.parquet`` (already computed by the setup
    pipeline) so it never re-derives the window — it delegates that logic to
    the existing pipeline.  Set metadata (set name, release date) is loaded
    from the local Scryfall bulk-data file on first call and cached in memory
    for up to one hour.

    All public methods are thread-safe.
    """

    def __init__(
        self,
        *,
        bulk_data_path: Optional[str] = None,
        window_months: int = 6,
    ) -> None:
        self._bulk_path: str = bulk_data_path or os.path.join(
            card_files_raw_dir(), _BULK_DATA_FILENAME
        )
        self._window_months = window_months
        self._lock = threading.RLock()
        # set_code → {"name": str, "released_at": str, "set_type": str}
        self._set_meta: dict[str, dict] = {}
        self._set_meta_loaded = False
        self._set_meta_ts: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_set_meta(self) -> None:
        """Load (or refresh) the set-metadata cache if stale."""
        import time
        now = time.time()
        with self._lock:
            if self._set_meta_loaded and (now - self._set_meta_ts) < _SET_META_TTL_SECONDS:
                return
            self._set_meta = self._load_set_meta()
            self._set_meta_loaded = True
            self._set_meta_ts = now

    def _load_set_meta(self) -> dict:
        """Single-pass scan of bulk data → ``set_code: {name, released_at, set_type}``.

        Only the first card encountered per set code is used.  In practice all
        cards within a Scryfall set share the same ``released_at`` and
        ``set_name`` values, so this is safe.
        """
        meta: dict = {}
        if not os.path.exists(self._bulk_path):
            logger.warning("Bulk data not found — set metadata unavailable: %s", self._bulk_path)
            return meta
        try:
            with open(self._bulk_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip().rstrip(",")
                    if not line or line in ("[", "]"):
                        continue
                    try:
                        card = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sc = card.get("set", "")
                    if sc and sc not in meta:
                        meta[sc] = {
                            "name": card.get("set_name", sc.upper()),
                            "released_at": card.get("released_at", ""),
                            "set_type": card.get("set_type", ""),
                        }
        except Exception as exc:
            logger.warning("Error loading set metadata: %s", exc)
        return meta

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_new_card_window(
        self, today: Optional[datetime.date] = None
    ) -> tuple[list[str], datetime.date, str]:
        """Determine the active new-card window.

        Uses the same algorithm as the setup pipeline (last 3 distinct
        expansion/commander set dates, plus a rolling cutoff) but derives
        expansion windows from the in-memory set-metadata cache rather than
        re-scanning the bulk file.

        Args:
            today: Date anchor (default: ``datetime.date.today()``).  Pass an
                   explicit value in tests to keep results deterministic.

        Returns:
            A 3-tuple ``(set_codes, rolling_cutoff, label)`` where:

            - ``set_codes`` is a list of set-code strings whose release date
              falls within the last-3-expansion window.
            - ``rolling_cutoff`` is ``today - window_months * 30 days``.
            - ``label`` is a human-readable description, e.g.
              ``"TLA, ECL, TMT (Nov 2025 – Mar 2026)"``.
        """
        if today is None:
            today = datetime.date.today()
        rolling_cutoff = today - datetime.timedelta(days=self._window_months * 30)

        self._ensure_set_meta()

        # Collect non-future expansion/commander sets and their release dates.
        expansion_sets: dict[str, datetime.date] = {}
        for sc, m in self._set_meta.items():
            if m.get("set_type") in ("expansion", "commander") and m.get("released_at"):
                try:
                    d = datetime.date.fromisoformat(m["released_at"])
                    if d <= today:
                        expansion_sets[sc] = d
                except ValueError:
                    pass

        # Last 3 distinct dates → window set codes.
        all_dates = sorted(set(expansion_sets.values()), reverse=True)
        window_dates = set(all_dates[:3])
        window_codes = [sc for sc, d in expansion_sets.items() if d in window_dates]

        # Build a human-readable label using set names grouped by release date.
        # Include ALL expansion/commander sets within the rolling window (>= rolling_cutoff),
        # not just the last-3-date codes, so sets like TLA that enter via the rolling
        # window appear in the label even if they predate the last-3 expansion dates.
        # Prefer the expansion set name over companion commander set when they share a date.
        all_window_sets: dict[str, datetime.date] = {
            sc: d for sc, d in expansion_sets.items() if d >= rolling_cutoff
        }
        label_sets = all_window_sets or {sc: expansion_sets[sc] for sc in window_codes}
        if label_sets:
            date_to_name: dict[datetime.date, str] = {}
            for sc, d in label_sets.items():
                m = self._set_meta.get(sc, {})
                stype = m.get("set_type", "")
                sname = m.get("name", sc.upper())
                if d not in date_to_name or stype == "expansion":
                    date_to_name[d] = sname
            names_sorted = [date_to_name[d] for d in sorted(date_to_name.keys())]
            effective_oldest = min(label_sets.values())
            effective_newest = max(label_sets.values())
            label = "{} ({} \u2013 {})".format(
                ", ".join(names_sorted),
                effective_oldest.strftime("%b %Y"),
                effective_newest.strftime("%b %Y"),
            )
        else:
            label = f"Rolling {self._window_months}-month window"

        return window_codes, rolling_cutoff, label

    def get_new_card_pool(
        self,
        color_identity: list[str],
        deck_themes: Optional[list[str]] = None,
        min_tag_overlap: int = 1,
        today: Optional[datetime.date] = None,
        max_per_niche_theme: int = 3,
        max_per_niche_util: int = 2,
        max_pool: int = 30,
        deck_card_names: Optional[set[str]] = None,
    ) -> list[UpgradeCandidate]:
        """Return new cards that fit within the given commander color identity.

        Reads ``isNew`` from ``all_cards.parquet`` (no bulk-data scan needed
        for the main list).  Set metadata is loaded from the bulk-data cache
        to populate ``set_name`` and ``released_at`` on each candidate.

        Args:
            color_identity: Color codes the commander allows,
                e.g. ``["G", "U", "W"]``.  An empty list means colorless-only
                (only cards with no color identity qualify).
            today: Date anchor for excluding future-dated set metadata entries.
                   Defaults to ``datetime.date.today()``.

        Returns:
            ``list[UpgradeCandidate]`` sorted by ``edhrecRank`` ascending
            (most popular first).  Gracefully returns ``[]`` if the parquet
            is missing or the ``isNew`` column is absent.
        """
        if today is None:
            today = datetime.date.today()

        self._ensure_set_meta()

        processed_path = get_processed_cards_path()
        if not os.path.exists(processed_path):
            logger.warning("Parquet not found — returning empty pool: %s", processed_path)
            return []

        try:
            df = pd.read_parquet(processed_path)
        except Exception as exc:
            logger.warning("Error reading parquet: %s", exc)
            return []

        if "isNew" not in df.columns:
            logger.warning("isNew column missing from parquet — returning empty pool")
            return []

        # Filter to new cards only.
        new_df = df[df["isNew"].fillna(False).astype(bool)].copy()
        if new_df.empty:
            return []

        # Filter out land-type cards.  Non-land faces of MDFCs are kept because
        # their own parquet row has a non-Land primary type.
        if "type" in new_df.columns:
            new_df = new_df[~new_df["type"].apply(_is_land_type)]
        if new_df.empty:
            return []

        # Color-identity filter: card's colors must be a subset of allowed.
        allowed = set(color_identity)

        def _color_ok(ci_str: object) -> bool:
            s = _str_val(ci_str)
            if not s:
                return True  # colorless/no-identity cards fit any deck
            card_colors = {c.strip() for c in s.split(",") if c.strip()}
            return card_colors <= allowed

        new_df = new_df[new_df["colorIdentity"].apply(_color_ok)]
        if new_df.empty:
            return []

        # Exclude cards already in the deck (case-insensitive on both name and faceName).
        if deck_card_names:
            lower_deck = {n.lower() for n in deck_card_names}
            new_df = new_df[
                ~new_df.apply(
                    lambda r: (
                        _str_val(r.get("faceName")).lower() in lower_deck
                        or _str_val(r.get("name")).lower() in lower_deck
                    ),
                    axis=1,
                )
            ]
            if new_df.empty:
                return []

        # Compute theme-relevance set — used for both filtering and matched_tags display.
        if deck_themes is not None:
            theme_allowed_lower: set[str] = (
                {t.lower() for t in deck_themes}
                | {t.lower() for t in _DEFAULT_IDEAL_ROLE_TAGS}
            )
        else:
            theme_allowed_lower = set()

        # Theme relevance filter: when deck_themes are provided, only keep cards that
        # share at least min_tag_overlap tags with the deck's chosen themes OR cover a
        # standard utility role (ramp, removal, wipes, card draw, protection).
        if theme_allowed_lower and "themeTags" in new_df.columns:
            new_df = new_df[new_df["themeTags"].apply(
                lambda raw: len({t.lower() for t in _parse_tags(raw)} & theme_allowed_lower) >= min_tag_overlap
            )]
            if new_df.empty:
                return []

        if "edhrecRank" in new_df.columns:
            new_df = new_df.sort_values("edhrecRank", na_position="last")

        results: list[UpgradeCandidate] = []
        seen_names: set[str] = set()
        for _, row in new_df.iterrows():
            face = _str_val(row.get("faceName"))
            name = face if face else _str_val(row.get("name"))
            if not name:
                continue
            if name in seen_names:
                continue
            seen_names.add(name)

            # Parse roles from comma-separated themeTags.
            roles = _parse_tags(row.get("themeTags", ""))
            matched_tags = [t for t in roles if t.lower() in theme_allowed_lower] if theme_allowed_lower else []

            cmc = float(row.get("manaValue") or 0.0)

            # Use the first printings entry as the set code.
            printings_raw = _str_val(row.get("printings"))
            set_codes_list = [s.strip() for s in printings_raw.split(",") if s.strip()]
            set_code = set_codes_list[0] if set_codes_list else ""

            sm = self._set_meta.get(set_code, {})
            set_name = sm.get("name", set_code.upper() if set_code else "Unknown")
            released_at = sm.get("released_at", "")

            # Defensive: skip cards whose set metadata places them in the future.
            if released_at:
                try:
                    if datetime.date.fromisoformat(released_at) > today:
                        continue
                except ValueError:
                    pass

            rank = row.get("edhrecRank")
            try:
                rank_f = float(rank) if rank is not None and str(rank) != "nan" else 30000.0
            except (TypeError, ValueError):
                rank_f = 30000.0
            fit_score = round(2.0 * len(matched_tags) + 1.0 / math.log10(rank_f + 10), 1)

            results.append(
                UpgradeCandidate(
                    name=name,
                    roles=roles,
                    matched_tags=matched_tags,
                    cmc=cmc,
                    set_code=set_code,
                    set_name=set_name,
                    released_at=released_at,
                    is_new_card=True,
                    fit_score=fit_score,
                )
            )

        # Niche deduplication: group by matched_tags fingerprint and keep only
        # the top N cards per unique role combination, where N depends on whether
        # the card overlaps a deck theme (higher cap) or is pure utility (lower cap).
        # Only applied when deck_themes are active (otherwise matched_tags is
        # always empty and all cards would collapse into the same niche bucket).
        # Sort by fit_score descending first so highest-synergy cards survive dedup.
        results.sort(key=lambda c: c.fit_score, reverse=True)
        if theme_allowed_lower:
            deck_themes_lower_set = {t.lower() for t in deck_themes} if deck_themes else set()
            niche_counts: dict[frozenset, int] = {}
            deduped: list[UpgradeCandidate] = []
            for c in results:  # sorted by fit_score descending
                key = frozenset(c.matched_tags)
                has_deck_theme = bool(deck_themes_lower_set & {t.lower() for t in c.matched_tags})
                cap = max_per_niche_theme if has_deck_theme else max_per_niche_util
                if niche_counts.get(key, 0) < cap:
                    deduped.append(c)
                    niche_counts[key] = niche_counts.get(key, 0) + 1
            results = deduped

        if max_pool > 0:
            results = results[:max_pool]

        return results

    # ------------------------------------------------------------------
    # M2: Swap candidate scoring
    # ------------------------------------------------------------------

    def score_swap_candidates(
        self,
        suggestion: UpgradeCandidate,
        deck_cards: list[DeckCard],
        top_n: int = DEFAULT_TOP_N,
    ) -> list[SwapCandidate]:
        """Rank deck cards as swap targets for the given upgrade candidate.

        Strategy depends on the upgrade's role profile:

        * **Single-role replacement** (suggestion has exactly 1 role):
          Prefer deck cards that share the same role at a *higher* CMC —
          the upgrade does the same job more efficiently.

        * **Multi-role upgrade** (suggestion has 2+ roles):

          - *Option B — direct upgrade*: deck card has all of the same roles
            at a higher CMC (strict improvement).
          - *Option A — consolidation*: deck card has fewer roles at a similar
            CMC (≥ suggestion_cmc × 0.75), so the upgrade replaces it while
            also filling additional roles.
          - *Partial overlap*: general role-count + CMC scoring.

        Exclusions (never returned):
        - ``is_commander == True``
        - ``is_locked == True``
        - lands (``card_type`` contains "land")

        Fallback: remaining slots filled by highest-CMC non-role-matched cards.
        """
        # Use matched_tags as the role basis when available — this restricts swap
        # target search to like-for-like replacements (same theme/utility role as
        # the reason the suggestion was recommended), not every tag the card carries.
        scoring_roles = suggestion.matched_tags if suggestion.matched_tags else suggestion.roles
        suggestion_roles = set(scoring_roles)
        is_single_role = len(suggestion_roles) == 1

        swappable = [
            c for c in deck_cards
            if not c.is_commander
            and not c.is_locked
            and "land" not in c.card_type.lower()
        ]

        if not swappable:
            return []

        scored: list[tuple[float, DeckCard, str]] = []
        for card in swappable:
            # Double-faced cards provide more value than their CMC suggests.
            # Reducing the effective cmc_delta makes them harder to flag as swap targets.
            dfc_adj = _DFC_CMC_BUMP if " // " in card.name else 0.0
            dfc_note = " (double-faced)" if dfc_adj else ""
            card_roles = set(card.roles)
            overlap = suggestion_roles & card_roles

            if not overlap:
                # No role match — CMC-only fallback weight; DFC cards score lower.
                eff = card.cmc - dfc_adj
                score = eff * _CMC_WEIGHT
                reason = f"no role match; high CMC ({int(card.cmc)})" if eff >= 4 else "no role match"

            elif is_single_role:
                # Single-role: reward cutting higher-CMC same-role cards.
                # DFC adjustment reduces effective savings to discourage swapping.
                cmc_delta = card.cmc - suggestion.cmc - dfc_adj
                score = _ROLE_OVERLAP_WEIGHT + max(0.0, cmc_delta) * _CMC_IMPROVEMENT_WEIGHT + _QUALITY_BONUS
                role = next(iter(suggestion_roles))
                if cmc_delta > 0:
                    saved = int(cmc_delta) if cmc_delta == int(cmc_delta) else round(cmc_delta, 1)
                    reason = f"Same {role}; saves {saved} mana{dfc_note}"
                else:
                    reason = f"Same {role}{dfc_note}"

            else:
                # Multi-role upgrade
                full_coverage = suggestion_roles <= card_roles  # card already does everything
                eff_cmc = card.cmc - dfc_adj  # effective CMC for threshold checks

                if full_coverage and eff_cmc > suggestion.cmc:
                    # Option B: direct upgrade — same roles at lower CMC
                    cmc_delta = eff_cmc - suggestion.cmc
                    score = (_ROLE_OVERLAP_WEIGHT * len(suggestion_roles) * 1.5
                             + cmc_delta * _CMC_IMPROVEMENT_WEIGHT + _QUALITY_BONUS)
                    roles_str = ", ".join(sorted(suggestion_roles)[:2])
                    reason = f"Direct upgrade: covers {roles_str} at lower CMC{dfc_note}"

                elif (len(card_roles) <= len(suggestion_roles)
                      and eff_cmc >= suggestion.cmc * 0.75):
                    # Option A: card has fewer/equal roles at similar CMC;
                    # upgrade covers those roles + more for roughly the same cost
                    score = _ROLE_OVERLAP_WEIGHT * 1.25 + eff_cmc * _CMC_WEIGHT * 0.25 + _QUALITY_BONUS
                    role_str = ", ".join(sorted(overlap)[:2])
                    reason = f"Upgrade covers {role_str} + adds roles{dfc_note}"

                else:
                    # Partial overlap — general scoring
                    score = len(overlap) * _ROLE_OVERLAP_WEIGHT + eff_cmc * _CMC_WEIGHT + _QUALITY_BONUS
                    shared = sorted(overlap)[:2]
                    suffix = " role" if len(overlap) == 1 else " roles"
                    reason = f"Shared {', '.join(shared)}{suffix}"
                    if eff_cmc >= 4:
                        reason += f"; high CMC ({int(card.cmc)}){dfc_note}"
                    elif dfc_note:
                        reason += dfc_note

            scored.append((score, card, reason))

        scored.sort(key=lambda t: (t[0], t[1].cmc), reverse=True)

        result: list[SwapCandidate] = []
        used_names: set[str] = set()

        for score, card, reason in scored:
            if len(result) >= top_n:
                break
            result.append(SwapCandidate(
                name=card.name,
                roles=card.roles,
                cmc=card.cmc,
                swap_score=round(score, 4),
                reason=reason,
            ))
            used_names.add(card.name)

        # Fallback: fill remaining slots sorted by highest effective CMC (DFC-adjusted).
        if len(result) < top_n:
            fallback_pool = sorted(
                [c for c in swappable if c.name not in used_names],
                key=lambda c: c.cmc - (_DFC_CMC_BUMP if " // " in c.name else 0.0),
                reverse=True,
            )
            for card in fallback_pool:
                if len(result) >= top_n:
                    break
                eff = card.cmc - (_DFC_CMC_BUMP if " // " in card.name else 0.0)
                score = eff * _CMC_WEIGHT
                result.append(SwapCandidate(
                    name=card.name,
                    roles=card.roles,
                    cmc=card.cmc,
                    swap_score=round(score, 4),
                    reason="no role match; CMC filler",
                ))

        return result

    # ------------------------------------------------------------------
    # M3: General upgrade suggestions
    # ------------------------------------------------------------------

    def get_general_suggestions(
        self,
        deck_card_names: set[str],
        color_identity: list[str],
        themes: list[str],
        role_counts: dict[str, int],
        budget_per_card: Optional[float] = None,
        today: Optional[datetime.date] = None,
        max_per_tier: int = 100,
    ) -> dict[str, list[UpgradeCandidate]]:
        """Return general upgrade candidates scored against the current deck.

        Cards already in the deck and ``isNew`` cards (covered by the new-card
        pool) are excluded.  Scoring:

        - ``theme_match``: 2.0 × count of deck themes that appear in the
          card's themeTags.
        - ``role_gap_bonus``: 1.5 × count of the card's roles that are
          under-represented in the deck (role_counts[role] < 5).
        - ``quality``: ``1.0 / log10(edhrecRank + 10)`` (lower rank = better).
        - ``total = theme_match + role_gap_bonus + quality``

        Results are bucketed by price tier when ``budget_per_card`` is set:
        - ``"Within Budget"``: price ≤ budget (first, expanded)
        - ``"Slightly Out of Budget"``: budget < price ≤ 2×budget
        - ``"Out of Budget"``: 2×budget < price ≤ 4×budget
        - Above 4×budget: excluded entirely

        When no budget is provided, all results are returned under
        ``"General Upgrades"``.

        Args:
            deck_card_names: Names of cards currently in the deck.
            color_identity: Color codes the commander allows.
            themes: Active theme tags for this deck.
            role_counts: Mapping of role → card count in the current deck.
            budget_per_card: Optional per-card budget in USD.
            today: Date anchor (default: ``datetime.date.today()``).
            max_per_tier: Maximum candidates returned per tier (default 100).

        Returns:
            ``dict[str, list[UpgradeCandidate]]`` keyed by tier label.
        """
        if today is None:
            today = datetime.date.today()

        processed_path = get_processed_cards_path()
        if not os.path.exists(processed_path):
            logger.warning("Parquet not found — returning empty general suggestions: %s", processed_path)
            return {}

        try:
            df = pd.read_parquet(processed_path)
        except Exception as exc:
            logger.warning("Error reading parquet for general suggestions: %s", exc)
            return {}

        # Exclude new cards (handled by new-card pool).
        if "isNew" in df.columns:
            df = df[~df["isNew"].fillna(False).astype(bool)]

        # Filter out land-type cards.  Non-land faces of MDFCs are kept because
        # their own parquet row has a non-Land primary type.
        if "type" in df.columns:
            df = df[~df["type"].apply(_is_land_type)]

        # Color-identity filter.
        allowed = set(color_identity)

        def _color_ok(ci_str: object) -> bool:
            s = _str_val(ci_str)
            if not s:
                return True
            card_colors = {c.strip() for c in s.split(",") if c.strip()}
            return card_colors <= allowed

        df = df[df["colorIdentity"].apply(_color_ok)]
        if df.empty:
            return {}

        # Exclude cards already in the deck (case-insensitive).
        lower_deck = {n.lower() for n in deck_card_names}
        if "faceName" in df.columns:
            df = df[
                ~df.apply(
                    lambda r: (
                        _str_val(r.get("faceName")).lower() in lower_deck
                        or _str_val(r.get("name")).lower() in lower_deck
                    ),
                    axis=1,
                )
            ]
        else:
            df = df[~df["name"].apply(lambda n: _str_val(n).lower() in lower_deck)]

        if df.empty:
            return {}

        deck_themes_lower = {t.lower() for t in themes if t}
        under_rep_roles = {role.lower() for role, cnt in role_counts.items() if cnt < 5}

        def _score_row(row: pd.Series) -> float:
            card_tags_lower = {t.lower() for t in _parse_tags(row.get("themeTags", ""))}

            theme_match = 2.0 * len(deck_themes_lower & card_tags_lower)
            role_gap_bonus = 1.5 * len(under_rep_roles & card_tags_lower)

            rank = row.get("edhrecRank")
            try:
                rank_f = float(rank) if rank is not None and str(rank) != "nan" else 30000.0
            except (TypeError, ValueError):
                rank_f = 30000.0
            quality = 1.0 / math.log10(rank_f + 10)

            return theme_match + role_gap_bonus + quality

        df = df.copy()
        df["_score"] = df.apply(_score_row, axis=1)
        df = df.sort_values("_score", ascending=False)

        self._ensure_set_meta()

        def _to_candidate(row: pd.Series) -> Optional[UpgradeCandidate]:
            face = _str_val(row.get("faceName"))
            name = face if face else _str_val(row.get("name"))
            if not name:
                return None

            roles = _parse_tags(row.get("themeTags", ""))

            cmc = float(row.get("manaValue") or 0.0)
            printings_raw = _str_val(row.get("printings"))
            set_codes_list = [s.strip() for s in printings_raw.split(",") if s.strip()]
            set_code = set_codes_list[0] if set_codes_list else ""
            sm = self._set_meta.get(set_code, {})
            set_name = sm.get("name", set_code.upper() if set_code else "Unknown")
            released_at = sm.get("released_at", "")

            all_relevant = deck_themes_lower | under_rep_roles
            matched = [t for t in roles if t.lower() in all_relevant]
            fit_score = round(float(row.get("_score", 0.0)), 1)
            return UpgradeCandidate(
                name=name,
                roles=roles,
                matched_tags=matched,
                cmc=cmc,
                set_code=set_code,
                set_name=set_name,
                released_at=released_at,
                is_new_card=False,
                fit_score=fit_score,
            )

        if budget_per_card and budget_per_card > 0:
            tiers: dict[str, list[UpgradeCandidate]] = {
                "Within Budget": [],
                "Slightly Out of Budget": [],
                "Out of Budget": [],
            }
            price_col = "price" if "price" in df.columns else ("usd" if "usd" in df.columns else None)
            for _, row in df.iterrows():
                if all(len(v) >= max_per_tier for v in tiers.values()):
                    break
                candidate = _to_candidate(row)
                if candidate is None:
                    continue
                price: Optional[float] = None
                if price_col:
                    try:
                        raw_price = row.get(price_col)
                        if raw_price is not None and str(raw_price) != "nan":
                            price = float(raw_price)
                    except (TypeError, ValueError):
                        price = None

                if price is None:
                    if len(tiers["Within Budget"]) < max_per_tier:
                        tiers["Within Budget"].append(candidate)
                elif price <= budget_per_card:
                    if len(tiers["Within Budget"]) < max_per_tier:
                        tiers["Within Budget"].append(candidate)
                elif price <= budget_per_card * 2:
                    if len(tiers["Slightly Out of Budget"]) < max_per_tier:
                        tiers["Slightly Out of Budget"].append(candidate)
                elif price <= budget_per_card * 4:
                    if len(tiers["Out of Budget"]) < max_per_tier:
                        tiers["Out of Budget"].append(candidate)
                # Above 4× budget: excluded entirely

            return {k: v for k, v in tiers.items() if v}
        else:
            general: list[UpgradeCandidate] = []
            for _, row in df.iterrows():
                if len(general) >= max_per_tier:
                    break
                candidate = _to_candidate(row)
                if candidate is not None:
                    general.append(candidate)
            return {"General Upgrades": general} if general else {}
