from __future__ import annotations

from typing import Dict, Any, List, Tuple
import copy
from deck_builder.builder import DeckBuilder
from deck_builder.phases.phase0_core import BRACKET_DEFINITIONS
from deck_builder import builder_constants as bc
import os
import time
import json
from datetime import datetime as _dt
import re
import unicodedata
from glob import glob


def _global_prune_disallowed_pool(b: DeckBuilder) -> None:
    """Hard-prune disallowed categories from the working pool based on bracket limits.

    This is a defensive, pool-level filter to ensure headless/JSON builds also
    honor hard bans (e.g., no Game Changers in brackets 1–2). It complements
    per-stage pre-filters and is safe to apply immediately after dataframes are
    set up.
    """
    try:
        limits = getattr(b, 'bracket_limits', {}) or {}

        def _prune_df(df):
            try:
                if df is None or getattr(df, 'empty', True):
                    return df
                cols = getattr(df, 'columns', [])
                name_col = 'name' if 'name' in cols else ('Card Name' if 'Card Name' in cols else None)
                if name_col is None:
                    return df
                work = df
                # 1) Game Changers: filter by authoritative name list regardless of tag presence
                try:
                    lim_gc = limits.get('game_changers')
                    if lim_gc is not None and int(lim_gc) == 0 and getattr(bc, 'GAME_CHANGERS', None):
                        gc_lower = {str(n).strip().lower() for n in getattr(bc, 'GAME_CHANGERS', [])}
                        work = work[~work[name_col].astype(str).str.lower().isin(gc_lower)]
                except Exception:
                    pass
                # 2) Additional categories rely on tags if present; skip if tag column missing
                try:
                    if 'themeTags' in getattr(work, 'columns', []):
                        # Normalize a lowercase tag list column
                        from deck_builder import builder_utils as _bu
                        if '_ltags' not in work.columns:
                            work = work.copy()
                            work['_ltags'] = work['themeTags'].apply(_bu.normalize_tag_cell)

                        def _has_any(lst, needles):
                            try:
                                return any(any(nd in t for nd in needles) for t in (lst or []))
                            except Exception:
                                return False

                        # Build disallow map
                        disallow = {
                            'extra_turns': (limits.get('extra_turns') is not None and int(limits.get('extra_turns')) == 0),
                            'mass_land_denial': (limits.get('mass_land_denial') is not None and int(limits.get('mass_land_denial')) == 0),
                            'tutors_nonland': (limits.get('tutors_nonland') is not None and int(limits.get('tutors_nonland')) == 0),
                        }
                        syn = {
                            'extra_turns': {'bracket:extraturn', 'extra turn', 'extra turns', 'extraturn'},
                            'mass_land_denial': {'bracket:masslanddenial', 'mass land denial', 'mld', 'masslanddenial'},
                            'tutors_nonland': {'bracket:tutornonland', 'tutor', 'tutors', 'nonland tutor', 'non-land tutor'},
                        }
                        if any(disallow.values()):
                            mask_keep = [True] * len(work)
                            tags_series = work['_ltags']
                            for key, dis in disallow.items():
                                if not dis:
                                    continue
                                needles = syn.get(key, set())
                                drop_idx = tags_series.apply(lambda lst, nd=needles: _has_any(lst, nd))
                                mask_keep = [mk and (not di) for mk, di in zip(mask_keep, drop_idx.tolist())]
                            try:
                                import pandas as _pd  # type: ignore
                                mask_keep = _pd.Series(mask_keep, index=work.index)
                            except Exception:
                                pass
                            work = work[mask_keep]
                except Exception:
                    pass

                return work
            except Exception:
                return df

        # Apply to both pools used by phases
        try:
            b._combined_cards_df = _prune_df(getattr(b, '_combined_cards_df', None))
        except Exception:
            pass
        try:
            b._full_cards_df = _prune_df(getattr(b, '_full_cards_df', None))
        except Exception:
            pass
    except Exception:
        return


