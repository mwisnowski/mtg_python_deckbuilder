"""Deck-build endpoints for the public REST API (R28 Milestone 3).

Reuses the same staged build engine (`start_build_ctx` / `run_stage`) as the
HTML/HTMX web UI, but tracks progress in `api_build_store.py` keyed by a
`build_id` (not a cookie session), and runs stages in a worker thread so the
event loop isn't blocked while a build is in progress.

Auth required for every endpoint here -- the public API never creates guest
builds (see roadmap_28_public_api.md's Milestone 3 note). Builds are only
visible to the user who created them.

Known limitation: `seed` is accepted but not yet wired up -- the staged
build engine (`start_build_ctx`) has no deterministic-seed support today;
that lives in a separate subsystem (`random_util.py`) used only by the
"Random build" feature. Revisit if/when that's unified.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from code.deck_builder.builder import DeckBuilder
from code.deck_builder import builder_utils as bu
from code.type_definitions import User

from ...services import api_alternatives
from ...services import api_build_store as build_store
from ...services import orchestrator as orch
from ...services.build_utils import owned_names as owned_names_helper
from ...utils.api_response import err, ok
from ..decks import _deck_dir
from .auth import get_api_user

router = APIRouter(prefix="/builds", tags=["builds"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


class CreateBuildRequest(BaseModel):
    commander: str
    themes: List[str] = Field(default_factory=list)
    bracket: Optional[int] = None
    budget: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    owned_only: bool = False
    prefer_owned: bool = False
    # "auto" runs every stage immediately in the background (default, unchanged
    # behavior). "guided" stops after each stage so a client can review/swap
    # cards via POST /{build_id}/advance before continuing.
    mode: str = "auto"
    # Multi-copy "package" selection, e.g. {"id": "hare_apparent", "name": "Hare
    # Apparent", "count": 25}. See GET /builds/multi-copy-options for viable
    # choices for a given commander/themes.
    multi_copy: Optional[Dict[str, Any]] = None
    # Any subset of the ideal-count categories (ramp, lands, basic_lands,
    # creatures, removal, wipes, card_advantage, protection). Missing keys
    # fall back to the server defaults (see GET /builds/ideal-defaults).
    ideal_counts: Optional[Dict[str, int]] = None
    include_cards: Optional[List[str]] = None
    exclude_cards: Optional[List[str]] = None


class ReplaceCardRequest(BaseModel):
    old_name: str
    new_name: str


class RemoveCardRequest(BaseModel):
    name: str


def _default_bracket() -> int:
    opts = orch.bracket_options()
    return int(opts[0]["level"]) if opts else 1


def _status_payload(build: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "status": build.get("status"),
        "progress_pct": build.get("progress_pct", 0),
        "stage_label": build.get("stage_label"),
    }
    if build.get("status") == "error":
        payload["error"] = build.get("error")
    return payload


def _run_build_sync(build_id: str, ctx: Dict[str, Any]) -> None:
    """Run every remaining stage to completion. Executed in a worker thread."""
    build_store.update_progress(build_id, status="running")
    try:
        stages = ctx["stages"]
        while ctx["idx"] < len(stages):
            result = orch.run_stage(ctx)
            build_store.update_progress(
                build_id,
                stage_idx=result.get("idx", ctx["idx"]),
                stage_total=result.get("total", len(stages)),
                stage_label=result.get("label"),
            )
            if result.get("gated"):
                # Compliance gating (see run_stage's bracket-FAIL branch)
                # holds ctx["idx"] in place so a human can review/adjust via
                # guided mode. Auto mode has no reviewer, so accept the
                # stage's result and advance past the gate instead of
                # looping forever re-checking the same stage.
                ctx.pop("gating", None)
                ctx["idx"] = int(result.get("idx", ctx["idx"]))
                continue
            if result.get("done"):
                build_store.mark_done(
                    build_id,
                    {
                        "csv_path": result.get("csv_path"),
                        "txt_path": result.get("txt_path"),
                        "summary": result.get("summary"),
                        "compliance": result.get("compliance"),
                        "include_exclude_diagnostics": result.get("include_exclude_diagnostics"),
                    },
                )
                return
    except Exception as exc:  # noqa: BLE001 -- surfaced to the client via the store
        build_store.mark_error(build_id, str(exc))


@router.post("", summary="Create a deck build")
async def create_build(body: CreateBuildRequest, request: Request, user: User = Depends(get_api_user)):
    """Start a new deck build. Returns immediately with a `build_id` to poll.

    `mode="guided"` skips the automatic background run; call
    `POST /{build_id}/advance` repeatedly to step through stages instead.
    """
    commander = body.commander.strip()
    if not commander:
        return err("commander is required.", "INVALID_COMMANDER", 400, _rid(request))
    if body.mode not in ("auto", "guided"):
        return err("mode must be 'auto' or 'guided'.", "INVALID_MODE", 400, _rid(request))
    bracket = body.bracket if body.bracket is not None else _default_bracket()

    owned_names_list = owned_names_helper() if (body.owned_only or body.prefer_owned) else None

    deck_dir = str(_deck_dir(str(user["id"])))

    ideals = orch.ideal_defaults()
    if body.ideal_counts:
        ideals.update({k: int(v) for k, v in body.ideal_counts.items()})

    try:
        ctx = await asyncio.to_thread(
            orch.start_build_ctx,
            commander=commander,
            tags=body.themes,
            bracket=bracket,
            ideals=ideals,
            use_owned_only=body.owned_only,
            prefer_owned=body.prefer_owned,
            owned_names=owned_names_list,
            budget_config=body.budget,
            deck_dir=deck_dir,
            multi_copy=body.multi_copy,
            include_cards=body.include_cards,
            exclude_cards=body.exclude_cards,
        )
    except ValueError as exc:
        return err(str(exc), "INVALID_BUILD_REQUEST", 400, _rid(request))
    except RuntimeError as exc:
        return err(str(exc), "SETUP_NOT_READY", 503, _rid(request))

    build_id = build_store.create_build(user["id"], body.model_dump())

    if body.mode == "guided":
        build_store.set_ctx(build_id, ctx)
        stage_total = len(ctx.get("stages", []))
        build_store.update_progress(build_id, status="ready", stage_idx=0, stage_total=stage_total)
        return ok(
            {"build_id": build_id, "status": "ready", "mode": "guided", "stage_total": stage_total},
            _rid(request),
            status_code=201,
        )

    asyncio.create_task(asyncio.to_thread(_run_build_sync, build_id, ctx))
    return ok({"build_id": build_id, "status": "queued"}, _rid(request), status_code=202)


def _detect_multi_copy_options_sync(commander: str, themes: List[str]) -> List[Dict[str, Any]]:
    """Lightweight, no-data-load detection of viable multi-copy packages.

    Mirrors `build_multicopy.py`'s `/multicopy/check` route (used by the HTML
    web UI), just without the session/HTML-modal plumbing.
    """
    tmp = DeckBuilder(output_func=lambda *_: None, input_func=lambda *_: "", headless=True)
    df = tmp.load_commander_data()
    row = df[df["name"].astype(str) == commander]
    if row.empty:
        raise ValueError(f"Commander not found: {commander}")
    tmp._apply_commander_selection(row.iloc[0])
    tmp.selected_tags = list(themes or [])
    tmp.determine_color_identity()
    return bu.detect_viable_multi_copy_archetypes(tmp) or []


@router.get("/multi-copy-options", summary="Suggest multi-copy packages")
async def get_multi_copy_options(
    commander: str,
    request: Request,
    themes: str = "",
    user: User = Depends(get_api_user),
):
    """Viable multi-copy "package" archetypes (Relentless Rats, Hare Apparent,
    etc.) for a commander/theme combo, for use as `multi_copy` in
    `POST /builds`. Empty list means none apply.
    """
    theme_list = [t.strip() for t in themes.split(",") if t.strip()]
    try:
        items = await asyncio.to_thread(_detect_multi_copy_options_sync, commander.strip(), theme_list)
    except ValueError as exc:
        return err(str(exc), "INVALID_COMMANDER", 400, _rid(request))
    return ok({"items": items}, _rid(request))


@router.get("/ideal-defaults", summary="Get default ideal counts")
async def get_ideal_defaults(request: Request, user: User = Depends(get_api_user)):
    """Server-side defaults for the `ideal_counts` field of `POST /builds`
    (ramp, lands, basic_lands, creatures, removal, wipes, card_advantage,
    protection). Use these to pre-fill an editable form.
    """
    return ok({"defaults": orch.ideal_defaults(), "labels": orch.ideal_labels()}, _rid(request))


@router.get("/{build_id}", summary="Get build status")
async def get_build_status(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Poll build status and progress."""
    build = build_store.get_build(build_id)
    if not build or build.get("user_id") != user["id"]:
        return err("Build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    return ok(_status_payload(build), _rid(request))


@router.get("/{build_id}/deck", summary="Get finished deck")
async def get_build_deck(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Fetch the full deck JSON once a build has finished."""
    build = build_store.get_build(build_id)
    if not build or build.get("user_id") != user["id"]:
        return err("Build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    status = build.get("status")
    if status == "error":
        return err(build.get("error") or "Build failed.", "BUILD_FAILED", 409, _rid(request))
    if status != "done":
        return err("Build is not complete yet.", "BUILD_NOT_READY", 409, _rid(request))
    return ok(build.get("result") or {}, _rid(request))


def _guided_build_or_none(build_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    build = build_store.get_build(build_id)
    if not build or build.get("user_id") != user_id:
        return None
    if (build.get("config") or {}).get("mode") != "guided":
        return None
    return build


def _run_stage_sync(ctx: Dict[str, Any], lock, *, rerun: bool = False, replace: bool = False) -> Dict[str, Any]:
    with lock:
        return orch.run_stage(ctx, rerun=rerun, show_skipped=False, replace=replace)


def _finalize_stage_result(build_id: str, ctx: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Update the build store from a `run_stage` result and build the API payload.

    Shared by `advance` (next stage) and `rerun` (re-draw the current stage).
    """
    stage_total = int(result.get("total") or len(ctx.get("stages", [])) or 0)
    stage_idx = int(result.get("idx") or 0)
    done = bool(result.get("done"))
    if done:
        build_store.mark_done(
            build_id,
            {
                "csv_path": result.get("csv_path"),
                "txt_path": result.get("txt_path"),
                "summary": result.get("summary"),
                "compliance": result.get("compliance"),
                "include_exclude_diagnostics": result.get("include_exclude_diagnostics"),
            },
        )
    else:
        build_store.update_progress(
            build_id,
            status="running",
            stage_idx=stage_idx,
            stage_total=stage_total,
            stage_label=result.get("label"),
        )

    return {
        "done": done,
        "status": "done" if done else "running",
        "stage_label": result.get("label"),
        "stage_idx": stage_idx,
        "stage_total": stage_total,
        "added_cards": result.get("added_cards") or [],
        "skipped": bool(result.get("skipped")),
        "gated": bool(result.get("gated")),
    }


@router.post("/{build_id}/advance", summary="Run the next build stage (guided mode)")
async def advance_build(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Run exactly one stage of a guided-mode build and return it for review.

    Call this repeatedly until the response has `"done": true`.
    """
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    if build.get("status") == "done":
        return err("Build is already complete.", "BUILD_ALREADY_DONE", 409, _rid(request))
    if build.get("status") == "error":
        return err(build.get("error") or "Build failed.", "BUILD_FAILED", 409, _rid(request))

    ctx = build_store.get_ctx(build_id)
    lock = build_store.get_stage_lock(build_id)
    if ctx is None or lock is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    try:
        result = await asyncio.to_thread(_run_stage_sync, ctx, lock)
    except Exception as exc:  # noqa: BLE001
        build_store.mark_error(build_id, str(exc))
        return err(str(exc), "BUILD_STAGE_FAILED", 500, _rid(request))

    payload = _finalize_stage_result(build_id, ctx, result)
    return ok(payload, _rid(request))


@router.post("/{build_id}/rerun", summary="Re-run the current build stage (guided mode)")
async def rerun_build_stage(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Re-run the most recently completed stage and pull a fresh batch of cards.

    Locked cards are preserved and the stage index does not advance further;
    use this to "reroll" a stage's picks without stepping forward.
    """
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    if build.get("status") == "done":
        return err("Build is already complete.", "BUILD_ALREADY_DONE", 409, _rid(request))
    if build.get("status") == "error":
        return err(build.get("error") or "Build failed.", "BUILD_FAILED", 409, _rid(request))

    ctx = build_store.get_ctx(build_id)
    lock = build_store.get_stage_lock(build_id)
    if ctx is None or lock is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    try:
        result = await asyncio.to_thread(_run_stage_sync, ctx, lock, rerun=True, replace=True)
    except Exception as exc:  # noqa: BLE001
        build_store.mark_error(build_id, str(exc))
        return err(str(exc), "BUILD_STAGE_FAILED", 500, _rid(request))

    payload = _finalize_stage_result(build_id, ctx, result)
    return ok(payload, _rid(request))


@router.get("/{build_id}/alternatives", summary="Suggest alternative cards (guided mode)")
async def get_build_alternatives(
    build_id: str,
    card: str,
    request: Request,
    owned_only: bool = False,
    exclude: Optional[str] = None,
    user: User = Depends(get_api_user),
):
    """Suggest alternatives for a card already in a guided build's deck-in-progress.

    `exclude` is an optional comma-separated list of card names to omit from
    the results (in addition to the build's own swap history) -- used by
    clients to "reroll" and see a different batch of suggestions.
    """
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    ctx = build_store.get_ctx(build_id)
    if ctx is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))
    b = ctx.get("builder")
    if b is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    exclude_set = set(ctx.get("alts_exclude") or [])
    if exclude:
        exclude_set.update(x.strip() for x in exclude.split(",") if x.strip())

    items = await asyncio.to_thread(
        api_alternatives.suggest_alternatives,
        b,
        card,
        owned_only=owned_only,
        exclude=exclude_set,
        locked=ctx.get("locks"),
        commander=getattr(b, "commander_name", None) or getattr(b, "commander", None),
    )
    return ok({"items": items}, _rid(request))


def _replace_card_sync(ctx: Dict[str, Any], old_name: str, new_name: str) -> Dict[str, str]:
    b = ctx.get("builder")
    o_disp = str(old_name).strip()
    n_disp = str(new_name).strip()
    o = o_disp.lower()
    n = n_disp.lower()

    lib = getattr(b, "card_library", {}) or {}
    old_key = None
    if o_disp in lib:
        old_key = o_disp
    else:
        for k in list(lib.keys()):
            if str(k).strip().lower() == o:
                old_key = k
                break
    if old_key is None:
        raise KeyError(f"'{old_name}' is not in the deck.")

    old_info = dict(lib.get(old_key) or {})
    role = str(old_info.get("Role") or "").strip()
    sub_role = str(old_info.get("SubRole") or "").strip()
    try:
        count = int(old_info.get("Count", 1))
    except Exception:
        count = 1
    del lib[old_key]

    df = getattr(b, "_combined_cards_df", None)
    new_key = n_disp
    card_type = ""
    mana_cost = ""
    if df is not None:
        try:
            row = df[df["name"].astype(str).str.strip().str.lower() == n]
            if not row.empty:
                new_key = str(row.iloc[0]["name"]) or n_disp
                card_type = str(row.iloc[0].get("type", row.iloc[0].get("type_line", "")) or "")
                mana_cost = str(row.iloc[0].get("mana_cost", row.iloc[0].get("manaCost", "")) or "")
        except Exception:
            pass

    lib[new_key] = {
        "Count": count,
        "Card Type": card_type,
        "Mana Cost": mana_cost,
        "Role": role,
        "SubRole": sub_role,
        "AddedBy": "Replace",
        "TriggerTag": str(old_info.get("TriggerTag") or ""),
    }
    try:
        preferred = getattr(b, "preferred_replacements", {}) or {}
        preferred[o] = n
        setattr(b, "preferred_replacements", preferred)
    except Exception:
        pass

    locks = set(ctx.get("locks") or [])
    locks.discard(o)
    locks.add(n)
    ctx["locks"] = locks
    exclude = set(ctx.get("alts_exclude") or [])
    exclude.add(o)
    ctx["alts_exclude"] = exclude

    return {"old_name": old_key, "new_name": new_key}


@router.post("/{build_id}/replace", summary="Swap a card in a guided build's deck-in-progress")
async def replace_build_card(
    build_id: str, body: ReplaceCardRequest, request: Request, user: User = Depends(get_api_user)
):
    """Replace `old_name` with `new_name` in the deck-in-progress, then lock
    `new_name` in place so later stages won't remove it.
    """
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    ctx = build_store.get_ctx(build_id)
    lock = build_store.get_stage_lock(build_id)
    if ctx is None or lock is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    def _run():
        with lock:
            return _replace_card_sync(ctx, body.old_name, body.new_name)

    try:
        result = await asyncio.to_thread(_run)
    except KeyError as exc:
        return err(str(exc), "CARD_NOT_IN_DECK", 404, _rid(request))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), "REPLACE_FAILED", 500, _rid(request))

    return ok(result, _rid(request))


