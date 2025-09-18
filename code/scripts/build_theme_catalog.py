"""Phase B: Merge curated YAML catalog with regenerated analytics to build theme_list.json.

See roadmap Phase B goals. This script unifies generation:
 - Discovers themes (constants + tagger + CSV dynamic tags)
 - Applies whitelist governance (normalization, pruning, always_include)
 - Recomputes frequencies & PMI co-occurrence for inference
 - Loads curated YAML files (Phase A outputs) for editorial overrides
 - Merges curated, enforced, and inferred synergies with precedence
 - Applies synergy cap without truncating curated or enforced entries
 - Emits theme_list.json with provenance block

Opt-in via env THEME_CATALOG_MODE=merge (or build/phaseb). Or run manually:
  python code/scripts/build_theme_catalog.py --verbose

This is intentionally side-effect only (writes JSON). Unit tests for Phase C will
add schema validation; for now we focus on deterministic, stable output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:  # Optional
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT / 'code'
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from scripts.extract_themes import (  # type: ignore
    BASE_COLORS,
    collect_theme_tags_from_constants,
    collect_theme_tags_from_tagger_source,
    gather_theme_tag_rows,
    tally_tag_frequencies_by_base_color,
    compute_cooccurrence,
    cooccurrence_scores_for,
    derive_synergies_for_tags,
    apply_normalization,
    load_whitelist_config,
    should_keep_theme,
)

CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'
OUTPUT_JSON = ROOT / 'config' / 'themes' / 'theme_list.json'


@dataclass
class ThemeYAML:
    id: str
    display_name: str
    curated_synergies: List[str]
    enforced_synergies: List[str]
    inferred_synergies: List[str]
    synergies: List[str]
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    notes: str = ''


def _log(msg: str, verbose: bool):  # pragma: no cover
    if verbose:
        print(f"[build_theme_catalog] {msg}", file=sys.stderr)


def load_catalog_yaml(verbose: bool) -> Dict[str, ThemeYAML]:
    out: Dict[str, ThemeYAML] = {}
    if not CATALOG_DIR.exists() or yaml is None:
        return out
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception:
            _log(f"Failed reading {path.name}", verbose)
            continue
        if not isinstance(data, dict):
            continue
        # Skip deprecated alias placeholder files (marked in notes)
        try:
            notes_field = data.get('notes')
            if isinstance(notes_field, str) and 'Deprecated alias file' in notes_field:
                continue
        except Exception:
            pass
        try:
            ty = ThemeYAML(
                id=str(data.get('id') or ''),
                display_name=str(data.get('display_name') or ''),
                curated_synergies=list(data.get('curated_synergies') or []),
                enforced_synergies=list(data.get('enforced_synergies') or []),
                inferred_synergies=list(data.get('inferred_synergies') or []),
                synergies=list(data.get('synergies') or []),
                primary_color=data.get('primary_color'),
                secondary_color=data.get('secondary_color'),
                notes=str(data.get('notes') or ''),
            )
        except Exception:
            continue
        if not ty.display_name:
            continue
        out[ty.display_name] = ty
    return out


def regenerate_analytics(verbose: bool):
    theme_tags: Set[str] = set()
    theme_tags |= collect_theme_tags_from_constants()
    theme_tags |= collect_theme_tags_from_tagger_source()
    try:
        csv_rows = gather_theme_tag_rows()
        for row_tags in csv_rows:
            for t in row_tags:
                if isinstance(t, str) and t:
                    theme_tags.add(t)
    except Exception:
        csv_rows = []

    whitelist = load_whitelist_config()
    normalization_map: Dict[str, str] = whitelist.get('normalization', {}) if isinstance(whitelist.get('normalization'), dict) else {}
    exclusions: Set[str] = set(whitelist.get('exclusions', []) or [])
    protected_prefixes: List[str] = list(whitelist.get('protected_prefixes', []) or [])
    protected_suffixes: List[str] = list(whitelist.get('protected_suffixes', []) or [])
    min_overrides: Dict[str, int] = whitelist.get('min_frequency_overrides', {}) or {}

    if normalization_map:
        theme_tags = apply_normalization(theme_tags, normalization_map)
    blacklist = {"Draw Triggers"}
    theme_tags = {t for t in theme_tags if t and t not in blacklist and t not in exclusions}

    try:
        frequencies = tally_tag_frequencies_by_base_color()
    except Exception:
        frequencies = {}

    if frequencies:
        def total_count(t: str) -> int:
            s = 0
            for c in BASE_COLORS.keys():
                try:
                    s += int(frequencies.get(c, {}).get(t, 0))
                except Exception:
                    pass
            return s
        kept: Set[str] = set()
        for t in list(theme_tags):
            if should_keep_theme(t, total_count(t), whitelist, protected_prefixes, protected_suffixes, min_overrides):
                kept.add(t)
        for extra in whitelist.get('always_include', []) or []:
            kept.add(str(extra))
        theme_tags = kept

    try:
        rows = csv_rows if csv_rows else gather_theme_tag_rows()
        co_map, tag_counts, total_rows = compute_cooccurrence(rows)
    except Exception:
        co_map, tag_counts, total_rows = {}, Counter(), 0

    return dict(theme_tags=theme_tags, frequencies=frequencies, co_map=co_map, tag_counts=tag_counts, total_rows=total_rows, whitelist=whitelist)


def _primary_secondary(theme: str, freqs: Dict[str, Dict[str, int]]):
    if not freqs:
        return None, None
    items: List[Tuple[str, int]] = []
    for color in BASE_COLORS.keys():
        try:
            items.append((color, int(freqs.get(color, {}).get(theme, 0))))
        except Exception:
            items.append((color, 0))
    items.sort(key=lambda x: (-x[1], x[0]))
    if not items or items[0][1] <= 0:
        return None, None
    title = {'white': 'White', 'blue': 'Blue', 'black': 'Black', 'red': 'Red', 'green': 'Green'}
    primary = title[items[0][0]]
    secondary = None
    for c, n in items[1:]:
        if n > 0:
            secondary = title[c]
            break
    return primary, secondary


def infer_synergies(anchor: str, curated: List[str], enforced: List[str], analytics: dict, pmi_min: float = 0.0, co_min: int = 5) -> List[str]:
    if anchor not in analytics['co_map'] or analytics['total_rows'] <= 0:
        return []
    scored = cooccurrence_scores_for(anchor, analytics['co_map'], analytics['tag_counts'], analytics['total_rows'])
    out: List[str] = []
    for other, score, co_count in scored:
        if score <= pmi_min or co_count < co_min:
            continue
        if other == anchor or other in curated or other in enforced or other in out:
            continue
        out.append(other)
        if len(out) >= 12:
            break
    return out


def build_catalog(limit: int, verbose: bool) -> Dict[str, Any]:
    analytics = regenerate_analytics(verbose)
    whitelist = analytics['whitelist']
    synergy_cap = int(whitelist.get('synergy_cap', 0) or 0)
    normalization_map: Dict[str, str] = whitelist.get('normalization', {}) if isinstance(whitelist.get('normalization'), dict) else {}
    enforced_cfg: Dict[str, List[str]] = whitelist.get('enforced_synergies', {}) or {}

    yaml_catalog = load_catalog_yaml(verbose)
    all_themes: Set[str] = set(analytics['theme_tags']) | {t.display_name for t in yaml_catalog.values()}
    if normalization_map:
        all_themes = apply_normalization(all_themes, normalization_map)
    curated_baseline = derive_synergies_for_tags(all_themes)

    entries: List[Dict[str, Any]] = []
    processed = 0
    for theme in sorted(all_themes):
        if limit and processed >= limit:
            break
        processed += 1
        y = yaml_catalog.get(theme)
        curated_list = list(y.curated_synergies) if y and y.curated_synergies else curated_baseline.get(theme, [])
        enforced_list: List[str] = []
        if y and y.enforced_synergies:
            for s in y.enforced_synergies:
                if s not in enforced_list:
                    enforced_list.append(s)
        if theme in enforced_cfg:
            for s in enforced_cfg.get(theme, []):
                if s not in enforced_list:
                    enforced_list.append(s)
        inferred_list = infer_synergies(theme, curated_list, enforced_list, analytics)
        if not inferred_list and y and y.inferred_synergies:
            inferred_list = [s for s in y.inferred_synergies if s not in curated_list and s not in enforced_list]

        if normalization_map:
            def _norm(seq: List[str]) -> List[str]:
                seen = set()
                out = []
                for s in seq:
                    s2 = normalization_map.get(s, s)
                    if s2 not in seen:
                        out.append(s2)
                        seen.add(s2)
                return out
            curated_list = _norm(curated_list)
            enforced_list = _norm(enforced_list)
            inferred_list = _norm(inferred_list)

        merged: List[str] = []
        for bucket in (curated_list, enforced_list, inferred_list):
            for s in bucket:
                if s == theme:
                    continue
                if s not in merged:
                    merged.append(s)

        # Noise suppression: remove ubiquitous Legends/Historics links except for their mutual pairing.
        # Rationale: Every legendary permanent is tagged with both themes (Historics also covers artifacts/enchantments),
        # creating low-signal "synergies" that crowd out more meaningful relationships. Requirement:
        #  - For any theme other than the two themselves, strip both "Legends Matter" and "Historics Matter".
        #  - For "Legends Matter", allow "Historics Matter" to remain (and vice-versa).
        special_noise = {"Legends Matter", "Historics Matter"}
        if theme not in special_noise:
            if any(s in special_noise for s in merged):
                merged = [s for s in merged if s not in special_noise]
        # If theme is one of the special ones, keep the other if present (no action needed beyond above filter logic).

        if synergy_cap > 0 and len(merged) > synergy_cap:
            ce_len = len(curated_list) + len([s for s in enforced_list if s not in curated_list])
            if ce_len < synergy_cap:
                allowed_inferred = synergy_cap - ce_len
                ce_part = merged[:ce_len]
                inferred_tail = [s for s in merged[ce_len:ce_len+allowed_inferred]]
                merged = ce_part + inferred_tail
            # else: keep all (soft exceed)

        if y and (y.primary_color or y.secondary_color):
            primary, secondary = y.primary_color, y.secondary_color
        else:
            primary, secondary = _primary_secondary(theme, analytics['frequencies'])

        entry = {'theme': theme, 'synergies': merged}
        if primary:
            entry['primary_color'] = primary
        if secondary:
            entry['secondary_color'] = secondary
        # Phase D: carry forward optional editorial metadata if present in YAML
        if y:
            if getattr(y, 'example_commanders', None):
                entry['example_commanders'] = [c for c in y.example_commanders if isinstance(c, str)][:12]
            if getattr(y, 'example_cards', None):
                # Limit to 20 for safety (UI may further cap)
                dedup_cards = []
                seen_cards = set()
                for c in y.example_cards:
                    if isinstance(c, str) and c and c not in seen_cards:
                        dedup_cards.append(c)
                        seen_cards.add(c)
                        if len(dedup_cards) >= 20:
                            break
                if dedup_cards:
                    entry['example_cards'] = dedup_cards
            if getattr(y, 'deck_archetype', None):
                entry['deck_archetype'] = y.deck_archetype
            if getattr(y, 'popularity_hint', None):
                entry['popularity_hint'] = y.popularity_hint
            # Pass through synergy_commanders if already curated (script will populate going forward)
            if hasattr(y, 'synergy_commanders') and getattr(y, 'synergy_commanders'):
                entry['synergy_commanders'] = [c for c in getattr(y, 'synergy_commanders') if isinstance(c, str)][:12]
        entries.append(entry)

    provenance = {
        'mode': 'merge',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'curated_yaml_files': len(yaml_catalog),
        'synergy_cap': synergy_cap,
        'inference': 'pmi',
        'version': 'phase-b-merge-v1'
    }
    return {
        'themes': entries,
        'frequencies_by_base_color': analytics['frequencies'],
        'generated_from': 'merge (analytics + curated YAML + whitelist)',
        'provenance': provenance,
    }


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Build merged theme catalog (Phase B)')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--schema', action='store_true', help='Print JSON Schema for catalog and exit')
    args = parser.parse_args()
    if args.schema:
        # Lazy import to avoid circular dependency: replicate minimal schema inline from models file if present
        try:
            from type_definitions_theme_catalog import ThemeCatalog  # type: ignore
            import json as _json
            print(_json.dumps(ThemeCatalog.model_json_schema(), indent=2))
            return
        except Exception as _e:  # pragma: no cover
            print(f"Failed to load schema models: {_e}")
            return
    data = build_catalog(limit=args.limit, verbose=args.verbose)
    if args.dry_run:
        print(json.dumps({'theme_count': len(data['themes']), 'provenance': data['provenance']}, indent=2))
    else:
        os.makedirs(OUTPUT_JSON.parent, exist_ok=True)
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # broad guard for orchestrator fallback
        print(f"ERROR: build_theme_catalog failed: {e}", file=sys.stderr)
        sys.exit(1)
