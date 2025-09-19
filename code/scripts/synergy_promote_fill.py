"""Editorial population helper for theme YAML files.

Features implemented here:

Commander population modes:
 - Padding: Fill undersized example_commanders lists (< --min) with synergy-derived commanders.
 - Rebalance: Prepend missing base-theme commanders if list already meets --min but lacks them.
 - Base-first rebuild: Overwrite lists using ordering (base tag -> synergy tag -> color fallback), truncating to --min.

Example cards population (NEW):
 - Optional (--fill-example-cards) creation/padding of example_cards lists to a target size (default 10)
   using base theme cards first, then synergy theme cards, then color-identity fallback.
 - EDHREC ordering: Uses ascending edhrecRank sourced from cards.csv (if present) or shard CSVs.
 - Avoids reusing commander names (base portion of commander entries) to diversify examples.

Safeguards:
 - Dry run by default (no writes unless --apply)
 - Does not truncate existing example_cards if already >= target
 - Deduplicates by raw card name

Typical usage:
  Populate commanders only (padding):
      python code/scripts/synergy_promote_fill.py --min 5 --apply

  Base-first rebuild of commanders AND populate 10 example cards:
      python code/scripts/synergy_promote_fill.py --base-first-rebuild --min 5 \
          --fill-example-cards --cards-target 10 --apply

  Only fill example cards (leave commanders untouched):
      python code/scripts/synergy_promote_fill.py --fill-example-cards --cards-target 10 --apply
"""
from __future__ import annotations
import argparse
import ast
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Set, Iterable, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / 'csv_files'
CATALOG_DIR = ROOT / 'config' / 'themes' / 'catalog'
COLOR_CSV_GLOB = '*_cards.csv'
COMMANDER_FILE = 'commander_cards.csv'
MASTER_CARDS_FILE = 'cards.csv'


def parse_theme_tags(raw: str) -> List[str]:
    if not raw:
        return []
    raw = raw.strip()
    if not raw or raw == '[]':
        return []
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, list):
            return [str(x) for x in val if isinstance(x, str)]
    except Exception:
        pass
    return [t.strip().strip("'\"") for t in raw.strip('[]').split(',') if t.strip()]


def parse_color_identity(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    raw = raw.strip()
    if not raw:
        return set()
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, (list, tuple)):
            return {str(x).upper() for x in val if str(x).upper() in {'W','U','B','R','G','C'}}
    except Exception:
        pass
    # fallback: collect mana letters present
    return {ch for ch in raw.upper() if ch in {'W','U','B','R','G','C'}}


def scan_sources(max_rank: float) -> Tuple[Dict[str, List[Tuple[float,str]]], Dict[str, List[Tuple[float,str]]], List[Tuple[float,str,Set[str]]]]:
    """Build commander candidate pools exclusively from commander_cards.csv.

    We intentionally ignore the color shard *_cards.csv sources here because those
    include many non-commander legendary permanents or context-specific lists; using
    only commander_cards.csv guarantees every suggestion is a legal commander.

    Returns:
        theme_hits: mapping theme tag -> sorted unique list of (rank, commander name)
        theme_all_legendary_hits: alias of theme_hits (legacy return shape)
        color_pool: list of (rank, commander name, color identity set)
    """
    theme_hits: Dict[str, List[Tuple[float,str]]] = {}
    color_pool: List[Tuple[float,str,Set[str]]] = []
    commander_path = CSV_DIR / COMMANDER_FILE
    if not commander_path.exists():
        return {}, {}, []
    try:
        with commander_path.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rank = float(row.get('edhrecRank') or 999999)
                except Exception:
                    rank = 999999
                if rank > max_rank:
                    continue
                typ = row.get('type') or ''
                if 'Legendary' not in typ:
                    continue
                name = row.get('name') or ''
                if not name:
                    continue
                ci = parse_color_identity(row.get('colorIdentity') or row.get('colors'))
                color_pool.append((rank, name, ci))
                tags_raw = row.get('themeTags') or ''
                if tags_raw:
                    for t in parse_theme_tags(tags_raw):
                        theme_hits.setdefault(t, []).append((rank, name))
    except Exception:
        pass
    # Deduplicate + sort theme hits
    for t, lst in theme_hits.items():
        lst.sort(key=lambda x: x[0])
        seen: Set[str] = set()
        dedup: List[Tuple[float,str]] = []
        for r, n in lst:
            if n in seen:
                continue
            seen.add(n)
            dedup.append((r, n))
        theme_hits[t] = dedup
    # Deduplicate color pool (keep best rank)
    color_pool.sort(key=lambda x: x[0])
    seen_cp: Set[str] = set()
    dedup_pool: List[Tuple[float,str,Set[str]]] = []
    for r, n, cset in color_pool:
        if n in seen_cp:
            continue
        seen_cp.add(n)
        dedup_pool.append((r, n, cset))
    return theme_hits, theme_hits, dedup_pool