def _attach_enforcement_plan(b: DeckBuilder, comp: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """When compliance FAILs, attach a non-destructive enforcement plan to show swaps in UI.

    Builds a list of candidate removals per over-limit category (no mutations), then
    attaches comp['enforcement'] with 'swaps' entries of the form
    {removed: name, added: None, role: role} and summaries of removed names.
    """
    try:
        if not isinstance(comp, dict):
            return comp
        if str(comp.get('overall', 'PASS')).upper() != 'FAIL':
            return comp
        cats = comp.get('categories') or {}
        lib = getattr(b, 'card_library', {}) or {}
        # Case-insensitive lookup for library names
        lib_lower_to_orig = {str(k).strip().lower(): k for k in lib.keys()}
        # Scoring helper mirroring enforcement: worse (higher rank) trimmed first
        df = getattr(b, '_combined_cards_df', None)
        def _score(name: str) -> tuple[int, float, str]:
            try:
                if df is not None and not getattr(df, 'empty', True) and 'name' in getattr(df, 'columns', []):
                    r = df[df['name'].astype(str) == str(name)]
                    if not r.empty:
                        rank = int(r.iloc[0].get('edhrecRank') or 10**9)
                        mv = float(r.iloc[0].get('manaValue') or r.iloc[0].get('cmc') or 0.0)
                        return (rank, mv, str(name))
            except Exception:
                pass
            return (10**9, 99.0, str(name))
        to_remove: list[str] = []
        for key in ('game_changers', 'extra_turns', 'mass_land_denial', 'tutors_nonland'):
            cat = cats.get(key) or {}
            lim = cat.get('limit')
            cnt = int(cat.get('count', 0) or 0)
            if lim is None or cnt <= int(lim):
                continue
            flagged = [n for n in (cat.get('flagged') or []) if isinstance(n, str)]
            # Map flagged names to the canonical in-deck key (case-insensitive)
            present_mapped: list[str] = []
            for n in flagged:
                n_key = str(n).strip()
                if n_key in lib:
                    present_mapped.append(n_key)
                    continue
                lk = n_key.lower()
                if lk in lib_lower_to_orig:
                    present_mapped.append(lib_lower_to_orig[lk])
            present = present_mapped
            if not present:
                continue
            over = cnt - int(lim)
            present_sorted = sorted(present, key=_score, reverse=True)
            to_remove.extend(present_sorted[:over])
        if not to_remove:
            return comp
        swaps = []
        for nm in to_remove:
            entry = lib.get(nm) or {}
            swaps.append({"removed": nm, "added": None, "role": entry.get('Role')})
        enf = comp.setdefault('enforcement', {})
        enf['removed'] = list(dict.fromkeys(to_remove))
        enf['added'] = []
        enf['swaps'] = swaps
        return comp
    except Exception:
        return comp


def commander_names() -> List[str]:
    tmp = DeckBuilder()
    df = tmp.load_commander_data()
    return df["name"].astype(str).tolist()


def commander_candidates(query: str, limit: int = 10) -> List[Tuple[str, int, List[str]]]:
    def _strip_accents(s: str) -> str:
        try:
            return ''.join(ch for ch in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(ch))
        except Exception:
            return str(s)

    def _simplify(s: str) -> str:
        try:
            s2 = _strip_accents(str(s))
            s2 = s2.lower()
            # remove punctuation/symbols, keep letters/numbers/spaces
            s2 = re.sub(r"[^a-z0-9\s]", " ", s2)
            s2 = re.sub(r"\s+", " ", s2).strip()
            return s2
        except Exception:
            return str(s).lower().strip()
    # Normalize query similar to CLI to reduce case sensitivity surprises
    tmp = DeckBuilder()
    try:
        if hasattr(tmp, '_normalize_commander_query'):
            query = tmp._normalize_commander_query(query)  # type: ignore[attr-defined]
        else:
            # Light fallback: basic title case
            query = ' '.join([w[:1].upper() + w[1:].lower() if w else w for w in str(query).split(' ')])
    except Exception:
        pass
    df = tmp.load_commander_data()
    # Filter to plausible commanders: Legendary Creature, or text explicitly allows being a commander.
    try:
        cols = set(df.columns.astype(str))
        has_type = ('type' in cols) or ('type_line' in cols)
        has_text = ('text' in cols) or ('oracleText' in cols)
        if has_type or has_text:
            def _is_commander_row(_r) -> bool:
                try:
                    tline = str(_r.get('type', _r.get('type_line', '')) or '').lower()
                    textv = str(_r.get('text', _r.get('oracleText', '')) or '').lower()
                    if 'legendary' in tline and 'creature' in tline:
                        return True
                    if 'legendary' in tline and 'planeswalker' in tline and 'can be your commander' in textv:
                        return True
                    if 'can be your commander' in textv:
                        return True
                except Exception:
                    return False
                return False
            df_comm = df[df.apply(_is_commander_row, axis=1)]
            if not df_comm.empty:
                df = df_comm
        # else: keep df as-is when columns not present
    except Exception:
        pass
    names = df["name"].astype(str).tolist()
    # Reuse existing scoring helpers through the DeckBuilder API
    scored_raw = tmp._gather_candidates(query, names)
    # Consider a wider pool for re-ranking so exact substrings bubble up
    pool = scored_raw[: max(limit * 5, 50)]
    # Force-include any names that contain the raw query as a substring (case-insensitive)
    # to avoid missing obvious matches like 'Inti, Seneschal of the Sun' for 'inti'.
    try:
        q_raw = (query or "").strip().lower()
        q_norm = _simplify(query)
        if q_raw:
            have = {n for (n, _s) in pool}
            # Map original scores for reuse
            base_scores = {n: int(s) for (n, s) in scored_raw}
            for n in names:
                nl = str(n).lower()
                nn = _simplify(n)
                if (q_raw in nl or (q_norm and q_norm in nn)) and n not in have:
                    # Assign a reasonable base score if not present; favor prefixes
                    approx_base = base_scores.get(n)
                    if approx_base is None:
                        starts = nl.startswith(q_raw) or (q_norm and nn.startswith(q_norm))
                        approx_base = 90 if starts else 80
                    approx = approx_base
                    pool.append((n, approx))
    except Exception:
        pass
    # Attach color identity for each candidate
    try:
        df = tmp.load_commander_data()
    except Exception:
        df = None
    q = (query or "").strip().lower()
    qn = _simplify(query)
    tokens = [t for t in re.split(r"[\s,]+", q) if t]
    tokens_norm = [t for t in (qn.split(" ") if qn else []) if t]
    def _color_list_for(name: str) -> List[str]:
        colors: List[str] = []
        try:
            if df is not None:
                row = df[df["name"].astype(str) == str(name)]
                if not row.empty:
                    ci = row.iloc[0].get("colorIdentity")
                    if isinstance(ci, list):
                        colors = [str(c).upper() for c in ci if str(c).strip()]
                    elif isinstance(ci, str) and ci.strip():
                        parts = [p.strip().upper() for p in ci.replace('[', '').replace(']', '').replace("'", '').split(',') if p.strip()]
                        colors = parts if parts else list(ci)
            if not colors:
                colors = ["C"]
        except Exception:
            colors = ["C"]
        return colors

    rescored: List[Tuple[str, int, List[str], int, int, int]] = []  # (name, orig_score, colors, rank_score, pos, exact_first_word)
    for name, score in pool:
        colors: List[str] = []
        colors = _color_list_for(name)
        nl = str(name).lower()
        nnorm = _simplify(name)
        bonus = 0
        pos = nl.find(q) if q else -1
        pos_norm = nnorm.find(qn) if qn else -1
        pos_final = pos if pos >= 0 else pos_norm
        # Extract first word (letters only) for exact first-word preference
        try:
            m_first = re.match(r"^[a-z0-9']+", nl)
            first_word = m_first.group(0) if m_first else ""
        except Exception:
            first_word = nl.split(" ", 1)[0] if nl else ""
        # Normalized first word
        try:
            m_first_n = re.match(r"^[a-z0-9']+", nnorm)
            first_word_n = m_first_n.group(0) if m_first_n else ""
        except Exception:
            first_word_n = nnorm.split(" ", 1)[0] if nnorm else ""
        exact_first = 1 if ((q and first_word == q) or (qn and first_word_n == qn)) else 0
        # Base heuristics
        if q or qn:
            if q and nl == q:
                bonus += 100
            elif qn and nnorm == qn:
                bonus += 85
            if (q and nl.startswith(q)) or (qn and nnorm.startswith(qn)):
                bonus += 60
            if q and re.search(r"\b" + re.escape(q), nl):
                bonus += 40
            if (q and q in nl) or (qn and qn in nnorm):
                bonus += 30
            # Strongly prefer exact first-word equality over general prefix
            if exact_first:
                bonus += 140
        # Multi-token bonuses
        if tokens_norm or tokens:
            present = 0
            all_present = 0
            if tokens_norm:
                present = sum(1 for t in tokens_norm if t in nnorm)
                all_present = 1 if all(t in nnorm for t in tokens_norm) else 0
            elif tokens:
                present = sum(1 for t in tokens if t in nl)
                all_present = 1 if all(t in nl for t in tokens) else 0
            bonus += present * 10 + all_present * 40
            # Extra if first token is a prefix
            t0 = (tokens_norm[0] if tokens_norm else (tokens[0] if tokens else None))
            if t0 and (nnorm.startswith(t0) or nl.startswith(t0)):
                bonus += 15
        # Favor shorter names slightly and earlier positions
        bonus += max(0, 20 - len(nl))
        if pos_final >= 0:
            bonus += max(0, 20 - pos_final)
        rank_score = int(score) + bonus
        rescored.append((name, int(score), colors, rank_score, pos_final if pos_final >= 0 else 10**6, exact_first))

    # Sort: exact first-word matches first, then by rank score desc, then earliest position, then original score desc, then name asc
    rescored.sort(key=lambda x: (-x[5], -x[3], x[4], -x[1], x[0]))
    top = rescored[:limit]
    return [(name, orig_score, colors) for (name, orig_score, colors, _r, _p, _e) in top]


def commander_inspect(name: str) -> Dict[str, Any]:
    tmp = DeckBuilder()
    df = tmp.load_commander_data()
    row = df[df["name"] == name]
    if row.empty:
        return {"ok": False, "error": "Commander not found"}
    pretty = tmp._format_commander_pretty(row.iloc[0])
    return {"ok": True, "pretty": pretty}


def commander_select(name: str) -> Dict[str, Any]:
    tmp = DeckBuilder()
    df = tmp.load_commander_data()
    # Try exact match, then normalized match
    row = df[df["name"] == name]
    if row.empty:
        try:
            if hasattr(tmp, '_normalize_commander_query'):
                name2 = tmp._normalize_commander_query(name)  # type: ignore[attr-defined]
            else:
                name2 = ' '.join([w[:1].upper() + w[1:].lower() if w else w for w in str(name).split(' ')])
            row = df[df["name"] == name2]
        except Exception:
            row = df[df["name"] == name]
    if row.empty:
        return {"ok": False, "error": "Commander not found"}
    tmp._apply_commander_selection(row.iloc[0])
    # Derive tags and a quick preview of bracket choices
    tags = list(dict.fromkeys(tmp.commander_tags)) if hasattr(tmp, "commander_tags") else []
    return {
        "ok": True,
        "name": name,
        "tags": tags,
    }


def tags_for_commander(name: str) -> List[str]:
    tmp = DeckBuilder()
    df = tmp.load_commander_data()
    row = df[df["name"] == name]
    if row.empty:
        return []
    raw = row.iloc[0].get("themeTags", [])
    if isinstance(raw, list):
        return list(dict.fromkeys([str(t).strip() for t in raw if str(t).strip()]))
    if isinstance(raw, str) and raw.strip():
        parts = [p.strip().strip("'\"") for p in raw.split(',')]
        return [p for p in parts if p]
    return []


def _recommended_scored(name: str, max_items: int = 5) -> List[Tuple[str, int, List[str]]]:
    """Internal: return list of (tag, score, reasons[]) for top recommendations."""
    available_list = list(tags_for_commander(name) or [])
    if not available_list:
        return []
    # Case-insensitive map: normalized -> original display tag
    def _norm(s: str) -> str:
        try:
            return re.sub(r"\s+", " ", str(s).strip().lower())
        except Exception:
            return str(s).strip().lower()
    norm_map: Dict[str, str] = { _norm(t): t for t in available_list }
    available_norm = set(norm_map.keys())
    available_norm_list = list(available_norm)

    def _best_match_norm(tn: str) -> str | None:
        """Return the best available normalized tag matching tn by exact or substring."""
        if tn in available_norm:
            return tn
        try:
            # prefer contains matches with minimal length difference
            candidates = []
            for an in available_norm_list:
                if tn in an or an in tn:
                    candidates.append((abs(len(an) - len(tn)), an))
            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1]))
                return candidates[0][1]
        except Exception:
            return None
        return None
    try:
        tmp = DeckBuilder()
        df = tmp.load_commander_data()
    except Exception:
        df = None
    # Gather commander text and colors
    text = ""
    colors: List[str] = []
    if df is not None:
        try:
            row = df[df["name"].astype(str) == str(name)]
            if not row.empty:
                r0 = row.iloc[0]
                text = str(r0.get("text", r0.get("oracleText", "")) or "").lower()
                ci = r0.get("colorIdentity")
                if isinstance(ci, list):
                    colors = [str(c).upper() for c in ci if str(c).strip()]
                elif isinstance(ci, str) and ci.strip():
                    parts = [p.strip().upper() for p in ci.replace('[', '').replace(']', '').replace("'", '').split(',') if p.strip()]
                    colors = parts if parts else list(ci)
        except Exception:
            pass
    if not colors:
        colors = ["C"]

    score: Dict[str, int] = {t: 0 for t in available_list}
    reasons: Dict[str, List[str]] = {t: [] for t in available_list}
    order_index = {t: i for i, t in enumerate(list(available_list))}

    # Anchor weight; omit reason to keep tooltip focused
    for t in list(available_list):
        score[t] += 30

    # Keyword patterns -> tags with labeled reasons
    patterns: List[Tuple[str, List[str], List[str], int]] = [
        ("Oracle mentions treasure/tokens", [r"\btreasure\b"], ["treasure", "tokens"], 8),
        ("Oracle mentions tokens", [r"\btoken\b", r"create .* token"], ["tokens"], 10),
        ("Oracle mentions sacrifice/death", [r"\bsacrifice\b", r"whenever .* dies"], ["sacrifice", "aristocrats"], 9),
        ("Oracle mentions graveyard/recursion", [r"graveyard", r"from your graveyard", r"return .* from graveyard"], ["graveyard"], 9),
        ("Oracle mentions lifegain/lifelink", [r"\bgain life\b", r"lifelink"], ["lifegain"], 9),
        ("Oracle mentions instants/sorceries", [r"instant or sorcery", r"whenever you cast an instant", r"prowess"], ["spellslinger", "spells"], 9),
        ("Oracle mentions artifacts/equipment", [r"\bartifact\b", r"equipment"], ["artifacts", "equipment"], 8),
        ("Oracle mentions enchantments/auras", [r"\benchant\b", r"aura"], ["enchantments", "auras"], 7),
        ("Oracle mentions +1/+1 counters", [r"\+1/\+1 counter", r"put .* counters?"], ["+1/+1 counters", "counters"], 8),
        ("Oracle suggests blink/flicker", [r"exile .* return .* battlefield", r"blink"], ["blink"], 7),
        ("Oracle mentions vehicles/crew", [r"vehicle", r"crew"], ["vehicles"], 6),
    ("Oracle references legendary/legends", [r"\blegendary\b", r"legend(ary)?\b"], ["legends matter", "legends", "legendary matters"], 8),
    ("Oracle references historic", [r"\bhistoric(s)?\b"], ["historics matter", "historic"], 7),
    ("Oracle suggests aggressive attacks/haste", [r"\bhaste\b", r"attacks? each combat", r"whenever .* attacks"], ["aggro"], 6),
    ("Oracle references direct damage", [r"deal \d+ damage", r"damage to any target", r"noncombat damage"], ["burn"], 6),
    ]
    for label, pats, tags_out, w in patterns:
        try:
            if any(re.search(p, text) for p in pats):
                for tg in tags_out:
                    tn = _norm(tg)
                    bm = _best_match_norm(tn)
                    if bm is None:
                        continue
                    orig = norm_map[bm]
                    score[orig] = score.get(orig, 0) + w
                    if len(reasons[orig]) < 3 and label not in reasons[orig]:
                        reasons[orig].append(label)
        except Exception:
            continue

    # Color identity mapped defaults
    ci_key_sorted = ''.join(sorted(colors))
    color_map: Dict[str, List[Tuple[str, int]]] = {
        'GW': [("tokens", 5), ("enchantments", 4), ("+1/+1 counters", 4)],
        'WU': [("blink", 5), ("control", 4)],
        'UB': [("graveyard", 5), ("control", 4)],
        'BR': [("sacrifice", 5), ("aristocrats", 4)],
        'RG': [("landfall", 4), ("tokens", 3)],
        'UR': [("spells", 5), ("artifacts", 4)],
        'WB': [("lifegain", 5), ("aristocrats", 4)],
        'BG': [("graveyard", 5), ("counters", 4)],
        'WR': [("equipment", 5), ("tokens", 4)],
        'UG': [("+1/+1 counters", 5), ("ramp", 4)],
        'WUB': [("blink", 4), ("control", 4)],
        'WBR': [("lifegain", 4), ("aristocrats", 4)],
        'UBR': [("spells", 4), ("artifacts", 3)],
        'BRG': [("sacrifice", 4), ("graveyard", 4)],
        'RGW': [("tokens", 4), ("counters", 3)],
        'GWU': [("blink", 4), ("enchantments", 3)],
        'WUBR': [("control", 4), ("spells", 3)],
        'UBRG': [("graveyard", 4), ("spells", 3)],
        'BRGW': [("tokens", 3), ("sacrifice", 3)],
        'RGWU': [("counters", 3), ("tokens", 3)],
        'WUBRG': [("artifacts", 3), ("tokens", 3)],
    }
    # Build lookup keyed by sorted color string to be order-agnostic
    try:
        color_map_lookup: Dict[str, List[Tuple[str, int]]] = { ''.join(sorted(list(k))): v for k, v in color_map.items() }
    except Exception:
        color_map_lookup = color_map
    if ci_key_sorted in color_map_lookup:
        for tg, w in color_map_lookup[ci_key_sorted]:
            tn = _norm(tg)
            bm = _best_match_norm(tn)
            if bm is None:
                continue
            orig = norm_map[bm]
            score[orig] = score.get(orig, 0) + w
            cr = f"Fits your colors ({ci_key_sorted})"
            if len(reasons[orig]) < 3 and cr not in reasons[orig]:
                reasons[orig].append(cr)

    # Past builds history
    try:
        for path in glob(os.path.join('deck_files', '*.summary.json')):
            try:
                st = os.stat(path)
                age_days = max(0, (time.time() - st.st_mtime) / 86400.0)
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f) or {}
                meta = data.get('meta') or {}
                if str(meta.get('commander', '')).strip() != str(name).strip():
                    continue
                tags_list = meta.get('tags') or []
                for tg in tags_list:
                    tn = _norm(str(tg))
                    if tn in available_norm:
                        orig = norm_map[tn]
                        inc = 2
                        recent = False
                        if age_days <= 30:
                            inc += 2
                            recent = True
                        elif age_days <= 90:
                            inc += 1
                        score[orig] = score.get(orig, 0) + inc
                        lbl = "Popular in your past builds" + (" (recent)" if recent else "")
                        if len(reasons[orig]) < 3 and lbl not in reasons[orig]:
                            reasons[orig].append(lbl)
            except Exception:
                continue
    except Exception:
        pass

    items = [(k, score.get(k, 0), reasons.get(k, [])) for k in available_list]
    items.sort(key=lambda x: (-x[1], order_index.get(x[0], 10**6), x[0]))
    # Trim reasons to at most two concise bullets and format as needed later
    top = items[:max_items]
    return top


def recommended_tags_for_commander(name: str, max_items: int = 5) -> List[str]:
    """Suggest up to `max_items` theme tags for a commander (tags only)."""
    try:
        return [tag for (tag, _s, _r) in _recommended_scored(name, max_items=max_items)]
    except Exception:
        return []


def recommended_tag_reasons_for_commander(name: str, max_items: int = 5) -> Dict[str, str]:
    """Return a mapping of tag -> short reason for why it was recommended."""
    try:
        res: Dict[str, str] = {}
        for tag, _score, rs in _recommended_scored(name, max_items=max_items):
            # Build a concise reason string
            if not rs:
                res[tag] = "From this commander's theme list"
            else:
                # Take up to two distinct reasons
                uniq: List[str] = []
                for r in rs:
                    if r and r not in uniq:
                        uniq.append(r)
                    if len(uniq) >= 2:
                        break
                res[tag] = "; ".join(uniq)
        return res
    except Exception:
        return {}


def bracket_options() -> List[Dict[str, Any]]:
    return [{"level": b.level, "name": b.name, "desc": b.short_desc} for b in BRACKET_DEFINITIONS]


def ideal_defaults() -> Dict[str, Any]:
    return {
        "ramp": getattr(bc, 'DEFAULT_RAMP_COUNT', 10),
        "lands": getattr(bc, 'DEFAULT_LAND_COUNT', 35),
        "basic_lands": getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20),
        "fetch_lands": getattr(bc, 'FETCH_LAND_DEFAULT_COUNT', 3),
        "creatures": getattr(bc, 'DEFAULT_CREATURE_COUNT', 28),
        "removal": getattr(bc, 'DEFAULT_REMOVAL_COUNT', 10),
        "wipes": getattr(bc, 'DEFAULT_WIPES_COUNT', 2),
        "card_advantage": getattr(bc, 'DEFAULT_CARD_ADVANTAGE_COUNT', 8),
        "protection": getattr(bc, 'DEFAULT_PROTECTION_COUNT', 4),
    }


def ideal_labels() -> Dict[str, str]:
    return {
        'ramp': 'Ramp',
        'lands': 'Total Lands',
        'basic_lands': 'Basic Lands (Min)',
        'fetch_lands': 'Fetch Lands',
        'creatures': 'Creatures',
        'removal': 'Spot Removal',
        'wipes': 'Board Wipes',
        'card_advantage': 'Card Advantage',
        'protection': 'Protection',
    }


def _is_truthy_env(name: str, default: str = '1') -> bool:
    try:
        val = os.getenv(name, default)
        return str(val).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        return default in {"1", "true", "yes", "on"}


def is_setup_ready() -> bool:
    """Fast readiness check: required files present and tagging completed.

    We consider the system ready if csv_files/cards.csv exists and the
    .tagging_complete.json flag exists. Freshness (mtime) is enforced only
    during auto-refresh inside _ensure_setup_ready, not here.
    """
    try:
        cards_path = os.path.join('csv_files', 'cards.csv')
        flag_path = os.path.join('csv_files', '.tagging_complete.json')
        return os.path.exists(cards_path) and os.path.exists(flag_path)
    except Exception:
        return False


