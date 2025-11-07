from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
import json

# Lightweight, internal utilities to avoid circular imports
from .brackets_compliance import evaluate_deck, POLICY_FILES


def _load_list_cards(paths: List[str]) -> Set[str]:
    out: Set[str] = set()
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            for n in (data.get("cards") or []):
                if isinstance(n, str) and n.strip():
                    out.add(n.strip())
        except Exception:
            continue
    return out


def _candidate_pool_for_role(builder, role: str) -> List[Tuple[str, dict]]:
    """Return a prioritized list of (name, rowdict) candidates for a replacement of a given role.

    This consults the current combined card pool, filters out lands and already-chosen names,
    and applies a role->tag mapping to find suitable replacements.
    """
    df = getattr(builder, "_combined_cards_df", None)
    if df is None or getattr(df, "empty", True):
        return []
    if "name" not in df.columns:
        return []
    # Normalize tag list per row
    def _norm_tags(x):
        return [str(t).lower() for t in x] if isinstance(x, list) else []
    work = df.copy()
    work["_ltags"] = work.get("themeTags", []).apply(_norm_tags)
    # Role to tag predicates
    def _is_protection(tags: List[str]) -> bool:
        return any("protection" in t for t in tags)

    def _is_draw(tags: List[str]) -> bool:
        return any(("draw" in t) or ("card advantage" in t) for t in tags)

    def _is_removal(tags: List[str]) -> bool:
        return any(("removal" in t) or ("spot removal" in t) for t in tags) and not any(("board wipe" in t) or ("mass removal" in t) for t in tags)

    def _is_wipe(tags: List[str]) -> bool:
        return any(("board wipe" in t) or ("mass removal" in t) for t in tags)

    # Theme fallback: anything that matches selected tags (primary/secondary/tertiary)
    sel_tags = [str(getattr(builder, k, "") or "").strip().lower() for k in ("primary_tag", "secondary_tag", "tertiary_tag")]
    sel_tags = [t for t in sel_tags if t]

    def _matches_theme(tags: List[str]) -> bool:
        if not sel_tags:
            return False
        for t in tags:
            for st in sel_tags:
                if st in t:
                    return True
        return False

    pred = None
    r = str(role or "").strip().lower()
    if r == "protection":
        pred = _is_protection
    elif r == "card_advantage":
        pred = _is_draw
    elif r == "removal":
        pred = _is_removal
    elif r in ("wipe", "board_wipe", "wipes"):
        pred = _is_wipe
    else:
        pred = _matches_theme

    pool = work[~work["type"].fillna("").str.contains("Land", case=False, na=False)]
    if pred is _matches_theme:
        pool = pool[pool["_ltags"].apply(_matches_theme)]
    else:
        pool = pool[pool["_ltags"].apply(pred)]
    # Exclude names already in the library
    already_lower = {str(n).lower() for n in getattr(builder, "card_library", {}).keys()}
    pool = pool[~pool["name"].astype(str).str.lower().isin(already_lower)]

    # Sort by edhrecRank then manaValue
    try:
        from . import builder_utils as bu
        sorted_df = bu.sort_by_priority(pool, ["edhrecRank", "manaValue"])
        # Prefer-owned bias
        if getattr(builder, "prefer_owned", False):
            owned = getattr(builder, "owned_card_names", None)
            if owned:
                sorted_df = bu.prefer_owned_first(sorted_df, {str(n).lower() for n in owned})
    except Exception:
        sorted_df = pool

    out: List[Tuple[str, dict]] = []
    for _, r in sorted_df.iterrows():
        nm = str(r.get("name"))
        if not nm:
            continue
        out.append((nm, r.to_dict()))
    return out


def _remove_card(builder, name: str) -> bool:
    entry = getattr(builder, "card_library", {}).get(name)
    if not entry:
        return False
    # Protect commander and locks
    if bool(entry.get("Commander")):
        return False
    if str(entry.get("AddedBy", "")).strip().lower() == "lock":
        return False
    try:
        del builder.card_library[name]
        return True
    except Exception:
        return False


