"""Theme preview sampling (Phase F – enhanced sampling & diversity heuristics).

Summary of implemented capabilities and pending roadmap items documented inline.
"""
from __future__ import annotations

from pathlib import Path
import csv
import time
import random
from collections import OrderedDict, deque
from typing import List, Dict, Any, Optional, Tuple, Iterable
import os
import json
import threading

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML already in requirements; defensive
    yaml = None  # type: ignore

from .theme_catalog_loader import load_index, slugify, project_detail

# NOTE: Remainder of module keeps large logic blocks; imports consolidated above per PEP8.

# Commander bias configuration constants
COMMANDER_COLOR_FILTER_STRICT = True  # If commander found, restrict sample to its color identity (except colorless)
COMMANDER_OVERLAP_BONUS = 1.8  # additive score bonus for sharing at least one tag with commander
COMMANDER_THEME_MATCH_BONUS = 0.9  # extra if also matches theme directly

## (duplicate imports removed)

# Adaptive TTL configuration (can be toggled via THEME_PREVIEW_ADAPTIVE=1)
# Starts at a baseline and is adjusted up/down based on cache hit ratio bands.
TTL_SECONDS = 600  # current effective TTL (mutable)
_TTL_BASE = 600
_TTL_MIN = 300
_TTL_MAX = 900
_ADAPT_SAMPLE_WINDOW = 120  # number of recent requests to evaluate
_ADAPTATION_ENABLED = (os.getenv("THEME_PREVIEW_ADAPTIVE") or "").lower() in {"1","true","yes","on"}
_RECENT_HITS: deque[bool] = deque(maxlen=_ADAPT_SAMPLE_WINDOW)
_LAST_ADAPT_AT: float | None = None
_ADAPT_INTERVAL_S = 30  # do not adapt more often than every 30s

_BG_REFRESH_THREAD_STARTED = False
_BG_REFRESH_INTERVAL_S = int(os.getenv("THEME_PREVIEW_BG_REFRESH_INTERVAL") or 120)
_BG_REFRESH_ENABLED = (os.getenv("THEME_PREVIEW_BG_REFRESH") or "").lower() in {"1","true","yes","on"}

# Adaptive background refresh heuristics (P2): we will adjust per-loop sleep based on
# recent error rate & p95 build latency. Bounds: [30s, 5 * base interval].
_BG_REFRESH_MIN = 30
_BG_REFRESH_MAX = max(300, _BG_REFRESH_INTERVAL_S * 5)

# Per-theme error histogram (P2 observability)
_PREVIEW_PER_THEME_ERRORS: Dict[str, int] = {}

# Optional curated synergy pair matrix externalization (P2 DATA).
_CURATED_SYNERGY_MATRIX_PATH = Path("config/themes/curated_synergy_matrix.yml")
_CURATED_SYNERGY_MATRIX: Dict[str, Dict[str, Any]] | None = None

