"""Theme preview orchestration.

Core Refactor Phase A (initial): sampling logic & cache container partially
extracted to `sampling.py` and `preview_cache.py` for modularity. This file now
focuses on orchestration: layering curated examples, invoking the sampling
pipeline, metrics aggregation, and cache usage. Public API (`get_theme_preview`,
`preview_metrics`, `bust_preview_cache`) remains stable.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import List, Dict, Any, Optional
import os
import json

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML already in requirements; defensive
    yaml = None  # type: ignore
from .preview_metrics import (
    record_build_duration,
    record_role_counts,
    record_curated_sampled,
    record_per_theme,
    record_request,
    record_per_theme_error,
    record_per_theme_request,
    preview_metrics,
    configure_external_access,
    record_splash_analytics,
)

from .theme_catalog_loader import load_index, slugify, project_detail
from .sampling import sample_real_cards_for_theme
from .sampling_config import (  # noqa: F401 (re-exported semantics; future use for inline commander display rules)
    COMMANDER_COLOR_FILTER_STRICT,
    COMMANDER_OVERLAP_BONUS,
    COMMANDER_THEME_MATCH_BONUS,
)
from .preview_cache import (
    PREVIEW_CACHE,
    bust_preview_cache,
    record_request_hit,
    maybe_adapt_ttl,
    ensure_bg_thread,
    ttl_seconds,
    recent_hit_window,
    preview_cache_last_bust_at,
    register_cache_hit,
    store_cache_entry,
    evict_if_needed,
)
from .preview_cache_backend import redis_get  # type: ignore
from .preview_metrics import record_redis_get, record_redis_store  # type: ignore

# Local alias to maintain existing internal variable name usage
_PREVIEW_CACHE = PREVIEW_CACHE

__all__ = ["get_theme_preview", "preview_metrics", "bust_preview_cache"]

# NOTE: Remainder of module keeps large logic blocks; imports consolidated above per PEP8.

# Commander bias configuration constants imported from sampling_config (centralized tuning)

## (duplicate imports removed)

# Legacy constant alias retained for any external references; now a function in cache module.
TTL_SECONDS = ttl_seconds  # type: ignore

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

def _collapse_duplicate_synergies(items: List[Dict[str, Any]], synergies_used: List[str]) -> None:
    """Annotate items that share identical synergy-overlap tag sets so UI can collapse.

    Heuristic rules:
      - Compute overlap set per card: tags intersecting synergies_used.
      - Only consider cards whose overlap set has size >=2 (strong synergy signal).
      - Group key = (primary_role, sorted_overlap_tuple).
      - Within each group of size >1, keep the highest score item as anchor; mark others:
            dup_collapsed=True, dup_anchor=<anchor name>, dup_group_size=N
      - Anchor receives fields: dup_anchor=True, dup_group_size=N
      - We do not mutate ordering or remove items (non-destructive); rendering layer may choose to hide collapsed ones behind an expand toggle.
    """
    if not items:
        return
    groups: Dict[tuple[str, tuple[str, ...]], List[Dict[str, Any]]] = {}
    for it in items:
        roles = it.get("roles") or []
        primary = roles[0] if roles else None
        if not primary or primary in {"example", "curated_synergy", "synthetic"}:
            continue
        tags = set(it.get("tags") or [])
        overlaps = [s for s in synergies_used if s in tags]
        if len(overlaps) < 2:
            continue
        key = (primary, tuple(sorted(overlaps)))
        groups.setdefault(key, []).append(it)
    for key, members in groups.items():
        if len(members) <= 1:
            continue
        # Pick anchor by highest score then alphabetical name for determinism
        anchor = sorted(members, key=lambda m: (-float(m.get("score", 0)), m.get("name", "")))[0]
        anchor["dup_anchor"] = True
        anchor["dup_group_size"] = len(members)
        for m in members:
            if m is anchor:
                continue
            m["dup_collapsed"] = True
            m["dup_anchor_name"] = anchor.get("name")
            m["dup_group_size"] = len(members)
            (m.setdefault("reasons", [])).append("duplicate_synergy_collapsed")


def _hot_slugs() -> list[str]:  # background refresh helper
    ranked = sorted(_PREVIEW_PER_THEME_REQUESTS.items(), key=lambda kv: kv[1], reverse=True)
    return [slug for slug,_cnt in ranked[:10]]

def _build_hot(slug: str) -> None:
    get_theme_preview(slug, limit=12, colors=None, commander=None, uncapped=True)

## Deprecated card index & rarity normalization logic previously embedded here has been
## fully migrated to `card_index.py` (Phase A). Residual globals & helpers removed
## 2025-09-23.
## NOTE: If legacy tests referenced `_CARD_INDEX` they should now patch via
## `code.web.services.card_index._CARD_INDEX` instead (already updated in new unit tests).
_PREVIEW_LAST_BUST_AT: float | None = None  # retained for backward compatibility (wired from cache)
_PER_THEME_BUILD: Dict[str, Dict[str, Any]] = {}  # lightweight local cache for hot list ranking only
_PREVIEW_PER_THEME_REQUESTS: Dict[str, int] = {}

## Rarity normalization moved to card ingestion pipeline (card_index).

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
    # Delegated to adaptive eviction logic (evict_if_needed handles size checks & errors)
    evict_if_needed()


## NOTE: Detailed sampling & scoring helpers removed; these now live in sampling.py.
## Only orchestration logic remains below.


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
            "score": float(limit - len(items)),
            "reasons": ["curated_synergy_example"],
        })
    return items
def get_theme_preview(theme_id: str, *, limit: int = 12, colors: Optional[str] = None, commander: Optional[str] = None, uncapped: bool = True) -> Dict[str, Any]:
    """Build or retrieve a theme preview sample.

    This is the orchestrator entrypoint used by the FastAPI route layer. It
    coordinates cache lookup, layered curated examples, real card sampling,
    metrics emission, and adaptive TTL / background refresh hooks.
    """
    idx = load_index()
    slug = slugify(theme_id)
    entry = idx.slug_to_entry.get(slug)
    if not entry:
        raise KeyError("theme_not_found")
    detail = project_detail(slug, entry, idx.slug_to_yaml, uncapped=uncapped)
    colors_key = colors or None
    commander_key = commander or None
    cache_key = (slug, limit, colors_key, commander_key, idx.etag)

    # Cache lookup path
    cached = PREVIEW_CACHE.get(cache_key)
    if cached and (_now() - cached.get("_cached_at", 0)) < ttl_seconds():
        record_request(hit=True)
        record_request_hit(True)
        record_per_theme_request(slug)
        # Update metadata for adaptive eviction heuristics
        register_cache_hit(cache_key)
        payload_cached = dict(cached["payload"])  # shallow copy to annotate
        payload_cached["cache_hit"] = True
        try:
            if (os.getenv("WEB_THEME_PREVIEW_LOG") or "").lower() in {"1","true","yes","on"}:
                print(json.dumps({
                    "event": "theme_preview_cache_hit",
                    "theme": slug,
                    "limit": limit,
                    "colors": colors_key,
                    "commander": commander_key,
                }, separators=(",",":")))  # noqa: T201
        except Exception:
            pass
        return payload_cached
    # Attempt Redis read-through if configured (memory miss only)
    if (not cached) and os.getenv("THEME_PREVIEW_REDIS_URL") and not os.getenv("THEME_PREVIEW_REDIS_DISABLE"):
        try:
            r_entry = redis_get(cache_key)
            if r_entry and (_now() - r_entry.get("_cached_at", 0)) < ttl_seconds():
                # Populate memory cache (no build cost measurement available; reuse stored)
                PREVIEW_CACHE[cache_key] = r_entry
                record_redis_get(hit=True)
                record_request(hit=True)
                record_request_hit(True)
                record_per_theme_request(slug)
                register_cache_hit(cache_key)
                payload_cached = dict(r_entry["payload"])
                payload_cached["cache_hit"] = True
                payload_cached["redis_source"] = True
                return payload_cached
            else:
                record_redis_get(hit=False)
        except Exception:
            record_redis_get(hit=False, error=True)

    # Cache miss path
    record_request(hit=False)
    record_request_hit(False)
    record_per_theme_request(slug)

    t0 = _now()
    try:
        items = _build_stub_items(detail, limit, colors_key, commander=commander_key)
        # Fill remaining with sampled real cards
        remaining = max(0, limit - len(items))
        if remaining:
            synergies = []
            if detail.get("uncapped_synergies"):
                synergies = detail.get("uncapped_synergies") or []
            else:
                seen_sy = set()
                for blk in (detail.get("curated_synergies") or [], detail.get("enforced_synergies") or [], detail.get("inferred_synergies") or []):
                    for s in blk:
                        if s not in seen_sy:
                            synergies.append(s)
                            seen_sy.add(s)
            real_cards = sample_real_cards_for_theme(detail.get("theme"), remaining, colors_key, synergies=synergies, commander=commander_key)
            for rc in real_cards:
                if len(items) >= limit:
                    break
                items.append(rc)
        # Pad with synthetic placeholders if still short
        if len(items) < limit:
            synergies_fallback = detail.get("uncapped_synergies") or detail.get("synergies") or []
            for s in synergies_fallback:
                if len(items) >= limit:
                    break
                items.append({
                    "name": f"[{s}]",
                    "colors": [],
                    "roles": ["synthetic"],
                    "tags": [s],
                    "score": 0.5,
                    "reasons": ["synthetic_synergy_placeholder"],
                })
        # Duplicate synergy collapse heuristic (Optional roadmap item)
        # Goal: group cards that share identical synergy overlap sets (>=2 overlaps) and same primary role.
        # We only mark metadata; UI decides whether to render collapsed items.
        try:
            synergies_used_local = detail.get("uncapped_synergies") or detail.get("synergies") or []
            if synergies_used_local:
                _collapse_duplicate_synergies(items, synergies_used_local)
        except Exception:
            # Heuristic failures must never break preview path
            pass
    except Exception as e:
        record_per_theme_error(slug)
        raise e

    build_ms = (_now() - t0) * 1000.0

    # Metrics aggregation
    curated_count = sum(1 for it in items if any(r in {"example", "curated_synergy"} for r in (it.get("roles") or [])))
    sampled_core_roles = {"payoff", "enabler", "support", "wildcard"}
    role_counts_local: Dict[str, int] = {r: 0 for r in sampled_core_roles}
    for it in items:
        for r in it.get("roles") or []:
            if r in role_counts_local:
                role_counts_local[r] += 1
    sampled_count = sum(role_counts_local.values())
    record_build_duration(build_ms)
    record_role_counts(role_counts_local)
    record_curated_sampled(curated_count, sampled_count)
    record_per_theme(slug, build_ms, curated_count, sampled_count)
    # Splash analytics: count off-color splash cards & penalty applications
    splash_off_color_cards = 0
    splash_penalty_events = 0
    for it in items:
        reasons = it.get("reasons") or []
        for r in reasons:
            if r.startswith("splash_off_color_penalty"):
                splash_penalty_events += 1
        if any(r.startswith("splash_off_color_penalty") for r in reasons):
            splash_off_color_cards += 1
    record_splash_analytics(splash_off_color_cards, splash_penalty_events)

    # Track lightweight per-theme build ms locally for hot list ranking (not authoritative metrics)
    per = _PER_THEME_BUILD.setdefault(slug, {"builds": 0, "total_ms": 0.0})
    per["builds"] += 1
    per["total_ms"] += build_ms

    synergies_used = detail.get("uncapped_synergies") or detail.get("synergies") or []
    payload = {
        "theme_id": slug,
        "theme": detail.get("theme"),
        "count_total": len(items),
        "sample": items,
        "synergies_used": synergies_used,
        "generated_at": idx.catalog.metadata_info.generated_at if idx.catalog.metadata_info else None,
        "colors_filter": colors_key,
        "commander": commander_key,
        "stub": False if any(it.get("roles") and it["roles"][0] in sampled_core_roles for it in items) else True,
        "role_counts": role_counts_local,
        "curated_pct": round((curated_count / max(1, len(items))) * 100, 2),
        "build_ms": round(build_ms, 2),
        "curated_total": curated_count,
        "sampled_total": sampled_count,
        "cache_hit": False,
        "collapsed_duplicates": sum(1 for it in items if it.get("dup_collapsed")),
        "commander_rationale": [],  # populated below if commander present
    }
    # Structured commander overlap & diversity rationale (server-side)
    try:
        if commander_key:
            rationale: List[Dict[str, Any]] = []
            # Factor 1: distinct synergy overlaps contributed by commander vs theme synergies
            # Recompute overlap metrics cheaply from sample items
            overlap_set = set()
            overlap_counts = 0
            for it in items:
                if not it.get("tags"):
                    continue
                tags_set = set(it.get("tags") or [])
                ov = tags_set.intersection(synergies_used)
                for s in ov:
                    overlap_set.add(s)
                overlap_counts += len(ov)
            total_real = max(1, sum(1 for it in items if (it.get("roles") and it["roles"][0] in sampled_core_roles)))
            avg_overlap = overlap_counts / total_real
            rationale.append({
                "id": "synergy_spread",
                "label": "Distinct synergy overlaps",
                "value": len(overlap_set),
                "detail": sorted(overlap_set)[:12],
            })
            rationale.append({
                "id": "avg_overlap_per_card",
                "label": "Average overlaps per card",
                "value": round(avg_overlap, 2),
            })
            # Role diversity heuristic (mirrors client derivation but server authoritative)
            ideal = {"payoff":0.4,"enabler":0.2,"support":0.2,"wildcard":0.2}
            diversity_score = 0.0
            for r, ideal_pct in ideal.items():
                actual = role_counts_local.get(r, 0) / max(1, total_real)
                diversity_score += (1 - abs(actual - ideal_pct))
            diversity_score = (diversity_score / len(ideal)) * 100
            rationale.append({
                "id": "role_diversity_score",
                "label": "Role diversity score",
                "value": round(diversity_score, 1),
            })
            # Commander theme match (if commander matches theme tag we already applied COMMANDER_THEME_MATCH_BONUS)
            if any("commander_theme_match" in (it.get("reasons") or []) for it in items):
                rationale.append({
                    "id": "commander_theme_match",
                    "label": "Commander matches theme",
                    "value": COMMANDER_THEME_MATCH_BONUS,
                })
            # Commander synergy overlap bonuses (aggregate derived from reasons tags)
            overlap_bonus_total = 0.0
            overlap_instances = 0
            for it in items:
                for r in (it.get("reasons") or []):
                    if r.startswith("commander_synergy_overlap:"):
                        parts = r.split(":")
                        if len(parts) >= 3:
                            try:
                                bonus = float(parts[2])
                                overlap_bonus_total += bonus
                                overlap_instances += 1
                            except Exception:
                                pass
            if overlap_instances:
                rationale.append({
                    "id": "commander_overlap_bonus",
                    "label": "Commander synergy overlap bonus",
                    "value": round(overlap_bonus_total, 2),
                    "instances": overlap_instances,
                    "max_bonus_per_card": COMMANDER_OVERLAP_BONUS,
                })
            # Splash penalty presence (indicates leniency adjustments)
            splash_penalties = 0
            for it in items:
                for r in (it.get("reasons") or []):
                    if r.startswith("splash_off_color_penalty"):
                        splash_penalties += 1
            if splash_penalties:
                rationale.append({
                    "id": "splash_penalties",
                    "label": "Splash leniency adjustments",
                    "value": splash_penalties,
                })
            payload["commander_rationale"] = rationale
    except Exception:
        pass
    store_cache_entry(cache_key, payload, build_ms)
    # Record store attempt metric (errors tracked inside preview_cache write-through silently)
    try:
        if os.getenv("THEME_PREVIEW_REDIS_URL") and not os.getenv("THEME_PREVIEW_REDIS_DISABLE"):
            record_redis_store()
    except Exception:
        pass
    _enforce_cache_limit()

    # Structured logging (diagnostics)
    try:
        if (os.getenv("WEB_THEME_PREVIEW_LOG") or "").lower() in {"1","true","yes","on"}:
            print(json.dumps({
                "event": "theme_preview_build",
                "theme": slug,
                "limit": limit,
                "colors": colors_key,
                "commander": commander_key,
                "build_ms": round(build_ms, 2),
                "curated_pct": payload["curated_pct"],
                "curated_total": curated_count,
                "sampled_total": sampled_count,
                "role_counts": role_counts_local,
                "splash_off_color_cards": splash_off_color_cards,
                "splash_penalty_events": splash_penalty_events,
                "cache_hit": False,
            }, separators=(",",":")))  # noqa: T201
    except Exception:
        pass

    # Adaptive hooks
    maybe_adapt_ttl()
    ensure_bg_thread(_build_hot, _hot_slugs)
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

## preview_metrics now imported from metrics module; re-export via __all__ above.


#############################################
# NOTE: bust_preview_cache re-exported from preview_cache module.
#############################################

# One-time wiring of external accessors for metrics module (idempotent)
_WIRED = False
def _wire_metrics_once() -> None:
    global _WIRED
    if _WIRED:
        return
    try:
        configure_external_access(
            ttl_seconds,
            recent_hit_window,
            lambda: len(PREVIEW_CACHE),
            preview_cache_last_bust_at,
            lambda: _CURATED_SYNERGY_MATRIX is not None,
            lambda: sum(len(v) for v in _CURATED_SYNERGY_MATRIX.values()) if _CURATED_SYNERGY_MATRIX else 0,
        )
        _WIRED = True
    except Exception:
        pass

_wire_metrics_once()
