from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple, Dict
import json
import os
import time


def _owned_dir() -> Path:
    """Resolve the owned cards directory (shared with CLI) for persistence.

    Precedence:
    - OWNED_CARDS_DIR env var
    - CARD_LIBRARY_DIR env var (back-compat)
    - ./owned_cards (if exists)
    - ./card_library (if exists)
    - default ./owned_cards
    """
    env_dir = os.getenv("OWNED_CARDS_DIR") or os.getenv("CARD_LIBRARY_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    for name in ("owned_cards", "card_library"):
        p = Path(name)
        if p.exists() and p.is_dir():
            return p.resolve()
    return Path("owned_cards").resolve()


def _db_path() -> Path:
    d = _owned_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return (d / ".web_owned_db.json").resolve()


def _load_raw() -> dict:
    p = _db_path()
    if p.exists():
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Back-compat defaults
                if "names" not in data or not isinstance(data.get("names"), list):
                    data["names"] = []
                if "meta" not in data or not isinstance(data.get("meta"), dict):
                    data["meta"] = {}
                return data
        except Exception:
            return {"names": [], "meta": {}}
    return {"names": [], "meta": {}}


def _save_raw(data: dict) -> None:
    p = _db_path()
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_names() -> List[str]:
    data = _load_raw()
    names = data.get("names") or []
    if not isinstance(names, list):
        return []
    # Normalize and dedupe while preserving stable ordering
    seen = set()
    out: List[str] = []
    for n in names:
        s = str(n).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def clear() -> None:
    _save_raw({"names": [], "meta": {}})


def add_names(names: Iterable[str]) -> Tuple[int, int]:
    """Add a batch of names; returns (added_count, total_after)."""
    data = _load_raw()
    cur = [str(x).strip() for x in (data.get("names") or []) if str(x).strip()]
    cur_set = {n.lower() for n in cur}
    added = 0
    for raw in names:
        try:
            s = str(raw).strip()
            if not s:
                continue
            key = s.lower()
            if key in cur_set:
                continue
            cur.append(s)
            cur_set.add(key)
            added += 1
        except Exception:
            continue
    data["names"] = cur
    if "meta" not in data or not isinstance(data.get("meta"), dict):
        data["meta"] = {}
    meta = data["meta"]
    now = int(time.time())
    # Ensure newly added names have an added_at
    for s in cur:
        info = meta.get(s)
        if not info:
            meta[s] = {"added_at": now}
        else:
            if "added_at" not in info:
                info["added_at"] = now
    _save_raw(data)
    return added, len(cur)


def _enrich_from_csvs(target_names: Iterable[str]) -> Dict[str, Dict[str, object]]:
    """Return metadata for target names by scanning all_cards.parquet (M4).
    Output: { Name: { 'tags': [..], 'type': str|None, 'colors': [..] } }
    """
    meta: Dict[str, Dict[str, object]] = {}
    want = {str(n).strip().lower() for n in target_names if str(n).strip()}
    if not want:
        return meta

    try:
        from deck_builder import builder_utils as bu
        df = bu._load_all_cards_parquet()
        if df.empty:
            return meta

        # Filter to cards we care about
        df['name_lower'] = df['name'].str.lower()
        df_filtered = df[df['name_lower'].isin(want)].copy()

        for _, row in df_filtered.iterrows():
            nm = str(row.get('name') or '').strip()
            if not nm:
                continue

            entry = meta.setdefault(nm, {"tags": [], "type": None, "colors": []})

            # Tags (already a list after our conversion in builder_utils)
            tags = row.get('themeTags')
            if tags and isinstance(tags, list):
                existing = entry.get('tags') or []
                seen = {str(t).lower() for t in existing}
                for t in tags:
                    t_str = str(t).strip()
                    if t_str and t_str.lower() not in seen:
                        existing.append(t_str)
                        seen.add(t_str.lower())
                entry['tags'] = existing

            # Type
            if not entry.get('type'):
                t_raw = str(row.get('type') or '').strip()
                if t_raw:
                    tline = t_raw.split('—')[0].strip() if '—' in t_raw else t_raw
                    prim = None
                    for cand in ['Creature','Instant','Sorcery','Artifact','Enchantment','Planeswalker','Land','Battle']:
                        if cand.lower() in tline.lower():
                            prim = cand
                            break
                    if not prim and tline:
                        prim = tline.split()[0]
                    if prim:
                        entry['type'] = prim

            # Colors
            if not entry.get('colors'):
                colors_raw = str(row.get('colorIdentity') or '').strip()
                if colors_raw:
                    parts = [c.strip() for c in colors_raw.split(',') if c.strip()]
                    entry['colors'] = parts

    except Exception:
        # Defensive: return empty or partial meta
        pass

    return meta


def add_and_enrich(names: Iterable[str]) -> Tuple[int, int]:
    """Add names and enrich their metadata from Parquet (M4).
    Returns (added_count, total_after).
    """
    data = _load_raw()
    current_names = [str(x).strip() for x in (data.get("names") or []) if str(x).strip()]
    cur_set = {n.lower() for n in current_names}
    new_names: List[str] = []
    for raw in names:
        try:
            s = str(raw).strip()
            if not s:
                continue
            key = s.lower()
            if key in cur_set:
                continue
            current_names.append(s)
            cur_set.add(key)
            new_names.append(s)
        except Exception:
            continue
    # Enrich
    meta = data.get("meta") or {}
    now = int(time.time())
    if new_names:
        enriched = _enrich_from_csvs(new_names)
        for nm, info in enriched.items():
            meta[nm] = info
        # Stamp added_at for new names if missing
        for nm in new_names:
            entry = meta.setdefault(nm, {})
            if "added_at" not in entry:
                entry["added_at"] = now
    data["names"] = current_names
    data["meta"] = meta
    _save_raw(data)
    return len(new_names), len(current_names)


def get_enriched() -> Tuple[List[str], Dict[str, List[str]], Dict[str, str], Dict[str, List[str]]]:
    """Return names and metadata dicts (tags_by_name, type_by_name, colors_by_name).
    If metadata missing, returns empty for those entries.
    """
    data = _load_raw()
    names = [str(x).strip() for x in (data.get("names") or []) if str(x).strip()]
    meta: Dict[str, Dict[str, object]] = data.get("meta") or {}
    tags_by_name: Dict[str, List[str]] = {}
    type_by_name: Dict[str, str] = {}
    colors_by_name: Dict[str, List[str]] = {}
    for n in names:
        info = meta.get(n) or {}
        tags = (info.get('tags') or [])
    # user-defined tags are no longer supported; no merge
        typ = info.get('type') or None
        cols = info.get('colors') or []
        if tags:
            tags_by_name[n] = [str(x) for x in tags if str(x)]
        if typ:
            type_by_name[n] = str(typ)
        if cols:
            colors_by_name[n] = [str(x).upper() for x in cols if str(x)]
    return names, tags_by_name, type_by_name, colors_by_name


# add_user_tag/remove_user_tag removed; user-defined tags are not persisted anymore


def get_added_at_map() -> Dict[str, int]:
    """Return a mapping of name -> added_at unix timestamp (if known)."""
    data = _load_raw()
    meta: Dict[str, Dict[str, object]] = data.get("meta") or {}
    out: Dict[str, int] = {}
    for n, info in meta.items():
        try:
            ts = info.get("added_at")
            if isinstance(ts, (int, float)):
                out[n] = int(ts)
        except Exception:
            continue
    return out


def remove_names(names: Iterable[str]) -> Tuple[int, int]:
    """Remove a batch of names; returns (removed_count, total_after)."""
    target = {str(n).strip().lower() for n in (names or []) if str(n).strip()}
    if not target:
        return 0, len(get_names())
    data = _load_raw()
    cur = [str(x).strip() for x in (data.get("names") or []) if str(x).strip()]
    before = len(cur)
    cur_kept: List[str] = []
    for s in cur:
        if s.lower() in target:
            continue
        cur_kept.append(s)
    removed = before - len(cur_kept)
    data["names"] = cur_kept
    meta = data.get("meta") or {}
    # Drop meta entries for removed names
    for s in list(meta.keys()):
        try:
            if s.lower() in target:
                meta.pop(s, None)
        except Exception:
            continue
    data["meta"] = meta
    _save_raw(data)
    return removed, len(cur_kept)


def get_user_tags_map() -> Dict[str, list[str]]:
    """Deprecated: user-defined tags have been removed. Always returns empty mapping."""
    return {}


def parse_txt_bytes(content: bytes) -> List[str]:
    out: List[str] = []
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        text = content.decode(errors="ignore")
    for line in text.splitlines():
        s = (line or "").strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        parts = s.split()
        if len(parts) >= 2 and (parts[0].isdigit() or (parts[0].lower().endswith('x') and parts[0][:-1].isdigit())):
            s = ' '.join(parts[1:])
        if s:
            out.append(s)
    return out


def parse_csv_bytes(content: bytes) -> List[str]:
    names: List[str] = []
    try:
        import csv
        from io import StringIO
        import re
        text = content.decode("utf-8", errors="ignore")
        f = StringIO(text)
        try:
            reader = csv.DictReader(f)
            headers = [h for h in (reader.fieldnames or []) if isinstance(h, str)]
            # Normalize headers: lowercase and remove non-letters (spaces, underscores, dashes)
            def norm(h: str) -> str:
                return re.sub(r"[^a-z]", "", (h or "").lower())

            # Map normalized -> original header
            norm_map = {norm(h): h for h in headers}

            # Preferred keys (exact normalized match)
            preferred = ["name", "cardname"]
            key = None
            for k in preferred:
                if k in norm_map:
                    key = norm_map[k]
                    break
            # Fallback: allow plain 'card' but avoid 'cardnumber', 'cardid', etc.
            if key is None:
                if "card" in norm_map and all(x not in norm_map for x in ("cardnumber", "cardno", "cardid", "collectornumber", "collector", "multiverseid")):
                    key = norm_map["card"]
            # Another fallback: try common variants if not strictly normalized
            if key is None:
                for h in headers:
                    h_clean = (h or "").strip().lower()
                    if h_clean in ("name", "card name", "card_name", "cardname"):
                        key = h
                        break

            if key:
                for row in reader:
                    val = str(row.get(key) or '').strip()
                    if not val:
                        continue
                    names.append(val)
            else:
                f.seek(0)
                reader2 = csv.reader(f)
                rows = list(reader2)
                if not rows:
                    pass
                else:
                    # Try to detect a likely name column from the first row
                    header = rows[0]
                    name_col = 0
                    if header:
                        # Look for header cells resembling name
                        for idx, cell in enumerate(header):
                            c = str(cell or '').strip()
                            cn = norm(c)
                            if cn in ("name", "cardname"):
                                name_col = idx
                                break
                        else:
                            # As a fallback, if any cell lower is exactly 'card', take it
                            for idx, cell in enumerate(header):
                                c = str(cell or '').strip().lower()
                                if c == 'card':
                                    name_col = idx
                                    break
                    # Iterate rows, skip header-like first row when it matches
                    for i, row in enumerate(rows):
                        if not row:
                            continue
                        if i == 0:
                            first = str(row[name_col] if len(row) > name_col else '').strip()
                            fn = norm(first)
                            if fn in ("name", "cardname") or first.lower() in ("name", "card name", "card", "card_name"):
                                continue  # skip header
                        val = str(row[name_col] if len(row) > name_col else '').strip()
                        if not val:
                            continue
                        # Skip rows that look like header or counts
                        low = val.lower()
                        if low in ("name", "card name", "card", "card_name"):
                            continue
                        names.append(val)
        except Exception:
            # Fallback: one name per line
            f.seek(0)
            for line in f:
                s = (line or '').strip()
                if s and s.lower() not in ('name', 'card', 'card name'):
                    names.append(s)
    except Exception:
        pass
    # Normalize, dedupe while preserving order
    seen = set()
    out: List[str] = []
    for n in names:
        s = str(n).strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out