def is_setup_stale() -> bool:
    """Return True if cards.csv exists but is older than the auto-refresh threshold.

    This does not imply not-ready; it is a hint for the UI to recommend a refresh.
    """
    try:
        # Refresh threshold (treat <=0 as "never stale")
        try:
            days = int(os.getenv('WEB_AUTO_REFRESH_DAYS', '7'))
        except Exception:
            days = 7
        if days <= 0:
            return False
        refresh_age_seconds = max(0, days) * 24 * 60 * 60

        # If setup is currently running, avoid prompting a refresh loop
        try:
            status_path = os.path.join('csv_files', '.setup_status.json')
            if os.path.exists(status_path):
                with open(status_path, 'r', encoding='utf-8') as f:
                    st = json.load(f) or {}
                if bool(st.get('running')):
                    return False
                # If we recently finished, honor finished_at (or updated) as a freshness signal
                ts_str = st.get('finished_at') or st.get('updated') or st.get('started_at')
                if isinstance(ts_str, str) and ts_str.strip():
                    try:
                        ts = _dt.fromisoformat(ts_str.strip())
                        if (time.time() - ts.timestamp()) <= refresh_age_seconds:
                            return False
                    except Exception:
                        pass
        except Exception:
            pass

        # If tagging completed recently, treat as fresh regardless of cards.csv mtime
        try:
            tag_flag = os.path.join('csv_files', '.tagging_complete.json')
            if os.path.exists(tag_flag):
                with open(tag_flag, 'r', encoding='utf-8') as f:
                    tf = json.load(f) or {}
                tstr = tf.get('tagged_at')
                if isinstance(tstr, str) and tstr.strip():
                    try:
                        tdt = _dt.fromisoformat(tstr.strip())
                        if (time.time() - tdt.timestamp()) <= refresh_age_seconds:
                            return False
                    except Exception:
                        pass
        except Exception:
            pass

        # Fallback: compare cards.csv mtime
        cards_path = os.path.join('csv_files', 'cards.csv')
        if not os.path.exists(cards_path):
            return False
        age_seconds = time.time() - os.path.getmtime(cards_path)
        return age_seconds > refresh_age_seconds
    except Exception:
        return False


def _ensure_setup_ready(out, force: bool = False) -> None:
    """Ensure card CSVs exist and tagging has completed; bootstrap if needed.

    Mirrors the CLI behavior used in build_deck_full: if csv_files/cards.csv is
    missing, too old, or the tagging flag is absent, run initial setup and tagging.
    """
    # Track whether a theme catalog export actually executed during this invocation
    theme_export_performed = False
    def _write_status(payload: dict) -> None:
        try:
            os.makedirs('csv_files', exist_ok=True)
            # Preserve started_at if present
            status_path = os.path.join('csv_files', '.setup_status.json')
            existing = {}
            try:
                if os.path.exists(status_path):
                    with open(status_path, 'r', encoding='utf-8') as _rf:
                        existing = json.load(_rf) or {}
            except Exception:
                existing = {}
            # Merge and keep started_at unless explicitly overridden
            merged = {**existing, **payload}
            if 'started_at' not in merged and existing.get('started_at'):
                merged['started_at'] = existing.get('started_at')
            merged['updated'] = _dt.now().isoformat(timespec='seconds')
            with open(status_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f)
        except Exception:
            pass

    def _refresh_theme_catalog(out_func, *, force: bool, fast_path: bool = False) -> None:
        """Generate or refresh theme JSON + per-theme YAML exports.

        force: when True pass --force to YAML exporter (used right after tagging).
        fast_path: when True indicates we are refreshing without a new tagging run.
        """
        try:  # Broad defensive guard: never let theme export kill setup flow
            phase_label = 'themes-fast' if fast_path else 'themes'
            # Start with an in-progress percent below 100 so UI knows additional work remains
            _write_status({"running": True, "phase": phase_label, "message": "Generating theme catalog...", "percent": 95})
            # Mark that we *attempted* an export; even if it fails we won't silently skip fallback repeat
            nonlocal theme_export_performed
            theme_export_performed = True
            from subprocess import run as _run
            # Resolve absolute script paths to avoid cwd-dependent failures inside container
            script_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
            extract_script = os.path.join(script_base, 'extract_themes.py')
            export_script = os.path.join(script_base, 'export_themes_to_yaml.py')
            build_script = os.path.join(script_base, 'build_theme_catalog.py')
            catalog_mode = os.environ.get('THEME_CATALOG_MODE', '').strip().lower()
            # Default to merge mode if build script exists unless explicitly set to 'legacy'
            use_merge = False
            if os.path.exists(build_script):
                if catalog_mode in {'merge', 'build', 'phaseb', ''} and catalog_mode != 'legacy':
                    use_merge = True
            import sys as _sys
            def _emit(msg: str):
                try:
                    if out_func:
                        out_func(msg)
                except Exception:
                    pass
                try:
                    print(msg)
                except Exception:
                    pass
            if use_merge:
                _emit("Attempting Phase B merged theme catalog build (build_theme_catalog.py)...")
                try:
                    _run([_sys.executable, build_script], check=True)
                    _emit("Merged theme catalog build complete.")
                    # Ensure per-theme YAML files are also updated so editorial workflows remain intact.
                    if os.path.exists(export_script):
                        # Optional fast-path skip: if enabled via env AND we are on fast_path AND not force.
                        # Default behavior now: ALWAYS force export so YAML stays aligned with merged JSON output.
                        fast_skip = False
                        try:
                            fast_skip = fast_path and not force and os.getenv('THEME_YAML_FAST_SKIP', '0').strip() not in {'', '0', 'false', 'False', 'no', 'NO'}
                        except Exception:
                            fast_skip = False
                        if fast_skip:
                            _emit("Per-theme YAML export skipped (fast path)")
                        else:
                            exp_args = [_sys.executable, export_script, '--force']  # unconditional force now
                            try:
                                _run(exp_args, check=True)
                                if fast_path:
                                    _emit("Per-theme YAML export (Phase A) completed post-merge (forced fast path).")
                                else:
                                    _emit("Per-theme YAML export (Phase A) completed post-merge (forced).")
                            except Exception as yerr:
                                _emit(f"YAML export after merge failed: {yerr}")
                except Exception as merge_err:
                    _emit(f"Merge build failed ({merge_err}); falling back to legacy extract/export.")
                    use_merge = False
            if not use_merge:
                if not os.path.exists(extract_script):
                    raise FileNotFoundError(f"extract script missing: {extract_script}")
                if not os.path.exists(export_script):
                    raise FileNotFoundError(f"export script missing: {export_script}")
                _emit("Refreshing theme catalog ({} path)...".format('fast' if fast_path else 'post-tagging'))
                _run([_sys.executable, extract_script], check=True)
                args = [_sys.executable, export_script]
                if force:
                    args.append('--force')
                _run(args, check=True)
                _emit("Theme catalog (JSON + YAML) refreshed{}.".format(" (fast path)" if fast_path else ""))
            # Mark progress complete
            _write_status({"running": True, "phase": phase_label, "message": "Theme catalog refreshed", "percent": 99})
            # Append status file enrichment with last export metrics
            try:
                status_path = os.path.join('csv_files', '.setup_status.json')
                if os.path.exists(status_path):
                    with open(status_path, 'r', encoding='utf-8') as _rf:
                        st = json.load(_rf) or {}
                else:
                    st = {}
                st.update({
                    'themes_last_export_at': _dt.now().isoformat(timespec='seconds'),
                    'themes_last_export_fast_path': bool(fast_path),
                    # Populate provenance if available (Phase B/C)
                })
                try:
                    theme_json_path = os.path.join('config', 'themes', 'theme_list.json')
                    if os.path.exists(theme_json_path):
                        with open(theme_json_path, 'r', encoding='utf-8') as _tf:
                            _td = json.load(_tf) or {}
                        prov = _td.get('provenance') or {}
                        if isinstance(prov, dict):
                            for k, v in prov.items():
                                st[f'theme_provenance_{k}'] = v
                except Exception:
                    pass
                # Write back
                with open(status_path, 'w', encoding='utf-8') as _wf:
                    json.dump(st, _wf)
            except Exception:
                pass
        except Exception as _e:  # pragma: no cover - non-critical diagnostics only
            try:
                out_func(f"Theme catalog refresh failed: {_e}")
            except Exception:
                pass
            try:
                print(f"Theme catalog refresh failed: {_e}")
            except Exception:
                pass
        finally:
            try:
                # Mark phase back to done if we were otherwise complete
                status_path = os.path.join('csv_files', '.setup_status.json')
                if os.path.exists(status_path):
                    with open(status_path, 'r', encoding='utf-8') as _rf:
                        st = json.load(_rf) or {}
                    # Only flip phase if previous run finished
                    if st.get('phase') in {'themes','themes-fast'}:
                        st['phase'] = 'done'
                        with open(status_path, 'w', encoding='utf-8') as _wf:
                            json.dump(st, _wf)
            except Exception:
                pass

    try:
        cards_path = os.path.join('csv_files', 'cards.csv')
        flag_path = os.path.join('csv_files', '.tagging_complete.json')
        auto_setup_enabled = _is_truthy_env('WEB_AUTO_SETUP', '1')
        # Allow tuning of time-based refresh; default 7 days
        try:
            days = int(os.getenv('WEB_AUTO_REFRESH_DAYS', '7'))
            refresh_age_seconds = max(0, days) * 24 * 60 * 60
        except Exception:
            refresh_age_seconds = 7 * 24 * 60 * 60
        refresh_needed = bool(force)
        if force:
            _write_status({"running": True, "phase": "setup", "message": "Forcing full setup and tagging...", "started_at": _dt.now().isoformat(timespec='seconds'), "percent": 0})

        if not os.path.exists(cards_path):
            out("cards.csv not found. Running initial setup and tagging...")
            _write_status({"running": True, "phase": "setup", "message": "Preparing card database (initial setup)...", "started_at": _dt.now().isoformat(timespec='seconds'), "percent": 0})
            refresh_needed = True
        else:
            try:
                age_seconds = time.time() - os.path.getmtime(cards_path)
                if age_seconds > refresh_age_seconds and not force:
                    out("cards.csv is older than 7 days. Refreshing data (setup + tagging)...")
                    _write_status({"running": True, "phase": "setup", "message": "Refreshing card database (initial setup)...", "started_at": _dt.now().isoformat(timespec='seconds'), "percent": 0})
                    refresh_needed = True
            except Exception:
                pass

        if not os.path.exists(flag_path):
            out("Tagging completion flag not found. Performing full tagging...")
            if not refresh_needed:
                _write_status({"running": True, "phase": "tagging", "message": "Applying tags to card database...", "started_at": _dt.now().isoformat(timespec='seconds'), "percent": 0})
            refresh_needed = True

        if refresh_needed:
            if not auto_setup_enabled and not force:
                out("Setup/tagging required, but WEB_AUTO_SETUP=0. Please run Setup from the UI.")
                _write_status({"running": False, "phase": "requires_setup", "message": "Setup required (auto disabled)."})
                return
            try:
                from file_setup.setup import initial_setup  # type: ignore
                # Always run initial_setup when forced or when cards are missing/stale
                initial_setup()
            except Exception as e:
                out(f"Initial setup failed: {e}")
                _write_status({"running": False, "phase": "error", "message": f"Initial setup failed: {e}"})
                return
            # Tagging with progress; support parallel workers for speed
            try:
                from tagging import tagger as _tagger  # type: ignore
                from settings import COLORS as _COLORS  # type: ignore
                colors = list(_COLORS)
                total = len(colors)
                use_parallel = str(os.getenv('WEB_TAG_PARALLEL', '1')).strip().lower() in {"1","true","yes","on"}
                max_workers_env = os.getenv('WEB_TAG_WORKERS')
                try:
                    max_workers = int(max_workers_env) if max_workers_env else None
                except Exception:
                    max_workers = None
                _write_status({
                    "running": True,
                    "phase": "tagging",
                    "message": "Tagging cards (this may take a while)..." if not use_parallel else "Tagging cards in parallel...",
                    "color": None,
                    "percent": 0,
                    "color_idx": 0,
                    "color_total": total,
                    "tagging_started_at": _dt.now().isoformat(timespec='seconds')
                })

                if use_parallel:
                    try:
                        import concurrent.futures as _f
                        completed = 0
                        with _f.ProcessPoolExecutor(max_workers=max_workers) as ex:
                            fut_map = {ex.submit(_tagger.load_dataframe, c): c for c in colors}
                            for fut in _f.as_completed(fut_map):
                                c = fut_map[fut]
                                try:
                                    fut.result()
                                    completed += 1
                                    pct = int(completed * 100 / max(1, total))
                                    _write_status({
                                        "running": True,
                                        "phase": "tagging",
                                        "message": f"Tagged {c}",
                                        "color": c,
                                        "percent": pct,
                                        "color_idx": completed,
                                        "color_total": total,
                                    })
                                except Exception as e:
                                    out(f"Parallel tagging failed for {c}: {e}")
                                    _write_status({"running": False, "phase": "error", "message": f"Tagging {c} failed: {e}", "color": c})
                                    return
                    except Exception as e:
                        out(f"Parallel tagging init failed: {e}; falling back to sequential")
                        use_parallel = False

                if not use_parallel:
                    for idx, _color in enumerate(colors, start=1):
                        try:
                            pct = int((idx - 1) * 100 / max(1, total))
                            # Estimate ETA based on average time per completed color
                            eta_s = None
                            try:
                                from datetime import datetime as __dt
                                ts = __dt.fromisoformat(json.load(open(os.path.join('csv_files', '.setup_status.json'), 'r', encoding='utf-8')).get('tagging_started_at'))  # type: ignore
                                elapsed = max(0.0, (_dt.now() - ts).total_seconds())
                                completed = max(0, idx - 1)
                                if completed > 0:
                                    avg = elapsed / completed
                                    remaining = max(0, total - completed)
                                    eta_s = int(avg * remaining)
                            except Exception:
                                eta_s = None
                            payload = {
                                "running": True,
                                "phase": "tagging",
                                "message": f"Tagging {_color}...",
                                "color": _color,
                                "percent": pct,
                                "color_idx": idx,
                                "color_total": total,
                            }
                            if eta_s is not None:
                                payload["eta_seconds"] = eta_s
                            _write_status(payload)
                            _tagger.load_dataframe(_color)
                        except Exception as e:
                            out(f"Tagging {_color} failed: {e}")
                            _write_status({"running": False, "phase": "error", "message": f"Tagging {_color} failed: {e}", "color": _color})
                            return
            except Exception as e:
                out(f"Tagging failed to start: {e}")
                _write_status({"running": False, "phase": "error", "message": f"Tagging failed to start: {e}"})
                return
            try:
                os.makedirs('csv_files', exist_ok=True)
                with open(flag_path, 'w', encoding='utf-8') as _fh:
                    json.dump({'tagged_at': _dt.now().isoformat(timespec='seconds')}, _fh)
                # Final status with percent 100 and timing info
                finished_dt = _dt.now()
                finished = finished_dt.isoformat(timespec='seconds')
                # Compute duration_seconds if started_at exists
                duration_s = None
                try:
                    from datetime import datetime as __dt
                    status_path = os.path.join('csv_files', '.setup_status.json')
                    with open(status_path, 'r', encoding='utf-8') as _rf:
                        _st = json.load(_rf) or {}
                    if _st.get('started_at'):
                        start_dt = __dt.fromisoformat(_st['started_at'])
                        duration_s = int(max(0.0, (finished_dt - start_dt).total_seconds()))
                except Exception:
                    duration_s = None
                # Generate / refresh theme catalog (JSON + per-theme YAML) BEFORE marking done so UI sees progress
                _refresh_theme_catalog(out, force=True, fast_path=False)
                payload = {"running": False, "phase": "done", "message": "Setup complete", "color": None, "percent": 100, "finished_at": finished, "themes_exported": True}
                if duration_s is not None:
                    payload["duration_seconds"] = duration_s
                _write_status(payload)
            except Exception:
                pass
    except Exception:
        # Non-fatal; downstream loads will still attempt and surface errors in logs
        _write_status({"running": False, "phase": "error", "message": "Setup check failed"})
    # Fast-path theme catalog refresh: if setup/tagging were already current (no refresh_needed executed)
    # ensure theme artifacts exist and are fresh relative to the tagging flag. This runs outside the
    # main try so that a failure here never blocks normal builds.
    try:  # noqa: E722 - defensive broad except acceptable for non-critical refresh
        # Only attempt if we did NOT just perform a refresh (refresh_needed False) and auto-setup enabled
        # We detect refresh_needed by checking presence of the status flag percent=100 and phase done.
        status_path = os.path.join('csv_files', '.setup_status.json')
        tag_flag = os.path.join('csv_files', '.tagging_complete.json')
        auto_setup_enabled = _is_truthy_env('WEB_AUTO_SETUP', '1')
        if not auto_setup_enabled:
            return
        refresh_recent = False
        try:
            if os.path.exists(status_path):
                with open(status_path, 'r', encoding='utf-8') as _rf:
                    st = json.load(_rf) or {}
                # If status percent just hit 100 moments ago (< 10s), we can skip fast-path work
                if st.get('percent') == 100 and st.get('phase') == 'done':
                    # If finished very recently we assume the main export already ran
                    fin = st.get('finished_at') or st.get('updated')
                    if isinstance(fin, str) and fin.strip():
                        try:
                            ts = _dt.fromisoformat(fin.strip())
                            if (time.time() - ts.timestamp()) < 10:
                                refresh_recent = True
                        except Exception:
                            pass
        except Exception:
            pass
        if refresh_recent:
            return

        theme_json = os.path.join('config', 'themes', 'theme_list.json')
        catalog_dir = os.path.join('config', 'themes', 'catalog')
        need_theme_refresh = False
        # Helper to parse ISO timestamp
        def _parse_iso(ts: str | None):
            if not ts:
                return None
            try:
                return _dt.fromisoformat(ts.strip()).timestamp()
            except Exception:
                return None
        tag_ts = None
        try:
            if os.path.exists(tag_flag):
                with open(tag_flag, 'r', encoding='utf-8') as f:
                    tag_ts = (json.load(f) or {}).get('tagged_at')
        except Exception:
            tag_ts = None
        tag_time = _parse_iso(tag_ts)
        theme_mtime = os.path.getmtime(theme_json) if os.path.exists(theme_json) else 0
        # Determine newest YAML or build script mtime to detect editorial changes
        newest_yaml_mtime = 0
        try:
            if os.path.isdir(catalog_dir):
                for fn in os.listdir(catalog_dir):
                    if fn.endswith('.yml'):
                        pth = os.path.join(catalog_dir, fn)
                        try:
                            mt = os.path.getmtime(pth)
                            if mt > newest_yaml_mtime:
                                newest_yaml_mtime = mt
                        except Exception:
                            pass
        except Exception:
            newest_yaml_mtime = 0
        build_script_path = os.path.join('code', 'scripts', 'build_theme_catalog.py')
        build_script_mtime = 0
        try:
            if os.path.exists(build_script_path):
                build_script_mtime = os.path.getmtime(build_script_path)
        except Exception:
            build_script_mtime = 0
        # Conditions triggering refresh:
        #  1. theme_list.json missing
        #  2. catalog dir missing or unusually small (< 100 files) – indicates first run or failure
        #  3. tagging flag newer than theme_list.json (themes stale relative to data)
        if not os.path.exists(theme_json):
            need_theme_refresh = True
        elif not os.path.isdir(catalog_dir):
            need_theme_refresh = True
        else:
            try:
                yml_count = len([p for p in os.listdir(catalog_dir) if p.endswith('.yml')])
                if yml_count < 100:  # heuristic threshold (we expect ~700+)
                    need_theme_refresh = True
            except Exception:
                need_theme_refresh = True
        # Trigger refresh if tagging newer
        if not need_theme_refresh and tag_time and tag_time > (theme_mtime + 1):
            need_theme_refresh = True
        # Trigger refresh if any catalog YAML newer than theme_list.json (editorial edits)
        if not need_theme_refresh and newest_yaml_mtime and newest_yaml_mtime > (theme_mtime + 1):
            need_theme_refresh = True
        # Trigger refresh if build script updated (logic changes)
        if not need_theme_refresh and build_script_mtime and build_script_mtime > (theme_mtime + 1):
            need_theme_refresh = True
        if need_theme_refresh:
            _refresh_theme_catalog(out, force=False, fast_path=True)
    except Exception:
        pass

    # Unconditional fallback: if (for any reason) no theme export ran above, perform a fast-path export now.
    # This guarantees that clicking Run Setup/Tagging always leaves themes current even when tagging wasn't needed.
    try:
        if not theme_export_performed:
            _refresh_theme_catalog(out, force=False, fast_path=True)
    except Exception:
        pass


