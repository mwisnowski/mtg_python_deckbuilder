"""Generate editorial metadata suggestions for theme YAML files (Phase D helper).

Features:
 - Scans color CSV files (skips monolithic cards.csv unless --include-master)
 - Collects top-N (lowest EDHREC rank) cards per theme based on themeTags column
 - Optionally derives commander suggestions from commander_cards.csv (if present)
 - Provides dry-run output (default) or can patch YAML files that lack example_cards / example_commanders
 - Prints streaming progress so the user sees real-time status

Usage (dry run):
  python code/scripts/generate_theme_editorial_suggestions.py --themes "Landfall,Reanimate" --top 8

Write back missing fields (only if not already present):
  python code/scripts/generate_theme_editorial_suggestions.py --apply --limit-yaml 500

Safety:
 - Existing example_cards / example_commanders are never overwritten unless --force is passed
 - Writes are limited by --limit-yaml (default 0 means unlimited) to avoid massive churn accidentally

Heuristics:
 - Deduplicate card names per theme
 - Filter out names with extremely poor rank (> 60000) by default (configurable)
 - For commander suggestions, prefer legendary creatures/planeswalkers in commander_cards.csv whose themeTags includes the theme
 - Fallback commander suggestions: take top legendary cards from color CSVs tagged with the theme
 - synergy_commanders: derive from top 3 synergies of each theme (3 from top, 2 from second, 1 from third)
 - Promotion: if fewer than --min-examples example_commanders exist after normal suggestion, promote synergy_commanders (in order) into example_commanders, annotating with " - Synergy (<synergy name>)"
"""
from __future__ import annotations

import argparse
import ast
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Set
import sys

try:  # optional dependency safety
    import yaml  # type: ignore
except Exception:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / 'csv_files'
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'

COLOR_CSV_GLOB = '*_cards.csv'
MASTER_FILE = 'cards.csv'
COMMANDER_FILE = 'commander_cards.csv'


@dataclass
class ThemeSuggestion:
    cards: List[str]
    commanders: List[str]
    synergy_commanders: List[str]


def _parse_theme_tags(raw: str) -> List[str]:
    if not raw:
        return []
    raw = raw.strip()
    if not raw or raw == '[]':
        return []
    try:
        # themeTags stored like "['Landfall', 'Ramp']" – use literal_eval safely
        val = ast.literal_eval(raw)
        if isinstance(val, list):
            return [str(x) for x in val if isinstance(x, str)]
    except Exception:
        pass
    # Fallback naive parse
    return [t.strip().strip("'\"") for t in raw.strip('[]').split(',') if t.strip()]


