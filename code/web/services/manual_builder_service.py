"""Shared business logic for the manual deck builder (Roadmap 25).

Kept as plain-Python functions (not inline in routes/templates) so a future
mobile-parity API milestone can call the same logic instead of duplicating it.
"""
from __future__ import annotations

import csv as _csv
import json
import os
import re
from collections import Counter
from datetime import date as _date
from typing import Any, Dict, List, Optional

import pandas as pd

from deck_builder.builder import DeckBuilder
from deck_builder import builder_constants as bc
from deck_builder.builder_utils import (
    basic_land_names,
    compute_color_source_matrix,
    compute_pip_density,
    fetch_land_allowed_for_colors,
    parse_theme_tags,
)
from deck_builder.brackets_compliance import (
    banned_category_names,
    capped_category_names,
    evaluate_deck,
)
from settings import MULTIPLE_COPY_CARDS
from code.services.all_cards_loader import AllCardsLoader
from code.web.services.card_search import apply_extra_clauses, apply_parsed_search, parse_search_query
from code.web.services.deck_visibility import resolve_visibility_for_write
from code.web.services.upgrade_suggestions_service import _IDEAL_KEY_TO_TAGS
from code.web.services.price_service import get_price_service

# Role buckets for the role health bar's own independent tag-matching (M5),
# in priority order used by `_card_role` (a tag match wins over the generic
# On-Theme/Land fallback, e.g. a mana-dork creature is bucketed as Ramp, not
# On-Theme). NOT tied to the Milestone 11 display categories below.
POOL_ROLES: List[str] = [
    "Ramp", "Removal", "Card Draw", "Protection", "Board Wipe",
    "On-Theme", "Land", "Other",
]
_RAMP_TAGS = {t.lower() for t in _IDEAL_KEY_TO_TAGS["ramp"]}
_REMOVAL_TAGS = {t.lower() for t in _IDEAL_KEY_TO_TAGS["removal"]}
_CARD_DRAW_TAGS = {t.lower() for t in _IDEAL_KEY_TO_TAGS["card_advantage"]}
_PROTECTION_TAGS = {t.lower() for t in _IDEAL_KEY_TO_TAGS["protection"]}
_WIPES_TAGS = {t.lower() for t in _IDEAL_KEY_TO_TAGS["wipes"]}

# Protection-ability names the scope-detection tagging pipeline recognizes
# (see code/tagging/protection_scope_detection.py's PROTECTION_ABILITIES),
# used to read the `metadataTags` "{scope}: {ability}" entries below.
_PROTECTION_ABILITY_NAMES = {"protection", "ward", "hexproof", "shroud", "indestructible"}

_loader: Optional[AllCardsLoader] = None


def _get_loader() -> AllCardsLoader:
    """Shared cached AllCardsLoader instance -- a fresh `AllCardsLoader()`
    per call would force a full parquet reload each time (no class-level
    cache), which was adding multi-second delays to add/remove-card
    requests that look up several off-pool cards.

    Rebuilds when `AllCardsLoader` itself has been swapped (tests monkeypatch
    this module's `AllCardsLoader` reference with a fake loader per-test), so
    the cache never masks a monkeypatch or serves a stale class across tests.
    """
    global _loader
    if _loader is None or type(_loader) is not AllCardsLoader:
        _loader = AllCardsLoader()
    return _loader

# Milestone 11: categorized pool layout. Order matches display order (top to
# bottom / left to right in the table-of-contents).
CATEGORY_KEYS: List[str] = [
    "new", "on_brand", "related_synergy",
    "creatures", "instants", "sorceries", "utility_artifacts",
    "enchantments", "battles", "planeswalkers", "utility_lands",
    "mana_artifacts", "lands", "other",
    "ramp", "removal", "card_draw", "board_wipes", "protection",
]
CATEGORY_LABELS: Dict[str, str] = {
    "new": "New Cards",
    "on_brand": "On-Brand Cards",
    "related_synergy": "Related Synergy",
    "creatures": "Creatures",
    "instants": "Instants",
    "sorceries": "Sorceries",
    "utility_artifacts": "Utility Artifacts",
    "enchantments": "Enchantments",
    "battles": "Battles",
    "planeswalkers": "Planeswalkers",
    "utility_lands": "Utility Lands",
    "mana_artifacts": "Mana Artifacts",
    "lands": "Lands",
    "other": "Other",
    "ramp": "Ramp",
    "removal": "Removal",
    "card_draw": "Card Draw",
    "board_wipes": "Board Wipes",
    "protection": "Protection",
}
# Role-based categories (below) surface cards that fill a deck-building
# "ideal" (ramp/removal/card draw/board wipes/protection) regardless of
# theme or card type, so they're findable even when off-brand - unlike the
# type buckets, a card can appear in one of these AND its type bucket (e.g.
# a removal creature shows in both Removal and Creatures).
_CATEGORY_TO_ROLE: Dict[str, str] = {
    "ramp": "Ramp",
    "removal": "Removal",
    "card_draw": "Card Draw",
    "board_wipes": "Board Wipe",
    "protection": "Protection",
}
# "On-Brand Cards" is a hard-capped top-N showcase, not a paginated category.
_ON_BRAND_CAP = 20
_CATEGORY_PAGE_SIZE = 20
# Every other category is capped to a max recommendation pool, not just
# paginated indefinitely - these are meant to be curated suggestions, not
# an exhaustive list of every legal card.
_CATEGORY_MAX_CARDS = 50
# Tags that don't count as "utility" on a Land (baseline ramp/fixing/identity
# tags every land carries), used to split Lands from Utility Lands. "Lands
# Matter"/"Land Types Matter" are near-universal identity tags (present on
# ~100%/~21% of land cards respectively), not actual utility effects.
_LAND_BASELINE_TAGS = {t.lower() for t in _RAMP_TAGS} | {
    "fetchland", "alt fetchland", "lands matter", "land types matter",
}

# Cards exempt from the Commander singleton rule (basic lands, plus the small
# set of named "any number of cards named X" cards e.g. Relentless Rats) -
# these stay visible in the pool even after being added to the deck.
_BASIC_LAND_NAMES = basic_land_names()
_UNLIMITED_COPY_NAMES_LOWER = {n.lower() for n in MULTIPLE_COPY_CARDS}


def is_basic_land(name: str) -> bool:
    return name in _BASIC_LAND_NAMES


def is_unlimited_copy_card(name: str) -> bool:
    """True if `name` may appear any number of times in the deck (basic lands
    and the Commander-legal "any number of cards named X" exceptions), so it
    should never be hidden from the pool just because a copy is already in
    the deck.
    """
    return is_basic_land(name) or name.strip().lower() in _UNLIMITED_COPY_NAMES_LOWER


def resolve_color_identity(
    commander: str,
    secondary_commander: Optional[str] = None,
    background: Optional[str] = None,
    partner_enabled: bool = False,
) -> List[str]:
    """Return color identity letters (e.g. ['R', 'G']) for a commander.

    Accounts for partner/background pairing when enabled. Returns an empty
    list if the commander can't be found rather than raising, since this is
    used for session bookkeeping (not the build pipeline itself).
    """
    if not commander:
        return []
    tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    if partner_enabled and secondary_commander:
        from deck_builder.partner_selection import apply_partner_inputs

        combined = apply_partner_inputs(
            tmp,
            primary_name=commander,
            secondary_name=secondary_commander,
            background_name=background,
            feature_enabled=True,
        )
        if combined and hasattr(combined, "color_identity"):
            return list(combined.color_identity)
        return []
    df = tmp.load_commander_data()
    row = df[df["name"].astype(str) == commander]
    if row.empty:
        return []
    raw_ci = row.iloc[0].get("colorIdentity", "") or ""
    if isinstance(raw_ci, (list, tuple, set)):
        return [str(c).strip().upper() for c in raw_ci if str(c).strip()]
    raw_ci = str(raw_ci)
    if raw_ci.strip().lower() == "colorless":
        return []
    if "," in raw_ci:
        return [c.strip().strip("'[] ").upper() for c in raw_ci.split(",") if c.strip().strip("'[] ")]
    return [c.upper() for c in raw_ci if c.isalpha()]


