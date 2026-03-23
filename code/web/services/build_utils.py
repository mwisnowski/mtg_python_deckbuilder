from __future__ import annotations

from typing import Any, Dict, Iterable, Optional
from fastapi import Request
from ..services import owned_store
from . import orchestrator as orch
from deck_builder import builder_constants as bc


_TRUE_SET = {"1", "true", "yes", "on", "y", "t"}
_FALSE_SET = {"0", "false", "no", "off", "n", "f"}


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        token = value.strip().lower()
        if not token:
            return default
        if token in _TRUE_SET:
            return True
        if token in _FALSE_SET:
            return False
    try:
        return bool(value)
    except Exception:
        return default


def _app_bool(name: str, default: bool = False) -> bool:
    import os
    import sys

    env_val = os.getenv(name)
    if env_val is not None:
        return _coerce_bool(env_val, default)

    app_module = sys.modules.get("code.web.app")
    if app_module is not None:
        try:
            if hasattr(app_module, name):
                return _coerce_bool(getattr(app_module, name), default)
        except Exception:
            return default

    return default


def step5_base_ctx(request: Request, sess: dict, *, include_name: bool = True, include_locks: bool = True) -> Dict[str, Any]:
    """Assemble the common Step 5 template context from session.

    Includes commander/tags/bracket/values, ownership flags, owned_set, locks, replace_mode,
    combo preferences, and static game_changers. Caller can layer run-specific results.
    """
    include_cards = list(sess.get("include_cards", []) or [])
    exclude_cards = list(sess.get("exclude_cards", []) or [])
    ctx: Dict[str, Any] = {
        "request": request,
        "commander": sess.get("commander"),
        "tags": sess.get("tags", []),
        "bracket": sess.get("bracket"),
        "values": sess.get("ideals", orch.ideal_defaults()),
        "owned_only": bool(sess.get("use_owned_only")),
        "prefer_owned": bool(sess.get("prefer_owned")),
        "partner_enabled": bool(sess.get("partner_enabled")) and _app_bool("ENABLE_PARTNER_MECHANICS", True),
        "secondary_commander": sess.get("secondary_commander"),
        "background": sess.get("background"),
        "partner_mode": sess.get("partner_mode"),
        "partner_warnings": list(sess.get("partner_warnings", []) or []),
        "combined_commander": sess.get("combined_commander"),
        "partner_auto_note": sess.get("partner_auto_note"),
        "owned_set": owned_set(),
        "game_changers": bc.GAME_CHANGERS,
        "replace_mode": bool(sess.get("replace_mode", True)),
        "prefer_combos": bool(sess.get("prefer_combos")),
        "combo_target_count": int(sess.get("combo_target_count", 2)),
        "combo_balance": str(sess.get("combo_balance", "mix")),
        "swap_mdfc_basics": bool(sess.get("swap_mdfc_basics")),
        "allow_must_haves": _app_bool("ALLOW_MUST_HAVES", True),
        "show_must_have_buttons": _app_bool("SHOW_MUST_HAVE_BUTTONS", False),
        "include_cards": include_cards,
        "exclude_cards": exclude_cards,
    }
    if include_name:
        ctx["name"] = sess.get("custom_export_base")
    if include_locks:
        ctx["locks"] = list(sess.get("locks", []))
    try:
        ctx["summary_token"] = int(sess.get("step5_summary_token", 0))
    except Exception:
        ctx["summary_token"] = 0
    ctx["summary_ready"] = bool(sess.get("step5_summary_ready"))
    try:
        raw_synergies = sess.get("step5_synergies")
        if isinstance(raw_synergies, (list, tuple, set)):
            ctx["synergies"] = [str(s) for s in raw_synergies if str(s).strip()]
        else:
            ctx["synergies"] = []
    except Exception:
        ctx["synergies"] = []
    ctx["must_have_state"] = {
        "includes": include_cards,
        "excludes": exclude_cards,
        "enforcement_mode": (sess.get("enforcement_mode") or "warn"),
        "allow_illegal": bool(sess.get("allow_illegal")),
        "fuzzy_matching": bool(sess.get("fuzzy_matching", True)),
    }
    ctx["budget_config"] = sess.get("budget_config") or {}
    ctx["build_id"] = str(sess.get("build_id") or "0")
    try:
        from ..services.price_service import get_price_service
        from code.settings import PRICE_STALE_WARNING_HOURS
        _svc = get_price_service()
        _svc._ensure_loaded()
        ctx["price_cache"] = _svc._cache  # keyed by lowercase card name → {usd, usd_foil, ...}
        _stale = _svc.get_stale_cards(PRICE_STALE_WARNING_HOURS) if PRICE_STALE_WARNING_HOURS > 0 else set()
        # Suppress per-card noise when >50% of the priced pool is stale
        if _stale and len(_stale) > len(_svc._cache) * 0.5:
            ctx["stale_prices"] = set()
            ctx["stale_prices_global"] = True
        else:
            ctx["stale_prices"] = _stale
            ctx["stale_prices_global"] = False
    except Exception:
        ctx["price_cache"] = {}
        ctx["stale_prices"] = set()
        ctx["stale_prices_global"] = False
    return ctx