def _try_add_replacement(builder, target_role: Optional[str], forbidden: Set[str]) -> Optional[str]:
    """Attempt to add one replacement card for the given role, avoiding forbidden names.

    Returns the name added, or None if no suitable candidate was found/added.
    """
    role = (target_role or "").strip().lower()
    tried_roles = [role] if role else []
    if role not in ("protection", "card_advantage", "removal", "wipe", "board_wipe", "wipes"):
        tried_roles.append("card_advantage")
        tried_roles.append("protection")
        tried_roles.append("removal")

    for r in tried_roles or ["card_advantage"]:
        candidates = _candidate_pool_for_role(builder, r)
        for nm, row in candidates:
            if nm in forbidden:
                continue
            # Enforce owned-only and color identity legality via builder.add_card (it will silently skip if illegal)
            before = set(getattr(builder, "card_library", {}).keys())
            builder.add_card(
                nm,
                card_type=str(row.get("type", row.get("type_line", "")) or ""),
                mana_cost=str(row.get("mana_cost", row.get("manaCost", "")) or ""),
                role=target_role or ("card_advantage" if r == "card_advantage" else ("protection" if r == "protection" else ("removal" if r == "removal" else "theme_spell"))),
                added_by="enforcement"
            )
            after = set(getattr(builder, "card_library", {}).keys())
            added = list(after - before)
            if added:
                return added[0]
    return None