def manual_session_state(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the manual-build session contract fields (roadmap_25 Key Contracts)."""
    budget_config = sess.get("budget_config") or {}
    return {
        "mode": sess.get("mode"),
        "commander": sess.get("commander"),
        "themes": list(sess.get("tags") or []),
        "color_identity": list(sess.get("color_identity") or []),
        "budget_total": budget_config.get("total"),
        "budget_per_card": budget_config.get("card_ceiling"),
        "bracket": sess.get("bracket"),
        "deck_cards": list(sess.get("deck_cards") or []),
        "edit_source_name": sess.get("edit_source_name"),
    }


# ---------------------------------------------------------------------------
# Milestone 2: browseable card pool
# ---------------------------------------------------------------------------

def _color_identity_subset(card_colors: Any, identity: set) -> bool:
    """True if `card_colors` (raw colorIdentity cell) is legal alongside a
    commander whose color identity is `identity`, i.e. the card's colors are
    a subset of the commander's. Mirrors DeckBuilder.setup_dataframes()'s
    `card_matches_identity` closure so the pool matches what the real
    auto-builder would consider legal.
    """
    if card_colors is None or (isinstance(card_colors, float) and pd.isna(card_colors)):
        return True
    if isinstance(card_colors, str):
        colors = {c.strip() for c in card_colors.split(",")} if card_colors else set()
    elif isinstance(card_colors, (list, tuple, set)):
        colors = set(card_colors)
    else:
        return True
    return colors.issubset(identity)


def _grants_protection_to_others(metadata_tags: Optional[List[str]]) -> bool:
    """True if `metadata_tags` shows evidence a card actually grants a
    protective ability to permanents beyond itself ("Your Permanents: X" or
    "Blanket: X" for X in Protection/Ward/Hexproof/Shroud/Indestructible).

    The broad "Protective Effects" themeTag (`_PROTECTION_TAGS`) alone isn't
    enough - it's applied to any card mentioning a protection keyword,
    including ones that only ever protect themselves (e.g. a creature with
    its own Ward, or a self-referential "put an indestructible counter on
    ~"), which shouldn't count toward a deck's Protection ideal/category.
    """
    for tag in metadata_tags or []:
        if ":" not in tag:
            continue
        scope, _, ability = tag.partition(":")
        if scope.strip().lower() in ("your permanents", "blanket") and ability.strip().lower() in _PROTECTION_ABILITY_NAMES:
            return True
    return False


def _card_role(
    type_line: Any,
    tags: List[str],
    has_theme_match: bool = False,
    metadata_tags: Optional[List[str]] = None,
) -> str:
    """Bucket a card into one of `POOL_ROLES` for the role health bar (M5).

    `has_theme_match` (whether the card matches one of the session's selected
    themes) decides between "On-Theme" and "Other" for creatures/planeswalkers
    that aren't Ramp/Removal/Card Draw/Protection/Board Wipe.
    """
    tl = str(type_line or "").lower()
    if "land" in tl:
        return "Land"
    tag_set = {t.lower() for t in tags}
    if tag_set & _RAMP_TAGS:
        return "Ramp"
    if tag_set & _REMOVAL_TAGS:
        return "Removal"
    if tag_set & _CARD_DRAW_TAGS:
        return "Card Draw"
    if tag_set & _WIPES_TAGS:
        return "Board Wipe"
    if tag_set & _PROTECTION_TAGS and _grants_protection_to_others(metadata_tags):
        return "Protection"
    if "creature" in tl or "planeswalker" in tl:
        return "On-Theme" if has_theme_match else "Other"
    return "Other"


# Deck-panel grouping order, mirroring the finished-deck summary's Type
# Summary precedence (`print_type_summary`/`build_deck_summary` in
# deck_builder/phases/phase6_reporting.py) so the in-progress deck list reads
# the same as the final export.
_DECK_TYPE_ORDER: List[str] = [
    "Battle", "Planeswalker", "Creature", "Instant", "Sorcery",
    "Artifact", "Enchantment", "Land", "Other",
]
_DECK_TYPE_LABELS: Dict[str, str] = {
    "Battle": "Battles",
    "Planeswalker": "Planeswalkers",
    "Creature": "Creatures",
    "Instant": "Instants",
    "Sorcery": "Sorceries",
    "Artifact": "Artifacts",
    "Enchantment": "Enchantments",
    "Land": "Lands",
    "Other": "Other",
}


def _deck_type_category(type_line: Any) -> str:
    """Classify a card's primary type for deck-panel grouping (see
    `_DECK_TYPE_ORDER`)."""
    tl = str(type_line or "").lower()
    if "battle" in tl:
        return "Battle"
    if "planeswalker" in tl:
        return "Planeswalker"
    if "creature" in tl:
        return "Creature"
    if "instant" in tl:
        return "Instant"
    if "sorcery" in tl:
        return "Sorcery"
    if "artifact" in tl:
        return "Artifact"
    if "enchantment" in tl:
        return "Enchantment"
    if "land" in tl:
        return "Land"
    return "Other"


def _card_role_labels(
    tags: List[str],
    theme_matches: List[str],
    metadata_tags: Optional[List[str]] = None,
) -> List[str]:
    """Every role/theme label to show next to a card in the deck panel:
    matched theme tag(s) first, then every ideal role (Ramp/Removal/Card
    Draw/Board Wipe/Protection) its tags satisfy. Unlike `_card_role`
    (single bucket for the health bar), a card can show more than one label
    here (e.g. a removal creature that's also on-theme). Deduped so a role
    that's also one of the deck's selected themes (e.g. a "Ramp"-themed
    deck's ramp spells) isn't listed twice.
    """
    labels = list(theme_matches)
    seen = {t.lower() for t in labels}
    tag_set = {t.lower() for t in tags}

    def _add(label: str, role_tags: set) -> None:
        if tag_set & role_tags and label.lower() not in seen:
            labels.append(label)
            seen.add(label.lower())

    _add("Ramp", _RAMP_TAGS)
    _add("Removal", _REMOVAL_TAGS)
    _add("Card Draw", _CARD_DRAW_TAGS)
    _add("Board Wipe", _WIPES_TAGS)
    if tag_set & _PROTECTION_TAGS and _grants_protection_to_others(metadata_tags) and "protection" not in seen:
        labels.append("Protection")
        seen.add("protection")
    return labels


def _land_is_utility(tags: List[str]) -> bool:
    """True if a Land card has a themeTag beyond baseline mana-fixing/ramp
    (e.g. Cycling, Sac Outlet) - splits Utility Lands from plain Lands.
    """
    tag_set = {t.lower() for t in tags}
    return bool(tag_set - _LAND_BASELINE_TAGS)


def _type_category(type_line: Any, tags: List[str]) -> str:
    """Bucket a card into ONE Milestone 11 type-based category, using
    Land > Creature > Planeswalker > Battle > Artifact > Instant > Sorcery >
    Enchantment precedence (mirrors `_card_role`'s land-first precedence).
    Returns "other" as a safety net for any type line none of these rules
    cover (shouldn't happen for legal Commander card types).
    """
    tl = str(type_line or "").lower()
    if "land" in tl:
        return "utility_lands" if _land_is_utility(tags) else "lands"
    if "creature" in tl:
        return "creatures"
    if "planeswalker" in tl:
        return "planeswalkers"
    if "battle" in tl:
        return "battles"
    if "artifact" in tl:
        tag_set = {t.lower() for t in tags}
        return "mana_artifacts" if (tag_set & _RAMP_TAGS) else "utility_artifacts"
    if "instant" in tl:
        return "instants"
    if "sorcery" in tl:
        return "sorceries"
    if "enchantment" in tl:
        return "enchantments"
    return "other"


def _merge_multi_face_pool_rows(pool: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-face rows for double-faced/split/adventure cards.

    `all_cards.parquet` stores one row per face for these cards (sharing an
    identical combined `name`, e.g. "Front // Back"), which otherwise makes
    the same physical card show up twice in the pool grid. Keeps the front
    face (`side == "a"`) when present, unioning `themeTags` across faces so
    theme/category matching still sees tags contributed by either side.
    """
    if "name" not in pool.columns:
        return pool
    dup_mask = pool["name"].astype(str).duplicated(keep=False)
    if not dup_mask.any():
        return pool

    has_side = "side" in pool.columns
    has_tags = "themeTags" in pool.columns
    keep_idx = []
    merged_tags: Dict[Any, List[str]] = {}
    grouped = pool[dup_mask].groupby(pool.loc[dup_mask, "name"].astype(str), sort=False)
    for _name, group in grouped:
        primary_idx = group.index[0]
        if has_side:
            front = group[group["side"].astype(str).str.lower() == "a"]
            if not front.empty:
                primary_idx = front.index[0]
        keep_idx.append(primary_idx)
        if has_tags:
            combined: List[str] = []
            seen: set = set()
            for tags in group["themeTags"]:
                for t in parse_theme_tags(tags):
                    if t not in seen:
                        seen.add(t)
                        combined.append(t)
            merged_tags[primary_idx] = combined

    drop_idx = set(pool.index[dup_mask]) - set(keep_idx)
    out = pool.drop(index=list(drop_idx)).copy()
    for idx, tags in merged_tags.items():
        out.at[idx, "themeTags"] = tags
    return out


def get_card_pool(sess: Dict[str, Any]) -> pd.DataFrame:
    """Return (and cache in `sess`) the commander's full color-legal card pool.

    Cards fully banned at the session's bracket (e.g. Game Changers at
    Bracket 1/2) are excluded outright, mirroring the color-identity filter.
    Cards allowed up to a positive cap (e.g. up to 3 Game Changers at
    Bracket 3) stay in the pool with a `_bracket_tags` label for the UI.

    Cached under a private session key since a manual-build session's
    commander/color identity/bracket never change after creation.
    """
    cached = sess.get("_pool_df")
    if cached is not None:
        return cached

    identity = set(sess.get("color_identity") or [])
    commander = sess.get("commander")
    bracket = str(sess.get("bracket") or 2)

    df = _get_loader().load()
    mask = df["colorIdentity"].apply(lambda c: _color_identity_subset(c, identity))
    pool = df[mask].copy()
    if commander:
        pool = pool[pool["name"].astype(str) != str(commander)]
    pool = _merge_multi_face_pool_rows(pool)

    # Fetch lands are colorless (no colorIdentity pips), so the plain
    # color-identity subset check above always lets them through even when
    # they only search for basic land types outside the deck's identity
    # (e.g. Polluted Delta -> Island/Swamp in a W/G deck). Filter those out.
    if "metadataTags" in pool.columns:
        identity_list = sorted(identity)
        fetch_mask = pool["metadataTags"].apply(
            lambda tags: fetch_land_allowed_for_colors(tags, identity_list)
        )
        pool = pool[fetch_mask]

    banned = banned_category_names(bracket)
    banned_names: set = set()
    for names in banned.values():
        banned_names |= names
    if banned_names:
        pool = pool[~pool["name"].astype(str).str.lower().isin(banned_names)]

    capped = capped_category_names(bracket)
    capped_labels = {
        "game_changers": "Game Changer",
        "tutors_nonland": "Tutor",
        "extra_turns": "Extra Turn",
        "mass_land_denial": "Mass Land Denial",
    }
    name_to_capped_tags: Dict[str, List[str]] = {}
    for key, names in capped.items():
        label = capped_labels.get(key, key)
        for n in names:
            name_to_capped_tags.setdefault(n, []).append(label)

    pool["_tags"] = pool.get("themeTags", pd.Series([[]] * len(pool), index=pool.index)).apply(parse_theme_tags)
    pool["_metadata_tags"] = pool.get("metadataTags", pd.Series([[]] * len(pool), index=pool.index)).apply(parse_theme_tags)
    pool["_bracket_tags"] = pool["name"].astype(str).str.lower().map(
        lambda n: name_to_capped_tags.get(n, [])
    )

    selected_themes = {t.lower() for t in (sess.get("tags") or [])}
    if selected_themes:
        pool["_theme_matches"] = pool["_tags"].apply(
            lambda tags: [t for t in tags if t.lower() in selected_themes]
        )
    else:
        pool["_theme_matches"] = [[] for _ in range(len(pool))]

    pool["_role"] = [
        _card_role(t, tags, bool(tm), meta)
        for t, tags, tm, meta in zip(pool.get("type", ""), pool["_tags"], pool["_theme_matches"], pool["_metadata_tags"])
    ]

    # Milestone 11 "Related Synergy": whichever of the commander's OWN
    # themeTags the user did NOT select during setup (e.g. commander has
    # Discard Matters/Exile Matters/Spellslinger, user only picked Discard
    # Matters -> the other two are candidates here).
    commander_tags, _ = _commander_tags_and_power(str(commander or ""))
    other_commander_tags = [t for t in commander_tags if t.lower() not in selected_themes]
    if other_commander_tags:
        other_lower = {t.lower() for t in other_commander_tags}
        pool["_commander_other_matches"] = pool["_tags"].apply(
            lambda tags: [t for t in other_commander_tags if t.lower() in other_lower and t.lower() in {x.lower() for x in tags}]
        )
    else:
        pool["_commander_other_matches"] = [[] for _ in range(len(pool))]

    pool["_type_category"] = [
        _type_category(t, tags) for t, tags in zip(pool.get("type", ""), pool["_tags"])
    ]

    sess["_pool_df"] = pool
    return pool


def _exclude_in_deck(sess: Dict[str, Any], pool: pd.DataFrame) -> pd.DataFrame:
    """Filter out cards already in the deck (pool exclusivity), except basic
    lands and the singleton exceptions in `is_unlimited_copy_card`.
    """
    deck_cards = sess.get("deck_cards") or []
    in_deck_lower = {c.strip().lower() for c in deck_cards if not is_unlimited_copy_card(c)}
    if in_deck_lower:
        return pool[~pool["name"].astype(str).str.lower().isin(in_deck_lower)]
    return pool


def _card_reasons(row: Any) -> List[str]:
    """Short, human-readable bullets explaining why a pool card is surfaced.

    Purely informational (never affects filtering/sorting); shown in the
    pool tile so users aren't left guessing why a card appears where it does.
    """
    reasons: List[str] = []
    theme_matches = list(row.get("_theme_matches") or [])
    if theme_matches:
        reasons.append(f"Matches your theme(s): {', '.join(theme_matches)}")
    other_matches = list(row.get("_commander_other_matches") or [])
    if other_matches:
        reasons.append(f"Fits your commander's other theme(s): {', '.join(other_matches)}")
    rank = row.get("edhrecRank")
    if rank is None or (isinstance(rank, float) and pd.isna(rank)):
        reasons.append("No EDHREC popularity data")
    elif rank <= 500:
        reasons.append("Highly popular on EDHREC")
    elif rank <= 3000:
        reasons.append("Moderately popular on EDHREC")
    if bool(row.get("isNew") or False):
        reasons.append("Recently released card")
    role = row.get("_role")
    if role and role != "Other":
        reasons.append(f"Fills the {role} role")
    return reasons


def _role_matching_tags(tags: List[str], role: Any) -> List[str]:
    """Whichever of a card's own tags are the specific ones that earned it
    `role`'s role-bar bucket (e.g. "Card Draw" for a card that's actually
    tagged `Card Advantage`), so the UI can badge those tags distinctly from
    the card's other, non-role-defining theme tags.
    """
    role_tag_set = {"Ramp": _RAMP_TAGS, "Removal": _REMOVAL_TAGS, "Card Draw": _CARD_DRAW_TAGS}.get(str(role or ""))
    if not role_tag_set:
        return []
    return [t for t in tags if t.lower() in role_tag_set]


def _tag_badges(row: Any) -> List[Dict[str, str]]:
    """All of a card's themeTags, each labeled with why it matters here so
    the UI can highlight them distinctly: "deck_theme" (matches a theme you
    selected - highest priority), "commander_theme" (one of the commander's
    OTHER themes), "role" (the tag that earned this card its role-bar
    bucket), or "other" (shown plainly, no special highlight).
    """
    tags = list(row.get("_tags") or [])
    if not tags:
        return []
    deck_theme_lower = {t.lower() for t in (row.get("_theme_matches") or [])}
    commander_theme_lower = {t.lower() for t in (row.get("_commander_other_matches") or [])}
    role_tags_lower = {t.lower() for t in _role_matching_tags(tags, row.get("_role"))}
    badges: List[Dict[str, str]] = []
    for t in tags:
        tl = t.lower()
        if tl in deck_theme_lower:
            kind = "deck_theme"
        elif tl in commander_theme_lower:
            kind = "commander_theme"
        elif tl in role_tags_lower:
            kind = "role"
        else:
            kind = "other"
        badges.append({"name": t, "kind": kind})
    return badges


def _build_card_dict(row: Any) -> Dict[str, Any]:
    """Shared per-card dict shape for `query_pool`/`query_category` results."""
    return {
        "name": row.get("name"),
        "role": row.get("_role"),
        "cmc": row.get("manaValue") or 0,
        "is_new": bool(row.get("isNew") or False),
        "bracket_tags": list(row.get("_bracket_tags") or []),
        "theme_matches": list(row.get("_theme_matches") or []),
        "tag_badges": _tag_badges(row),
        "reasons": _card_reasons(row),
        "oracle_text": row.get("text") or "",
    }


def query_pool(
    sess: Dict[str, Any],
    role: str = "Any",
    sort: str = "relevance",
    search: str = "",
    page: int = 1,
    per_page: int = _CATEGORY_PAGE_SIZE,
) -> Dict[str, Any]:
    """Filter/sort/paginate the card pool for the "search outside the pool"
    fallback and `search_off_pool` (Milestone 11 replaced the role-dropdown
    pool grid with `categorize_pool`/`query_category` below).

    Budget ceilings are never applied as a filter here — over-budget cards
    stay visible (flagged client-side via the existing `.over-budget` CSS
    class), matching the auto-builder's own step 5 behavior.

    `sort="relevance"` (the default) is EDHREC popularity rank, ascending
    (lower rank = more popular). Callers should label this clearly in the
    UI rather than leaving "Relevance" ambiguous.

    Cards already in the deck are hidden from the pool once added (they can
    be re-added after being removed), except basic lands and the singleton
    exceptions in `is_unlimited_copy_card` (Relentless Rats, etc.), which
    stay visible since they can be added any number of times.
    """
    pool = get_card_pool(sess)
    filtered = _exclude_in_deck(sess, pool)
    if role and role != "Any":
        filtered = filtered[filtered["_role"] == role]
    if search and search.strip():
        # Same Scryfall-style syntax as the mobile app's card browser (c:/t:/o:/
        # m:/mv:/pow:/tou:/loy:/tag:/theme: flags, negation, etc.) -- see card_search.py.
        parsed = parse_search_query(search)
        filtered = apply_parsed_search(filtered, parsed)
        filtered = apply_extra_clauses(filtered, parsed)

    if sort == "cmc":
        filtered = filtered.sort_values(by="manaValue", na_position="last")
    elif sort == "name":
        filtered = filtered.sort_values(by="name", key=lambda s: s.str.lower())
    elif sort == "price":
        names = filtered["name"].astype(str).tolist()
        price_map = get_price_service().get_prices_batch(names)
        prices = [price_map.get(n) if price_map.get(n) is not None else float("inf") for n in names]
        filtered = filtered.assign(_sort_price=prices).sort_values(by="_sort_price")
    elif sort == "theme":
        match_counts = filtered["_theme_matches"].apply(len)
        filtered = filtered.assign(_theme_match_count=match_counts).sort_values(
            by=["_theme_match_count", "edhrecRank"], ascending=[False, True], na_position="last"
        )
    else:
        sort = "relevance"
        filtered = filtered.sort_values(by="edhrecRank", na_position="last")

    total = len(filtered)
    per_page = max(1, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_df = filtered.iloc[start:start + per_page]

    cards: List[Dict[str, Any]] = [_build_card_dict(row) for _, row in page_df.iterrows()]

    return {
        "cards": cards,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "role": role,
        "sort": sort,
        "search": search,
    }


def _ensure_computed_columns(pool: pd.DataFrame) -> pd.DataFrame:
    """Backfill the `_tags`/`_role`/etc. columns `get_card_pool` normally
    computes, for callers (mainly tests) that monkeypatch `get_card_pool`
    with a bare DataFrame straight from the loader.
    """
    if "_tags" not in pool.columns:
        pool = pool.copy()
        pool["_tags"] = pool.get("themeTags", pd.Series([[]] * len(pool), index=pool.index)).apply(parse_theme_tags)
    if "_metadata_tags" not in pool.columns:
        pool["_metadata_tags"] = pool.get("metadataTags", pd.Series([[]] * len(pool), index=pool.index)).apply(parse_theme_tags)
    if "_theme_matches" not in pool.columns:
        pool["_theme_matches"] = [[] for _ in range(len(pool))]
    if "_role" not in pool.columns:
        pool["_role"] = [
            _card_role(t, tags, bool(tm), meta)
            for t, tags, tm, meta in zip(pool.get("type", ""), pool["_tags"], pool["_theme_matches"], pool["_metadata_tags"])
        ]
    if "_bracket_tags" not in pool.columns:
        pool["_bracket_tags"] = [[] for _ in range(len(pool))]
    if "_commander_other_matches" not in pool.columns:
        pool["_commander_other_matches"] = [[] for _ in range(len(pool))]
    if "_type_category" not in pool.columns:
        pool["_type_category"] = [_type_category(t, tags) for t, tags in zip(pool.get("type", ""), pool["_tags"])]
    return pool


def query_category(
    sess: Dict[str, Any],
    category: str,
    search: str = "",
    _full_pool: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Filter/sort one Milestone 11 pool category, showing every matching
    card at once (no pagination).

    "new"/"on_brand"/"related_synergy" are cross-cutting highlight sections
    (any card type); the rest are mutually-exclusive type buckets assigned
    by `_type_category`. Every category except "on_brand" is capped at
    `_CATEGORY_MAX_CARDS`; "on_brand" is capped at `_ON_BRAND_CAP`.

    The cap is chosen from the full pool BEFORE excluding cards already in
    the deck, so it's a fixed curated top-N that only ever shrinks as cards
    are added (they disappear from the list) and grows back if removed -
    it never "replenishes" by pulling in a new card ranked just past the
    cap once a higher-ranked one is added to the deck.

    `_full_pool` lets `categorize_pool` compute the (already-computed-
    columns) pool once and reuse it across all category keys, instead of
    redoing that scan 14x per request.
    """
    if category not in CATEGORY_LABELS:
        raise ValueError(f"Unknown pool category: {category}")

    filtered = _full_pool if _full_pool is not None else _ensure_computed_columns(get_card_pool(sess))

    if category == "new":
        filtered = filtered[filtered["isNew"].fillna(False).astype(bool)]
    elif category == "on_brand":
        pass  # any type; ranking below does the work
    elif category == "related_synergy":
        filtered = filtered[
            (filtered["_commander_other_matches"].apply(len) > 0)
            & (filtered["_theme_matches"].apply(len) == 0)
        ]
    elif category in _CATEGORY_TO_ROLE:
        filtered = filtered[filtered["_role"] == _CATEGORY_TO_ROLE[category]]
    elif category in ("battles", "planeswalkers"):
        # Both are highly situational card types; showing every legal one
        # (regardless of relevance) muddies the pool, so only surface ones
        # that actually match one of the deck's selected themes.
        filtered = filtered[
            (filtered["_type_category"] == category)
            & (filtered["_theme_matches"].apply(len) > 0)
        ]
    else:
        filtered = filtered[filtered["_type_category"] == category]

    if search and search.strip():
        # Same Scryfall-style syntax as the mobile app's card browser (c:/t:/o:/
        # m:/mv:/pow:/tou:/loy:/tag:/theme: flags, negation, etc.) -- see card_search.py.
        parsed = parse_search_query(search)
        filtered = apply_parsed_search(filtered, parsed)
        filtered = apply_extra_clauses(filtered, parsed)

    if category == "on_brand":
        # Milestone 10's usage_synergy_score isn't wired in yet; falls back
        # to theme-match count + EDHREC rank only until it lands.
        theme_ct = filtered["_theme_matches"].apply(len)
        filtered = filtered.assign(_theme_ct=theme_ct).sort_values(
            by=["_theme_ct", "edhrecRank"], ascending=[False, True], na_position="last"
        )
    elif category == "related_synergy":
        rel_ct = filtered["_commander_other_matches"].apply(len)
        filtered = filtered.assign(_rel_ct=rel_ct).sort_values(
            by=["_rel_ct", "edhrecRank"], ascending=[False, True], na_position="last"
        )
    elif category in ("mana_artifacts", "lands", "new") or category in _CATEGORY_TO_ROLE:
        # Role categories (Ramp/Removal/etc.) are meant to be theme-
        # independent - sorting by theme-match count here would just
        # resurface on-theme cards ahead of more generally useful ones,
        # defeating the point of a category that exists to show non-theme
        # options.
        filtered = filtered.sort_values(by="edhrecRank", na_position="last")
    else:
        theme_ct = filtered["_theme_matches"].apply(len)
        filtered = filtered.assign(_theme_ct=theme_ct).sort_values(
            by=["_theme_ct", "edhrecRank"], ascending=[False, True], na_position="last"
        )

    # A search should surface every matching legal card, not just the
    # curated top N shown when idly browsing - only cap when unsearched.
    # Capping happens BEFORE excluding in-deck cards (see docstring) so the
    # cap doesn't silently refill itself as cards move into the deck.
    capped = not search
    if capped:
        cap = _ON_BRAND_CAP if category == "on_brand" else _CATEGORY_MAX_CARDS
        filtered = filtered.iloc[:cap]

    filtered = _exclude_in_deck(sess, filtered)
    total = len(filtered)
    cards: List[Dict[str, Any]] = [_build_card_dict(row) for _, row in filtered.iterrows()]

    return {
        "category": category,
        "label": CATEGORY_LABELS[category],
        "cards": cards,
        "total": total,
        "search": search,
        "capped": capped,
    }


def categorize_pool(sess: Dict[str, Any], search: str = "") -> Dict[str, Dict[str, Any]]:
    """Full (unpaginated, capped) data for every Milestone 11 category,
    keyed by category id.

    The "other" catch-all is only included if it actually has matching
    cards (safety net for a future card type the precedence rules in
    `_type_category` don't cover).
    """
    pool = _ensure_computed_columns(get_card_pool(sess))
    result: Dict[str, Dict[str, Any]] = {}
    for key in CATEGORY_KEYS:
        cat = query_category(sess, key, search=search, _full_pool=pool)
        if key == "other" and not cat["cards"]:
            continue
        result[key] = cat
    return result


def search_off_pool(
    sess: Dict[str, Any],
    query: str,
    page: int = 1,
    per_page: int = _CATEGORY_PAGE_SIZE,
) -> Dict[str, Any]:
    """Search the color-legal (and bracket-legal) card set for the M3
    "search" endpoint, using the same Scryfall-style query syntax as the
    mobile app's card browser (see `code/web/services/card_search.py`):
    plain words match the card name, and `t:`/`o:`/`c:`/`id:`/`m:`/`mv:`/
    `pow:`/`tou:`/`loy:` flags filter by type, oracle text, colors, color
    identity, mana cost, mana value, power, toughness, and loyalty. Shares
    `get_card_pool`'s bracket filtering, so every result is genuinely
    addable; `in_pool` is always True since this is a search over the same
    underlying set, not a separate pool.
    """
    result = query_pool(sess, role="Any", sort="relevance", search=query, page=page, per_page=per_page)
    for card in result["cards"]:
        card["in_pool"] = True
    return result


def best_search_match(query: str, cards: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The single card a Shift+Enter quick-add should add for `query`: an
    exact (case-insensitive) name match if one is present in `cards`,
    otherwise the top (most relevant/popular) result. `cards` should be
    page 1 of `search_off_pool`'s results - a later page's top card isn't
    the best guess for the query as a whole.
    """
    if not cards:
        return None
    q_norm = query.strip().lower()
    if q_norm:
        for card in cards:
            if str(card.get("name") or "").strip().lower() == q_norm:
                return card
    return cards[0]


# ---------------------------------------------------------------------------
# Milestone 3: add / remove / deck panel
# ---------------------------------------------------------------------------

def _lookup_card_rows(sess: Dict[str, Any], names: List[str]) -> Dict[str, Optional[pd.Series]]:
    """Batch version of `_lookup_card_row`: resolves many names in one
    vectorized pass over the pool/full dataframe instead of re-running a
    fresh `.astype(str).str.lower()` scan per name. `deck_panel_data`,
    `mana_overview_data`, and `role_bar_data` each used to loop
    `_lookup_card_row()` over every card in the deck, so a 60-card deck did
    3 x 60 full-table scans on every add/remove; this cuts that to 3 scans.
    """
    result: Dict[str, Optional[pd.Series]] = {}
    if not names:
        return result
    needle_to_names: Dict[str, List[str]] = {}
    for name in names:
        needle_to_names.setdefault(name.strip().lower(), []).append(name)
    remaining = set(needle_to_names.keys())

    pool = sess.get("_pool_df")
    if pool is not None and not pool.empty:
        lower_col = pool["name"].astype(str).str.lower()
        mask = lower_col.isin(remaining)
        if mask.any():
            sub = pool[mask]
            sub_lower = lower_col[mask]
            for needle, idx in sub_lower.groupby(sub_lower).groups.items():
                row = sub.loc[idx[0]]
                for orig in needle_to_names[needle]:
                    result[orig] = row
                remaining.discard(needle)

    if remaining:
        df = _get_loader().load()
        lower_col = df["name"].astype(str).str.lower()
        mask = lower_col.isin(remaining)
        if mask.any():
            sub = df[mask]
            sub_lower = lower_col[mask]
            selected_themes = {t.lower() for t in (sess.get("tags") or [])}
            for needle, idx in sub_lower.groupby(sub_lower).groups.items():
                row = sub.loc[idx[0]].copy()
                tags = parse_theme_tags(row.get("themeTags"))
                row["_tags"] = tags
                metadata_tags = parse_theme_tags(row.get("metadataTags"))
                row["_metadata_tags"] = metadata_tags
                theme_matches = [t for t in tags if t.lower() in selected_themes]
                row["_theme_matches"] = theme_matches
                row["_role"] = _card_role(row.get("type"), tags, bool(theme_matches), metadata_tags)
                for orig in needle_to_names[needle]:
                    result[orig] = row
                remaining.discard(needle)

    for name in names:
        result.setdefault(name, None)
    return result


def _lookup_card_row(sess: Dict[str, Any], name: str) -> Optional[pd.Series]:
    """Find a card by case-insensitive name: prefers the cached pool (already
    scoped to color identity, with `_role`/`_tags` precomputed), falling back
    to the full card database for off-pool cards.
    """
    return _lookup_card_rows(sess, [name]).get(name)


def add_card_to_deck(sess: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Add a card to the session deck.

    Returns ``{"status": "added"|"duplicate"|"not_found"|"bracket_banned", "name": str}``.
    Duplicates are blocked for non-basic-land cards (Commander singleton
    rule); basic lands may be added any number of times. `bracket_banned` is
    a defense-in-depth check (the pool/search already exclude these cards,
    but a card could be added via a stale request) for categories fully
    banned at the session's bracket, e.g. Game Changers at Bracket 1/2.
    """
    row = _lookup_card_row(sess, name)
    if row is None:
        return {"status": "not_found", "name": name}
    canonical_name = str(row.get("name"))
    banned = banned_category_names(str(sess.get("bracket") or 2))
    banned_names: set = set()
    for names in banned.values():
        banned_names |= names
    if canonical_name.lower() in banned_names:
        return {"status": "bracket_banned", "name": canonical_name}
    deck_cards: List[str] = sess.setdefault("deck_cards", [])
    if not is_basic_land(canonical_name):
        if any(c.lower() == canonical_name.lower() for c in deck_cards):
            return {"status": "duplicate", "name": canonical_name}
    deck_cards.append(canonical_name)
    return {"status": "added", "name": canonical_name}


def remove_card_from_deck(sess: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Remove one copy of `name` from the session deck (case-insensitive)."""
    deck_cards: List[str] = sess.get("deck_cards") or []
    needle = name.strip().lower()
    for i in range(len(deck_cards) - 1, -1, -1):
        if deck_cards[i].lower() == needle:
            removed = deck_cards.pop(i)
            return {"status": "removed", "name": removed}
    return {"status": "not_found", "name": name}


def set_card_count(sess: Dict[str, Any], name: str, count: int) -> Dict[str, Any]:
    """Set the exact copy count of `name` in the deck (basic lands and other
    unlimited-copy cards only, e.g. Relentless Rats). Non-multi-copy cards
    are clamped to 0 or 1 since the Commander singleton rule still applies.
    Returns ``{"status": "set"|"not_found", "name": str, "count": int}``.
    """
    row = _lookup_card_row(sess, name)
    if row is None:
        return {"status": "not_found", "name": name, "count": 0}
    canonical_name = str(row.get("name"))
    count = max(0, int(count))
    if not is_unlimited_copy_card(canonical_name):
        count = min(count, 1)
    deck_cards: List[str] = sess.setdefault("deck_cards", [])
    deck_cards[:] = [c for c in deck_cards if c.lower() != canonical_name.lower()]
    deck_cards.extend([canonical_name] * count)
    return {"status": "set", "name": canonical_name, "count": count}


def _commander_tags_and_power(commander: str) -> tuple:
    """Best-effort ``(tags, power)`` for a commander, mirroring the inputs the
    auto-builder passes into `bc.STAPLE_LAND_CONDITIONS`. Returns ``([], 0)``
    if the commander can't be found.
    """
    if not commander:
        return [], 0
    tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    df = tmp.load_commander_data()
    row = df[df["name"].astype(str) == commander]
    if row.empty:
        return [], 0
    tags = parse_theme_tags(row.iloc[0].get("themeTags"))
    power = 0
    raw_power = row.iloc[0].get("power")
    if isinstance(raw_power, (int, float)) and not (isinstance(raw_power, float) and pd.isna(raw_power)):
        power = int(raw_power)
    elif isinstance(raw_power, str) and raw_power.isdigit():
        power = int(raw_power)
    return tags, power


def add_land_package(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-add a starting land base: basic lands (up to the session's basic-land
    ideal, split evenly across the commander's colors, remainder going to the
    first colors in WUBRG order) plus the generic staple lands from
    `bc.STAPLE_LAND_CONDITIONS` (Command Tower, Reliquary Tower, etc. - same
    set/conditions the auto-builder uses in its own land Step 2, excluding
    Kindred lands). Staples already in the deck are skipped; basics are
    always added fresh since they're an unlimited-copy exception. Intended as
    a one-shot starting point, not idempotent - calling it twice adds a
    second land package.
    """
    deck_cards: List[str] = sess.setdefault("deck_cards", [])
    added: List[str] = []

    ideals = sess.get("ideals") or {}
    basic_target = max(0, int(ideals.get("basic_lands") or bc.DEFAULT_BASIC_LAND_COUNT))
    identity = [c for c in ["W", "U", "B", "R", "G"] if c in (sess.get("color_identity") or [])]
    if not identity:
        identity = ["C"]
    base_count, remainder = divmod(basic_target, len(identity))
    for i, color in enumerate(identity):
        land_name = bc.COLOR_TO_BASIC_LAND.get(color)
        if not land_name:
            continue
        count = base_count + (1 if i < remainder else 0)
        for _ in range(count):
            deck_cards.append(land_name)
            added.append(land_name)

    commander_tags, commander_power = _commander_tags_and_power(str(sess.get("commander") or ""))
    colors = sess.get("color_identity") or []
    existing_lower = {c.lower() for c in deck_cards}
    for land_name, cond in bc.STAPLE_LAND_CONDITIONS.items():
        if land_name.lower() in existing_lower:
            continue
        try:
            include = bool(cond(commander_tags, colors, commander_power))
        except Exception:
            include = False
        if include:
            deck_cards.append(land_name)
            added.append(land_name)
            existing_lower.add(land_name.lower())

    return {"status": "added", "lands": added, "count": len(added)}


def deck_card_counts(sess: Dict[str, Any]) -> Counter:
    """Quantity per unique card name (case preserved as first-added spelling)."""
    return Counter(sess.get("deck_cards") or [])


def deck_panel_data(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Group the current deck's cards by card type (mirrors the finished
    deck summary's Type Summary order, see `_DECK_TYPE_ORDER`), each card
    tagged with the on-theme/ideal-role labels it's filling."""
    counts = deck_card_counts(sess)
    rows = _lookup_card_rows(sess, list(counts.keys()))
    groups: Dict[str, List[Dict[str, Any]]] = {t: [] for t in _DECK_TYPE_ORDER}
    for name, count in counts.items():
        row = rows.get(name)
        category = _deck_type_category(row.get("type") if row is not None else "")
        cmc = (row.get("manaValue") or 0) if row is not None else 0
        tags = list(row.get("_tags") or []) if row is not None else []
        theme_matches = list(row.get("_theme_matches") or []) if row is not None else []
        metadata_tags = list(row.get("_metadata_tags") or []) if row is not None else []
        groups.setdefault(category, []).append({
            "name": name,
            "count": count,
            "cmc": cmc,
            "is_multi_copy": is_unlimited_copy_card(name),
            "roles": _card_role_labels(tags, theme_matches, metadata_tags),
        })
    for cat_cards in groups.values():
        cat_cards.sort(key=lambda c: c["name"].lower())
    ordered_groups = [
        {"role": _DECK_TYPE_LABELS[t], "cards": groups[t]} for t in _DECK_TYPE_ORDER if groups.get(t)
    ]
    total_cards = sum(counts.values())
    # +1 for the commander's own slot (never part of deck_cards itself).
    deck_size_target = bc.DECK_NON_COMMANDER_SLOTS + 1
    return {
        "groups": ordered_groups,
        "total_cards": total_cards,
        "total_with_commander": total_cards + 1,
        "deck_size_target": deck_size_target,
    }


def _mana_card_library(sess: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Optional[pd.Series]]]:
    """Card-library dict (name -> {Card Type, Mana Cost, Count}) for the
    deck's cards plus the commander, and the raw row lookups behind it.
    Shared by `mana_overview_data` (live in-progress sidebar) and
    `_build_deck_summary` (saved `.summary.json`) so both compute pips/
    sources the same way instead of drifting apart.
    """
    counts = deck_card_counts(sess)
    commander_name = sess.get("commander")
    lookup_names = list(counts.keys())
    if commander_name and commander_name not in counts:
        lookup_names.append(commander_name)
    rows = _lookup_card_rows(sess, lookup_names)
    card_library: Dict[str, Dict[str, Any]] = {}
    for name, count in counts.items():
        row = rows.get(name)
        card_library[name] = {
            "Card Type": str(row.get("type") or "") if row is not None else "",
            "Mana Cost": str(row.get("manaCost") or "") if row is not None else "",
            "Count": count,
        }

    # The commander itself isn't part of deck_cards (it has its own slot),
    # but its pips/mana cost still count toward the deck's mana base.
    if commander_name and commander_name not in card_library:
        commander_row = rows.get(commander_name)
        card_library[commander_name] = {
            "Card Type": str(commander_row.get("type") or "") if commander_row is not None else "",
            "Mana Cost": str(commander_row.get("manaCost") or "") if commander_row is not None else "",
            "Count": 1,
        }
    return card_library, rows


def _mana_pip_and_source_summary(sess: Dict[str, Any]) -> Dict[str, Any]:
    """`pip_distribution`/`mana_generation` in the same shape
    `DeckBuilder.build_deck_summary()` produces (counts/weights/cards dicts,
    raw source counts rather than percentages) for the saved deck's
    `.summary.json` - which `decks/view.html`'s Mana Overview panel reads
    via `partials/deck_summary.html`. Unlike `mana_overview_data` (percentage-
    based, list-shaped, for the live in-progress sidebar), this matches the
    finished-deck schema so manually-built decks render the same as
    auto-built ones after saving.
    """
    color_identity = [c for c in ("W", "U", "B", "R", "G") if c in (sess.get("color_identity") or [])]
    card_library, _rows = _mana_card_library(sess)

    pip_density = compute_pip_density(card_library, color_identity)
    pip_counts: Dict[str, float] = {}
    for c in ("W", "U", "B", "R", "G"):
        d = pip_density[c]
        pip_counts[c] = float(d["single"] + d["double"] * 2 + d["triple"] * 3 + d["phyrexian"])
    pip_cards: Dict[str, List[Dict[str, Any]]] = {c: [] for c in ("W", "U", "B", "R", "G")}
    for name, entry in card_library.items():
        if "land" in str(entry.get("Card Type") or "").lower():
            continue
        mana_cost = entry.get("Mana Cost") or ""
        if not isinstance(mana_cost, str):
            continue
        colors_for_card: set = set()
        for match in re.findall(r"\{([^}]+)\}", mana_cost):
            sym = match.upper()
            if len(sym) == 1 and sym in pip_cards:
                colors_for_card.add(sym)
            elif "/" in sym:
                for p in sym.split("/"):
                    if p in pip_cards:
                        colors_for_card.add(p)
            elif sym.endswith("P") and len(sym) == 2 and sym[0] in pip_cards:
                colors_for_card.add(sym[0])
        if colors_for_card:
            cnt = int(entry.get("Count", 1))
            for c in colors_for_card:
                pip_cards[c].append({"name": name, "count": cnt})
    total_pips = sum(pip_counts.values())
    if total_pips <= 0 and color_identity:
        share = 1 / len(color_identity)
        for c in color_identity:
            pip_counts[c] = share
        total_pips = 1.0
    pip_weights = {c: (pip_counts[c] / total_pips if total_pips else 0.0) for c in pip_counts}

    full_df = _get_loader().load()
    scoped_df = full_df[full_df["name"].astype(str).isin(card_library.keys())]
    matrix = compute_color_source_matrix(card_library, scoped_df)
    source_counts: Dict[str, int] = {c: 0 for c in ("W", "U", "B", "R", "G", "C")}
    source_cards: Dict[str, List[Dict[str, Any]]] = {c: [] for c in ("W", "U", "B", "R", "G", "C")}
    for name, flags in matrix.items():
        copies = int(card_library.get(name, {}).get("Count", 1))
        for c in source_counts:
            if int(flags.get(c, 0)):
                source_counts[c] += copies
                source_cards[c].append({"name": name, "count": copies})
    total_sources = sum(source_counts.values())

    return {
        "pip_distribution": {"counts": pip_counts, "weights": pip_weights, "cards": pip_cards},
        "mana_generation": {**source_counts, "total_sources": total_sources, "cards": source_cards},
    }


def mana_overview_data(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Pip distribution, mana sources, and mana curve for the in-progress
    deck, for the sidebar mana-overview panel next to the commander image.
    Reuses the same builder_utils helpers as the finished-deck summary
    (`DeckBuilder.build_deck_summary`), fed from a synthetic card_library
    built out of the session's deck_cards rather than a full DeckBuilder.
    """
    color_identity = [c for c in ["W", "U", "B", "R", "G"] if c in (sess.get("color_identity") or [])]
    card_library, rows = _mana_card_library(sess)

    pip_density = compute_pip_density(card_library, color_identity)
    pip_counts: Dict[str, float] = {}
    for c in ("W", "U", "B", "R", "G"):
        d = pip_density[c]
        pip_counts[c] = float(d["single"] + d["double"] * 2 + d["triple"] * 3 + d["phyrexian"])
    total_pips = sum(pip_counts.values())
    if total_pips <= 0 and color_identity:
        share = 100.0 / len(color_identity)
        pips = [{"color": c, "count": 0, "pct": int(share) if c in color_identity else 0} for c in color_identity]
    else:
        pips = [
            {"color": c, "count": pip_counts.get(c, 0.0), "pct": int(round(pip_counts.get(c, 0.0) * 100 / total_pips))}
            for c in color_identity
        ] if total_pips else [{"color": c, "count": 0, "pct": 0} for c in color_identity]

    full_df = _get_loader().load()
    # compute_color_source_matrix() does a full-table iterrows() to build its
    # name lookup -- scope it to just this deck's cards (a handful of rows)
    # instead of all ~32k cards, since this runs on every add/remove.
    scoped_df = full_df[full_df["name"].astype(str).isin(card_library.keys())]
    matrix = compute_color_source_matrix(card_library, scoped_df)
    source_counts = {c: 0 for c in ("W", "U", "B", "R", "G", "C")}
    for name, flags in matrix.items():
        copies = card_library.get(name, {}).get("Count", 1)
        for c in source_counts:
            if int(flags.get(c, 0)):
                source_counts[c] += copies
    source_colors = list(color_identity)
    if source_counts.get("C", 0) > 0:
        source_colors.append("C")
    max_source = max((source_counts.get(c, 0) for c in source_colors), default=0)
    sources = [
        {"color": c, "count": source_counts.get(c, 0), "pct": int(round(source_counts.get(c, 0) * 100 / max_source)) if max_source else 0}
        for c in source_colors
    ]
    total_sources = sum(source_counts.values())

    curve_bins = ["0", "1", "2", "3", "4", "5", "6+"]
    curve_counts = {b: 0 for b in curve_bins}
    total_spells = 0
    for name, entry in card_library.items():
        row = rows.get(name)
        ctype = str(row.get("type") or "") if row is not None else ""
        if "land" in ctype.lower():
            continue
        try:
            val = float(row.get("manaValue") or 0) if row is not None else 0.0
        except (TypeError, ValueError):
            val = 0.0
        bucket = "6+" if val >= 6 else str(int(val))
        if bucket not in curve_counts:
            bucket = "6+"
        count = entry.get("Count", 1)
        curve_counts[bucket] += count
        total_spells += count
    curve = [
        {"label": b, "count": curve_counts[b], "pct": int(round(curve_counts[b] * 100 / total_spells)) if total_spells else 0}
        for b in curve_bins
    ]

    return {
        "mana_overview": {
            "pips": pips,
            "sources": sources,
            "sources_total": total_sources,
            "curve": curve,
            "curve_total": total_spells,
        }
    }


# ---------------------------------------------------------------------------
# Milestone 4: on-the-fly hover suggestions
# ---------------------------------------------------------------------------

def hover_suggestions(sess: Dict[str, Any], card_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Up to `limit` alternative pool cards for the "Other Good Options"
    hover panel: same role, CMC within +/-2, not already in the deck.
    """
    row = _lookup_card_row(sess, card_name)
    if row is None:
        return []
    role = row.get("_role")
    cmc = float(row.get("manaValue") or 0)
    deck_lower = {c.lower() for c in (sess.get("deck_cards") or [])}

    pool = get_card_pool(sess)
    candidates = pool[
        (pool["_role"] == role)
        & (pool["manaValue"].fillna(0).between(cmc - 2, cmc + 2))
        & (pool["name"].astype(str).str.lower() != card_name.strip().lower())
        & (~pool["name"].astype(str).str.lower().isin(deck_lower))
    ].sort_values(by="edhrecRank", na_position="last").head(limit)

    names = candidates["name"].astype(str).tolist()
    price_map = get_price_service().get_prices_batch(names) if names else {}

    results: List[Dict[str, Any]] = []
    for _, r in candidates.iterrows():
        cname = str(r.get("name"))
        results.append({
            "name": cname,
            "cmc": r.get("manaValue") or 0,
            "roles": list(r.get("_tags") or []),
            "price": price_map.get(cname),
            "is_new": bool(r.get("isNew") or False),
            "in_pool": True,
        })
    return results


# ---------------------------------------------------------------------------
# Milestone 5: role health bar
# ---------------------------------------------------------------------------

# Targets sourced from builder_constants (never hardcoded).
ROLE_BAR_TARGETS: Dict[str, int] = {
    "Ramp": bc.DEFAULT_RAMP_COUNT,
    "Removal": bc.DEFAULT_REMOVAL_COUNT,
    "Card Draw": bc.DEFAULT_CARD_ADVANTAGE_COUNT,
    "Protection": bc.DEFAULT_PROTECTION_COUNT,
    "Board Wipe": bc.DEFAULT_WIPES_COUNT,
    "Land": bc.DEFAULT_LAND_COUNT,
}
ROLE_BAR_LABELS: Dict[str, str] = {
    "Ramp": "Ramp",
    "Removal": "Removal",
    "Card Draw": "Draw",
    "Protection": "Protection",
    "Board Wipe": "Board Wipe",
    "Land": "Lands",
}


def _role_bar_status(role: str, actual: int, target: int) -> str:
    if role == "Land":
        # Roadmap 25 M5: lands use fixed thresholds independent of the target.
        if actual < 33:
            return "red"
        if actual <= 35:
            return "yellow"
        return "green"
    if actual >= target:
        return "green"
    if actual >= target - 2:
        return "yellow"
    return "red"


def role_bar_data(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Live role counts vs. targets for the role health bar."""
    counts = deck_card_counts(sess)
    rows = _lookup_card_rows(sess, list(counts.keys()))
    role_totals: Dict[str, int] = {r: 0 for r in ROLE_BAR_TARGETS}
    for name, qty in counts.items():
        row = rows.get(name)
        role = str(row.get("_role")) if row is not None else "Other"
        if role in role_totals:
            role_totals[role] += qty

    pills: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for role, target in ROLE_BAR_TARGETS.items():
        actual = role_totals[role]
        status = _role_bar_status(role, actual, target)
        label = ROLE_BAR_LABELS[role]
        pills.append({"role": role, "label": label, "actual": actual, "target": target, "status": status})
        if status == "red":
            warnings.append(f"You're short on {label} ({actual}/{target}). Consider adding more {label.lower()}.")
    return {"pills": pills, "warnings": warnings}


# ---------------------------------------------------------------------------
# Bracket compliance bar (Game Changers / Extra Turns / Mass Land Denial /
# Nonland Tutors / Two-Card Combos): reuses the same evaluator the Step 5
# compliance report uses, so the manual builder's live status matches what
# the auto-builder would report for the same deck and bracket.
# ---------------------------------------------------------------------------

BRACKET_CATEGORY_LABELS: Dict[str, str] = {
    "game_changers": "Game Changers",
    "extra_turns": "Extra Turns",
    "mass_land_denial": "Mass Land Denial",
    "tutors_nonland": "Nonland Tutors",
    "two_card_combos": "Two-Card Combos",
}
_STATUS_TO_COLOR: Dict[str, str] = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}


def manual_compliance_report(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Bracket-compliance status for the in-progress manual deck.

    Combo detection needs the full current deck list (a combo is a pair of
    specific cards), so unlike the single-card categories it can only ever
    be checked here, never filtered out of the pool up front - it always
    surfaces as a warning, never blocks or hides a card.
    """
    names = list(deck_card_counts(sess).keys())
    commander = sess.get("commander")
    if commander:
        names.append(commander)
    deck_cards = {n: {} for n in names}
    bracket = str(sess.get("bracket") or 2)
    report = evaluate_deck(deck_cards, commander_name=commander, bracket=bracket)

    pills: List[Dict[str, Any]] = []
    flagged_notes: List[str] = []
    for key, label in BRACKET_CATEGORY_LABELS.items():
        cat = report["categories"].get(key) or {}
        status = _STATUS_TO_COLOR.get(cat.get("status"), "green")
        limit = cat.get("limit")
        pills.append({
            "key": key,
            "label": label,
            "count": cat.get("count", 0),
            "limit": limit,
            "status": status,
        })
        if cat.get("status") in ("WARN", "FAIL") and cat.get("flagged"):
            flagged = ", ".join(cat["flagged"])
            flagged_notes.append(f"{label}: {flagged}")
    return {"bracket_pills": pills, "bracket_notes": flagged_notes, "bracket_overall": report.get("overall")}


# ---------------------------------------------------------------------------
# Milestone 6: export & save
# ---------------------------------------------------------------------------

# Matches the built-deck CSV schema read by upgrade_suggestions._load_deck /
# deck_import_service.save_imported_deck - keep these three in sync.
_CSV_HEADERS = [
    "Name", "Count", "Type", "ManaCost", "ManaValue", "Colors",
    "Power", "Toughness", "Role", "SubRole", "AddedBy", "TriggerTag",
    "Synergy", "Tags", "MetadataTags", "Text", "DFCNote", "Owned",
    "Price (TCGPlayer)",
]


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name or "")
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:60] or "manual_deck"


def _build_deck_rows(sess: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per unique card (commander first), for CSV/TXT export."""
    commander = sess.get("commander") or ""
    counts = deck_card_counts(sess)
    rows: List[Dict[str, Any]] = []
    if commander:
        row = _lookup_card_row(sess, commander)
        rows.append({
            "name": commander,
            "count": 1,
            "type": str(row.get("type") or "") if row is not None else "",
            "cmc": (row.get("manaValue") or 0) if row is not None else 0,
            "tags": list(row.get("_tags") or []) if row is not None else [],
            "is_commander": True,
        })
    for name, count in counts.items():
        row = _lookup_card_row(sess, name)
        rows.append({
            "name": name,
            "count": count,
            "type": str(row.get("type") or "") if row is not None else "",
            "cmc": (row.get("manaValue") or 0) if row is not None else 0,
            "tags": list(row.get("_tags") or []) if row is not None else [],
            "is_commander": False,
        })
    return rows


def build_deck_csv_text(sess: Dict[str, Any]) -> str:
    """Render the current session deck as CSV text (built-deck schema)."""
    import io

    rows = _build_deck_rows(sess)
    color_str = "".join(sess.get("color_identity") or [])
    commander = sess.get("commander") or ""
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(_CSV_HEADERS + [f"Commanders: {commander}"])
    for r in rows:
        if r["is_commander"]:
            role = "commander"
        elif "land" in r["type"].lower():
            role = "land"
        elif "creature" in r["type"].lower():
            role = "creature"
        else:
            role = "spell"
        tags_str = "; ".join(r["tags"])
        writer.writerow([
            r["name"], r["count"], r["type"], "", r["cmc"],
            color_str if r["is_commander"] else "",
            "", "", role, "", "", "", "", tags_str, "", "", "", "", "", "",
        ])
    return buf.getvalue()


def build_deck_txt_text(sess: Dict[str, Any]) -> str:
    """Render the current session deck as plain text (one line per card)."""
    rows = _build_deck_rows(sess)
    commander = sess.get("commander") or ""
    lines = [f"# Commanders: {commander}", ""]
    for r in rows:
        lines.append(f"{r['count']} {r['name']}")
    return "\n".join(lines) + "\n"


def _build_deck_summary(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full `.summary.json` `summary` block (type_breakdown +
    pip_distribution + mana_generation + mana_curve + colors) from the
    in-memory session, matching `DeckBuilder.build_deck_summary()`'s schema
    so the finished-deck view page (`decks/view.html` /
    `partials/deck_summary.html`) renders manual decks - including a real
    Mana Overview panel - the same as any auto-built deck.
    """
    rows = _build_deck_rows(sess)
    type_counts: Dict[str, int] = {}
    type_cards: Dict[str, List[Dict[str, Any]]] = {}
    curve_bins = ["0", "1", "2", "3", "4", "5", "6+"]
    curve_counts: Dict[str, int] = {b: 0 for b in curve_bins}
    curve_cards: Dict[str, List[Dict[str, Any]]] = {b: [] for b in curve_bins}

    def _mv_bucket(mv: Any) -> str:
        try:
            v = float(mv)
        except Exception:
            v = 0.0
        return "6+" if v >= 6 else str(int(v))

    for r in rows:
        if r["is_commander"]:
            continue
        cat = _deck_type_category(r["type"])
        type_counts[cat] = type_counts.get(cat, 0) + r["count"]
        type_cards.setdefault(cat, []).append({
            "name": r["name"], "count": r["count"], "tags": r["tags"],
        })
        if "land" not in r["type"].lower():
            bucket = _mv_bucket(r["cmc"])
            curve_counts[bucket] += r["count"]
            curve_cards[bucket].append({"name": r["name"], "count": r["count"]})

    type_order = [t for t in _DECK_TYPE_ORDER if t in type_counts]
    mana_summary = _mana_pip_and_source_summary(sess)
    return {
        "type_breakdown": {
            "counts": type_counts,
            "order": type_order,
            "cards": type_cards,
            "total": sum(type_counts.values()),
        },
        "pip_distribution": mana_summary["pip_distribution"],
        "mana_generation": mana_summary["mana_generation"],
        "mana_curve": {
            **curve_counts,
            "total_spells": sum(curve_counts.values()),
            "cards": curve_cards,
        },
        "colors": list(sess.get("color_identity") or []),
    }


def save_manual_deck(sess: Dict[str, Any], deck_dir: str) -> tuple:
    """Write the manual deck's CSV + TXT + `.summary.json` + `_compliance.json`
    sidecars. Mirrors `deck_import_service.save_imported_deck`'s file-writing
    pattern so saved manual decks are indistinguishable from any other deck
    to R23 Suggested Upgrades / R24 Import Analysis.

    If `sess["edit_source_path"]` is set (deck opened via "Edit Deck" from an
    existing saved deck), overwrites that same file in place instead of
    generating a new dated filename, preserving any extra fields already in
    its `.summary.json` (e.g. original `source`) and its stored visibility.

    Returns ``(csv_name, txt_name, summary_name)`` - bare filenames.
    Raises RuntimeError on any write failure.
    """
    commander_name = sess.get("commander") or "Manual_Deck"
    os.makedirs(deck_dir, exist_ok=True)

    edit_source = sess.get("edit_source_path")
    orig_meta: Dict[str, Any] = {}
    if edit_source and os.path.exists(edit_source) and os.path.dirname(os.path.abspath(edit_source)) == os.path.abspath(deck_dir):
        csv_path = edit_source
        csv_name = os.path.basename(csv_path)
        sidecar = csv_path.replace(".csv", ".summary.json")
        if os.path.exists(sidecar):
            try:
                orig_meta = (json.loads(open(sidecar, "r", encoding="utf-8").read()) or {}).get("meta") or {}
            except Exception:
                orig_meta = {}
    else:
        slug = _safe_slug(commander_name)
        today = _date.today().strftime("%Y%m%d")
        base = f"{slug}_{today}"
        counter = 0
        while True:
            suffix = f"_{counter}" if counter else ""
            csv_name = f"{base}{suffix}.csv"
            if not os.path.exists(os.path.join(deck_dir, csv_name)):
                break
            counter += 1
        csv_path = os.path.join(deck_dir, csv_name)

    txt_name = csv_name.replace(".csv", ".txt")
    summary_name = csv_name.replace(".csv", ".summary.json")
    compliance_name = csv_name.replace(".csv", "_compliance.json")
    txt_path = os.path.join(deck_dir, txt_name)
    summary_path = os.path.join(deck_dir, summary_name)
    compliance_path = os.path.join(deck_dir, compliance_name)

    # Resolve visibility before overwriting the sidecar so an edit preserves
    # whatever visibility was already set on the deck.
    visibility = resolve_visibility_for_write(csv_path, deck_dir=deck_dir)

    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(build_deck_csv_text(sess))
    except Exception as exc:
        raise RuntimeError(f"Failed to write CSV: {exc}") from exc

    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(build_deck_txt_text(sess))
    except Exception as exc:
        try:
            os.remove(csv_path)
        except Exception:
            pass
        raise RuntimeError(f"Failed to write TXT: {exc}") from exc

    try:
        meta = {
            **orig_meta,
            "commander": commander_name,
            "commander_names": [commander_name],
            "name": commander_name,
            "tags": list(sess.get("tags") or []),
            "color_identity": list(sess.get("color_identity") or []),
            "source": orig_meta.get("source") or "manual",
            "bracket": sess.get("bracket"),
            "csv": csv_name,
            "txt": txt_name,
            "budget_config": sess.get("budget_config") or orig_meta.get("budget_config") or {},
            "visibility": visibility,
        }
        if edit_source:
            meta["last_edited"] = _date.today().isoformat()
        card_count = sum(deck_card_counts(sess).values()) + (1 if commander_name else 0)
        summary = {"card_count": card_count, **_build_deck_summary(sess)}
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "summary": summary}, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        try:
            os.remove(csv_path)
            os.remove(txt_path)
        except Exception:
            pass
        raise RuntimeError(f"Failed to write summary JSON: {exc}") from exc

    try:
        names = list(deck_card_counts(sess).keys())
        if commander_name:
            names.append(commander_name)
        raw_report = evaluate_deck(
            {n: {} for n in names},
            commander_name=commander_name,
            bracket=str(sess.get("bracket") or 2),
        )
        with open(compliance_path, "w", encoding="utf-8") as fh:
            json.dump(raw_report, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Compliance sidecar is a best-effort convenience; never fail the save over it.
        pass

    return csv_name, txt_name, summary_name


# ---------------------------------------------------------------------------
# Deck editor: load an existing saved deck into a manual-builder session
# ---------------------------------------------------------------------------

def _read_counts_from_csv(csv_path: str) -> Dict[str, int]:
    """Name -> total count from a saved deck CSV. A small local reader (kept
    separate from `decks.py`'s `_read_deck_counts` since services shouldn't
    import route modules).
    """
    counts: Dict[str, int] = {}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = _csv.reader(fh)
            headers = next(reader, [])
            name_idx = headers.index("Name") if "Name" in headers else 0
            count_idx = headers.index("Count") if "Count" in headers else 1
            for row in reader:
                if not row:
                    continue
                try:
                    name = str(row[name_idx]).strip()
                except Exception:
                    continue
                if not name:
                    continue
                try:
                    cnt = int(float(row[count_idx])) if row[count_idx] else 1
                except Exception:
                    cnt = 1
                counts[name] = counts.get(name, 0) + cnt
    except Exception:
        pass
    return counts


def load_deck_for_edit(sess: Dict[str, Any], csv_path: str) -> None:
    """Populate a manual-builder session from an existing saved deck's CSV
    and sidecars, so "Edit Deck" reuses the exact same pool/add/remove/save
    UI as building a deck from scratch. Sets `sess["edit_source_path"]` so
    `save_manual_deck` overwrites this file in place instead of creating a
    new one.
    """
    meta: Dict[str, Any] = {}
    sidecar = csv_path.replace(".csv", ".summary.json")
    if os.path.exists(sidecar):
        try:
            meta = (json.loads(open(sidecar, "r", encoding="utf-8").read()) or {}).get("meta") or {}
        except Exception:
            meta = {}

    commander = meta.get("commander") or ""
    color_identity = list(meta.get("color_identity") or [])
    if not color_identity and commander:
        color_identity = resolve_color_identity(commander)

    # Bracket isn't always in the sidecar meta (older/imported/auto-built
    # decks) - fall back to the compliance sidecar's recorded level, then a
    # hard default of Bracket 2 (Core), matching the New Deck modal's default.
    bracket = meta.get("bracket")
    if not bracket:
        compliance_path = csv_path.replace(".csv", "_compliance.json")
        if os.path.exists(compliance_path):
            try:
                comp = json.loads(open(compliance_path, "r", encoding="utf-8").read()) or {}
                bracket = comp.get("level")
            except Exception:
                bracket = None
    bracket = int(bracket) if bracket else 2

    counts = _read_counts_from_csv(csv_path)
    counts.pop(commander, None)
    deck_cards: List[str] = []
    for name, count in counts.items():
        deck_cards.extend([name] * count)

    sess["mode"] = "manual"
    sess["commander"] = commander
    sess["color_identity"] = color_identity
    sess["tags"] = list(meta.get("tags") or [])
    sess["bracket"] = bracket
    sess["budget_config"] = meta.get("budget_config") or {}
    sess["deck_cards"] = deck_cards
    sess["edit_source_path"] = csv_path
    sess["edit_source_name"] = os.path.basename(csv_path)
    sess.pop("_pool_df", None)
