from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from ..app import templates
from deck_builder import builder_constants as bc
from ..services import orchestrator as orch
from ..services.tasks import get_session, new_sid

router = APIRouter(prefix="/build")


@router.get("/", response_class=HTMLResponse)
async def build_index(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    resp = templates.TemplateResponse(
        "build/index.html",
        {"request": request, "sid": sid, "commander": sess.get("commander"), "tags": sess.get("tags", [])},
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step1", response_class=HTMLResponse)
async def build_step1(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})


@router.post("/step1", response_class=HTMLResponse)
async def build_step1_search(
    request: Request,
    query: str = Form(""),
    auto: str | None = Form(None),
    active: str | None = Form(None),
) -> HTMLResponse:
    query = (query or "").strip()
    auto_enabled = True if (auto == "1") else False
    candidates = []
    if query:
        candidates = orch.commander_candidates(query, limit=10)
        # Optional auto-select at a stricter threshold
        if auto_enabled and candidates and len(candidates[0]) >= 2 and int(candidates[0][1]) >= 98:
            top_name = candidates[0][0]
            res = orch.commander_select(top_name)
            if res.get("ok"):
                return templates.TemplateResponse(
                    "build/_step2.html",
                    {
                        "request": request,
                        "commander": res,
                        "tags": orch.tags_for_commander(res["name"]),
                        "recommended": orch.recommended_tags_for_commander(res["name"]),
                        "recommended_reasons": orch.recommended_tag_reasons_for_commander(res["name"]),
                        "brackets": orch.bracket_options(),
                    },
                )
    return templates.TemplateResponse(
        "build/_step1.html",
        {
            "request": request,
            "query": query,
            "candidates": candidates,
            "auto": auto_enabled,
            "active": active,
            "count": len(candidates) if candidates else 0,
        },
    )


@router.post("/step1/inspect", response_class=HTMLResponse)
async def build_step1_inspect(request: Request, name: str = Form(...)) -> HTMLResponse:
    info = orch.commander_inspect(name)
    return templates.TemplateResponse(
        "build/_step1.html",
        {"request": request, "inspect": info, "selected": name, "tags": orch.tags_for_commander(name)},
    )


@router.post("/step1/confirm", response_class=HTMLResponse)
async def build_step1_confirm(request: Request, name: str = Form(...)) -> HTMLResponse:
    res = orch.commander_select(name)
    if not res.get("ok"):
        return templates.TemplateResponse("build/_step1.html", {"request": request, "error": res.get("error"), "selected": name})
    # Proceed to step2 placeholder
    return templates.TemplateResponse(
        "build/_step2.html",
        {
            "request": request,
            "commander": res,
            "tags": orch.tags_for_commander(res["name"]),
            "recommended": orch.recommended_tags_for_commander(res["name"]),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(res["name"]),
            "brackets": orch.bracket_options(),
        },
    )


@router.get("/step2", response_class=HTMLResponse)
async def build_step2_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    if not commander:
        # Fallback to step1 if no commander in session
        return templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": []})
    tags = orch.tags_for_commander(commander)
    selected = sess.get("tags", [])
    return templates.TemplateResponse(
        "build/_step2.html",
        {
            "request": request,
            "commander": {"name": commander},
            "tags": tags,
            "recommended": orch.recommended_tags_for_commander(commander),
            "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
            "brackets": orch.bracket_options(),
            "primary_tag": selected[0] if len(selected) > 0 else "",
            "secondary_tag": selected[1] if len(selected) > 1 else "",
            "tertiary_tag": selected[2] if len(selected) > 2 else "",
            "selected_bracket": sess.get("bracket"),
            "tag_mode": sess.get("tag_mode", "AND"),
        },
    )


@router.post("/step2", response_class=HTMLResponse)
async def build_step2_submit(
    request: Request,
    commander: str = Form(...),
    primary_tag: str | None = Form(None),
    secondary_tag: str | None = Form(None),
    tertiary_tag: str | None = Form(None),
    tag_mode: str | None = Form("AND"),
    bracket: int = Form(...),
) -> HTMLResponse:
    # Validate primary tag selection if tags are available
    available_tags = orch.tags_for_commander(commander)
    if available_tags and not (primary_tag and primary_tag.strip()):
        return templates.TemplateResponse(
            "build/_step2.html",
            {
                "request": request,
                "commander": {"name": commander},
                "tags": available_tags,
                "recommended": orch.recommended_tags_for_commander(commander),
                "recommended_reasons": orch.recommended_tag_reasons_for_commander(commander),
                "brackets": orch.bracket_options(),
                "error": "Please choose a primary theme.",
                "primary_tag": primary_tag or "",
                "secondary_tag": secondary_tag or "",
                "tertiary_tag": tertiary_tag or "",
                "selected_bracket": int(bracket) if bracket is not None else None,
                "tag_mode": (tag_mode or "AND"),
            },
        )

    # Save selection to session (basic MVP; real build will use this later)
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["commander"] = commander
    sess["tags"] = [t for t in [primary_tag, secondary_tag, tertiary_tag] if t]
    sess["tag_mode"] = (tag_mode or "AND").upper()
    sess["bracket"] = int(bracket)
    # Proceed to Step 3 placeholder for now
    return templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "commander": commander,
            "tags": sess["tags"],
            "bracket": sess["bracket"],
            "defaults": orch.ideal_defaults(),
            "labels": orch.ideal_labels(),
            "values": orch.ideal_defaults(),
        },
    )


