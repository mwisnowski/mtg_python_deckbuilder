from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import Request
from ..services import owned_store
from . import orchestrator as orch
from deck_builder import builder_constants as bc


def step5_base_ctx(request: Request, sess: dict, *, include_name: bool = True, include_locks: bool = True) -> Dict[str, Any]:
    """Assemble the common Step 5 template context from session.

    Includes commander/tags/bracket/values, ownership flags, owned_set, locks, replace_mode,
    combo preferences, and static game_changers. Caller can layer run-specific results.
    """
    ctx: Dict[str, Any] = {
        "request": request,
        "commander": sess.get("commander"),
        "tags": sess.get("tags", []),
        "bracket": sess.get("bracket"),
        "values": sess.get("ideals", orch.ideal_defaults()),
        "owned_only": bool(sess.get("use_owned_only")),
        "prefer_owned": bool(sess.get("prefer_owned")),
    "owned_set": owned_set(),
        "game_changers": bc.GAME_CHANGERS,
        "replace_mode": bool(sess.get("replace_mode", True)),
        "prefer_combos": bool(sess.get("prefer_combos")),
        "combo_target_count": int(sess.get("combo_target_count", 2)),
        "combo_balance": str(sess.get("combo_balance", "mix")),
    }
    if include_name:
        ctx["name"] = sess.get("custom_export_base")
    if include_locks:
        ctx["locks"] = list(sess.get("locks", []))
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
    )
    if set_on_session:
        sess["build_ctx"] = ctx
    return ctx


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
    ctx: Dict[str, Any] = {
        **base,
        "status": status_text,
        "stage_label": res.get("label"),
        "log": res.get("log_delta", ""),
        "added_cards": res.get("added_cards", []),
        "i": res.get("idx"),
        "n": res.get("total"),
        "csv_path": res.get("csv_path") if done else None,
        "txt_path": res.get("txt_path") if done else None,
        "summary": res.get("summary") if done else None,
        "show_skipped": bool(show_skipped),
        "total_cards": res.get("total_cards"),
        "added_total": res.get("added_total"),
        "mc_adjustments": res.get("mc_adjustments"),
        "clamped_overflow": res.get("clamped_overflow"),
        "mc_summary": res.get("mc_summary"),
        "skipped": bool(res.get("skipped")),
    }
    if extras:
        ctx.update(extras)
    return ctx


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
