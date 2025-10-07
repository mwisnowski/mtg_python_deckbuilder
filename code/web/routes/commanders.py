from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import ceil
from typing import Dict, Iterable, Mapping, Sequence, Tuple
from urllib.parse import urlencode
import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ..app import templates
from ..services.commander_catalog_loader import CommanderCatalog, CommanderRecord, load_commander_catalog
from ..services.theme_catalog_loader import load_index, slugify
from ..services.telemetry import log_commander_page_view

router = APIRouter(prefix="/commanders", tags=["commanders"])

PAGE_SIZE = 20
_THEME_MATCH_THRESHOLD = 0.52
_THEME_RECOMMENDATION_FLOOR = 0.35
_THEME_RECOMMENDATION_LIMIT = 6
_MIN_NAME_MATCH_SCORE = 0.8
_WORD_PATTERN = re.compile(r"[a-z0-9]+")

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


@dataclass(frozen=True, slots=True)
class ThemeRecommendation:
    name: str
    score: float


@dataclass(slots=True)
class CommanderFilterCacheEntry:
    records: Tuple[CommanderRecord, ...]
    theme_recommendations: Tuple[ThemeRecommendation, ...]
    page_views: Dict[int, Tuple[CommanderView, ...]]


_FILTER_CACHE_MAX = 48
_FILTER_CACHE: "OrderedDict[tuple[str, str, str, str], CommanderFilterCacheEntry]" = OrderedDict()
_THEME_OPTIONS_CACHE: Dict[str, Tuple[str, ...]] = {}
_COLOR_OPTIONS_CACHE: Dict[str, Tuple[Tuple[str, str], ...]] = {}
_LAST_SEEN_ETAG: str | None = None


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


def _cache_key_for_filters(etag: str, query: str | None, theme_query: str | None, color: str | None) -> tuple[str, str, str, str]:
    def _normalize(text: str | None) -> str:
        return (text or "").strip().lower()

    return (
        etag,
        _normalize(query),
        _normalize(theme_query),
        (color or "").strip().upper(),
    )


def _ensure_catalog_caches(etag: str) -> None:
    global _LAST_SEEN_ETAG
    if _LAST_SEEN_ETAG == etag:
        return
    _LAST_SEEN_ETAG = etag
    _FILTER_CACHE.clear()
    _THEME_OPTIONS_CACHE.clear()
    _COLOR_OPTIONS_CACHE.clear()


def _theme_options_for_catalog(entries: Sequence[CommanderRecord], *, etag: str) -> Tuple[str, ...]:
    cached = _THEME_OPTIONS_CACHE.get(etag)
    if cached is not None:
        return cached
    options = _collect_theme_names(entries)
    result = tuple(options)
    _THEME_OPTIONS_CACHE[etag] = result
    return result


def _color_options_for_catalog(entries: Sequence[CommanderRecord], *, etag: str) -> Tuple[Tuple[str, str], ...]:
    cached = _COLOR_OPTIONS_CACHE.get(etag)
    if cached is not None:
        return cached
    options = tuple(_build_color_options(entries))
    _COLOR_OPTIONS_CACHE[etag] = options
    return options


def _get_cached_filter_entry(
    catalog: CommanderCatalog,
    query: str | None,
    theme_query: str | None,
    canon_color: str | None,
    theme_options: Sequence[str],
) -> CommanderFilterCacheEntry:
    key = _cache_key_for_filters(catalog.etag, query, theme_query, canon_color)
    cached = _FILTER_CACHE.get(key)
    if cached is not None:
        _FILTER_CACHE.move_to_end(key)
        return cached

    filtered = tuple(_filter_commanders(catalog.entries, query, canon_color, theme_query))
    recommendations = tuple(_build_theme_recommendations(theme_query, theme_options))
    entry = CommanderFilterCacheEntry(
        records=filtered,
        theme_recommendations=recommendations,
        page_views={},
    )
    _FILTER_CACHE[key] = entry
    _FILTER_CACHE.move_to_end(key)
    if len(_FILTER_CACHE) > _FILTER_CACHE_MAX:
        _FILTER_CACHE.popitem(last=False)
    return entry


