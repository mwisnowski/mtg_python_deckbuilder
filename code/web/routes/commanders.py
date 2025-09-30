from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ..app import templates
from ..services.commander_catalog_loader import CommanderRecord, load_commander_catalog
from ..services.theme_catalog_loader import load_index, slugify
from ..services.telemetry import log_commander_page_view

router = APIRouter(prefix="/commanders", tags=["commanders"])

PAGE_SIZE = 20

_WUBRG_ORDER: tuple[str, ...] = ("W", "U", "B", "R", "G")
_COLOR_NAMES: dict[str, str] = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}
_TWO_COLOR_LABELS: dict[str, str] = {
    "WU": "Azorius",
    "UB": "Dimir",
    "BR": "Rakdos",
    "RG": "Gruul",
    "WG": "Selesnya",
    "WB": "Orzhov",
    "UR": "Izzet",
    "BG": "Golgari",
    "WR": "Boros",
    "UG": "Simic",
}
_THREE_COLOR_LABELS: dict[str, str] = {
    "WUB": "Esper",
    "UBR": "Grixis",
    "BRG": "Jund",
    "WRG": "Naya",
    "WUG": "Bant",
    "WBR": "Mardu",
    "WUR": "Jeskai",
    "UBG": "Sultai",
    "URG": "Temur",
    "WBG": "Abzan",
}
_FOUR_COLOR_LABELS: dict[str, str] = {
    "WUBR": "Yore-Tiller",
    "WUBG": "Witch-Maw",
    "WURG": "Ink-Treader",
    "WBRG": "Dune-Brood",
    "UBRG": "Glint-Eye",
}


@dataclass(frozen=True, slots=True)
class CommanderTheme:
    name: str
    slug: str
    summary: str | None


@dataclass(slots=True)
class CommanderView:
    record: CommanderRecord
    color_code: str
    color_label: str
    color_aria_label: str
    themes: tuple[CommanderTheme, ...]
    partner_summary: tuple[str, ...]


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _record_color_code(record: CommanderRecord) -> str:
    code = record.color_identity_key or ""
    if not code and record.is_colorless:
        return "C"
    return code


