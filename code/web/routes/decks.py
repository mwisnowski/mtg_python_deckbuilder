from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pathlib import Path
import csv
import os
from typing import Dict, List, Tuple, Optional

from ..app import templates
from ..services import owned_store
from deck_builder import builder_constants as bc


router = APIRouter(prefix="/decks")


def _deck_dir() -> Path:
    # Prefer explicit env var if provided, else default to ./deck_files
    p = os.getenv("DECK_EXPORTS")
    if p:
        return Path(p).resolve()
    return (Path.cwd() / "deck_files").resolve()


def _list_decks() -> list[dict]:
    d = _deck_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    items: list[dict] = []
    # Prefer CSV entries and pair with matching TXT if present
    for p in sorted(d.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        meta = {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime}
        stem = p.stem
        txt = p.with_suffix('.txt')
        if txt.exists():
            meta["txt_name"] = txt.name
            meta["txt_path"] = str(txt)
        # Prefer sidecar summary meta if present
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
            except Exception:
                pass
        # Fallback to parsing commander/themes from filename convention Commander_Themes_YYYYMMDD
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
                    type_cards.setdefault(cat, []).append({
                        'name': name,
                        'count': cnt,
                        'role': role,
                        'tags': tags_list,
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
    items = _list_decks()
    return templates.TemplateResponse("decks/index.html", {"request": request, "items": items})


@router.get("/view", response_class=HTMLResponse)
async def decks_view(request: Request, name: str) -> HTMLResponse:
    base = _deck_dir()
    p = (base / name).resolve()
    if not _safe_within(base, p) or not (p.exists() and p.is_file() and p.suffix.lower() == ".csv"):
        return templates.TemplateResponse("decks/index.html", {"request": request, "items": _list_decks(), "error": "Deck not found."})

    # Try to load sidecar summary JSON first
    summary = None
    commander_name = ''
    tags: List[str] = []
    sidecar = p.with_suffix('.summary.json')
    if sidecar.exists():
        try:
            import json as _json
            payload = _json.loads(sidecar.read_text(encoding='utf-8'))
            if isinstance(payload, dict):
                summary = payload.get('summary')
                meta = payload.get('meta', {})
                if isinstance(meta, dict):
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
    "game_changers": bc.GAME_CHANGERS,
    "owned_set": {n.lower() for n in owned_store.get_names()},
    }
    return templates.TemplateResponse("decks/view.html", ctx)


@router.get("/compare", response_class=HTMLResponse)
async def decks_compare(request: Request, A: Optional[str] = None, B: Optional[str] = None) -> HTMLResponse:
    """Compare two finished deck CSVs and show diffs.

    Query params:
      - A: filename of first deck (e.g., Alena_..._20250827.csv)
      - B: filename of second deck
    """
    base = _deck_dir()
    items = _list_decks()
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
        options.append({"name": it.get("name"), "label": label, "mtime": mt_val})  # type: ignore[arg-type]

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
