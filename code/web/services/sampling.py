"""Sampling utilities extracted from theme_preview (Core Refactor Phase A - initial extraction).

This module contains card index construction and the deterministic sampling
pipeline used to build preview role buckets. Logic moved with minimal changes
to preserve behavior; future refactor steps will further decompose (e.g.,
separating card index & rarity calibration, introducing typed models).

Public (stable) surface for Phase A:
    sample_real_cards_for_theme(theme: str, limit: int, colors_filter: str | None,
                                *, synergies: list[str], commander: str | None) -> list[dict]

Internal helpers intentionally start with an underscore to discourage external
use; they may change in subsequent refactor steps.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, TypedDict

from .card_index import maybe_build_index, get_tag_pool, lookup_commander
from .sampling_config import (
    COMMANDER_COLOR_FILTER_STRICT,
    COMMANDER_OVERLAP_BONUS,
    COMMANDER_THEME_MATCH_BONUS,
    SPLASH_OFF_COLOR_PENALTY,
    SPLASH_ADAPTIVE_ENABLED,
    parse_splash_adaptive_scale,
    ROLE_BASE_WEIGHTS,
    ROLE_SATURATION_PENALTY,
    rarity_weight_base,
    parse_rarity_diversity_targets,
    RARITY_DIVERSITY_OVER_PENALTY,
)


_CARD_INDEX_DEPRECATED: Dict[str, List[Dict[str, Any]]] = {}  # kept for back-compat in tests; will be removed


class SampledCard(TypedDict, total=False):
    """Typed shape for a sampled card entry emitted to preview layer.

    total=False because curated examples / synthetic placeholders may lack
    full DB-enriched fields (mana_cost, rarity, color_identity_list, etc.).
    """
    name: str
    colors: List[str]
    roles: List[str]
    tags: List[str]
    score: float
    reasons: List[str]
    mana_cost: str
    rarity: str
    color_identity_list: List[str]
    pip_colors: List[str]


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
    score += ROLE_BASE_WEIGHTS.get(role, 0.5)
    return score


def _commander_overlap_scale(commander_tags: set[str], card_tags: List[str], synergy_set: set[str]) -> float:
    if not commander_tags or not synergy_set:
        return 0.0
    overlap_synergy = len(commander_tags.intersection(synergy_set).intersection(card_tags))
    if overlap_synergy <= 0:
        return 0.0
    return COMMANDER_OVERLAP_BONUS * (1 - (0.5 ** overlap_synergy))


def _lookup_commander(commander: Optional[str]) -> Optional[Dict[str, Any]]:  # thin wrapper for legacy name
    return lookup_commander(commander)


def sample_real_cards_for_theme(theme: str, limit: int, colors_filter: Optional[str], *, synergies: List[str], commander: Optional[str]) -> List[SampledCard]:
    """Return scored, role-classified real cards for a theme.

    Mirrors prior `_sample_real_cards_for_theme` behavior for parity.
    """
    maybe_build_index()
    pool = get_tag_pool(theme)
    if not pool:
        return []
    commander_card = _lookup_commander(commander)
    commander_colors: set[str] = set(commander_card.get("color_identity", "")) if commander_card else set()
    commander_tags: set[str] = set(commander_card.get("tags", [])) if commander_card else set()
    if colors_filter:
        allowed = {c.strip().upper() for c in colors_filter.split(',') if c.strip()}
        if allowed:
            pool = [c for c in pool if set(c.get("color_identity", "")).issubset(allowed) or not c.get("color_identity")]
    if commander_card and COMMANDER_COLOR_FILTER_STRICT and commander_colors:
        allow_splash = len(commander_colors) >= 4
        new_pool: List[Dict[str, Any]] = []
        for c in pool:
            ci = set(c.get("color_identity", ""))
            if not ci or ci.issubset(commander_colors):
                new_pool.append(c)
                continue
            if allow_splash:
                off = ci - commander_colors
                if len(off) == 1:
                    c["_splash_off_color"] = True  # type: ignore
                    new_pool.append(c)
                    continue
        pool = new_pool
    seen_names: set[str] = set()
    payoff: List[SampledCard] = []
    enabler: List[SampledCard] = []
    support: List[SampledCard] = []
    wildcard: List[SampledCard] = []
    rarity_counts: Dict[str, int] = {}
    rarity_diversity = parse_rarity_diversity_targets()
    synergy_set = set(synergies)
    rarity_weight_cfg = rarity_weight_base()
    splash_scale = parse_splash_adaptive_scale() if SPLASH_ADAPTIVE_ENABLED else None
    commander_color_count = len(commander_colors) if commander_colors else 0
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
            base_rarity_weight = rarity_weight_cfg.get(rarity, 0.25)
            count_so_far = rarity_counts.get(rarity, 0)
            increment_weight = base_rarity_weight / (1 + 0.4 * count_so_far)
            score += increment_weight
            rarity_counts[rarity] = count_so_far + 1
            reasons.append(f"rarity_weight_calibrated:{rarity}:{round(increment_weight,2)}")
            if rarity_diversity and rarity in rarity_diversity:
                lo, hi = rarity_diversity[rarity]
                # Only enforce upper bound (overflow penalty)
                if rarity_counts[rarity] > hi:
                    score += RARITY_DIVERSITY_OVER_PENALTY
                    reasons.append(f"rarity_diversity_overflow:{rarity}:{hi}:{RARITY_DIVERSITY_OVER_PENALTY}")
        if raw.get("_splash_off_color"):
            penalty = SPLASH_OFF_COLOR_PENALTY
            if splash_scale and commander_color_count:
                scale = splash_scale.get(commander_color_count, 1.0)
                adaptive_penalty = round(penalty * scale, 4)
                score += adaptive_penalty
                reasons.append(f"splash_off_color_penalty_adaptive:{commander_color_count}:{adaptive_penalty}")
            else:
                score += penalty  # negative value
                reasons.append(f"splash_off_color_penalty:{penalty}")
        item: SampledCard = {
            "name": nm,
            "colors": list(raw.get("color_identity", "")),
            "roles": [role],
            "tags": tags,
            "score": score,
            "reasons": reasons,
            "mana_cost": raw.get("mana_cost"),
            "rarity": rarity,
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
    seed = _seed_from(theme, commander)
    for bucket in (payoff, enabler, support, wildcard):
        _deterministic_shuffle(bucket, seed)
        bucket.sort(key=lambda x: (-x["score"], x["name"]))
    target_payoff = max(1, int(round(limit * 0.4)))
    target_enabler_support = max(1, int(round(limit * 0.4)))
    target_wild = max(0, limit - target_payoff - target_enabler_support)

    def take(n: int, source: List[SampledCard]):
        for i in range(min(n, len(source))):
            yield source[i]

    chosen: List[SampledCard] = []
    chosen.extend(take(target_payoff, payoff))
    es_combined = enabler + support
    chosen.extend(take(target_enabler_support, es_combined))
    chosen.extend(take(target_wild, wildcard))

    if len(chosen) < limit:
        def fill_from(src: List[SampledCard]):
            nonlocal chosen
            for it in src:
                if len(chosen) >= limit:
                    break
                if it not in chosen:
                    chosen.append(it)
        for bucket in (payoff, enabler, support, wildcard):
            fill_from(bucket)

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
            it["score"] = it.get("score", 0) + ROLE_SATURATION_PENALTY  # negative value
            (it.setdefault("reasons", [])).append(f"role_saturation_penalty:{ROLE_SATURATION_PENALTY}")
    if len(chosen) > limit:
        chosen = chosen[:limit]
    return chosen

# Expose overlap scale for unit tests
commander_overlap_scale = _commander_overlap_scale