@router.post("/step3", response_class=HTMLResponse)
async def build_step3_submit(
    request: Request,
    ramp: int = Form(...),
    lands: int = Form(...),
    basic_lands: int = Form(...),
    creatures: int = Form(...),
    removal: int = Form(...),
    wipes: int = Form(...),
    card_advantage: int = Form(...),
    protection: int = Form(...),
) -> HTMLResponse:
    labels = orch.ideal_labels()
    submitted = {
        "ramp": ramp,
        "lands": lands,
        "basic_lands": basic_lands,
        "creatures": creatures,
        "removal": removal,
        "wipes": wipes,
        "card_advantage": card_advantage,
        "protection": protection,
    }

    errors: list[str] = []
    for k, v in submitted.items():
        try:
            iv = int(v)
        except Exception:
            errors.append(f"{labels.get(k, k)} must be a number.")
            continue
        if iv < 0:
            errors.append(f"{labels.get(k, k)} cannot be negative.")
        submitted[k] = iv
    # Cross-field validation: basic lands should not exceed total lands
    if isinstance(submitted.get("basic_lands"), int) and isinstance(submitted.get("lands"), int):
        if submitted["basic_lands"] > submitted["lands"]:
            errors.append("Basic Lands cannot exceed Total Lands.")

    if errors:
        sid = request.cookies.get("sid") or new_sid()
        sess = get_session(sid)
        return templates.TemplateResponse(
            "build/_step3.html",
            {
                "request": request,
                "defaults": orch.ideal_defaults(),
                "labels": labels,
                "values": submitted,
                "error": " ".join(errors),
                "commander": sess.get("commander"),
                "tags": sess.get("tags", []),
                "bracket": sess.get("bracket"),
            },
        )

    # Save to session
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    sess["ideals"] = submitted

    # Proceed to review (Step 4)
    return templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": submitted,
            "commander": sess.get("commander"),
        },
    )


