"""Budget evaluation service for deck cost analysis.

Evaluates a deck against a budget constraint, identifies over-budget cards,
finds cheaper alternatives (same tags + color identity, lower price), and
produces a BudgetReport with replacements, per-card breakdown, and a
pickups list for targeted acquisition.

Priority order (highest to lowest):
  exclude > include > budget > bracket

Include-list cards are never auto-replaced; their cost is reported separately
as ``include_budget_overage``.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Set

from code.web.services.base import BaseService
from code.web.services.price_service import PriceService, get_price_service
from code import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# Splurge tier ceilings as a fraction of the total budget.
# S = top 20 %, M = top 10 %, L = top 5 %
_TIER_FRACTIONS = {"S": 0.20, "M": 0.10, "L": 0.05}

# How many alternatives to return per card at most.
_MAX_ALTERNATIVES = 5

# Ordered broad MTG card types — first match wins for type detection.
_BROAD_TYPES = ("Land", "Creature", "Planeswalker", "Battle", "Enchantment", "Artifact", "Instant", "Sorcery")

# M8: Build stage category order and tag patterns for category spend breakdown.
CATEGORY_ORDER = ["Land", "Ramp", "Creature", "Card Draw", "Removal", "Wipe", "Protection", "Synergy", "Other"]
_CATEGORY_COLORS: Dict[str, str] = {
    "Land":       "#94a3b8",
    "Ramp":       "#34d399",
    "Creature":   "#fb923c",
    "Card Draw":  "#60a5fa",
    "Removal":    "#f87171",
    "Wipe":       "#dc2626",
    "Protection": "#06b6d4",
    "Synergy":    "#c084fc",
    "Other":      "#f59e0b",
}
# Creature is handled via broad_type fallback (after tag patterns), not listed here
_CATEGORY_PATTERNS: List[tuple] = [
    ("Land",       ["land"]),
    ("Ramp",       ["ramp", "mana rock", "mana dork", "mana acceleration", "mana production"]),
    ("Card Draw",  ["card draw", "draw", "card advantage", "cantrip", "looting", "cycling"]),
    ("Removal",    ["removal", "spot removal", "bounce", "exile"]),
    ("Wipe",       ["board wipe", "sweeper", "wrath"]),
    ("Protection", ["protection", "counterspell", "hexproof", "shroud", "indestructible", "ward"]),
    ("Synergy",    ["synergy", "combo", "payoff", "enabler"]),
]
def _fmt_price_label(price: float) -> str:
    """Short x-axis label for a histogram bin boundary."""
    if price <= 0:
        return "$0"
    if price < 1.0:
        return f"${price:.2f}"
    if price < 10.0:
        return f"${price:.1f}" if price != int(price) else f"${int(price)}"
    return f"${price:.0f}"


# Basic land names excluded from price histogram (their prices are ~$0 and skew the chart)
_BASIC_LANDS: frozenset = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes",
})

# Green → amber gradient for 10 histogram bins (cheap → expensive)
_HIST_COLORS = [
    "#34d399", "#3fda8e", "#5de087", "#92e77a", "#c4e66a",
    "#f0e05a", "#f5c840", "#f5ab2a", "#f59116", "#f59e0b",
]


def compute_price_category_breakdown(
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate per-card prices into build stage buckets for M8 stacked bar chart.

    Each item should have: {card, price, tags: list[str], broad_type (optional)}.
    Returns {"totals": {cat: float}, "colors": {cat: hex}, "total": float, "order": [...]}.
    """
    totals: Dict[str, float] = {cat: 0.0 for cat in CATEGORY_ORDER}
    for item in items:
        price = item.get("price")
        if price is None:
            continue
        tags_lower = [str(t).lower() for t in (item.get("tags") or [])]
        broad_type = str(item.get("broad_type") or "").lower()
        matched = "Other"
        # Land check first — use broad_type or tag
        if broad_type == "land" or any("land" in t for t in tags_lower):
            matched = "Land"
        else:
            for cat, patterns in _CATEGORY_PATTERNS[1:]:  # skip Land; Creature handled below
                if any(any(p in t for p in patterns) for t in tags_lower):
                    matched = cat
                    break
            else:
                if broad_type == "creature":
                    matched = "Creature"
        totals[matched] = round(totals[matched] + float(price), 2)

    grand_total = round(sum(totals.values()), 2)
    return {"totals": totals, "colors": _CATEGORY_COLORS, "total": grand_total, "order": CATEGORY_ORDER}