def run_build(commander: str, tags: List[str], bracket: int, ideals: Dict[str, int], tag_mode: str | None = None, *, use_owned_only: bool | None = None, prefer_owned: bool | None = None, owned_names: List[str] | None = None, prefer_combos: bool | None = None, combo_target_count: int | None = None, combo_balance: str | None = None) -> Dict[str, Any]:
    """Run the deck build end-to-end with provided selections and capture logs.

    Returns: { ok: bool, log: str, csv_path: Optional[str], txt_path: Optional[str], error: Optional[str] }
    """
    logs: List[str] = []

    def out(msg: str) -> None:
        try:
            logs.append(msg)
        except Exception:
            pass

    # Defaults for return payload
    csv_path = None
    txt_path = None
    summary = None
    compliance_obj = None

    try:
        # Provide a no-op input function so any leftover prompts auto-accept defaults
        b = DeckBuilder(output_func=out, input_func=lambda _prompt: "", headless=True)
        # Ensure setup/tagging present for web headless run
        _ensure_setup_ready(out)
        # Commander selection
        df = b.load_commander_data()
        row = df[df["name"].astype(str) == str(commander)]
        if row.empty:
            return {"ok": False, "error": f"Commander not found: {commander}", "log": "\n".join(logs)}
        b._apply_commander_selection(row.iloc[0])

        # Tags
        b.selected_tags = list(tags or [])
        b.primary_tag = b.selected_tags[0] if len(b.selected_tags) > 0 else None
        b.secondary_tag = b.selected_tags[1] if len(b.selected_tags) > 1 else None
        b.tertiary_tag = b.selected_tags[2] if len(b.selected_tags) > 2 else None
        try:
            b._update_commander_dict_with_selected_tags()
        except Exception:
            pass

        # Bracket
        bd = next((x for x in BRACKET_DEFINITIONS if int(getattr(x, 'level', 0)) == int(bracket)), None)
        if bd is None:
            return {"ok": False, "error": f"Invalid bracket level: {bracket}", "log": "\n".join(logs)}
        b.bracket_definition = bd
        b.bracket_level = bd.level
        b.bracket_name = bd.name
        b.bracket_limits = dict(getattr(bd, 'limits', {}))

        # Ideal counts
        b.ideal_counts = {k: int(v) for k, v in (ideals or {}).items()}

        # Apply tag combine mode
        try:
            b.tag_mode = (str(tag_mode).upper() if tag_mode else b.tag_mode)
            if b.tag_mode not in ('AND','OR'):
                b.tag_mode = 'AND'
        except Exception:
            pass

        # Owned/Prefer-owned integration (optional for headless runs)
        try:
            if use_owned_only:
                b.use_owned_only = True  # type: ignore[attr-defined]
                # Prefer explicit owned_names list if provided; else let builder discover from files
                if owned_names:
                    try:
                        b.owned_card_names = set(str(n).strip() for n in owned_names if str(n).strip())  # type: ignore[attr-defined]
                    except Exception:
                        b.owned_card_names = set()  # type: ignore[attr-defined]
            # Soft preference flag does not filter; only biases selection order
            if prefer_owned:
                try:
                    b.prefer_owned = True  # type: ignore[attr-defined]
                    if owned_names and not getattr(b, 'owned_card_names', None):
                        b.owned_card_names = set(str(n).strip() for n in owned_names if str(n).strip())  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            pass

        # Load data and run phases
        try:
            b.determine_color_identity()
            b.setup_dataframes()
            # Global safety prune of disallowed categories (e.g., Game Changers) for headless builds
            _global_prune_disallowed_pool(b)
        except Exception as e:
            out(f"Failed to load color identity/card pool: {e}")

        # Thread combo preferences (if provided)
        try:
            if prefer_combos is not None:
                b.prefer_combos = bool(prefer_combos)  # type: ignore[attr-defined]
            if combo_target_count is not None:
                b.combo_target_count = int(combo_target_count)  # type: ignore[attr-defined]
            if combo_balance:
                bal = str(combo_balance).strip().lower()
                if bal in ('early','late','mix'):
                    b.combo_balance = bal  # type: ignore[attr-defined]
        except Exception:
            pass

        try:
            b._run_land_build_steps()
        except Exception as e:
            out(f"Land build failed: {e}")

        # M3: Inject includes after lands, before creatures/spells (matching CLI behavior)
        try:
            if hasattr(b, '_inject_includes_after_lands'):
                print(f"DEBUG WEB: About to inject includes. Include cards: {getattr(b, 'include_cards', [])}")
                # Use builder's logger if available
                if hasattr(b, 'logger'):
                    b.logger.info(f"DEBUG WEB: About to inject includes. Include cards: {getattr(b, 'include_cards', [])}")
                b._inject_includes_after_lands()
                print(f"DEBUG WEB: Finished injecting includes. Current deck size: {len(getattr(b, 'card_library', {}))}")
                if hasattr(b, 'logger'):
                    b.logger.info(f"DEBUG WEB: Finished injecting includes. Current deck size: {len(getattr(b, 'card_library', {}))}")
        except Exception as e:
            out(f"Include injection failed: {e}")
            print(f"Include injection failed: {e}")
            if hasattr(b, 'logger'):
                b.logger.error(f"Include injection failed: {e}")

        try:
            if hasattr(b, 'add_creatures_phase'):
                b.add_creatures_phase()
        except Exception as e:
            out(f"Creature phase failed: {e}")
        try:
            if hasattr(b, 'add_spells_phase'):
                # When combos are preferred, run auto-complete before bulk spells so additions aren't clamped
                try:
                    if bool(getattr(b, 'prefer_combos', False)):
                        # Re-use the staged runner logic for auto-combos
                        _ = run_stage  # anchor for mypy
                        # Minimal inline runner: mimic '__auto_complete_combos__' block
                        try:
                            # Load curated combos
                            from tagging.combo_schema import load_and_validate_combos as _load_combos
                            combos_model = None
                            try:
                                combos_model = _load_combos("config/card_lists/combos.json")
                            except Exception:
                                combos_model = None
                            # Build current name set including commander
                            names: list[str] = []
                            try:
                                names.extend(list(getattr(b, 'card_library', {}).keys()))
                            except Exception:
                                pass
                            try:
                                cmd = getattr(b, 'commander_name', None)
                                if cmd:
                                    names.append(cmd)
                            except Exception:
                                pass
                            # Count existing completed combos to reduce target budget
                            existing_pairs = 0
                            try:
                                if combos_model:
                                    present = {str(x).strip().lower() for x in names if str(x).strip()}
                                    for p in combos_model.pairs:
                                        a = str(p.a).strip().lower()
                                        bnm = str(p.b).strip().lower()
                                        if a in present and bnm in present:
                                            existing_pairs += 1
                            except Exception:
                                existing_pairs = 0
                            # Determine target and balance
                            try:
                                target_total = int(getattr(b, 'combo_target_count', 2))
                            except Exception:
                                target_total = 2
                            try:
                                balance = str(getattr(b, 'combo_balance', 'mix')).strip().lower()
                            except Exception:
                                balance = 'mix'
                            if balance not in ('early','late','mix'):
                                balance = 'mix'
                            remaining_pairs = max(0, target_total - existing_pairs)
                            lib_lower = {str(n).strip().lower() for n in getattr(b, 'card_library', {}).keys()}
                            added_any = False
                            # Determine missing partners
                            candidates: list[tuple[int, str]] = []
                            for p in (combos_model.pairs if combos_model else []):
                                a = str(p.a).strip()
                                bnm = str(p.b).strip()
                                a_l = a.lower()
                                b_l = bnm.lower()
                                has_a = (a_l in lib_lower) or (a_l == str(getattr(b, 'commander_name', '')).lower())
                                has_b = (b_l in lib_lower) or (b_l == str(getattr(b, 'commander_name', '')).lower())
                                target: str | None = None
                                if has_a and not has_b:
                                    target = bnm
                                elif has_b and not has_a:
                                    target = a
                                if not target:
                                    continue
                                # Score per balance
                                score = 0
                                try:
                                    if balance == 'early':
                                        score += (5 if getattr(p, 'cheap_early', False) else 0)
                                        score += (0 if getattr(p, 'setup_dependent', False) else 1)
                                    elif balance == 'late':
                                        score += (4 if getattr(p, 'setup_dependent', False) else 0)
                                        score += (0 if getattr(p, 'cheap_early', False) else 1)
                                    else:
                                        score += (3 if getattr(p, 'cheap_early', False) else 0)
                                        score += (2 if getattr(p, 'setup_dependent', False) else 0)
                                except Exception:
                                    pass
                                candidates.append((score, target))
                            candidates.sort(key=lambda x: (-x[0], x[1].lower()))
                            for _ in range(remaining_pairs):
                                if not candidates:
                                    break
                                _score, pick = candidates.pop(0)
                                # Resolve in current pool; enrich type/mana
                                try:
                                    df_pool = getattr(b, '_combined_cards_df', None)
                                    df_full = getattr(b, '_full_cards_df', None)
                                    row = None
                                    for df in (df_pool, df_full):
                                        if df is not None and not df.empty and 'name' in df.columns:
                                            r = df[df['name'].astype(str).str.lower() == pick.lower()]
                                            if not r.empty:
                                                row = r
                                                break
                                    if row is None or row.empty:
                                        continue
                                    pick = str(row.iloc[0]['name'])
                                    card_type = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                                    mana_cost = str(row.iloc[0].get('mana_cost', row.iloc[0].get('manaCost', '')) or '')
                                except Exception:
                                    card_type = ''
                                    mana_cost = ''
                                try:
                                    b.add_card(pick, card_type=card_type, mana_cost=mana_cost, role='Support', sub_role='Combo Partner', added_by='AutoCombos')
                                    out(f"Auto-Complete Combos: added '{pick}' to complete a detected pair.")
                                    added_any = True
                                    lib_lower.add(pick.lower())
                                except Exception:
                                    continue
                            if not added_any:
                                out("No combo partners added.")
                        except Exception as _e:
                            out(f"Auto-Complete Combos failed: {_e}")
                except Exception:
                    pass
                b.add_spells_phase()
        except Exception as e:
            out(f"Spell phase failed: {e}")
        try:
            if hasattr(b, 'post_spell_land_adjust'):
                b.post_spell_land_adjust()
        except Exception as e:
            out(f"Post-spell land adjust failed: {e}")

    # Reporting/exports
        try:
            if hasattr(b, 'run_reporting_phase'):
                b.run_reporting_phase()
        except Exception as e:
            out(f"Reporting phase failed: {e}")
        try:
            # If a custom export base is threaded via environment/session in web, we can respect env var
            try:
                custom_base = os.getenv('WEB_CUSTOM_EXPORT_BASE')
                if custom_base:
                    setattr(b, 'custom_export_base', custom_base)
            except Exception:
                pass
            if hasattr(b, 'export_decklist_csv'):
                csv_path = b.export_decklist_csv()  # type: ignore[attr-defined]
        except Exception as e:
            out(f"CSV export failed: {e}")
        try:
            if hasattr(b, 'export_decklist_text'):
                # Try to mirror build_deck_full behavior by displaying the contents
                import os as _os
                base, _ext = _os.path.splitext(_os.path.basename(csv_path)) if csv_path else (f"deck_{b.timestamp}", "")
                txt_path = b.export_decklist_text(filename=base + '.txt')  # type: ignore[attr-defined]
                try:
                    b._display_txt_contents(txt_path)
                except Exception:
                    pass
                # Compute bracket compliance and save JSON alongside exports
                try:
                    if hasattr(b, 'compute_and_print_compliance'):
                        rep0 = b.compute_and_print_compliance(base_stem=base)  # type: ignore[attr-defined]
                        # Attach planning preview (no mutation) and only auto-enforce if explicitly enabled
                        rep0 = _attach_enforcement_plan(b, rep0)
                        try:
                            import os as __os
                            _auto = str(__os.getenv('WEB_AUTO_ENFORCE', '0')).strip().lower() in {"1","true","yes","on"}
                        except Exception:
                            _auto = False
                        if _auto and isinstance(rep0, dict) and rep0.get('overall') == 'FAIL' and hasattr(b, 'enforce_and_reexport'):
                            b.enforce_and_reexport(base_stem=base, mode='auto')  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Load compliance JSON for UI consumption
                try:
                    # Prefer the in-memory report (with enforcement plan) when available
                    if rep0 is not None:
                        compliance_obj = rep0
                    else:
                        import json as _json
                        comp_path = _os.path.join('deck_files', f"{base}_compliance.json")
                        if _os.path.exists(comp_path):
                            with open(comp_path, 'r', encoding='utf-8') as _cf:
                                compliance_obj = _json.load(_cf)
                except Exception:
                    compliance_obj = None
        except Exception as e:
            out(f"Text export failed: {e}")

        # Build structured summary for UI
        try:
            if hasattr(b, 'build_deck_summary'):
                summary = b.build_deck_summary()  # type: ignore[attr-defined]
        except Exception:
            summary = None
        # Write sidecar summary JSON next to CSV (if available)
        try:
            if summary and csv_path:
                import os as _os
                import json as _json
                base, _ = _os.path.splitext(csv_path)
                sidecar = base + '.summary.json'
                meta = {
                    "commander": getattr(b, 'commander_name', '') or getattr(b, 'commander', ''),
                    "tags": list(getattr(b, 'selected_tags', []) or []) or [t for t in [getattr(b, 'primary_tag', None), getattr(b, 'secondary_tag', None), getattr(b, 'tertiary_tag', None)] if t],
                    "bracket_level": getattr(b, 'bracket_level', None),
                    "csv": csv_path,
                    "txt": txt_path,
                }
                # Attach custom deck name if provided
                try:
                    custom_base = getattr(b, 'custom_export_base', None)
                except Exception:
                    custom_base = None
                if isinstance(custom_base, str) and custom_base.strip():
                    meta["name"] = custom_base.strip()
                payload = {"meta": meta, "summary": summary}
                with open(sidecar, 'w', encoding='utf-8') as f:
                    _json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # Success return
        return {"ok": True, "log": "\n".join(logs), "csv_path": csv_path, "txt_path": txt_path, "summary": summary, "compliance": compliance_obj}
    except Exception as e:
        logs.append(f"Build failed: {e}")
        return {"ok": False, "error": str(e), "log": "\n".join(logs)}