@router.get("/step3", response_class=HTMLResponse)
async def build_step3_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    defaults = orch.ideal_defaults()
    values = sess.get("ideals") or defaults
    resp = templates.TemplateResponse(
        "build/_step3.html",
        {
            "request": request,
            "defaults": defaults,
            "labels": orch.ideal_labels(),
            "values": values,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.get("/step4", response_class=HTMLResponse)
async def build_step4_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    labels = orch.ideal_labels()
    values = sess.get("ideals") or orch.ideal_defaults()
    commander = sess.get("commander")
    return templates.TemplateResponse(
        "build/_step4.html",
        {
            "request": request,
            "labels": labels,
            "values": values,
            "commander": commander,
        },
    )


@router.get("/step5", response_class=HTMLResponse)
async def build_step5_get(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    resp = templates.TemplateResponse(
        "build/_step5.html",
        {
            "request": request,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
            "values": sess.get("ideals", orch.ideal_defaults()),
            "status": None,
            "stage_label": None,
            "log": None,
            "added_cards": [],
            "game_changers": bc.GAME_CHANGERS,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp
    
@router.post("/step5/continue", response_class=HTMLResponse)
async def build_step5_continue(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Validate commander; redirect to step1 if missing
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Ensure build context exists; if not, start it first
    if not sess.get("build_ctx"):
        opts = orch.bracket_options()
        default_bracket = (opts[0]["level"] if opts else 1)
        bracket_val = sess.get("bracket")
        try:
            safe_bracket = int(bracket_val) if bracket_val is not None else int(default_bracket)
        except Exception:
            safe_bracket = int(default_bracket)
        ideals_val = sess.get("ideals") or orch.ideal_defaults()
        sess["build_ctx"] = orch.start_build_ctx(
            commander=sess.get("commander"),
            tags=sess.get("tags", []),
            bracket=safe_bracket,
            ideals=ideals_val,
            tag_mode=sess.get("tag_mode", "AND"),
        )
    res = orch.run_stage(sess["build_ctx"], rerun=False)
    status = "Build complete" if res.get("done") else "Stage complete"
    stage_label = res.get("label")
    log = res.get("log_delta", "")
    added_cards = res.get("added_cards", [])
    # Progress & downloads
    i = res.get("idx")
    n = res.get("total")
    csv_path = res.get("csv_path") if res.get("done") else None
    txt_path = res.get("txt_path") if res.get("done") else None
    summary = res.get("summary") if res.get("done") else None
    resp = templates.TemplateResponse(
        "build/_step5.html",
        {
            "request": request,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
            "values": sess.get("ideals", orch.ideal_defaults()),
            "status": status,
            "stage_label": stage_label,
            "log": log,
            "added_cards": added_cards,
            "i": i,
            "n": n,
            "csv_path": csv_path,
            "txt_path": txt_path,
            "summary": summary,
            "game_changers": bc.GAME_CHANGERS,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@router.post("/step5/rerun", response_class=HTMLResponse)
async def build_step5_rerun(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    if not sess.get("commander"):
        resp = templates.TemplateResponse("build/_step1.html", {"request": request, "candidates": [], "error": "Please select a commander first."})
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    # Rerun requires an existing context; if missing, create it and run first stage as rerun
    if not sess.get("build_ctx"):
        opts = orch.bracket_options()
        default_bracket = (opts[0]["level"] if opts else 1)
        bracket_val = sess.get("bracket")
        try:
            safe_bracket = int(bracket_val) if bracket_val is not None else int(default_bracket)
        except Exception:
            safe_bracket = int(default_bracket)
        ideals_val = sess.get("ideals") or orch.ideal_defaults()
        sess["build_ctx"] = orch.start_build_ctx(
            commander=sess.get("commander"),
            tags=sess.get("tags", []),
            bracket=safe_bracket,
            ideals=ideals_val,
            tag_mode=sess.get("tag_mode", "AND"),
        )
    res = orch.run_stage(sess["build_ctx"], rerun=True)
    status = "Stage rerun complete" if not res.get("done") else "Build complete"
    stage_label = res.get("label")
    log = res.get("log_delta", "")
    added_cards = res.get("added_cards", [])
    i = res.get("idx")
    n = res.get("total")
    csv_path = res.get("csv_path") if res.get("done") else None
    txt_path = res.get("txt_path") if res.get("done") else None
    summary = res.get("summary") if res.get("done") else None
    resp = templates.TemplateResponse(
        "build/_step5.html",
        {
            "request": request,
            "commander": sess.get("commander"),
            "tags": sess.get("tags", []),
            "bracket": sess.get("bracket"),
            "values": sess.get("ideals", orch.ideal_defaults()),
            "status": status,
            "stage_label": stage_label,
            "log": log,
            "added_cards": added_cards,
            "i": i,
            "n": n,
            "csv_path": csv_path,
            "txt_path": txt_path,
            "summary": summary,
            "game_changers": bc.GAME_CHANGERS,
        },
    )
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@router.post("/step5/start", response_class=HTMLResponse)
async def build_step5_start(request: Request) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    # Validate commander exists before starting
    commander = sess.get("commander")
    if not commander:
        resp = templates.TemplateResponse(
            "build/_step1.html",
            {"request": request, "candidates": [], "error": "Please select a commander first."},
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    try:
        # Initialize step-by-step build context and run first stage
        opts = orch.bracket_options()
        default_bracket = (opts[0]["level"] if opts else 1)
        bracket_val = sess.get("bracket")
        try:
            safe_bracket = int(bracket_val) if bracket_val is not None else int(default_bracket)
        except Exception:
            safe_bracket = int(default_bracket)
        ideals_val = sess.get("ideals") or orch.ideal_defaults()
        sess["build_ctx"] = orch.start_build_ctx(
            commander=commander,
            tags=sess.get("tags", []),
            bracket=safe_bracket,
            ideals=ideals_val,
            tag_mode=sess.get("tag_mode", "AND"),
        )
        res = orch.run_stage(sess["build_ctx"], rerun=False)
        status = "Stage complete" if not res.get("done") else "Build complete"
        stage_label = res.get("label")
        log = res.get("log_delta", "")
        added_cards = res.get("added_cards", [])
        i = res.get("idx")
        n = res.get("total")
        csv_path = res.get("csv_path") if res.get("done") else None
        txt_path = res.get("txt_path") if res.get("done") else None
        summary = res.get("summary") if res.get("done") else None
        resp = templates.TemplateResponse(
            "build/_step5.html",
            {
                "request": request,
                "commander": commander,
                "tags": sess.get("tags", []),
                "bracket": sess.get("bracket"),
                "values": sess.get("ideals", orch.ideal_defaults()),
                "status": status,
                "stage_label": stage_label,
                "log": log,
                "added_cards": added_cards,
                "i": i,
                "n": n,
                "csv_path": csv_path,
                "txt_path": txt_path,
                "summary": summary,
                "game_changers": bc.GAME_CHANGERS,
            },
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp
    except Exception as e:
        # Surface a friendly error on the step 5 screen
        resp = templates.TemplateResponse(
            "build/_step5.html",
            {
                "request": request,
                "commander": commander,
                "tags": sess.get("tags", []),
                "bracket": sess.get("bracket"),
                "values": sess.get("ideals", orch.ideal_defaults()),
                "status": "Error",
                "stage_label": None,
                "log": f"Failed to start build: {e}",
                "added_cards": [],
                "i": None,
                "n": None,
                "csv_path": None,
                "txt_path": None,
                "summary": None,
                "game_changers": bc.GAME_CHANGERS,
            },
        )
        resp.set_cookie("sid", sid, httponly=True, samesite="lax")
        return resp

@router.get("/step5/start", response_class=HTMLResponse)
async def build_step5_start_get(request: Request) -> HTMLResponse:
    # Allow GET as a fallback to start the build (delegates to POST handler)
    return await build_step5_start(request)


@router.get("/banner", response_class=HTMLResponse)
async def build_banner(request: Request, step: str = "", i: int | None = None, n: int | None = None) -> HTMLResponse:
    sid = request.cookies.get("sid") or new_sid()
    sess = get_session(sid)
    commander = sess.get("commander")
    tags = sess.get("tags", [])
    # Render only the inner text for the subtitle
    return templates.TemplateResponse(
        "build/_banner_subtitle.html",
    {"request": request, "commander": commander, "tags": tags, "step": step, "i": i, "n": n},
    )