def compute_price_histogram(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute a 10-bin price distribution histogram for M8.

    Uses logarithmic bin boundaries when the price range spans >4x (typical for
    MTG decks) so cheap cards are spread across multiple narrow bins rather than
    all landing in bin 0.  Bar heights use sqrt scaling for a quick-glance view
    where even a bin with 1 card is still visibly present.

    Items: list of {card, price, ...}. Cards without price are excluded.
    Basic lands are excluded (their near-zero prices skew the distribution).
    Returns [] if fewer than 2 priced cards.
    Each entry: {label, range_min, range_max, x_label, count, pct, color, cards}.
    """
    priced_items = [
        item for item in items
        if item.get("price") is not None and item.get("card", "") not in _BASIC_LANDS
    ]
    prices = [float(item["price"]) for item in priced_items]
    if len(prices) < 2:
        return []

    min_p = min(prices)
    max_p = max(prices)

    def _card_entry(item: Dict[str, Any]) -> Dict[str, Any]:
        return {"name": item["card"], "price": float(item["price"])}

    if max_p == min_p:
        # All same price — single populated bin, rest empty
        all_cards = sorted([_card_entry(it) for it in priced_items], key=lambda c: c["price"])
        bins: List[Dict[str, Any]] = []
        for i in range(10):
            bins.append({
                "label": f"{min_p:.2f}",
                "range_min": min_p,
                "range_max": max_p,
                "x_label": _fmt_price_label(min_p) + "\u2013" + _fmt_price_label(max_p),
                "count": len(prices) if i == 0 else 0,
                "pct": 100 if i == 0 else 0,
                "color": _HIST_COLORS[i],
                "cards": all_cards if i == 0 else [],
            })
        return bins

    # Choose bin boundary strategy: log-scale when range spans >4x, else linear.
    # Clamp lower floor to 0.01 so log doesn't blow up on near-zero prices.
    log_floor = max(min_p, 0.01)
    use_log = (max_p / log_floor) > 4.0

    if use_log:
        log_lo = math.log(log_floor)
        log_hi = math.log(max(max_p, log_floor * 1.001))
        log_step = (log_hi - log_lo) / 10
        boundaries = [math.exp(log_lo + i * log_step) for i in range(11)]
        boundaries[0] = min(boundaries[0], min_p)  # don't drop cards below float rounding
        boundaries[10] = max_p  # prevent exp(log(x)) != x float drift from losing last card
    else:
        step = (max_p - min_p) / 10
        boundaries = [min_p + i * step for i in range(11)]

    max_count = 0
    raw_bins: List[Dict[str, Any]] = []
    for i in range(10):
        lo = boundaries[i]
        hi = boundaries[i + 1]
        if i < 9:
            bin_items = [it for it in priced_items if lo <= float(it["price"]) < hi]
        else:
            bin_items = [it for it in priced_items if lo <= float(it["price"]) <= hi]
        count = len(bin_items)
        max_count = max(max_count, count)
        raw_bins.append({
            "label": f"{lo:.2f}~{hi:.2f}",
            "range_min": round(lo, 2),
            "range_max": round(hi, 2),
            "x_label": _fmt_price_label(lo) + "\u2013" + _fmt_price_label(hi),
            "count": count,
            "color": _HIST_COLORS[i],
            "cards": sorted([_card_entry(it) for it in bin_items], key=lambda c: c["price"]),
        })

    # Sqrt scaling: a bin with 1 card still shows ~13% height vs ~2% with linear.
    # This gives a quick-glance shape without the tallest bar crushing small ones.
    sqrt_denom = math.sqrt(max_count) if max_count > 0 else 1.0
    for b in raw_bins:
        b["pct"] = round(math.sqrt(b["count"]) * 100 / sqrt_denom)

    return raw_bins


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Replacement record: {original, replacement, original_price, replacement_price, price_diff}
Replacement = Dict[str, Any]
# Pickup record: {card, price, tier, priority, tags}
Pickup = Dict[str, Any]
# BudgetReport schema (see class docstring for full spec)
BudgetReport = Dict[str, Any]


class BudgetEvaluatorService(BaseService):
    """Evaluate a deck list against a budget and suggest replacements.

    Requires access to a ``PriceService`` for price lookups and a card index
    for tag-based alternative discovery (loaded lazily from the Parquet file).

    Usage::

        svc = BudgetEvaluatorService()
        report = svc.evaluate_deck(
            decklist=["Sol Ring", "Mana Crypt", ...],
            budget_total=150.0,
            mode="soft",
            include_cards=["Mana Crypt"],  # exempt from replacement
        )
    """

    def __init__(self, price_service: Optional[PriceService] = None) -> None:
        super().__init__()
        self._price_svc = price_service or get_price_service()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_deck(
        self,
        decklist: List[str],
        budget_total: float,
        mode: str = "soft",
        *,
        card_ceiling: Optional[float] = None,
        region: str = "usd",
        foil: bool = False,
        include_cards: Optional[List[str]] = None,
        color_identity: Optional[List[str]] = None,
        legacy_fail_open: bool = True,
    ) -> BudgetReport:
        """Evaluate deck cost versus budget and produce a BudgetReport.

        Args:
            decklist: Card names in the deck (one entry per card slot, no
                duplicates for normal cards; include the same name once per slot
                for multi-copy cards).
            budget_total: Maximum total deck cost in USD (or EUR if ``region``
                is ``"eur"``).
            mode: ``"soft"`` — advisory only; ``"hard"`` — flags budget
                violations but does not auto-replace.
            card_ceiling: Optional per-card price cap.  Cards priced above this
                are flagged independently of the total.
            region: Price region — ``"usd"`` (default) or ``"eur"``.
            foil: If ``True``, compare foil prices.
            include_cards: Cards exempt from budget enforcement (never
                auto-flagged for replacement).
            color_identity: Commander color identity letters, e.g. ``["U","B"]``.
                Used to filter alternatives so they remain legal.
            legacy_fail_open: If ``True`` (default), cards with no price data
                are skipped in the budget calculation rather than causing an
                error.

        Returns:
            A ``BudgetReport`` dict with the following keys:

            - ``total_price`` — sum of all prices found
            - ``budget_status`` — ``"under"`` | ``"soft_exceeded"`` |
              ``"hard_exceeded"``
            - ``overage`` — amount over budget (0 if under)
            - ``include_budget_overage`` — cost from include-list cards
            - ``over_budget_cards`` — list of {card, price, ceiling_exceeded}
              for cards above ceiling or contributing most to overage
            - ``price_breakdown`` — per-card {card, price, is_include,
              ceiling_exceeded, stale}
            - ``stale_prices`` — cards whose price data may be outdated
            - ``pickups_list`` — priority-sorted acquisition suggestions
            - ``replacements_available`` — alternative cards for over-budget
              slots (excludes include-list cards)
        """
        self._validate(budget_total >= 0, "budget_total must be non-negative")
        self._validate(mode in ("soft", "hard"), "mode must be 'soft' or 'hard'")
        if card_ceiling is not None:
            self._validate(card_ceiling >= 0, "card_ceiling must be non-negative")

        include_set: Set[str] = {c.lower().strip() for c in (include_cards or [])}
        names = [n.strip() for n in decklist if n.strip()]
        prices = self._price_svc.get_prices_batch(names, region=region, foil=foil)

        total_price = 0.0
        include_overage = 0.0
        breakdown: List[Dict[str, Any]] = []
        over_budget_cards: List[Dict[str, Any]] = []
        stale: List[str] = []

        for card in names:
            price = prices.get(card)
            is_include = card.lower().strip() in include_set

            if price is None:
                if not legacy_fail_open:
                    raise ValueError(f"No price data for '{card}' and legacy_fail_open=False")
                stale.append(card)
                price_used = 0.0
            else:
                price_used = price

            ceil_exceeded = card_ceiling is not None and price_used > card_ceiling
            total_price += price_used

            if is_include:
                include_overage += price_used

            breakdown.append({
                "card": card,
                "price": price_used if price is not None else None,
                "is_include": is_include,
                "ceiling_exceeded": ceil_exceeded,
            })

            if ceil_exceeded and not is_include:
                over_budget_cards.append({
                    "card": card,
                    "price": price_used,
                    "ceiling_exceeded": True,
                })

        overage = max(0.0, total_price - budget_total)

        if overage == 0.0:
            status = "under"
        elif mode == "hard":
            status = "hard_exceeded"
        else:
            status = "soft_exceeded"

        # Compute replacements for over-budget / ceiling-exceeded cards
        replacements = self._find_replacements(
            over_budget_cards=over_budget_cards,
            all_prices=prices,
            include_set=include_set,
            card_ceiling=card_ceiling,
            region=region,
            foil=foil,
            color_identity=color_identity,
        )

        # Build pickups list from cards not in deck, sorted by priority tier
        pickups = self._build_pickups_list(
            decklist=names,
            region=region,
            foil=foil,
            budget_remaining=max(0.0, budget_total - total_price),
            color_identity=color_identity,
        )

        return {
            "total_price": round(total_price, 2),
            "budget_status": status,
            "overage": round(overage, 2),
            "include_budget_overage": round(include_overage, 2),
            "over_budget_cards": over_budget_cards,
            "price_breakdown": breakdown,
            "stale_prices": stale,
            "pickups_list": pickups,
            "replacements_available": replacements,
        }

    def find_cheaper_alternatives(
        self,
        card_name: str,
        max_price: float,
        *,
        region: str = "usd",
        foil: bool = False,
        color_identity: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        require_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find cards that share tags with *card_name* and cost ≤ *max_price*.

        Args:
            card_name: The card to find alternatives for.
            max_price: Maximum price for alternatives in the given region.
            region: Price region.
            foil: If ``True``, compare foil prices.
            color_identity: If given, filter to cards legal in this identity.
            tags: Tags to use for matching (skips lookup if provided).
            require_type: If given, only return cards whose type_line contains
                this string (e.g. "Land", "Creature"). Auto-detected from the
                card index when not provided.

        Returns:
            List of dicts ``{name, price, tags, shared_tags}`` sorted by most
            shared tags descending then price ascending, capped at
            ``_MAX_ALTERNATIVES``.
        """
        lookup_tags = tags or self._get_card_tags(card_name)
        if not lookup_tags:
            return []

        # Determine the broad card type for like-for-like filtering.
        source_type = require_type or self._get_card_broad_type(card_name)

        candidates: Dict[str, Dict[str, Any]] = {}  # name → candidate dict

        try:
            from code.web.services.card_index import get_tag_pool, maybe_build_index
            maybe_build_index()

            ci_set: Optional[Set[str]] = (
                {c.upper() for c in color_identity} if color_identity else None
            )

            for tag in lookup_tags:
                for card in get_tag_pool(tag):
                    name = card.get("name", "")
                    if not name or name.lower() == card_name.lower():
                        continue

                    # Like-for-like type filter (Land→Land, Creature→Creature, etc.)
                    if source_type:
                        type_line = card.get("type_line", "")
                        if source_type not in type_line:
                            continue

                    # Color identity check
                    if ci_set is not None:
                        card_colors = set(card.get("color_identity_list", []))
                        if card_colors and not card_colors.issubset(ci_set):
                            continue

                    if name not in candidates:
                        candidates[name] = {
                            "name": name,
                            "tags": card.get("tags", []),
                            "shared_tags": set(),
                        }
                    candidates[name]["shared_tags"].add(tag)

        except Exception as exc:
            logger.warning("Card index unavailable for alternatives: %s", exc)
            return []

        if not candidates:
            return []

        # Batch price lookup for all candidates
        candidate_names = list(candidates.keys())
        prices = self._price_svc.get_prices_batch(candidate_names, region=region, foil=foil)

        results = []
        for name, info in candidates.items():
            price = prices.get(name)
            if price is None or price > max_price:
                continue
            results.append({
                "name": name,
                "price": round(price, 2),
                "tags": info["tags"],
                "shared_tags": sorted(info["shared_tags"]),
            })

        # Sort by most shared tags first (most role-matched), then price ascending.
        results.sort(key=lambda x: (-len(x["shared_tags"]), x["price"]))
        return results[:_MAX_ALTERNATIVES]

    def calculate_tier_ceilings(self, total_budget: float) -> Dict[str, float]:
        """Compute splurge tier price ceilings from *total_budget*.

        S-tier = up to 20 % of budget per card slot
        M-tier = up to 10 %
        L-tier = up to 5 %

        Args:
            total_budget: Total deck budget.

        Returns:
            Dict ``{"S": float, "M": float, "L": float}``.
        """
        return {tier: round(total_budget * frac, 2) for tier, frac in _TIER_FRACTIONS.items()}

    def generate_pickups_list(
        self,
        decklist: List[str],
        budget_remaining: float,
        *,
        region: str = "usd",
        foil: bool = False,
        color_identity: Optional[List[str]] = None,
    ) -> List[Pickup]:
        """Generate a prioritized acquisition list of cards not in *decklist*.

        Finds cards that fit the color identity, share tags with the current
        deck, and cost ≤ *budget_remaining*, sorted by number of shared tags
        (most synergistic first).

        Args:
            decklist: Current deck card names.
            budget_remaining: Maximum price per card to include.
            region: Price region.
            foil: If ``True``, use foil prices.
            color_identity: Commander color identity for legality filter.

        Returns:
            List of pickup dicts sorted by synergy score (shared tags count).
        """
        return self._build_pickups_list(
            decklist=decklist,
            region=region,
            foil=foil,
            budget_remaining=budget_remaining,
            color_identity=color_identity,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_card_tags(self, card_name: str) -> List[str]:
        """Look up theme tags for a single card from the card index."""
        try:
            from code.web.services.card_index import maybe_build_index, _CARD_INDEX
            maybe_build_index()
            needle = card_name.lower()
            for cards in _CARD_INDEX.values():
                for c in cards:
                    if c.get("name", "").lower() == needle:
                        return list(c.get("tags", []))
        except Exception:
            pass
        return []

    def _get_card_broad_type(self, card_name: str) -> Optional[str]:
        """Return the first matching broad MTG type for a card (e.g. 'Land', 'Creature')."""
        try:
            from code.web.services.card_index import maybe_build_index, _CARD_INDEX
            maybe_build_index()
            needle = card_name.lower()
            for cards in _CARD_INDEX.values():
                for c in cards:
                    if c.get("name", "").lower() == needle:
                        type_line = c.get("type_line", "")
                        for broad in _BROAD_TYPES:
                            if broad in type_line:
                                return broad
                        return None
        except Exception:
            pass
        return None

    def _find_replacements(
        self,
        *,
        over_budget_cards: List[Dict[str, Any]],
        all_prices: Dict[str, Optional[float]],
        include_set: Set[str],
        card_ceiling: Optional[float],
        region: str,
        foil: bool,
        color_identity: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Find cheaper alternatives for over-budget (non-include) cards."""
        results = []
        for entry in over_budget_cards:
            card = entry["card"]
            price = entry["price"]
            if card.lower().strip() in include_set:
                continue
            max_alt_price = (card_ceiling - 0.01) if card_ceiling else max(0.0, price - 0.01)
            alts = self.find_cheaper_alternatives(
                card,
                max_price=max_alt_price,
                region=region,
                foil=foil,
                color_identity=color_identity,
            )
            if alts:
                results.append({
                    "original": card,
                    "original_price": price,
                    "alternatives": alts,
                })
        return results

    def _build_pickups_list(
        self,
        decklist: List[str],
        region: str,
        foil: bool,
        budget_remaining: float,
        color_identity: Optional[List[str]],
    ) -> List[Pickup]:
        """Build a ranked pickups list using shared-tag scoring."""
        if budget_remaining <= 0:
            return []

        deck_set = {n.lower() for n in decklist}

        # Collect all unique tags from the current deck
        deck_tags: Set[str] = set()
        try:
            from code.web.services.card_index import maybe_build_index, _CARD_INDEX
            maybe_build_index()

            for name in decklist:
                needle = name.lower()
                for cards in _CARD_INDEX.values():
                    for c in cards:
                        if c.get("name", "").lower() == needle:
                            deck_tags.update(c.get("tags", []))
                            break

            if not deck_tags:
                return []

            ci_set: Optional[Set[str]] = (
                {c.upper() for c in color_identity} if color_identity else None
            )

            # Score candidate cards not in deck by shared tags
            candidates: Dict[str, Dict[str, Any]] = {}
            for tag in deck_tags:
                for card in _CARD_INDEX.get(tag, []):
                    name = card.get("name", "")
                    if not name or name.lower() in deck_set:
                        continue
                    if ci_set:
                        card_colors = set(card.get("color_identity_list", []))
                        if card_colors and not card_colors.issubset(ci_set):
                            continue
                    if name not in candidates:
                        candidates[name] = {"name": name, "tags": card.get("tags", []), "score": 0}
                    candidates[name]["score"] += 1

        except Exception as exc:
            logger.warning("Could not build pickups list: %s", exc)
            return []

        if not candidates:
            return []

        # Price filter
        top_candidates = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:200]
        names = [c["name"] for c in top_candidates]
        prices = self._price_svc.get_prices_batch(names, region=region, foil=foil)

        tier_ceilings = self.calculate_tier_ceilings(budget_remaining)
        pickups: List[Pickup] = []

        for c in top_candidates:
            price = prices.get(c["name"])
            if price is None or price > budget_remaining:
                continue
            tier = "L"
            if price <= tier_ceilings["L"]:
                tier = "L"
            if price <= tier_ceilings["M"]:
                tier = "M"
            if price <= tier_ceilings["S"]:
                tier = "S"
            pickups.append({
                "card": c["name"],
                "price": round(price, 2),
                "tier": tier,
                "priority": c["score"],
                "tags": c["tags"],
            })

        # Sort: most synergistic first, then cheapest
        pickups.sort(key=lambda x: (-x["priority"], x["price"]))
        return pickups[:50]
