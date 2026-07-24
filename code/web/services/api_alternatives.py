"""Role-based alternative card suggestions for the public REST API.

Lighter-weight sibling of `routes/build_alternatives.py` (the HTML/session
route used by the web wizard). Shares the same role-resolution and filtering
approach (role from the deck-library entry, role-tag pool filtering, sort by
edhrecRank/manaValue, tag-overlap fallback), but returns plain JSON-ready
dicts instead of an HTML partial and takes explicit params instead of reading
a cookie session. Intentionally skips the web route's land-specific
sub-heuristics (mono-color exclusions, fetch/dual/triple sub-role bucketing,
World Tree color check) -- those are cosmetic refinements, not needed for a
correct v1 API result set.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from deck_builder import builder_utils as bu

from .build_utils import builder_display_map, builder_present_names, owned_set as owned_set_helper

_ROLE_TAG_ROLES = {"ramp", "removal", "wipe", "card_advantage", "protection", "creature", "land"}


def _is_wipe(tags: List[str]) -> bool:
    return any(("board wipe" in t) or ("mass removal" in t) for t in tags)


def _is_removal(tags: List[str]) -> bool:
    return any(("removal" in t) or ("spot removal" in t) for t in tags)


def _is_draw(tags: List[str]) -> bool:
    return any(("draw" in t) or ("card advantage" in t) for t in tags)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and value != value:  # NaN
            return ""
        return str(value).strip()
    except Exception:
        return ""


def suggest_alternatives(
    b: Any,
    card_name: str,
    *,
    role_hint: Optional[str] = None,
    owned_only: bool = False,
    exclude: Optional[Iterable[str]] = None,
    locked: Optional[Iterable[str]] = None,
    commander: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Suggest up to `limit` alternative cards for `card_name`.

    Resolves role from `role_hint` if given, else from the card's current
    `Role` entry in `b.card_library`. Falls back to tag-overlap similarity
    when the role can't be determined or card data is unavailable.
    """
    name_disp = str(card_name).strip()
    name_l = name_disp.lower()
    commander_l = str(commander or "").strip().lower()
    locked_set = {str(x).strip().lower() for x in (locked or [])}
    exclude_set = {str(x).strip().lower() for x in (exclude or [])}
    owned = owned_set_helper()

    lib = getattr(b, "card_library", {}) or {}
    lib_key = None
    if name_disp in lib:
        lib_key = name_disp
    else:
        lower_map = {str(k).strip().lower(): k for k in lib.keys()}
        lib_key = lower_map.get(name_l)
    entry = lib.get(lib_key) if lib_key else None

    role = (role_hint or "").strip().lower() or None
    if not role and isinstance(entry, dict):
        raw_role = entry.get("Role")
        role = str(raw_role).strip().lower() if raw_role else None
    if isinstance(entry, dict):
        card_type = str(entry.get("Card Type") or entry.get("Type") or "").lower()
        if "land" in card_type:
            role = "land"

    # The specific theme tag(s) that caused this card to be added (e.g. a
    # creature added during the "Creatures: Primary" stage for an "Angel
    # Kindred" theme carries `TriggerTag='Angel Kindred'`). When present,
    # alternatives are narrowed to cards sharing at least one of these tags
    # so swaps stay on-theme instead of pulling from the whole role pool.
    trigger_tags: List[str] = []
    if isinstance(entry, dict):
        raw_trigger = entry.get("TriggerTag")
        if raw_trigger:
            trigger_tags = [t.strip().lower() for t in str(raw_trigger).split(",") if t.strip()]

    in_deck = builder_present_names(b)
    df = getattr(b, "_combined_cards_df", None)

    items: List[Dict[str, Any]] = []

    def _excluded(nm_l: str) -> bool:
        return (
            nm_l == name_l
            or nm_l in in_deck
            or nm_l in locked_set
            or nm_l in exclude_set
            or (commander_l and nm_l == commander_l)
        )

    if df is not None and hasattr(df, "copy") and role in _ROLE_TAG_ROLES:
        pool = df.copy()
        try:
            pool["_ltags"] = pool.get("themeTags", []).apply(bu.normalize_tag_cell)
        except Exception:
            pool["_ltags"] = pool.get("themeTags", []).apply(
                lambda x: [str(t).strip().lower() for t in (x or [])] if isinstance(x, list) else []
            )
        if "type" in pool.columns:
            if role == "land":
                pool = pool[pool["type"].fillna("").str.contains("Land", case=False, na=False)]
            else:
                pool = pool[~pool["type"].fillna("").str.contains("Land", case=False, na=False)]
        if "name" in pool.columns and commander_l:
            pool = pool[pool["name"].astype(str).str.strip().str.lower() != commander_l]

        if role == "ramp":
            pool = pool[pool["_ltags"].apply(lambda tags: any("ramp" in t for t in tags))]
        elif role == "removal":
            pool = pool[pool["_ltags"].apply(_is_removal) & ~pool["_ltags"].apply(_is_wipe)]
        elif role == "wipe":
            pool = pool[pool["_ltags"].apply(_is_wipe)]
        elif role == "card_advantage":
            pool = pool[pool["_ltags"].apply(_is_draw)]
        elif role == "protection":
            pool = pool[pool["_ltags"].apply(lambda tags: any("protection" in t for t in tags))]
        elif role == "creature":
            if "type" in pool.columns:
                pool = pool[pool["type"].fillna("").str.contains("Creature", case=False, na=False)]
        # role == "land": no extra tag filter beyond the type filter above,
        # except a color-identity safety filter for fetch-shaped lands (a
        # fetch land is never a correct suggestion if it can't find a basic
        # in the commander's colors)
        if role == "land" and "metadataTags" in pool.columns:
            colors = list(getattr(b, "color_identity", []) or [])
            try:
                pool = pool[pool["metadataTags"].apply(lambda mt: bu.fetch_land_allowed_for_colors(mt, colors))]
            except Exception:
                pass

        if trigger_tags:
            def _matches_trigger(tags: List[str]) -> bool:
                return any(t in tags or any(t in x for x in tags) for t in trigger_tags)

            themed_pool = pool[pool["_ltags"].apply(_matches_trigger)]
            if not themed_pool.empty:
                pool = themed_pool

        try:
            pool = bu.sort_by_priority(pool, ["edhrecRank", "manaValue"])
        except Exception:
            pass

        if owned_only and owned:
            try:
                pool = pool[pool["name"].astype(str).str.strip().str.lower().isin(owned)]
            except Exception:
                pass

        if "name" in pool.columns:
            lower_names: List[str] = pool["name"].astype(str).str.strip().str.lower().tolist()
            display_map = builder_display_map(b, set(lower_names))
            for nm_l in lower_names:
                if _excluded(nm_l):
                    continue
                row = pool[pool["name"].astype(str).str.strip().str.lower() == nm_l]
                mana = rarity = ""
                tags: List[str] = []
                if not row.empty:
                    r0 = row.iloc[0]
                    mana = _clean(r0.get("mana_cost") or r0.get("manaCost") or r0.get("manaValue"))
                    rarity = _clean(r0.get("rarity"))
                    tags = [str(t).strip() for t in (r0.get("_ltags") or []) if str(t).strip()]
                    if trigger_tags:
                        def _matches_tag(tag: str, _trigger_tags: List[str] = trigger_tags) -> bool:
                            tl = tag.lower()
                            return any(tt in tl or tl in tt for tt in _trigger_tags)

                        tags.sort(key=lambda t: 0 if _matches_tag(t) else 1)
                items.append(
                    {
                        "name": display_map.get(nm_l, nm_l),
                        "role": role,
                        "mana_cost": mana,
                        "rarity": rarity,
                        "tags": tags,
                        "owned": nm_l in owned,
                    }
                )
                if len(items) >= limit:
                    break

    if items:
        return items

    # Fallback: tag-overlap similarity (mirrors the web route's fallback).
    tags_idx = getattr(b, "_card_name_tags_index", {}) or {}
    seed_tags = set(tags_idx.get(name_l) or [])
    candidates: List[tuple[str, int]] = []
    for nm in tags_idx.keys():
        if _excluded(nm):
            continue
        score = len(seed_tags & set(tags_idx.get(nm) or []))
        if score <= 0:
            continue
        candidates.append((nm, score))
    candidates.sort(key=lambda x: (-x[1], 0 if x[0] in owned else 1, x[0]))
    display_map = builder_display_map(b, {nm for nm, _s in candidates[:limit]})
    for nm, _score in candidates[:limit]:
        items.append(
            {
                "name": display_map.get(nm, nm),
                "role": role or "",
                "mana_cost": "",
                "rarity": "",
                "tags": list(tags_idx.get(nm) or []),
                "owned": nm in owned,
            }
        )
    return items
