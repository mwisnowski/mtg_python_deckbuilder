from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from pathlib import Path
import csv
import io
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ..app import templates
from ..services.orchestrator import tags_for_commander
from ..services.summary_utils import format_theme_label, format_theme_list, summary_ctx
from ..services.user_db import get_user_by_id, get_user_by_username
from ..services.deck_visibility import (
    DEFAULT_VISIBILITY,
    VALID_VISIBILITIES,
    get_deck_visibility as _get_deck_visibility_by_path,
    set_deck_visibility as _set_deck_visibility_by_path,
)
from ..app import ENABLE_BUDGET_MODE, ENABLE_PREFETCH


router = APIRouter(prefix="/decks")


def _user_id(request: Request) -> str:
    """Return the scoped directory name for the current user.

    Authenticated users get their UUID; everyone else (including guest) uses 'guest'.
    """
    u = getattr(request.state, "current_user", None)
    if u and not u.get("is_guest") and u.get("id"):
        return str(u["id"])
    return "guest"


def _deck_dir(user_id: str = "guest") -> Path:
    # Prefer explicit env var if provided, else default to ./deck_files/{user_id}
    p = os.getenv("DECK_EXPORTS")
    if p:
        return (Path(p) / user_id).resolve()
    return (Path.cwd() / "deck_files" / user_id).resolve()