def owned_set() -> set[str]:
    """Return lowercase owned card names with trimming for robust matching."""
    try:
        return {str(n).strip().lower() for n in owned_store.get_names()}
    except Exception:
        return set()


def owned_names() -> list[str]:
    """Return raw owned card names from the store (original casing)."""
    try:
        return list(owned_store.get_names())
    except Exception:
        return []


def start_ctx_from_session(sess: dict, *, set_on_session: bool = True) -> Dict[str, Any]:
    """Create a staged build context from the current session selections.

    Pulls commander, tags, bracket, ideals, tag_mode, ownership flags, locks, custom name,
    multi-copy selection, and combo preferences from the session and starts a build context.
    """
    opts = orch.bracket_options()
    default_bracket = (opts[0]["level"] if opts else 1)
    bracket_val = sess.get("bracket")
    try:
        safe_bracket = int(bracket_val) if bracket_val is not None else int(default_bracket)
    except Exception:
        safe_bracket = int(default_bracket)
    ideals_val = sess.get("ideals") or orch.ideal_defaults()
    use_owned = bool(sess.get("use_owned_only"))
    prefer = bool(sess.get("prefer_owned"))
    owned_names_list = owned_names() if (use_owned or prefer) else None
    partner_enabled = bool(sess.get("partner_enabled")) and _app_bool("ENABLE_PARTNER_MECHANICS", True)
    secondary_commander = sess.get("secondary_commander") if partner_enabled else None
    background_choice = sess.get("background") if partner_enabled else None
    ctx = orch.start_build_ctx(
        commander=sess.get("commander"),
        tags=sess.get("tags", []),
        bracket=safe_bracket,
        ideals=ideals_val,
        tag_mode=sess.get("tag_mode", "AND"),
        use_owned_only=use_owned,
        prefer_owned=prefer,
        owned_names=owned_names_list,
        locks=list(sess.get("locks", [])),
        custom_export_base=sess.get("custom_export_base"),
        multi_copy=sess.get("multi_copy"),
        prefer_combos=bool(sess.get("prefer_combos")),
        combo_target_count=int(sess.get("combo_target_count", 2)),
        combo_balance=str(sess.get("combo_balance", "mix")),
        include_cards=sess.get("include_cards"),
        exclude_cards=sess.get("exclude_cards"),
        swap_mdfc_basics=bool(sess.get("swap_mdfc_basics")),
        partner_feature_enabled=partner_enabled,
        secondary_commander=secondary_commander,
        background_commander=background_choice,
        budget_config=sess.get("budget_config"),
    )
    if set_on_session:
        sess["build_ctx"] = ctx
    if partner_enabled:
        ctx["partner_mode"] = sess.get("partner_mode")
        ctx["combined_commander"] = sess.get("combined_commander")
        ctx["partner_warnings"] = list(sess.get("partner_warnings", []) or [])
    # M2: Attach session reference to context for skip controls
    ctx["session"] = sess
    return ctx


