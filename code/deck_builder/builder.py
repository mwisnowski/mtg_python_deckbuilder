from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple
import pandas as pd
import math
import random
import re
import datetime

# Logging (must precede heavy module logic to ensure handlers ready)
import logging_util

# Phase 0 core primitives (fuzzy helpers, bracket definitions)
from .phases.phase0_core import (
    _full_ratio, _top_matches,
    EXACT_NAME_THRESHOLD, FIRST_WORD_THRESHOLD, MAX_PRESENTED_CHOICES,
    BracketDefinition
)
from .phases.phase1_commander import CommanderSelectionMixin
from .phases.phase2_lands_basics import LandBasicsMixin
from .phases.phase2_lands_staples import LandStaplesMixin
from .phases.phase2_lands_kindred import LandKindredMixin
from .phases.phase2_lands_fetch import LandFetchMixin
from .phases.phase2_lands_duals import LandDualsMixin
from .phases.phase2_lands_triples import LandTripleMixin
from .phases.phase2_lands_misc import LandMiscUtilityMixin
from .phases.phase2_lands_optimize import LandOptimizationMixin
from .phases.phase3_creatures import CreatureAdditionMixin
from .phases.phase4_spells import SpellAdditionMixin
from .phases.phase5_color_balance import ColorBalanceMixin
from .phases.phase6_reporting import ReportingMixin

# Local application imports
from . import builder_constants as bc
from . import builder_utils as bu

# Create logger consistent with existing pattern (mirrors tagging/tagger.py usage)
logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
# Avoid duplicate handler attachment if reloaded (defensive; get_logger already guards but we mirror tagger.py approach)
if not any(isinstance(h, logging_util.logging.FileHandler) and getattr(h, 'baseFilename', '').endswith('deck_builder.log') for h in logger.handlers):
    logger.addHandler(logging_util.file_handler)
if not any(isinstance(h, logging_util.logging.StreamHandler) for h in logger.handlers):
    logger.addHandler(logging_util.stream_handler)

## Phase 0 extraction note: fuzzy helpers & BRACKET_DEFINITIONS imported above

## Phase 0 extraction: BracketDefinition & BRACKET_DEFINITIONS now imported