def _list_from_dir(d: Path) -> list[dict]:
    """Read CSV deck entries from a single directory."""
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    items: list[dict] = []
    for p in sorted(d.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        meta: dict = {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime}
        stem = p.stem
        txt = p.with_suffix('.txt')
        if txt.exists():
            meta["txt_name"] = txt.name
            meta["txt_path"] = str(txt)
        sidecar = p.with_suffix('.summary.json')
        if sidecar.exists():
            try:
                import json as _json
                payload = _json.loads(sidecar.read_text(encoding='utf-8'))
                _m = payload.get('meta', {}) if isinstance(payload, dict) else {}
                meta["commander"] = _m.get('commander') or meta.get("commander")
                meta["tags"] = _m.get('tags') or meta.get("tags") or []
                if _m.get('name'):
                    meta["display"] = _m.get('name')
                if _m.get('source'):
                    meta["source"] = _m.get('source')
            except Exception:
                pass
        meta["visibility"] = _get_deck_visibility_by_path(p)
        if not meta.get("commander"):
            parts = stem.split('_')
            if len(parts) >= 3:
                meta["commander"] = parts[0]
                meta["tags"] = parts[1:-1]
            else:
                meta["commander"] = stem
                meta["tags"] = []
        items.append(meta)
    return items


def _list_decks(user_id: str = "guest") -> list[dict]:
    """Return decks from the user-scoped directory."""
    return _list_from_dir(_deck_dir(user_id))


def _list_guest_decks() -> list[dict]:
    """Return decks from the shared guest directory (visible to all users)."""
    return _list_from_dir(_deck_dir("guest"))


def _list_legacy_decks() -> list[dict]:
    """Return CSV files sitting directly in the root deck_files/ directory.

    These are pre-auth builds that landed in the root before user accounts
    were introduced.  They are visible to everyone.
    """
    root = Path(os.getenv("DECK_EXPORTS") or "deck_files").resolve()
    if not root.exists():
        return []
    # Only files directly in root (not in sub-dirs like guest/ or uuid/)
    return _list_from_dir(root)


def _deck_base_for_section(uid: str, section: str) -> Path:
    """Return the validated base directory for a given section key."""
    if section == "guest":
        return _deck_dir("guest")
    if section == "legacy":
        return Path(os.getenv("DECK_EXPORTS") or "deck_files").resolve()
    return _deck_dir(uid)  # "mine" or unrecognised → user's own dir


def _check_deck_access(request: Request, owner_user_id: str, deck_name: str) -> bool:
    """Return True if the current requester may view/download this deck.

    Owner and admins are always allowed. Public and unlisted decks are
    accessible to anyone with the URL (guests included). Private decks are
    only accessible to the owner/admin. Callers should 404 (never 403) on
    denial so deck existence is never revealed to non-owners.
    """
    uid = _user_id(request)
    user = getattr(request.state, "current_user", None)
    if uid == owner_user_id or bool(user and user.get("is_admin")):
        return True
    visibility = _get_deck_visibility_by_path(_deck_dir(owner_user_id) / deck_name)
    return visibility in ("public", "unlisted")


def get_deck_visibility(user_id: str, deck_name: str) -> str:
    """Return a deck's visibility ('public'|'unlisted'|'private') for the given owner.

    Missing sidecar or visibility key defaults to 'private'.
    """
    return _get_deck_visibility_by_path(_deck_dir(user_id) / deck_name)


def set_deck_visibility(user_id: str, deck_name: str, visibility: str) -> None:
    """Set a deck's visibility for the given owner.

    Raises ValueError for an invalid visibility value, FileNotFoundError if
    the deck's sidecar does not exist.
    """
    _set_deck_visibility_by_path(_deck_dir(user_id) / deck_name, visibility)


_PUBLIC_DECKS_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_PUBLIC_DECKS_CACHE_TTL = 60.0


def _scan_public_decks() -> List[dict]:
    """Scan every user's deck directory for public decks. No caching here."""
    root = Path(os.getenv("DECK_EXPORTS") or "deck_files").resolve()
    if not root.exists():
        return []
    items: List[dict] = []
    for user_dir in root.iterdir():
        if not user_dir.is_dir() or user_dir.name == "guest":
            continue  # guest decks are always private (M1 design decision)
        user_id = user_dir.name
        try:
            owner = get_user_by_id(user_id)
        except Exception:
            owner = None
        username = owner.get("username") if owner else None
        if not username:
            continue  # can't build a shareable URL without a known username
        for sidecar in user_dir.glob("*.summary.json"):
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            meta = payload.get("meta") if isinstance(payload, dict) else None
            if not isinstance(meta, dict) or meta.get("visibility") != "public":
                continue
            try:
                mtime = sidecar.stat().st_mtime
            except Exception:
                mtime = 0.0
            csv_name = sidecar.name[: -len(".summary.json")] + ".csv"
            has_txt = (user_dir / (sidecar.name[: -len(".summary.json")] + ".txt")).exists()
            items.append({
                "user_id": user_id,
                "username": username,
                "name": csv_name,
                "commander": meta.get("commander") or "",
                "tags": list(meta.get("tags") or []),
                "display": meta.get("name") or "",
                "mtime": mtime,
                "has_txt": has_txt,
            })
    return items


def list_public_decks(exclude_user_id: str, limit: int = 20) -> List[dict]:
    """Return public decks from all users (excluding ``exclude_user_id``).

    Results are cached in memory for 60s to avoid repeated filesystem scans;
    sorted by most recently modified first and capped at ``limit``.
    """
    now = time.time()
    cached = _PUBLIC_DECKS_CACHE.get("data")
    if cached is None or (now - _PUBLIC_DECKS_CACHE.get("ts", 0.0)) >= _PUBLIC_DECKS_CACHE_TTL:
        cached = _scan_public_decks()
        _PUBLIC_DECKS_CACHE["data"] = cached
        _PUBLIC_DECKS_CACHE["ts"] = now
    filtered = [it for it in cached if it["user_id"] != exclude_user_id]
    filtered.sort(key=lambda it: it.get("mtime", 0), reverse=True)
    return filtered[:limit]


def _index_sections(uid: str) -> list[dict]:
    """Build the ordered sections list for the deck index page."""
    is_guest = uid == "guest"
    sections = []

    my_decks = _list_decks(uid)
    sections.append({
        "id": "mine",
        "label": "Decks" if is_guest else "My Decks",
        "subtitle": None if is_guest else "Decks built with your account.",
        "decks": my_decks,
    })

    public_decks = list_public_decks(exclude_user_id=uid)
    if public_decks:
        sections.append({
            "id": "others",
            "label": "Other Users' Decks",
            "subtitle": "Public decks shared by other users.",
            "decks": public_decks,
        })

    if not is_guest:
        guest_decks = _list_guest_decks()
        if guest_decks:
            sections.append({
                "id": "guest",
                "label": "Community Builds",
                "subtitle": "Decks built while not logged in — visible to everyone.",
                "decks": guest_decks,
            })

    legacy_decks = _list_legacy_decks()
    if legacy_decks:
        # For legacy, exclude any files that are already the user's own deck (same filename)
        my_names = {d["name"] for d in my_decks}
        guest_names = {d["name"] for sec in sections if sec["id"] == "guest" for d in sec["decks"]}
        filtered = [d for d in legacy_decks if d["name"] not in my_names and d["name"] not in guest_names]
        if filtered:
            sections.append({
                "id": "legacy",
                "label": "Legacy Decks",
                "subtitle": "Decks from before user accounts were added — visible to everyone.",
                "decks": filtered,
            })

    return sections


def _safe_within(base: Path, target: Path) -> bool:
    try:
        base_r = base.resolve()
        targ_r = target.resolve()
        return (base_r == targ_r) or (base_r in targ_r.parents)
    except Exception:
        return False


def _read_csv_summary(csv_path: Path) -> Tuple[dict, Dict[str, int], Dict[str, int], Dict[str, List[dict]]]:
    """Parse CSV export to reconstruct minimal summary pieces.

    Returns: (meta, type_counts, curve_counts, type_cards)
      meta: { 'commander': str, 'colors': [..] }
    """
    headers = []
    type_counts: Dict[str, int] = {}
    type_cards: Dict[str, List[dict]] = {}
    curve_bins = ['0','1','2','3','4','5','6+']
    curve_counts: Dict[str, int] = {b: 0 for b in curve_bins}
    curve_cards: Dict[str, List[dict]] = {b: [] for b in curve_bins}
    meta: dict = {"commander": "", "colors": []}
    commander_seen = False
    # Infer commander from filename stem (pattern Commander_Themes_YYYYMMDD)
    stem_parts = csv_path.stem.split('_')
    inferred_commander = stem_parts[0] if stem_parts else ''

    def classify_mv(raw) -> str:
        try:
            v = float(raw)
        except Exception:
            v = 0.0
        return '6+' if v >= 6 else str(int(v))

    try:
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            # Expected columns include: Name, Count, Type, ManaCost, ManaValue, Colors, Power, Toughness, Role, ..., Tags, Text, Owned
            name_idx = headers.index('Name') if 'Name' in headers else 0
            count_idx = headers.index('Count') if 'Count' in headers else 1
            type_idx = headers.index('Type') if 'Type' in headers else 2
            mv_idx = headers.index('ManaValue') if 'ManaValue' in headers else (headers.index('Mana Value') if 'Mana Value' in headers else -1)
            role_idx = headers.index('Role') if 'Role' in headers else -1
            tags_idx = headers.index('Tags') if 'Tags' in headers else -1
            colors_idx = headers.index('Colors') if 'Colors' in headers else -1

            for row in reader:
                if not row:
                    continue
                try:
                    name = row[name_idx]
                except Exception:
                    continue
                try:
                    cnt = int(float(row[count_idx])) if row[count_idx] else 1
                except Exception:
                    cnt = 1
                type_line = row[type_idx] if type_idx >= 0 and type_idx < len(row) else ''
                role = (row[role_idx] if role_idx >= 0 and role_idx < len(row) else '')
                tags = (row[tags_idx] if tags_idx >= 0 and tags_idx < len(row) else '')
                tags_list = [t.strip() for t in tags.split(';') if t.strip()]

                # Commander detection: prefer filename inference; else best-effort via type line containing 'Commander'
                is_commander = (inferred_commander and name == inferred_commander)
                if not is_commander:
                    is_commander = isinstance(type_line, str) and ('commander' in type_line.lower())
                if is_commander and not commander_seen:
                    meta['commander'] = name
                    commander_seen = True

                # Map type_line to broad category
                tl = (type_line or '').lower()
                if 'battle' in tl:
                    cat = 'Battle'
                elif 'planeswalker' in tl:
                    cat = 'Planeswalker'
                elif 'creature' in tl:
                    cat = 'Creature'
                elif 'instant' in tl:
                    cat = 'Instant'
                elif 'sorcery' in tl:
                    cat = 'Sorcery'
                elif 'artifact' in tl:
                    cat = 'Artifact'
                elif 'enchantment' in tl:
                    cat = 'Enchantment'
                elif 'land' in tl:
                    cat = 'Land'
                else:
                    cat = 'Other'

                # Type counts/cards (exclude commander entry from distribution)
                if not is_commander:
                    type_counts[cat] = type_counts.get(cat, 0) + cnt
                    # M5: Extract metadata tags column if present
                    metadata_tags_raw = ''
                    metadata_idx = headers.index('MetadataTags') if 'MetadataTags' in headers else -1
                    if metadata_idx >= 0 and metadata_idx < len(row):
                        metadata_tags_raw = row[metadata_idx] or ''
                    metadata_tags_list = [t.strip() for t in metadata_tags_raw.split(';') if t.strip()]
                    type_cards.setdefault(cat, []).append({
                        'name': name,
                        'count': cnt,
                        'role': role,
                        'tags': tags_list,
                        'metadata_tags': metadata_tags_list,  # M5: Include metadata tags
                    })

                # Curve
                if mv_idx >= 0 and mv_idx < len(row):
                    bucket = classify_mv(row[mv_idx])
                    if bucket not in curve_counts:
                        bucket = '6+'
                    curve_counts[bucket] += cnt
                    curve_cards[bucket].append({'name': name, 'count': cnt})

                # Colors (from Colors col for commander/overall)
                if is_commander and colors_idx >= 0 and colors_idx < len(row):
                    cid = row[colors_idx] or ''
                    if isinstance(cid, str):
                        meta['colors'] = list(cid)
    except Exception:
        pass

    # Precedence ordering
    precedence_order = [
        'Battle', 'Planeswalker', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land', 'Other'
    ]
    prec_index = {k: i for i, k in enumerate(precedence_order)}
    type_order = sorted(type_counts.keys(), key=lambda k: prec_index.get(k, 999))

    summary = {
        'type_breakdown': {
            'counts': type_counts,
            'order': type_order,
            'cards': type_cards,
            'total': sum(type_counts.values()),
        },
        'pip_distribution': {
            # Not recoverable from CSV without mana symbols; leave zeros
            'counts': {c: 0 for c in ('W','U','B','R','G')},
            'weights': {c: 0 for c in ('W','U','B','R','G')},
        },
        'mana_generation': {
            # Not recoverable from CSV alone
            'W': 0, 'U': 0, 'B': 0, 'R': 0, 'G': 0, 'total_sources': 0,
        },
        'mana_curve': {
            **curve_counts,
            'total_spells': sum(curve_counts.values()),
            'cards': curve_cards,
        },
        'colors': meta.get('colors', []),
    }
    return summary, type_counts, curve_counts, type_cards


def _read_deck_counts(csv_path: Path) -> Dict[str, int]:
    """Read a CSV deck export and return a mapping of card name -> total count.

    Falls back to zero on parse issues; ignores header case and missing columns.
    """
    counts: Dict[str, int] = {}
    try:
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            name_idx = headers.index('Name') if 'Name' in headers else 0
            count_idx = headers.index('Count') if 'Count' in headers else 1
            for row in reader:
                if not row:
                    continue
                try:
                    name = row[name_idx]
                except Exception:
                    continue
                try:
                    cnt = int(float(row[count_idx])) if row[count_idx] else 1
                except Exception:
                    cnt = 1
                name = str(name).strip()
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + cnt
    except Exception:
        pass
    return counts


@router.get("/", response_class=HTMLResponse)
async def decks_index(request: Request) -> HTMLResponse:
    uid = _user_id(request)
    return templates.TemplateResponse("decks/index.html", {"request": request, "sections": _index_sections(uid)})


@router.get("/view", response_class=HTMLResponse)
async def decks_view(request: Request, name: str, section: str = "mine") -> HTMLResponse:
    uid = _user_id(request)
    base = _deck_base_for_section(uid, section)
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return templates.TemplateResponse("decks/index.html", {"request": request, "sections": _index_sections(uid), "error": "Deck not found."})

    # "legacy" decks predate visibility/ownership; treat as always accessible.
    owner_user_id = None if section == "legacy" else (uid if section == "mine" else "guest")
    if owner_user_id and not _check_deck_access(request, owner_user_id, name):
        return templates.TemplateResponse(
            "decks/index.html",
            {"request": request, "sections": _index_sections(uid), "error": "Deck not found."},
            status_code=404,
        )

    is_owner = bool(owner_user_id) and owner_user_id == uid and uid != "guest"
    owner_username: Optional[str] = None
    if is_owner:
        user = getattr(request.state, "current_user", None)
        owner_username = user.get("username") if user else None

    return _render_deck_view(
        request,
        uid,
        p,
        owner_user_id=owner_user_id or "guest",
        is_owner=is_owner,
        owner_username=owner_username,
    )


@router.get("/{username}/{deck_name}", response_class=HTMLResponse)
async def decks_view_by_username(request: Request, username: str, deck_name: str) -> HTMLResponse:
    """Namespaced deck view: resolves `username` to an owner and renders their deck."""
    uid = _user_id(request)
    owner = get_user_by_username(username)
    if not owner:
        return templates.TemplateResponse(
            "decks/index.html",
            {"request": request, "sections": _index_sections(uid), "error": "Deck not found."},
            status_code=404,
        )
    owner_user_id = str(owner["id"])
    base = _deck_dir(owner_user_id)
    p = (base / deck_name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return templates.TemplateResponse(
            "decks/index.html",
            {"request": request, "sections": _index_sections(uid), "error": "Deck not found."},
            status_code=404,
        )
    if not _check_deck_access(request, owner_user_id, deck_name):
        return templates.TemplateResponse(
            "decks/private_notice.html",
            {"request": request},
            status_code=403,
        )
    is_owner = (owner_user_id == uid) and uid != "guest"
    return _render_deck_view(
        request,
        uid,
        p,
        owner_user_id=owner_user_id,
        is_owner=is_owner,
        owner_username=str(owner["username"]),
    )


def _render_deck_view(
    request: Request,
    uid: str,
    p: Path,
    *,
    owner_user_id: str,
    is_owner: bool,
    owner_username: Optional[str] = None,
) -> HTMLResponse:
    """Build and render the deck-view template for an already-access-checked deck path."""
    # Try to load sidecar summary JSON first
    summary = None
    commander_name = ''
    tags: List[str] = []
    meta_info: Dict[str, Any] = {}
    sidecar = p.with_suffix('.summary.json')
    if sidecar.exists():
        try:
            import json as _json
            payload = _json.loads(sidecar.read_text(encoding='utf-8'))
            if isinstance(payload, dict):
                summary = payload.get('summary')
                meta = payload.get('meta', {})
                if isinstance(meta, dict):
                    meta_info = meta
                    commander_name = meta.get('commander') or ''
                    _tags = meta.get('tags') or []
                    if isinstance(_tags, list):
                        tags = [str(t) for t in _tags]
                    display_name = meta.get('name') or ''
        except Exception:
            summary = None
            display_name = ''
    if not summary:
        # Reconstruct minimal summary from CSV
        summary, _tc, _cc, _tcs = _read_csv_summary(p)
        display_name = ''
    stem = p.stem
    txt_path = p.with_suffix('.txt')
    # If missing still, infer from filename stem
    if not commander_name:
        parts = stem.split('_')
        commander_name = parts[0] if parts else ''

    ctx = {
        "request": request,
        "name": p.name,
        "csv_path": str(p),
        "txt_path": str(txt_path) if txt_path.exists() else None,
        "summary": summary,
        "commander": commander_name,
        "tags": tags,
        "display_name": display_name,
        "is_owner": is_owner,
        "owner_user_id": owner_user_id,
        "deck_visibility": _get_deck_visibility_by_path(p),
        "visibility_options": VALID_VISIBILITIES,
        "share_url": f"/decks/{owner_username}/{p.name}" if owner_username else None,
    }
    ctx.update(summary_ctx(summary=summary, commander=commander_name, tags=tags, meta=meta_info))

    def _extend_sources(values: list[Any], candidate: Any) -> None:
        if isinstance(candidate, list):
            values.extend(candidate)
        elif isinstance(candidate, tuple):
            values.extend(list(candidate))
        elif isinstance(candidate, str):
            values.append(candidate)

    deck_theme_sources: list[Any] = list(ctx.get("synergies") or tags or [])
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
        commander_meta = meta_info.get("commander", {})
        if isinstance(commander_meta, dict):
            _extend_sources(commander_theme_sources, commander_meta.get("tags"))
            _extend_sources(commander_theme_sources, commander_meta.get("themes"))
    commander_theme_tags = format_theme_list(commander_theme_sources)
    if not commander_theme_tags and commander_name:
        commander_theme_tags = format_theme_list(tags_for_commander(commander_name))

    combined_tags: list[str] = []
    combined_seen: set[str] = set()
    for collection in (commander_theme_tags, deck_theme_tags):
        for label in collection:
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

    commander_tag_slugs = []
    slug_seen: set[str] = set()
    for label in combined_tags:
        slug = " ".join(str(label or "").strip().lower().split())
        if not slug or slug in slug_seen:
            continue
        slug_seen.add(slug)
        commander_tag_slugs.append(slug)

    reason_bits: list[str] = []
    if deck_theme_tags:
        reason_bits.append("Deck themes: " + ", ".join(deck_theme_tags))
    if commander_theme_tags:
        reason_bits.append("Commander tags: " + ", ".join(commander_theme_tags))
    commander_reason_text = "; ".join(reason_bits)

    ctx.update(
        {
            "deck_theme_tags": deck_theme_tags,
            "commander_theme_tags": commander_theme_tags,
            "commander_combined_tags": combined_tags,
            "commander_tag_slugs": commander_tag_slugs,
            "commander_reason_text": commander_reason_text,
            "commander_overlap_tags": overlap_tags,
            "commander_role_label": format_theme_label("Commander"),
        }
    )

    # Budget evaluation (only when budget_config is stored in the sidecar meta)
    if ENABLE_BUDGET_MODE:
        budget_config = meta_info.get("budget_config") if isinstance(meta_info, dict) else None
        if isinstance(budget_config, dict) and budget_config.get("total"):
            try:
                from ..services.budget_evaluator import BudgetEvaluatorService
                card_counts = _read_deck_counts(p)
                decklist = list(card_counts.keys())
                color_identity = meta_info.get("color_identity") if isinstance(meta_info, dict) else None
                include_cards = list(meta_info.get("include_cards") or []) if isinstance(meta_info, dict) else []
                svc = BudgetEvaluatorService()
                budget_report = svc.evaluate_deck(
                    decklist=decklist,
                    budget_total=float(budget_config["total"]),
                    mode=str(budget_config.get("mode", "soft")),
                    card_ceiling=float(budget_config["card_ceiling"]) if budget_config.get("card_ceiling") else None,
                    color_identity=color_identity,
                    include_cards=include_cards or None,
                )
                ctx["budget_report"] = budget_report
                ctx["budget_config"] = budget_config
                # M8: Price charts
                try:
                    from ..services.budget_evaluator import compute_price_category_breakdown, compute_price_histogram
                    _breakdown = budget_report.get("price_breakdown") or []
                    _card_tags: Dict[str, List[str]] = {}
                    if isinstance(summary, dict):
                        _tb = (summary.get("type_breakdown") or {}).get("cards") or {}
                        for _clist in _tb.values():
                            for _c in (_clist or []):
                                if isinstance(_c, dict) and _c.get("name"):
                                    _card_tags[_c["name"]] = list(_c.get("tags") or [])
                    _enriched = [{**item, "tags": _card_tags.get(item.get("card", ""), [])} for item in _breakdown]
                    ctx["price_category_chart"] = compute_price_category_breakdown(_enriched)
                    ctx["price_histogram_chart"] = compute_price_histogram(_breakdown)
                except Exception:
                    pass
            except Exception:
                pass

    resp = templates.TemplateResponse("decks/view.html", ctx)
    if ENABLE_PREFETCH:
        resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
    return resp


@router.get("/compare", response_class=HTMLResponse)
async def decks_compare(request: Request, A: Optional[str] = None, B: Optional[str] = None) -> HTMLResponse:
    """
    Compare two finished deck CSVs and show diffs.

    Query params:
      - A: filename of first deck (e.g., Alena_..._20250827.csv)
      - B: filename of second deck
    """
    uid = _user_id(request)
    base = _deck_dir(uid)
    items = _list_decks(uid)
    # Build select options with friendly display labels
    options: List[Dict[str, str]] = []
    for it in items:
        label = it.get("display") or it.get("commander") or it.get("name")
        # Include mtime for "Latest two" selection refinement
        mt = it.get("mtime", 0)
        try:
            mt_val = str(int(mt))
        except Exception:
            mt_val = "0"
        options.append({"name": it.get("name"), "label": label, "mtime": mt_val})

    diffs = None
    metaA: Dict[str, str] = {}
    metaB: Dict[str, str] = {}
    if A and B:
        pA = (base / A)
        pB = (base / B)
        if _safe_within(base, pA) and _safe_within(base, pB) and pA.exists() and pB.exists():
            ca = _read_deck_counts(pA)
            cb = _read_deck_counts(pB)
            setA = set(ca.keys())
            setB = set(cb.keys())
            onlyA = sorted(list(setA - setB))
            onlyB = sorted(list(setB - setA))
            changed: List[Tuple[str, int, int]] = []
            for n in sorted(setA & setB):
                if ca.get(n, 0) != cb.get(n, 0):
                    changed.append((n, ca.get(n, 0), cb.get(n, 0)))
            # Side meta (commander/name/tags) if available
            def _meta_for(path: Path) -> Dict[str, str]:
                out: Dict[str, str] = {"filename": path.name}
                sc = path.with_suffix('.summary.json')
                try:
                    if sc.exists():
                        import json as _json
                        payload = _json.loads(sc.read_text(encoding='utf-8'))
                        if isinstance(payload, dict):
                            m = payload.get('meta', {}) or {}
                            out["display"] = (m.get('name') or '')
                            out["commander"] = (m.get('commander') or '')
                            out["tags"] = ', '.join(m.get('tags') or [])
                except Exception:
                    pass
                if not out.get("commander"):
                    parts = path.stem.split('_')
                    if parts:
                        out["commander"] = parts[0]
                return out
            metaA = _meta_for(pA)
            metaB = _meta_for(pB)
            diffs = {
                "onlyA": onlyA,
                "onlyB": onlyB,
                "changed": changed,
                "A": A,
                "B": B,
            }

    return templates.TemplateResponse(
        "decks/compare.html",
        {
            "request": request,
            "options": options,
            "A": A or "",
            "B": B or "",
            "diffs": diffs,
            "metaA": metaA,
            "metaB": metaB,
        },
    )


@router.get("/pickups", response_class=HTMLResponse)
async def decks_pickups(request: Request, name: str) -> HTMLResponse:
    """Show the pickups list for a deck that was built with budget mode enabled."""
    uid = _user_id(request)
    base = _deck_dir(uid)
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return templates.TemplateResponse(
            "decks/index.html",
            {"request": request, "sections": _index_sections(uid), "error": "Deck not found."},
        )

    meta_info: Dict[str, Any] = {}
    commander_name = ""
    sidecar = p.with_suffix(".summary.json")
    if sidecar.exists():
        try:
            import json as _json
            payload = _json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                meta_info = payload.get("meta") or {}
                commander_name = meta_info.get("commander") or ""
        except Exception:
            pass

    budget_config = meta_info.get("budget_config") if isinstance(meta_info, dict) else None
    budget_report = None
    error_msg = None

    if not ENABLE_BUDGET_MODE:
        error_msg = "Budget mode is not enabled (set ENABLE_BUDGET_MODE=1)."
    elif not isinstance(budget_config, dict) or not budget_config.get("total"):
        error_msg = "Budget mode was not enabled when this deck was built."
    else:
        try:
            from ..services.budget_evaluator import BudgetEvaluatorService
            card_counts = _read_deck_counts(p)
            decklist = list(card_counts.keys())
            color_identity = meta_info.get("color_identity") if isinstance(meta_info, dict) else None
            include_cards = list(meta_info.get("include_cards") or []) if isinstance(meta_info, dict) else []
            svc = BudgetEvaluatorService()
            budget_report = svc.evaluate_deck(
                decklist=decklist,
                budget_total=float(budget_config["total"]),
                mode=str(budget_config.get("mode", "soft")),
                card_ceiling=float(budget_config["card_ceiling"]) if budget_config.get("card_ceiling") else None,
                color_identity=color_identity,
                include_cards=include_cards or None,
            )
        except Exception as exc:
            error_msg = f"Budget evaluation failed: {exc}"

    stale_prices: set[str] = set()
    stale_prices_global = False
    try:
        from ..services.price_service import get_price_service
        from code.settings import PRICE_STALE_WARNING_HOURS
        _psvc = get_price_service()
        _psvc._ensure_loaded()
        if PRICE_STALE_WARNING_HOURS > 0:
            _stale = _psvc.get_stale_cards(PRICE_STALE_WARNING_HOURS)
            if _stale and len(_stale) > len(_psvc._cache) * 0.5:
                stale_prices_global = True
            else:
                stale_prices = _stale
    except Exception:
        pass

    owned: set[str] = set()
    try:
        from ..services.build_utils import owned_set as _owned_set
        owned = _owned_set()
    except Exception:
        pass

    return templates.TemplateResponse(
        "decks/pickups.html",
        {
            "request": request,
            "name": p.name,
            "commander": commander_name,
            "budget_config": budget_config,
            "budget_report": budget_report,
            "error": error_msg,
            "stale_prices": stale_prices,
            "stale_prices_global": stale_prices_global,
            "owned_names": owned,
        },
    )


@router.get("/download-csv")
async def decks_download_csv(request: Request, name: str, section: str = "mine") -> Response:
    """Serve a CSV export with live prices fetched at download time."""
    uid = _user_id(request)
    base = _deck_base_for_section(uid, section)
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return HTMLResponse("File not found", status_code=404)
    owner_user_id = None if section == "legacy" else (uid if section == "mine" else "guest")
    if owner_user_id and not _check_deck_access(request, owner_user_id, name):
        return HTMLResponse("File not found", status_code=404)
    return _build_csv_download_response(p)


@router.get("/{username}/{deck_name}/download")
async def decks_download_csv_by_username(request: Request, username: str, deck_name: str) -> Response:
    """Namespaced CSV download: resolves `username` to an owner and serves their deck."""
    owner = get_user_by_username(username)
    if not owner:
        return HTMLResponse("File not found", status_code=404)
    owner_user_id = str(owner["id"])
    if not _check_deck_access(request, owner_user_id, deck_name):
        return HTMLResponse("File not found", status_code=404)
    base = _deck_dir(owner_user_id)
    p = (base / deck_name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return HTMLResponse("File not found", status_code=404)
    return _build_csv_download_response(p)


@router.get("/{username}/{deck_name}/download-txt")
async def decks_download_txt_by_username(request: Request, username: str, deck_name: str) -> Response:
    """Namespaced TXT download: resolves `username` to an owner and serves their deck's TXT export."""
    owner = get_user_by_username(username)
    if not owner:
        return HTMLResponse("File not found", status_code=404)
    owner_user_id = str(owner["id"])
    if not _check_deck_access(request, owner_user_id, deck_name):
        return HTMLResponse("File not found", status_code=404)
    base = _deck_dir(owner_user_id)
    p = (base / deck_name).resolve()
    txt_p = p.with_suffix(".txt")
    if not _safe_within(base, txt_p) or not (txt_p.exists() and txt_p.is_file() and txt_p.suffix.lower() == ".txt"):
        return HTMLResponse("File not found", status_code=404)
    return Response(
        content=txt_p.read_bytes(),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{txt_p.name}"'},
    )


def _build_csv_download_response(p: Path) -> Response:
    """Read a deck CSV, attach live prices, and build the download response."""
    try:
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            data_rows = list(reader)
    except Exception:
        return HTMLResponse("Could not read CSV", status_code=500)

    # Strip any stale baked Price column
    if "Price" in headers:
        price_idx = headers.index("Price")
        headers = [h for i, h in enumerate(headers) if i != price_idx]
        data_rows = [[v for i, v in enumerate(row) if i != price_idx] for row in data_rows]

    name_idx = headers.index("Name") if "Name" in headers else 0
    card_names = [
        row[name_idx] for row in data_rows
        if row and len(row) > name_idx and row[name_idx] and row[name_idx] != "Total"
    ]

    prices_map: Dict[str, Any] = {}
    try:
        from ..services.price_service import get_price_service
        prices_map = get_price_service().get_prices_batch(card_names) or {}
    except Exception:
        pass

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers + ["Price"])
    for row in data_rows:
        if not row:
            continue
        name_val = row[name_idx] if len(row) > name_idx else ""
        if name_val == "Total":
            continue
        price_val = prices_map.get(name_val)
        writer.writerow(row + [f"{price_val:.2f}" if price_val is not None else ""])

    if prices_map:
        total = sum(v for v in prices_map.values() if v is not None)
        empty = [""] * len(headers)
        empty[name_idx] = "Total"
        writer.writerow(empty + [f"{total:.2f}"])

    return Response(
        content=output.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'},
    )


@router.post("/set-visibility", response_class=HTMLResponse)
async def decks_set_visibility(
    request: Request,
    deck_name: str = Form(...),
    visibility: str = Form(...),
) -> HTMLResponse:
    """Update a deck's visibility. Owner-only; guests are forbidden."""
    uid = _user_id(request)
    user = getattr(request.state, "current_user", None)
    if uid == "guest" or not user or user.get("is_guest"):
        return HTMLResponse("Forbidden", status_code=403)
    if visibility not in VALID_VISIBILITIES:
        return HTMLResponse("Invalid visibility.", status_code=400)
    base = _deck_dir(uid)
    p = (base / deck_name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return HTMLResponse("Deck not found.", status_code=404)
    try:
        _set_deck_visibility_by_path(p, visibility)
    except (ValueError, FileNotFoundError):
        return HTMLResponse("Deck not found.", status_code=404)
    label = {"public": "Public", "unlisted": "Unlisted", "private": "Private"}.get(visibility, visibility)
    username = user.get("username") if user else None
    share_block = ""
    if visibility == "private":
        share_block = (
            '<div class="muted deck-share-url-message" style="font-size:12px; margin-top:.35rem;">'
            "This deck is private &mdash; the link won't work for anyone else until you set visibility "
            "to Unlisted or Public.</div>"
        )
    elif username:
        share_url = f"/decks/{username}/{deck_name}"
        full_url = f"{request.url.scheme}://{request.url.netloc}{share_url}"
        share_block = (
            '<div class="muted deck-share-url" style="font-size:12px; margin-top:.35rem;">'
            f'<span id="deck-share-url-value" style="display:none;">{full_url}</span> '
            '<button type="button" class="btn btn-sm" onclick="try{ navigator.clipboard.writeText('
            "document.getElementById('deck-share-url-value').textContent); if(window.toast) "
            "toast('Link copied.', 'success'); }catch(_){}\">Copy Shareable Link</button></div>"
        )
    return HTMLResponse(
        f"<script>window.toast && window.toast('Visibility set to {label}.', 'success');</script>"
        f'<div id="deck-share-url-block" hx-swap-oob="true">{share_block}</div>'
    )


@router.post("/delete")
async def decks_delete(request: Request, name: str, section: str = "mine") -> Response:
    """Delete a finished deck and its sidecars.

    - 'mine' section: any authenticated (non-guest) user may delete their own decks.
    - 'guest' / 'legacy' sections: admin only.
    """
    uid = _user_id(request)
    user = getattr(request.state, "current_user", None)
    is_admin = bool(user and user.get("is_admin"))
    is_guest_user = not user or bool(user.get("is_guest"))

    # Permission check
    if section in ("guest", "legacy"):
        if not is_admin:
            return Response("Forbidden", status_code=403)
    else:
        # 'mine'
        if is_guest_user:
            return Response("Forbidden", status_code=403)

    base = _deck_base_for_section(uid, section)
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return Response("Not found", status_code=404)

    # Delete CSV + known sidecars
    stem = p.stem
    for suffix in (".csv", ".txt", ".summary.json", "_compliance.json"):
        candidate = p.parent / (stem + suffix)
        try:
            if candidate.exists():
                candidate.unlink()
        except Exception:
            pass

    # Return empty 200 — HTMX will swap the panel out of the DOM
    return Response("", status_code=200)