def _remove_card_sync(ctx: Dict[str, Any], name: str) -> Dict[str, Any]:
    b = ctx.get("builder")
    disp = str(name).strip()
    key = disp.lower()

    lib = getattr(b, "card_library", {}) or {}
    old_key = None
    if disp in lib:
        old_key = disp
    else:
        for k in list(lib.keys()):
            if str(k).strip().lower() == key:
                old_key = k
                break
    if old_key is None:
        raise KeyError(f"'{name}' is not in the deck.")

    entry = lib.get(old_key) or {}
    if entry.get("Commander"):
        raise ValueError("Cannot remove the commander.")

    entry_snapshot = dict(entry)
    try:
        cnt = int(entry.get("Count", 1))
    except Exception:
        cnt = 1
    if cnt <= 1:
        del lib[old_key]
    else:
        entry["Count"] = cnt - 1

    was_land = "land" in str(entry_snapshot.get("Card Type", "")).lower()
    try:
        if was_land:
            b._color_source_cache_dirty = True
        else:
            b._spell_pip_cache_dirty = True
    except Exception:
        pass

    locks = set(ctx.get("locks") or [])
    locks.discard(key)
    ctx["locks"] = locks

    exclude = set(ctx.get("alts_exclude") or [])
    exclude.add(key)
    ctx["alts_exclude"] = exclude

    ctx["last_remove"] = {
        "name": key,
        "display_name": old_key,
        "entry": entry_snapshot,
        "had_multiple": cnt > 1,
    }

    return {"name": old_key, "removed": True}


