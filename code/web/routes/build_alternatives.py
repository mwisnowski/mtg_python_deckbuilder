"""Build Alternatives Route

Phase 5 extraction from build.py:
- GET /build/alternatives - Role-based card suggestions with tag overlap fallback

This module provides intelligent alternative card suggestions based on deck role,
tags, and builder context. Supports owned-only filtering and caching.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Any
from ..app import templates
from ..services.tasks import get_session, new_sid
from ..services.build_utils import owned_set as owned_set_helper, builder_present_names, builder_display_map
from deck_builder.builder import DeckBuilder
from deck_builder import builder_constants as bc
from deck_builder import builder_utils as bu
from ..services.alts_utils import get_cached as _alts_get_cached, set_cached as _alts_set_cached


router = APIRouter(prefix="/build")


@router.get("/alternatives", response_class=HTMLResponse)
async def build_alternatives(
    request: Request,
    name: str,
    stage: str | None = None,
    owned_only: int = Query(0),
    refresh: int = Query(0),
) -> HTMLResponse:
    """Suggest alternative cards for a given card name, preferring role-specific pools.

    Strategy:
    1) Determine the seed card's role from the current deck (Role field) or optional `stage` hint.
    2) Build a candidate pool from the combined DataFrame using the same filters as the build phase
       for that role (ramp/removal/wipes/card_advantage/protection).
    3) Exclude commander, lands (where applicable), in-deck, locked, and the seed itself; then sort
       by edhrecRank/manaValue. Apply owned-only filter if requested.
    4) Fall back to tag-overlap similarity when role cannot be determined or data is missing.

    Returns an HTML partial listing up to ~10 alternatives with Replace buttons.
    """
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    ctx = sess.get("build_ctx") or {}
    b = ctx.get("builder") if isinstance(ctx, dict) else None
    # Owned library
    owned_set = owned_set_helper()
    require_owned = bool(int(owned_only or 0)) or bool(sess.get("use_owned_only"))
    refresh_requested = bool(int(refresh or 0))
    # If builder context missing, show a guidance message
    if not b:
        html = '<div class="alts"><div class="muted">Start the build to see alternatives.</div></div>'
        return HTMLResponse(html)
    try:
        name_disp = str(name).strip()
        name_l = name_disp.lower()
        commander_l = str((sess.get("commander") or "")).strip().lower()
        locked_set = {str(x).strip().lower() for x in (sess.get("locks", []) or [])}
        # Exclusions from prior inline replacements
        alts_exclude = {str(x).strip().lower() for x in (sess.get("alts_exclude", []) or [])}
        alts_exclude_v = int(sess.get("alts_exclude_v") or 0)

        # Resolve role from stage hint or current library entry
        stage_hint = (stage or "").strip().lower()
        stage_map = {
            "ramp": "ramp",
            "removal": "removal",
            "wipes": "wipe",
            "wipe": "wipe",
            "board_wipe": "wipe",
            "card_advantage": "card_advantage",
            "draw": "card_advantage",
            "protection": "protection",
            # Additional mappings for creature stages
            "creature": "creature",
            "creatures": "creature",
            "primary": "creature",
            "secondary": "creature",
            # Land-related hints
            "land": "land",
            "lands": "land",
            "utility": "land",
            "misc": "land",
            "fetch": "land",
            "dual": "land",
        }
        hinted_role = stage_map.get(stage_hint) if stage_hint else None
        lib = getattr(b, "card_library", {}) or {}
        # Case-insensitive lookup in deck library
        lib_key = None
        try:
            if name_disp in lib:
                lib_key = name_disp
            else:
                lm = {str(k).strip().lower(): k for k in lib.keys()}
                lib_key = lm.get(name_l)
        except Exception:
            lib_key = None
        entry = lib.get(lib_key) if lib_key else None
        role = hinted_role or (entry.get("Role") if isinstance(entry, dict) else None)
        if isinstance(role, str):
            role = role.strip().lower()

        # Build role-specific pool from combined DataFrame
        items: list[dict] = []

        def _clean(value: Any) -> str:
            try:
                if value is None:
                    return ""
                if isinstance(value, float) and value != value:
                    return ""
                text = str(value)
                return text.strip()
            except Exception:
                return ""

        def _normalize_tags(raw: Any) -> list[str]:
            if not raw:
                return []
            if isinstance(raw, (list, tuple, set)):
                return [str(t).strip() for t in raw if str(t).strip()]
            if isinstance(raw, str):
                txt = raw.strip()
                if not txt:
                    return []
                if txt.startswith("[") and txt.endswith("]"):
                    try:
                        import json as _json
                        parsed = _json.loads(txt)
                        if isinstance(parsed, list):
                            return [str(t).strip() for t in parsed if str(t).strip()]
                    except Exception:
                        pass
                return [s.strip() for s in txt.split(',') if s.strip()]
            return []

        def _meta_from_row(row_obj: Any) -> dict[str, Any]:
            meta = {
                "mana": "",
                "rarity": "",
                "role": "",
                "tags": [],
                "hover_simple": True,
            }
            if row_obj is None:
                meta["role"] = _clean(used_role or "")
                return meta

            def _pull(*keys: str) -> Any:
                for key in keys:
                    try:
                        if isinstance(row_obj, dict):
                            val = row_obj.get(key)
                        elif hasattr(row_obj, "get"):
                            val = row_obj.get(key)
                        else:
                            val = getattr(row_obj, key, None)
                    except Exception:
                        val = None
                    if val not in (None, ""):
                        if isinstance(val, float) and val != val:
                            continue
                        return val
                return None

            meta["mana"] = _clean(_pull("mana_cost", "manaCost", "mana", "manaValue", "cmc", "mv"))
            meta["rarity"] = _clean(_pull("rarity"))
            role_val = _pull("role", "primaryRole", "subRole")
            if not role_val:
                role_val = used_role or ""
            meta["role"] = _clean(role_val)
            tags_val = _pull("themeTags", "_ltags", "tags")
            meta_tags = _normalize_tags(tags_val)
            meta["tags"] = meta_tags
            meta["hover_simple"] = not (meta["mana"] or meta["rarity"] or (meta_tags and len(meta_tags) > 0))
            return meta

        def _build_meta_map(df_obj) -> dict[str, dict[str, Any]]:
            mapping: dict[str, dict[str, Any]] = {}
            try:
                if df_obj is None or not hasattr(df_obj, "iterrows"):
                    return mapping
                for _, row in df_obj.iterrows():
                    try:
                        nm_val = str(row.get("name") or "").strip()
                    except Exception:
                        nm_val = ""
                    if not nm_val:
                        continue
                    key = nm_val.lower()
                    if key in mapping:
                        continue
                    mapping[key] = _meta_from_row(row)
            except Exception:
                return mapping
            return mapping

        def _sampler(seq: list[str], limit: int) -> list[str]:
            if limit <= 0:
                return []
            if len(seq) <= limit:
                return list(seq)
            rng = getattr(b, "rng", None)
            try:
                if rng is not None:
                    return rng.sample(seq, limit) if len(seq) >= limit else list(seq)
                import random as _rnd
                return _rnd.sample(seq, limit) if len(seq) >= limit else list(seq)
            except Exception:
                return list(seq[:limit])
        used_role = role if isinstance(role, str) and role else None
        # Promote to 'land' role when the seed card is a land (regardless of stored role)
        try:
            if entry and isinstance(entry, dict):
                ctype = str(entry.get("Card Type") or entry.get("Type") or "").lower()
                if "land" in ctype:
                    used_role = "land"
        except Exception:
            pass
        df = getattr(b, "_combined_cards_df", None)

        # Compute current deck fingerprint to avoid stale cached alternatives after stage changes
        in_deck: set[str] = builder_present_names(b)
        try:
            import hashlib as _hl
            deck_fp = _hl.md5(
                ("|".join(sorted(in_deck)) if in_deck else "").encode("utf-8")
            ).hexdigest()[:8]
        except Exception:
            deck_fp = str(len(in_deck))

        # Use a cache key that includes the exclusions version and deck fingerprint
        cache_key = (name_l, commander_l, used_role or "_fallback_", require_owned, alts_exclude_v, deck_fp)
        cached = None
        if used_role != 'land' and not refresh_requested:
            cached = _alts_get_cached(cache_key)
        if cached is not None:
            return HTMLResponse(cached)

        def _render_and_cache(_items: list[dict]):
            html_str = templates.get_template("build/_alternatives.html").render({
                "request": request,
                "name": name_disp,
                "require_owned": require_owned,
                "items": _items,
            })
            # Skip caching when used_role == land or refresh requested for per-call randomness
            if used_role != 'land' and not refresh_requested:
                try:
                    _alts_set_cached(cache_key, html_str)
                except Exception:
                    pass
            return HTMLResponse(html_str)

        # Helper: map display names
        def _display_map_for(lower_pool: set[str]) -> dict[str, str]:
            try:
                return builder_display_map(b, lower_pool)
            except Exception:
                return {nm: nm for nm in lower_pool}

        # Common exclusions
    # in_deck already computed above

        def _exclude(df0):
            out = df0.copy()
            if "name" in out.columns:
                out["_lname"] = out["name"].astype(str).str.strip().str.lower()
                mask = ~out["_lname"].isin({name_l} | in_deck | locked_set | alts_exclude | ({commander_l} if commander_l else set()))
                out = out[mask]
            return out

        # If we have data and a recognized role, mirror the phase logic
        if df is not None and hasattr(df, "copy") and (used_role in {"ramp","removal","wipe","card_advantage","protection","creature","land"}):
            pool = df.copy()
            try:
                pool["_ltags"] = pool.get("themeTags", []).apply(bu.normalize_tag_cell)
            except Exception:
                # best-effort normalize
                pool["_ltags"] = pool.get("themeTags", []).apply(lambda x: [str(t).strip().lower() for t in (x or [])] if isinstance(x, list) else [])
            # Role-specific base filtering
            if used_role != "land":
                # Exclude lands for non-land roles
                if "type" in pool.columns:
                    pool = pool[~pool["type"].fillna("").str.contains("Land", case=False, na=False)]
            else:
                # Keep only lands
                if "type" in pool.columns:
                    pool = pool[pool["type"].fillna("").str.contains("Land", case=False, na=False)]
                # Seed info to guide filtering
                seed_is_basic = False
                try:
                    seed_is_basic = bool(name_l in {b.strip().lower() for b in getattr(bc, 'BASIC_LANDS', [])})
                except Exception:
                    seed_is_basic = False
                if seed_is_basic:
                    # For basics: show other basics (different colors) to allow quick swaps
                    try:
                        pool = pool[pool['name'].astype(str).str.strip().str.lower().isin({x.lower() for x in getattr(bc, 'BASIC_LANDS', [])})]
                    except Exception:
                        pass
                else:
                    # For non-basics: prefer other non-basics
                    try:
                        pool = pool[~pool['name'].astype(str).str.strip().str.lower().isin({x.lower() for x in getattr(bc, 'BASIC_LANDS', [])})]
                    except Exception:
                        pass
                # Apply mono-color misc land filters (no debug CSV dependency)
                try:
                    colors = list(getattr(b, 'color_identity', []) or [])
                    mono = len(colors) <= 1
                    mono_exclude = {n.lower() for n in getattr(bc, 'MONO_COLOR_MISC_LAND_EXCLUDE', [])}
                    mono_keep = {n.lower() for n in getattr(bc, 'MONO_COLOR_MISC_LAND_KEEP_ALWAYS', [])}
                    kindred_all = {n.lower() for n in getattr(bc, 'KINDRED_ALL_LAND_NAMES', [])}
                    any_color_phrases = [s.lower() for s in getattr(bc, 'ANY_COLOR_MANA_PHRASES', [])]
                    extra_rainbow_terms = [s.lower() for s in getattr(bc, 'MONO_COLOR_RAINBOW_TEXT_EXTRA', [])]
                    fetch_names = set()
                    for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
                        for nm in seq:
                            fetch_names.add(nm.lower())
                    for nm in getattr(bc, 'GENERIC_FETCH_LANDS', []):
                        fetch_names.add(nm.lower())
                    # World Tree check needs all five colors
                    need_all_colors = {'w','u','b','r','g'}
                    def _illegal_world_tree(nm: str) -> bool:
                        return nm == 'the world tree' and set(c.lower() for c in colors) != need_all_colors
                    # Text column fallback
                    text_col = 'text'
                    if text_col not in pool.columns:
                        for c in pool.columns:
                            if 'text' in c.lower():
                                text_col = c
                                break
                    def _exclude_row(row) -> bool:
                        nm_l = str(row['name']).strip().lower()
                        if mono and nm_l in mono_exclude and nm_l not in mono_keep and nm_l not in kindred_all:
                            return True
                        if mono and nm_l not in mono_keep and nm_l not in kindred_all:
                            try:
                                txt = str(row.get(text_col, '') or '').lower()
                                if any(p in txt for p in any_color_phrases + extra_rainbow_terms):
                                    return True
                            except Exception:
                                pass
                        if nm_l in fetch_names:
                            return True
                        if _illegal_world_tree(nm_l):
                            return True
                        return False
                    pool = pool[~pool.apply(_exclude_row, axis=1)]
                except Exception:
                    pass
                # Optional sub-role filtering (only if enough depth)
                try:
                    subrole = str((entry or {}).get('SubRole') or '').strip().lower()
                    if subrole:
                        # Heuristic categories for grouping
                        cat_map = {
                            'fetch': 'fetch',
                            'dual': 'dual',
                            'triple': 'triple',
                            'misc': 'misc',
                            'utility': 'misc',
                            'basic': 'basic'
                        }
                        target_cat = None
                        for key, val in cat_map.items():
                            if key in subrole:
                                target_cat = val
                                break
                        if target_cat and len(pool) > 25:
                            # Lightweight textual filter using known markers
                            def _cat_row(rname: str, rtype: str) -> str:
                                rl = rname.lower()
                                rt = rtype.lower()
                                if any(k in rl for k in ('vista','strand','delta','mire','heath','rainforest','mesa','foothills','catacombs','tarn','flat','expanse','wilds','landscape','tunnel','terrace','vista')):
                                    return 'fetch'
                                if 'triple' in rt or 'three' in rt:
                                    return 'triple'
                                if any(t in rt for t in ('forest','plains','island','swamp','mountain')) and any(sym in rt for sym in ('forest','plains','island','swamp','mountain')) and 'land' in rt:
                                    # Basic-check crude
                                    return 'basic'
                                return 'misc'
                            try:
                                tmp = pool.copy()
                                tmp['_cat'] = tmp.apply(lambda r: _cat_row(str(r.get('name','')), str(r.get('type',''))), axis=1)
                                sub_pool = tmp[tmp['_cat'] == target_cat]
                                if len(sub_pool) >= 10:
                                    pool = sub_pool.drop(columns=['_cat'])
                            except Exception:
                                pass
                except Exception:
                    pass
            # Exclude commander explicitly
            if "name" in pool.columns and commander_l:
                pool = pool[pool["name"].astype(str).str.strip().str.lower() != commander_l]
            # Role-specific filter
            def _is_wipe(tags: list[str]) -> bool:
                return any(("board wipe" in t) or ("mass removal" in t) for t in tags)
            def _is_removal(tags: list[str]) -> bool:
                return any(("removal" in t) or ("spot removal" in t) for t in tags)
            def _is_draw(tags: list[str]) -> bool:
                return any(("draw" in t) or ("card advantage" in t) for t in tags)
            def _matches_selected(tags: list[str]) -> bool:
                try:
                    sel = [str(t).strip().lower() for t in (sess.get("tags") or []) if str(t).strip()]
                    if not sel:
                        return True
                    st = set(sel)
                    return any(any(s in t for s in st) for t in tags)
                except Exception:
                    return True
            if used_role == "ramp":
                pool = pool[pool["_ltags"].apply(lambda tags: any("ramp" in t for t in tags))]
            elif used_role == "removal":
                pool = pool[pool["_ltags"].apply(_is_removal) & ~pool["_ltags"].apply(_is_wipe)]
            elif used_role == "wipe":
                pool = pool[pool["_ltags"].apply(_is_wipe)]
            elif used_role == "card_advantage":
                pool = pool[pool["_ltags"].apply(_is_draw)]
            elif used_role == "protection":
                pool = pool[pool["_ltags"].apply(lambda tags: any("protection" in t for t in tags))]
            elif used_role == "creature":
                # Keep only creatures; bias toward selected theme tags when available
                if "type" in pool.columns:
                    pool = pool[pool["type"].fillna("").str.contains("Creature", case=False, na=False)]
                try:
                    pool = pool[pool["_ltags"].apply(_matches_selected)]
                except Exception:
                    pass
            elif used_role == "land":
                # Already constrained to lands; no additional tag filter needed
                pass
            # Sort by priority like the builder
            try:
                pool = bu.sort_by_priority(pool, ["edhrecRank","manaValue"])
            except Exception:
                pass
            # Exclusions and ownership (for non-random roles this stays before slicing)
            pool = _exclude(pool)
            try:
                if bool(sess.get("prefer_owned")) and getattr(b, "owned_card_names", None):
                    pool = bu.prefer_owned_first(pool, {str(n).lower() for n in getattr(b, "owned_card_names", set())})
            except Exception:
                pass
            row_meta = _build_meta_map(pool)
            # Land role: random 12 from top 60-100 window
            if used_role == 'land':
                import random as _rnd
                total = len(pool)
                if total == 0:
                    pass
                else:
                    cap = min(100, total)
                    floor = min(60, cap)  # if fewer than 60 just use all
                    if cap <= 12:
                        window_size = cap
                    else:
                        if cap == floor:
                            window_size = cap
                        else:
                            rng_obj = getattr(b, 'rng', None)
                            if rng_obj:
                                window_size = rng_obj.randint(floor, cap)
                            else:
                                window_size = _rnd.randint(floor, cap)
                    window_df = pool.head(window_size)
                    names = window_df['name'].astype(str).str.strip().tolist()
                    # Random sample up to 12 distinct names
                    sample_n = min(12, len(names))
                    if sample_n > 0:
                        if getattr(b, 'rng', None):
                            chosen = getattr(b,'rng').sample(names, sample_n) if len(names) >= sample_n else names
                        else:
                            chosen = _rnd.sample(names, sample_n) if len(names) >= sample_n else names
                        lower_map = {n.strip().lower(): n for n in chosen}
                        display_map = _display_map_for(set(k for k in lower_map.keys()))
                        for nm_lc, orig in lower_map.items():
                            is_owned = (nm_lc in owned_set)
                            if require_owned and not is_owned:
                                continue
                            if nm_lc == name_l or (in_deck and nm_lc in in_deck):
                                continue
                            meta = row_meta.get(nm_lc) or _meta_from_row(None)
                            items.append({
                                'name': display_map.get(nm_lc, orig),
                                'name_lower': nm_lc,
                                'owned': is_owned,
                                'tags': meta.get('tags') or [],
                                'role': meta.get('role', ''),
                                'mana': meta.get('mana', ''),
                                'rarity': meta.get('rarity', ''),
                                'hover_simple': bool(meta.get('hover_simple', True)),
                            })
                if items:
                    return _render_and_cache(items)
            else:
                # Default deterministic top-N (increase to 12 for parity)
                lower_pool: list[str] = []
                try:
                    lower_pool = pool["name"].astype(str).str.strip().str.lower().tolist()
                except Exception:
                    lower_pool = []
                display_map = _display_map_for(set(lower_pool))
                iteration_order = lower_pool
                if refresh_requested and len(lower_pool) > 12:
                    window_size = min(len(lower_pool), 30)
                    window = lower_pool[:window_size]
                    sampled = _sampler(window, min(window_size, 12))
                    seen_sampled = set(sampled)
                    iteration_order = sampled + [nm for nm in lower_pool if nm not in seen_sampled]
                for nm_l in iteration_order:
                    is_owned = (nm_l in owned_set)
                    if require_owned and not is_owned:
                        continue
                    if nm_l == name_l or (in_deck and nm_l in in_deck):
                        continue
                    meta = row_meta.get(nm_l) or _meta_from_row(None)
                    items.append({
                        "name": display_map.get(nm_l, nm_l),
                        "name_lower": nm_l,
                        "owned": is_owned,
                        "tags": meta.get("tags") or [],
                        "role": meta.get("role", ""),
                        "mana": meta.get("mana", ""),
                        "rarity": meta.get("rarity", ""),
                        "hover_simple": bool(meta.get("hover_simple", True)),
                    })
                    if len(items) >= 12:
                        break
                if items:
                    return _render_and_cache(items)

        # Fallback: tag-similarity suggestions (previous behavior)
        tags_idx = getattr(b, "_card_name_tags_index", {}) or {}
        seed_tags = set(tags_idx.get(name_l) or [])
        all_names = set(tags_idx.keys())
        candidates: list[tuple[str, int]] = []  # (name, score)
        for nm in all_names:
            if nm == name_l:
                continue
            if commander_l and nm == commander_l:
                continue
            if in_deck and nm in in_deck:
                continue
            if locked_set and nm in locked_set:
                continue
            if nm in alts_exclude:
                continue
            tgs = set(tags_idx.get(nm) or [])
            score = len(seed_tags & tgs)
            if score <= 0:
                continue
            candidates.append((nm, score))
        # If no tag-based candidates, try shared trigger tag from library entry
        if not candidates and isinstance(entry, dict):
            try:
                trig = str(entry.get("TriggerTag") or "").strip().lower()
            except Exception:
                trig = ""
            if trig:
                for nm, tglist in tags_idx.items():
                    if nm == name_l:
                        continue
                    if nm in {str(k).strip().lower() for k in lib.keys()}:
                        continue
                    if trig in {str(t).strip().lower() for t in (tglist or [])}:
                        candidates.append((nm, 1))
        def _owned(nm: str) -> bool:
            return nm in owned_set
        candidates.sort(key=lambda x: (-x[1], 0 if _owned(x[0]) else 1, x[0]))
        if refresh_requested and len(candidates) > 1:
            name_sequence = [nm for nm, _score in candidates]
            sampled_names = _sampler(name_sequence, min(len(name_sequence), 10))
            sampled_set = set(sampled_names)
            reordered: list[tuple[str, int]] = []
            for nm in sampled_names:
                for cand_nm, cand_score in candidates:
                    if cand_nm == nm:
                        reordered.append((cand_nm, cand_score))
                        break
            for cand_nm, cand_score in candidates:
                if cand_nm not in sampled_set:
                    reordered.append((cand_nm, cand_score))
            candidates = reordered
        pool_lower = {nm for (nm, _s) in candidates}
        display_map = _display_map_for(pool_lower)
        seen = set()
        for nm, score in candidates:
            if nm in seen:
                continue
            seen.add(nm)
            is_owned = (nm in owned_set)
            if require_owned and not is_owned:
                continue
            items.append({
                "name": display_map.get(nm, nm),
                "name_lower": nm,
                "owned": is_owned,
                "tags": list(tags_idx.get(nm) or []),
                "role": "",
                "mana": "",
                "rarity": "",
                "hover_simple": True,
            })
            if len(items) >= 10:
                break
        return _render_and_cache(items)
    except Exception as e:
        return HTMLResponse(f'<div class="alts"><div class="muted">No alternatives: {e}</div></div>')
