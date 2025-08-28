from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from ..app import templates
from ..services import owned_store as store
# Session helpers are not required for owned routes


router = APIRouter(prefix="/owned")


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
    """Build the template context for the Owned Library page, including
    enrichment from csv_files and filter option lists.
    """
    # Read enriched data from the store (fast path; avoids per-request CSV parsing)
    names, tags_by_name, type_by_name, colors_by_name = store.get_enriched()
    added_at_map = store.get_added_at_map()
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
async def owned_index(request: Request) -> HTMLResponse:
    ctx = _build_owned_context(request)
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
        added, total = store.add_and_enrich(names)
        notice = f"Added {added} new name(s). Total: {total}."
        ctx = _build_owned_context(request, notice=notice)
        return templates.TemplateResponse("owned/index.html", ctx)
    except Exception as e:
        ctx = _build_owned_context(request, error=f"Upload failed: {e}")
        return templates.TemplateResponse("owned/index.html", ctx)


@router.post("/clear", response_class=HTMLResponse)
async def owned_clear(request: Request) -> HTMLResponse:
    try:
        store.clear()
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
        removed, total = store.remove_names(names)
        notice = f"Removed {removed} name(s). Total: {total}."
        ctx = _build_owned_context(request, notice=notice)
        return templates.TemplateResponse("owned/index.html", ctx)
    except Exception as e:
        ctx = _build_owned_context(request, error=f"Remove failed: {e}")
        return templates.TemplateResponse("owned/index.html", ctx)


# Bulk user-tag endpoints removed by request.


"""
Note: Per request, all user tag add/remove endpoints have been removed.
"""


# Legacy /owned/use route removed; owned-only toggle now lives on the Builder Review step.


@router.get("/export")
async def owned_export_txt() -> Response:
    """Download the owned library as a simple TXT (one name per line)."""
    names, _, _, _ = store.get_enriched()
    # Stable case-insensitive sort
    lines = "\n".join(sorted((names or []), key=lambda s: s.lower()))
    return Response(
        content=lines + ("\n" if lines else ""),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=owned_cards.txt"},
    )


@router.get("/export.csv")
async def owned_export_csv() -> Response:
    """Download the owned library with enrichment as CSV (Name,Type,Colors,Tags)."""
    names, tags_by_name, type_by_name, colors_by_name = store.get_enriched()
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
        all_names, tags_by_name, type_by_name, colors_by_name = store.get_enriched()
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