def _load_curated_synergy_matrix() -> None:
    global _CURATED_SYNERGY_MATRIX
    if _CURATED_SYNERGY_MATRIX is not None:
        return
    if not _CURATED_SYNERGY_MATRIX_PATH.exists() or yaml is None:
        _CURATED_SYNERGY_MATRIX = None
        return
    try:
        with _CURATED_SYNERGY_MATRIX_PATH.open('r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict):
            # Expect top-level key 'pairs' but allow raw mapping
            pairs = data.get('pairs', data)
            if isinstance(pairs, dict):
                _CURATED_SYNERGY_MATRIX = pairs  # type: ignore
            else:
                _CURATED_SYNERGY_MATRIX = None
        else:
            _CURATED_SYNERGY_MATRIX = None
    except Exception:
        _CURATED_SYNERGY_MATRIX = None

_load_curated_synergy_matrix()

def _maybe_adapt_ttl(now: float) -> None:
    """Adjust global TTL_SECONDS based on recent hit ratio bands.

    Strategy:
      - If hit ratio < 0.25: decrease TTL slightly (favor freshness) ( -60s )
      - If hit ratio between 0.25–0.55: gently nudge toward base ( +/- 30s toward _TTL_BASE )
      - If hit ratio between 0.55–0.75: slight increase (+60s) (stability payoff)
      - If hit ratio > 0.75: stronger increase (+90s) to leverage locality
    Never exceeds [_TTL_MIN, _TTL_MAX]. Only runs if enough samples.
    """
    global TTL_SECONDS, _LAST_ADAPT_AT
    if not _ADAPTATION_ENABLED:
        return
    if len(_RECENT_HITS) < max(30, int(_ADAPT_SAMPLE_WINDOW * 0.5)):
        return  # insufficient data
    if _LAST_ADAPT_AT and (now - _LAST_ADAPT_AT) < _ADAPT_INTERVAL_S:
        return
    hit_ratio = sum(1 for h in _RECENT_HITS if h) / len(_RECENT_HITS)
    new_ttl = TTL_SECONDS
    if hit_ratio < 0.25:
        new_ttl = max(_TTL_MIN, TTL_SECONDS - 60)
    elif hit_ratio < 0.55:
        # move 30s toward base
        if TTL_SECONDS > _TTL_BASE:
            new_ttl = max(_TTL_BASE, TTL_SECONDS - 30)
        elif TTL_SECONDS < _TTL_BASE:
            new_ttl = min(_TTL_BASE, TTL_SECONDS + 30)
    elif hit_ratio < 0.75:
        new_ttl = min(_TTL_MAX, TTL_SECONDS + 60)
    else:
        new_ttl = min(_TTL_MAX, TTL_SECONDS + 90)
    if new_ttl != TTL_SECONDS:
        TTL_SECONDS = new_ttl
        try:
            print(json.dumps({"event":"theme_preview_ttl_adapt","hit_ratio":round(hit_ratio,3),"ttl":TTL_SECONDS}))  # noqa: T201
        except Exception:
            pass
    _LAST_ADAPT_AT = now

def _compute_bg_interval() -> int:
    """Derive adaptive sleep interval using recent metrics (P2 PERF)."""
    try:
        m = preview_metrics()
        p95 = float(m.get('preview_p95_build_ms') or 0.0)
        err_rate = float(m.get('preview_error_rate_pct') or 0.0)
        base = _BG_REFRESH_INTERVAL_S
        # Heuristic: high latency -> lengthen interval slightly (avoid stampede), high error rate -> shorten (refresh quicker)
        interval = base
        if p95 > 350:  # slow builds
            interval = int(base * 1.75)
        elif p95 > 250:
            interval = int(base * 1.4)
        elif p95 < 120:
            interval = int(base * 0.85)
        # Error rate influence
        if err_rate > 5.0:
            interval = max(_BG_REFRESH_MIN, int(interval * 0.6))
        elif err_rate < 1.0 and p95 < 180:
            # Very healthy -> stretch slightly (less churn)
            interval = min(_BG_REFRESH_MAX, int(interval * 1.15))
        return max(_BG_REFRESH_MIN, min(_BG_REFRESH_MAX, interval))
    except Exception:
        return max(_BG_REFRESH_MIN, _BG_REFRESH_INTERVAL_S)

def _bg_refresh_loop():  # pragma: no cover (background behavior)
    import time as _t
    while True:
        if not _BG_REFRESH_ENABLED:
            return
        try:
            ranked = sorted(_PREVIEW_PER_THEME_REQUESTS.items(), key=lambda kv: kv[1], reverse=True)
            top = [slug for slug,_cnt in ranked[:10]]
            for slug in top:
                try:
                    get_theme_preview(slug, limit=12, colors=None, commander=None, uncapped=True)
                except Exception:
                    continue
        except Exception:
            pass
        _t.sleep(_compute_bg_interval())

def _ensure_bg_refresh_thread():  # pragma: no cover
    global _BG_REFRESH_THREAD_STARTED
    if _BG_REFRESH_THREAD_STARTED or not _BG_REFRESH_ENABLED:
        return
    try:
        th = threading.Thread(target=_bg_refresh_loop, name="theme_preview_bg_refresh", daemon=True)
        th.start()
        _BG_REFRESH_THREAD_STARTED = True
    except Exception:
        pass

_PREVIEW_CACHE: "OrderedDict[Tuple[str, int, str | None, str | None, str], Dict[str, Any]]" = OrderedDict()
_CARD_INDEX: Dict[str, List[Dict[str, Any]]] = {}
_CARD_INDEX_MTIME: float | None = None
_PREVIEW_REQUESTS = 0
_PREVIEW_CACHE_HITS = 0
_PREVIEW_ERROR_COUNT = 0  # rolling count of preview build failures (non-cache operational)
_PREVIEW_REQUEST_ERROR_COUNT = 0  # client side reported fetch errors
_PREVIEW_BUILD_MS_TOTAL = 0.0
_PREVIEW_BUILD_COUNT = 0
_PREVIEW_LAST_BUST_AT: float | None = None
# Per-theme stats and global distribution tracking
_PREVIEW_PER_THEME: Dict[str, Dict[str, Any]] = {}
_PREVIEW_PER_THEME_REQUESTS: Dict[str, int] = {}
_BUILD_DURATIONS = deque(maxlen=500)  # rolling window for percentile calc
_ROLE_GLOBAL_COUNTS: Dict[str, int] = {"payoff": 0, "enabler": 0, "support": 0, "wildcard": 0}
_CURATED_GLOBAL = 0  # example + curated_synergy (non-synthetic curated content)
_SAMPLED_GLOBAL = 0

# Rarity normalization mapping (baseline – extend as new variants appear)
_RARITY_NORM = {
    "mythic rare": "mythic",
    "mythic": "mythic",
    "m": "mythic",
    "rare": "rare",
    "r": "rare",
    "uncommon": "uncommon",
    "u": "uncommon",
    "common": "common",
    "c": "common",
}

def _normalize_rarity(raw: str) -> str:
    r = (raw or "").strip().lower()
    return _RARITY_NORM.get(r, r)

def _preview_cache_max() -> int:
    try:
        val_raw = (__import__('os').getenv('THEME_PREVIEW_CACHE_MAX') or '400')
        val = int(val_raw)
        if val <= 0:
            raise ValueError("cache max must be >0")
        return val
    except Exception:
        # Emit single-line warning (stdout) – diagnostics style (won't break)
        try:
            print(json.dumps({"event":"theme_preview_cache_config_warning","message":"Invalid THEME_PREVIEW_CACHE_MAX; using default 400"}))  # noqa: T201
        except Exception:
            pass
        return 400

def _enforce_cache_limit():
    try:
        limit = max(50, _preview_cache_max())
        while len(_PREVIEW_CACHE) > limit:
            _PREVIEW_CACHE.popitem(last=False)  # FIFO eviction
    except Exception:
        pass

CARD_FILES_GLOB = [
    Path("csv_files/blue_cards.csv"),
    Path("csv_files/white_cards.csv"),
    Path("csv_files/black_cards.csv"),
    Path("csv_files/red_cards.csv"),
    Path("csv_files/green_cards.csv"),
    Path("csv_files/colorless_cards.csv"),
    Path("csv_files/cards.csv"),  # fallback large file last
]

THEME_TAGS_COL = "themeTags"
NAME_COL = "name"
COLOR_IDENTITY_COL = "colorIdentity"
MANA_COST_COL = "manaCost"
RARITY_COL = "rarity"  # Some CSVs may not include; optional


def _maybe_build_card_index():
    global _CARD_INDEX, _CARD_INDEX_MTIME
    latest = 0.0
    mtimes: List[float] = []
    for p in CARD_FILES_GLOB:
        if p.exists():
            mt = p.stat().st_mtime
            mtimes.append(mt)
            if mt > latest:
                latest = mt
    if _CARD_INDEX and _CARD_INDEX_MTIME and latest <= _CARD_INDEX_MTIME:
        return
    # Rebuild index
    _CARD_INDEX = {}
    for p in CARD_FILES_GLOB:
        if not p.exists():
            continue
        try:
            with p.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames or THEME_TAGS_COL not in reader.fieldnames:
                    continue
                for row in reader:
                    name = row.get(NAME_COL) or row.get("faceName") or ""
                    tags_raw = row.get(THEME_TAGS_COL) or ""
                    # tags stored like "['Blink', 'Enter the Battlefield']"; naive parse
                    tags = [t.strip(" '[]") for t in tags_raw.split(',') if t.strip()] if tags_raw else []
                    if not tags:
                        continue
                    color_id = (row.get(COLOR_IDENTITY_COL) or "").strip()
                    mana_cost = (row.get(MANA_COST_COL) or "").strip()
                    rarity = _normalize_rarity(row.get(RARITY_COL) or "")
                    for tg in tags:
                        if not tg:
                            continue
                        _CARD_INDEX.setdefault(tg, []).append({
                            "name": name,
                            "color_identity": color_id,
                            "tags": tags,
                            "mana_cost": mana_cost,
                            "rarity": rarity,
                            # Pre-parsed helpers (color identity list & pip colors from mana cost)
                            "color_identity_list": list(color_id) if color_id else [],
                            "pip_colors": [c for c in mana_cost if c in {"W","U","B","R","G"}],
                        })
        except Exception:
            continue
    _CARD_INDEX_MTIME = latest


def _classify_role(theme: str, synergies: List[str], tags: List[str]) -> str:
    tag_set = set(tags)
    synergy_overlap = tag_set.intersection(synergies)
    if theme in tag_set:
        return "payoff"
    if len(synergy_overlap) >= 2:
        return "enabler"
    if len(synergy_overlap) == 1:
        return "support"
    return "wildcard"


def _seed_from(theme: str, commander: Optional[str]) -> int:
    base = f"{theme.lower()}|{(commander or '').lower()}".encode("utf-8")
    # simple deterministic hash (stable across runs within Python version – keep primitive)
    h = 0
    for b in base:
        h = (h * 131 + b) & 0xFFFFFFFF
    return h or 1


def _deterministic_shuffle(items: List[Any], seed: int) -> None:
    rnd = random.Random(seed)
    rnd.shuffle(items)


def _score_card(theme: str, synergies: List[str], role: str, tags: List[str]) -> float:
    tag_set = set(tags)
    synergy_overlap = len(tag_set.intersection(synergies))
    score = 0.0
    if theme in tag_set:
        score += 3.0
    score += synergy_overlap * 1.2
    # Role weight baseline
    role_weights = {
        "payoff": 2.5,
        "enabler": 2.0,
        "support": 1.5,
        "wildcard": 0.9,
    }
    score += role_weights.get(role, 0.5)
    # Base rarity weighting (future: dynamic diminishing duplicate penalty)
    # Access rarity via closure later by augmenting item after score (handled outside)
    return score

def _commander_overlap_scale(commander_tags: set[str], card_tags: List[str], synergy_set: set[str]) -> float:
    """Refined overlap scaling: only synergy tag intersections count toward diminishing curve.

    Uses geometric diminishing returns: bonus = B * (1 - 0.5 ** n) where n is synergy overlap count.
    Guarantees first overlap grants 50% of base, second 75%, third 87.5%, asymptotically approaching B.
    """
    if not commander_tags or not synergy_set:
        return 0.0
    overlap_synergy = len(commander_tags.intersection(synergy_set).intersection(card_tags))
    if overlap_synergy <= 0:
        return 0.0
    return COMMANDER_OVERLAP_BONUS * (1 - (0.5 ** overlap_synergy))


def _lookup_commander(commander: Optional[str]) -> Optional[Dict[str, Any]]:
    if not commander:
        return None
    _maybe_build_card_index()
    # Commander can appear under many tags; brute scan limited to first match
    needle = commander.lower().strip()
    for tag_cards in _CARD_INDEX.values():
        for c in tag_cards:
            if c.get("name", "").lower() == needle:
                return c
    return None


def _sample_real_cards_for_theme(theme: str, limit: int, colors_filter: Optional[str], *, synergies: List[str], commander: Optional[str]) -> List[Dict[str, Any]]:
    _maybe_build_card_index()
    pool = _CARD_INDEX.get(theme) or []
    if not pool:
        return []
    commander_card = _lookup_commander(commander)
    commander_colors: set[str] = set(commander_card.get("color_identity", "")) if commander_card else set()
    commander_tags: set[str] = set(commander_card.get("tags", [])) if commander_card else set()
    if colors_filter:
        allowed = {c.strip().upper() for c in colors_filter.split(',') if c.strip()}
        if allowed:
            pool = [c for c in pool if set(c.get("color_identity", "")).issubset(allowed) or not c.get("color_identity")]
    # Apply commander color identity restriction if configured
    if commander_card and COMMANDER_COLOR_FILTER_STRICT and commander_colors:
        # Allow single off-color splash for 4-5 color commanders (leniency policy) with later mild penalty
        allow_splash = len(commander_colors) >= 4
        new_pool = []
        for c in pool:
            ci = set(c.get("color_identity", ""))
            if not ci or ci.issubset(commander_colors):
                new_pool.append(c)
                continue
            if allow_splash:
                off = ci - commander_colors
                if len(off) == 1:  # single off-color splash
                    # mark for later penalty (avoid mutating shared index structure deeply; tag ephemeral flag)
                    c["_splash_off_color"] = True  # type: ignore
                    new_pool.append(c)
                    continue
        pool = new_pool
    # Build role buckets
    seen_names: set[str] = set()
    payoff: List[Dict[str, Any]] = []
    enabler: List[Dict[str, Any]] = []
    support: List[Dict[str, Any]] = []
    wildcard: List[Dict[str, Any]] = []
    rarity_counts: Dict[str, int] = {}
    synergy_set = set(synergies)
    # Rarity calibration (P2 SAMPLING): allow tuning via env; default adjusted after observation.
    rarity_weight_base = {
        "mythic": float(os.getenv("RARITY_W_MYTHIC", "1.2")),
        "rare": float(os.getenv("RARITY_W_RARE", "0.9")),
        "uncommon": float(os.getenv("RARITY_W_UNCOMMON", "0.65")),
        "common": float(os.getenv("RARITY_W_COMMON", "0.4")),
    }
    for raw in pool:
        nm = raw.get("name")
        if not nm or nm in seen_names:
            continue
        seen_names.add(nm)
        tags = raw.get("tags", [])
        role = _classify_role(theme, synergies, tags)
        score = _score_card(theme, synergies, role, tags)
        reasons = [f"role:{role}", f"synergy_overlap:{len(set(tags).intersection(synergies))}"]
        if commander_card:
            if theme in tags:
                score += COMMANDER_THEME_MATCH_BONUS
                reasons.append("commander_theme_match")
            scaled = _commander_overlap_scale(commander_tags, tags, synergy_set)
            if scaled:
                score += scaled
                reasons.append(f"commander_synergy_overlap:{len(commander_tags.intersection(synergy_set).intersection(tags))}:{round(scaled,2)}")
            reasons.append("commander_bias")
        rarity = raw.get("rarity") or ""
        if rarity:
            base_rarity_weight = rarity_weight_base.get(rarity, 0.25)
            count_so_far = rarity_counts.get(rarity, 0)
            # Diminishing influence: divide by (1 + 0.4 * duplicates_already)
            score += base_rarity_weight / (1 + 0.4 * count_so_far)
            rarity_counts[rarity] = count_so_far + 1
            reasons.append(f"rarity_weight_calibrated:{rarity}:{round(base_rarity_weight/(1+0.4*count_so_far),2)}")
        # Splash leniency penalty (applied after other scoring)
        if raw.get("_splash_off_color"):
            score -= 0.3
            reasons.append("splash_off_color_penalty:-0.3")
        item = {
            "name": nm,
            "colors": list(raw.get("color_identity", "")),
            "roles": [role],
            "tags": tags,
            "score": score,
            "reasons": reasons,
            "mana_cost": raw.get("mana_cost"),
            "rarity": rarity,
            # Newly exposed server authoritative parsed helpers
            "color_identity_list": raw.get("color_identity_list", []),
            "pip_colors": raw.get("pip_colors", []),
        }
        if role == "payoff":
            payoff.append(item)
        elif role == "enabler":
            enabler.append(item)
        elif role == "support":
            support.append(item)
        else:
            wildcard.append(item)
    # Deterministic shuffle inside each bucket to avoid bias from CSV ordering
    seed = _seed_from(theme, commander)
    for bucket in (payoff, enabler, support, wildcard):
        _deterministic_shuffle(bucket, seed)
        # stable secondary ordering: higher score first, then name
        bucket.sort(key=lambda x: (-x["score"], x["name"]))

    # Diversity targets (after curated examples are pinned externally)
    target_payoff = max(1, int(round(limit * 0.4)))
    target_enabler_support = max(1, int(round(limit * 0.4)))
    # support grouped with enabler for quota distribution
    target_wild = max(0, limit - target_payoff - target_enabler_support)

    def take(n: int, source: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        for i in range(min(n, len(source))):
            yield source[i]

    chosen: List[Dict[str, Any]] = []
    # Collect payoff
    chosen.extend(take(target_payoff, payoff))
    # Collect enabler + support mix
    remaining_for_enab = target_enabler_support
    es_combined = enabler + support
    chosen.extend(take(remaining_for_enab, es_combined))
    # Collect wildcards
    chosen.extend(take(target_wild, wildcard))

    # If still short fill from remaining (payoff first, then enab, support, wildcard)
    if len(chosen) < limit:
        def fill_from(src: List[Dict[str, Any]]):
            nonlocal chosen
            for it in src:
                if len(chosen) >= limit:
                    break
                if it not in chosen:
                    chosen.append(it)
        for bucket in (payoff, enabler, support, wildcard):
            fill_from(bucket)

    # Role saturation penalty (post-selection adjustment): discourage dominance overflow beyond soft thresholds
    role_soft_caps = {
        "payoff": int(round(limit * 0.5)),
        "enabler": int(round(limit * 0.35)),
        "support": int(round(limit * 0.35)),
        "wildcard": int(round(limit * 0.25)),
    }
    role_seen: Dict[str, int] = {k: 0 for k in role_soft_caps}
    for it in chosen:
        r = (it.get("roles") or [None])[0]
        if not r or r not in role_soft_caps:
            continue
        role_seen[r] += 1
        if role_seen[r] > max(1, role_soft_caps[r]):
            it["score"] = it.get("score", 0) - 0.4
            (it.setdefault("reasons", [])).append("role_saturation_penalty:-0.4")
    # Truncate and re-rank final sequence deterministically by score then name (already ordered by selection except fill)
    if len(chosen) > limit:
        chosen = chosen[:limit]
    # Normalize score scale (optional future; keep raw for now)
    return chosen
# key: (slug, limit, colors, commander, etag)


def _now() -> float:  # small indirection for future test monkeypatch
    return time.time()


def _build_stub_items(detail: Dict[str, Any], limit: int, colors_filter: Optional[str], *, commander: Optional[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    # Start with curated example cards if present, else generic example_cards
    curated_cards = detail.get("example_cards") or []
    for idx, name in enumerate(curated_cards):
        if len(items) >= limit:
            break
        items.append({
            "name": name,
            "colors": [],  # unknown without deeper card DB link
            "roles": ["example"],
            "tags": [],
            "score": float(limit - idx),  # simple descending score
            "reasons": ["curated_example"],
        })
    # Curated synergy example cards (if any) follow standard examples but before sampled
    synergy_curated = detail.get("synergy_example_cards") or []
    for name in synergy_curated:
        if len(items) >= limit:
            break
        # Skip duplicates with example_cards
        if any(it["name"] == name for it in items):
            continue
        items.append({
            "name": name,
            "colors": [],
            "roles": ["curated_synergy"],
            "tags": [],
            "score": max((it["score"] for it in items), default=1.0) - 0.1,  # just below top examples
            "reasons": ["curated_synergy_example"],
        })
    # Remaining slots after curated examples
    remaining = max(0, limit - len(items))
    if remaining:
        theme_name = detail.get("theme")
        if isinstance(theme_name, str):
            all_synergies = []
            # Use uncapped synergies if available else merged list
            if detail.get("uncapped_synergies"):
                all_synergies = detail.get("uncapped_synergies") or []
            else:
                # Combine curated/enforced/inferred
                seen = set()
                for blk in (detail.get("curated_synergies") or [], detail.get("enforced_synergies") or [], detail.get("inferred_synergies") or []):
                    for s in blk:
                        if s not in seen:
                            all_synergies.append(s)
                            seen.add(s)
            real_cards = _sample_real_cards_for_theme(theme_name, remaining, colors_filter, synergies=all_synergies, commander=commander)
            for rc in real_cards:
                if len(items) >= limit:
                    break
                items.append(rc)
    if len(items) < limit:
        # Pad using synergies as synthetic placeholders to reach requested size
        synergies = detail.get("uncapped_synergies") or detail.get("synergies") or []
        for s in synergies:
            if len(items) >= limit:
                break
            synthetic_name = f"[{s}]"
            items.append({
                "name": synthetic_name,
                "colors": [],
                "roles": ["synthetic"],
                "tags": [s],
                "score": 0.5,  # lower score to keep curated first
                "reasons": ["synthetic_synergy_placeholder"],
            })
    return items


def get_theme_preview(theme_id: str, *, limit: int = 12, colors: Optional[str] = None, commander: Optional[str] = None, uncapped: bool = True) -> Dict[str, Any]:
    global _PREVIEW_REQUESTS, _PREVIEW_CACHE_HITS, _PREVIEW_BUILD_MS_TOTAL, _PREVIEW_BUILD_COUNT
    idx = load_index()
    slug = slugify(theme_id)
    entry = idx.slug_to_entry.get(slug)
    if not entry:
        raise KeyError("theme_not_found")
    # Use uncapped synergies for better placeholder coverage (diagnostics flag gating not applied here; placeholder only)
    detail = project_detail(slug, entry, idx.slug_to_yaml, uncapped=uncapped)
    colors_key = colors or None
    commander_key = commander or None
    cache_key = (slug, limit, colors_key, commander_key, idx.etag)
    _PREVIEW_REQUESTS += 1
    cached = _PREVIEW_CACHE.get(cache_key)
    if cached and (_now() - cached["_cached_at"]) < TTL_SECONDS:
        _PREVIEW_CACHE_HITS += 1
        _RECENT_HITS.append(True)
        # Count request (even if cache hit) for per-theme metrics
        _PREVIEW_PER_THEME_REQUESTS[slug] = _PREVIEW_PER_THEME_REQUESTS.get(slug, 0) + 1
        # Structured cache hit log (diagnostics gated)
        try:
            if (os.getenv("WEB_THEME_PREVIEW_LOG") or "").lower() in {"1","true","yes","on"}:
                print(json.dumps({
                    "event": "theme_preview_cache_hit",
                    "theme": slug,
                    "limit": limit,
                    "colors": colors_key,
                    "commander": commander_key,
                    "ttl_remaining_s": round(TTL_SECONDS - (_now() - cached["_cached_at"]), 2)
                }, separators=(",",":")))  # noqa: T201
        except Exception:
            pass
        # Annotate cache hit flag (shallow copy to avoid mutating stored payload timings)
        payload_cached = dict(cached["payload"])
        payload_cached["cache_hit"] = True
        return payload_cached
    _RECENT_HITS.append(False)
    # Build items
    t0 = _now()
    try:
        items = _build_stub_items(detail, limit, colors_key, commander=commander_key)
    except Exception as e:
        # Record error histogram & propagate
        _PREVIEW_PER_THEME_ERRORS[slug] = _PREVIEW_PER_THEME_ERRORS.get(slug, 0) + 1
        _PREVIEW_ERROR_COUNT += 1  # type: ignore
        raise e

    # Race condition guard (P2 RESILIENCE): If we somehow produced an empty sample (e.g., catalog rebuild mid-flight)
    # retry a limited number of times with small backoff.
    if not items:
        for _retry in range(2):  # up to 2 retries
            time.sleep(0.05)
            try:
                items = _build_stub_items(detail, limit, colors_key, commander=commander_key)
            except Exception:
                _PREVIEW_PER_THEME_ERRORS[slug] = _PREVIEW_PER_THEME_ERRORS.get(slug, 0) + 1
                _PREVIEW_ERROR_COUNT += 1  # type: ignore
                break
            if items:
                try:
                    print(json.dumps({"event":"theme_preview_retry_after_empty","theme":slug}))  # noqa: T201
                except Exception:
                    pass
                break
    build_ms = (_now() - t0) * 1000.0
    _PREVIEW_BUILD_MS_TOTAL += build_ms
    _PREVIEW_BUILD_COUNT += 1
    # Duplicate suppression safety across roles (should already be unique, defensive)
    seen_names: set[str] = set()
    dedup: List[Dict[str, Any]] = []
    for it in items:
        nm = it.get("name")
        if not nm:
            continue
        if nm in seen_names:
            continue
        seen_names.add(nm)
        dedup.append(it)
    items = dedup

    # Aggregate statistics
    curated_count = sum(1 for i in items if any(r in {"example", "curated_synergy"} for r in (i.get("roles") or [])))
    sampled_core_roles = {"payoff", "enabler", "support", "wildcard"}
    role_counts_local: Dict[str, int] = {r: 0 for r in sampled_core_roles}
    for i in items:
        roles = i.get("roles") or []
        for r in roles:
            if r in role_counts_local:
                role_counts_local[r] += 1
    # Update global counters
    global _ROLE_GLOBAL_COUNTS, _CURATED_GLOBAL, _SAMPLED_GLOBAL
    for r, c in role_counts_local.items():
        _ROLE_GLOBAL_COUNTS[r] = _ROLE_GLOBAL_COUNTS.get(r, 0) + c
    _CURATED_GLOBAL += curated_count
    _SAMPLED_GLOBAL += sum(role_counts_local.values())
    _BUILD_DURATIONS.append(build_ms)
    per = _PREVIEW_PER_THEME.setdefault(slug, {"builds": 0, "total_ms": 0.0, "durations": deque(maxlen=50), "role_counts": {r: 0 for r in sampled_core_roles}, "curated": 0, "sampled": 0})
    per["builds"] += 1
    per["total_ms"] += build_ms
    per["durations"].append(build_ms)
    per["curated"] += curated_count
    per["sampled"] += sum(role_counts_local.values())
    for r, c in role_counts_local.items():
        per["role_counts"][r] = per["role_counts"].get(r, 0) + c

    synergies_used = detail.get("uncapped_synergies") or detail.get("synergies") or []
    payload = {
        "theme_id": slug,
        "theme": detail.get("theme"),
        "count_total": len(items),  # population size TBD when full sampling added
        "sample": items,
        "synergies_used": synergies_used,
        "generated_at": idx.catalog.metadata_info.generated_at if idx.catalog.metadata_info else None,
        "colors_filter": colors_key,
        "commander": commander_key,
        "stub": False if any(it.get("roles") and it["roles"][0] in {"payoff", "support", "enabler", "wildcard"} for it in items) else True,
        "role_counts": role_counts_local,
        "curated_pct": round((curated_count / max(1, len(items))) * 100, 2),
        "build_ms": round(build_ms, 2),
        "curated_total": curated_count,
        "sampled_total": sum(role_counts_local.values()),
        "cache_hit": False,
    }
    _PREVIEW_CACHE[cache_key] = {"payload": payload, "_cached_at": _now()}
    _PREVIEW_CACHE.move_to_end(cache_key)
    _enforce_cache_limit()
    # Track request count post-build
    _PREVIEW_PER_THEME_REQUESTS[slug] = _PREVIEW_PER_THEME_REQUESTS.get(slug, 0) + 1
    # Structured logging (opt-in)
    try:
        if (os.getenv("WEB_THEME_PREVIEW_LOG") or "").lower() in {"1","true","yes","on"}:
            log_obj = {
                "event": "theme_preview_build",
                "theme": slug,
                "limit": limit,
                "colors": colors_key,
                "commander": commander_key,
                "build_ms": round(build_ms, 2),
                "curated_pct": payload["curated_pct"],
                "curated_total": payload["curated_total"],
                "sampled_total": payload["sampled_total"],
                "role_counts": role_counts_local,
                "cache_hit": False,
            }
            print(json.dumps(log_obj, separators=(",",":")))  # noqa: T201
    except Exception:
        pass
    # Post-build adaptive TTL evaluation & background refresher initialization
    _maybe_adapt_ttl(_now())
    _ensure_bg_refresh_thread()
    return payload


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1

def preview_metrics() -> Dict[str, Any]:
    avg_ms = (_PREVIEW_BUILD_MS_TOTAL / _PREVIEW_BUILD_COUNT) if _PREVIEW_BUILD_COUNT else 0.0
    durations_list = sorted(list(_BUILD_DURATIONS))
    p95 = _percentile(durations_list, 0.95)
    # Role distribution actual vs target (aggregate)
    total_roles = sum(_ROLE_GLOBAL_COUNTS.values()) or 1
    target = {"payoff": 0.4, "enabler+support": 0.4, "wildcard": 0.2}
    actual_enabler_support = (_ROLE_GLOBAL_COUNTS.get("enabler", 0) + _ROLE_GLOBAL_COUNTS.get("support", 0)) / total_roles
    role_distribution = {
        "payoff": {
            "count": _ROLE_GLOBAL_COUNTS.get("payoff", 0),
            "actual_pct": round((_ROLE_GLOBAL_COUNTS.get("payoff", 0) / total_roles) * 100, 2),
            "target_pct": target["payoff"] * 100,
        },
        "enabler_support": {
            "count": _ROLE_GLOBAL_COUNTS.get("enabler", 0) + _ROLE_GLOBAL_COUNTS.get("support", 0),
            "actual_pct": round(actual_enabler_support * 100, 2),
            "target_pct": target["enabler+support"] * 100,
        },
        "wildcard": {
            "count": _ROLE_GLOBAL_COUNTS.get("wildcard", 0),
            "actual_pct": round((_ROLE_GLOBAL_COUNTS.get("wildcard", 0) / total_roles) * 100, 2),
            "target_pct": target["wildcard"] * 100,
        },
    }
    editorial_coverage_pct = round((_CURATED_GLOBAL / max(1, (_CURATED_GLOBAL + _SAMPLED_GLOBAL))) * 100, 2)
    per_theme_stats = {}
    for slug, data in list(_PREVIEW_PER_THEME.items())[:50]:
        durs = list(data.get("durations", []))
        sd = sorted(durs)
        p50 = _percentile(sd, 0.50)
        p95_local = _percentile(sd, 0.95)
        per_theme_stats[slug] = {
            "avg_ms": round(data["total_ms"] / max(1, data["builds"]), 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95_local, 2),
            "builds": data["builds"],
            "avg_curated_pct": round((data["curated"] / max(1, (data["curated"] + data["sampled"])) ) * 100, 2),
            "requests": _PREVIEW_PER_THEME_REQUESTS.get(slug, 0),
            "curated_total": data.get("curated", 0),
            "sampled_total": data.get("sampled", 0),
        }
    error_rate = 0.0
    total_req = _PREVIEW_REQUESTS or 0
    if total_req:
        error_rate = round((_PREVIEW_ERROR_COUNT / total_req) * 100, 2)
    # Example coverage enforcement flag: when curated coverage exceeds threshold (default 90%)
    try:
        enforce_threshold = float(os.getenv("EXAMPLE_ENFORCE_THRESHOLD", "90"))
    except Exception:
        enforce_threshold = 90.0
    example_enforcement_active = editorial_coverage_pct >= enforce_threshold
    return {
        "preview_requests": _PREVIEW_REQUESTS,
        "preview_cache_hits": _PREVIEW_CACHE_HITS,
        "preview_cache_entries": len(_PREVIEW_CACHE),
        "preview_avg_build_ms": round(avg_ms, 2),
        "preview_p95_build_ms": round(p95, 2),
        "preview_error_rate_pct": error_rate,
        "preview_client_fetch_errors": _PREVIEW_REQUEST_ERROR_COUNT,
        "preview_ttl_seconds": TTL_SECONDS,
    "preview_ttl_adaptive": _ADAPTATION_ENABLED,
    "preview_ttl_window": len(_RECENT_HITS),
        "preview_last_bust_at": _PREVIEW_LAST_BUST_AT,
        "role_distribution": role_distribution,
    "editorial_curated_vs_sampled_pct": editorial_coverage_pct,
    "example_enforcement_active": example_enforcement_active,
    "example_enforce_threshold_pct": enforce_threshold,
        "editorial_curated_total": _CURATED_GLOBAL,
        "editorial_sampled_total": _SAMPLED_GLOBAL,
        "per_theme": per_theme_stats,
        "per_theme_errors": dict(list(_PREVIEW_PER_THEME_ERRORS.items())[:50]),
        "curated_synergy_matrix_loaded": _CURATED_SYNERGY_MATRIX is not None,
        "curated_synergy_matrix_size": sum(len(v) for v in _CURATED_SYNERGY_MATRIX.values()) if _CURATED_SYNERGY_MATRIX else 0,
    }


def bust_preview_cache(reason: str | None = None) -> None:
    """Clear in-memory preview cache (e.g., after catalog rebuild or tagging).

    Exposed for orchestrator hooks. Keeps metrics counters (requests/hits) for
    observability; records last bust timestamp.
    """
    global _PREVIEW_CACHE, _PREVIEW_LAST_BUST_AT
    try:  # defensive; never raise
        _PREVIEW_CACHE.clear()
        import time as _t
        _PREVIEW_LAST_BUST_AT = _t.time()
    except Exception:
        pass