def _extend_sources(target: list[Any], values: Any) -> None:
    if not values:
        return
    if isinstance(values, (list, tuple, set)):
        for item in values:
            if item is None:
                continue
            target.append(item)
    else:
        target.append(values)


def commander_hover_context(
    commander_name: str | None,
    deck_tags: Iterable[Any] | None,
    summary: Dict[str, Any] | None,
    combined: Any | None = None,
) -> Dict[str, Any]:
    try:
        from .summary_utils import format_theme_label, format_theme_list
    except Exception:
        # Fallbacks in the unlikely event of circular import issues
        def format_theme_label(value: Any) -> str:
            text = str(value or "").strip().replace("_", " ")
            if not text:
                return ""
            parts = []
            for chunk in text.split():
                if chunk.isupper():
                    parts.append(chunk)
                else:
                    parts.append(chunk[:1].upper() + chunk[1:].lower())
            return " ".join(parts)

        def format_theme_list(values: Iterable[Any]) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for raw in values or []:
                label = format_theme_label(raw)
                if not label or len(label) <= 1:
                    continue
                key = label.casefold()
                if key in seen:
                    continue
                seen.add(key)
                result.append(label)
            return result

    combined_info: Dict[str, Any]
    if isinstance(combined, dict):
        combined_info = combined
    else:
        combined_info = {}
    has_combined = bool(combined_info)

    deck_theme_sources: list[Any] = []
    _extend_sources(deck_theme_sources, list(deck_tags or []))
    meta_info: Dict[str, Any] = {}
    if isinstance(summary, dict):
        meta_info = summary.get("meta") or {}
        if isinstance(meta_info, dict):
            for key in (
                "display_themes",
                "resolved_themes",
                "auto_filled_themes",
                "random_display_themes",
                "random_resolved_themes",
                "random_auto_filled_themes",
                "primary_theme",
                "secondary_theme",
                "tertiary_theme",
            ):
                _extend_sources(deck_theme_sources, meta_info.get(key))
    deck_theme_tags = format_theme_list(deck_theme_sources)

    commander_theme_sources: list[Any] = []
    if isinstance(meta_info, dict):
        for key in (
            "commander_tags",
            "commander_theme_tags",
            "commander_themes",
            "commander_tag_list",
            "primary_commander_theme",
            "secondary_commander_theme",
        ):
            _extend_sources(commander_theme_sources, meta_info.get(key))
        commander_meta = meta_info.get("commander") if isinstance(meta_info, dict) else {}
        if isinstance(commander_meta, dict):
            _extend_sources(commander_theme_sources, commander_meta.get("tags"))
            _extend_sources(commander_theme_sources, commander_meta.get("themes"))

    _extend_sources(commander_theme_sources, combined_info.get("theme_tags"))

    commander_theme_tags = format_theme_list(commander_theme_sources)
    if commander_name and not commander_theme_tags:
        try:
            commander_theme_tags = format_theme_list(orch.tags_for_commander(commander_name))
        except Exception:
            commander_theme_tags = []

    combined_tags: list[str] = []
    combined_seen: set[str] = set()
    for source in (commander_theme_tags, deck_theme_tags):
        for label in source:
            key = label.casefold()
            if key in combined_seen:
                continue
            combined_seen.add(key)
            combined_tags.append(label)

    overlap_tags: list[str] = []
    overlap_seen: set[str] = set()
    combined_keys = {label.casefold() for label in combined_tags}
    for label in deck_theme_tags:
        key = label.casefold()
        if key in combined_keys and key not in overlap_seen:
            overlap_tags.append(label)
            overlap_seen.add(key)

    commander_tag_slugs: list[str] = []
    slug_seen: set[str] = set()
    for label in combined_tags:
        slug = " ".join(str(label or "").strip().lower().split())
        if not slug or slug in slug_seen:
            continue
        slug_seen.add(slug)
        commander_tag_slugs.append(slug)

    raw_color_identity = combined_info.get("color_identity") if combined_info else None
    commander_color_identity: list[str] = []
    
    # If we have a combined commander (partner/background), use its color identity
    if isinstance(raw_color_identity, (list, tuple, set)):
        for item in raw_color_identity:
            token = str(item).strip().upper()
            if token:
                commander_color_identity.append(token)
    
    # For regular commanders (no partner/background), look up from commander catalog first
    if not commander_color_identity and not has_combined and commander_name:
        try:
            from .commander_catalog_loader import find_commander_record
            record = find_commander_record(commander_name)
            if record and hasattr(record, 'color_identity'):
                raw_ci = record.color_identity
                if isinstance(raw_ci, (list, tuple, set)):
                    for item in raw_ci:
                        token = str(item).strip().upper()
                        if token:
                            commander_color_identity.append(token)
        except Exception:
            pass
    
    # Fallback: check summary.colors if we still don't have color identity
    if not commander_color_identity and not has_combined and isinstance(summary, dict):
        summary_colors = summary.get("colors")
        if isinstance(summary_colors, (list, tuple, set)):
            for item in summary_colors:
                token = str(item).strip().upper()
                if token:
                    commander_color_identity.append(token)

    commander_color_label = ""
    if has_combined:
        commander_color_label = str(combined_info.get("color_label") or "").strip()
    if not commander_color_label and commander_color_identity:
        commander_color_label = " / ".join(commander_color_identity)
    # M5: Set colorless label for ANY commander with empty color identity (not just partner/combined)
    if not commander_color_label and (has_combined or commander_name):
        # Empty color_identity list means colorless
        if not commander_color_identity:
            commander_color_label = "Colorless (C)"

    commander_color_code = str(combined_info.get("color_code") or "").strip() if has_combined else ""
    commander_partner_mode = str(combined_info.get("partner_mode") or "").strip() if has_combined else ""
    commander_secondary_name = str(combined_info.get("secondary_name") or "").strip() if has_combined else ""
    commander_primary_name = str(combined_info.get("primary_name") or commander_name or "").strip()

    commander_display_name = commander_primary_name
    if commander_secondary_name:
        if commander_partner_mode == "background":
            commander_display_name = f"{commander_primary_name} + Background: {commander_secondary_name}".strip()
        else:
            commander_display_name = f"{commander_primary_name} + {commander_secondary_name}".strip()
    elif not commander_display_name:
        commander_display_name = str(commander_name or "").strip()

    reason_bits: list[str] = []
    if deck_theme_tags:
        reason_bits.append("Deck themes: " + ", ".join(deck_theme_tags))
    if commander_theme_tags:
        reason_bits.append("Commander tags: " + ", ".join(commander_theme_tags))

    return {
        "deck_theme_tags": deck_theme_tags,
        "commander_theme_tags": commander_theme_tags,
        "commander_combined_tags": combined_tags,
        "commander_tag_slugs": commander_tag_slugs,
        "commander_overlap_tags": overlap_tags,
        "commander_reason_text": "; ".join(reason_bits),
        "commander_role_label": format_theme_label("Commander") if commander_name else "",
        "commander_color_identity": commander_color_identity,
        "commander_color_label": commander_color_label,
        "commander_color_code": commander_color_code,
        "commander_partner_mode": commander_partner_mode,
        "commander_secondary_name": commander_secondary_name,
        "commander_primary_name": commander_primary_name,
        "commander_display_name": commander_display_name,
    }


