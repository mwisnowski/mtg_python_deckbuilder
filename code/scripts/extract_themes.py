import os
import json
import re
import sys
from collections import Counter
from typing import Dict, List, Set, Any

import pandas as pd
import itertools
import math
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency; script warns if missing
    yaml = None

# Ensure local 'code' package shadows stdlib 'code' module
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from code.settings import CSV_DIRECTORY  # type: ignore
from code.tagging import tag_constants  # type: ignore

BASE_COLORS = {
    'white': 'W',
    'blue': 'U',
    'black': 'B',
    'red': 'R',
    'green': 'G',
}

COLOR_LETTERS = set(BASE_COLORS.values())


def collect_theme_tags_from_constants() -> Set[str]:
    tags: Set[str] = set()
    # TYPE_TAG_MAPPING values
    for tags_list in tag_constants.TYPE_TAG_MAPPING.values():
        tags.update(tags_list)
    # DRAW_RELATED_TAGS
    tags.update(tag_constants.DRAW_RELATED_TAGS)
    # Some known groupings categories as tags
    for tgroup in tag_constants.TAG_GROUPS.values():
        tags.update(tgroup)
    # Known specific tags referenced in constants
    for name in dir(tag_constants):
        if name.endswith('_RELATED_TAGS') or name.endswith('_SPECIFIC_CARDS'):
            val = getattr(tag_constants, name)
            if isinstance(val, list):
                # Only include tag-like strings (skip obvious card names)
                for v in val:
                    if isinstance(v, str) and re.search(r"[A-Za-z]", v) and ' ' in v:
                        # Heuristic inclusion
                        pass
    return tags


def collect_theme_tags_from_tagger_source() -> Set[str]:
    tags: Set[str] = set()
    tagger_path = os.path.join(os.path.dirname(__file__), '..', 'tagging', 'tagger.py')
    tagger_path = os.path.abspath(tagger_path)
    with open(tagger_path, 'r', encoding='utf-8') as f:
        src = f.read()
    # Find tag_utils.apply_tag_vectorized(df, mask, ['Tag1', 'Tag2', ...]) occurrences
    vector_calls = re.findall(r"apply_tag_vectorized\([^\)]*\[([^\]]+)\]", src)
    for group in vector_calls:
        # Split strings within the list literal
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", group)
        for a, b in parts:
            s = a or b
            if s:
                tags.add(s)
    # Also capture tags passed via apply_rules([... {'tags': [ ... ]} ...])
    for group in re.findall(r"'tags'\s*:\s*\[([^\]]+)\]", src):
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", group)
        for a, b in parts:
            s = a or b
            if s:
                tags.add(s)
    # Also capture tags passed via apply_rules([... {'tags': [ ... ]} ...])
    for group in re.findall(r"['\"]tags['\"]\s*:\s*\[([^\]]+)\]", src):
        parts = re.findall(r"'([^']+)'|\"([^\"]+)\"", group)
        for a, b in parts:
            s = a or b
            if s:
                tags.add(s)
    return tags


