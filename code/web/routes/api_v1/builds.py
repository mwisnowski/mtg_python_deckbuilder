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

from code.type_definitions import User

from ...services import api_build_store as build_store
from ...services import orchestrator as orch
from ...services.build_utils import owned_names as owned_names_helper
from ...utils.api_response import err, ok
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
            if result.get("done"):
                build_store.mark_done(
                    build_id,
                    {
                        "csv_path": result.get("csv_path"),
                        "txt_path": result.get("txt_path"),
                        "summary": result.get("summary"),
                        "compliance": result.get("compliance"),
                    },
                )
                return
    except Exception as exc:  # noqa: BLE001 -- surfaced to the client via the store
        build_store.mark_error(build_id, str(exc))


@router.post("", summary="Create a deck build")
async def create_build(body: CreateBuildRequest, request: Request, user: User = Depends(get_api_user)):
    """Start a new deck build. Returns immediately with a `build_id` to poll."""
    commander = body.commander.strip()
    if not commander:
        return err("commander is required.", "INVALID_COMMANDER", 400, _rid(request))
    bracket = body.bracket if body.bracket is not None else _default_bracket()

    owned_names_list = owned_names_helper() if (body.owned_only or body.prefer_owned) else None

    try:
        ctx = await asyncio.to_thread(
            orch.start_build_ctx,
            commander=commander,
            tags=body.themes,
            bracket=bracket,
            ideals=orch.ideal_defaults(),
            use_owned_only=body.owned_only,
            prefer_owned=body.prefer_owned,
            owned_names=owned_names_list,
            budget_config=body.budget,
        )
    except ValueError as exc:
        return err(str(exc), "INVALID_BUILD_REQUEST", 400, _rid(request))
    except RuntimeError as exc:
        return err(str(exc), "SETUP_NOT_READY", 503, _rid(request))

    build_id = build_store.create_build(user["id"], body.model_dump())
    asyncio.create_task(asyncio.to_thread(_run_build_sync, build_id, ctx))

    return ok({"build_id": build_id, "status": "queued"}, _rid(request), status_code=202)


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


@router.delete("/{build_id}", summary="Delete a build record")
async def delete_build(build_id: str, request: Request, user: User = Depends(get_api_user)):
    """Discard a build record. Does not interrupt an in-progress build thread."""
    build = build_store.get_build(build_id)
    if not build or build.get("user_id") != user["id"]:
        return err("Build not found.", "BUILD_NOT_FOUND", 404, _rid(request))
    build_store.delete_build(build_id)
    return ok({"deleted": True}, _rid(request))