def _color_aria_label(record: CommanderRecord) -> str:
    if record.color_identity:
        names = [_COLOR_NAMES.get(ch, ch) for ch in record.color_identity]
        return ", ".join(names)
    return _COLOR_NAMES.get("C", "Colorless")


def _partner_summary(record: CommanderRecord) -> tuple[str, ...]:
    parts: list[str] = []
    if record.partner_with:
        parts.append("Partner with " + ", ".join(record.partner_with))
    elif getattr(record, "has_plain_partner", False):
        parts.append("Partner available")
    elif record.is_partner:
        parts.append("Partner (restricted)")
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


def _normalize_search_text(value: str | None) -> str:
    if not value:
        return ""
    tokens = _WORD_PATTERN.findall(value.lower())
    if not tokens:
        return ""
    return " ".join(tokens)


def _commander_name_candidates(record: CommanderRecord) -> tuple[str, ...]:
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in (record.display_name, record.face_name, record.name):
        normalized = _normalize_search_text(raw)
        if not normalized:
            continue
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return tuple(candidates)


def _partial_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    length = len(shorter)
    if length == 0:
        return 0.0
    best = 0.0
    window_count = len(longer) - length + 1
    for start in range(max(1, window_count)):
        end = start + length
        if end > len(longer):
            segment = longer[-length:]
        else:
            segment = longer[start:end]
        score = SequenceMatcher(None, shorter, segment).ratio()
        if score > best:
            best = score
            if best >= 0.99:
                break
    return best


def _token_scores(query_tokens: tuple[str, ...], candidate_tokens: tuple[str, ...]) -> tuple[float, float]:
    if not query_tokens or not candidate_tokens:
        return 0.0, 0.0
    totals: list[float] = []
    for token in query_tokens:
        best = 0.0
        for candidate in candidate_tokens:
            score = SequenceMatcher(None, token, candidate).ratio()
            if score > best:
                best = score
                if best >= 0.99:
                    break
        totals.append(best)
    average = sum(totals) / len(totals) if totals else 0.0
    minimum = min(totals) if totals else 0.0
    return average, minimum


def _commander_name_match_score(query: str, record: CommanderRecord) -> float:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return 0.0
    query_tokens = tuple(normalized_query.split())
    best_score = 0.0
    for candidate in _commander_name_candidates(record):
        candidate_tokens = tuple(candidate.split())
        base_score = SequenceMatcher(None, normalized_query, candidate).ratio()
        partial = _partial_ratio(normalized_query, candidate)
        token_average, token_minimum = _token_scores(query_tokens, candidate_tokens)

        substring_bonus = 0.0
        if candidate.startswith(normalized_query):
            substring_bonus = 1.0
        elif query_tokens and all(token in candidate_tokens for token in query_tokens):
            substring_bonus = 0.92
        elif normalized_query in candidate:
            substring_bonus = 0.88
        elif query_tokens and all(token in candidate for token in query_tokens):
            substring_bonus = 0.8
        elif query_tokens and any(token in candidate for token in query_tokens):
            substring_bonus = 0.65

        score = max(base_score, partial, token_average, substring_bonus)
        if query_tokens and token_minimum < 0.45 and not candidate.startswith(normalized_query) and normalized_query not in candidate:
            score = min(score, token_minimum)
        if score > best_score:
            best_score = score
            if best_score >= 0.999:
                break
    return best_score