def _undo_remove_card_sync(ctx: Dict[str, Any]) -> Dict[str, Any]:
    last = ctx.get("last_remove") or {}
    key = str(last.get("name") or "")
    entry_snapshot = last.get("entry") if isinstance(last, dict) else None
    b = ctx.get("builder")
    if b is None or not key or not entry_snapshot:
        return {"restored": False}

    lib = getattr(b, "card_library", None)
    if lib is None:
        lib = {}
        b.card_library = lib

    old_key = None
    for k in list(lib.keys()):
        if str(k).strip().lower() == key:
            old_key = k
            break

    if old_key is not None and last.get("had_multiple"):
        lib[old_key]["Count"] = int(lib[old_key].get("Count", 0)) + 1
        restore_key = old_key
    else:
        restore_key = old_key or last.get("display_name") or key
        lib[restore_key] = dict(entry_snapshot)

    restored_entry = dict(lib.get(restore_key) or {})
    try:
        restored_count = int(restored_entry.get("Count", 1))
    except Exception:
        restored_count = 1

    was_land = "land" in str(entry_snapshot.get("Card Type", "")).lower()
    try:
        if was_land:
            b._color_source_cache_dirty = True
        else:
            b._spell_pip_cache_dirty = True
    except Exception:
        pass

    exclude = set(ctx.get("alts_exclude") or [])
    exclude.discard(key)
    ctx["alts_exclude"] = exclude
    ctx.pop("last_remove", None)

    return {"restored": True, "name": str(restore_key), "count": restored_count}