def scan_color_csvs(include_master: bool, max_rank: float, progress_every: int) -> Tuple[Dict[str, List[Tuple[float, str]]], Dict[str, List[Tuple[float, str]]]]:
    theme_hits: Dict[str, List[Tuple[float, str]]] = {}
    legendary_hits: Dict[str, List[Tuple[float, str]]] = {}
    files: List[Path] = []
    for fp in sorted(CSV_DIR.glob(COLOR_CSV_GLOB)):
        name = fp.name
        if name == MASTER_FILE and not include_master:
            continue
        if name == COMMANDER_FILE:
            continue
        # skip testdata
        if 'testdata' in str(fp):
            continue
        files.append(fp)
    total_files = len(files)
    processed = 0
    for fp in files:
        processed += 1
        try:
            with fp.open(encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                line_idx = 0
                for row in reader:
                    line_idx += 1
                    if progress_every and line_idx % progress_every == 0:
                        print(f"[scan] {fp.name} line {line_idx}", file=sys.stderr, flush=True)
                    tags_raw = row.get('themeTags') or ''
                    if not tags_raw:
                        continue
                    try:
                        rank = float(row.get('edhrecRank') or 999999)
                    except Exception:
                        rank = 999999
                    if rank > max_rank:
                        continue
                    tags = _parse_theme_tags(tags_raw)
                    name = row.get('name') or ''
                    if not name:
                        continue
                    is_legendary = False
                    try:
                        typ = row.get('type') or ''
                        if isinstance(typ, str) and 'Legendary' in typ.split():
                            is_legendary = True
                    except Exception:
                        pass
                    for t in tags:
                        if not t:
                            continue
                        theme_hits.setdefault(t, []).append((rank, name))
                        if is_legendary:
                            legendary_hits.setdefault(t, []).append((rank, name))
        except Exception as e:  # pragma: no cover
            print(f"[warn] failed reading {fp.name}: {e}", file=sys.stderr)
        print(f"[scan] completed {fp.name} ({processed}/{total_files})", file=sys.stderr, flush=True)
    # Trim each bucket to reasonable size (keep best ranks)
    for mapping, cap in ((theme_hits, 120), (legendary_hits, 80)):
        for t, lst in mapping.items():
            lst.sort(key=lambda x: x[0])
            if len(lst) > cap:
                del lst[cap:]
    return theme_hits, legendary_hits


def scan_commander_csv(max_rank: float) -> Dict[str, List[Tuple[float, str]]]:
    path = CSV_DIR / COMMANDER_FILE
    out: Dict[str, List[Tuple[float, str]]] = {}
    if not path.exists():
        return out
    try:
        with path.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tags_raw = row.get('themeTags') or ''
                if not tags_raw:
                    continue
                tags = _parse_theme_tags(tags_raw)
                try:
                    rank = float(row.get('edhrecRank') or 999999)
                except Exception:
                    rank = 999999
                if rank > max_rank:
                    continue
                name = row.get('name') or ''
                if not name:
                    continue
                for t in tags:
                    if not t:
                        continue
                    out.setdefault(t, []).append((rank, name))
    except Exception as e:  # pragma: no cover
        print(f"[warn] failed reading {COMMANDER_FILE}: {e}", file=sys.stderr)
    for t, lst in out.items():
        lst.sort(key=lambda x: x[0])
        if len(lst) > 60:
            del lst[60:]
    return out


def load_yaml_theme(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8')) if yaml else {}
    except Exception:
        return {}


def write_yaml_theme(path: Path, data: dict):
    txt = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(txt, encoding='utf-8')


def build_suggestions(theme_hits: Dict[str, List[Tuple[float, str]]], commander_hits: Dict[str, List[Tuple[float, str]]], top: int, top_commanders: int, *, synergy_top=(3,2,1), min_examples: int = 5) -> Dict[str, ThemeSuggestion]:
    suggestions: Dict[str, ThemeSuggestion] = {}
    all_themes: Set[str] = set(theme_hits.keys()) | set(commander_hits.keys())
    for t in sorted(all_themes):
        card_names: List[str] = []
        if t in theme_hits:
            for rank, name in theme_hits[t][: top * 3]:  # oversample then dedup
                if name not in card_names:
                    card_names.append(name)
                if len(card_names) >= top:
                    break
        commander_names: List[str] = []
        if t in commander_hits:
            for rank, name in commander_hits[t][: top_commanders * 2]:
                if name not in commander_names:
                    commander_names.append(name)
                if len(commander_names) >= top_commanders:
                    break
        # Placeholder synergy_commanders; will be filled later after we know synergies per theme from YAML
        suggestions[t] = ThemeSuggestion(cards=card_names, commanders=commander_names, synergy_commanders=[])
    return suggestions


def _derive_synergy_commanders(base_theme: str, data: dict, all_yaml: Dict[str, dict], commander_hits: Dict[str, List[Tuple[float, str]]], legendary_hits: Dict[str, List[Tuple[float, str]]], synergy_top=(3,2,1)) -> List[Tuple[str, str]]:
    """Pick synergy commanders with their originating synergy label.
    Returns list of (commander_name, synergy_theme) preserving order of (top synergy, second, third) and internal ranking.
    """
    synergies = data.get('synergies') or []
    if not isinstance(synergies, list):
        return []
    pattern = list(synergy_top)
    out: List[Tuple[str, str]] = []
    for idx, count in enumerate(pattern):
        if idx >= len(synergies):
            break
        s_name = synergies[idx]
        bucket = commander_hits.get(s_name) or []
        taken = 0
        for _, cname in bucket:
            if all(cname != existing for existing, _ in out):
                out.append((cname, s_name))
                taken += 1
                if taken >= count:
                    break
        if taken < count:
            # fallback to legendary card hits tagged with that synergy
            fallback_bucket = legendary_hits.get(s_name) or []
            for _, cname in fallback_bucket:
                if all(cname != existing for existing, _ in out):
                    out.append((cname, s_name))
                    taken += 1
                    if taken >= count:
                        break
    return out


def _augment_synergies(data: dict, base_theme: str) -> bool:
    """Heuristically augment the 'synergies' list when it's sparse.
    Rules:
      - If synergies length >= 3, leave as-is.
      - Start with existing synergies then append curated/enforced/inferred (in that order) if missing.
      - For any theme whose display_name contains 'Counter' add 'Counters Matter' and 'Proliferate'.
    Returns True if modified.
    """
    synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
    if not isinstance(synergies, list):
        return False
    original = list(synergies)
    if len(synergies) < 3:
        for key in ('curated_synergies', 'enforced_synergies', 'inferred_synergies'):
            lst = data.get(key)
            if isinstance(lst, list):
                for s in lst:
                    if isinstance(s, str) and s and s not in synergies:
                        synergies.append(s)
    name = data.get('display_name') or base_theme
    if isinstance(name, str) and 'counter' in name.lower():
        for extra in ('Counters Matter', 'Proliferate'):
            if extra not in synergies:
                synergies.append(extra)
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for s in synergies:
        if s not in seen:
            deduped.append(s)
            seen.add(s)
    if deduped != synergies:
        synergies = deduped
    if synergies != original:
        data['synergies'] = synergies
        return True
    return False


def apply_to_yaml(suggestions: Dict[str, ThemeSuggestion], *, limit_yaml: int, force: bool, themes_filter: Set[str], commander_hits: Dict[str, List[Tuple[float, str]]], legendary_hits: Dict[str, List[Tuple[float, str]]], synergy_top=(3,2,1), min_examples: int = 5, augment_synergies: bool = False, treat_placeholders_missing: bool = False):
    updated = 0
    # Preload all YAML for synergy lookups (avoid repeated disk IO inside loop)
    all_yaml_cache: Dict[str, dict] = {}
    for p in CATALOG_DIR.glob('*.yml'):
        try:
            all_yaml_cache[p.name] = load_yaml_theme(p)
        except Exception:
            pass
    for path in sorted(CATALOG_DIR.glob('*.yml')):
        data = load_yaml_theme(path)
        if not isinstance(data, dict):
            continue
        display = data.get('display_name')
        if not isinstance(display, str) or not display:
            continue
        if themes_filter and display not in themes_filter:
            continue
        sug = suggestions.get(display)
        if not sug:
            continue
        changed = False
        # Optional synergy augmentation prior to commander derivation
        if augment_synergies and _augment_synergies(data, display):
            changed = True
        # Derive synergy_commanders before promotion logic
        synergy_cmds = _derive_synergy_commanders(display, data, all_yaml_cache, commander_hits, legendary_hits, synergy_top=synergy_top)
        # Annotate synergy_commanders with their synergy source for transparency
        synergy_cmd_names = [f"{c} - Synergy ({src})" for c, src in synergy_cmds]
        if (force or not data.get('example_cards')) and sug.cards:
            data['example_cards'] = sug.cards
            changed = True
        existing_examples: List[str] = list(data.get('example_commanders') or []) if isinstance(data.get('example_commanders'), list) else []
        # Treat an all-placeholder (" Anchor" suffix) list as effectively empty when flag enabled
        if treat_placeholders_missing and existing_examples and all(isinstance(e, str) and e.endswith(' Anchor') for e in existing_examples):
            existing_examples = []
        if force or not existing_examples:
            if sug.commanders:
                data['example_commanders'] = list(sug.commanders)
                existing_examples = data['example_commanders']
                changed = True
        # (Attachment of synergy_commanders moved to after promotion so we can filter duplicates with example_commanders)
        # Re-annotate existing example_commanders if they use old base-theme annotation pattern
        if existing_examples and synergy_cmds:
            # Detect old pattern: ends with base theme name inside parentheses
            needs_reannotate = False
            old_suffix = f" - Synergy ({display})"
            for ex in existing_examples:
                if ex.endswith(old_suffix):
                    needs_reannotate = True
                    break
            if needs_reannotate:
                # Build mapping from commander name to synergy source
                source_map = {name: src for name, src in synergy_cmds}
                new_examples: List[str] = []
                for ex in existing_examples:
                    if ' - Synergy (' in ex:
                        base_name = ex.split(' - Synergy ')[0]
                        if base_name in source_map:
                            new_examples.append(f"{base_name} - Synergy ({source_map[base_name]})")
                            continue
                    new_examples.append(ex)
                if new_examples != existing_examples:
                    data['example_commanders'] = new_examples
                    existing_examples = new_examples
                    changed = True
        # Promotion: ensure at least min_examples in example_commanders by moving from synergy list (without duplicates)
        if (len(existing_examples) < min_examples) and synergy_cmd_names:
            needed = min_examples - len(existing_examples)
            promoted = []
            for cname, source_synergy in synergy_cmds:
                # Avoid duplicate even with annotation
                if not any(cname == base.split(' - Synergy ')[0] for base in existing_examples):
                    annotated = f"{cname} - Synergy ({source_synergy})"
                    existing_examples.append(annotated)
                    promoted.append(cname)
                    needed -= 1
                    if needed <= 0:
                        break
            if promoted:
                data['example_commanders'] = existing_examples
                changed = True
        # After any potential promotions / re-annotations, attach synergy_commanders excluding any commanders already present in example_commanders
        existing_base_names = {ex.split(' - Synergy ')[0] for ex in (data.get('example_commanders') or []) if isinstance(ex, str)}
        filtered_synergy_cmd_names = []
        for entry in synergy_cmd_names:
            base = entry.split(' - Synergy ')[0]
            if base not in existing_base_names:
                filtered_synergy_cmd_names.append(entry)
        prior_synergy_cmds = data.get('synergy_commanders') if isinstance(data.get('synergy_commanders'), list) else []
        if prior_synergy_cmds != filtered_synergy_cmd_names:
            if filtered_synergy_cmd_names or force or prior_synergy_cmds:
                data['synergy_commanders'] = filtered_synergy_cmd_names
                changed = True

        if changed:
            write_yaml_theme(path, data)
            updated += 1
            print(f"[apply] updated {path.name}")
            if limit_yaml and updated >= limit_yaml:
                print(f"[apply] reached limit {limit_yaml}; stopping")
                break
    return updated


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Generate example_cards / example_commanders suggestions for theme YAML')
    parser.add_argument('--themes', type=str, help='Comma-separated subset of display names to restrict')
    parser.add_argument('--top', type=int, default=8, help='Target number of example_cards suggestions')
    parser.add_argument('--top-commanders', type=int, default=5, help='Target number of example_commanders suggestions')
    parser.add_argument('--max-rank', type=float, default=60000, help='Skip cards with EDHREC rank above this threshold')
    parser.add_argument('--include-master', action='store_true', help='Include large cards.csv in scan (slower)')
    parser.add_argument('--progress-every', type=int, default=0, help='Emit a progress line every N rows per file')
    parser.add_argument('--apply', action='store_true', help='Write missing fields into YAML files')
    parser.add_argument('--limit-yaml', type=int, default=0, help='Limit number of YAML files modified (0 = unlimited)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing example lists')
    parser.add_argument('--min-examples', type=int, default=5, help='Minimum desired example_commanders; promote from synergy_commanders if short')
    parser.add_argument('--augment-synergies', action='store_true', help='Heuristically augment sparse synergies list before deriving synergy_commanders')
    parser.add_argument('--treat-placeholders', action='store_true', help='Consider Anchor-only example_commanders lists as missing so they can be replaced')
    args = parser.parse_args()

    themes_filter: Set[str] = set()
    if args.themes:
        themes_filter = {t.strip() for t in args.themes.split(',') if t.strip()}

    print('[info] scanning CSVs...', file=sys.stderr)
    theme_hits, legendary_hits = scan_color_csvs(args.include_master, args.max_rank, args.progress_every)
    print('[info] scanning commander CSV...', file=sys.stderr)
    commander_hits = scan_commander_csv(args.max_rank)
    print('[info] building suggestions...', file=sys.stderr)
    suggestions = build_suggestions(theme_hits, commander_hits, args.top, args.top_commanders, min_examples=args.min_examples)

    if not args.apply:
        # Dry run: print JSON-like summary for filtered subset (or first 25 themes)
        to_show = sorted(themes_filter) if themes_filter else list(sorted(suggestions.keys())[:25])
        for t in to_show:
            s = suggestions.get(t)
            if not s:
                continue
            print(f"\n=== {t} ===")
            print('example_cards:', ', '.join(s.cards) or '(none)')
            print('example_commanders:', ', '.join(s.commanders) or '(none)')
            print('synergy_commanders: (computed at apply time)')
        print('\n[info] dry-run complete (use --apply to write)')
        return

    if yaml is None:
        print('ERROR: PyYAML not installed; cannot apply changes.', file=sys.stderr)
        sys.exit(1)
    updated = apply_to_yaml(
        suggestions,
        limit_yaml=args.limit_yaml,
        force=args.force,
        themes_filter=themes_filter,
        commander_hits=commander_hits,
        legendary_hits=legendary_hits,
        synergy_top=(3,2,1),
        min_examples=args.min_examples,
        augment_synergies=args.augment_synergies,
        treat_placeholders_missing=args.treat_placeholders,
    )
    print(f'[info] updated {updated} YAML files')


if __name__ == '__main__':  # pragma: no cover
    main()