def _canon_color_code(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.upper()
    seen: set[str] = set()
    ordered: list[str] = []
    for color in _WUBRG_ORDER:
        if color in text:
            seen.add(color)
            ordered.append(color)
    if not ordered and "C" in text:
        return "C"
    return "".join(ordered)


def _color_label_from_code(code: str) -> str:
    if not code:
        return ""
    if code == "C":
        return "Colorless (C)"
    if len(code) == 1:
        base = _COLOR_NAMES.get(code, code)
        return f"{base} ({code})"
    if len(code) == 2:
        label = _TWO_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if len(code) == 3:
        label = _THREE_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if len(code) == 4:
        label = _FOUR_COLOR_LABELS.get(code)
        if label:
            return f"{label} ({code})"
    if code == "WUBRG":
        return "Five-Color (WUBRG)"
    parts = [_COLOR_NAMES.get(ch, ch) for ch in code]
    pretty = " / ".join(parts)
    return f"{pretty} ({code})"


def _color_aria_label(record: CommanderRecord) -> str:
    if record.color_identity:
        names = [_COLOR_NAMES.get(ch, ch) for ch in record.color_identity]
        return ", ".join(names)
    return _COLOR_NAMES.get("C", "Colorless")


def _partner_summary(record: CommanderRecord) -> tuple[str, ...]:
    parts: list[str] = []
    if record.partner_with:
        parts.append("Partner with " + ", ".join(record.partner_with))
    elif record.is_partner:
        parts.append("Partner available")
    if record.supports_backgrounds:
        parts.append("Choose a Background")
    if record.is_background:
        parts.append("Background commander")
    return tuple(parts)


def _record_to_view(record: CommanderRecord, theme_info: Mapping[str, CommanderTheme]) -> CommanderView:
    theme_objs: list[CommanderTheme] = []
    for theme_name in record.themes:
        info = theme_info.get(theme_name)
        if info is not None:
            theme_objs.append(info)
        else:
            slug = slugify(theme_name)
            theme_objs.append(CommanderTheme(name=theme_name, slug=slug, summary=None))
    color_code = _record_color_code(record)
    return CommanderView(
        record=record,
        color_code=color_code,
        color_label=_color_label_from_code(color_code),
        color_aria_label=_color_aria_label(record),
        themes=tuple(theme_objs),
        partner_summary=_partner_summary(record),
    )


def _filter_commanders(records: Iterable[CommanderRecord], q: str | None, color: str | None) -> list[CommanderRecord]:
    items = list(records)
    color_code = _canon_color_code(color)
    if color_code:
        items = [rec for rec in items if _record_color_code(rec) == color_code]
    if q:
        lowered = q.lower().strip()
        if lowered:
            tokens = [tok for tok in lowered.split() if tok]
            if tokens:
                filtered: list[CommanderRecord] = []
                for rec in items:
                    haystack = rec.search_haystack or ""
                    if all(tok in haystack for tok in tokens):
                        filtered.append(rec)
                items = filtered
    return items


def _build_color_options(records: Sequence[CommanderRecord]) -> list[tuple[str, str]]:
    present: set[str] = set()
    for rec in records:
        code = _record_color_code(rec)
        if code:
            present.add(code)
    options: list[tuple[str, str]] = []
    for mono in ("W", "U", "B", "R", "G", "C"):
        if mono in present:
            options.append((mono, _color_label_from_code(mono)))
    combos = sorted((code for code in present if len(code) >= 2), key=lambda c: (len(c), c))
    for code in combos:
        options.append((code, _color_label_from_code(code)))
    return options


def _build_theme_info(records: Sequence[CommanderRecord]) -> dict[str, CommanderTheme]:
    unique_names: set[str] = set()
    for rec in records:
        unique_names.update(rec.themes)
    if not unique_names:
        return {}
    try:
        idx = load_index()
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    info: dict[str, CommanderTheme] = {}
    for name in unique_names:
        try:
            slug = slugify(name)
        except Exception:
            slug = name
        summary: str | None = None
        try:
            data = idx.summary_by_slug.get(slug)
            if data:
                summary = data.get("short_description") or data.get("description")
        except Exception:
            summary = None
        info[name] = CommanderTheme(name=name, slug=slug, summary=summary)
    return info


@router.get("/", response_class=HTMLResponse)
async def commanders_index(
    request: Request,
    q: str | None = Query(default=None, alias="q"),
    color: str | None = Query(default=None, alias="color"),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    entries: Sequence[CommanderRecord] = ()
    error: str | None = None
    try:
        catalog = load_commander_catalog()
        entries = catalog.entries
    except FileNotFoundError:
        error = "Commander catalog is unavailable. Ensure csv_files/commander_cards.csv exists."
    filtered = _filter_commanders(entries, q, color)
    total_filtered = len(filtered)
    page_count = max(1, ceil(total_filtered / PAGE_SIZE)) if total_filtered else 1
    if page > page_count:
        page = page_count
    start_index = (page - 1) * PAGE_SIZE
    end_index = start_index + PAGE_SIZE
    page_records = filtered[start_index:end_index]
    theme_info = _build_theme_info(page_records)
    views = [_record_to_view(rec, theme_info) for rec in page_records]
    color_options = _build_color_options(entries) if entries else []
    page_start = start_index + 1 if total_filtered else 0
    page_end = start_index + len(page_records)
    has_prev = page > 1
    has_next = page < page_count
    canon_color = _canon_color_code(color)

    def _page_url(page_value: int) -> str:
        params: dict[str, str] = {}
        if q:
            params["q"] = q
        if canon_color:
            params["color"] = canon_color
        params["page"] = str(page_value)
        return f"/commanders?{urlencode(params)}"

    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None
    prev_url = _page_url(prev_page) if prev_page else None
    next_url = _page_url(next_page) if next_page else None

    current_path = request.url.path or "/commanders"
    current_query = request.url.query or ""
    if current_query:
        return_url = f"{current_path}?{current_query}"
    else:
        return_url = current_path

    context = {
        "request": request,
        "commanders": views,
        "query": q or "",
        "color": canon_color,
        "color_options": color_options,
        "total_count": len(entries),
        "result_count": len(views),
        "result_total": total_filtered,
        "page": page,
        "page_count": page_count,
        "page_size": PAGE_SIZE,
        "page_start": page_start,
        "page_end": page_end,
        "has_prev": has_prev,
        "has_next": has_next,
        "prev_page": prev_page,
        "next_page": next_page,
        "prev_url": prev_url,
        "next_url": next_url,
        "is_filtered": bool((q or "").strip() or (color or "").strip()),
        "error": error,
        "return_url": return_url,
    }
    template_name = "commanders/list_fragment.html" if _is_htmx(request) else "commanders/index.html"
    try:
        log_commander_page_view(
            request,
            page=page,
            result_total=total_filtered,
            result_count=len(views),
            is_htmx=_is_htmx(request),
        )
    except Exception:
        pass
    return templates.TemplateResponse(template_name, context)
