from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, Response
from ..app import templates
from ..services import owned_store as store
from ..services.tasks import get_session, new_sid

try:
    from code.deck_builder.color_identity_utils import color_identity_badges
    from code.web.services.card_search import (
        _color_matches,
        _compare_numeric,
        filter_names_fuzzy,
        has_structured_flags,
        parse_search_query,
    )
except ImportError:
    from deck_builder.color_identity_utils import color_identity_badges
    from web.services.card_search import (
        _color_matches,
        _compare_numeric,
        filter_names_fuzzy,
        has_structured_flags,
        parse_search_query,
    )


router = APIRouter(prefix="/owned")


def _user_id(request: Request) -> str:
    """Return the store key for the current user (UUID or 'guest')."""
    u = getattr(request.state, "current_user", None)
    if u and not u.get("is_guest") and u.get("id"):
        return str(u["id"])
    return "guest"


def _apply_owned_search(
    names: list[str],
    search: str,
    tags_by_name: dict[str, list[str]],
    type_by_name: dict[str, str],
    colors_by_name: dict[str, list[str]],
    stats_map: dict[str, dict[str, object]],
) -> list[str]:
    """Filter owned `names` by the search box: plain text keeps the existing
    substring name match, but a query containing Scryfall-style flags
    (t:/c:/id:/tag:/pow:/tou:/mv:/cmc:) is filtered structurally using the
    same parser as the card browser and manual deck builder. Flags with no
    owned-library equivalent (o:/oracle, r:/rarity, m:/mana, loy:, is:new,
    set:) have no owned card data to check and are ignored rather than
    excluding every card.
    """
    if not search:
        return names

    parsed = parse_search_query(search)
    if not has_structured_flags(parsed):
        return filter_names_fuzzy(names, [search.strip()], [])

    allowed_by_name = set(filter_names_fuzzy(names, parsed.name_include, parsed.name_exclude))

    def _matches(name: str) -> bool:
        if (parsed.name_include or parsed.name_exclude) and name not in allowed_by_name:
            return False

        type_lower = (type_by_name.get(name) or "").lower()
        if parsed.type_include and not all(term.lower() in type_lower for term in parsed.type_include):
            return False
        if parsed.type_exclude and any(term.lower() in type_lower for term in parsed.type_exclude):
            return False

        card_letters = {c.upper() for c in (colors_by_name.get(name) or [])}
        if parsed.color_clauses and not all(_color_matches(card_letters, c) for c in parsed.color_clauses):
            return False
        if parsed.identity_clauses and not all(_color_matches(card_letters, c) for c in parsed.identity_clauses):
            return False

        if parsed.tags or parsed.tags_exclude:
            card_tags = {t.lower() for t in (tags_by_name.get(name) or [])}
            if parsed.tags and not all(tag in card_tags for tag in parsed.tags):
                return False
            if parsed.tags_exclude and any(tag in card_tags for tag in parsed.tags_exclude):
                return False

        stats = stats_map.get(name) or {}
        for clauses, key in (
            (parsed.power_clauses, "power"),
            (parsed.toughness_clauses, "toughness"),
            (parsed.cmc_clauses, "manaValue"),
        ):
            if not clauses:
                continue
            try:
                actual = float(stats.get(key)) if stats.get(key) is not None else None
            except (ValueError, TypeError):
                actual = None
            if actual is None:
                return False
            for clause in clauses:
                other = stats.get(clause.compare_to) if clause.compare_to else clause.value
                try:
                    other = float(other) if other is not None else None
                except (ValueError, TypeError):
                    other = None
                if other is None:
                    return False
                matched = bool(_compare_numeric(actual, clause.op, other))
                if clause.negate:
                    matched = not matched
                if not matched:
                    return False
        return True

    return [n for n in names if _matches(n)]


def _build_owned_context(request: Request, notice: str | None = None, error: str | None = None) -> dict:
    """Build the template context for the Owned Library page."""
    uid = _user_id(request)
    names, tags_by_name, type_by_name, colors_by_name = store.get_enriched(uid)
    added_at_map = store.get_added_at_map(uid)
    # Default sort by name (case-insensitive)
    names_sorted = sorted(names, key=lambda s: s.lower())
    all_tags = sorted({t for n in names_sorted for t in (tags_by_name.get(n) or [])}, key=lambda s: s.lower())
    # Per-card guild/shard/wedge/nephilim name badges + WUBRG dots, for the
    # same clickable color-identity badges shown on the card browser.
    badges_by_name = {n: color_identity_badges(colors_by_name.get(n) or []) for n in names_sorted}
    ctx = {
        "request": request,
        "names": names_sorted,
        "count": len(names_sorted),
        "tags_by_name": tags_by_name,
        "type_by_name": type_by_name,
        "colors_by_name": colors_by_name,
        "all_tags": all_tags,
    "badges_by_name": badges_by_name,
    "added_at_map": added_at_map,
    }
    # Session-scoped printing selection (cosmetic only; does not affect
    # owned-card matching/filtering). Mirrors the build wizard's picker.
    sid = request.cookies.get("sid") or new_sid()
    ctx["printings"] = dict(get_session(sid).get("printings") or {})
    ctx["foils"] = dict(get_session(sid).get("foils") or {})
    ctx["_sid"] = sid
    if notice:
        ctx["notice"] = notice
    if error:
        ctx["error"] = error
    return ctx


@router.get("/", response_class=HTMLResponse)
async def owned_index(
    request: Request,
    search: str = Query("", description="Card name search, or Scryfall-style flags (t:/c:/id:/tag:/pow:/tou:/mv:)"),
    sort_by: str = Query("name"),
    filter_tags: list[str] = Query([]),
) -> HTMLResponse:
    ctx = _build_owned_context(request)

    names: list[str] = ctx["names"]
    tags_by_name: dict = ctx.get("tags_by_name") or {}
    type_by_name: dict = ctx.get("type_by_name") or {}
    colors_by_name: dict = ctx.get("colors_by_name") or {}
    added_at_map: dict = ctx.get("added_at_map") or {}
    total_count: int = ctx["count"]

    # Search box: plain name substring, or Scryfall-style flags
    if search:
        stats_map = store.get_stats_map(_user_id(request))
        names = _apply_owned_search(names, search, tags_by_name, type_by_name, colors_by_name, stats_map)

    # Tag filter (AND logic: card must have ALL selected themes)
    for ftag in filter_tags:
        ftag_lower = ftag.lower()
        names = [n for n in names if any(t.lower() == ftag_lower for t in (tags_by_name.get(n) or []))]

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
        "filter_tags": filter_tags,
    })
    had_sid_cookie = bool(request.cookies.get("sid"))
    resp = templates.TemplateResponse("owned/index.html", ctx)
    if not had_sid_cookie:
        try:
            resp.set_cookie("sid", ctx["_sid"], max_age=60 * 60 * 8, httponly=True, samesite="lax")
        except Exception:
            pass
    return resp


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