@dataclass
class DeckBuilder(CommanderSelectionMixin,
                  LandBasicsMixin,
                  LandStaplesMixin,
                  LandKindredMixin,
                  LandFetchMixin,
                  LandDualsMixin,
                  LandTripleMixin,
                  LandMiscUtilityMixin,
                  LandOptimizationMixin,
                  CreatureAdditionMixin,
                  SpellAdditionMixin,
                  ColorBalanceMixin,
                  ReportingMixin):
    # Commander core selection state
    commander_name: str = ""
    commander_row: Optional[pd.Series] = None
    commander_tags: List[str] = field(default_factory=list)

    # Tag prioritization
    primary_tag: Optional[str] = None
    secondary_tag: Optional[str] = None
    tertiary_tag: Optional[str] = None
    selected_tags: List[str] = field(default_factory=list)

    # Future deck config placeholders
    color_identity: List[str] = field(default_factory=list)  # raw list of color letters e.g. ['B','G']
    color_identity_key: Optional[str] = None  # canonical key form e.g. 'B, G'
    color_identity_full: Optional[str] = None  # human readable e.g. 'Golgari: Black/Green'
    files_to_load: List[str] = field(default_factory=list)  # csv file stems to load
    synergy_profile: Dict[str, Any] = field(default_factory=dict)
    deck_goal: Optional[str] = None

    # Aggregated commander info (scalar fields)
    commander_dict: Dict[str, Any] = field(default_factory=dict)

    # Power bracket state (Deck Building Step 1)
    bracket_level: Optional[int] = None
    bracket_name: Optional[str] = None
    bracket_limits: Dict[str, Optional[int]] = field(default_factory=dict)
    bracket_definition: Optional[BracketDefinition] = None

    # Cached data
    _commander_df: Optional[pd.DataFrame] = None
    _combined_cards_df: Optional[pd.DataFrame] = None
    _full_cards_df: Optional[pd.DataFrame] = None  # immutable snapshot of original combined pool

    # Deck library (cards added so far) mapping name->record
    card_library: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Tag tracking: counts of unique cards per tag (not per copy)
    tag_counts: Dict[str,int] = field(default_factory=dict)
    # Internal map name -> set of tags used for uniqueness checks
    _card_name_tags_index: Dict[str,set] = field(default_factory=dict)
    # Deferred suggested lands based on tags / conditions
    suggested_lands_queue: List[Dict[str, Any]] = field(default_factory=list)
    # Baseline color source matrix captured after land build, before spell adjustments
    color_source_matrix_baseline: Optional[Dict[str, Dict[str,int]]] = None
    # Live cached color source matrix (recomputed lazily when lands change)
    _color_source_matrix_cache: Optional[Dict[str, Dict[str,int]]] = None
    _color_source_cache_dirty: bool = True
    # Cached spell pip weights (invalidate on non-land changes)
    _spell_pip_weights_cache: Optional[Dict[str, float]] = None
    _spell_pip_cache_dirty: bool = True

    # Build/session timestamp for export naming
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime('%Y%m%d%H%M%S'))

    # IO injection for testing
    input_func: Callable[[str], str] = field(default=lambda prompt: input(prompt))
    output_func: Callable[[str], None] = field(default=lambda msg: print(msg))
    # Deterministic random support
    seed: Optional[int] = None
    _rng: Any = field(default=None, repr=False)

    # Logging / output behavior
    log_outputs: bool = True  # if True, mirror output_func messages into logger at INFO level
    _original_output_func: Optional[Callable[[str], None]] = field(default=None, repr=False)

    def __post_init__(self):
        """Post-init hook to wrap the provided output function so that all user-facing
        messages are also captured in the central log (at INFO level) unless disabled.
        """
        if self.log_outputs:
            # Preserve original
            self._original_output_func = self.output_func

            def _wrapped(msg: str):
                try:
                    # Collapse excessive blank lines for log readability, but keep printing original
                    log_msg = msg.rstrip()
                    if log_msg:
                        logger.info(log_msg)
                except Exception:
                    pass
                self._original_output_func(msg)

            self.output_func = _wrapped  # type: ignore

    # Internal explicit logging helper for code paths where we do NOT want to echo to user
    def _log_debug(self, msg: str):
        logger.debug(msg)

    def _log_info(self, msg: str):
        logger.info(msg)

    def _log_warning(self, msg: str):
        logger.warning(msg)

    def _log_error(self, msg: str):
        logger.error(msg)

    # ---------------------------
    # High-level Orchestration
    # ---------------------------
    def build_deck_full(self) -> None:
        """Run the full interactive deck building pipeline and export deck CSV.

        Steps:
          1. Commander selection & tag prioritization
          2. Power bracket & ideal composition inputs
          3. Land building steps (1-8)
          4. Creature addition (theme-weighted)
          5. Non-creature spell categories & filler
          6. Post-spell land color balancing & basic rebalance
          7. CSV export (deck_files/<name>_<date>.csv)
        """
        logger.info("=== Deck Build: START ===")
        start_ts = datetime.datetime.now()
        try:
            logger.info("Step 0: Initial setup")
            self.run_initial_setup()
            logger.info("Step 1: Commander selection & tag prioritization complete")
            self.run_deck_build_step1()
            logger.info("Step 2: Power bracket & composition inputs")
            self.run_deck_build_step2()
            # Land steps (1-8)
            for step in range(1, 9):
                m = getattr(self, f"run_land_step{step}", None)
                if callable(m):
                    logger.info(f"Land Step {step}: begin")
                    m()
                    logger.info(f"Land Step {step}: complete (current land count {self._current_land_count() if hasattr(self, '_current_land_count') else 'n/a'})")
            # Creatures
            if hasattr(self, 'add_creatures'):
                logger.info("Adding creatures phase")
                self.add_creatures()
            # Non-creature spells
            if hasattr(self, 'add_non_creature_spells'):
                logger.info("Adding non-creature spells phase")
                self.add_non_creature_spells()
            # Post-spell land adjustments
            if hasattr(self, 'post_spell_land_adjust'):
                logger.info("Post-spell land adjustment phase")
                self.post_spell_land_adjust()
            # Export
            if hasattr(self, 'export_decklist_csv'):
                logger.info("Export decklist phase")
                csv_path = self.export_decklist_csv()
                # Also emit plaintext list (.txt) for quick copy/paste
                try:
                    # Derive matching stem by replacing extension from csv_path
                    import os as _os
                    base, _ext = _os.path.splitext(_os.path.basename(csv_path))
                    self.export_decklist_text(filename=base + '.txt')  # type: ignore[attr-defined]
                except Exception:
                    logger.warning("Plaintext export failed (non-fatal)")
            end_ts = datetime.datetime.now()
            logger.info(f"=== Deck Build: COMPLETE in {(end_ts - start_ts).total_seconds():.2f}s ===")
        except KeyboardInterrupt:
            logger.warning("Deck build cancelled by user (KeyboardInterrupt).")
            self.output_func("\nDeck build cancelled by user.")
        except Exception as e:
            logger.exception("Deck build failed with exception")
            self.output_func(f"Deck build failed: {e}")

    # ---------------------------
    # RNG Initialization
    # ---------------------------
    def _get_rng(self):  # lazy init to allow seed set post-construction
        if self._rng is None:
            import random as _r
            self._rng = _r.Random(self.seed) if self.seed is not None else _r
        return self._rng

    # ---------------------------
    # Data Loading
    # ---------------------------
    def load_commander_data(self) -> pd.DataFrame:
        if self._commander_df is not None:
            return self._commander_df
        df = pd.read_csv(
            bc.COMMANDER_CSV_PATH,
            converters=getattr(bc, "COMMANDER_CONVERTERS", None)
        )
        if "themeTags" not in df.columns:
            df["themeTags"] = [[] for _ in range(len(df))]
        if "creatureTypes" not in df.columns:
            df["creatureTypes"] = [[] for _ in range(len(df))]
        self._commander_df = df
        return df

    # ---------------------------
    # Fuzzy Search Helpers
    # ---------------------------
    def _auto_accept(self, query: str, candidate: str) -> bool:
        full = _full_ratio(query, candidate)
        if full >= EXACT_NAME_THRESHOLD:
            return True
        q_first = query.strip().split()[0].lower() if query.strip() else ""
        c_first = candidate.split()[0].lower()
        if q_first and _full_ratio(q_first, c_first) >= FIRST_WORD_THRESHOLD:
            return True
        return False

    def _gather_candidates(self, query: str, names: List[str]) -> List[tuple]:
        scored = _top_matches(query, names, MAX_PRESENTED_CHOICES)
        uniq: Dict[str, int] = {}
        for n, s in scored:
            uniq[n] = max(uniq.get(n, 0), s)
        return sorted(uniq.items(), key=lambda x: x[1], reverse=True)

    # ---------------------------
    # Commander Dict Initialization
    # ---------------------------
    def _initialize_commander_dict(self, row: pd.Series):
        def get(field: str, default=""):
            return row.get(field, default) if isinstance(row, pd.Series) else default

        mana_cost = get("manaCost", "")
        mana_value = get("manaValue", get("cmc", None))
        try:
            if mana_value is None and isinstance(mana_cost, str):
                mana_value = mana_cost.count("}") if "}" in mana_cost else None
        except Exception:
            pass

        color_identity_raw = get("colorIdentity", get("colors", []))
        if isinstance(color_identity_raw, str):
            stripped = color_identity_raw.strip("[] ")
            if "," in stripped:
                color_identity = [c.strip(" '\"") for c in stripped.split(",")]
            else:
                color_identity = list(stripped)
        else:
            color_identity = color_identity_raw if isinstance(color_identity_raw, list) else []

        colors_field = get("colors", color_identity)
        if isinstance(colors_field, str):
            colors = list(colors_field)
        else:
            colors = colors_field if isinstance(colors_field, list) else []

        type_line = get("type", get("type_line", ""))
        creature_types = get("creatureTypes", [])
        if isinstance(creature_types, str):
            creature_types = [s.strip() for s in creature_types.split(",") if s.strip()]

        text_field = get("text", get("oracleText", ""))
        if isinstance(text_field, str):
            text_field = text_field.replace("\\n", "\n")

        power = get("power", "")
        toughness = get("toughness", "")
        themes = get("themeTags", [])
        if isinstance(themes, str):
            themes = [t.strip() for t in themes.split(",") if t.strip()]

        cmc = get("cmc", mana_value if mana_value is not None else 0.0)
        try:
            cmc = float(cmc) if cmc not in ("", None) else 0.0
        except Exception:
            cmc = 0.0

        self.commander_dict = {
            "Commander Name": self.commander_name,
            "Mana Cost": mana_cost,
            "Mana Value": mana_value,
            "Color Identity": color_identity,
            "Colors": colors,
            "Type": type_line,
            "Creature Types": creature_types,
            "Text": text_field,
            "Power": power,
            "Toughness": toughness,
            "Themes": themes,
            "CMC": cmc,
        }
        # Ensure commander added to card library
        try:
            self.add_card(
                card_name=self.commander_name,
                card_type=type_line,
                mana_cost=mana_cost,
                mana_value=cmc,
                creature_types=creature_types if isinstance(creature_types, list) else [],
                tags=themes if isinstance(themes, list) else [],
                is_commander=True
            )
        except Exception:
            pass

    # ---------------------------
    # Pretty Display
    # ---------------------------
    def _format_commander_pretty(self, row: pd.Series) -> str:

        def norm(val):
            if isinstance(val, list) and len(val) == 1:
                val = val[0]
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return "-"
            return val

        def join_list(val, sep=", "):
            val = norm(val)
            if isinstance(val, list):
                return sep.join(str(x) for x in val) if val else "-"
            return str(val)

        name = norm(row.get("name", ""))
        face_name = norm(row.get("faceName", name))
        edhrec = norm(row.get("edhrecRank", "-"))
        color_identity = join_list(row.get("colorIdentity", row.get("colors", [])), "")
        colors = join_list(row.get("colors", []), "")
        mana_cost = norm(row.get("manaCost", ""))
        mana_value = norm(row.get("manaValue", row.get("cmc", "-")))
        type_line = norm(row.get("type", row.get("type_line", "")))
        creature_types = join_list(row.get("creatureTypes", []))
        text_field = norm(row.get("text", row.get("oracleText", "")))
        text_field = str(text_field).replace("\\n", "\n")
        power = norm(row.get("power", "-"))
        toughness = norm(row.get("toughness", "-"))
        keywords = join_list(row.get("keywords", []))
        raw_tags = row.get("themeTags", [])
        if isinstance(raw_tags, str):
            tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            if len(raw_tags) == 1 and isinstance(raw_tags[0], list):
                tags_list = raw_tags[0]
            else:
                tags_list = raw_tags
        else:
            tags_list = []
        layout = norm(row.get("layout", "-"))
        side = norm(row.get("side", "-"))

        lines = [
            "Selected Commander:",
            f"Name: {name}",
            f"Face Name: {face_name}",
            f"EDHREC Rank: {edhrec}",
            f"Color Identity: {color_identity}",
            f"Colors: {colors}",
            f"Mana Cost: {mana_cost}",
            f"Mana Value: {mana_value}",
            f"Type: {type_line}",
            f"Creature Types: {creature_types}",
            f"Power/Toughness: {power}/{toughness}",
            f"Keywords: {keywords}",
            f"Layout: {layout}",
            f"Side: {side}",
        ]
        if tags_list:
            lines.append("Theme Tags:")
            for t in tags_list:
                lines.append(f"  - {t}")
        else:
            lines.append("Theme Tags: -")
        lines.extend([
            "Text:",
            text_field,
            ""
        ])
        return "\n".join(lines)

    def _present_commander_and_confirm(self, df: pd.DataFrame, name: str) -> bool:
        row = df[df["name"] == name].iloc[0]
        pretty = self._format_commander_pretty(row)
        self.output_func("\n" + pretty)
        while True:
            resp = self.input_func("Is this the commander you want? (y/n): ").strip().lower()
            if resp in ("y", "yes"):
                self._apply_commander_selection(row)
                return True
            if resp in ("n", "no"):
                return False
            self.output_func("Please enter y or n.")

    # (Commander selection, tag prioritization, and power bracket methods moved to CommanderSelectionMixin in phases/phase1_commander.py)

    # ---------------------------
    # Color Identity & Card Pool Loading (New Step)
    # ---------------------------
    def _canonical_color_key(self, colors: List[str]) -> str:
        """Return canonical key like 'B, G, W' or 'COLORLESS'. Uses alphabetical ordering.

        The legacy constants expect a specific ordering (alphabetical seems consistent in provided maps).
        """
        if not colors:
            return 'COLORLESS'
        # Deduplicate & sort
        uniq = sorted({c.strip().upper() for c in colors if c.strip()})
        return ', '.join(uniq)

    def determine_color_identity(self) -> Tuple[str, List[str]]:
        """Determine color identity key/full name and derive csv file list.

        Returns (color_identity_full, files_to_load).
        """
        if self.commander_row is None:
            raise RuntimeError("Commander must be selected before determining color identity.")

        raw_ci = self.commander_row.get('colorIdentity')
        if isinstance(raw_ci, list):
            colors_list = raw_ci
        elif isinstance(raw_ci, str) and raw_ci.strip():
            # Could be formatted like "['B','G']" or 'BG'; attempt simple parsing
            if ',' in raw_ci:
                colors_list = [c.strip().strip("'[] ") for c in raw_ci.split(',') if c.strip().strip("'[] ")]
            else:
                colors_list = [c for c in raw_ci if c.isalpha()]
        else:
            # Fallback to 'colors' field or treat as colorless
            alt = self.commander_row.get('colors')
            if isinstance(alt, list):
                colors_list = alt
            elif isinstance(alt, str) and alt.strip():
                colors_list = [c for c in alt if c.isalpha()]
            else:
                colors_list = []

        self.color_identity = [c.upper() for c in colors_list]
        self.color_identity_key = self._canonical_color_key(self.color_identity)

        # Match against maps
        full = None
        load_files: List[str] = []
        key = self.color_identity_key
        if key in bc.MONO_COLOR_MAP:
            full, load_files = bc.MONO_COLOR_MAP[key]
        elif key in bc.DUAL_COLOR_MAP:
            info = bc.DUAL_COLOR_MAP[key]
            full, load_files = info[0], info[2]
        elif key in bc.TRI_COLOR_MAP:
            info = bc.TRI_COLOR_MAP[key]
            full, load_files = info[0], info[2]
        elif key in bc.OTHER_COLOR_MAP:
            info = bc.OTHER_COLOR_MAP[key]
            full, load_files = info[0], info[2]
        else:
            # Unknown / treat as colorless fallback
            full, load_files = 'Unknown', ['colorless']

        self.color_identity_full = full
        self.files_to_load = load_files
        return full, load_files

    def setup_dataframes(self) -> pd.DataFrame:
        """Load all csv files for current color identity into one combined DataFrame.

        Each file stem in files_to_load corresponds to csv_files/{stem}_cards.csv.
        The result is cached and returned. Minimal validation only (non-empty, required columns exist if known).
        """
        if self._combined_cards_df is not None:
            return self._combined_cards_df
        if not self.files_to_load:
            # Attempt to determine if not yet done
            self.determine_color_identity()
        dfs = []
        required = getattr(bc, 'CSV_REQUIRED_COLUMNS', [])
        for stem in self.files_to_load:
            path = f'csv_files/{stem}_cards.csv'
            try:
                df = pd.read_csv(path)
                if required:
                    missing = [c for c in required if c not in df.columns]
                    if missing:
                        # Skip or still keep with warning; choose to warn
                        self.output_func(f"Warning: {path} missing columns: {missing}")
                dfs.append(df)
            except FileNotFoundError:
                self.output_func(f"Warning: CSV file not found: {path}")
                continue
        if not dfs:
            raise RuntimeError("No CSV files loaded for color identity.")
        combined = pd.concat(dfs, axis=0, ignore_index=True)
        # Drop duplicate rows by 'name' if column exists
        if 'name' in combined.columns:
            combined = combined.drop_duplicates(subset='name', keep='first')
        self._combined_cards_df = combined
        # Preserve original snapshot for enrichment across subsequent removals
        if self._full_cards_df is None:
            self._full_cards_df = combined.copy()
        return combined

    # ---------------------------
    # Card Library Management
    # ---------------------------
    def add_card(self,
                 card_name: str,
                 card_type: str = '',
                 mana_cost: str = '',
                 mana_value: Optional[float] = None,
                 creature_types: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None,
                 is_commander: bool = False,
                 role: Optional[str] = None,
                 sub_role: Optional[str] = None,
                 added_by: Optional[str] = None,
                 trigger_tag: Optional[str] = None,
                 synergy: Optional[int] = None) -> None:
        """Add (or increment) a card in the deck library.

        Stores minimal metadata; duplicates increment Count. Basic lands allowed unlimited.
        """
        if creature_types is None:
            creature_types = []
        if tags is None:
            tags = []
        # Compute mana value if missing from cost (simple heuristic: count symbols between braces)
        if mana_value is None and mana_cost:
            try:
                if '{' in mana_cost and '}' in mana_cost:
                    # naive parse: digits add numeric value; individual colored symbols count as 1
                    symbols = re.findall(r'\{([^}]+)\}', mana_cost)
                    total = 0
                    for sym in symbols:
                        if sym.isdigit():
                            total += int(sym)
                        else:
                            total += 1
                    mana_value = total
            except Exception:
                mana_value = None
        entry = self.card_library.get(card_name)
        if entry:
            # Enforce Commander singleton rules: only basic lands may have multiple copies
            try:
                from deck_builder import builder_constants as bc
                from settings import MULTIPLE_COPY_CARDS
            except Exception:
                MULTIPLE_COPY_CARDS = []  # type: ignore
            is_land = 'land' in str(card_type or entry.get('Card Type','')).lower()
            is_basic = False
            try:
                basic_list = getattr(bc, 'BASIC_LANDS', [])
                is_basic = any(card_name == bl or card_name.startswith(bl + ' ') for bl in basic_list)
            except Exception:
                pass
            if is_land and not is_basic:
                # Non-basic land: do not increment
                return
            if card_name in MULTIPLE_COPY_CARDS:
                # Explicit multi-copy list still restricted to 1 in Commander context
                return
            # Basic lands (or other allowed future exceptions) increment
            entry['Count'] += 1
            # Optionally enrich metadata if provided
            if role is not None:
                entry['Role'] = role
            if sub_role is not None:
                entry['SubRole'] = sub_role
            if added_by is not None:
                entry['AddedBy'] = added_by
            if trigger_tag is not None:
                entry['TriggerTag'] = trigger_tag
            if synergy is not None:
                entry['Synergy'] = synergy
        else:
            # If no tags passed attempt enrichment from full snapshot / combined pool
            if not tags:
                df_src = self._full_cards_df if self._full_cards_df is not None else self._combined_cards_df
                try:
                    if df_src is not None and not df_src.empty and 'name' in df_src.columns:
                        row_match = df_src[df_src['name'] == card_name]
                        if not row_match.empty:
                            raw_tags = row_match.iloc[0].get('themeTags', [])
                            if isinstance(raw_tags, list):
                                tags = [str(t).strip() for t in raw_tags if str(t).strip()]
                            elif isinstance(raw_tags, str) and raw_tags.strip():
                                # tolerate comma separated
                                parts = [p.strip().strip("'\"") for p in raw_tags.split(',')]
                                tags = [p for p in parts if p]
                except Exception:
                    pass
            # Normalize & dedupe tags
            norm_tags: list[str] = []
            seen_tag = set()
            for t in tags:
                if not isinstance(t, str):
                    t = str(t)
                tt = t.strip()
                if not tt or tt.lower() == 'nan':
                    continue
                if tt not in seen_tag:
                    norm_tags.append(tt)
                    seen_tag.add(tt)
            tags = norm_tags
            self.card_library[card_name] = {
                'Card Name': card_name,
                'Card Type': card_type,
                'Mana Cost': mana_cost,
                'Mana Value': mana_value,
                'Creature Types': creature_types,
                'Tags': tags,
                'Commander': is_commander,
                'Count': 1,
                'Role': (role or ('commander' if is_commander else None)),
                'SubRole': sub_role,
                'AddedBy': added_by,
                'TriggerTag': trigger_tag,
                'Synergy': synergy,
            }
            # Update tag counts for new unique card
            tag_set = set(tags)
            self._card_name_tags_index[card_name] = tag_set
            for tg in tag_set:
                self.tag_counts[tg] = self.tag_counts.get(tg, 0) + 1
        # Keep commander dict CMC up to date if adding commander
        if is_commander and self.commander_dict:
            if mana_value is not None:
                self.commander_dict['CMC'] = mana_value
        # Remove this card from combined pool if present
        self._remove_from_pool(card_name)
        # Invalidate color source cache if land added
        try:
            if 'land' in str(card_type).lower():
                self._color_source_cache_dirty = True
            else:
                self._spell_pip_cache_dirty = True
        except Exception:
            pass

    def _remove_from_pool(self, card_name: str):
        if self._combined_cards_df is None:
            return
        df = self._combined_cards_df
        if 'name' in df.columns:
            self._combined_cards_df = df[df['name'] != card_name]
        elif 'Card Name' in df.columns:
            self._combined_cards_df = df[df['Card Name'] != card_name]

    # (Power bracket summary/printing now provided by mixin; _format_limits retained locally for reuse)

    @staticmethod
    def _format_limits(limits: Dict[str, Optional[int]]) -> str:
        labels = {
            "game_changers": "Game Changers",
            "mass_land_denial": "Mass Land Denial",
            "extra_turns": "Extra Turn Cards",
            "tutors_nonland": "Nonland Tutors",
            "two_card_combos": "Two-Card Combos"
        }
        lines = []
        for key, label in labels.items():
            val = limits.get(key, None)
            if val is None:
                lines.append(f"  {label}: Unlimited")
            else:
                lines.append(f"  {label}: {val}")
        return "\n".join(lines)

    def run_deck_build_step1(self):
        self.select_power_bracket()

    # ---------------------------
    # Reporting Helper
    # ---------------------------
    def print_commander_dict_table(self):
        if self.commander_row is None:
            self.output_func("No commander selected.")
            return
        block = self._format_commander_pretty(self.commander_row)
        self.output_func("\n" + block)
        # New: show which CSV files (stems) were loaded for this color identity
        if self.files_to_load:
            file_list = ", ".join(f"{stem}_cards.csv" for stem in self.files_to_load)
            self.output_func(f"Card Pool Files: {file_list}")
        if self.selected_tags:
            self.output_func("Chosen Tags:")
            if self.primary_tag:
                self.output_func(f"  Primary : {self.primary_tag}")
            if self.secondary_tag:
                self.output_func(f"  Secondary: {self.secondary_tag}")
            if self.tertiary_tag:
                self.output_func(f"  Tertiary : {self.tertiary_tag}")
            self.output_func("")
        if self.bracket_definition:
            self.output_func(f"Power Bracket: {self.bracket_level} - {self.bracket_name}")
            self.output_func(self._format_limits(self.bracket_limits))
            self.output_func("")

    # ---------------------------
    # Orchestration
    # ---------------------------
    def run_initial_setup(self):
        self.choose_commander()
        self.select_commander_tags()
        # New: color identity & card pool loading
        try:
            self.determine_color_identity()
            self.setup_dataframes()
        except Exception as e:
            self.output_func(f"Failed to load color-identity card pool: {e}")
        self.print_commander_dict_table()

    def run_full_initial_with_bracket(self):
        self.run_initial_setup()
        self.run_deck_build_step1()
        # (Further steps can be chained here)
        self.print_commander_dict_table()

    # ===========================
    # Deck Building Step 2: Ideal Composition Counts
    # ===========================
    ideal_counts: Dict[str, int] = field(default_factory=dict)

    def run_deck_build_step2(self) -> Dict[str, int]:
        """Determine ideal counts for general card categories (bracket‑agnostic baseline).

        Prompts the user (Enter to keep default). Stores results in ideal_counts and returns it.
        Categories:
          ramp, lands, basic_lands, creatures, removal, wipes, card_advantage, protection
        """
        # Initialize defaults from constants if not already present
        defaults = {
            'ramp': bc.DEFAULT_RAMP_COUNT,
            'lands': bc.DEFAULT_LAND_COUNT,
            'basic_lands': bc.DEFAULT_BASIC_LAND_COUNT,
            'creatures': bc.DEFAULT_CREATURE_COUNT,
            'removal': bc.DEFAULT_REMOVAL_COUNT,
            'wipes': bc.DEFAULT_WIPES_COUNT,
            'card_advantage': bc.DEFAULT_CARD_ADVANTAGE_COUNT,
            'protection': bc.DEFAULT_PROTECTION_COUNT,
        }

        # Seed existing values if already set (allow re-run keeping previous choices)
        for k, v in defaults.items():
            if k not in self.ideal_counts:
                self.ideal_counts[k] = v

        self.output_func("\nSet Ideal Deck Composition Counts (press Enter to accept default/current):")
        for key, prompt in bc.DECK_COMPOSITION_PROMPTS.items():
            if key not in defaults:  # skip price prompts & others for this step
                continue
            current_default = self.ideal_counts[key]
            value = self._prompt_int_with_default(f"{prompt} ", current_default, minimum=0, maximum=200)
            self.ideal_counts[key] = value

        # Basic validation adjustments
        # Ensure basic_lands <= lands
        if self.ideal_counts['basic_lands'] > self.ideal_counts['lands']:
            self.output_func("Adjusting basic lands to not exceed total lands.")
            self.ideal_counts['basic_lands'] = self.ideal_counts['lands']

        self._print_ideal_counts_summary()
        return self.ideal_counts

    # Helper to prompt integer values with default
    def _prompt_int_with_default(self, prompt: str, default: int, minimum: int = 0, maximum: int = 999) -> int:
        while True:
            raw = self.input_func(f"{prompt}[{default}] ").strip()
            if raw == "":
                return default
            if raw.isdigit():
                val = int(raw)
                if minimum <= val <= maximum:
                    return val
            self.output_func(f"Enter a number between {minimum} and {maximum}, or press Enter for {default}.")

    def _print_ideal_counts_summary(self):
        self.output_func("\nIdeal Composition Targets:")
        order = [
            ('ramp', 'Ramp Pieces'),
            ('lands', 'Total Lands'),
            ('basic_lands', 'Minimum Basic Lands'),
            ('creatures', 'Creatures'),
            ('removal', 'Spot Removal'),
            ('wipes', 'Board Wipes'),
            ('card_advantage', 'Card Advantage'),
            ('protection', 'Protection')
        ]
        width = max(len(label) for _, label in order)
        for key, label in order:
            if key in self.ideal_counts:
                self.output_func(f"  {label.ljust(width)} : {self.ideal_counts[key]}")

    # Public wrapper for external callers / tests
    def print_ideal_counts(self):
        if not self.ideal_counts:
            self.output_func("Ideal counts not set. Run run_deck_build_step2() first.")
            return
        # Reuse formatting but with a simpler heading per user request
        self.output_func("\nIdeal Counts:")
        order = [
            ('ramp', 'Ramp'),
            ('lands', 'Total Lands'),
            ('basic_lands', 'Basic Lands (Min)'),
            ('creatures', 'Creatures'),
            ('removal', 'Spot Removal'),
            ('wipes', 'Board Wipes'),
            ('card_advantage', 'Card Advantage'),
            ('protection', 'Protection')
        ]
        width = max(len(label) for _, label in order)
        for key, label in order:
            if key in self.ideal_counts:
                self.output_func(f"  {label.ljust(width)} : {self.ideal_counts[key]}")

    # (Basic land logic moved to LandBasicsMixin in phases/phase2_lands_basics.py)

    # ---------------------------
    # Land Building Step 2: Staple Nonbasic Lands (NO Kindred yet)
    # ---------------------------
    def _current_land_count(self) -> int:
        """Return total number of land cards currently in the library (counts duplicates)."""
        total = 0
        for name, entry in self.card_library.items():
            # If we recorded type when adding basics or staples, use that
            ctype = entry.get('Card Type', '')
            if ctype and 'land' in ctype.lower():
                total += entry.get('Count', 1)
                continue
            # Else attempt enrichment from combined pool
            if self._combined_cards_df is not None and 'name' in self._combined_cards_df.columns:
                row = self._combined_cards_df[self._combined_cards_df['name'] == name]
                if not row.empty:
                    type_field = str(row.iloc[0].get('type', '')).lower()
                    if 'land' in type_field:
                        total += entry.get('Count', 1)
        return total

    # (Staple land logic moved to LandStaplesMixin in phases/phase2_lands_staples.py)

    # ---------------------------
    # Land Building Step 3: Kindred / Creature-Type Focused Lands
    # ---------------------------
    # (Kindred land logic moved to LandKindredMixin in phases/phase2_lands_kindred.py)

    # (Fetch land logic moved to LandFetchMixin in phases/phase2_lands_fetch.py)

    # ---------------------------
    # Internal Helper: Basic Land Floor
    # ---------------------------
    def _basic_floor(self, min_basic_cfg: int) -> int:
        """Return the minimum number of basics we will not trim below.

        Currently defined as ceil(bc.BASIC_FLOOR_FACTOR * configured_basic_count). Centralizing here so
        future tuning (e.g., dynamic by color count, bracket, or pip distribution) only
        needs a single change. min_basic_cfg already accounts for ideal_counts override.
        """
        try:
            return max(0, int(math.ceil(bc.BASIC_FLOOR_FACTOR * float(min_basic_cfg))))
        except Exception:
            return max(0, min_basic_cfg)

    # ---------------------------
    # Land Building Step 5: Dual Lands (Two-Color Typed Lands)
    # ---------------------------
    # (Dual land logic moved to LandDualsMixin in phases/phase2_lands_duals.py)

    # ---------------------------
    # Land Building Step 6: Triple (Tri-Color) Typed Lands
    # ---------------------------
    def add_triple_lands(self, requested_count: Optional[int] = None):
        """Add three-color typed lands (e.g., Triomes) respecting land target and basic floor.

        Logic parallels add_dual_lands but restricted to lands whose type line contains exactly
        three distinct basic land types that are all within the deck's color identity.
        Selection aims for 1-2 (default) with weighted random ordering among viable tri-color combos
        to avoid always choosing the same land when multiple exist.
        """
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add triple lands until color identity resolved: {e}")
                return
        colors = [c for c in self.color_identity if c in ['W','U','B','R','G']]
        if len(colors) < 3:
            self.output_func("Triple Lands: Fewer than three colors; skipping step 6.")
            return

        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        df = self._combined_cards_df
        pool: list[str] = []
        type_map: dict[str,str] = {}
        tri_buckets: dict[frozenset[str], list[str]] = {}
        if df is not None and not df.empty and {'name','type'}.issubset(df.columns):
            try:
                for _, row in df.iterrows():
                    try:
                        name = str(row.get('name',''))
                        if not name or name in self.card_library:
                            continue
                        tline = str(row.get('type','')).lower()
                        if 'land' not in tline:
                            continue
                        basics_found = [b for b in ['plains','island','swamp','mountain','forest'] if b in tline]
                        uniq_basics = []
                        for b in basics_found:
                            if b not in uniq_basics:
                                uniq_basics.append(b)
                        if len(uniq_basics) != 3:
                            continue
                        mapped = set()
                        for b in uniq_basics:
                            if b == 'plains':
                                mapped.add('W')
                            elif b == 'island':
                                mapped.add('U')
                            elif b == 'swamp':
                                mapped.add('B')
                            elif b == 'mountain':
                                mapped.add('R')
                            elif b == 'forest':
                                mapped.add('G')
                        if len(mapped) != 3:
                            continue
                        if not mapped.issubset(set(colors)):
                            continue
                        pool.append(name)
                        type_map[name] = tline
                        key = frozenset(mapped)
                        tri_buckets.setdefault(key, []).append(name)
                    except Exception:
                        continue
            except Exception:
                pass
        pool = list(dict.fromkeys(pool))
        if not pool:
            self.output_func("Triple Lands: No candidate triple typed lands found.")
            return

        # Rank tri lands: those that can enter untapped / have cycling / fetchable (heuristic), else default
        def rank(name: str) -> int:
            lname = name.lower()
            tline = type_map.get(name,'')
            score = 0
            # Triomes & similar premium typed tri-lands
            if 'forest' in tline and 'plains' in tline and 'island' in tline:
                score += 1  # minor bump per type already inherent; focus on special abilities
            if 'cycling' in tline:
                score += 3
            if 'enters the battlefield tapped' not in tline:
                score += 5
            if 'trium' in lname or 'triome' in lname or 'panorama' in lname:
                score += 4
            if 'domain' in tline:
                score += 1
            return score
        for key, names in tri_buckets.items():
            names.sort(key=lambda n: rank(n), reverse=True)
            if len(names) > 1:
                rng_obj = getattr(self, 'rng', None)
                try:
                    weighted = [(n, max(1, rank(n))+1) for n in names]
                    shuffled: list[str] = []
                    while weighted:
                        total = sum(w for _, w in weighted)
                        r = (rng_obj.random() if rng_obj else self._get_rng().random()) * total
                        acc = 0.0
                        for idx, (n, w) in enumerate(weighted):
                            acc += w
                            if r <= acc:
                                shuffled.append(n)
                                del weighted[idx]
                                break
                    tri_buckets[key] = shuffled
                except Exception:
                    tri_buckets[key] = names
            else:
                tri_buckets[key] = names
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        default_triple_target = getattr(bc, 'TRIPLE_LAND_DEFAULT_COUNT', 2)
        remaining_capacity = max(0, land_target - self._current_land_count())
        effective_default = min(default_triple_target, remaining_capacity if remaining_capacity>0 else len(pool), len(pool))
        desired = effective_default if requested_count is None else max(0, int(requested_count))
        if desired == 0:
            self.output_func("Triple Lands: Desired count 0; skipping.")
            return
        if remaining_capacity == 0 and desired > 0:
            slots_needed = desired
            freed = 0
            while freed < slots_needed and self._count_basic_lands() > basic_floor:
                target_basic = self._choose_basic_to_trim()
                if not target_basic or not self._decrement_card(target_basic):
                    break
                freed += 1
            if freed == 0:
                desired = 0
        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(pool))
        if desired <= 0:
            self.output_func("Triple Lands: No capacity after trimming; skipping.")
            return

        chosen: list[str] = []
        bucket_keys = list(tri_buckets.keys())
        rng = getattr(self, 'rng', None)
        try:
            if rng:
                rng.shuffle(bucket_keys)  # type: ignore
            else:
                random.shuffle(bucket_keys)
        except Exception:
            pass
        indices = {k:0 for k in bucket_keys}
        while len(chosen) < desired and bucket_keys:
            progressed = False
            for k in list(bucket_keys):
                idx = indices[k]
                names = tri_buckets.get(k, [])
                if idx >= len(names):
                    continue
                name = names[idx]
                indices[k] += 1
                if name in chosen:
                    continue
                chosen.append(name)
                progressed = True
                if len(chosen) >= desired:
                    break
            if not progressed:
                break

        added: list[str] = []
        for name in chosen:
            if self._current_land_count() >= land_target:
                break
            self.add_card(name, card_type='Land')
            added.append(name)

        self.output_func("\nTriple Lands Added (Step 6):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step6(self, requested_count: Optional[int] = None):
        self.add_triple_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Triples (Step 6)")

    # ---------------------------
    # Land Building Step 7: Misc / Utility Lands
    # ---------------------------
    # (Misc utility land logic moved to LandMiscUtilityMixin in phases/phase2_lands_misc.py)
    # (Tapped land optimization moved to LandOptimizationMixin in phases/phase2_lands_optimize.py)

    # ---------------------------
    # Tag-driven utility suggestions
    # ---------------------------
    def _build_tag_driven_land_suggestions(self):
        
        # Delegate construction of suggestion dicts to utility module.
        suggestions = bu.build_tag_driven_suggestions(self)
        if suggestions:
            self.suggested_lands_queue.extend(suggestions)

    def _apply_land_suggestions_if_room(self):
        if not self.suggested_lands_queue:
            return
        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        applied: list[dict] = []
        remaining: list[dict] = []
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)
        for sug in self.suggested_lands_queue:
            name = sug['name']
            if name in self.card_library:
                continue
            if not sug['condition'](self):
                remaining.append(sug)
                continue
            if self._current_land_count() >= land_target:
                if sug.get('defer_if_full'):
                    if self._count_basic_lands() > basic_floor:
                        target_basic = self._choose_basic_to_trim()
                        if not target_basic or not self._decrement_card(target_basic):
                            remaining.append(sug)
                            continue
                    else:
                        remaining.append(sug)
                        continue
            self.add_card(name, card_type='Land')
            if sug.get('flex') and name in self.card_library:
                self.card_library[name]['Role'] = 'flex'
            applied.append(sug)
        self.suggested_lands_queue = remaining
        if applied:
            self.output_func("\nTag-Driven Utility Lands Added:")
            width = max(len(s['name']) for s in applied)
            for s in applied:
                role = ' (flex)' if s.get('flex') else ''
                self.output_func(f"  {s['name'].ljust(width)} : 1  {s['reason']}{role}")

    # ---------------------------
    # (Color balance helpers & post-spell adjustment moved to ColorBalanceMixin)

    # ---------------------------
    # Land Cap Enforcement (applies after every non-basic step)
    # ---------------------------
    def _basic_land_names(self) -> set:
        """Return set of all basic (and snow basic) land names plus Wastes."""
        
        return bu.basic_land_names()

    def _count_basic_lands(self) -> int:
        """Count total copies of basic lands currently in the library."""
        
        return bu.count_basic_lands(self.card_library)

    def _choose_basic_to_trim(self) -> Optional[str]:
        """Return a basic land name to trim (highest count) or None."""
        
        return bu.choose_basic_to_trim(self.card_library)

    def _decrement_card(self, name: str) -> bool:
        entry = self.card_library.get(name)
        if not entry:
            return False
        cnt = entry.get('Count', 1)
        was_land = 'land' in str(entry.get('Card Type','')).lower()
        was_non_land = not was_land
        if cnt <= 1:
            # remove entire entry
            try:
                del self.card_library[name]
            except Exception:
                return False
        else:
            entry['Count'] = cnt - 1
        if was_land:
            self._color_source_cache_dirty = True
        if was_non_land:
            self._spell_pip_cache_dirty = True
        return True

    def _enforce_land_cap(self, step_label: str = ""):
        """Delegate land cap enforcement to utility helper."""
        
        bu.enforce_land_cap(self, step_label)

    # ===========================
    # Non-Land Addition: Creatures (moved to CreatureAdditionMixin)
    # ===========================
    # Implementation now in phases/phase3_creatures.py (CreatureAdditionMixin)

    # Non-Creature Additions (moved to SpellAdditionMixin)
    # Implementations now located in phases/phase4_spells.py (SpellAdditionMixin)

    # (Type summary now provided by ReportingMixin)

    # ---------------------------
    # Card Library Reporting
    # ---------------------------
    # (CSV export now provided by ReportingMixin)

    # (Card library printing & tag summary now provided by ReportingMixin)

    # Internal helper for wrapping cell contents to keep table readable
    # (_wrap_cell helper moved to ReportingMixin)

    # Convenience to run Step 1 & 2 sequentially (future orchestrator)
    def run_deck_build_steps_1_2(self):
        self.run_deck_build_step1()
        self.run_deck_build_step2()