def scan_card_pool(max_rank: float, use_master: bool = False) -> Tuple[Dict[str, List[Tuple[float, str, Set[str]]]], List[Tuple[float, str, Set[str]]]]:
    """Scan non-commander card pool for example_cards population.

    Default behavior (preferred per project guidance): ONLY use the shard color CSVs ([color]_cards.csv).
    The consolidated master ``cards.csv`` contains every card face/variant and can introduce duplicate
    or art-variant noise (e.g., "Sol Ring // Sol Ring"). We therefore avoid it unless explicitly
    requested via ``use_master=True`` / ``--use-master-cards``.

    When the master file is used we prefer ``faceName`` over ``name`` (falls back to name) and
    collapse redundant split names like "Foo // Foo" to just "Foo".

    Returns:
        theme_card_hits: mapping theme tag -> [(rank, card name, color set)] sorted & deduped
        color_pool: global list of unique cards for color fallback
    """
    theme_card_hits: Dict[str, List[Tuple[float, str, Set[str]]]] = {}
    color_pool: List[Tuple[float, str, Set[str]]] = []
    master_path = CSV_DIR / MASTER_CARDS_FILE

    def canonical_name(row: Dict[str, str]) -> str:
        nm = (row.get('faceName') or row.get('name') or '').strip()
        if '//' in nm:
            parts = [p.strip() for p in nm.split('//')]
            if len(parts) == 2 and parts[0] == parts[1]:
                nm = parts[0]
        return nm

    def _process_row(row: Dict[str, str]):
        try:
            rank = float(row.get('edhrecRank') or 999999)
        except Exception:
            rank = 999999
        if rank > max_rank:
            return
        # Prefer canonicalized name (faceName if present; collapse duplicate split faces)
        name = canonical_name(row)
        if not name:
            return
        ci = parse_color_identity(row.get('colorIdentity') or row.get('colors'))
        tags_raw = row.get('themeTags') or ''
        if tags_raw:
            for t in parse_theme_tags(tags_raw):
                theme_card_hits.setdefault(t, []).append((rank, name, ci))
        color_pool.append((rank, name, ci))
    # Collection strategy
    if use_master and master_path.exists():
        try:
            with master_path.open(encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    _process_row(row)
        except Exception:
            pass  # fall through to shards if master problematic
    # Always process shards (either primary source or to ensure we have coverage if master read failed)
    if not use_master or not master_path.exists():
        for fp in sorted(CSV_DIR.glob(COLOR_CSV_GLOB)):
            if fp.name in {COMMANDER_FILE}:
                continue
            if 'testdata' in str(fp):
                continue
            try:
                with fp.open(encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        _process_row(row)
            except Exception:
                continue

    # Dedup + rank-sort per theme
    for t, lst in theme_card_hits.items():
        lst.sort(key=lambda x: x[0])
        seen: Set[str] = set()
        dedup: List[Tuple[float, str, Set[str]]] = []
        for r, n, cset in lst:
            if n in seen:
                continue
            seen.add(n)
            dedup.append((r, n, cset))
        theme_card_hits[t] = dedup
    # Dedup global color pool (keep best rank occurrence)
    color_pool.sort(key=lambda x: x[0])
    seen_global: Set[str] = set()
    dedup_global: List[Tuple[float, str, Set[str]]] = []
    for r, n, cset in color_pool:
        if n in seen_global:
            continue
        seen_global.add(n)
        dedup_global.append((r, n, cset))
    return theme_card_hits, dedup_global


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8')) if yaml else {}
    except Exception:
        return {}


def save_yaml(path: Path, data: dict):
    txt = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(txt, encoding='utf-8')


def theme_color_set(data: dict) -> Set[str]:
    mapping = {'White':'W','Blue':'U','Black':'B','Red':'R','Green':'G','Colorless':'C'}
    out: Set[str] = set()
    for key in ('primary_color','secondary_color','tertiary_color'):
        val = data.get(key)
        if isinstance(val, str) and val in mapping:
            out.add(mapping[val])
    return out


def rebuild_base_first(
    data: dict,
    theme_hits: Dict[str, List[Tuple[float,str]]],
    min_examples: int,
    color_pool: Iterable[Tuple[float,str,Set[str]]],
    annotate_color_reason: bool = False,
) -> List[str]:
    """Return new example_commanders list using base-first strategy."""
    if not isinstance(data, dict):
        return []
    display = data.get('display_name') or ''
    synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
    chosen: List[str] = []
    used: Set[str] = set()
    # Base theme hits first (rank order)
    for _, cname in theme_hits.get(display, []):
        if len(chosen) >= min_examples:
            break
        if cname in used:
            continue
        chosen.append(cname)
        used.add(cname)
    # Synergy hits annotated
    if len(chosen) < min_examples:
        for syn in synergies:
            for _, cname in theme_hits.get(syn, []):
                if len(chosen) >= min_examples:
                    break
                if cname in used:
                    continue
                chosen.append(f"{cname} - Synergy ({syn})")
                used.add(cname)
            if len(chosen) >= min_examples:
                break
    # Color fallback
    if len(chosen) < min_examples:
        t_colors = theme_color_set(data)
        if t_colors:
            for _, cname, cset in color_pool:
                if len(chosen) >= min_examples:
                    break
                if cset - t_colors:
                    continue
                if cname in used:
                    continue
                if annotate_color_reason:
                    chosen.append(f"{cname} - Color Fallback (no on-theme commander available)")
                else:
                    chosen.append(cname)
                used.add(cname)
    return chosen[:min_examples]


def fill_example_cards(
    data: dict,
    theme_card_hits: Dict[str, List[Tuple[float, str, Set[str]]]],
    color_pool: Iterable[Tuple[float, str, Set[str]]],
    target: int,
    avoid: Optional[Set[str]] = None,
    allow_color_fallback: bool = True,
    rebuild: bool = False,
) -> Tuple[bool, List[str]]:
    """Populate or pad example_cards using base->synergy->color ordering.

    - Card ordering within each phase preserves ascending EDHREC rank (already sorted).
    - 'avoid' set lets us skip commander names to diversify examples.
    - Does not shrink an overfilled list (only grows up to target).
    Returns (changed, added_entries).
    """
    if not isinstance(data, dict):
        return False, []
    cards_field = data.get('example_cards')
    if not isinstance(cards_field, list):
        cards_field = []
    # Rebuild forces clearing existing list so we can repopulate even if already at target size
    if rebuild:
        cards_field = []
    original = list(cards_field)
    if len(cards_field) >= target and not rebuild:
        return False, []  # nothing to do when already populated unless rebuilding
    display = data.get('display_name') or ''
    synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
    used: Set[str] = {c for c in cards_field if isinstance(c, str)}
    if avoid:
        used |= avoid
    # Phase 1: base theme cards
    for _, name, _ in theme_card_hits.get(display, []):
        if len(cards_field) >= target:
            break
        if name in used:
            continue
        cards_field.append(name)
        used.add(name)
    # Phase 2: synergy cards
    if len(cards_field) < target:
        for syn in synergies:
            for _, name, _ in theme_card_hits.get(syn, []):
                if len(cards_field) >= target:
                    break
                if name in used:
                    continue
                cards_field.append(name)
                used.add(name)
            if len(cards_field) >= target:
                break
    # Phase 3: color fallback
    if allow_color_fallback and len(cards_field) < target:
        t_colors = theme_color_set(data)
        if t_colors:
            for _, name, cset in color_pool:
                if len(cards_field) >= target:
                    break
                if name in used:
                    continue
                if cset - t_colors:
                    continue
                cards_field.append(name)
                used.add(name)
    # Trim safeguard (should not exceed target)
    if len(cards_field) > target:
        del cards_field[target:]
    if cards_field != original:
        data['example_cards'] = cards_field
        added = [c for c in cards_field if c not in original]
        return True, added
    return False, []


def pad_theme(
    data: dict,
    theme_hits: Dict[str, List[Tuple[float,str]]],
    min_examples: int,
    color_pool: Iterable[Tuple[float,str,Set[str]]],
    base_min: int = 2,
    drop_annotation_if_base: bool = True,
) -> Tuple[bool, List[str]]:
    """Return (changed, added_entries).

    Hybrid strategy:
      1. Ensure up to base_min commanders directly tagged with the base theme (display_name) appear (unannotated)
         before filling remaining slots.
      2. Then add synergy-tagged commanders (annotated) in listed order, skipping duplicates.
      3. If still short, cycle remaining base hits (if any unused) and then color fallback.
      4. If a commander is both a base hit and added during synergy phase and drop_annotation_if_base=True,
         we emit it unannotated to highlight it as a flagship example.
    """
    if not isinstance(data, dict):
        return False, []
    examples = data.get('example_commanders')
    if not isinstance(examples, list):
        # Treat missing / invalid field as empty to allow first-time population
        examples = []
        data['example_commanders'] = examples
    if len(examples) >= min_examples:
        return False, []
    synergies = data.get('synergies') if isinstance(data.get('synergies'), list) else []
    display = data.get('display_name') or ''
    base_names = {e.split(' - Synergy ')[0] for e in examples if isinstance(e,str)}
    added: List[str] = []
    # Phase 1: seed with base theme commanders (unannotated) up to base_min
    base_cands = theme_hits.get(display) or []
    for _, cname in base_cands:
        if len(examples) + len(added) >= min_examples or len([a for a in added if ' - Synergy (' not in a]) >= base_min:
            break
        if cname in base_names:
            continue
        base_names.add(cname)
        added.append(cname)

    # Phase 2: synergy-based candidates following list order
    for syn in synergies:
        if len(examples) + len(added) >= min_examples:
            break
        cand_list = theme_hits.get(syn) or []
        for _, cname in cand_list:
            if len(examples) + len(added) >= min_examples:
                break
            if cname in base_names:
                continue
            # If commander is ALSO tagged with base theme and we want a clean flagship, drop annotation
            base_tagged = any(cname == bn for _, bn in base_cands)
            if base_tagged and drop_annotation_if_base:
                annotated = cname
            else:
                annotated = f"{cname} - Synergy ({syn})"
            base_names.add(cname)
            added.append(annotated)

    # Phase 3: if still short, add any remaining unused base hits (unannotated)
    if len(examples) + len(added) < min_examples:
        for _, cname in base_cands:
            if len(examples) + len(added) >= min_examples:
                break
            if cname in base_names:
                continue
            base_names.add(cname)
            added.append(cname)
    if len(examples) + len(added) < min_examples:
        # Color-aware fallback: fill with top-ranked legendary commanders whose color identity is subset of theme colors
        t_colors = theme_color_set(data)
        if t_colors:
            for _, cname, cset in color_pool:
                if len(examples) + len(added) >= min_examples:
                    break
                if not cset:  # colorless commander acceptable if theme includes C or any color (subset logic handles) 
                    pass
                if cset - t_colors:
                    continue  # requires colors outside theme palette
                if cname in base_names:
                    continue
                base_names.add(cname)
                added.append(cname)  # unannotated to avoid invalid synergy annotation
    if added:
        data['example_commanders'] = examples + added
        return True, added
    return False, []


def main():  # pragma: no cover (script orchestration)
    ap = argparse.ArgumentParser(description='Synergy-based padding for undersized example_commanders lists')
    ap.add_argument('--min', type=int, default=5, help='Minimum target examples (default 5)')
    ap.add_argument('--max-rank', type=float, default=60000, help='EDHREC rank ceiling for candidate commanders')
    ap.add_argument('--base-min', type=int, default=2, help='Minimum number of base-theme commanders (default 2)')
    ap.add_argument('--no-drop-base-annotation', action='store_true', help='Do not drop synergy annotation when commander also has base theme tag')
    ap.add_argument('--rebalance', action='store_true', help='Adjust themes already meeting --min if they lack required base-theme commanders')
    ap.add_argument('--base-first-rebuild', action='store_true', help='Overwrite lists using base-first strategy (base -> synergy -> color)')
    ap.add_argument('--apply', action='store_true', help='Write changes (default dry-run)')
    # Example cards population flags
    ap.add_argument('--fill-example-cards', action='store_true', help='Populate example_cards (base->synergy->[color fallback])')
    ap.add_argument('--cards-target', type=int, default=10, help='Target number of example_cards (default 10)')
    ap.add_argument('--cards-max-rank', type=float, default=60000, help='EDHREC rank ceiling for example_cards candidates')
    ap.add_argument('--cards-no-color-fallback', action='store_true', help='Do NOT use color identity fallback for example_cards (only theme & synergies)')
    ap.add_argument('--rebuild-example-cards', action='store_true', help='Discard existing example_cards and rebuild from scratch')
    ap.add_argument('--text-heuristics', action='store_true', help='Augment example_cards by scanning card text for theme keywords when direct tag hits are empty')
    ap.add_argument('--no-generic-pad', action='store_true', help='When true, leave example_cards shorter than target instead of filling with generic color-fallback or staple cards')
    ap.add_argument('--annotate-color-fallback-commanders', action='store_true', help='Annotate color fallback commander additions with reason when base/synergy empty')
    ap.add_argument('--heuristic-rank-cap', type=float, default=25000, help='Maximum EDHREC rank allowed for heuristic text-derived candidates (default 25000)')
    ap.add_argument('--use-master-cards', action='store_true', help='Use consolidated master cards.csv (default: use only shard [color]_cards.csv files)')
    ap.add_argument('--cards-limited-color-fallback-threshold', type=int, default=0, help='If >0 and color fallback disabled, allow a second limited color fallback pass only for themes whose example_cards count remains below this threshold after heuristics')
    ap.add_argument('--common-card-threshold', type=float, default=0.18, help='Exclude candidate example_cards appearing (before build) in > this fraction of themes (default 0.18 = 18%)')
    ap.add_argument('--print-dup-metrics', action='store_true', help='Print global duplicate frequency metrics for example_cards after run')
    args = ap.parse_args()
    if yaml is None:
        print('PyYAML not installed')
        raise SystemExit(1)
    theme_hits, _, color_pool = scan_sources(args.max_rank)
    theme_card_hits: Dict[str, List[Tuple[float, str, Set[str]]]] = {}
    card_color_pool: List[Tuple[float, str, Set[str]]] = []
    name_index: Dict[str, Tuple[float, str, Set[str]]] = {}
    if args.fill_example_cards:
        theme_card_hits, card_color_pool = scan_card_pool(args.cards_max_rank, use_master=args.use_master_cards)
        # Build quick lookup for manual overrides
        name_index = {n: (r, n, c) for r, n, c in card_color_pool}
    changed_count = 0
    cards_changed = 0
    # Precompute text index lazily only if requested
    text_index: Dict[str, List[Tuple[float, str, Set[str]]]] = {}
    staples_block: Set[str] = {  # common generic staples to suppress unless they match heuristics explicitly
        'Sol Ring','Arcane Signet','Command Tower','Exotic Orchard','Path of Ancestry','Swiftfoot Boots','Lightning Greaves','Reliquary Tower'
    }
    # Build text index if heuristics requested
    if args.text_heuristics:
        # Build text index from the same source strategy: master (optional) + shards, honoring faceName & canonical split collapse.
        import re
        def _scan_rows_for_text(reader):
            for row in reader:
                try:
                    rank = float(row.get('edhrecRank') or 999999)
                except Exception:
                    rank = 999999
                if rank > args.cards_max_rank:
                    continue
                # canonical naming logic (mirrors scan_card_pool)
                nm = (row.get('faceName') or row.get('name') or '').strip()
                if '//' in nm:
                    parts = [p.strip() for p in nm.split('//')]
                    if len(parts) == 2 and parts[0] == parts[1]:
                        nm = parts[0]
                if not nm:
                    continue
                text = (row.get('text') or '').lower()
                ci = parse_color_identity(row.get('colorIdentity') or row.get('colors'))
                tokens = set(re.findall(r"\+1/\+1|[a-zA-Z']+", text))
                for t in tokens:
                    if not t:
                        continue
                    bucket = text_index.setdefault(t, [])
                    bucket.append((rank, nm, ci))
        try:
            if args.use_master_cards and (CSV_DIR / MASTER_CARDS_FILE).exists():
                with (CSV_DIR / MASTER_CARDS_FILE).open(encoding='utf-8', newline='') as f:
                    _scan_rows_for_text(csv.DictReader(f))
            # Always include shards (they are authoritative curated sets)
            for fp in sorted(CSV_DIR.glob(COLOR_CSV_GLOB)):
                if fp.name in {COMMANDER_FILE} or 'testdata' in str(fp):
                    continue
                with fp.open(encoding='utf-8', newline='') as f:
                    _scan_rows_for_text(csv.DictReader(f))
            # sort & dedup per token
            for tok, lst in text_index.items():
                lst.sort(key=lambda x: x[0])
                seen_tok: Set[str] = set()
                dedup_tok: List[Tuple[float, str, Set[str]]] = []
                for r, n, c in lst:
                    if n in seen_tok:
                        continue
                    seen_tok.add(n)
                    dedup_tok.append((r, n, c))
                text_index[tok] = dedup_tok
        except Exception:
            text_index = {}

    def heuristic_candidates(theme_name: str) -> List[Tuple[float, str, Set[str]]]:
        if not args.text_heuristics or not text_index:
            return []
        name_lower = theme_name.lower()
        manual: Dict[str, List[str]] = {
            'landfall': ['landfall'],
            'reanimate': ['reanimate','unearth','eternalize','return','graveyard'],
            'tokens matter': ['token','populate','clue','treasure','food','blood','incubator','map','powerstone','role'],
            '+1/+1 counters': ['+1/+1','counter','proliferate','adapt','evolve'],
            'superfriends': ['planeswalker','loyalty','proliferate'],
            'aggro': ['haste','attack','battalion','raid','melee'],
            'lifegain': ['life','lifelink'],
            'graveyard matters': ['graveyard','dies','mill','disturb','flashback'],
            'group hug': ['draw','each','everyone','opponent','card','all'],
            'politics': ['each','player','vote','council'],
            'stax': ['sacrifice','upkeep','each','player','skip'],
            'aristocrats': ['dies','sacrifice','token'],
            'sacrifice matters': ['sacrifice','dies'],
            'sacrifice to draw': ['sacrifice','draw'],
            'artifact tokens': ['treasure','clue','food','blood','powerstone','incubator','map'],
            'archer kindred': ['archer','bow','ranged'],
            'eerie': ['enchant','aura','role','eerie'],
        }
        # Manual hand-picked iconic cards per theme (prioritized before token buckets)
        manual_cards: Dict[str, List[str]] = {
            'group hug': [
                'Howling Mine','Temple Bell','Rites of Flourishing','Kami of the Crescent Moon','Dictate of Kruphix',
                'Font of Mythos','Minds Aglow','Collective Voyage','Horn of Greed','Prosperity'
            ],
            'reanimate': [
                'Reanimate','Animate Dead','Victimize','Living Death','Necromancy',
                'Exhume','Dread Return','Unburial Rites','Persist','Stitch Together'
            ],
            'archer kindred': [
                'Greatbow Doyen','Archer\'s Parapet','Jagged-Scar Archers','Silklash Spider','Elite Scaleguard',
                'Kyren Sniper','Viridian Longbow','Brigid, Hero of Kinsbaile','Longshot Squad','Evolution Sage'
            ],
            'eerie': [
                'Sythis, Harvest\'s Hand','Enchantress\'s Presence','Setessan Champion','Eidolon of Blossoms','Mesa Enchantress',
                'Sterling Grove','Calix, Guided by Fate','Femeref Enchantress','Satyr Enchanter','Argothian Enchantress'
            ],
        }
        keys = manual.get(name_lower, [])
        if not keys:
            # derive naive tokens: split words >3 chars
            import re
            keys = [w for w in re.findall(r'[a-zA-Z\+\/]+', name_lower) if len(w) > 3 or '+1/+1' in w]
        merged: List[Tuple[float, str, Set[str]]] = []
        seen: Set[str] = set()
        # Insert manual card overrides first (respect rank cap if available)
        if name_lower in manual_cards and name_index:
            for card in manual_cards[name_lower]:
                tup = name_index.get(card)
                if not tup:
                    continue
                r, n, ci = tup
                if r > args.heuristic_rank_cap:
                    continue
                if n in seen:
                    continue
                seen.add(n)
                merged.append(tup)
        for k in keys:
            bucket = text_index.get(k)
            if not bucket:
                continue
            for r, n, ci in bucket[:120]:
                if n in seen:
                    continue
                if r > args.heuristic_rank_cap:
                    continue
                # skip staples if they lack the keyword in name (avoid universal ramp/utility artifacts)
                if n in staples_block and k not in n.lower():
                    continue
                seen.add(n)
                merged.append((r, n, ci))
            if len(merged) >= 60:
                break
        return merged

    for path in sorted(CATALOG_DIR.glob('*.yml')):
        data = load_yaml(path)
        if not data or not isinstance(data, dict) or not data.get('display_name'):
            continue
        notes = data.get('notes')
        if isinstance(notes, str) and 'Deprecated alias file' in notes:
            continue
        ex = data.get('example_commanders')
        if not isinstance(ex, list):
            ex = []
            data['example_commanders'] = ex
        need_rebalance = False
        if args.base_first_rebuild:
            new_list = rebuild_base_first(
                data,
                theme_hits,
                args.min,
                color_pool,
                annotate_color_reason=args.annotate_color_fallback_commanders,
            )
            if new_list != ex:
                data['example_commanders'] = new_list
                changed_count += 1
                print(f"[rebuild] {path.name}: {len(ex)} -> {len(new_list)}")
                if args.apply:
                    save_yaml(path, data)
        else:
            if len(ex) >= args.min:
                if args.rebalance and data.get('display_name'):
                    base_tag = data['display_name']
                    base_cands = {n for _, n in theme_hits.get(base_tag, [])}
                    existing_base_examples = [e for e in ex if (e.split(' - Synergy ')[0]) in base_cands and ' - Synergy (' not in e]
                    if len(existing_base_examples) < args.base_min and base_cands:
                        need_rebalance = True
                if not need_rebalance:
                    pass  # leave commanders untouched (might still fill cards)
            if need_rebalance:
                orig_len = len(ex)
                base_tag = data['display_name']
                base_cands_ordered = [n for _, n in theme_hits.get(base_tag, [])]
                current_base_names = {e.split(' - Synergy ')[0] for e in ex}
                additions: List[str] = []
                for cname in base_cands_ordered:
                    if len([a for a in ex + additions if ' - Synergy (' not in a]) >= args.base_min:
                        break
                    if cname in current_base_names:
                        continue
                    additions.append(cname)
                    current_base_names.add(cname)
                if additions:
                    data['example_commanders'] = additions + ex
                    changed_count += 1
                    print(f"[rebalance] {path.name}: inserted {len(additions)} base exemplars (len {orig_len} -> {len(data['example_commanders'])})")
                    if args.apply:
                        save_yaml(path, data)
            else:
                if len(ex) < args.min:
                    orig_len = len(ex)
                    changed, added = pad_theme(
                        data,
                        theme_hits,
                        args.min,
                        color_pool,
                        base_min=args.base_min,
                        drop_annotation_if_base=not args.no_drop_base_annotation,
                    )
                    if changed:
                        changed_count += 1
                        print(f"[promote] {path.name}: {orig_len} -> {len(data['example_commanders'])} (added {len(added)})")
                        if args.apply:
                            save_yaml(path, data)
        # Example cards population
        if args.fill_example_cards:
            avoid = {c.split(' - Synergy ')[0] for c in data.get('example_commanders', []) if isinstance(c, str)}
            pre_cards_len = len(data.get('example_cards') or []) if isinstance(data.get('example_cards'), list) else 0
            # If no direct tag hits for base theme AND heuristics enabled, inject synthetic hits
            display = data.get('display_name') or ''
            if args.text_heuristics and display and not theme_card_hits.get(display):
                cand = heuristic_candidates(display)
                if cand:
                    theme_card_hits[display] = cand
            # Build global duplicate frequency map ONCE (baseline prior to this run) if threshold active
            if args.common_card_threshold > 0 and 'GLOBAL_CARD_FREQ' not in globals():  # type: ignore
                freq: Dict[str, int] = {}
                total_themes = 0
                for fp0 in CATALOG_DIR.glob('*.yml'):
                    dat0 = load_yaml(fp0)
                    if not isinstance(dat0, dict):
                        continue
                    ecs0 = dat0.get('example_cards')
                    if not isinstance(ecs0, list) or not ecs0:
                        continue
                    total_themes += 1
                    seen_local: Set[str] = set()
                    for c in ecs0:
                        if not isinstance(c, str) or c in seen_local:
                            continue
                        seen_local.add(c)
                        freq[c] = freq.get(c, 0) + 1
                globals()['GLOBAL_CARD_FREQ'] = (freq, total_themes)  # type: ignore
            # Apply duplicate filtering to candidate lists (do NOT mutate existing example_cards)
            if args.common_card_threshold > 0 and 'GLOBAL_CARD_FREQ' in globals():  # type: ignore
                freq_map, total_prev = globals()['GLOBAL_CARD_FREQ']  # type: ignore
                if total_prev > 0:  # avoid div-by-zero
                    cutoff = args.common_card_threshold
                    def _filter(lst: List[Tuple[float, str, Set[str]]]) -> List[Tuple[float, str, Set[str]]]:
                        out: List[Tuple[float, str, Set[str]]] = []
                        for r, n, cset in lst:
                            if (freq_map.get(n, 0) / total_prev) > cutoff:
                                continue
                            out.append((r, n, cset))
                        return out
                    if display in theme_card_hits:
                        theme_card_hits[display] = _filter(theme_card_hits[display])
                    for syn in (data.get('synergies') or []):
                        if syn in theme_card_hits:
                            theme_card_hits[syn] = _filter(theme_card_hits[syn])
            changed_cards, added_cards = fill_example_cards(
                data,
                theme_card_hits,
                card_color_pool,
                # Keep target upper bound even when --no-generic-pad so we still collect
                # base + synergy thematic cards; the flag simply disables color/generic
                # fallback padding rather than suppressing all population.
                args.cards_target,
                avoid=avoid,
                allow_color_fallback=(not args.cards_no_color_fallback and not args.no_generic_pad),
                rebuild=args.rebuild_example_cards,
            )
            # Optional second pass limited color fallback for sparse themes
            if (not changed_cards or len(data.get('example_cards', []) or []) < args.cards_target) and args.cards_limited_color_fallback_threshold > 0 and args.cards_no_color_fallback:
                current_len = len(data.get('example_cards') or [])
                if current_len < args.cards_limited_color_fallback_threshold:
                    # Top up with color fallback only for remaining slots
                    changed2, added2 = fill_example_cards(
                        data,
                        theme_card_hits,
                        card_color_pool,
                        args.cards_target,
                        avoid=avoid,
                        allow_color_fallback=True,
                        rebuild=False,
                    )
                    if changed2:
                        changed_cards = True
                        added_cards.extend(added2)
            if changed_cards:
                cards_changed += 1
                print(f"[cards] {path.name}: {pre_cards_len} -> {len(data['example_cards'])} (added {len(added_cards)})")
                if args.apply:
                    save_yaml(path, data)
    print(f"[promote] modified {changed_count} themes")
    if args.fill_example_cards:
        print(f"[cards] modified {cards_changed} themes (target {args.cards_target})")
        if args.print_dup_metrics and 'GLOBAL_CARD_FREQ' in globals():  # type: ignore
            freq_map, total_prev = globals()['GLOBAL_CARD_FREQ']  # type: ignore
            if total_prev:
                items = sorted(freq_map.items(), key=lambda x: (-x[1], x[0]))[:30]
                print('[dup-metrics] Top shared example_cards (baseline before this run):')
                for name, cnt in items:
                    print(f"  {name}: {cnt}/{total_prev} ({cnt/max(total_prev,1):.1%})")
    raise SystemExit(0)


if __name__ == '__main__':  # pragma: no cover
    main()