def _collect_theme_names(records: Sequence[CommanderRecord]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for rec in records:
        for theme_name in rec.themes:
            if not theme_name:
                continue
            if theme_name not in seen:
                seen.add(theme_name)
                ordered.append(theme_name)
    ordered.sort(key=lambda name: name.lower())
    return tuple(ordered)


def _theme_match_score(normalized_query: str, query_tokens: tuple[str, ...], candidate: str) -> float:
    normalized_candidate = _normalize_search_text(candidate)
    if not normalized_candidate:
        return 0.0
    candidate_tokens = tuple(normalized_candidate.split())
    base_score = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
    partial = _partial_ratio(normalized_query, normalized_candidate)
    token_average, token_minimum = _token_scores(query_tokens, candidate_tokens)

    substring_bonus = 0.0
    if normalized_candidate.startswith(normalized_query):
        substring_bonus = 1.0
    elif normalized_query in normalized_candidate:
        substring_bonus = 0.9
    elif query_tokens and all(token in candidate_tokens for token in query_tokens):
        substring_bonus = 0.85
    elif query_tokens and any(token in candidate_tokens for token in query_tokens):
        substring_bonus = 0.7

    score = max(base_score, partial, token_average, substring_bonus)
    if query_tokens and token_minimum < 0.4 and not normalized_candidate.startswith(normalized_query) and normalized_query not in normalized_candidate:
        score = min(score, max(token_minimum, 0.0))
    return score


def _best_theme_match_score(normalized_query: str, query_tokens: tuple[str, ...], record: CommanderRecord) -> float:
    best = 0.0
    for theme_name in record.themes:
        score = _theme_match_score(normalized_query, query_tokens, theme_name)
        if score > best:
            best = score
            if best >= 0.999:
                break
    return best


def _build_theme_recommendations(theme_query: str | None, theme_names: Sequence[str]) -> tuple[ThemeRecommendation, ...]:
    normalized_query = _normalize_search_text(theme_query)
    if not normalized_query:
        return tuple()
    query_tokens = tuple(normalized_query.split())
    scored: list[ThemeRecommendation] = []
    for name in theme_names:
        score = _theme_match_score(normalized_query, query_tokens, name)
        if score <= 0.0:
            continue
        scored.append(ThemeRecommendation(name=name, score=score))
    if not scored:
        return tuple()
    scored.sort(key=lambda item: (-item.score, item.name.lower()))
    filtered = [item for item in scored if item.score >= _THEME_RECOMMENDATION_FLOOR]
    if not filtered:
        filtered = scored
    return tuple(filtered[:_THEME_RECOMMENDATION_LIMIT])


def _filter_commanders(records: Iterable[CommanderRecord], q: str | None, color: str | None, theme: str | None) -> Sequence[CommanderRecord]:
    items: Sequence[CommanderRecord]
    if isinstance(records, Sequence):
        items = records
    else:
        items = tuple(records)

    color_code = _canon_color_code(color)
    if color_code:
        items = [rec for rec in items if _record_color_code(rec) == color_code]

    normalized_query = _normalize_search_text(q)
    if normalized_query and items:
        filtered: list[tuple[float, CommanderRecord]] = []
        for rec in items:
            score = _commander_name_match_score(normalized_query, rec)
            if score >= _MIN_NAME_MATCH_SCORE:
                filtered.append((score, rec))
        if filtered:
            filtered.sort(key=lambda pair: (-pair[0], pair[1].display_name.lower()))
            items = [rec for _, rec in filtered]
        else:
            items = []

    normalized_theme_query = _normalize_search_text(theme)
    if normalized_theme_query and items:
        theme_tokens = tuple(normalized_theme_query.split())
        filtered_by_theme: list[tuple[float, CommanderRecord]] = []
        for rec in items:
            score = _best_theme_match_score(normalized_theme_query, theme_tokens, rec)
            if score >= _THEME_MATCH_THRESHOLD:
                filtered_by_theme.append((score, rec))
        if filtered_by_theme:
            filtered_by_theme.sort(key=lambda pair: (-pair[0], pair[1].display_name.lower()))
            items = [rec for _, rec in filtered_by_theme]
        else:
            items = []

    if isinstance(items, list):
        return items
    return tuple(items)


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
                description = data.get("description") if isinstance(data, dict) else None
                short_description = data.get("short_description") if isinstance(data, dict) else None
                summary = description or short_description
                if (summary is None or not summary.strip()) and short_description:
                    summary = short_description
        except Exception:
            summary = None
        info[name] = CommanderTheme(name=name, slug=slug, summary=summary)
    return info


@router.get("/", response_class=HTMLResponse)
async def commanders_index(
    request: Request,
    q: str | None = Query(default=None, alias="q"),
    theme: str | None = Query(default=None, alias="theme"),
    color: str | None = Query(default=None, alias="color"),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    catalog: CommanderCatalog | None = None
    entries: Sequence[CommanderRecord] = ()
    error: str | None = None
    try:
        catalog = load_commander_catalog()
        entries = catalog.entries
        _ensure_catalog_caches(catalog.etag)
    except FileNotFoundError:
        error = "Commander catalog is unavailable. Ensure csv_files/commander_cards.csv exists."
    except Exception:
        error = "Commander catalog failed to load. Check server logs."

    theme_query = (theme or "").strip()
    query_value = (q or "").strip()
    canon_color = _canon_color_code(color)

    theme_names: Tuple[str, ...] = ()
    color_options: Tuple[Tuple[str, str], ...] | list[Tuple[str, str]] = ()
    filter_entry: CommanderFilterCacheEntry | None = None
    total_filtered = 0
    page_count = 1
    page_records: Sequence[CommanderRecord] = ()
    views: Tuple[CommanderView, ...] = ()
    theme_recommendations: Tuple[ThemeRecommendation, ...] = ()

    if catalog is not None:
        theme_names = _theme_options_for_catalog(entries, etag=catalog.etag)
        color_options = _color_options_for_catalog(entries, etag=catalog.etag)
        filter_entry = _get_cached_filter_entry(
            catalog,
            query_value,
            theme_query,
            canon_color,
            theme_names,
        )
        total_filtered = len(filter_entry.records)
        page_count = max(1, ceil(total_filtered / PAGE_SIZE)) if total_filtered else 1
        if page > page_count:
            page = page_count
        if page < 1:
            page = 1
        start_index = (page - 1) * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        page_records = filter_entry.records[start_index:end_index]
        cached_views = filter_entry.page_views.get(page) if filter_entry else None
        if cached_views is None:
            theme_info = _build_theme_info(page_records)
            computed_views = tuple(_record_to_view(rec, theme_info) for rec in page_records)
            if filter_entry is not None:
                filter_entry.page_views[page] = computed_views
                if len(filter_entry.page_views) > 6:
                    oldest_key = next(iter(filter_entry.page_views))
                    if oldest_key != page:
                        filter_entry.page_views.pop(oldest_key, None)
            views = computed_views
        else:
            views = cached_views
        theme_recommendations = filter_entry.theme_recommendations
    else:
        page = 1
        start_index = 0
        end_index = 0

    page_start = start_index + 1 if total_filtered else 0
    page_end = start_index + len(page_records)
    has_prev = page > 1
    has_next = page < page_count
    canon_color = _canon_color_code(color)

    def _page_url(page_value: int) -> str:
        params: dict[str, str] = {}
        if q:
            params["q"] = q
        if theme_query:
            params["theme"] = theme_query
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
        "query": query_value,
        "theme_query": theme_query,
        "color": canon_color,
        "color_options": list(color_options) if color_options else [],
        "theme_options": theme_names,
        "theme_recommendations": theme_recommendations,
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
        "is_filtered": bool((q or "").strip() or (color or "").strip() or theme_query),
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

@router.get("", response_class=HTMLResponse)
async def commanders_index_alias(
    request: Request,
    q: str | None = Query(default=None, alias="q"),
    theme: str | None = Query(default=None, alias="theme"),
    color: str | None = Query(default=None, alias="color"),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    return await commanders_index(request, q=q, theme=theme, color=color, page=page)


def prewarm_default_page() -> None:
    """Prime the commander catalog caches for the default (no-filter) view."""

    try:
        catalog = load_commander_catalog()
    except Exception:
        return

    try:
        _ensure_catalog_caches(catalog.etag)
        theme_options = _theme_options_for_catalog(catalog.entries, etag=catalog.etag)
        entry = _get_cached_filter_entry(catalog, "", "", "", theme_options)
        if 1 not in entry.page_views:
            page_records = entry.records[:PAGE_SIZE]
            theme_info = _build_theme_info(page_records)
            entry.page_views[1] = tuple(_record_to_view(rec, theme_info) for rec in page_records)
    except Exception:
        return