def tally_tag_frequencies_by_base_color() -> Dict[str, Dict[str, int]]:
    result: Dict[str, Dict[str, int]] = {c: Counter() for c in BASE_COLORS.keys()}
    # Iterate over per-color CSVs; if not present, skip
    for color in BASE_COLORS.keys():
        path = os.path.join(CSV_DIRECTORY, f"{color}_cards.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, converters={'themeTags': pd.eval, 'colorIdentity': pd.eval})
        except Exception:
            df = pd.read_csv(path)
            if 'themeTags' in df.columns:
                try:
                    df['themeTags'] = df['themeTags'].apply(pd.eval)
                except Exception:
                    df['themeTags'] = df['themeTags'].apply(lambda x: [])
            if 'colorIdentity' in df.columns:
                try:
                    df['colorIdentity'] = df['colorIdentity'].apply(pd.eval)
                except Exception:
                    pass
        if 'themeTags' not in df.columns:
            continue
        # Derive base colors from colorIdentity if available, else assume single color file
        def rows_base_colors(row):
            ids = row.get('colorIdentity') if isinstance(row, dict) else row
            if isinstance(ids, list):
                letters = set(ids)
            else:
                letters = set()
            derived = set()
            for name, letter in BASE_COLORS.items():
                if letter in letters:
                    derived.add(name)
            if not derived:
                derived.add(color)
            return derived
        # Iterate rows
        for _, row in df.iterrows():
            tags = list(row['themeTags']) if hasattr(row.get('themeTags'), '__len__') and not isinstance(row.get('themeTags'), str) else []
            # Compute base colors contribution
            ci = row['colorIdentity'] if 'colorIdentity' in row else None
            letters = set(ci) if isinstance(ci, list) else set()
            bases = {name for name, letter in BASE_COLORS.items() if letter in letters}
            if not bases:
                bases = {color}
            for bc in bases:
                for t in tags:
                    result[bc][t] += 1
    # Convert Counters to plain dicts
    return {k: dict(v) for k, v in result.items()}


def gather_theme_tag_rows() -> List[List[str]]:
    """Collect per-card themeTags lists across all base color CSVs.

    Returns a list of themeTags arrays, one per card row where themeTags is present.
    """
    rows: List[List[str]] = []
    for color in BASE_COLORS.keys():
        path = os.path.join(CSV_DIRECTORY, f"{color}_cards.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, converters={'themeTags': pd.eval})
        except Exception:
            df = pd.read_csv(path)
            if 'themeTags' in df.columns:
                try:
                    df['themeTags'] = df['themeTags'].apply(pd.eval)
                except Exception:
                    df['themeTags'] = df['themeTags'].apply(lambda x: [])
        if 'themeTags' not in df.columns:
            continue
        for _, row in df.iterrows():
            tags = list(row['themeTags']) if hasattr(row.get('themeTags'), '__len__') and not isinstance(row.get('themeTags'), str) else []
            if tags:
                rows.append(tags)
    return rows


def compute_cooccurrence(rows: List[List[str]]):
    """Compute co-occurrence counts between tags.

    Returns:
      - co: dict[tag] -> Counter(other_tag -> co_count)
      - counts: Counter[tag] overall occurrence counts
      - total_rows: int number of rows (cards considered)
    """
    co: Dict[str, Counter] = {}
    counts: Counter = Counter()
    for tags in rows:
        uniq = sorted(set(t for t in tags if isinstance(t, str) and t))
        for t in uniq:
            counts[t] += 1
        for a, b in itertools.combinations(uniq, 2):
            co.setdefault(a, Counter())[b] += 1
            co.setdefault(b, Counter())[a] += 1
    return co, counts, len(rows)


def cooccurrence_scores_for(anchor: str, co: Dict[str, Counter], counts: Counter, total_rows: int) -> List[tuple[str, float, int]]:
    """Return list of (other_tag, score, co_count) sorted by score desc.

    Score uses PMI: log2( (co_count * total_rows) / (count_a * count_b) ).
    """
    results: List[tuple[str, float, int]] = []
    if anchor not in co:
        return results
    count_a = max(1, counts.get(anchor, 1))
    for other, co_count in co[anchor].items():
        count_b = max(1, counts.get(other, 1))
        # Avoid div by zero; require minimal counts
        if co_count <= 0:
            continue
        # PMI
        pmi = math.log2((co_count * max(1, total_rows)) / (count_a * count_b))
        results.append((other, pmi, co_count))
    results.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return results


def derive_synergies_for_tags(tags: Set[str]) -> Dict[str, List[str]]:
    # Curated baseline mappings for important themes (extended)
    pairs = [
        # Tokens / go-wide
        ("Tokens Matter", ["Token Creation", "Creature Tokens", "Populate"]),
        ("Creature Tokens", ["Tokens Matter", "Token Creation", "Populate"]),
        ("Token Creation", ["Tokens Matter", "Creature Tokens", "Populate"]),
        # Spells
        ("Spellslinger", ["Spells Matter", "Prowess", "Noncreature Spells"]),
        ("Noncreature Spells", ["Spellslinger", "Prowess"]),
        ("Prowess", ["Spellslinger", "Noncreature Spells"]),
        # Artifacts / Enchantments
        ("Artifacts Matter", ["Treasure Token", "Equipment Matters", "Vehicles", "Improvise"]),
        ("Enchantments Matter", ["Auras", "Constellation", "Card Draw"]),
        ("Auras", ["Constellation", "Voltron", "Enchantments Matter"]),
        ("Treasure Token", ["Sacrifice Matters", "Artifacts Matter", "Ramp"]),
        ("Vehicles", ["Artifacts Matter", "Crew", "Vehicles"]),
        # Counters / Proliferate
        ("Counters Matter", ["Proliferate", "+1/+1 Counters", "Adapt", "Outlast"]),
        ("+1/+1 Counters", ["Proliferate", "Counters Matter", "Adapt", "Evolve"]),
        ("-1/-1 Counters", ["Proliferate", "Counters Matter", "Wither", "Persist", "Infect"]),
        ("Proliferate", ["Counters Matter", "+1/+1 Counters", "Planeswalkers"]),
        # Lands / ramp
        ("Lands Matter", ["Landfall", "Domain", "Land Tutors"]),
        ("Landfall", ["Lands Matter", "Ramp", "Token Creation"]),
        ("Domain", ["Lands Matter", "Ramp"]),
        # Combat / Voltron
        ("Voltron", ["Equipment Matters", "Auras", "Double Strike"]),
        # Card flow
        ("Card Draw", ["Loot", "Wheels", "Replacement Draw", "Unconditional Draw", "Conditional Draw"]),
        ("Loot", ["Card Draw", "Discard Matters", "Reanimate"]),
        ("Wheels", ["Discard Matters", "Card Draw", "Spellslinger"]),
        ("Discard Matters", ["Loot", "Wheels", "Hellbent", "Reanimate"]),
        # Sacrifice / death
        ("Aristocrats", ["Sacrifice", "Death Triggers", "Token Creation"]),
        ("Sacrifice", ["Aristocrats", "Death Triggers", "Treasure Token"]),
        ("Death Triggers", ["Aristocrats", "Sacrifice"]),
        # Graveyard cluster
        ("Graveyard Matters", ["Reanimate", "Mill", "Unearth", "Surveil"]),
        ("Reanimate", ["Mill", "Graveyard Matters", "Enter the Battlefield"]),
        ("Unearth", ["Reanimate", "Graveyard Matters"]),
        ("Surveil", ["Mill", "Reanimate", "Graveyard Matters"]),
        # Planeswalkers / blink
        ("Superfriends", ["Planeswalkers", "Proliferate", "Token Creation"]),
        ("Planeswalkers", ["Proliferate", "Superfriends"]),
        ("Enter the Battlefield", ["Blink", "Reanimate", "Token Creation"]),
        ("Blink", ["Enter the Battlefield", "Flicker", "Token Creation"]),
        # Politics / table dynamics
        ("Stax", ["Taxing Effects", "Hatebears"]),
        ("Monarch", ["Politics", "Group Hug", "Card Draw"]),
        ("Group Hug", ["Politics", "Card Draw"]),
        # Life
        ("Life Matters", ["Lifegain", "Lifedrain", "Extort"]),
        ("Lifegain", ["Life Matters", "Lifedrain", "Extort"]),
        ("Lifedrain", ["Lifegain", "Life Matters"]),
        # Treasure / economy cross-link
        ("Ramp", ["Treasure Token", "Land Tutors"]),
    ]
    m: Dict[str, List[str]] = {}
    for base, syn in pairs:
        if base in tags:
            m[base] = syn
    return m


def load_whitelist_config() -> Dict[str, Any]:
    """Load whitelist governance YAML if present.

    Returns empty dict if file missing or YAML unavailable.
    """
    path = os.path.join('config', 'themes', 'theme_whitelist.yml')
    if not os.path.exists(path) or yaml is None:
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return {}
            return data
    except Exception:
        return {}


def apply_normalization(tags: Set[str], normalization: Dict[str, str]) -> Set[str]:
    if not normalization:
        return tags
    normalized = set()
    for t in tags:
        normalized.add(normalization.get(t, t))
    return normalized


def should_keep_theme(theme: str, total_count: int, cfg: Dict[str, Any], protected_prefixes: List[str], protected_suffixes: List[str], min_overrides: Dict[str, int]) -> bool:
    # Always include explicit always_include list
    if theme in cfg.get('always_include', []):
        return True
    # Protected prefixes/suffixes
    for pref in protected_prefixes:
        if theme.startswith(pref + ' '):  # prefix followed by space
            return True
    for suff in protected_suffixes:
        if theme.endswith(' ' + suff) or theme.endswith(suff):
            return True
    # Min frequency override
    if theme in min_overrides:
        return total_count >= min_overrides[theme]
    # Default global rule (>1 occurrences)
    return total_count > 1


def main() -> None:
    whitelist_cfg = load_whitelist_config()
    normalization_map: Dict[str, str] = whitelist_cfg.get('normalization', {}) if isinstance(whitelist_cfg.get('normalization', {}), dict) else {}
    exclusions: Set[str] = set(whitelist_cfg.get('exclusions', []) or [])
    protected_prefixes: List[str] = list(whitelist_cfg.get('protected_prefixes', []) or [])
    protected_suffixes: List[str] = list(whitelist_cfg.get('protected_suffixes', []) or [])
    min_overrides: Dict[str, int] = whitelist_cfg.get('min_frequency_overrides', {}) or {}
    synergy_cap: int = int(whitelist_cfg.get('synergy_cap', 0) or 0)
    enforced_synergies_cfg: Dict[str, List[str]] = whitelist_cfg.get('enforced_synergies', {}) or {}

    theme_tags = set()
    theme_tags |= collect_theme_tags_from_constants()
    theme_tags |= collect_theme_tags_from_tagger_source()

    # Also include any tags that already exist in the per-color CSVs. This captures
    # dynamically constructed tags like "{CreatureType} Kindred" that don't appear
    # as string literals in source code but are present in data.
    try:
        csv_rows = gather_theme_tag_rows()
        if csv_rows:
            for row_tags in csv_rows:
                for t in row_tags:
                    if isinstance(t, str) and t:
                        theme_tags.add(t)
    except Exception:
        # If CSVs are unavailable, continue with tags from code only
        csv_rows = []

    # Normalization before other operations (so pruning & synergies use canonical names)
    if normalization_map:
        theme_tags = apply_normalization(theme_tags, normalization_map)

    # Remove excluded / blacklisted helper tags we might not want to expose as themes
    blacklist = {"Draw Triggers"}
    theme_tags = {t for t in theme_tags if t and t not in blacklist and t not in exclusions}

    # If we have frequency data, filter out extremely rare themes
    # Rule: Drop any theme whose total count across all base colors is <= 1
    # This removes one-off/accidental tags from the theme catalog.
    # We apply the filter only when frequencies were computed successfully.
    try:
        _freq_probe = tally_tag_frequencies_by_base_color()
        has_freqs = bool(_freq_probe)
    except Exception:
        has_freqs = False

    if has_freqs:
        def total_count(t: str) -> int:
            total = 0
            for color in BASE_COLORS.keys():
                try:
                    total += int(_freq_probe.get(color, {}).get(t, 0))
                except Exception:
                    pass
            return total
        kept: Set[str] = set()
        for t in list(theme_tags):
            if should_keep_theme(t, total_count(t), whitelist_cfg, protected_prefixes, protected_suffixes, min_overrides):
                kept.add(t)
        # Merge always_include even if absent
        for extra in whitelist_cfg.get('always_include', []) or []:
            kept.add(extra if isinstance(extra, str) else str(extra))
        theme_tags = kept

    # Sort tags for stable output
    sorted_tags = sorted(theme_tags)

    # Derive synergies mapping
    synergies = derive_synergies_for_tags(theme_tags)

    # Tally frequencies by base color if CSVs exist
    try:
        frequencies = tally_tag_frequencies_by_base_color()
    except Exception:
        frequencies = {}

    # Co-occurrence synergies (data-driven) if CSVs exist
    try:
        # Reuse rows from earlier if available; otherwise gather now
        rows = csv_rows if 'csv_rows' in locals() and csv_rows else gather_theme_tag_rows()
        co_map, tag_counts, total_rows = compute_cooccurrence(rows)
    except Exception:
        rows = []
        co_map, tag_counts, total_rows = {}, Counter(), 0

    # Helper: compute primary/secondary colors for a theme
    def primary_secondary_for(theme: str, freqs: Dict[str, Dict[str, int]]):
        if not freqs:
            return None, None
        # Collect counts per base color for this theme
        items = []
        for color in BASE_COLORS.keys():
            count = 0
            try:
                count = int(freqs.get(color, {}).get(theme, 0))
            except Exception:
                count = 0
            items.append((color, count))
        # Sort by count desc, then by color name for stability
        items.sort(key=lambda x: (-x[1], x[0]))
        # If all zeros, return None
        if not items or items[0][1] <= 0:
            return None, None
        color_title = {
            'white': 'White', 'blue': 'Blue', 'black': 'Black', 'red': 'Red', 'green': 'Green'
        }
        primary = color_title[items[0][0]]
        secondary = None
        # Find the next non-zero distinct color if available
        for c, n in items[1:]:
            if n > 0:
                secondary = color_title[c]
                break
        return primary, secondary

    output = []
    def _uniq(seq: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in seq:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out
    for t in sorted_tags:
        p, s = primary_secondary_for(t, frequencies)
        # Build synergy list: curated + top co-occurrences
        curated = synergies.get(t, [])
        inferred: List[str] = []
        if t in co_map and total_rows > 0:
            # Denylist for clearly noisy combos
            denylist = {
                ('-1/-1 Counters', 'Burn'),
                ('-1/-1 Counters', 'Voltron'),
            }
            # Whitelist focus for specific anchors
            focus: Dict[str, List[str]] = {
                '-1/-1 Counters': ['Counters Matter', 'Infect', 'Proliferate', 'Wither', 'Persist'],
            }
            # Compute PMI scores and filter
            scored = cooccurrence_scores_for(t, co_map, tag_counts, total_rows)
            # Keep only positive PMI and co-occurrence >= 5 (tunable)
            filtered = [(o, s, c) for (o, s, c) in scored if s > 0 and c >= 5]
            # If focused tags exist, ensure they bubble up first when present
            preferred = focus.get(t, [])
            if preferred:
                # Partition into preferred and others
                pref = [x for x in filtered if x[0] in preferred]
                others = [x for x in filtered if x[0] not in preferred]
                filtered = pref + others
            # Select up to 6, skipping denylist and duplicates
            for other, _score, _c in filtered:
                if (t, other) in denylist or (other, t) in denylist:
                    continue
                if other == t or other in curated or other in inferred:
                    continue
                inferred.append(other)
                if len(inferred) >= 6:
                    break
        combined = list(curated)
        # Enforced synergies from config (high precedence after curated)
        enforced = enforced_synergies_cfg.get(t, [])
        for es in enforced:
            if es != t and es not in combined:
                combined.append(es)
        # Legacy automatic enforcement (backwards compatibility) if not already covered by enforced config
        if not enforced:
            if re.search(r'counter', t, flags=re.IGNORECASE) or t == 'Proliferate':
                for needed in ['Counters Matter', 'Proliferate']:
                    if needed != t and needed not in combined:
                        combined.append(needed)
            if re.search(r'token', t, flags=re.IGNORECASE) and t != 'Tokens Matter':
                if 'Tokens Matter' not in combined:
                    combined.append('Tokens Matter')
        # Append inferred last (lowest precedence)
        for inf in inferred:
            if inf != t and inf not in combined:
                combined.append(inf)
        # Deduplicate
        combined = _uniq(combined)
        # Apply synergy cap if configured (>0)
        if synergy_cap > 0 and len(combined) > synergy_cap:
            combined = combined[:synergy_cap]
        entry = {
            "theme": t,
            "synergies": combined,
        }
        if p:
            entry["primary_color"] = p
        if s:
            entry["secondary_color"] = s
        output.append(entry)

    os.makedirs(os.path.join('config', 'themes'), exist_ok=True)
    with open(os.path.join('config', 'themes', 'theme_list.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "themes": output,
            "frequencies_by_base_color": frequencies,
            "generated_from": "tagger + constants",
        }, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