# -----------------
# Step-by-step build session
# -----------------
def _make_stages(b: DeckBuilder) -> List[Dict[str, Any]]:
    stages: List[Dict[str, Any]] = []
    # Run Multi-Copy before land steps (per web-first flow preference)
    mc_selected = False
    try:
        mc_selected = bool(getattr(b, '_web_multi_copy', None))
    except Exception:
        mc_selected = False
    # Web UI: skip theme confirmation stages (CLI-only pauses)
    # Multi-Copy package first (if selected) so lands & targets can account for it
    if mc_selected:
        stages.append({"key": "multicopy", "label": "Multi-Copy Package", "runner_name": "__add_multi_copy__"})
    # Note: Combos auto-complete now runs late (near theme autofill), so we defer adding it here.
    # Land steps 1..8 (if present)
    for i in range(1, 9):
        fn = getattr(b, f"run_land_step{i}", None)
        if callable(fn):
            stages.append({"key": f"land{i}", "label": f"Lands (Step {i})", "runner_name": f"run_land_step{i}"})
    
    # M3: Include injection stage after lands, before creatures
    if hasattr(b, '_inject_includes_after_lands') and getattr(b, 'include_cards', None):
        stages.append({"key": "inject_includes", "label": "Include Cards", "runner_name": "__inject_includes__"})
    # Creatures split into theme sub-stages for web confirm
    # AND-mode pre-pass: add cards that match ALL selected themes first
    try:
        combine_mode = getattr(b, 'tag_mode', 'AND')
    except Exception:
        combine_mode = 'AND'
    has_two_tags = bool(getattr(b, 'primary_tag', None) and getattr(b, 'secondary_tag', None))
    if combine_mode == 'AND' and has_two_tags and hasattr(b, 'add_creatures_all_theme_phase'):
        stages.append({"key": "creatures_all_theme", "label": "Creatures: All-Theme", "runner_name": "add_creatures_all_theme_phase"})
    if getattr(b, 'primary_tag', None) and hasattr(b, 'add_creatures_primary_phase'):
        stages.append({"key": "creatures_primary", "label": "Creatures: Primary", "runner_name": "add_creatures_primary_phase"})
    if getattr(b, 'secondary_tag', None) and hasattr(b, 'add_creatures_secondary_phase'):
        stages.append({"key": "creatures_secondary", "label": "Creatures: Secondary", "runner_name": "add_creatures_secondary_phase"})
    if getattr(b, 'tertiary_tag', None) and hasattr(b, 'add_creatures_tertiary_phase'):
        stages.append({"key": "creatures_tertiary", "label": "Creatures: Tertiary", "runner_name": "add_creatures_tertiary_phase"})
    if hasattr(b, 'add_creatures_fill_phase'):
        stages.append({"key": "creatures_fill", "label": "Creatures: Fill", "runner_name": "add_creatures_fill_phase"})
    # Spells: prefer granular categories when available; otherwise fall back to bulk
    spell_categories: List[Tuple[str, str, str]] = [
        ("ramp", "Confirm Ramp", "add_ramp"),
        ("removal", "Confirm Removal", "add_removal"),
        ("wipes", "Confirm Board Wipes", "add_board_wipes"),
        ("card_advantage", "Confirm Card Advantage", "add_card_advantage"),
        ("protection", "Confirm Protection", "add_protection"),
    ]
    any_granular = any(callable(getattr(b, rn, None)) for _key, _label, rn in spell_categories)
    if any_granular:
        for key, label, runner in spell_categories:
            if callable(getattr(b, runner, None)):
                # Web UI: omit confirm stages; show only the action stage
                label_action = label.replace("Confirm ", "")
                stages.append({"key": f"spells_{key}", "label": label_action, "runner_name": runner})
        # When combos are preferred, run Auto-Complete Combos BEFORE final theme fill so there is room to add partners.
        try:
            prefer_c = bool(getattr(b, 'prefer_combos', False))
        except Exception:
            prefer_c = False
        # Respect bracket limits: if two-card combos are disallowed (limit == 0), skip auto-combos stage
        allow_combos = True
        try:
            lim = getattr(b, 'bracket_limits', {}).get('two_card_combos')
            if lim is not None and int(lim) == 0:
                allow_combos = False
        except Exception:
            allow_combos = True
        if prefer_c and allow_combos:
            stages.append({"key": "autocombos", "label": "Auto-Complete Combos", "runner_name": "__auto_complete_combos__"})
        # Ensure we include the theme filler step to top up to 100 cards
        if callable(getattr(b, 'fill_remaining_theme_spells', None)):
            stages.append({"key": "spells_fill", "label": "Theme Spell Fill", "runner_name": "fill_remaining_theme_spells"})
    elif hasattr(b, 'add_spells_phase'):
        # For monolithic spells, insert combos BEFORE the big spells stage so additions aren't clamped away
        try:
            prefer_c = bool(getattr(b, 'prefer_combos', False))
            allow_combos = True
            try:
                lim = getattr(b, 'bracket_limits', {}).get('two_card_combos')
                if lim is not None and int(lim) == 0:
                    allow_combos = False
            except Exception:
                allow_combos = True
            if prefer_c and allow_combos:
                stages.append({"key": "autocombos", "label": "Auto-Complete Combos", "runner_name": "__auto_complete_combos__"})
        except Exception:
            pass
        stages.append({"key": "spells", "label": "Spells", "runner_name": "add_spells_phase"})
    # Post-adjust
    if hasattr(b, 'post_spell_land_adjust'):
        stages.append({"key": "post_adjust", "label": "Post-Spell Land Adjust", "runner_name": "post_spell_land_adjust"})
    # Reporting
    if hasattr(b, 'run_reporting_phase'):
        stages.append({"key": "reporting", "label": "Reporting", "runner_name": "run_reporting_phase"})
    # Export is not a separate stage here; we will auto-export at the final continue.
    return stages


