"""Theme catalog loader & projection utilities.

Phase E foundation + Phase F performance optimizations.

Responsibilities:
 - Lazy load & cache merged catalog JSON + YAML overlays.
 - Provide slug -> ThemeEntry and raw YAML maps.
 - Provide summary & detail projections (with synergy segmentation).
 - NEW (Phase F perf): precompute summary dicts & lowercase haystacks, and
     add fast filtering / result caching to accelerate list & API endpoints.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Dict, Any, List, Optional, Tuple, Iterable

import yaml  # type: ignore
from pydantic import BaseModel

# Import ThemeCatalog & ThemeEntry with resilient fallbacks.
# Runtime contexts:
#  - Local dev (cwd == project root): modules available as top-level.
#  - Docker (WORKDIR /app/code): modules also available top-level.
#  - Package/zip installs (rare): may require 'code.' prefix.
try:
    from type_definitions_theme_catalog import ThemeCatalog, ThemeEntry  # type: ignore
except ImportError:  # pragma: no cover - fallback path
    try:
        from code.type_definitions_theme_catalog import ThemeCatalog, ThemeEntry  # type: ignore
    except ImportError:  # pragma: no cover - last resort (avoid beyond top-level relative import)
        raise

CATALOG_JSON = Path("config/themes/theme_list.json")
YAML_DIR = Path("config/themes/catalog")

_CACHE: Dict[str, Any] = {}
# Filter result cache: key = (etag, q, archetype, bucket, colors_tuple)
_FILTER_CACHE: Dict[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[Tuple[str, ...]]], List[str]] = {}
_FILTER_REQUESTS = 0
_FILTER_CACHE_HITS = 0
_FILTER_LAST_BUST_AT: float | None = None
_FILTER_PREWARMED = False  # guarded single-run prewarm flag

# --- Performance: YAML newest mtime scan caching ---
# Repeated calls to _needs_reload() previously scanned every *.yml file (~700 files)
# on each theme list/filter request, contributing noticeable latency on Windows (many stat calls).
# We cache the newest YAML mtime for a short interval (default 2s, tunable via env) to avoid
# excessive directory traversal while still detecting edits quickly during active authoring.
_YAML_SCAN_CACHE: Dict[str, Any] = {  # keys: newest_mtime (float), scanned_at (float)
    "newest_mtime": 0.0,
    "scanned_at": 0.0,
}
try:
    import os as _os
    _YAML_SCAN_INTERVAL = float((_os.getenv("THEME_CATALOG_YAML_SCAN_INTERVAL_SEC") or "2.0"))
except Exception:  # pragma: no cover - fallback
    _YAML_SCAN_INTERVAL = 2.0


class SlugThemeIndex(BaseModel):
    catalog: ThemeCatalog
    slug_to_entry: Dict[str, ThemeEntry]
    slug_to_yaml: Dict[str, Dict[str, Any]]  # raw YAML data per theme
    # Performance precomputations for fast list filtering
    summary_by_slug: Dict[str, Dict[str, Any]]
    haystack_by_slug: Dict[str, str]
    primary_color_by_slug: Dict[str, Optional[str]]
    secondary_color_by_slug: Dict[str, Optional[str]]
    mtime: float
    yaml_mtime_max: float
    etag: str


_GENERIC_DESCRIPTION_PREFIXES = [
    "Accumulates ",  # many auto-generated variants start like this
    "Builds around ",
    "Leverages ",
]


_SLUG_RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = name.lower().strip()
    # Preserve +1/+1 pattern meaningfully by converting '+' to 'plus'
    s = s.replace("+", "plus")
    s = _SLUG_RE_NON_ALNUM.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _needs_reload() -> bool:
    if not CATALOG_JSON.exists():
        return bool(_CACHE)
    mtime = CATALOG_JSON.stat().st_mtime
    idx: SlugThemeIndex | None = _CACHE.get("index")  # type: ignore
    if idx is None:
        return True
    if mtime > idx.mtime:
        return True
    # If any YAML newer than catalog mtime or newest YAML newer than cached scan -> reload
    if YAML_DIR.exists():
        import time as _t
        now = _t.time()
        # Use cached newest mtime if within interval; else rescan.
        if (now - _YAML_SCAN_CACHE["scanned_at"]) < _YAML_SCAN_INTERVAL:
            newest_yaml = _YAML_SCAN_CACHE["newest_mtime"]
        else:
            # Fast path: use os.scandir for lower overhead vs Path.glob
            newest = 0.0
            try:
                import os as _os
                with _os.scandir(YAML_DIR) as it:  # type: ignore[arg-type]
                    for entry in it:
                        if entry.is_file() and entry.name.endswith('.yml'):
                            try:
                                st = entry.stat()
                                if st.st_mtime > newest:
                                    newest = st.st_mtime
                            except Exception:
                                continue
            except Exception:  # pragma: no cover - scandir failure fallback
                newest = max((p.stat().st_mtime for p in YAML_DIR.glob('*.yml')), default=0.0)
            _YAML_SCAN_CACHE["newest_mtime"] = newest
            _YAML_SCAN_CACHE["scanned_at"] = now
            newest_yaml = newest
        if newest_yaml > idx.yaml_mtime_max:
            return True
    return False


def _load_yaml_map() -> Tuple[Dict[str, Dict[str, Any]], float]:
    latest = 0.0
    out: Dict[str, Dict[str, Any]] = {}
    if not YAML_DIR.exists():
        return out, latest
    for p in YAML_DIR.glob("*.yml"):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                slug = data.get("id") or slugify(data.get("display_name", p.stem))
                out[str(slug)] = data
            if p.stat().st_mtime > latest:
                latest = p.stat().st_mtime
        except Exception:
            continue
    return out, latest


def _compute_etag(size: int, mtime: float, yaml_mtime: float) -> str:
    return f"{int(size)}-{int(mtime)}-{int(yaml_mtime)}"


def load_index() -> SlugThemeIndex:
    if not _needs_reload():
        return _CACHE["index"]  # type: ignore
    if not CATALOG_JSON.exists():
        raise FileNotFoundError("theme_list.json missing")
    raw = json.loads(CATALOG_JSON.read_text(encoding="utf-8") or "{}")
    catalog = ThemeCatalog.model_validate(raw)
    slug_to_entry: Dict[str, ThemeEntry] = {}
    summary_by_slug: Dict[str, Dict[str, Any]] = {}
    haystack_by_slug: Dict[str, str] = {}
    primary_color_by_slug: Dict[str, Optional[str]] = {}
    secondary_color_by_slug: Dict[str, Optional[str]] = {}
    for t in catalog.themes:
        slug = slugify(t.theme)
        slug_to_entry[slug] = t
        summary = project_summary(t)
        summary_by_slug[slug] = summary
        haystack_by_slug[slug] = "|".join([t.theme] + t.synergies).lower()
        primary_color_by_slug[slug] = t.primary_color
        secondary_color_by_slug[slug] = t.secondary_color
    yaml_map, yaml_mtime_max = _load_yaml_map()
    idx = SlugThemeIndex(
        catalog=catalog,
        slug_to_entry=slug_to_entry,
        slug_to_yaml=yaml_map,
        summary_by_slug=summary_by_slug,
        haystack_by_slug=haystack_by_slug,
        primary_color_by_slug=primary_color_by_slug,
        secondary_color_by_slug=secondary_color_by_slug,
        mtime=CATALOG_JSON.stat().st_mtime,
        yaml_mtime_max=yaml_mtime_max,
        etag=_compute_etag(CATALOG_JSON.stat().st_size, CATALOG_JSON.stat().st_mtime, yaml_mtime_max),
    )
    _CACHE["index"] = idx
    _FILTER_CACHE.clear()  # Invalidate fast filter cache on any reload
    return idx


def validate_catalog_integrity(rebuild: bool = True) -> Dict[str, Any]:
    """Validate that theme_list.json matches current YAML set via catalog_hash.

    Returns dict with status fields. If drift detected and rebuild=True and
    THEME_CATALOG_MODE merge script is available, attempts an automatic rebuild.
    Environment flags:
      THEME_CATALOG_VALIDATE=1 enables invocation from app startup (else caller controls).
    """
    out: Dict[str, Any] = {"ok": True, "rebuild_attempted": False, "drift": False}
    if not CATALOG_JSON.exists():
        out.update({"ok": False, "error": "theme_list_missing"})
        return out
    try:
        raw = json.loads(CATALOG_JSON.read_text(encoding="utf-8") or "{}")
        meta = raw.get("metadata_info") or {}
        recorded_hash = meta.get("catalog_hash")
    except Exception as e:  # pragma: no cover
        out.update({"ok": False, "error": f"read_error:{e}"})
        return out
    # Recompute hash using same heuristic as build script
    from scripts.build_theme_catalog import load_catalog_yaml  # type: ignore
    try:
        yaml_catalog = load_catalog_yaml(verbose=False)  # keyed by display_name
    except Exception:
        yaml_catalog = {}
    import hashlib as _hashlib
    h = _hashlib.sha256()
    for name in sorted(yaml_catalog.keys()):
        yobj = yaml_catalog[name]
        try:
            payload = (
                getattr(yobj, 'id', ''),
                getattr(yobj, 'display_name', ''),
                tuple(getattr(yobj, 'curated_synergies', []) or []),
                tuple(getattr(yobj, 'enforced_synergies', []) or []),
                tuple(getattr(yobj, 'example_commanders', []) or []),
                tuple(getattr(yobj, 'example_cards', []) or []),
                getattr(yobj, 'deck_archetype', None),
                getattr(yobj, 'popularity_hint', None),
                getattr(yobj, 'description', None),
                getattr(yobj, 'editorial_quality', None),
            )
            h.update(repr(payload).encode('utf-8'))
        except Exception:
            continue
    # Synergy cap influences ordering; include if present in meta
    if meta.get('synergy_cap') is not None:
        h.update(str(meta.get('synergy_cap')).encode('utf-8'))
    current_hash = h.hexdigest()
    if recorded_hash and recorded_hash != current_hash:
        out['drift'] = True
        out['recorded_hash'] = recorded_hash
        out['current_hash'] = current_hash
        if rebuild:
            import subprocess
            import os as _os
            import sys as _sys
            out['rebuild_attempted'] = True
            try:
                env = {**_os.environ, 'THEME_CATALOG_MODE': 'merge'}
                subprocess.run([
                    _sys.executable, 'code/scripts/build_theme_catalog.py'
                ], check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out['rebuild_ok'] = True
            except Exception as e:
                out['rebuild_ok'] = False
                out['rebuild_error'] = str(e)
    else:
        out['drift'] = False
        out['recorded_hash'] = recorded_hash
        out['current_hash'] = current_hash
    return out


def has_fallback_description(entry: ThemeEntry) -> bool:
    if not entry.description:
        return True
    desc = entry.description.strip()
    # Simple heuristic: generic if starts with any generic prefix and length < 160
    if len(desc) < 160 and any(desc.startswith(p) for p in _GENERIC_DESCRIPTION_PREFIXES):
        return True
    return False


def project_summary(entry: ThemeEntry) -> Dict[str, Any]:
    # Short description (snippet) for list hover / condensed display
    desc = entry.description or ""
    short_desc = desc.strip()
    if len(short_desc) > 110:
        short_desc = short_desc[:107].rstrip() + "…"
    return {
        "id": slugify(entry.theme),
        "theme": entry.theme,
        "primary_color": entry.primary_color,
        "secondary_color": entry.secondary_color,
        "popularity_bucket": entry.popularity_bucket,
        "deck_archetype": entry.deck_archetype,
        "editorial_quality": entry.editorial_quality,
        "description": entry.description,
        "short_description": short_desc,
        "synergies": entry.synergies,
        "synergy_count": len(entry.synergies),
        "has_fallback_description": has_fallback_description(entry),
    }


def _split_synergies(slug: str, entry: ThemeEntry, yaml_map: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    y = yaml_map.get(slug)
    if not y:
        return {"curated": [], "enforced": [], "inferred": []}
    return {
        "curated": [s for s in y.get("curated_synergies", []) if isinstance(s, str)],
        "enforced": [s for s in y.get("enforced_synergies", []) if isinstance(s, str)],
        "inferred": [s for s in y.get("inferred_synergies", []) if isinstance(s, str)],
    }


def project_detail(slug: str, entry: ThemeEntry, yaml_map: Dict[str, Dict[str, Any]], uncapped: bool = False) -> Dict[str, Any]:
    seg = _split_synergies(slug, entry, yaml_map)
    uncapped_synergies: Optional[List[str]] = None
    if uncapped:
        # Full ordered list reconstructed: curated + enforced (preserve duplication guard) + inferred
        seen = set()
        full: List[str] = []
        for block in (seg["curated"], seg["enforced"], seg["inferred"]):
            for s in block:
                if s not in seen:
                    full.append(s)
                    seen.add(s)
        uncapped_synergies = full
    d = project_summary(entry)
    d.update({
        "curated_synergies": seg["curated"],
        "enforced_synergies": seg["enforced"],
        "inferred_synergies": seg["inferred"],
    })
    if uncapped_synergies is not None:
        d["uncapped_synergies"] = uncapped_synergies
    # Add editorial lists with YAML fallback (REGRESSION FIX 2025-09-20):
    # The current theme_list.json emitted by the build pipeline omits the
    # example_* and synergy_* editorial arrays. Earlier logic populated these
    # from the JSON so previews showed curated examples. After the omission,
    # ThemeEntry fields default to empty lists and curated examples vanished
    # from the preview (user-reported). We now fallback to the per-theme YAML
    # source when the ThemeEntry lists are empty to restore expected behavior
    # without requiring an immediate catalog rebuild.
    y_entry: Dict[str, Any] = yaml_map.get(slug, {}) or {}
    def _norm_list(val: Any) -> List[str]:
        if isinstance(val, list):
            return [str(x) for x in val if isinstance(x, str)]
        return []
    example_commanders = entry.example_commanders or _norm_list(y_entry.get("example_commanders"))
    example_cards = entry.example_cards or _norm_list(y_entry.get("example_cards"))
    synergy_example_cards = getattr(entry, 'synergy_example_cards', None) or _norm_list(y_entry.get("synergy_example_cards"))
    synergy_commanders = entry.synergy_commanders or _norm_list(y_entry.get("synergy_commanders"))
    # YAML fallback for description & selected editorial fields (REGRESSION FIX 2025-09-20):
    # theme_list.json currently omits description/editorial_quality/popularity_bucket for some themes after P2 build changes.
    # Use YAML values when the ThemeEntry field is empty/None. Preserve existing non-empty entry values.
    description = entry.description or y_entry.get("description") or None
    editorial_quality = entry.editorial_quality or y_entry.get("editorial_quality") or None
    popularity_bucket = entry.popularity_bucket or y_entry.get("popularity_bucket") or None
    d.update({
        "example_commanders": example_commanders,
        "example_cards": example_cards,
        "synergy_example_cards": synergy_example_cards,
        "synergy_commanders": synergy_commanders,
        "description": description,
        "editorial_quality": editorial_quality,
        "popularity_bucket": popularity_bucket,
    })
    return d


def filter_entries(entries: List[ThemeEntry], *, q: Optional[str] = None, archetype: Optional[str] = None, bucket: Optional[str] = None, colors: Optional[List[str]] = None) -> List[ThemeEntry]:
    q_lower = q.lower() if q else None
    colors_set = {c.strip().upper() for c in colors} if colors else None
    out: List[ThemeEntry] = []
    for e in entries:
        if archetype and e.deck_archetype != archetype:
            continue
        if bucket and e.popularity_bucket != bucket:
            continue
        if colors_set:
            pc = (e.primary_color or "").upper()[:1]
            sc = (e.secondary_color or "").upper()[:1]
            if not (pc in colors_set or sc in colors_set):
                continue
        if q_lower:
            hay = "|".join([e.theme] + e.synergies).lower()
            if q_lower not in hay:
                continue
        out.append(e)
    return out


# -------------------- Optimized filtering (fast path) --------------------
def _color_match(slug: str, colors_set: Optional[set[str]], idx: SlugThemeIndex) -> bool:
    if not colors_set:
        return True
    pc = (idx.primary_color_by_slug.get(slug) or "").upper()[:1]
    sc = (idx.secondary_color_by_slug.get(slug) or "").upper()[:1]
    return (pc in colors_set) or (sc in colors_set)


def filter_slugs_fast(
    idx: SlugThemeIndex,
    *,
    q: Optional[str] = None,
    archetype: Optional[str] = None,
    bucket: Optional[str] = None,
    colors: Optional[List[str]] = None,
) -> List[str]:
    """Return filtered slugs using precomputed haystacks & memoized cache.

    Cache key: (etag, q_lower, archetype, bucket, colors_tuple) where colors_tuple
    is sorted & uppercased. Cache invalidates automatically when index reloads.
    """
    colors_key: Optional[Tuple[str, ...]] = (
        tuple(sorted({c.strip().upper() for c in colors})) if colors else None
    )
    cache_key = (idx.etag, q.lower() if q else None, archetype, bucket, colors_key)
    global _FILTER_REQUESTS, _FILTER_CACHE_HITS
    _FILTER_REQUESTS += 1
    cached = _FILTER_CACHE.get(cache_key)
    if cached is not None:
        _FILTER_CACHE_HITS += 1
        return cached
    q_lower = q.lower() if q else None
    colors_set = set(colors_key) if colors_key else None
    out: List[str] = []
    for slug, entry in idx.slug_to_entry.items():
        if archetype and entry.deck_archetype != archetype:
            continue
        if bucket and entry.popularity_bucket != bucket:
            continue
        if colors_set and not _color_match(slug, colors_set, idx):
            continue
        if q_lower and q_lower not in idx.haystack_by_slug.get(slug, ""):
            continue
        out.append(slug)
    _FILTER_CACHE[cache_key] = out
    return out


def summaries_for_slugs(idx: SlugThemeIndex, slugs: Iterable[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in slugs:
        summ = idx.summary_by_slug.get(s)
        if summ:
            out.append(summ.copy())  # shallow copy so route can pop diag-only fields
    return out


def catalog_metrics() -> Dict[str, Any]:
    """Return lightweight catalog filtering/cache metrics (diagnostics only)."""
    return {
        "filter_requests": _FILTER_REQUESTS,
        "filter_cache_hits": _FILTER_CACHE_HITS,
        "filter_cache_entries": len(_FILTER_CACHE),
        "filter_last_bust_at": _FILTER_LAST_BUST_AT,
        "filter_prewarmed": _FILTER_PREWARMED,
    }


def bust_filter_cache(reason: str | None = None) -> None:
    """Clear fast filter cache (call after catalog rebuild or yaml change)."""
    global _FILTER_CACHE, _FILTER_LAST_BUST_AT
    try:
        _FILTER_CACHE.clear()
        import time as _t
        _FILTER_LAST_BUST_AT = _t.time()
    except Exception:
        pass


def prewarm_common_filters(max_archetypes: int = 12) -> None:
    """Pre-execute a handful of common filter queries to prime the fast cache.

    This is intentionally conservative (only a small cartesian of bucket/archetype)
    and gated by WEB_THEME_FILTER_PREWARM=1 environment variable as well as a
    single-run guard. Safe to call multiple times (no-op after first success).
    """
    global _FILTER_PREWARMED
    if _FILTER_PREWARMED:
        return
    import os
    if (os.getenv("WEB_THEME_FILTER_PREWARM") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    try:
        idx = load_index()
    except Exception:
        return
    # Gather archetypes & buckets (limited)
    archetypes: List[str] = []
    try:
        archetypes = [a for a in {t.deck_archetype for t in idx.catalog.themes if t.deck_archetype}][:max_archetypes]  # type: ignore[arg-type]
    except Exception:
        archetypes = []
    buckets = ["Very Common", "Common", "Uncommon", "Niche", "Rare"]
    # Execute fast filter queries (ignore output, we only want cache side effects)
    try:
        # Global (no filters) & each bucket
        filter_slugs_fast(idx)
        for b in buckets:
            filter_slugs_fast(idx, bucket=b)
        # Archetype only combos (first N)
        for a in archetypes:
            filter_slugs_fast(idx, archetype=a)
        # Archetype + bucket cross (cap combinations)
        for a in archetypes[:5]:
            for b in buckets[:3]:
                filter_slugs_fast(idx, archetype=a, bucket=b)
        _FILTER_PREWARMED = True
    except Exception:
        # Swallow any unexpected error; prewarm is opportunistic
        return