def enforce_bracket_compliance(builder, mode: str = "prompt") -> Dict:
    """Trim over-limit bracket categories and add role-consistent replacements.

    mode: 'prompt' for interactive CLI (respects builder.headless); 'auto' for non-interactive.
    Returns the final compliance report after enforcement (or the original if no changes).
    """
    # Compute initial report
    bracket_key = str(getattr(builder, 'bracket_name', '') or getattr(builder, 'bracket_level', 'core')).lower()
    commander = getattr(builder, 'commander_name', None)
    report = evaluate_deck(getattr(builder, 'card_library', {}), commander_name=commander, bracket=bracket_key)
    if report.get("overall") != "FAIL":
        return report

    # Prepare prohibited set (avoid adding these during replacement)
    forbidden_lists = list(POLICY_FILES.values())
    prohibited: Set[str] = _load_list_cards(forbidden_lists)

    # Determine offenders per category
    cats = report.get("categories", {}) or {}
    to_remove: List[str] = []
    # Build a helper to rank offenders: keep better (lower edhrecRank) ones
    df = getattr(builder, "_combined_cards_df", None)
    def _score(name: str) -> Tuple[int, float, str]:
        try:
            if df is not None and not getattr(df, 'empty', True) and 'name' in df.columns:
                r = df[df['name'].astype(str) == str(name)]
                if not r.empty:
                    rank = int(r.iloc[0].get('edhrecRank') or 10**9)
                    mv = float(r.iloc[0].get('manaValue') or r.iloc[0].get('cmc') or 0.0)
                    return (rank, mv, str(name))
        except Exception:
            pass
        return (10**9, 99.0, str(name))

    # Interactive helper
    interactive = (mode == 'prompt' and not bool(getattr(builder, 'headless', False)))

    for key, cat in cats.items():
        if key not in ("game_changers", "extra_turns", "mass_land_denial", "tutors_nonland"):
            continue
        lim = cat.get("limit")
        cnt = int(cat.get("count", 0) or 0)
        if lim is None or cnt <= int(lim):
            continue
        flagged = [n for n in (cat.get("flagged") or []) if isinstance(n, str)]
        # Only consider flagged names that are actually in the library now
        lib = getattr(builder, 'card_library', {})
        present = [n for n in flagged if n in lib]
        if not present:
            continue
        # Determine how many need trimming
        over = cnt - int(lim)
        # Sort by ascending desirability to keep: worst ranks first for removal
        present_sorted = sorted(present, key=_score, reverse=True)  # worst first
        if interactive:
            # Present choices to keep
            try:
                out = getattr(builder, 'output_func', print)
                inp = getattr(builder, 'input_func', input)
                out(f"\nEnforcement: {key.replace('_',' ').title()} is over the limit ({cnt} > {lim}).")
                out("Select the indices to KEEP (comma-separated). Press Enter to auto-keep the best:")
                for i, nm in enumerate(sorted(present, key=_score)):
                    sc = _score(nm)
                    out(f"  [{i}] {nm}  (edhrecRank={sc[0] if sc[0] < 10**9 else 'n/a'})")
                raw = str(inp("Keep which? ").strip())
                keep_idx: Set[int] = set()
                if raw:
                    for tok in raw.split(','):
                        tok = tok.strip()
                        if tok.isdigit():
                            keep_idx.add(int(tok))
                # Compute the names to keep up to the allowed count
                allowed = max(0, int(lim))
                keep_list: List[str] = []
                for i, nm in enumerate(sorted(present, key=_score)):
                    if len(keep_list) >= allowed:
                        break
                    if i in keep_idx:
                        keep_list.append(nm)
                # If still short, fill with best-ranked remaining
                for nm in sorted(present, key=_score):
                    if len(keep_list) >= allowed:
                        break
                    if nm not in keep_list:
                        keep_list.append(nm)
                # Remove the others (beyond keep_list)
                for nm in present:
                    if nm not in keep_list and over > 0:
                        to_remove.append(nm)
                        over -= 1
                if over > 0:
                    # If user kept too many, trim worst extras
                    for nm in present_sorted:
                        if over <= 0:
                            break
                        if nm in keep_list:
                            to_remove.append(nm)
                            over -= 1
            except Exception:
                # Fallback to auto behavior
                to_remove.extend(present_sorted[:over])
        else:
            # Auto: remove the worst-ranked extras first
            to_remove.extend(present_sorted[:over])

    # Execute removals and replacements
    actually_removed: List[str] = []
    actually_added: List[str] = []
    swaps: List[dict] = []
    # Load preferred replacements mapping (lowercased keys/values)
    pref_map_lower: Dict[str, str] = {}
    try:
        raw = getattr(builder, 'preferred_replacements', {}) or {}
        for k, v in raw.items():
            ks = str(k).strip().lower()
            vs = str(v).strip().lower()
            if ks and vs:
                pref_map_lower[ks] = vs
    except Exception:
        pref_map_lower = {}
    for nm in to_remove:
        entry = getattr(builder, 'card_library', {}).get(nm)
        if not entry:
            continue
        role = entry.get('Role') or None
        if _remove_card(builder, nm):
            actually_removed.append(nm)
            # First, honor any explicit user-chosen replacement
            added = None
            try:
                want = pref_map_lower.get(str(nm).strip().lower())
                if want:
                    # Avoid adding prohibited or duplicates
                    lib_l = {str(x).strip().lower() for x in getattr(builder, 'card_library', {}).keys()}
                    if (want not in prohibited) and (want not in lib_l):
                        df = getattr(builder, '_combined_cards_df', None)
                        target_name = None
                        card_type = ''
                        mana_cost = ''
                        if df is not None and not getattr(df, 'empty', True) and 'name' in df.columns:
                            r = df[df['name'].astype(str).str.lower() == want]
                            if not r.empty:
                                target_name = str(r.iloc[0]['name'])
                                card_type = str(r.iloc[0].get('type', r.iloc[0].get('type_line', '')) or '')
                                mana_cost = str(r.iloc[0].get('mana_cost', r.iloc[0].get('manaCost', '')) or '')
                        # If we couldn't resolve row, still try to add by name
                        target = target_name or want
                        before = set(getattr(builder, 'card_library', {}).keys())
                        builder.add_card(target, card_type=card_type, mana_cost=mana_cost, role=role, added_by='enforcement')
                        after = set(getattr(builder, 'card_library', {}).keys())
                        delta = list(after - before)
                        if delta:
                            added = delta[0]
            except Exception:
                added = None
            # If no explicit or failed, try to add an automatic role-consistent replacement
            if not added:
                added = _try_add_replacement(builder, role, prohibited)
            if added:
                actually_added.append(added)
                swaps.append({"removed": nm, "added": added, "role": role})
            else:
                swaps.append({"removed": nm, "added": None, "role": role})

    # Recompute report after initial category-based changes
    final_report = evaluate_deck(getattr(builder, 'card_library', {}), commander_name=commander, bracket=bracket_key)

    # --- Second pass: break cheap/early two-card combos if still over the limit ---
    try:
        cats2 = final_report.get("categories", {}) or {}
        two = cats2.get("two_card_combos") or {}
        curr = int(two.get("count", 0) or 0)
        lim = two.get("limit")
        if lim is not None and curr > int(lim):
            # Build present cheap/early pairs from the report
            pairs: List[Tuple[str, str]] = []
            for p in (final_report.get("combos") or []):
                try:
                    if not p.get("cheap_early"):
                        continue
                    a = str(p.get("a") or "").strip()
                    b = str(p.get("b") or "").strip()
                    if not a or not b:
                        continue
                    # Only consider if both still present
                    lib = getattr(builder, 'card_library', {}) or {}
                    if a in lib and b in lib:
                        pairs.append((a, b))
                except Exception:
                    continue

            # Helper to recompute count and frequencies from current pairs
            def _freq(ps: List[Tuple[str, str]]) -> Dict[str, int]:
                mp: Dict[str, int] = {}
                for (a, b) in ps:
                    mp[a] = mp.get(a, 0) + 1
                    mp[b] = mp.get(b, 0) + 1
                return mp

            current_pairs = list(pairs)
            blocked: Set[str] = set()
            # Keep removing until combos count <= limit or no progress possible
            while len(current_pairs) > int(lim):
                freq = _freq(current_pairs)
                if not freq:
                    break
                # Rank candidates: break the most combos first; break ties by worst desirability
                cand_names = list(freq.keys())
                cand_names.sort(key=lambda nm: (-int(freq.get(nm, 0)), _score(nm)), reverse=False)
                removed_any = False
                for nm in cand_names:
                    if nm in blocked:
                        continue
                    entry = getattr(builder, 'card_library', {}).get(nm)
                    role = entry.get('Role') if isinstance(entry, dict) else None
                    # Try to remove; protects commander/locks inside helper
                    if _remove_card(builder, nm):
                        actually_removed.append(nm)
                        # Preferred replacement first
                        added = None
                        try:
                            want = pref_map_lower.get(str(nm).strip().lower())
                            if want:
                                lib_l = {str(x).strip().lower() for x in getattr(builder, 'card_library', {}).keys()}
                                if (want not in prohibited) and (want not in lib_l):
                                    df2 = getattr(builder, '_combined_cards_df', None)
                                    target_name = None
                                    card_type = ''
                                    mana_cost = ''
                                    if df2 is not None and not getattr(df2, 'empty', True) and 'name' in df2.columns:
                                        r = df2[df2['name'].astype(str).str.lower() == want]
                                        if not r.empty:
                                            target_name = str(r.iloc[0]['name'])
                                            card_type = str(r.iloc[0].get('type', r.iloc[0].get('type_line', '')) or '')
                                            mana_cost = str(r.iloc[0].get('mana_cost', r.iloc[0].get('manaCost', '')) or '')
                                    target = target_name or want
                                    before = set(getattr(builder, 'card_library', {}).keys())
                                    builder.add_card(target, card_type=card_type, mana_cost=mana_cost, role=role, added_by='enforcement')
                                    after = set(getattr(builder, 'card_library', {}).keys())
                                    delta = list(after - before)
                                    if delta:
                                        added = delta[0]
                        except Exception:
                            added = None
                        if not added:
                            added = _try_add_replacement(builder, role, prohibited)
                        if added:
                            actually_added.append(added)
                            swaps.append({"removed": nm, "added": added, "role": role})
                        else:
                            swaps.append({"removed": nm, "added": None, "role": role})
                        # Update pairs by removing any that contain nm
                        current_pairs = [(a, b) for (a, b) in current_pairs if (a != nm and b != nm)]
                        removed_any = True
                        break
                    else:
                        blocked.add(nm)
                if not removed_any:
                    # Cannot break further due to locks/commander; stop to avoid infinite loop
                    break

            # Recompute report after combo-breaking
            final_report = evaluate_deck(getattr(builder, 'card_library', {}), commander_name=commander, bracket=bracket_key)
    except Exception:
        # If combo-breaking fails for any reason, fall back to the current report
        pass
    # Attach enforcement actions for downstream consumers
    try:
        final_report.setdefault('enforcement', {})
        final_report['enforcement']['removed'] = list(actually_removed)
        final_report['enforcement']['added'] = list(actually_added)
        final_report['enforcement']['swaps'] = list(swaps)
    except Exception:
        pass
    # Log concise summary if possible
    try:
        out = getattr(builder, 'output_func', print)
        if actually_removed or actually_added:
            out("\nEnforcement applied:")
            if actually_removed:
                out("Removed:")
                for x in actually_removed:
                    out(f"  - {x}")
            if actually_added:
                out("Added:")
                for x in actually_added:
                    out(f"  + {x}")
        out(f"Compliance after enforcement: {final_report.get('overall')}")
    except Exception:
        pass
    return final_report