def start_build_ctx(
    commander: str,
    tags: List[str],
    bracket: int,
    ideals: Dict[str, int],
    tag_mode: str | None = None,
    *,
    use_owned_only: bool | None = None,
    prefer_owned: bool | None = None,
    owned_names: List[str] | None = None,
    locks: List[str] | None = None,
    custom_export_base: str | None = None,
    multi_copy: Dict[str, Any] | None = None,
    prefer_combos: bool | None = None,
    combo_target_count: int | None = None,
    combo_balance: str | None = None,
    include_cards: List[str] | None = None,
    exclude_cards: List[str] | None = None,
) -> Dict[str, Any]:
    logs: List[str] = []

    def out(msg: str) -> None:
        logs.append(msg)

    # Provide a no-op input function so staged web builds never block on input
    b = DeckBuilder(output_func=out, input_func=lambda _prompt: "", headless=True)
    # Ensure setup/tagging present before staged build, but respect WEB_AUTO_SETUP
    if not is_setup_ready():
        if _is_truthy_env('WEB_AUTO_SETUP', '1'):
            _ensure_setup_ready(out)
        else:
            out("Setup/tagging not ready. Please run Setup first (WEB_AUTO_SETUP=0).")
            raise RuntimeError("Setup required (WEB_AUTO_SETUP disabled)")
    # Commander selection
    df = b.load_commander_data()
    row = df[df["name"].astype(str) == str(commander)]
    if row.empty:
        raise ValueError(f"Commander not found: {commander}")
    b._apply_commander_selection(row.iloc[0])
    # Tags
    b.selected_tags = list(tags or [])
    b.primary_tag = b.selected_tags[0] if len(b.selected_tags) > 0 else None
    b.secondary_tag = b.selected_tags[1] if len(b.selected_tags) > 1 else None
    b.tertiary_tag = b.selected_tags[2] if len(b.selected_tags) > 2 else None
    try:
        b._update_commander_dict_with_selected_tags()
    except Exception:
        pass
    # Bracket
    bd = next((x for x in BRACKET_DEFINITIONS if int(getattr(x, 'level', 0)) == int(bracket)), None)
    if bd is None:
        raise ValueError(f"Invalid bracket level: {bracket}")
    b.bracket_definition = bd
    b.bracket_level = bd.level
    b.bracket_name = bd.name
    b.bracket_limits = dict(getattr(bd, 'limits', {}))
    # Ideals
    b.ideal_counts = {k: int(v) for k, v in (ideals or {}).items()}
    # Apply tag combine mode
    try:
        b.tag_mode = (str(tag_mode).upper() if tag_mode else b.tag_mode)
        if b.tag_mode not in ('AND','OR'):
            b.tag_mode = 'AND'
    except Exception:
        pass

    # Owned-only / prefer-owned (if requested)
    try:
        if use_owned_only:
            b.use_owned_only = True  # type: ignore[attr-defined]
            if owned_names:
                try:
                    b.owned_card_names = set(str(n).strip() for n in owned_names if str(n).strip())  # type: ignore[attr-defined]
                except Exception:
                    b.owned_card_names = set()  # type: ignore[attr-defined]
        if prefer_owned:
            try:
                b.prefer_owned = True  # type: ignore[attr-defined]
                if owned_names and not getattr(b, 'owned_card_names', None):
                    b.owned_card_names = set(str(n).strip() for n in owned_names if str(n).strip())  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass

    # Data load
    b.determine_color_identity()
    b.setup_dataframes()
    # Apply the same global pool pruning in interactive builds for consistency
    _global_prune_disallowed_pool(b)
    
    # Apply include/exclude cards (M3: Phase 2 - Full Include/Exclude)
    try:
        out(f"DEBUG ORCHESTRATOR: include_cards parameter: {include_cards}")
        out(f"DEBUG ORCHESTRATOR: exclude_cards parameter: {exclude_cards}")
        
        if include_cards:
            b.include_cards = list(include_cards)
            out(f"Applied include cards: {len(include_cards)} cards")
            out(f"DEBUG ORCHESTRATOR: Set builder.include_cards to: {b.include_cards}")
        else:
            out("DEBUG ORCHESTRATOR: No include cards to apply")
        if exclude_cards:
            b.exclude_cards = list(exclude_cards)
            # The filtering is already applied in setup_dataframes(), but we need
            # to call it again after setting exclude_cards
            b._combined_cards_df = None  # Clear cache to force rebuild
            b.setup_dataframes()  # This will now apply the exclude filtering
            out(f"Applied exclude filtering for {len(exclude_cards)} patterns")
        else:
            out("DEBUG ORCHESTRATOR: No exclude cards to apply")
    except Exception as e:
        out(f"Failed to apply include/exclude cards: {e}")
    
    # Thread multi-copy selection onto builder for stage generation/runner
    try:
        b._web_multi_copy = (multi_copy or None)
    except Exception:
        pass
    # Preference flags
    try:
        b.prefer_combos = bool(prefer_combos)
    except Exception:
        pass
    # Thread combo config
    try:
        if combo_target_count is not None:
            b.combo_target_count = int(combo_target_count)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        if combo_balance:
            bal = str(combo_balance).strip().lower()
            if bal in ('early','late','mix'):
                b.combo_balance = bal  # type: ignore[attr-defined]
    except Exception:
        pass
    # Stages
    stages = _make_stages(b)
    ctx = {
        "builder": b,
        "logs": logs,
        "stages": stages,
        "idx": 0,
        "last_log_idx": 0,
        "csv_path": None,
        "txt_path": None,
        "snapshot": None,
    "history": [],  # list of {i, key, label, snapshot}
        "locks": {str(n).strip().lower() for n in (locks or []) if str(n).strip()},
    "custom_export_base": str(custom_export_base).strip() if isinstance(custom_export_base, str) and custom_export_base.strip() else None,
    }
    return ctx


def _snapshot_builder(b: DeckBuilder) -> Dict[str, Any]:
    """Capture mutable state needed to rerun a stage."""
    snap: Dict[str, Any] = {}
    # Core collections
    snap["card_library"] = copy.deepcopy(getattr(b, 'card_library', {}))
    snap["tag_counts"] = copy.deepcopy(getattr(b, 'tag_counts', {}))
    snap["_card_name_tags_index"] = copy.deepcopy(getattr(b, '_card_name_tags_index', {}))
    snap["suggested_lands_queue"] = copy.deepcopy(getattr(b, 'suggested_lands_queue', []))
    # Caches and pools
    try:
        if getattr(b, '_combined_cards_df', None) is not None:
            snap["_combined_cards_df"] = b._combined_cards_df.copy(deep=True)
    except Exception:
        snap["_combined_cards_df"] = None
    try:
        if getattr(b, '_full_cards_df', None) is not None:
            snap["_full_cards_df"] = b._full_cards_df.copy(deep=True)
    except Exception:
        snap["_full_cards_df"] = None
    snap["_color_source_matrix_baseline"] = copy.deepcopy(getattr(b, '_color_source_matrix_baseline', None))
    snap["_color_source_matrix_cache"] = copy.deepcopy(getattr(b, '_color_source_matrix_cache', None))
    snap["_color_source_cache_dirty"] = getattr(b, '_color_source_cache_dirty', True)
    snap["_spell_pip_weights_cache"] = copy.deepcopy(getattr(b, '_spell_pip_weights_cache', None))
    snap["_spell_pip_cache_dirty"] = getattr(b, '_spell_pip_cache_dirty', True)
    return snap


def _restore_builder(b: DeckBuilder, snap: Dict[str, Any]) -> None:
    b.card_library = copy.deepcopy(snap.get("card_library", {}))
    b.tag_counts = copy.deepcopy(snap.get("tag_counts", {}))
    b._card_name_tags_index = copy.deepcopy(snap.get("_card_name_tags_index", {}))
    b.suggested_lands_queue = copy.deepcopy(snap.get("suggested_lands_queue", []))
    if "_combined_cards_df" in snap:
        b._combined_cards_df = snap["_combined_cards_df"]
    if "_full_cards_df" in snap:
        b._full_cards_df = snap["_full_cards_df"]
    b._color_source_matrix_baseline = copy.deepcopy(snap.get("_color_source_matrix_baseline", None))
    b._color_source_matrix_cache = copy.deepcopy(snap.get("_color_source_matrix_cache", None))
    b._color_source_cache_dirty = bool(snap.get("_color_source_cache_dirty", True))
    b._spell_pip_weights_cache = copy.deepcopy(snap.get("_spell_pip_weights_cache", None))
    b._spell_pip_cache_dirty = bool(snap.get("_spell_pip_cache_dirty", True))


