from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, Response
from ..app import templates
from ..services import owned_store as store


router = APIRouter(prefix="/owned")


def _user_id(request: Request) -> str:
    """Return the store key for the current user (UUID or 'guest')."""
    u = getattr(request.state, "current_user", None)
    if u and not u.get("is_guest") and u.get("id"):
        return str(u["id"])
    return "guest"


def _canon_color_code(seq: list[str] | tuple[str, ...]) -> str:
    """Canonicalize a color identity sequence to a stable code (WUBRG order, no 'C' unless only color)."""
    order = {'W':0,'U':1,'B':2,'R':3,'G':4,'C':5}
    uniq: list[str] = []
    seen: set[str] = set()
    for c in (seq or []):
        uc = (c or '').upper()
        if uc in order and uc not in seen:
            seen.add(uc)
            uniq.append(uc)
    uniq.sort(key=lambda x: order[x])
    code = ''.join([c for c in uniq if c != 'C'])
    return code or ('C' if 'C' in seen else '')


def _color_combo_label(code: str) -> str:
    """Return friendly label for a 2/3/4-color combo code; empty if unknown.

    Uses standard names: Guilds, Shards/Wedges, and Nephilim-style for 4-color.
    """
    two_map = {
        'WU':'Azorius','UB':'Dimir','BR':'Rakdos','RG':'Gruul','WG':'Selesnya',
        'WB':'Orzhov','UR':'Izzet','BG':'Golgari','WR':'Boros','UG':'Simic',
    }
    three_map = {
        'WUB':'Esper','UBR':'Grixis','BRG':'Jund','WRG':'Naya','WUG':'Bant',
        'WBR':'Mardu','WUR':'Jeskai','UBG':'Sultai','URG':'Temur','WBG':'Abzan',
    }
    four_map = {
        'WUBR': 'Yore-Tiller',   # no G
        'WUBG': 'Witch-Maw',     # no R
        'WURG': 'Ink-Treader',   # no B
        'WBRG': 'Dune-Brood',    # no U
        'UBRG': 'Glint-Eye',     # no W
    }
    if len(code) == 2:
        return two_map.get(code, '')
    if len(code) == 3:
        return three_map.get(code, '')
    if len(code) == 4:
        return four_map.get(code, '')
    return ''