def step5_ctx_from_result(
    request: Request,
    sess: dict,
    res: dict,
    *,
    status_text: Optional[str] = None,
    show_skipped: bool = False,
    include_name: bool = True,
    include_locks: bool = True,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Step 5 context by merging base session data with a build stage result dict.

    res is expected to be the dict returned from orchestrator.run_stage or similar with keys like
    label, log_delta, added_cards, idx, total, csv_path, txt_path, summary, etc.
    """
    base = step5_base_ctx(request, sess, include_name=include_name, include_locks=include_locks)
    done = bool(res.get("done"))
    include_lower = {str(name).strip().lower(): str(name) for name in (sess.get("include_cards") or []) if str(name).strip()}
    exclude_lower = {str(name).strip().lower(): str(name) for name in (sess.get("exclude_cards") or []) if str(name).strip()}

    raw_added = list(res.get("added_cards", []) or [])
    normalized_added: list[dict[str, Any]] = []
    for item in raw_added:
        if isinstance(item, dict):
            entry: dict[str, Any] = dict(item)
        else:
            entry = {}
            try:
                entry.update(vars(item))
            except Exception:
                pass
            # Preserve common attributes when vars() empty
            for attr in ("name", "role", "sub_role", "tags", "tags_slug", "reason", "count"):
                if attr not in entry and hasattr(item, attr):
                    try:
                        entry[attr] = getattr(item, attr)
                    except Exception:
                        continue
        name_val = str(entry.get("name") or "").strip()
        key = name_val.lower()
        entry["name"] = name_val
        entry["must_include"] = key in include_lower
        entry["must_exclude"] = key in exclude_lower
        entry["must_include_label"] = include_lower.get(key)
        entry["must_exclude_label"] = exclude_lower.get(key)
        normalized_added.append(entry)

    ctx: Dict[str, Any] = {
        **base,
        "status": status_text,
        "stage_label": res.get("label"),
        "log": res.get("log_delta", ""),
        "added_cards": normalized_added,
        "i": res.get("idx"),
        "n": res.get("total"),
        "csv_path": res.get("csv_path") if done else None,
        "txt_path": res.get("txt_path") if done else None,
        "summary": res.get("summary") if done else None,
        "compliance": res.get("compliance") if done else None,
        "show_skipped": bool(show_skipped),
        "total_cards": res.get("total_cards"),
        "added_total": res.get("added_total"),
        "mc_adjustments": res.get("mc_adjustments"),
        "clamped_overflow": res.get("clamped_overflow"),
        "mc_summary": res.get("mc_summary"),
        "skipped": bool(res.get("skipped")),
        "gated": bool(res.get("gated")),
    }
    if extras:
        ctx.update(extras)

    hover_meta = commander_hover_context(
        commander_name=ctx.get("commander"),
        deck_tags=sess.get("tags"),
        summary=ctx.get("summary") if ctx.get("summary") else res.get("summary"),
        combined=ctx.get("combined_commander"),
    )
    ctx.update(hover_meta)
    if "commander_display_name" not in ctx or not ctx.get("commander_display_name"):
        ctx["commander_display_name"] = ctx.get("commander")

    try:
        token_val = int(sess.get("step5_summary_token", 0))
    except Exception:
        token_val = 0
    summary_value = ctx.get("summary")
    synergies_list: list[str] = []
    if summary_value is not None:
        try:
            sess["step5_summary"] = summary_value
        except Exception:
            pass
        if isinstance(summary_value, dict):
            raw_synergies = summary_value.get("synergies")
            if isinstance(raw_synergies, (list, tuple, set)):
                synergies_list = [str(item) for item in raw_synergies if str(item).strip()]
            else:
                meta = summary_value.get("meta") if isinstance(summary_value.get("meta"), dict) else {}
                if isinstance(meta, dict):
                    raw_synergies = meta.get("synergies") or meta.get("commander_synergies")
                    if isinstance(raw_synergies, (list, tuple, set)):
                        synergies_list = [str(item) for item in raw_synergies if str(item).strip()]
        token_val += 1
        sess["step5_summary_token"] = token_val
        sess["step5_summary_ready"] = True
        if synergies_list:
            sess["step5_synergies"] = synergies_list
        else:
            try:
                if "step5_synergies" in sess:
                    del sess["step5_synergies"]
            except Exception:
                pass
    else:
        token_val += 1
        sess["step5_summary_token"] = token_val
        sess["step5_summary_ready"] = False
        try:
            if "step5_summary" in sess:
                del sess["step5_summary"]
        except Exception:
            pass
        try:
            if "step5_synergies" in sess:
                del sess["step5_synergies"]
        except Exception:
            pass
        synergies_list = []
    ctx["summary_token"] = token_val
    ctx["summary_ready"] = bool(sess.get("step5_summary_ready"))
    ctx["synergies"] = synergies_list

    # M5: Post-build budget review (only when build is done and budget mode active)
    if done:
        try:
            _apply_budget_review_ctx(sess, res, ctx)
        except Exception:
            ctx.setdefault("over_budget_review", False)
            ctx.setdefault("budget_review_visible", False)
            ctx.setdefault("price_category_chart", None)
            ctx.setdefault("price_histogram_chart", None)
    else:
        ctx.setdefault("over_budget_review", False)
        ctx.setdefault("budget_review_visible", False)
        ctx.setdefault("price_category_chart", None)
        ctx.setdefault("price_histogram_chart", None)

    return ctx


def _apply_budget_review_ctx(sess: dict, res: dict, ctx: dict) -> None:
    """M5: Compute end-of-build budget review data and inject into ctx.

    Triggers when total deck cost exceeds budget_total by more than BUDGET_TOTAL_TOLERANCE.
    Shows the most expensive non-include cards (contributors to total overage) with
    cheaper alternatives drawn from find_cheaper_alternatives().
    """
    budget_cfg = sess.get("budget_config") or {}
    try:
        budget_total = float(budget_cfg.get("total") or 0)
    except Exception:
        budget_total = 0.0
    if budget_total <= 0:
        ctx["over_budget_review"] = False
        return

    budget_mode = "soft"
    try:
        card_ceiling = float(budget_cfg.get("card_ceiling")) if budget_cfg.get("card_ceiling") else None
    except Exception:
        card_ceiling = None
    include_cards = [str(c).strip() for c in (sess.get("include_cards") or []) if str(c).strip()]

    # Extract card names from build summary + build name -> {type, role, tags} lookup
    summary = res.get("summary") or {}
    card_names: list[str] = []
    card_meta: dict[str, dict] = {}
    if isinstance(summary, dict):
        tb = summary.get("type_breakdown") or {}
        for type_key, type_cards_list in (tb.get("cards") or {}).items():
            for c in type_cards_list:
                name = c.get("name") if isinstance(c, dict) else None
                if name:
                    sname = str(name).strip()
                    card_names.append(sname)
                    card_meta[sname] = {
                        "type": type_key,
                        "role": str(c.get("role") or "").strip(),
                        "tags": list(c.get("tags") or []),
                    }

    if not card_names:
        ctx["over_budget_review"] = False
        return

    # Persist snapshot for the swap route
    sess["budget_deck_snapshot"] = list(card_names)

    color_identity: list[str] | None = None
    try:
        ci_raw = sess.get("color_identity")
        if ci_raw and isinstance(ci_raw, list):
            color_identity = [str(c).upper() for c in ci_raw]
    except Exception:
        pass

    from ..services.budget_evaluator import BudgetEvaluatorService
    svc = BudgetEvaluatorService()
    report = svc.evaluate_deck(
        card_names,
        budget_total,
        mode=budget_mode,
        card_ceiling=card_ceiling,
        include_cards=include_cards,
        color_identity=color_identity,
    )

    total_price = float(report.get("total_price", 0.0))
    tolerance = bc.BUDGET_TOTAL_TOLERANCE
    over_budget_review = total_price > budget_total * (1.0 + tolerance)

    ctx["budget_review_visible"] = over_budget_review  # only shown when deck total exceeds tolerance
    ctx["over_budget_review"] = over_budget_review
    ctx["budget_review_total"] = round(total_price, 2)
    ctx["budget_review_cap"] = round(budget_total, 2)
    ctx["budget_overage_pct"] = 0.0
    ctx["over_budget_cards"] = []

    overage = total_price - budget_total
    if over_budget_review:
        ctx["budget_overage_pct"] = round(overage / budget_total * 100, 1)

    include_set = {c.lower().strip() for c in include_cards}

    # Use price_breakdown sorted by price desc — most expensive cards are the biggest
    # contributors to the total overage regardless of any per-card ceiling.
    breakdown = report.get("price_breakdown") or []
    priced = sorted(
        [e for e in breakdown
         if not e.get("is_include") and (e.get("price") is not None) and float(e.get("price") or 0.0) > 0],
        key=lambda x: -float(x.get("price") or 0.0),
    )

    over_cards_out: list[dict] = []
    for entry in priced[:6]:
        name = entry.get("card", "")
        price = float(entry.get("price") or 0.0)
        is_include = name.lower().strip() in include_set
        meta = card_meta.get(name, {})
        try:
            # Any cheaper alternative reduces the total; use price - 0.01 as the ceiling
            alts_raw = svc.find_cheaper_alternatives(
                name,
                max_price=max(0.0, price - 0.01),
                region="usd",
                color_identity=color_identity,
                tags=meta.get("tags") or None,
                require_type=meta.get("type") or None,
            )
        except Exception:
            alts_raw = []
        over_cards_out.append({
            "name": name,
            "price": price,
            "swap_disabled": is_include,
            "card_type": meta.get("type", ""),
            "card_role": meta.get("role", ""),
            "card_tags": meta.get("tags", []),
            "alternatives": [
                {"name": a["name"], "price": a.get("price"), "shared_tags": a.get("shared_tags", [])}
                for a in alts_raw[:3]
            ],
        })

    ctx["over_budget_cards"] = over_cards_out

    # M8: Price charts — category breakdown + histogram
    try:
        from ..services.budget_evaluator import compute_price_category_breakdown, compute_price_histogram
        _breakdown = report.get("price_breakdown") or []
        _enriched = [
            {**item, "tags": card_meta.get(item.get("card", ""), {}).get("tags", [])}
            for item in _breakdown
        ]
        ctx["price_category_chart"] = compute_price_category_breakdown(_enriched)
        ctx["price_histogram_chart"] = compute_price_histogram(_breakdown)
    except Exception:
        ctx.setdefault("price_category_chart", None)
        ctx.setdefault("price_histogram_chart", None)


def step5_error_ctx(
    request: Request,
    sess: dict,
    message: str,
    *,
    include_name: bool = True,
    include_locks: bool = True,
    status_text: str = "Error",
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a normalized Step 5 context for error states.

    Provides all keys expected by the _step5.html template so the UI stays consistent
    even when a build can't start or a stage fails. The error message is placed in `log`.
    """
    base = step5_base_ctx(request, sess, include_name=include_name, include_locks=include_locks)
    ctx: Dict[str, Any] = {
        **base,
        "status": status_text,
        "stage_label": None,
        "log": str(message),
        "added_cards": [],
        "i": None,
        "n": None,
        "csv_path": None,
        "txt_path": None,
        "summary": None,
        "show_skipped": False,
        "total_cards": None,
        "added_total": 0,
        "skipped": False,
    }
    try:
        token_val = int(sess.get("step5_summary_token", 0)) + 1
    except Exception:
        token_val = 1
    sess["step5_summary_token"] = token_val
    sess["step5_summary_ready"] = False
    try:
        if "step5_summary" in sess:
            del sess["step5_summary"]
    except Exception:
        pass
    try:
        if "step5_synergies" in sess:
            del sess["step5_synergies"]
    except Exception:
        pass
    ctx["summary_token"] = token_val
    ctx["summary_ready"] = False
    ctx["synergies"] = []
    if extras:
        ctx.update(extras)
    return ctx


def step5_empty_ctx(
    request: Request,
    sess: dict,
    *,
    include_name: bool = True,
    include_locks: bool = True,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a baseline Step 5 context with empty stage data.

    Used for GET /step5 and reset-stage flows to render the screen before any stage is run.
    """
    base = step5_base_ctx(request, sess, include_name=include_name, include_locks=include_locks)
    ctx: Dict[str, Any] = {
        **base,
        "status": None,
        "stage_label": None,
        "log": None,
        "added_cards": [],
        "i": None,
        "n": None,
        "total_cards": None,
        "added_total": 0,
        "show_skipped": False,
        "skipped": False,
    }
    try:
        token_val = int(sess.get("step5_summary_token", 0)) + 1
    except Exception:
        token_val = 1
    sess["step5_summary_token"] = token_val
    sess["step5_summary_ready"] = False
    try:
        if "step5_summary" in sess:
            del sess["step5_summary"]
    except Exception:
        pass
    try:
        if "step5_synergies" in sess:
            del sess["step5_synergies"]
    except Exception:
        pass
    ctx["summary_token"] = token_val
    ctx["summary_ready"] = False
    ctx["synergies"] = []
    if extras:
        ctx.update(extras)
    return ctx


def builder_present_names(builder: Any) -> set[str]:
    """Return a lowercase set of names currently present in the builder/deck structures.

    Safely probes a variety of attributes used across different builder implementations.
    """
    present: set[str] = set()
    def _add_names(x: Any) -> None:
        try:
            if not x:
                return
            if isinstance(x, dict):
                for k, v in x.items():
                    if isinstance(k, str) and k.strip():
                        present.add(k.strip().lower())
                    elif isinstance(v, dict) and v.get('name'):
                        present.add(str(v.get('name')).strip().lower())
            elif isinstance(x, (list, tuple, set)):
                for item in x:
                    if isinstance(item, str) and item.strip():
                        present.add(item.strip().lower())
                    elif isinstance(item, dict) and item.get('name'):
                        present.add(str(item.get('name')).strip().lower())
                    else:
                        try:
                            nm = getattr(item, 'name', None)
                            if isinstance(nm, str) and nm.strip():
                                present.add(nm.strip().lower())
                        except Exception:
                            pass
        except Exception:
            pass
    try:
        if builder is None:
            return present
        for attr in (
            'current_deck', 'deck', 'final_deck', 'final_cards',
            'chosen_cards', 'selected_cards', 'picked_cards', 'cards_in_deck',
        ):
            _add_names(getattr(builder, attr, None))
        # Also include names present in the library itself, which is the authoritative deck source post-build
        try:
            lib = getattr(builder, 'card_library', None)
            if isinstance(lib, dict) and lib:
                for k in lib.keys():
                    if isinstance(k, str) and k.strip():
                        present.add(k.strip().lower())
        except Exception:
            pass
        for attr in ('current_names', 'deck_names', 'final_names'):
            val = getattr(builder, attr, None)
            if isinstance(val, (list, tuple, set)):
                for n in val:
                    if isinstance(n, str) and n.strip():
                        present.add(n.strip().lower())
    except Exception:
        pass
    return present


def builder_display_map(builder: Any, pool_lower: set[str]) -> Dict[str, str]:
    """Map lowercased names in pool_lower to display names using the combined DataFrame, if present."""
    display_map: Dict[str, str] = {}
    try:
        if builder is None or not pool_lower:
            return display_map
        df = getattr(builder, "_combined_cards_df", None)
        if df is not None and not df.empty:
            sub = df[df["name"].astype(str).str.lower().isin(pool_lower)]
            for _idx, row in sub.iterrows():
                display_map[str(row["name"]).strip().lower()] = str(row["name"]).strip()
    except Exception:
        display_map = {}
    return display_map