@router.post("/{build_id}/remove-card", summary="Remove a card from a guided build's deck-in-progress")
async def remove_build_card(
    build_id: str, body: RemoveCardRequest, request: Request, user: User = Depends(get_api_user)
):
    """Remove `name` entirely from the deck-in-progress (unlocking it if locked).

    The freed slot is left open for later stages to fill naturally; this does
    not permanently block the card from being picked again on a stage rerun.
    Call `POST /{build_id}/remove-card/undo` to restore it.
    """
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    ctx = build_store.get_ctx(build_id)
    lock = build_store.get_stage_lock(build_id)
    if ctx is None or lock is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    def _run():
        with lock:
            return _remove_card_sync(ctx, body.name)

    try:
        result = await asyncio.to_thread(_run)
    except KeyError as exc:
        return err(str(exc), "CARD_NOT_IN_DECK", 404, _rid(request))
    except ValueError as exc:
        return err(str(exc), "CANNOT_REMOVE_COMMANDER", 400, _rid(request))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), "REMOVE_FAILED", 500, _rid(request))

    return ok(result, _rid(request))


@router.post("/{build_id}/remove-card/undo", summary="Undo the last card removal")
async def undo_remove_build_card(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Restore the most recently removed card back into the deck-in-progress."""
    build = _guided_build_or_none(build_id, user["id"])
    if build is None:
        return err("Guided build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    ctx = build_store.get_ctx(build_id)
    lock = build_store.get_stage_lock(build_id)
    if ctx is None or lock is None:
        return err("Build session expired.", "BUILD_SESSION_EXPIRED", 410, _rid(request))

    def _run():
        with lock:
            return _undo_remove_card_sync(ctx)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), "UNDO_FAILED", 500, _rid(request))

    return ok(result, _rid(request))


@router.delete("/{build_id}", summary="Delete a build record")
async def delete_build(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Discard a build record. Does not interrupt an in-progress build thread."""
    build = build_store.get_build(build_id)
    if not build or build.get("user_id") != user["id"]:
        return err("Build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    build_store.delete_build(build_id)
    return ok({"deleted": True}, _rid(request))
