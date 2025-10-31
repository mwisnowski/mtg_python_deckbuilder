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
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import re

try:  # Optional
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

try:
    # Support running as `python code/scripts/build_theme_catalog.py` when 'code' already on path
    from scripts.extract_themes import (
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
except ModuleNotFoundError:
    # Fallback: direct relative import when running within scripts package context
    from extract_themes import (
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

try:
    from scripts.export_themes_to_yaml import slugify as slugify_theme
except Exception:
    _SLUG_RE = re.compile(r'[^a-z0-9-]')

    def slugify_theme(name: str) -> str:
        s = name.strip().lower()
        s = s.replace('+', 'plus')
        s = s.replace('/', '-')
        s = re.sub(r'[\s_]+', '-', s)
        s = _SLUG_RE.sub('', s)
        s = re.sub(r'-{2,}', '-', s)
        return s.strip('-')

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT / 'code'
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

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
    # Phase D+ editorial metadata (may be absent in older files)
    example_commanders: List[str] = field(default_factory=list)
    example_cards: List[str] = field(default_factory=list)
    synergy_commanders: List[str] = field(default_factory=list)
    deck_archetype: Optional[str] = None
    popularity_hint: Optional[str] = None
    popularity_bucket: Optional[str] = None
    description: Optional[str] = None
    editorial_quality: Optional[str] = None  # draft|reviewed|final (optional quality flag)
    # Internal bookkeeping: source file path for backfill writes
    _path: Optional[Path] = None


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
                example_commanders=list(data.get('example_commanders') or []),
                example_cards=list(data.get('example_cards') or []),
                synergy_commanders=list(data.get('synergy_commanders') or []),
                deck_archetype=data.get('deck_archetype'),
                popularity_hint=data.get('popularity_hint'),
                popularity_bucket=data.get('popularity_bucket'),
                description=data.get('description'),
                editorial_quality=data.get('editorial_quality'),
                _path=path,
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


def _auto_description(theme: str, synergies: List[str]) -> str:
    """Generate a concise description for a theme using heuristics.

    Rules:
      - Kindred / tribal: "Focuses on getting a high number of <Type> creatures into play with shared payoffs (e.g., X, Y)."
      - Proliferate: emphasize adding and multiplying counters.
      - +1/+1 Counters / Counters Matter: growth & scaling payoffs.
      - Graveyard / Reanimate: recursion loops & value from graveyard.
      - Tokens / Treasure: generating and exploiting resource tokens.
      - Default: "Builds around <theme> leveraging synergies with <top 2 synergies>."
    """
    base = theme.strip()
    lower = base.lower()
    syn_preview = [s for s in synergies if s and s != theme][:4]
    def list_fmt(items: List[str], cap: int = 3) -> str:
        if not items:
            return ''
        items = items[:cap]
        if len(items) == 1:
            return items[0]
        return ', '.join(items[:-1]) + f" and {items[-1]}"

    # Identify top synergy preview (skip self)
    syn_preview = [s for s in synergies if s and s.lower() != lower][:4]
    syn_fmt2 = list_fmt(syn_preview, 2)

    # --- Mapping refactor (Phase D+ extension) ---
    # Ordered list of mapping rules. Each rule: (list_of_substring_triggers, description_template_fn)
    # The first matching rule wins. Substring matches are on `lower`.
    def synergic(phrase: str) -> str:
        if syn_fmt2:
            return phrase + (f" Synergies like {syn_fmt2} reinforce the plan." if not phrase.endswith('.') else f" Synergies like {syn_fmt2} reinforce the plan.")
        return phrase

    # Attempt to load external mapping file (YAML) for curator overrides.
    external_mapping: List[Tuple[List[str], Any]] = []
    mapping_path = ROOT / 'config' / 'themes' / 'description_mapping.yml'
    if yaml is not None and mapping_path.exists():  # pragma: no cover (I/O heavy)
        try:
            raw_map = yaml.safe_load(mapping_path.read_text(encoding='utf-8')) or []
            if isinstance(raw_map, list):
                for item in raw_map:
                    if not isinstance(item, dict):
                        continue
                    triggers = item.get('triggers') or []
                    desc_template = item.get('description') or ''
                    if not (isinstance(triggers, list) and isinstance(desc_template, str) and triggers):
                        continue
                    triggers_norm = [str(t).lower() for t in triggers if isinstance(t, str) and t]
                    if not triggers_norm:
                        continue
                    def _factory(template: str):
                        def _fn():
                            if '{SYNERGIES}' in template:
                                rep = f" Synergies like {syn_fmt2} reinforce the plan." if syn_fmt2 else ''
                                return template.replace('{SYNERGIES}', rep)
                            # If template omitted placeholder but we have synergies, append politely.
                            if syn_fmt2:
                                return template.rstrip('.') + f". Synergies like {syn_fmt2} reinforce the plan."
                            return template
                        return _fn
                    external_mapping.append((triggers_norm, _factory(desc_template)))
        except Exception:
            external_mapping = []

    MAPPING_RULES: List[Tuple[List[str], Any]] = external_mapping if external_mapping else [
        (['aristocrats', 'aristocrat'], lambda: synergic('Sacrifices expendable creatures and tokens to trigger death payoffs, recursion, and incremental drain.')),
        (['sacrifice'], lambda: synergic('Leverages sacrifice outlets and death triggers to grind incremental value and drain opponents.')),
        (['spellslinger', 'spells matter', 'magecraft', 'prowess'], lambda: 'Chains cheap instants & sorceries for velocity—converting triggers into scalable damage or card advantage before a finisher.'),
        (['voltron'], lambda: 'Stacks auras, equipment, and protection on a single threat to push commander damage with layered resilience.'),
        (['group hug'], lambda: 'Accelerates the whole table (cards / mana / tokens) to shape politics, then pivots that shared growth into asymmetric advantage.'),
        (['pillowfort'], lambda: 'Deploys deterrents and taxation effects to deflect aggression while assembling a protected win route.'),
        (['stax'], lambda: 'Applies asymmetric resource denial (tax, tap, sacrifice, lock pieces) to throttle opponents while advancing a resilient engine.'),
        (['aggro','burn'], lambda: 'Applies early pressure and combat tempo to close the game before slower value engines stabilize.'),
        (['control'], lambda: 'Trades efficiently, accrues card advantage, and wins via inevitability once the board is stabilized.'),
        (['midrange'], lambda: 'Uses flexible value threats & interaction, pivoting between pressure and attrition based on table texture.'),
        (['ramp','big mana'], lambda: 'Accelerates mana ahead of curve, then converts surplus into oversized threats or multi-spell bursts.'),
        (['combo'], lambda: 'Assembles compact piece interactions to generate infinite or overwhelming advantage, protected by tutors & stack interaction.'),
        (['storm'], lambda: 'Builds storm count with cheap spells & mana bursts, converting it into a lethal payoff turn.'),
        (['wheel','wheels'], lambda: 'Loops mass draw/discard effects to refill, disrupt sculpted hands, and weaponize symmetrical replacement triggers.'),
        (['mill'], lambda: 'Attacks libraries as a resource—looping self-mill or opponent mill into recursion and payoff engines.'),
        (['reanimate','graveyard','dredge'], lambda: 'Loads high-impact cards into the graveyard early and reanimates them for explosive tempo or combo loops.'),
        (['blink','flicker'], lambda: 'Recycles enter-the-battlefield triggers through blink/flicker loops for compounding value and soft locks.'),
        (['landfall','lands matter','lands-matter'], lambda: 'Abuses extra land drops and recursion to chain Landfall triggers and scale permanent-based payoffs.'),
        (['artifact tokens'], lambda: 'Generates artifact tokens as modular resources—fueling sacrifice, draw, and cost-reduction engines.'),
        (['artifact'], lambda: 'Leverages dense artifact counts for cost reduction, recursion, and modular scaling payoffs.'),
        (['equipment'], lambda: 'Tutors and reuses equipment to stack stats/keywords onto resilient bodies for persistent pressure.'),
        (['constellation'], lambda: 'Chains enchantment drops to trigger constellation loops in draw, drain, or scaling effects.'),
        (['enchant'], lambda: 'Stacks enchantment-based engines (cost reduction, constellation, aura recursion) for relentless value accrual.'),
        (['shrines'], lambda: 'Accumulates Shrines whose upkeep triggers scale multiplicatively into inevitability.'),
        (['token'], lambda: 'Goes wide with creature tokens then converts mass into damage, draw, drain, or sacrifice engines.'),
        (['treasure'], lambda: 'Produces Treasure tokens as flexible ramp & combo fuel enabling explosive payoff turns.'),
        (['clue','investigate'], lambda: 'Banks Clue tokens for delayed card draw while fueling artifact & token synergies.'),
        (['food'], lambda: 'Creates Food tokens for life padding and sacrifice loops that translate into drain, draw, or recursion.'),
        (['blood'], lambda: 'Uses Blood tokens to loot, set up graveyard recursion, and trigger discard/madness payoffs.'),
        (['map token','map tokens','map '], lambda: 'Generates Map tokens to surveil repeatedly, sculpting draws and fueling artifact/token synergies.'),
        (['incubate','incubator'], lambda: 'Banks Incubator tokens then transforms them into delayed board presence & artifact synergy triggers.'),
        (['powerstone'], lambda: 'Creates Powerstones for non-creature ramp powering large artifacts and activation-heavy engines.'),
        (['role token','role tokens','role '], lambda: 'Applies Role tokens as stackable mini-auras that generate incremental buffs or sacrifice fodder.'),
        (['energy'], lambda: 'Accumulates Energy counters as a parallel resource spent for tempo spikes, draw, or scalable removal.'),
        (['poison','infect','toxic'], lambda: 'Leverages Infect/Toxic pressure and proliferate to accelerate poison win thresholds.'),
        (['proliferate'], lambda: 'Multiplies diverse counters (e.g., +1/+1, loyalty, poison) to escalate board state and inevitability.'),
        (['+1/+1 counters','counters matter','counters-matter'], lambda: 'Stacks +1/+1 counters broadly then doubles, proliferates, or redistributes them for exponential scaling.'),
        (['-1/-1 counters'], lambda: 'Spreads -1/-1 counters for removal, attrition, and loop engines leveraging death & sacrifice triggers.'),
        (['experience'], lambda: 'Builds experience counters to scale commander-centric engines into exponential payoffs.'),
        (['loyalty','superfriends','planeswalker'], lambda: 'Protects and reuses planeswalkers—amplifying loyalty via proliferate and recursion for inevitability.'),
        (['shield counter'], lambda: 'Applies shield counters to insulate threats and create lopsided removal trades.'),
        (['sagas matter','sagas'], lambda: 'Loops and resets Sagas to repeatedly harvest chapter-based value sequences.'),
        (['lifegain','life gain','life-matters'], lambda: 'Turns repeat lifegain triggers into card draw, scaling bodies, or drain-based win pressure.'),
        (['lifeloss','life loss'], lambda: 'Channels symmetrical life loss into card flow, recursion, and inevitability drains.'),
        (['theft','steal'], lambda: 'Acquires opponents’ permanents temporarily or permanently to convert their resources into board control.'),
        (['devotion'], lambda: 'Concentrates colored pips to unlock Devotion payoffs and scalable static advantages.'),
        (['domain'], lambda: 'Assembles multiple basic land types rapidly to scale Domain-based effects.'),
        (['metalcraft'], lambda: 'Maintains ≥3 artifacts to turn on Metalcraft efficiencies and scaling bonuses.'),
        (['affinity'], lambda: 'Reduces spell costs via board resource counts (Affinity) enabling explosive early multi-spell turns.'),
        (['improvise'], lambda: 'Taps artifacts as pseudo-mana (Improvise) to deploy oversized non-artifact spells ahead of curve.'),
        (['convoke'], lambda: 'Converts creature presence into mana (Convoke) accelerating large or off-color spells.'),
        (['cascade'], lambda: 'Chains cascade triggers to convert single casts into multi-spell value bursts.'),
        (['mutate'], lambda: 'Stacks mutate layers to reuse mutate triggers and build a resilient evolving threat.'),
        (['evolve'], lambda: 'Sequentially upgrades creatures with Evolve counters, then leverages accumulated stats or counter synergies.'),
        (['delirium'], lambda: 'Diversifies graveyard card types to unlock Delirium power thresholds.'),
        (['threshold'], lambda: 'Fills the graveyard quickly to meet Threshold counts and upgrade spell/creature efficiencies.'),
        (['vehicles','crew '], lambda: 'Leverages efficient Vehicles and crew bodies to field evasive, sweep-resilient threats.'),
        (['goad'], lambda: 'Redirects combat outward by goading opponents’ creatures, destabilizing defenses while you build advantage.'),
        (['monarch'], lambda: 'Claims and defends the Monarch for sustained card draw with evasion & deterrents.'),
        (['surveil'], lambda: 'Continuously filters with Surveil to sculpt draws, fuel recursion, and enable graveyard synergies.'),
        (['explore'], lambda: 'Uses Explore triggers to smooth draws, grow creatures, and feed graveyard-adjacent engines.'),
        (['exploit'], lambda: 'Sacrifices creatures on ETB (Exploit) converting fodder into removal, draw, or recursion leverage.'),
        (['venture'], lambda: 'Repeats Venture into the Dungeon steps to layer incremental room rewards into compounding advantage.'),
        (['dungeon'], lambda: 'Progresses through dungeons repeatedly to chain room value and synergize with venture payoffs.'),
        (['initiative'], lambda: 'Claims the Initiative, advancing the Undercity while defending control of the progression track.'),
        (['backgrounds matter','background'], lambda: 'Pairs a Commander with Backgrounds for modular static buffs & class-style customization.'),
        (['connive'], lambda: 'Uses Connive looting + counters to sculpt hands, grow threats, and feed recursion lines.'),
        (['discover'], lambda: 'Leverages Discover to cheat spell mana values, chaining free cascade-like board development.'),
        (['craft'], lambda: 'Transforms / upgrades permanents via Craft, banking latent value until a timing pivot.'),
        (['learn'], lambda: 'Uses Learn to toolbox from side selections (or discard/draw) enhancing adaptability & consistency.'),
        (['escape'], lambda: 'Escapes threats from the graveyard by exiling spent resources, generating recursive inevitability.'),
        (['flashback'], lambda: 'Replays instants & sorceries from the graveyard (Flashback) for incremental spell velocity.'),
        (['aftermath'], lambda: 'Extracts two-phase value from split Aftermath spells, maximizing flexible sequencing.'),
        (['adventure'], lambda: 'Casts Adventure spell sides first to stack value before committing creature bodies to board.'),
        (['foretell'], lambda: 'Foretells spells early to smooth curve, conceal information, and discount impactful future turns.'),
        (['miracle'], lambda: 'Manipulates topdecks / draw timing to exploit Miracle cost reductions on splashy spells.'),
        (['kicker','multikicker'], lambda: 'Kicker / Multikicker spells scale flexibly—paying extra mana for amplified late-game impact.'),
        (['buyback'], lambda: 'Loops Buyback spells to convert excess mana into repeatable effects & inevitability.'),
        (['suspend'], lambda: 'Suspends spells early to pay off delayed powerful effects at discounted timing.'),
        (['retrace'], lambda: 'Turns dead land draws into fuel by recasting Retrace spells for attrition resilience.'),
        (['rebound'], lambda: 'Uses Rebound to double-cast value spells, banking a delayed second resolution.'),
        (['escalate'], lambda: 'Selects multiple modes on Escalate spells, trading mana/cards for flexible stacked effects.'),
        (['overload'], lambda: 'Overloads modal spells into one-sided board impacts or mass disruption swings.'),
        (['prowl'], lambda: 'Enables Prowl cost reductions via tribe-based combat connections, accelerating tempo sequencing.'),
        (['delve'], lambda: 'Exiles graveyard cards to pay for Delve spells, converting stocked yard into mana efficiency.'),
        (['madness'], lambda: 'Turns discard into mana-efficient Madness casts, leveraging looting & Blood token filtering.'),
        (['escape'], lambda: 'Recurs Escape cards by exiling spent graveyard fodder for inevitability. (dedupe)')
    ]

    for keys, fn in MAPPING_RULES:
        for k in keys:
            if k in lower:
                try:
                    return fn()
                except Exception:
                    pass

    # Additional generic counters subtype fallback (not already matched)
    if lower.endswith(' counters') and all(x not in lower for x in ['+1/+1', '-1/-1', 'poison']):
        root = base.replace('Counters','').strip()
        return f"Accumulates {root.lower()} counters to unlock scaling payoffs, removal triggers, or delayed value conversions.".replace('  ',' ')

    # (Legacy chain retained for any themes not yet incorporated in mapping; will be pruned later.)
    if lower == 'aristocrats' or 'aristocrat' in lower or 'sacrifice' in lower:
        core = 'Sacrifices expendable creatures and tokens to trigger death payoffs, recursive engines, and incremental drain.'
        if syn_fmt2:
            return core + f" Synergies like {syn_fmt2} reinforce inevitability."
        return core
    if 'spellslinger' in lower or 'spells matter' in lower or (lower == 'spells') or 'prowess' in lower or 'magecraft' in lower:
        return ("Chains cheap instants & sorceries for velocity—turning card draw, mana bursts, and prowess/Magecraft triggers into"
                " scalable damage or resource advantage before a decisive finisher.")
    if 'voltron' in lower:
        return ("Stacks auras, equipment, and protective buffs onto a single threat—pushing commander damage with evasion, recursion,"
                " and layered protection.")
    if lower == 'group hug' or 'group hug' in lower:
        return ("Accelerates the whole table with cards, mana, or tokens to shape politics—then pivots shared growth into subtle win paths"
                " or leverage effects that scale better for you.")
    if 'pillowfort' in lower:
        return ("Erects deterrents and taxation effects to discourage attacks while assembling incremental advantage and a protected win condition.")
    if 'stax' in lower:
        return ("Applies asymmetric resource denial (tax, tap, sacrifice, lock pieces) to constrict opponents while advancing a resilient engine.")
    if lower in {'aggro', 'burn'} or 'aggro' in lower:
        return ("Applies fast early pressure and combat-focused tempo to reduce life totals before slower decks stabilize.")
    if lower == 'control' or 'control' in lower:
        return ("Trades efficiently with threats, accumulates card advantage, and stabilizes into inevitability via superior late-game engines.")
    if 'midrange' in lower:
        return ("Deploys flexible, value-centric threats and interaction—pivoting between aggression and attrition based on table texture.")
    if 'ramp' in lower or 'big mana' in lower:
        return ("Accelerates mana production ahead of curve, then converts the surplus into oversized threats or multi-spell turns.")
    if 'combo' in lower:
        return ("Assembles a small set of interlocking pieces that produce infinite or overwhelming advantage, protecting the line with tutors & stack interaction.")
    if 'storm' in lower:
        return ("Builds a critical mass of cheap spells and mana bursts to inflate storm count, converting it into a lethal finisher or overwhelming value turn.")
    if 'wheels' in lower or 'wheel' in lower:
        return ("Loops mass draw/discard effects (wheel spells) to refill, disrupt sculpted hands, and amplify payoffs like locust or damage triggers.")
    if 'mill' in lower:
        return ("Targets libraries as the primary resource—using repeatable self or opponent milling plus recursion / payoff loops.")
    if 'reanimate' in lower or (('reanimat' in lower or 'graveyard' in lower) and 'aristocrat' not in lower):
        return ("Dumps high-impact creatures into the graveyard early, then reanimates them efficiently for explosive board presence or combo loops.")
    if 'blink' in lower or 'flicker' in lower:
        return ("Repeatedly exiles and returns creatures to reuse powerful enter-the-battlefield triggers and incremental value engines.")
    if 'landfall' in lower or 'lands matter' in lower or 'lands-matter' in lower:
        return ("Accelerates extra land drops and recursion to trigger Landfall chains and scalable land-based payoffs.")
    if 'artifact' in lower and 'tokens' not in lower:
        return ("Leverages artifact density for cost reduction, recursion, and modular value engines—scaling with synergies that reward artifact count.")
    if 'equipment' in lower:
        return ("Equips repeatable stat and keyword boosts onto resilient bodies, tutoring and reusing gear to maintain pressure through removal.")
    if 'aura' in lower or 'enchant' in lower and 'enchantments matter' in lower:
        return ("Stacks enchantment or aura-based value engines (draw, cost reduction, constellation) into compounding board & card advantage.")
    if 'constellation' in lower:
        return ("Triggers constellation by repeatedly landing enchantments, converting steady plays into card draw, drain, or board scaling.")
    if 'shrine' in lower or 'shrines' in lower:
        return ("Accumulates Shrines whose upkeep triggers scale multiplicatively, protecting the board while compounding advantage.")
    if 'token' in lower and 'treasure' not in lower:
        return ("Goes wide generating expendable creature tokens, then converts board mass into damage, draw, or aristocrat-style drains.")
    if 'treasure' in lower:
        return ("Manufactures Treasure tokens as flexible ramp and combo fuel—translating temporary mana into explosive payoff turns.")
    if 'clue' in lower:
        return ("Generates Clue tokens as delayed draw—fueling card advantage engines and artifact/token synergies.")
    if 'food' in lower:
        return ("Creates Food tokens for life buffering and sacrifice value, converting them into draw, drain, or resource loops.")
    if 'blood' in lower:
        return ("Uses Blood tokens to filter draws, enable graveyard setups, and trigger discard/madness or artifact payoffs.")
    if 'map token' in lower or 'map' in lower and 'token' in lower:
        return ("Generates Map tokens to repeatedly surveil and sculpt draws while enabling artifact & token synergies.")
    if 'incubate' in lower or 'incubator' in lower:
        return ("Creates Incubator tokens then transforms them into creatures—banking future board presence and artifact synergies.")
    if 'powerstone' in lower:
        return ("Produces Powerstone tokens for non-creature ramp, channeling the mana into large artifacts or activated engines.")
    if 'role token' in lower or 'role' in lower and 'token' in lower:
        return ("Applies Role tokens as layered auras providing incremental buffs, sacrifice fodder, or value triggers.")
    if 'energy' in lower and 'counter' not in lower:
        return ("Accumulates Energy counters as a parallel resource—spending them for burst tempo, card flow, or scalable removal.")
    if 'poison' in lower or 'infect' in lower or 'toxic' in lower:
        return ("Applies poison counters through Infect/Toxic pressure and proliferate tools to accelerate an alternate win condition.")
    if 'proliferate' in lower:
        return ("Adds and multiplies counters (e.g., +1/+1, loyalty, poison) by repeatedly proliferating incremental board advantages.")
    if '+1/+1 counters' in lower or 'counters matter' in lower or 'counters-matter' in lower:
        return ("Stacks +1/+1 counters across the board, then amplifies them via doubling, proliferate, or modular scaling payoffs.")
    if 'dredge' in lower:
        return ("Replaces draws with self-mill to load the graveyard, then recurs or reanimates high-value pieces for compounding advantage.")
    if 'delirium' in lower:
        return ("Diversifies card types in the graveyard to unlock Delirium thresholds, turning on boosted stats or efficient effects.")
    if 'threshold' in lower:
        return ("Fills the graveyard rapidly to meet Threshold counts, upgrading spell efficiencies and creature stats.")
    if 'affinity' in lower:
        return ("Reduces spell costs via artifact / basic synergy counts, enabling explosive multi-spell turns and early board presence.")
    if 'improvise' in lower:
        return ("Taps artifacts as mana sources (Improvise) to cast oversized non-artifact spells ahead of curve.")
    if 'convoke' in lower:
        return ("Turns creatures into a mana engine (Convoke), deploying large spells while developing board presence.")
    if 'cascade' in lower:
        return ("Chains cascade triggers to convert high-cost spells into multiple free spells, snowballing value and board impact.")
    if 'mutate' in lower:
        return ("Stacks mutate piles to reuse mutate triggers while building a resilient, scaling singular threat.")
    if 'evolve' in lower:
        return ("Sequentially grows creatures with Evolve triggers, then leverages the accumulated stats or counter synergies.")
    if 'devotion' in lower:
        return ("Concentrates colored pips on permanents to unlock Devotion payoffs (static buffs, card draw, or burst mana).")
    if 'domain' in lower:
        return ("Assembles multiple basic land types quickly to scale Domain-based spells and effects.")
    if 'metalcraft' in lower:
        return ("Maintains a high artifact count (3+) to turn on efficient Metalcraft bonuses and scaling payoffs.")
    if 'vehicles' in lower or 'crew' in lower:
        return ("Uses under-costed Vehicles and efficient crew bodies—turning transient artifacts into evasive, hard-to-wipe threats.")
    if 'goad' in lower:
        return ("Forces opponents' creatures to attack each other (Goad), destabilizing defenses while you set up value engines.")
    if 'monarch' in lower:
        return ("Claims and defends the Monarch for steady card draw while using evasion, deterrents, or removal to keep the crown.")
    if 'investigate' in lower:
        return ("Generates Clue tokens to bank future card draw while triggering artifact and token-matter synergies.")
    if 'surveil' in lower:
        return ("Filters and stocks the graveyard with Surveil, enabling recursion, delve, and threshold-like payoffs.")
    if 'explore' in lower:
        return ("Uses Explore triggers to smooth draws, grow creatures with counters, and fuel graveyard-adjacent synergies.")
    if 'historic' in lower and 'historics' in lower:
        return ("Casts a dense mix of artifacts, legendaries, and sagas to trigger Historic-matter payoffs repeatedly.")
    if 'exploit' in lower:
        return ("Sacrifices creatures on ETB (Exploit) to convert fodder into removal, card draw, or recursion leverage.")
    if '-1/-1' in lower:
        return ("Distributes -1/-1 counters for removal, attrition, and combo loops—recycling or exploiting death triggers.")
    if 'experience' in lower:
        return ("Builds experience counters to scale repeatable commander-specific payoffs into exponential board or value growth.")
    if 'loyalty' in lower or 'superfriends' in lower or 'planeswalker' in lower:
        return ("Protects and reuses planeswalkers—stacking loyalty acceleration, proliferate, and recurring interaction for inevitability.")
    if 'shield counter' in lower or 'shield-counters' in lower:
        return ("Applies shield counters to insulate key threats, turning removal trades lopsided while advancing a protected board state.")
    if 'sagas matter' in lower or 'sagas' in lower:
        return ("Cycles through Saga chapters for repeatable value—abusing recursion, copying, or reset effects to replay powerful chapter triggers.")
    if 'exp counters' in lower:
        return ("Accumulates experience counters as a permanent scaling vector, compounding the efficiency of commander-centric engines.")
    if 'lifegain' in lower or 'life gain' in lower or 'life-matters' in lower:
        return ("Turns repeated lifegain triggers into card draw, scaling creatures, or alternate win drains while stabilizing vs. aggression.")
    if 'lifeloss' in lower and 'life loss' in lower:
        return ("Leverages incremental life loss across the table to fuel symmetric draw, recursion, and inevitability drains.")
    if 'wheels' in lower:
        return ("Continuously refills hands with mass draw/discard (wheel) effects, weaponizing symmetrical replacement via damage or token payoffs.")
    if 'theft' in lower or 'steal' in lower:
        return ("Temporarily or permanently acquires opponents' permanents, converting stolen assets into board control and resource denial.")
    if 'blink' in lower:
        return ("Loops enter-the-battlefield triggers via flicker/blink effects for compounding value and soft-lock synergies.")

    # Remaining generic branch and tribal fallback
    if 'kindred' in lower or (base.endswith(' Tribe') or base.endswith(' Tribal')):
        # Extract creature type (first word before Kindred, or first token)
        parts = base.split()
        ctype = parts[0] if parts else 'creature'
        ex = list_fmt(syn_preview, 2)
        tail = f" (e.g., {ex})" if ex else ''
        return f"Focuses on getting a high number of {ctype} creatures into play with shared payoffs{tail}."
    if 'extra turn' in lower:
        return "Accumulates extra turn effects to snowball card advantage, combat steps, and inevitability."
    ex2 = list_fmt(syn_preview, 2)
    if ex2:
        return f"Builds around {base} leveraging synergies with {ex2}."
    return f"Builds around the {base} theme and its supporting synergies."


def _derive_popularity_bucket(count: int, boundaries: List[int]) -> str:
    # boundaries expected ascending length 4 dividing into 5 buckets
    # Example: [50, 120, 250, 600]
    if count <= boundaries[0]:
        return 'Rare'
    if count <= boundaries[1]:
        return 'Niche'
    if count <= boundaries[2]:
        return 'Uncommon'
    if count <= boundaries[3]:
        return 'Common'
    return 'Very Common'


def build_catalog(limit: int, verbose: bool) -> Dict[str, Any]:
    # Deterministic seed for inference ordering & any randomized fallback ordering
    seed_env = os.environ.get('EDITORIAL_SEED')
    if seed_env:
        try:
            random.seed(int(seed_env))
        except Exception:
            random.seed(seed_env)
    analytics = regenerate_analytics(verbose)
    whitelist = analytics['whitelist']
    synergy_cap = int(whitelist.get('synergy_cap', 0) or 0)
    normalization_map: Dict[str, str] = whitelist.get('normalization', {}) if isinstance(whitelist.get('normalization'), dict) else {}
    enforced_cfg: Dict[str, List[str]] = whitelist.get('enforced_synergies', {}) or {}
    aggressive_fill = bool(int(os.environ.get('EDITORIAL_AGGRESSIVE_FILL', '0') or '0'))

    yaml_catalog = load_catalog_yaml(verbose)
    all_themes: Set[str] = set(analytics['theme_tags']) | {t.display_name for t in yaml_catalog.values()}
    if normalization_map:
        all_themes = apply_normalization(all_themes, normalization_map)
    curated_baseline = derive_synergies_for_tags(all_themes)

    # --- Synergy pairs fallback (external curated pairs) ---
    synergy_pairs_path = ROOT / 'config' / 'themes' / 'synergy_pairs.yml'
    synergy_pairs: Dict[str, List[str]] = {}
    if yaml is not None and synergy_pairs_path.exists():  # pragma: no cover (I/O)
        try:
            raw_pairs = yaml.safe_load(synergy_pairs_path.read_text(encoding='utf-8')) or {}
            sp = raw_pairs.get('synergy_pairs', {}) if isinstance(raw_pairs, dict) else {}
            if isinstance(sp, dict):
                for k, v in sp.items():
                    if isinstance(k, str) and isinstance(v, list):
                        cleaned = [str(x) for x in v if isinstance(x, str) and x]
                        if cleaned:
                            synergy_pairs[k] = cleaned[:8]  # safety cap
        except Exception as _e:  # pragma: no cover
            if verbose:
                print(f"[build_theme_catalog] Failed loading synergy_pairs.yml: {_e}", file=sys.stderr)
    # Apply normalization to synergy pair keys if needed
    if normalization_map and synergy_pairs:
        normalized_pairs: Dict[str, List[str]] = {}
        for k, lst in synergy_pairs.items():
            nk = normalization_map.get(k, k)
            normed_list = []
            seen = set()
            for s in lst:
                s2 = normalization_map.get(s, s)
                if s2 not in seen:
                    normed_list.append(s2)
                    seen.add(s2)
            if nk not in normalized_pairs:
                normalized_pairs[nk] = normed_list
        synergy_pairs = normalized_pairs

    entries: List[Dict[str, Any]] = []
    processed = 0
    sorted_themes = sorted(all_themes)
    if seed_env:  # Optional shuffle for testing ordering stability (then re-sort deterministically by name removed)
        # Keep original alphabetical for stable UX; deterministic seed only affects downstream random choices.
        pass
    for theme in sorted_themes:
        if limit and processed >= limit:
            break
        processed += 1
        y = yaml_catalog.get(theme)
        curated_list = []
        if y and y.curated_synergies:
            curated_list = list(y.curated_synergies)
        else:
            # Baseline heuristics
            curated_list = curated_baseline.get(theme, [])
            # If still empty, attempt synergy_pairs fallback
            if (not curated_list) and theme in synergy_pairs:
                curated_list = list(synergy_pairs.get(theme, []))
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

        # Aggressive fill mode: if after merge we would have <3 synergies (excluding curated/enforced), attempt to borrow
        # from global top co-occurrences even if below normal thresholds. This is opt-in for ultra sparse themes.
        if aggressive_fill and len(curated_list) + len(enforced_list) < 2 and len(inferred_list) < 2:
            anchor = theme
            co_map = analytics['co_map']
            if anchor in co_map:
                candidates = cooccurrence_scores_for(anchor, analytics['co_map'], analytics['tag_counts'], analytics['total_rows'])
                for other, score, co_count in candidates:
                    if other in curated_list or other in enforced_list or other == anchor or other in inferred_list:
                        continue
                    inferred_list.append(other)
                    if len(inferred_list) >= 4:
                        break

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

        # Land type theme filtering: Gates/Caves/Spheres are land types, not artifact/token mechanics.
        # Rationale: These themes tag specific land cards, creating spurious correlations with artifact/token
        # themes when those cards happen to also produce artifacts/tokens (e.g., Tireless Tracker in Gates decks).
        # Filter out artifact/token synergies that don't make thematic sense for land-type-matters strategies.
        land_type_themes = {"Gates Matter"}
        incompatible_with_land_types = {
            "Investigate", "Clue Token", "Detective Kindred"
        }
        if theme in land_type_themes:
            merged = [s for s in merged if s not in incompatible_with_land_types]
        # For non-land-type themes, don't filter (they can legitimately synergize with these)

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

        slug = getattr(y, 'id', None) or slugify_theme(theme)
        entry = {'id': slug, 'theme': theme, 'synergies': merged}
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
            if hasattr(y, 'popularity_bucket') and getattr(y, 'popularity_bucket'):
                entry['popularity_bucket'] = getattr(y, 'popularity_bucket')
            if hasattr(y, 'editorial_quality') and getattr(y, 'editorial_quality'):
                entry['editorial_quality'] = getattr(y, 'editorial_quality')
        # Derive popularity bucket if absent using total frequency across colors
        if 'popularity_bucket' not in entry:
            total_freq = 0
            for c in analytics['frequencies'].keys():
                try:
                    total_freq += int(analytics['frequencies'].get(c, {}).get(theme, 0))
                except Exception:
                    pass
            # Heuristic boundaries (tunable via env override)
            b_env = os.environ.get('EDITORIAL_POP_BOUNDARIES')  # e.g. "50,120,250,600"
            if b_env:
                try:
                    parts = [int(x.strip()) for x in b_env.split(',') if x.strip()]
                    if len(parts) == 4:
                        boundaries = parts
                    else:
                        boundaries = [40, 100, 220, 500]
                except Exception:
                    boundaries = [40, 100, 220, 500]
            else:
                boundaries = [40, 100, 220, 500]
            entry['popularity_bucket'] = _derive_popularity_bucket(total_freq, boundaries)
        # Description: respect curated YAML description if provided; else auto-generate.
        if y and hasattr(y, 'description') and getattr(y, 'description'):
            entry['description'] = getattr(y, 'description')
        else:
            try:
                entry['description'] = _auto_description(theme, entry.get('synergies', []))
            except Exception:
                pass
        entries.append(entry)

    # Renamed from 'provenance' to 'metadata_info' (migration phase)
    # Compute deterministic hash of YAML catalog + synergy_cap for drift detection
    import hashlib as _hashlib  # local import to avoid top-level cost
    def _catalog_hash() -> str:
        h = _hashlib.sha256()
        # Stable ordering: sort by display_name then key ordering inside dict for a subset of stable fields
        for name in sorted(yaml_catalog.keys()):
            yobj = yaml_catalog[name]
            try:
                # Compose a tuple of fields that should reflect editorial drift
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
        h.update(str(synergy_cap).encode('utf-8'))
        return h.hexdigest()
    metadata_info = {
        'mode': 'merge',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'curated_yaml_files': len(yaml_catalog),
        'synergy_cap': synergy_cap,
        'inference': 'pmi',
        'version': 'phase-b-merge-v1',
        'catalog_hash': _catalog_hash(),
    }
    # Optional popularity analytics export for Phase D metrics collection
    if os.environ.get('EDITORIAL_POP_EXPORT'):
        try:
            bucket_counts: Dict[str, int] = {}
            for t in entries:
                b = t.get('popularity_bucket', 'Unknown')
                bucket_counts[b] = bucket_counts.get(b, 0) + 1
            export = {
                'generated_at': metadata_info['generated_at'],
                'bucket_counts': bucket_counts,
                'total_themes': len(entries),
            }
            metrics_path = OUTPUT_JSON.parent / 'theme_popularity_metrics.json'
            with open(metrics_path, 'w', encoding='utf-8') as mf:
                json.dump(export, mf, indent=2)
        except Exception as _e:  # pragma: no cover
            if verbose:
                print(f"[build_theme_catalog] Failed popularity metrics export: {_e}", file=sys.stderr)
    return {
        'themes': entries,
        'frequencies_by_base_color': analytics['frequencies'],
    'generated_from': 'merge (analytics + curated YAML + whitelist)',
    'metadata_info': metadata_info,
        'yaml_catalog': yaml_catalog,  # include for optional backfill step
        # Lightweight analytics for downstream tests/reports (not written unless explicitly requested)
        'description_fallback_summary': _compute_fallback_summary(entries, analytics['frequencies']) if os.environ.get('EDITORIAL_INCLUDE_FALLBACK_SUMMARY') else None,
    }


def _compute_fallback_summary(entries: List[Dict[str, Any]], freqs: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Compute statistics about generic fallback descriptions.

    A description is considered a generic fallback if it begins with one of the
    standard generic stems produced by _auto_description:
      - "Builds around "
    Tribal phrasing ("Focuses on getting a high number of ...") is NOT treated
    as generic; it conveys archetype specificity.
    """
    def total_freq(theme: str) -> int:
        s = 0
        for c in freqs.keys():
            try:
                s += int(freqs.get(c, {}).get(theme, 0))
            except Exception:
                pass
        return s

    generic: List[Dict[str, Any]] = []
    generic_with_synergies = 0
    generic_plain = 0
    for e in entries:
        desc = (e.get('description') or '').strip()
        if not desc.startswith('Builds around'):
            continue
        # Distinguish forms
        if desc.startswith('Builds around the '):
            generic_plain += 1
        else:
            generic_with_synergies += 1
        theme = e.get('theme')
        generic.append({
            'theme': theme,
            'popularity_bucket': e.get('popularity_bucket'),
            'synergy_count': len(e.get('synergies') or []),
            'total_frequency': total_freq(theme),
            'description': desc,
        })

    generic.sort(key=lambda x: (-x['total_frequency'], x['theme']))
    return {
        'total_themes': len(entries),
        'generic_total': len(generic),
        'generic_with_synergies': generic_with_synergies,
        'generic_plain': generic_plain,
        'generic_pct': round(100.0 * len(generic) / max(1, len(entries)), 2),
        'top_generic_by_frequency': generic[:50],  # cap for brevity
    }



def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description='Build merged theme catalog (Phase B)')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--schema', action='store_true', help='Print JSON Schema for catalog and exit')
    parser.add_argument('--allow-limit-write', action='store_true', help='Allow writing theme_list.json when --limit > 0 (safety guard)')
    parser.add_argument('--backfill-yaml', action='store_true', help='Write auto-generated description & popularity_bucket back into YAML files (fills missing only)')
    parser.add_argument('--force-backfill-yaml', action='store_true', help='Force overwrite existing description/popularity_bucket in YAML when backfilling')
    parser.add_argument('--output', type=str, default=str(OUTPUT_JSON), help='Output path for theme_list.json (tests can override)')
    args = parser.parse_args()
    if args.schema:
        # Lazy import to avoid circular dependency: replicate minimal schema inline from models file if present
        try:
            from type_definitions_theme_catalog import ThemeCatalog
            import json as _json
            print(_json.dumps(ThemeCatalog.model_json_schema(), indent=2))
            return
        except Exception as _e:  # pragma: no cover
            print(f"Failed to load schema models: {_e}")
            return
    data = build_catalog(limit=args.limit, verbose=args.verbose)
    if args.dry_run:
        print(json.dumps({'theme_count': len(data['themes']), 'metadata_info': data['metadata_info']}, indent=2))
    else:
        out_path = Path(args.output).resolve()
        target_is_default = out_path == OUTPUT_JSON
        if target_is_default and args.limit and not args.allow_limit_write:
            print(f"Refusing to overwrite {OUTPUT_JSON.name} with truncated list (limit={args.limit}). Use --allow-limit-write to force or omit --limit.", file=sys.stderr)
            return
        os.makedirs(out_path.parent, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in data.items() if k != 'yaml_catalog'}, f, indent=2, ensure_ascii=False)

        # KPI fallback summary history (append JSONL) if computed
        if data.get('description_fallback_summary'):
            try:
                history_path = OUTPUT_JSON.parent / 'description_fallback_history.jsonl'
                record = {
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    **(data['description_fallback_summary'] or {})
                }
                with open(history_path, 'a', encoding='utf-8') as hf:
                    hf.write(json.dumps(record) + '\n')
            except Exception as _e:  # pragma: no cover
                print(f"[build_theme_catalog] Failed writing KPI history: {_e}", file=sys.stderr)

        # Optional YAML backfill step (CLI flag or env EDITORIAL_BACKFILL_YAML=1)
        do_backfill_env = bool(int(os.environ.get('EDITORIAL_BACKFILL_YAML', '0') or '0'))
        if (args.backfill_yaml or do_backfill_env) and target_is_default:
            # Safeguard: if catalog dir missing, attempt to auto-export Phase A YAML first
            if not CATALOG_DIR.exists():  # pragma: no cover (environmental)
                try:
                    from scripts.export_themes_to_yaml import main as export_main
                    export_main(['--force'])
                except Exception as _e:
                    print(f"[build_theme_catalog] WARNING: catalog dir missing and auto export failed: {_e}", file=sys.stderr)
            if yaml is None:
                print('[build_theme_catalog] PyYAML not available; skipping YAML backfill', file=sys.stderr)
            else:
                force = args.force_backfill_yaml
                updated = 0
                for entry in data['themes']:
                    theme_name = entry.get('theme')
                    ty = data['yaml_catalog'].get(theme_name) if isinstance(data.get('yaml_catalog'), dict) else None
                    if not ty or not getattr(ty, '_path', None):
                        continue
                    try:
                        raw = yaml.safe_load(ty._path.read_text(encoding='utf-8')) or {}
                    except Exception:
                        continue
                    changed = False
                    # Metadata info stamping (formerly 'provenance')
                    meta_block = raw.get('metadata_info') if isinstance(raw.get('metadata_info'), dict) else {}
                    # Legacy migration: if no metadata_info but legacy provenance present, adopt it
                    if not meta_block and isinstance(raw.get('provenance'), dict):
                        meta_block = raw.get('provenance')
                        changed = True
                    if force or not meta_block.get('last_backfill'):
                        meta_block['last_backfill'] = time.strftime('%Y-%m-%dT%H:%M:%S')
                        meta_block['script'] = 'build_theme_catalog.py'
                        meta_block['version'] = 'phase-b-merge-v1'
                        raw['metadata_info'] = meta_block
                        if 'provenance' in raw:
                            del raw['provenance']
                        changed = True
                    # Backfill description
                    if force or not raw.get('description'):
                        if entry.get('description'):
                            raw['description'] = entry['description']
                            changed = True
                    # Backfill popularity_bucket (always reflect derived unless pinned and not forcing?)
                    if force or not raw.get('popularity_bucket'):
                        if entry.get('popularity_bucket'):
                            raw['popularity_bucket'] = entry['popularity_bucket']
                            changed = True
                    # Backfill editorial_quality if forcing and present in catalog entry but absent in YAML
                    if force and entry.get('editorial_quality') and not raw.get('editorial_quality'):
                        raw['editorial_quality'] = entry['editorial_quality']
                        changed = True
                    if changed:
                        try:
                            with open(ty._path, 'w', encoding='utf-8') as yf:
                                yaml.safe_dump(raw, yf, sort_keys=False, allow_unicode=True)
                            updated += 1
                        except Exception as _e:  # pragma: no cover
                            print(f"[build_theme_catalog] Failed writing back {ty._path.name}: {_e}", file=sys.stderr)
                if updated and args.verbose:
                    print(f"[build_theme_catalog] Backfilled metadata into {updated} YAML files", file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # broad guard for orchestrator fallback
        print(f"ERROR: build_theme_catalog failed: {e}", file=sys.stderr)
        sys.exit(1)