def run_stage(ctx: Dict[str, Any], rerun: bool = False, show_skipped: bool = False, *, replace: bool = False) -> Dict[str, Any]:
    b: DeckBuilder = ctx["builder"]
    stages: List[Dict[str, Any]] = ctx["stages"]
    logs: List[str] = ctx["logs"]
    locks_set: set[str] = set(ctx.get("locks") or [])

    # If all stages done, finalize exports (interactive/manual build)
    if ctx["idx"] >= len(stages):
        # Apply custom export base if present in context
        try:
            custom_base = ctx.get("custom_export_base")
            if custom_base:
                setattr(b, 'custom_export_base', str(custom_base))
        except Exception:
            pass
        if not ctx.get("txt_path") and hasattr(b, 'export_decklist_text'):
            try:
                ctx["csv_path"] = b.export_decklist_csv()  # type: ignore[attr-defined]
            except Exception as e:
                logs.append(f"CSV export failed: {e}")
        if not ctx.get("txt_path") and hasattr(b, 'export_decklist_text'):
            try:
                import os as _os
                base, _ext = _os.path.splitext(_os.path.basename(ctx.get("csv_path") or f"deck_{b.timestamp}.csv"))
                ctx["txt_path"] = b.export_decklist_text(filename=base + '.txt')  # type: ignore[attr-defined]
                # Export the run configuration JSON for manual builds
                try:
                    b.export_run_config_json(directory='config', filename=base + '.json')  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Compute bracket compliance and save JSON alongside exports
                try:
                    if hasattr(b, 'compute_and_print_compliance'):
                        rep0 = b.compute_and_print_compliance(base_stem=base)  # type: ignore[attr-defined]
                        rep0 = _attach_enforcement_plan(b, rep0)
                        try:
                            import os as __os
                            _auto = str(__os.getenv('WEB_AUTO_ENFORCE', '0')).strip().lower() in {"1","true","yes","on"}
                        except Exception:
                            _auto = False
                        if _auto and isinstance(rep0, dict) and rep0.get('overall') == 'FAIL' and hasattr(b, 'enforce_and_reexport'):
                            b.enforce_and_reexport(base_stem=base, mode='auto')  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Load compliance JSON for UI consumption
                try:
                    # Prefer in-memory report if available
                    if rep0 is not None:
                        ctx["compliance"] = rep0
                    else:
                        import json as _json
                        comp_path = _os.path.join('deck_files', f"{base}_compliance.json")
                        if _os.path.exists(comp_path):
                            with open(comp_path, 'r', encoding='utf-8') as _cf:
                                ctx["compliance"] = _json.load(_cf)
                except Exception:
                    ctx["compliance"] = None
            except Exception as e:
                logs.append(f"Text export failed: {e}")
        # Final lock enforcement before finishing
        try:
            for lname in locks_set:
                try:
                    # If locked card missing, attempt to add a placeholder entry
                    if lname not in {str(n).strip().lower() for n in getattr(b, 'card_library', {}).keys()}:
                        # Try to find exact name in dataframes
                        target_name = None
                        try:
                            df = getattr(b, '_combined_cards_df', None)
                            if df is not None and not df.empty:
                                row = df[df['name'].astype(str).str.lower() == lname]
                                if not row.empty:
                                    target_name = str(row.iloc[0]['name'])
                        except Exception:
                            target_name = None
                        if target_name is None:
                            # As fallback, use the locked name as-is (display only)
                            target_name = lname
                        b.card_library[target_name] = {
                            'Count': 1,
                            'Role': 'Locked',
                            'SubRole': '',
                            'AddedBy': 'Lock',
                            'TriggerTag': '',
                        }
                except Exception:
                    continue
        except Exception:
            pass
        # Build structured summary for UI
        summary = None
        try:
            if hasattr(b, 'build_deck_summary'):
                summary = b.build_deck_summary()  # type: ignore[attr-defined]
        except Exception:
            summary = None
        # Write sidecar summary JSON next to CSV (if available)
        try:
            if summary and ctx.get("csv_path"):
                import os as _os
                import json as _json
                csv_path = ctx.get("csv_path")
                base, _ = _os.path.splitext(csv_path)
                sidecar = base + '.summary.json'
                meta = {
                    "commander": getattr(b, 'commander_name', '') or getattr(b, 'commander', ''),
                    "tags": list(getattr(b, 'selected_tags', []) or []) or [t for t in [getattr(b, 'primary_tag', None), getattr(b, 'secondary_tag', None), getattr(b, 'tertiary_tag', None)] if t],
                    "bracket_level": getattr(b, 'bracket_level', None),
                    "csv": ctx.get("csv_path"),
                    "txt": ctx.get("txt_path"),
                }
                try:
                    custom_base = getattr(b, 'custom_export_base', None)
                except Exception:
                    custom_base = None
                if isinstance(custom_base, str) and custom_base.strip():
                    meta["name"] = custom_base.strip()
                payload = {"meta": meta, "summary": summary}
                with open(sidecar, 'w', encoding='utf-8') as f:
                    _json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return {
            "done": True,
            "label": "Complete",
            "log_delta": "",
            "idx": len(stages),
            "total": len(stages),
            "csv_path": ctx.get("csv_path"),
            "txt_path": ctx.get("txt_path"),
            "summary": summary,
            "compliance": ctx.get("compliance"),
        }

    # Determine which stage index to run (rerun last visible, else current)
    if rerun:
        i = max(0, int(ctx.get("last_visible_idx", ctx["idx"]) or 1) - 1)
    else:
        i = ctx["idx"]

    # If compliance gating is active for the current stage, do not rerun the stage; block advancement until PASS
    try:
        gating = ctx.get('gating') or None
        if gating and isinstance(gating, dict) and int(gating.get('stage_idx', -1)) == int(i):
            # Recompute compliance snapshot
            comp_now = None
            try:
                if hasattr(b, 'compute_and_print_compliance'):
                    comp_now = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
            except Exception:
                comp_now = None
            try:
                if comp_now:
                    comp_now = _attach_enforcement_plan(b, comp_now)  # type: ignore[attr-defined]
            except Exception:
                pass
            # If still FAIL, return the saved result without advancing or rerunning
            try:
                if comp_now and str(comp_now.get('overall', 'PASS')).upper() == 'FAIL':
                    # Update total_cards live before returning saved result
                    try:
                        total_cards = 0
                        for _n, _e in getattr(b, 'card_library', {}).items():
                            try:
                                total_cards += int(_e.get('Count', 1))
                            except Exception:
                                total_cards += 1
                    except Exception:
                        total_cards = None
                    saved = gating.get('res') or {}
                    saved['total_cards'] = total_cards
                    saved['gated'] = True
                    return saved
            except Exception:
                pass
            # Gating cleared: advance to the next stage without rerunning the gated one
            try:
                del ctx['gating']
            except Exception:
                ctx['gating'] = None
            i = i + 1
            ctx['idx'] = i
            # continue into loop with advanced index
    except Exception:
        pass

    # Iterate forward until we find a stage that adds cards, skipping no-ops
    while i < len(stages):
        stage = stages[i]
        label = stage["label"]
        runner_name = stage["runner_name"]

        # Take snapshot before executing; for rerun with replace, restore first if we have one
        if rerun and replace and ctx.get("snapshot") is not None and i == max(0, int(ctx.get("last_visible_idx", ctx["idx"]) or 1) - 1):
            _restore_builder(b, ctx["snapshot"])  # restore to pre-stage state
        snap_before = _snapshot_builder(b)

        # Run the stage and capture logs delta
        start_log = len(logs)
        fn = getattr(b, runner_name, None)
        if runner_name == '__add_multi_copy__':
            try:
                sel = getattr(b, '_web_multi_copy', None) or {}
                card_name = str(sel.get('name') or '').strip()
                count = int(sel.get('count') or 0)
                add_thrum = bool(sel.get('thrumming'))
                sel_id = str(sel.get('id') or '').strip()
                # Look up archetype meta for type hints
                try:
                    from deck_builder import builder_constants as _bc
                    meta = (_bc.MULTI_COPY_ARCHETYPES or {}).get(sel_id, {})
                    type_hint = str(meta.get('type_hint') or '').strip().lower()
                except Exception:
                    type_hint = ''
                added_any = False
                mc_adjustments: list[str] = []
                # Helper: resolve display name via combined DF if possible for correct casing
                def _resolve_name(nm: str) -> str:
                    try:
                        df = getattr(b, '_combined_cards_df', None)
                        if df is not None and not df.empty:
                            row = df[df['name'].astype(str).str.lower() == str(nm).strip().lower()]
                            if not row.empty:
                                return str(row.iloc[0]['name'])
                    except Exception:
                        pass
                    return nm
                # Helper: enrich library entry with type and mana cost from DF when possible
                def _enrich_from_df(entry: dict, nm: str) -> None:
                    try:
                        df = getattr(b, '_combined_cards_df', None)
                        if df is None or getattr(df, 'empty', True):
                            return
                        row = df[df['name'].astype(str).str.lower() == str(nm).strip().lower()]
                        if row.empty:
                            return
                        r0 = row.iloc[0]
                        tline = str(r0.get('type', r0.get('type_line', '')) or '')
                        if tline:
                            entry['Card Type'] = tline
                        mc = r0.get('mana_cost', r0.get('manaCost'))
                        if isinstance(mc, str) and mc:
                            entry['Mana Cost'] = mc
                    except Exception:
                        return
                mc_summary_parts: list[str] = []
                if card_name and count > 0:
                    dn = _resolve_name(card_name)
                    entry = b.card_library.get(dn)
                    prev = int(entry.get('Count', 0)) if isinstance(entry, dict) else 0
                    new_count = prev + count
                    new_entry = {
                        'Count': new_count,
                        'Role': 'Theme',
                        'SubRole': 'Multi-Copy',
                        'AddedBy': 'MultiCopy',
                        'TriggerTag': ''
                    }
                    _enrich_from_df(new_entry, dn)
                    b.card_library[dn] = new_entry
                    logs.append(f"Added multi-copy package: {dn} x{count} (total {new_count}).")
                    mc_summary_parts.append(f"{dn} ×{count}")
                    added_any = True
                if add_thrum:
                    try:
                        tn = _resolve_name('Thrumming Stone')
                        e2 = b.card_library.get(tn)
                        prev2 = int(e2.get('Count', 0)) if isinstance(e2, dict) else 0
                        new_e2 = {
                            'Count': prev2 + 1,
                            'Role': 'Support',
                            'SubRole': 'Multi-Copy',
                            'AddedBy': 'MultiCopy',
                            'TriggerTag': ''
                        }
                        _enrich_from_df(new_e2, tn)
                        b.card_library[tn] = new_e2
                        logs.append("Included Thrumming Stone (1x).")
                        mc_summary_parts.append("Thrumming Stone ×1")
                        added_any = True
                    except Exception:
                        pass
                # Adjust ideal targets to prevent overfilling later phases
                try:
                    # Reduce creature target when the multi-copy is a creature-type archetype
                    if type_hint == 'creature':
                        cur = int(getattr(b, 'ideal_counts', {}).get('creatures', 0))
                        new_val = max(0, cur - max(0, count))
                        b.ideal_counts['creatures'] = new_val
                        logs.append(f"Adjusted target: creatures {cur} -> {new_val} due to multi-copy ({count}).")
                        mc_adjustments.append(f"creatures {cur}→{new_val}")
                    else:
                        # Spread reduction across spell categories in a stable order
                        to_spread = max(0, count + (1 if add_thrum else 0))
                        order = ['card_advantage', 'protection', 'removal', 'wipes']
                        for key in order:
                            if to_spread <= 0:
                                break
                            try:
                                cur = int(getattr(b, 'ideal_counts', {}).get(key, 0))
                            except Exception:
                                cur = 0
                            if cur <= 0:
                                continue
                            take = min(cur, to_spread)
                            b.ideal_counts[key] = cur - take
                            to_spread -= take
                            logs.append(f"Adjusted target: {key} {cur} -> {cur - take} due to multi-copy.")
                            mc_adjustments.append(f"{key} {cur}→{cur - take}")
                except Exception:
                    pass
                # Surface adjustments for Step 5 UI
                try:
                    if mc_adjustments:
                        ctx.setdefault('mc_adjustments', mc_adjustments)
                except Exception:
                    pass
                # Surface a concise summary for UI chip
                try:
                    if mc_summary_parts:
                        ctx['mc_summary'] = ' + '.join(mc_summary_parts)
                except Exception:
                    pass
                if not added_any:
                    logs.append("No multi-copy additions (empty selection).")
            except Exception as e:
                logs.append(f"Stage '{label}' failed: {e}")
        elif runner_name == '__inject_includes__':
            try:
                if hasattr(b, '_inject_includes_after_lands'):
                    b._inject_includes_after_lands()
                    include_count = len(getattr(b, 'include_cards', []))
                    logs.append(f"Include injection completed: {include_count} cards processed")
                else:
                    logs.append("Include injection method not available")
            except Exception as e:
                logs.append(f"Include injection failed: {e}")
                if hasattr(b, 'logger'):
                    b.logger.error(f"Include injection failed: {e}")
        elif runner_name == '__auto_complete_combos__':
            try:
                # Load curated combos
                from tagging.combo_schema import load_and_validate_combos as _load_combos
                combos_model = None
                try:
                    combos_model = _load_combos("config/card_lists/combos.json")
                except Exception:
                    combos_model = None
                # Build current name set including commander
                names: list[str] = []
                try:
                    names.extend(list(getattr(b, 'card_library', {}).keys()))
                except Exception:
                    pass
                try:
                    cmd = getattr(b, 'commander_name', None)
                    if cmd:
                        names.append(cmd)
                except Exception:
                    pass
                # Count existing completed combos to reduce target budget
                existing_pairs = 0
                try:
                    if combos_model:
                        present = {str(x).strip().lower() for x in names if str(x).strip()}
                        for p in combos_model.pairs:
                            a = str(p.a).strip().lower()
                            bnm = str(p.b).strip().lower()
                            if a in present and bnm in present:
                                existing_pairs += 1
                except Exception:
                    existing_pairs = 0
                # Determine target and balance
                try:
                    target_total = int(getattr(b, 'combo_target_count', 2))
                except Exception:
                    target_total = 2
                try:
                    balance = str(getattr(b, 'combo_balance', 'mix')).strip().lower()
                except Exception:
                    balance = 'mix'
                if balance not in ('early','late','mix'):
                    balance = 'mix'
                # Remaining pairs to aim for
                remaining_pairs = max(0, target_total - existing_pairs)
                # Determine missing partners for any pair where exactly one is present
                lib_lower = {str(n).strip().lower() for n in getattr(b, 'card_library', {}).keys()}
                locks_lower = locks_set
                added_any = False
                if remaining_pairs <= 0:
                    logs.append("Combo plan met by existing pairs; no additions needed.")
                # Build candidate list with scoring for balance
                candidates: list[tuple[int, str, dict]] = []  # (score, target_name, enrich_meta)
                for p in (combos_model.pairs if combos_model else []):
                    a = str(p.a).strip()
                    bname = str(p.b).strip()
                    a_l = a.lower()
                    b_l = bname.lower()
                    has_a = (a_l in lib_lower) or (a_l == str(getattr(b, 'commander_name', '')).lower())
                    has_b = (b_l in lib_lower) or (b_l == str(getattr(b, 'commander_name', '')).lower())
                    # If exactly one side present, attempt to add the other
                    target: str | None = None
                    if has_a and not has_b:
                        target = bname
                    elif has_b and not has_a:
                        target = a
                    if not target:
                        continue
                    # Respect locks
                    if target.lower() in locks_lower:
                        continue
                    # Owned-only check
                    try:
                        if getattr(b, 'use_owned_only', False):
                            owned = getattr(b, 'owned_card_names', set()) or set()
                            if owned and target.lower() not in {n.lower() for n in owned}:
                                continue
                    except Exception:
                        pass
                    # Score per balance
                    score = 0
                    try:
                        if balance == 'early':
                            score += (5 if getattr(p, 'cheap_early', False) else 0)
                            score += (0 if getattr(p, 'setup_dependent', False) else 1)
                        elif balance == 'late':
                            score += (4 if getattr(p, 'setup_dependent', False) else 0)
                            score += (0 if getattr(p, 'cheap_early', False) else 1)
                        else:  # mix
                            score += (3 if getattr(p, 'cheap_early', False) else 0)
                            score += (2 if getattr(p, 'setup_dependent', False) else 0)
                    except Exception:
                        pass
                    # Prefer targets that aren't already in library (already ensured), and stable name sort as tiebreaker
                    score_tuple = (score, target.lower(), {})
                    candidates.append(score_tuple)
                # Sort candidates descending by score then name asc
                candidates.sort(key=lambda x: (-x[0], x[1]))
                # Add up to remaining_pairs partners
                for _ in range(remaining_pairs):
                    if not candidates:
                        break
                    _score, pick, meta = candidates.pop(0)
                    # Resolve display name and enrich type/mana
                    card_type = ''
                    mana_cost = ''
                    try:
                        # Only consider the current filtered pool first (color-identity compliant).
                        df_pool = getattr(b, '_combined_cards_df', None)
                        df_full = getattr(b, '_full_cards_df', None)
                        row = None
                        for df in (df_pool, df_full):
                            if df is not None and not df.empty and 'name' in df.columns:
                                r = df[df['name'].astype(str).str.lower() == pick.lower()]
                                if not r.empty:
                                    row = r
                                    break
                        if row is None or row.empty:
                            # Skip if we cannot resolve in current pool (likely off-color/unavailable)
                            continue
                        pick = str(row.iloc[0]['name'])
                        card_type = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                        mana_cost = str(row.iloc[0].get('mana_cost', row.iloc[0].get('manaCost', '')) or '')
                    except Exception:
                        pass
                    try:
                        b.add_card(pick, card_type=card_type, mana_cost=mana_cost, role='Support', sub_role='Combo Partner', added_by='AutoCombos')
                        logs.append(f"Auto-Complete Combos: added '{pick}' to complete a detected pair.")
                        added_any = True
                        lib_lower.add(pick.lower())
                    except Exception:
                        continue
                if not added_any:
                    logs.append("No combo partners added.")
            except Exception as e:
                logs.append(f"Stage '{label}' failed: {e}")
        elif callable(fn):
            try:
                fn()
            except Exception as e:
                logs.append(f"Stage '{label}' failed: {e}")
        else:
            logs.append(f"Runner not available: {runner_name}")
        delta_log = "\n".join(logs[start_log:])

        # Enforce locks immediately after the stage runs so they appear in added list
        try:
            for lname in locks_set:
                try:
                    lib_keys_lower = {str(n).strip().lower(): str(n) for n in getattr(b, 'card_library', {}).keys()}
                    if lname not in lib_keys_lower:
                        # Try to resolve canonical name from DF
                        target_name = None
                        try:
                            df = getattr(b, '_combined_cards_df', None)
                            if df is not None and not df.empty:
                                row = df[df['name'].astype(str).str.lower() == lname]
                                if not row.empty:
                                    target_name = str(row.iloc[0]['name'])
                                    target_type = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                                    target_cost = str(row.iloc[0].get('mana_cost', row.iloc[0].get('manaCost', '')) or '')
                                else:
                                    target_type = ''
                                    target_cost = ''
                            else:
                                target_type = ''
                                target_cost = ''
                        except Exception:
                            target_name = None
                            target_type = ''
                            target_cost = ''
                        # Only add a lock placeholder if we can resolve this name in the current pool
                        if target_name is None:
                            # Unresolvable (likely off-color or unavailable) -> skip placeholder
                            continue
                        b.card_library[target_name] = {
                            'Count': 1,
                            'Card Type': target_type,
                            'Mana Cost': target_cost,
                            'Role': 'Locked',
                            'SubRole': '',
                            'AddedBy': 'Lock',
                            'TriggerTag': '',
                        }
                except Exception:
                    continue
        except Exception:
            pass

        # Compute added cards based on snapshot
        try:
            prev_lib = snap_before.get("card_library", {}) if isinstance(snap_before, dict) else {}
            added_cards: list[dict] = []
            for name, entry in b.card_library.items():
                try:
                    prev_entry = prev_lib.get(name)
                    prev_count = int(prev_entry.get('Count', 0)) if isinstance(prev_entry, dict) else 0
                    new_count = int(entry.get('Count', 1))
                    delta_count = max(0, new_count - prev_count)
                    if delta_count <= 0:
                        continue
                    role = str(entry.get('Role') or '').strip()
                    sub_role = str(entry.get('SubRole') or '').strip()
                    added_by = str(entry.get('AddedBy') or '').strip()
                    trig = str(entry.get('TriggerTag') or '').strip()
                    parts: list[str] = []
                    if role:
                        parts.append(role)
                    if sub_role:
                        parts.append(sub_role)
                    if added_by:
                        parts.append(f"by {added_by}")
                    if trig:
                        parts.append(f"tag: {trig}")
                    reason = " • ".join(parts)
                    added_cards.append({
                        "name": name,
                        "count": delta_count,
                        "reason": reason,
                        "role": role,
                        "sub_role": sub_role,
                        "trigger_tag": trig,
                    })
                except Exception:
                    continue
            added_cards.sort(key=lambda x: (x.get('reason') or '', x['name']))
        except Exception:
            added_cards = []

        # Final safety clamp: keep total deck size <= 100 by trimming this stage's additions first
        clamped_overflow = 0
        # Compute current total_cards upfront (used below and in response)
        try:
            total_cards = 0
            for _n, _e in getattr(b, 'card_library', {}).items():
                try:
                    total_cards += int(_e.get('Count', 1))
                except Exception:
                    total_cards += 1
        except Exception:
            total_cards = None
        try:
            overflow = max(0, int(total_cards) - 100)
            if overflow > 0 and added_cards:
                # Trim from added cards without reducing below pre-stage counts; skip locked names
                remaining = overflow
                for ac in reversed(added_cards):
                    if remaining <= 0:
                        break
                    try:
                        name = str(ac.get('name'))
                        if not name:
                            continue
                        if name.strip().lower() in locks_set:
                            continue
                        prev_entry = (snap_before.get('card_library') or {}).get(name)
                        prev_cnt = int(prev_entry.get('Count', 0)) if isinstance(prev_entry, dict) else 0
                        cur_entry = getattr(b, 'card_library', {}).get(name)
                        cur_cnt = int(cur_entry.get('Count', 1)) if isinstance(cur_entry, dict) else 1
                        can_reduce = max(0, cur_cnt - prev_cnt)
                        if can_reduce <= 0:
                            continue
                        take = min(can_reduce, remaining, int(ac.get('count', 0) or 0))
                        if take <= 0:
                            continue
                        new_cnt = cur_cnt - take
                        if new_cnt <= 0:
                            try:
                                del b.card_library[name]
                            except Exception:
                                pass
                        else:
                            cur_entry['Count'] = new_cnt
                        ac['count'] = max(0, int(ac.get('count', 0) or 0) - take)
                        remaining -= take
                        clamped_overflow += take
                    except Exception:
                        continue
                # Drop any zero-count added rows
                added_cards = [x for x in added_cards if int(x.get('count', 0) or 0) > 0]
                if clamped_overflow > 0:
                    try:
                        logs.append(f"Clamped {clamped_overflow} card(s) from this stage to remain at 100.")
                    except Exception:
                        pass
        except Exception:
            clamped_overflow = 0

        # Compute compliance after this stage and apply gating when FAIL
        comp = None
        try:
            if hasattr(b, 'compute_and_print_compliance'):
                comp = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
        except Exception:
            comp = None
        try:
            if comp:
                comp = _attach_enforcement_plan(b, comp)
        except Exception:
            pass

        # If FAIL, do not advance; save gating state and return current stage results
        try:
            if comp and str(comp.get('overall', 'PASS')).upper() == 'FAIL':
                # Save a snapshot of the response to reuse while gated
                res_hold = {
                    "done": False,
                    "label": label,
                    "log_delta": delta_log,
                    "added_cards": added_cards,
                    "idx": i + 1,
                    "total": len(stages),
                    "total_cards": total_cards,
                    "added_total": sum(int(c.get('count', 0) or 0) for c in added_cards) if added_cards else 0,
                    "mc_adjustments": ctx.get('mc_adjustments'),
                    "clamped_overflow": clamped_overflow,
                    "mc_summary": ctx.get('mc_summary'),
                    "gated": True,
                }
                ctx['gating'] = {"stage_idx": i, "label": label, "res": res_hold}
                # Keep current index (do not advance)
                ctx["snapshot"] = snap_before
                ctx["last_visible_idx"] = i + 1
                return res_hold
        except Exception:
            pass

        # If this stage added cards, present it and advance idx
        if added_cards:
            # Progress counts
            try:
                total_cards = 0
                for _n, _e in getattr(b, 'card_library', {}).items():
                    try:
                        total_cards += int(_e.get('Count', 1))
                    except Exception:
                        total_cards += 1
            except Exception:
                total_cards = None
            added_total = 0
            try:
                added_total = sum(int(c.get('count', 0) or 0) for c in added_cards)
            except Exception:
                added_total = 0
            ctx["snapshot"] = snap_before  # snapshot for rerun
            try:
                (ctx.setdefault("history", [])).append({
                    "i": i + 1,
                    "key": stage.get("key"),
                    "label": label,
                    "snapshot": snap_before,
                })
            except Exception:
                pass
            ctx["idx"] = i + 1
            ctx["last_visible_idx"] = i + 1
            return {
                "done": False,
                "label": label,
                "log_delta": delta_log,
                "added_cards": added_cards,
                "idx": i + 1,
                "total": len(stages),
                "total_cards": total_cards,
                "added_total": added_total,
                "mc_adjustments": ctx.get('mc_adjustments'),
                "clamped_overflow": clamped_overflow,
                "mc_summary": ctx.get('mc_summary'),
            }

        # No cards added: either skip or surface as a 'skipped' stage
        if show_skipped:
            # Compute compliance even when skipped; gate progression if FAIL
            comp = None
            try:
                if hasattr(b, 'compute_and_print_compliance'):
                    comp = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
            except Exception:
                comp = None
            try:
                if comp:
                    comp = _attach_enforcement_plan(b, comp)
            except Exception:
                pass
            try:
                if comp and str(comp.get('overall', 'PASS')).upper() == 'FAIL':
                    res_hold = {
                        "done": False,
                        "label": label,
                        "log_delta": delta_log,
                        "added_cards": [],
                        "skipped": True,
                        "idx": i + 1,
                        "total": len(stages),
                        "total_cards": total_cards,
                        "added_total": 0,
                        "gated": True,
                    }
                    ctx['gating'] = {"stage_idx": i, "label": label, "res": res_hold}
                    ctx["snapshot"] = snap_before
                    ctx["last_visible_idx"] = i + 1
                    return res_hold
            except Exception:
                pass
            # Progress counts even when skipped
            try:
                total_cards = 0
                for _n, _e in getattr(b, 'card_library', {}).items():
                    try:
                        total_cards += int(_e.get('Count', 1))
                    except Exception:
                        total_cards += 1
            except Exception:
                total_cards = None
            ctx["snapshot"] = snap_before
            try:
                (ctx.setdefault("history", [])).append({
                    "i": i + 1,
                    "key": stage.get("key"),
                    "label": label,
                    "snapshot": snap_before,
                })
            except Exception:
                pass
            ctx["idx"] = i + 1
            ctx["last_visible_idx"] = i + 1
            return {
                "done": False,
                "label": label,
                "log_delta": delta_log,
                "added_cards": [],
                "skipped": True,
                "idx": i + 1,
                "total": len(stages),
                "total_cards": total_cards,
                "added_total": 0,
            }

        # No cards added and not showing skipped: advance to next stage unless compliance FAIL gates progression
        try:
            comp = None
            try:
                if hasattr(b, 'compute_and_print_compliance'):
                    comp = b.compute_and_print_compliance(base_stem=None)  # type: ignore[attr-defined]
            except Exception:
                comp = None
            try:
                if comp:
                    comp = _attach_enforcement_plan(b, comp)
            except Exception:
                pass
            if comp and str(comp.get('overall', 'PASS')).upper() == 'FAIL':
                # Gate here with a skipped stage result
                res_hold = {
                    "done": False,
                    "label": label,
                    "log_delta": delta_log,
                    "added_cards": [],
                    "skipped": True,
                    "idx": i + 1,
                    "total": len(stages),
                    "total_cards": total_cards,
                    "added_total": 0,
                    "gated": True,
                }
                ctx['gating'] = {"stage_idx": i, "label": label, "res": res_hold}
                ctx["snapshot"] = snap_before
                ctx["last_visible_idx"] = i + 1
                return res_hold
        except Exception:
            pass
        i += 1
        # Continue loop to auto-advance

    # If we reached here, all remaining stages were no-ops; finalize exports
    ctx["idx"] = len(stages)
    # Apply custom export base if present
    try:
        custom_base = ctx.get("custom_export_base")
        if custom_base:
            setattr(b, 'custom_export_base', str(custom_base))
    except Exception:
        pass
    if not ctx.get("csv_path") and hasattr(b, 'export_decklist_csv'):
        try:
            ctx["csv_path"] = b.export_decklist_csv()  # type: ignore[attr-defined]
        except Exception as e:
            logs.append(f"CSV export failed: {e}")
    if not ctx.get("txt_path") and hasattr(b, 'export_decklist_text'):
        try:
            import os as _os
            base, _ext = _os.path.splitext(_os.path.basename(ctx.get("csv_path") or f"deck_{b.timestamp}.csv"))
            ctx["txt_path"] = b.export_decklist_text(filename=base + '.txt')  # type: ignore[attr-defined]
            # Export the run configuration JSON for manual builds
            try:
                b.export_run_config_json(directory='config', filename=base + '.json')  # type: ignore[attr-defined]
            except Exception:
                pass
            # Compute bracket compliance and save JSON alongside exports
            try:
                if hasattr(b, 'compute_and_print_compliance'):
                    rep0 = b.compute_and_print_compliance(base_stem=base)  # type: ignore[attr-defined]
                    rep0 = _attach_enforcement_plan(b, rep0)
                    try:
                        import os as __os
                        _auto = str(__os.getenv('WEB_AUTO_ENFORCE', '0')).strip().lower() in {"1","true","yes","on"}
                    except Exception:
                        _auto = False
                    if _auto and isinstance(rep0, dict) and rep0.get('overall') == 'FAIL' and hasattr(b, 'enforce_and_reexport'):
                        b.enforce_and_reexport(base_stem=base, mode='auto')  # type: ignore[attr-defined]
            except Exception:
                pass
            # Load compliance JSON for UI consumption
            try:
                if rep0 is not None:
                    ctx["compliance"] = rep0
                else:
                    import json as _json
                    comp_path = _os.path.join('deck_files', f"{base}_compliance.json")
                    if _os.path.exists(comp_path):
                        with open(comp_path, 'r', encoding='utf-8') as _cf:
                            ctx["compliance"] = _json.load(_cf)
            except Exception:
                ctx["compliance"] = None
        except Exception as e:
            logs.append(f"Text export failed: {e}")
    # Build structured summary for UI
    summary = None
    try:
        if hasattr(b, 'build_deck_summary'):
            summary = b.build_deck_summary()  # type: ignore[attr-defined]
    except Exception:
        summary = None
    # Write sidecar summary JSON next to CSV (if available)
    try:
        if summary and ctx.get("csv_path"):
            import os as _os
            import json as _json
            csv_path = ctx.get("csv_path")
            base, _ = _os.path.splitext(csv_path)
            sidecar = base + '.summary.json'
            meta = {
                "commander": getattr(b, 'commander_name', '') or getattr(b, 'commander', ''),
                "tags": list(getattr(b, 'selected_tags', []) or []) or [t for t in [getattr(b, 'primary_tag', None), getattr(b, 'secondary_tag', None), getattr(b, 'tertiary_tag', None)] if t],
                "bracket_level": getattr(b, 'bracket_level', None),
                "csv": ctx.get("csv_path"),
                "txt": ctx.get("txt_path"),
            }
            try:
                custom_base = getattr(b, 'custom_export_base', None)
            except Exception:
                custom_base = None
            if isinstance(custom_base, str) and custom_base.strip():
                meta["name"] = custom_base.strip()
            payload = {"meta": meta, "summary": summary}
            with open(sidecar, 'w', encoding='utf-8') as f:
                _json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # Final progress
    try:
        total_cards = 0
        for _n, _e in getattr(b, 'card_library', {}).items():
            try:
                total_cards += int(_e.get('Count', 1))
            except Exception:
                total_cards += 1
    except Exception:
        total_cards = None
    return {
        "done": True,
        "label": "Complete",
        "log_delta": "",
        "idx": len(stages),
        "total": len(stages),
        "csv_path": ctx.get("csv_path"),
        "txt_path": ctx.get("txt_path"),
        "summary": summary,
        "total_cards": total_cards,
        "added_total": 0,
        "compliance": ctx.get("compliance"),
    }