def _build_color_combos(names_sorted: list[str], colors_by_name: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Compute present color combos and return [(code, display)], ordered by length then code."""
    combo_set: set[str] = set()
    for n in names_sorted:
        cols = (colors_by_name.get(n) or [])
        code = _canon_color_code(cols)
        if len(code) >= 2:
            combo_set.add(code)
    combos: list[tuple[str, str]] = []
    for code in sorted(combo_set, key=lambda s: (len(s), s)):
        label = _color_combo_label(code)
        display = f"{label} ({code})" if label else code
        combos.append((code, display))
    return combos


def _build_owned_context(request: Request, notice: str | None = None, error: str | None = None) -> dict:
    """Build the template context for the Owned Library page."""
    uid = _user_id(request)
    names, tags_by_name, type_by_name, colors_by_name = store.get_enriched(uid)
    added_at_map = store.get_added_at_map(uid)
    # Default sort by name (case-insensitive)
    names_sorted = sorted(names, key=lambda s: s.lower())
    # Build filter option sets
    all_types = sorted({type_by_name.get(n) for n in names_sorted if type_by_name.get(n)}, key=lambda s: s.lower())
    all_tags = sorted({t for n in names_sorted for t in (tags_by_name.get(n) or [])}, key=lambda s: s.lower())
    all_colors = ['W','U','B','R','G','C']
    # Build color combos displayed in the filter
    combos = _build_color_combos(names_sorted, colors_by_name)
    ctx = {
        "request": request,
        "names": names_sorted,
        "count": len(names_sorted),
        "tags_by_name": tags_by_name,
        "type_by_name": type_by_name,
        "colors_by_name": colors_by_name,
        "all_types": all_types,
        "all_tags": all_tags,
        "all_colors": all_colors,
    "color_combos": combos,
    "added_at_map": added_at_map,
    }
    if notice:
        ctx["notice"] = notice
    if error:
        ctx["error"] = error
    return ctx


@router.get("/", response_class=HTMLResponse)
async def owned_index(
    request: Request,
    search: str = Query(""),
    sort_by: str = Query("name"),
    filter_type: str = Query(""),
    filter_tags: list[str] = Query([]),
    filter_color: str = Query(""),
    cmc_min: str = Query(""),
    cmc_max: str = Query(""),
    power_min: str = Query(""),
    power_max: str = Query(""),
    tough_min: str = Query(""),
    tough_max: str = Query(""),
) -> HTMLResponse:
    ctx = _build_owned_context(request)

    names: list[str] = ctx["names"]
    tags_by_name: dict = ctx.get("tags_by_name") or {}
    type_by_name: dict = ctx.get("type_by_name") or {}
    colors_by_name: dict = ctx.get("colors_by_name") or {}
    added_at_map: dict = ctx.get("added_at_map") or {}
    total_count: int = ctx["count"]

    # Search filter
    if search:
        sq = search.strip().lower()
        names = [n for n in names if sq in n.lower()]

    # Type filter
    if filter_type:
        ft = filter_type.lower()
        names = [n for n in names if ft in (type_by_name.get(n) or "").lower()]

    # Tag filter (AND logic: card must have ALL selected themes)
    for ftag in filter_tags:
        ftag_lower = ftag.lower()
        names = [n for n in names if any(t.lower() == ftag_lower for t in (tags_by_name.get(n) or []))]

    # Color filter
    if filter_color:
        fcode = _canon_color_code(list(filter_color.upper()))
        names = [n for n in names if _canon_color_code(colors_by_name.get(n) or []) == fcode]

    # CMC / Power / Toughness range filters
    if cmc_min or cmc_max or power_min or power_max or tough_min or tough_max:
        stats_map = store.get_stats_map(_user_id(request))

        def _to_float(s: str) -> float | None:
            try:
                return float(s) if s else None
            except (ValueError, TypeError):
                return None

        cmc_lo = _to_float(cmc_min)
        cmc_hi = _to_float(cmc_max)
        pw_lo  = _to_float(power_min)
        pw_hi  = _to_float(power_max)
        th_lo  = _to_float(tough_min)
        th_hi  = _to_float(tough_max)

        def _in_range(val: object, lo: float | None, hi: float | None) -> bool:
            if lo is None and hi is None:
                return True
            try:
                v = float(val)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                return False
            return (lo is None or v >= lo) and (hi is None or v <= hi)

        filtered: list[str] = []
        for n in names:
            s = stats_map.get(n) or {}
            if not _in_range(s.get("manaValue"), cmc_lo, cmc_hi):
                continue
            if not _in_range(s.get("power"), pw_lo, pw_hi):
                continue
            if not _in_range(s.get("toughness"), th_lo, th_hi):
                continue
            filtered.append(n)
        names = filtered

    # Sort
    if sort_by == "type":
        names.sort(key=lambda n: (type_by_name.get(n) or "").lower())
    elif sort_by == "color":
        names.sort(key=lambda n: "".join(colors_by_name.get(n) or []))
    elif sort_by == "tags":
        names.sort(key=lambda n: len(tags_by_name.get(n) or []))
    elif sort_by == "recent":
        names.sort(key=lambda n: -(added_at_map.get(n) or 0))
    # else "name": already A-Z from _build_owned_context

    ctx.update({
        "names": names,
        "count": total_count,
        "filtered_count": len(names),
        "search": search,
        "sort_by": sort_by,
        "filter_type": filter_type,
        "filter_tags": filter_tags,
        "filter_color": filter_color,
        "cmc_min": cmc_min,
        "cmc_max": cmc_max,
        "power_min": power_min,
        "power_max": power_max,
        "tough_min": tough_min,
        "tough_max": tough_max,
    })
    return templates.TemplateResponse("owned/index.html", ctx)


@router.post("/upload", response_class=HTMLResponse)
async def owned_upload(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    try:
        content = await file.read()
        fname = (file.filename or "").lower()
        if fname.endswith(".csv"):
            names = store.parse_csv_bytes(content)
        else:
            names = store.parse_txt_bytes(content)
        # Add and enrich immediately so the page doesn't need to parse CSVs
        added, total = store.add_and_enrich(names, _user_id(request))
        notice = f"Added {added} new name(s). Total: {total}."
        ctx = _build_owned_context(request, notice=notice)
        return templates.TemplateResponse("owned/index.html", ctx)
    except Exception as e:
        ctx = _build_owned_context(request, error=f"Upload failed: {e}")
        return templates.TemplateResponse("owned/index.html", ctx)


@router.post("/clear", response_class=HTMLResponse)
async def owned_clear(request: Request) -> HTMLResponse:
    try:
        store.clear(_user_id(request))
        ctx = _build_owned_context(request, notice="Library cleared.")
        return templates.TemplateResponse("owned/index.html", ctx)
    except Exception as e:
        ctx = _build_owned_context(request, error=f"Clear failed: {e}")
        return templates.TemplateResponse("owned/index.html", ctx)


@router.post("/remove", response_class=HTMLResponse)
async def owned_remove(request: Request) -> HTMLResponse:
    """Remove a set of names provided as JSON or form data under 'names'."""
    try:
        names: list[str] = []
        # Try JSON first
        try:
            payload = await request.json()
            if isinstance(payload, dict) and isinstance(payload.get("names"), list):
                names = [str(x) for x in payload.get("names")]
            elif isinstance(payload, list):
                names = [str(x) for x in payload]
        except Exception:
            # Fallback to form field 'names' as comma-separated
            form = await request.form()
            raw = form.get("names") or ""
            if raw:
                names = [s.strip() for s in str(raw).split(',') if s.strip()]
        removed, total = store.remove_names(names, _user_id(request))
        notice = f"Removed {removed} name(s). Total: {total}."
        ctx = _build_owned_context(request, notice=notice)
        return templates.TemplateResponse("owned/index.html", ctx)
    except Exception as e:
        ctx = _build_owned_context(request, error=f"Remove failed: {e}")
        return templates.TemplateResponse("owned/index.html", ctx)


# Bulk user-tag endpoints removed by request.


@router.get("/search-autocomplete", response_class=HTMLResponse)
async def owned_search_autocomplete(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=20),
) -> HTMLResponse:
    """Return card name suggestions from the owned library for the search autocomplete."""
    names, _, _, _ = store.get_enriched(_user_id(request))
    ql = q.strip().lower()
    matches = [n for n in names if ql in n.lower()][:limit]
    if not matches:
        return HTMLResponse(content='<div class="autocomplete-empty">No matches in owned library</div>')
    html = "\n".join(
        f'<div class="autocomplete-item" data-value="{n}" role="option">{n}</div>'
        for n in matches
    )
    return HTMLResponse(content=html)


"""
Note: Per request, all user tag add/remove endpoints have been removed.
"""


# Legacy /owned/use route removed; owned-only toggle now lives on the Builder Review step.


@router.get("/export")
async def owned_export_txt(request: Request) -> Response:
    """Download the owned library as a simple TXT (one name per line)."""
    names, _, _, _ = store.get_enriched(_user_id(request))
    # Stable case-insensitive sort
    lines = "\n".join(sorted((names or []), key=lambda s: s.lower()))
    return Response(
        content=lines + ("\n" if lines else ""),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=owned_cards.txt"},
    )


@router.get("/export.csv")
async def owned_export_csv(request: Request) -> Response:
    """Download the owned library with enrichment as CSV (Name,Type,Colors,Tags)."""
    names, tags_by_name, type_by_name, colors_by_name = store.get_enriched(_user_id(request))
    # Prepare CSV content
    import csv
    from io import StringIO

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Type", "Colors", "Tags"]) 
    for n in sorted((names or []), key=lambda s: s.lower()):
        tline = type_by_name.get(n, "")
        cols = ''.join(colors_by_name.get(n, []) or [])
        tags = '|'.join(tags_by_name.get(n, []) or [])
        writer.writerow([n, tline, cols, tags])
    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=owned_cards.csv"},
    )


@router.post("/export-visible")
async def owned_export_visible_txt(request: Request) -> Response:
    """Download the provided names (visible subset) as TXT."""
    try:
        names: list[str] = []
        try:
            payload = await request.json()
            if isinstance(payload, dict) and isinstance(payload.get("names"), list):
                names = [str(x) for x in payload.get("names")]
            elif isinstance(payload, list):
                names = [str(x) for x in payload]
        except Exception:
            form = await request.form()
            raw = form.get("names") or ""
            if raw:
                names = [s.strip() for s in str(raw).split(',') if s.strip()]
        # Stable case-insensitive sort
        lines = "\n".join(sorted((names or []), key=lambda s: s.lower()))
        return Response(
            content=lines + ("\n" if lines else ""),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=owned_visible.txt"},
        )
    except Exception:
        # On error return empty file
        return Response(content="", media_type="text/plain; charset=utf-8")


@router.post("/export-visible.csv")
async def owned_export_visible_csv(request: Request) -> Response:
    """Download the provided names (visible subset) with enrichment as CSV."""
    try:
        names: list[str] = []
        try:
            payload = await request.json()
            if isinstance(payload, dict) and isinstance(payload.get("names"), list):
                names = [str(x) for x in payload.get("names")]
            elif isinstance(payload, list):
                names = [str(x) for x in payload]
        except Exception:
            form = await request.form()
            raw = form.get("names") or ""
            if raw:
                names = [s.strip() for s in str(raw).split(',') if s.strip()]
        # Build CSV using current enrichment
        all_names, tags_by_name, type_by_name, colors_by_name = store.get_enriched(_user_id(request))
        import csv
        from io import StringIO
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Name", "Type", "Colors", "Tags"])
        for n in sorted((names or []), key=lambda s: s.lower()):
            tline = type_by_name.get(n, "")
            cols = ''.join(colors_by_name.get(n, []) or [])
            tags = '|'.join(tags_by_name.get(n, []) or [])
            writer.writerow([n, tline, cols, tags])
        content = buf.getvalue()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=owned_visible.csv"},
        )
    except Exception:
        return Response(content="", media_type="text/csv; charset=utf-8")
