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


def _ensure_setup_ready(out, force: bool = False) -> None:
    """Ensure card CSVs exist and tagging has completed; bootstrap if needed.

    Mirrors the CLI behavior used in build_deck_full: if csv_files/cards.csv is
    missing, too old, or the tagging flag is absent, run initial setup and tagging.
    """
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

    try:
        cards_path = os.path.join('csv_files', 'cards.csv')
        flag_path = os.path.join('csv_files', '.tagging_complete.json')
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
                if age_seconds > 7 * 24 * 60 * 60 and not force:
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
                payload = {"running": False, "phase": "done", "message": "Setup complete", "color": None, "percent": 100, "finished_at": finished}
                if duration_s is not None:
                    payload["duration_seconds"] = duration_s
                _write_status(payload)
            except Exception:
                pass
    except Exception:
        # Non-fatal; downstream loads will still attempt and surface errors in logs
        _write_status({"running": False, "phase": "error", "message": "Setup check failed"})


def run_build(commander: str, tags: List[str], bracket: int, ideals: Dict[str, int], tag_mode: str | None = None, *, use_owned_only: bool | None = None, prefer_owned: bool | None = None, owned_names: List[str] | None = None) -> Dict[str, Any]:
    """Run the deck build end-to-end with provided selections and capture logs.

    Returns: { ok: bool, log: str, csv_path: Optional[str], txt_path: Optional[str], error: Optional[str] }
    """
    logs: List[str] = []

    def out(msg: str) -> None:
        try:
            logs.append(msg)
        except Exception:
            pass

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
        except Exception as e:
            out(f"Failed to load color identity/card pool: {e}")

        try:
            b._run_land_build_steps()
        except Exception as e:
            out(f"Land build failed: {e}")

        try:
            if hasattr(b, 'add_creatures_phase'):
                b.add_creatures_phase()
        except Exception as e:
            out(f"Creature phase failed: {e}")
        try:
            if hasattr(b, 'add_spells_phase'):
                b.add_spells_phase()
        except Exception as e:
            out(f"Spell phase failed: {e}")
        try:
            if hasattr(b, 'post_spell_land_adjust'):
                b.post_spell_land_adjust()
        except Exception as e:
            out(f"Post-spell land adjust failed: {e}")

        # Reporting/exports
        csv_path = None
        txt_path = None
        try:
            if hasattr(b, 'run_reporting_phase'):
                b.run_reporting_phase()
        except Exception as e:
            out(f"Reporting phase failed: {e}")
        try:
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
        except Exception as e:
            out(f"Text export failed: {e}")

        # Build structured summary for UI
        summary = None
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
                payload = {"meta": meta, "summary": summary}
                with open(sidecar, 'w', encoding='utf-8') as f:
                    _json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return {"ok": True, "log": "\n".join(logs), "csv_path": csv_path, "txt_path": txt_path, "summary": summary}
    except Exception as e:
        logs.append(f"Build failed: {e}")
        return {"ok": False, "error": str(e), "log": "\n".join(logs)}


# -----------------
# Step-by-step build session
# -----------------
def _make_stages(b: DeckBuilder) -> List[Dict[str, Any]]:
    stages: List[Dict[str, Any]] = []
    # Web UI: skip theme confirmation stages (CLI-only pauses)
    # Land steps 1..8 (if present)
    for i in range(1, 9):
        fn = getattr(b, f"run_land_step{i}", None)
        if callable(fn):
            stages.append({"key": f"land{i}", "label": f"Lands (Step {i})", "runner_name": f"run_land_step{i}"})
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
        # Ensure we include the theme filler step to top up to 100 cards
        if callable(getattr(b, 'fill_remaining_theme_spells', None)):
            stages.append({"key": "spells_fill", "label": "Theme Spell Fill", "runner_name": "fill_remaining_theme_spells"})
    elif hasattr(b, 'add_spells_phase'):
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
) -> Dict[str, Any]:
    logs: List[str] = []

    def out(msg: str) -> None:
        logs.append(msg)

    # Provide a no-op input function so staged web builds never block on input
    b = DeckBuilder(output_func=out, input_func=lambda _prompt: "", headless=True)
    # Ensure setup/tagging present before staged build
    _ensure_setup_ready(out)
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


def run_stage(ctx: Dict[str, Any], rerun: bool = False, show_skipped: bool = False) -> Dict[str, Any]:
    b: DeckBuilder = ctx["builder"]
    stages: List[Dict[str, Any]] = ctx["stages"]
    logs: List[str] = ctx["logs"]

    # If all stages done, finalize exports (interactive/manual build)
    if ctx["idx"] >= len(stages):
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
        }

    # Determine which stage index to run (rerun last visible, else current)
    if rerun:
        i = max(0, int(ctx.get("last_visible_idx", ctx["idx"]) or 1) - 1)
    else:
        i = ctx["idx"]

    # Iterate forward until we find a stage that adds cards, skipping no-ops
    while i < len(stages):
        stage = stages[i]
        label = stage["label"]
        runner_name = stage["runner_name"]

        # Take snapshot before executing; for rerun, restore first if we have one
        if rerun and ctx.get("snapshot") is not None and i == max(0, int(ctx.get("last_visible_idx", ctx["idx"]) or 1) - 1):
            _restore_builder(b, ctx["snapshot"])  # restore to pre-stage state
        snap_before = _snapshot_builder(b)

        # Run the stage and capture logs delta
        start_log = len(logs)
        fn = getattr(b, runner_name, None)
        if callable(fn):
            try:
                fn()
            except Exception as e:
                logs.append(f"Stage '{label}' failed: {e}")
        else:
            logs.append(f"Runner not available: {runner_name}")
        delta_log = "\n".join(logs[start_log:])

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
            }

        # No cards added: either skip or surface as a 'skipped' stage
        if show_skipped:
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

        # No cards added and not showing skipped: advance to next
        i += 1
        # Continue loop to auto-advance

    # If we reached here, all remaining stages were no-ops; finalize exports
    ctx["idx"] = len(stages)
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
    }
