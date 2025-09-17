from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple, Set
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
# Include/exclude utilities (M1: Config + Validation + Persistence)
from .include_exclude_utils import (
    IncludeExcludeDiagnostics,
    fuzzy_match_card_name,
    validate_list_sizes,
    collapse_duplicates
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
import os
from settings import CSV_DIRECTORY
from file_setup.setup import initial_setup

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
class DeckBuilder(
    CommanderSelectionMixin,
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
    ReportingMixin
):
    # Seedable RNG support (minimal surface area):
    # - seed: optional seed value stored for diagnostics
    # - _rng: internal Random instance; access via self.rng
    seed: Optional[int] = field(default=None, repr=False)
    _rng: Any = field(default=None, repr=False)

    @property
    def rng(self):
        """Lazy, per-builder RNG instance. If a seed was set, use it deterministically."""
        if self._rng is None:
            try:
                # If a seed was assigned pre-init, use it
                if self.seed is not None:
                    # Import here to avoid any heavy import cycles at module import time
                    from random_util import set_seed as _set_seed  # type: ignore
                    self._rng = _set_seed(int(self.seed))
                else:
                    self._rng = random.Random()
            except Exception:
                # Fallback to module random
                self._rng = random
        return self._rng

    def set_seed(self, seed: int | str) -> None:
        """Set deterministic seed for this builder and reset its RNG instance."""
        try:
            from random_util import derive_seed_from_string as _derive, set_seed as _set_seed  # type: ignore
            s = _derive(seed)
            self.seed = int(s)
            self._rng = _set_seed(s)
        except Exception:
            try:
                self.seed = int(seed) if not isinstance(seed, int) else seed
                r = random.Random()
                r.seed(self.seed)
                self._rng = r
            except Exception:
                # Leave RNG as-is on unexpected error
                pass
    def build_deck_full(self):
        """Orchestrate the full deck build process, chaining all major phases."""
        start_ts = datetime.datetime.now()
        logger.info("=== Deck Build: BEGIN ===")
        try:
            # Ensure CSVs exist and are tagged before starting any deck build logic
            try:
                import time as _time
                import json as _json
                from datetime import datetime as _dt
                cards_path = os.path.join(CSV_DIRECTORY, 'cards.csv')
                flag_path = os.path.join(CSV_DIRECTORY, '.tagging_complete.json')
                refresh_needed = False
                if not os.path.exists(cards_path):
                    logger.info("cards.csv not found. Running initial setup and tagging before deck build...")
                    refresh_needed = True
                else:
                    try:
                        age_seconds = _time.time() - os.path.getmtime(cards_path)
                        if age_seconds > 7 * 24 * 60 * 60:
                            logger.info("cards.csv is older than 7 days. Refreshing data before deck build...")
                            refresh_needed = True
                    except Exception:
                        pass
                if not os.path.exists(flag_path):
                    logger.info("Tagging completion flag not found. Performing full tagging before deck build...")
                    refresh_needed = True
                if refresh_needed:
                    initial_setup()
                    from tagging import tagger as _tagger
                    _tagger.run_tagging()
                    try:
                        os.makedirs(CSV_DIRECTORY, exist_ok=True)
                        with open(flag_path, 'w', encoding='utf-8') as _fh:
                            _json.dump({'tagged_at': _dt.now().isoformat(timespec='seconds')}, _fh)
                    except Exception:
                        logger.warning("Failed to write tagging completion flag (non-fatal).")
            except Exception as e:
                logger.error(f"Failed ensuring CSVs before deck build: {e}")
            self.run_initial_setup()
            self.run_deck_build_step1()
            self.run_deck_build_step2()
            self._run_land_build_steps()
            # M2: Inject includes after lands, before creatures/spells
            logger.info(f"DEBUG BUILD: About to inject includes. Include cards: {self.include_cards}")
            self._inject_includes_after_lands()
            logger.info(f"DEBUG BUILD: Finished injecting includes. Current deck size: {len(self.card_library)}")
            if hasattr(self, 'add_creatures_phase'):
                self.add_creatures_phase()
            if hasattr(self, 'add_spells_phase'):
                self.add_spells_phase()
            if hasattr(self, 'post_spell_land_adjust'):
                self.post_spell_land_adjust()
            # Modular reporting phase
            if hasattr(self, 'run_reporting_phase'):
                self.run_reporting_phase()
            # Immediately after content additions and summary, if compliance is enforced later,
            # we want to display what would be swapped. For interactive runs, surface a dry prompt.
            try:
                # Compute a quick compliance snapshot here to hint at upcoming enforcement
                if hasattr(self, 'compute_and_print_compliance') and not getattr(self, 'headless', False):
                    from deck_builder.brackets_compliance import evaluate_deck as _eval  # type: ignore
                    bracket_key = str(getattr(self, 'bracket_name', '') or getattr(self, 'bracket_level', 'core')).lower()
                    commander = getattr(self, 'commander_name', None)
                    snap = _eval(self.card_library, commander_name=commander, bracket=bracket_key)
                    if snap.get('overall') == 'FAIL':
                        self.output_func("\nNote: Limits exceeded. You'll get a chance to review swaps next.")
            except Exception:
                pass
            if hasattr(self, 'export_decklist_csv'):
                # If user opted out of owned-only, silently load all owned files for marking
                try:
                    if not self.use_owned_only and not self.owned_card_names:
                        self._load_all_owned_silent()
                except Exception:
                    pass
                csv_path = self.export_decklist_csv()
                try:
                    import os as _os
                    base, _ext = _os.path.splitext(_os.path.basename(csv_path))
                    txt_path = self.export_decklist_text(filename=base + '.txt')  # type: ignore[attr-defined]
                    # Display the text file contents for easy copy/paste to online deck builders
                    self._display_txt_contents(txt_path)
                    # Compute bracket compliance and save a JSON report alongside exports
                    try:
                        if hasattr(self, 'compute_and_print_compliance'):
                            report0 = self.compute_and_print_compliance(base_stem=base)  # type: ignore[attr-defined]
                            # If non-compliant and interactive, offer enforcement now
                            try:
                                if isinstance(report0, dict) and report0.get('overall') == 'FAIL' and not getattr(self, 'headless', False):
                                    from deck_builder.phases.phase6_reporting import ReportingMixin as _RM  # type: ignore
                                    if isinstance(self, _RM) and hasattr(self, 'enforce_and_reexport'):
                                        self.output_func("One or more bracket limits exceeded. Enter to auto-resolve, or Ctrl+C to skip.")
                                        try:
                                            _ = self.input_func("")
                                        except Exception:
                                            pass
                                        self.enforce_and_reexport(base_stem=base, mode='prompt')  # type: ignore[attr-defined]
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # If owned-only build is incomplete, generate recommendations
                    try:
                        total_cards = sum(int(v.get('Count', 1)) for v in self.card_library.values())
                        if self.use_owned_only and total_cards < 100:
                            missing = 100 - total_cards
                            rec_limit = int(math.ceil(1.5 * float(missing)))
                            self._generate_recommendations(base_stem=base, limit=rec_limit)
                    except Exception:
                        pass
                    # Also export a matching JSON config for replay (interactive builds only)
                    if not getattr(self, 'headless', False):
                        try:
                            # Choose config output dir: DECK_CONFIG dir > /app/config > ./config
                            import os as _os
                            cfg_path_env = _os.getenv('DECK_CONFIG')
                            cfg_dir = None
                            if cfg_path_env:
                                cfg_dir = _os.path.dirname(cfg_path_env) or '.'
                            elif _os.path.isdir('/app/config'):
                                cfg_dir = '/app/config'
                            else:
                                cfg_dir = 'config'
                            if cfg_dir:
                                _os.makedirs(cfg_dir, exist_ok=True)
                                self.export_run_config_json(directory=cfg_dir, filename=base + '.json')  # type: ignore[attr-defined]
                            # Also, if DECK_CONFIG explicitly points to a file path, write exactly there too
                            if cfg_path_env:
                                cfg_dir2 = _os.path.dirname(cfg_path_env) or '.'
                                cfg_name2 = _os.path.basename(cfg_path_env)
                                _os.makedirs(cfg_dir2, exist_ok=True)
                                self.export_run_config_json(directory=cfg_dir2, filename=cfg_name2)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    logger.warning("Plaintext export failed (non-fatal)")
            # If owned-only and deck not complete, print a note
            try:
                if self.use_owned_only:
                    total_cards = sum(int(v.get('Count', 1)) for v in self.card_library.values())
                    if total_cards < 100:
                        self.output_func(f"Note: deck is incomplete ({total_cards}/100). Not enough owned cards to fill the deck.")
            except Exception:
                pass
            end_ts = datetime.datetime.now()
            logger.info(f"=== Deck Build: COMPLETE in {(end_ts - start_ts).total_seconds():.2f}s ===")
        except KeyboardInterrupt:
            logger.warning("Deck build cancelled by user (KeyboardInterrupt).")
            self.output_func("\nDeck build cancelled by user.")
        except Exception as e:
            logger.exception("Deck build failed with exception")
            self.output_func(f"Deck build failed: {e}")

    def _display_txt_contents(self, txt_path: str):
        """Display the contents of the exported .txt file for easy copy/paste to online deck builders."""
        try:
            import os
            if not os.path.exists(txt_path):
                self.output_func("Warning: Text file not found for display.")
                return
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                contents = f.read().strip()
            
            if not contents:
                self.output_func("Warning: Text file is empty.")
                return
            
            # Create a nice display format
            filename = os.path.basename(txt_path)
            separator = "=" * 60
            
            self.output_func(f"\n{separator}")
            self.output_func(f"DECK LIST - {filename}")
            self.output_func("Ready for copy/paste to Moxfield, EDHREC, or other deck builders")
            self.output_func(f"{separator}")
            self.output_func(contents)
            # self.output_func(f"{separator}")
            # self.output_func(f"Deck list also saved to: {txt_path}")
            self.output_func(f"{separator}\n")
            
        except Exception as e:
            logger.warning(f"Failed to display text file contents: {e}")
            self.output_func(f"Warning: Could not display deck list contents. Check {txt_path} manually.")

    def add_creatures_phase(self):
        """Run the creature addition phase (delegated to CreatureAdditionMixin)."""
        if hasattr(super(), 'add_creatures_phase'):
            return super().add_creatures_phase()
        raise NotImplementedError("Creature addition phase not implemented.")

    def add_spells_phase(self):
        """Run the spell addition phase (delegated to SpellAdditionMixin)."""
        if hasattr(super(), 'add_spells_phase'):
            return super().add_spells_phase()
        raise NotImplementedError("Spell addition phase not implemented.")
    # ---------------------------
    # Lightweight confirmations (CLI pauses; web auto-continues)
    # ---------------------------
    def _pause(self, message: str = "Press Enter to continue...") -> None:
        try:
            _ = self.input_func(message)
        except Exception:
            pass

    def confirm_primary_theme(self) -> None:
        if getattr(self, 'primary_tag', None):
            self.output_func(f"Primary Theme: {self.primary_tag}")
        self._pause()

    def confirm_secondary_theme(self) -> None:
        if getattr(self, 'secondary_tag', None):
            self.output_func(f"Secondary Theme: {self.secondary_tag}")
        self._pause()

    def confirm_tertiary_theme(self) -> None:
        if getattr(self, 'tertiary_tag', None):
            self.output_func(f"Tertiary Theme: {self.tertiary_tag}")
        self._pause()

    def confirm_ramp_spells(self) -> None:
        self.output_func("Confirm Ramp")
        self._pause()

    def confirm_removal_spells(self) -> None:
        self.output_func("Confirm Removal")
        self._pause()

    def confirm_wipes_spells(self) -> None:
        self.output_func("Confirm Board Wipes")
        self._pause()

    def confirm_card_advantage_spells(self) -> None:
        self.output_func("Confirm Card Advantage")
        self._pause()

    def confirm_protection_spells(self) -> None:
        self.output_func("Confirm Protection")
        self._pause()
    # Commander core selection state
    commander_name: str = ""
    commander_row: Optional[pd.Series] = None
    commander_tags: List[str] = field(default_factory=list)

    # Tag prioritization
    primary_tag: Optional[str] = None
    secondary_tag: Optional[str] = None
    tertiary_tag: Optional[str] = None
    selected_tags: List[str] = field(default_factory=list)
    # How to combine multiple selected tags when prioritizing cards: 'AND' or 'OR'
    tag_mode: str = 'AND'

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
    # Owned-cards mode
    use_owned_only: bool = False
    owned_card_names: set[str] = field(default_factory=set)
    owned_files_selected: List[str] = field(default_factory=list)
    # Soft preference: bias selection toward owned names without excluding others
    prefer_owned: bool = False

    # Include/Exclude Cards (M1: Full Configuration Support)
    include_cards: List[str] = field(default_factory=list)
    exclude_cards: List[str] = field(default_factory=list)
    enforcement_mode: str = "warn"  # "warn" | "strict"
    allow_illegal: bool = False
    fuzzy_matching: bool = True
    # Diagnostics storage for include/exclude processing
    include_exclude_diagnostics: Optional[Dict[str, Any]] = None

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
    # Random support (no external seeding)
    _rng: Any = field(default=None, repr=False)

    # Logging / output behavior
    log_outputs: bool = True  # if True, mirror output_func messages into logger at INFO level
    _original_output_func: Optional[Callable[[str], None]] = field(default=None, repr=False)

    # Chosen land counts (only fetches are tracked/exported; others vary randomly)
    fetch_count: Optional[int] = None
    # Whether this build is running in headless mode (suppress some interactive-only exports)
    headless: bool = False

    def __post_init__(self):
        """Post-init hook to wrap the provided output function so that all user-facing
        messages are also captured in the central log (at INFO level) unless disabled.
        """
        if self.log_outputs:
            # Preserve original
            self._original_output_func = self.output_func

            def _wrapped(msg: str):
                # Collapse excessive blank lines for log readability, but keep printing original
                log_msg = msg.rstrip()
                if log_msg:
                    logger.info(log_msg)
                self._original_output_func(msg)

            self.output_func = _wrapped

    def _run_land_build_steps(self):
        """Run all land build steps (1-8) in order, logging progress."""
        for step in range(1, 9):
            m = getattr(self, f"run_land_step{step}", None)
            if callable(m):
                logger.info(f"Land Step {step}: begin")
                m()
                logger.info(f"Land Step {step}: complete (current land count {self._current_land_count() if hasattr(self, '_current_land_count') else 'n/a'})")

    def _generate_recommendations(self, base_stem: str, limit: int):
        """Silently build a full (non-owned-filtered) deck with same choices and export top recommendations.

        - Uses same commander, tags, bracket, and ideal_counts.
        - Excludes any cards already in this deck's library.
        - Exports CSV and TXT to deck_files with suffix _recommendations.
        """
        try:
            # Nothing to recommend if limit <= 0 or no commander
            if limit <= 0 or not self.commander_row is not None:
                return
            # Prepare a quiet builder
            def _silent_out(_msg: str) -> None:
                return None
            def _silent_in(_prompt: str) -> str:
                return ""
            rec = DeckBuilder(input_func=_silent_in, output_func=_silent_out, log_outputs=False, headless=True)
            # Carry over selections
            rec.commander_name = self.commander_name
            rec.commander_row = self.commander_row
            rec.commander_tags = list(self.commander_tags)
            rec.primary_tag = self.primary_tag
            rec.secondary_tag = self.secondary_tag
            rec.tertiary_tag = self.tertiary_tag
            rec.selected_tags = list(self.selected_tags)
            rec.bracket_definition = self.bracket_definition
            rec.bracket_level = self.bracket_level
            rec.bracket_name = self.bracket_name
            rec.bracket_limits = dict(self.bracket_limits) if self.bracket_limits else {}
            rec.ideal_counts = dict(self.ideal_counts) if self.ideal_counts else {}
            # Initialize commander dict (also adds commander to library)
            try:
                if rec.commander_row is not None:
                    rec._initialize_commander_dict(rec.commander_row)
            except Exception:
                pass
            # Build on full pool (owned-only disabled by default)
            rec.determine_color_identity()
            rec.setup_dataframes()
            # Ensure bracket applied and counts present
            try:
                rec.run_deck_build_step1()
            except Exception:
                pass
            # Run the content-adding phases silently
            try:
                rec._run_land_build_steps()
            except Exception:
                pass
            try:
                if hasattr(rec, 'add_creatures_phase'):
                    rec.add_creatures_phase()
            except Exception:
                pass
            try:
                if hasattr(rec, 'add_spells_phase'):
                    rec.add_spells_phase()
            except Exception:
                pass
            try:
                if hasattr(rec, 'post_spell_land_adjust'):
                    rec.post_spell_land_adjust()
            except Exception:
                pass

            # Build recommendation subset excluding already-chosen names
            chosen = set(self.card_library.keys())
            rec_items = []
            for nm, info in rec.card_library.items():
                if nm not in chosen:
                    rec_items.append((nm, info))
            if not rec_items:
                return
            # Cap to requested limit
            rec_subset: Dict[str, Dict[str, Any]] = {}
            for nm, info in rec_items[:max(0, int(limit))]:
                rec_subset[nm] = info

            # Temporarily export subset using the recommendation builder's context/snapshots
            original_lib = rec.card_library
            try:
                rec.card_library = rec_subset
                # Export CSV and TXT with suffix
                rec.export_decklist_csv(directory='deck_files', filename=base_stem + '_recommendations.csv', suppress_output=True)  # type: ignore[attr-defined]
                rec.export_decklist_text(directory='deck_files', filename=base_stem + '_recommendations.txt', suppress_output=True)  # type: ignore[attr-defined]
            finally:
                rec.card_library = original_lib
            # Notify user succinctly
            try:
                self.output_func(f"Recommended but unowned cards in deck_files/{base_stem}_recommendations.csv")
            except Exception:
                pass
        except Exception as _e:
            try:
                self.output_func(f"Failed to generate recommendations: {_e}")
            except Exception:
                pass

    # ---------------------------
    # Owned Cards Helpers
    # ---------------------------
    def _card_library_dir(self) -> str:
        """Return folder to read owned cards from, preferring 'owned_cards'.

        Precedence:
        - OWNED_CARDS_DIR env var
        - CARD_LIBRARY_DIR env var (back-compat)
        - 'owned_cards' if exists
        - 'card_library' if exists (back-compat)
        - default 'owned_cards'
        """
        try:
            import os as _os
            # Env overrides
            env_dir = _os.getenv('OWNED_CARDS_DIR') or _os.getenv('CARD_LIBRARY_DIR')
            if env_dir:
                return env_dir
            # Prefer new name
            if _os.path.isdir('owned_cards'):
                return 'owned_cards'
            if _os.path.isdir('card_library'):
                return 'card_library'
            return 'owned_cards'
        except Exception:
            return 'owned_cards'

    def _find_owned_files(self) -> List[str]:
        import os as _os
        folder = self._card_library_dir()
        try:
            entries = []
            if _os.path.isdir(folder):
                for name in _os.listdir(folder):
                    p = _os.path.join(folder, name)
                    if _os.path.isfile(p) and name.lower().endswith(('.txt', '.csv')):
                        entries.append(p)
            return sorted(entries)
        except Exception:
            return []

    def _parse_owned_line(self, line: str) -> Optional[str]:
        s = (line or '').strip()
        if not s or s.startswith('#') or s.startswith('//'):
            return None
        parts = s.split()
        if len(parts) >= 2 and (parts[0].isdigit() or (parts[0].lower().endswith('x') and parts[0][:-1].isdigit())):
            s = ' '.join(parts[1:])
        return s.strip() or None

    def _read_txt_owned(self, path: str) -> List[str]:
        out: List[str] = []
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    n = self._parse_owned_line(line)
                    if n:
                        out.append(n)
        except Exception:
            pass
        return out

    def _read_csv_owned(self, path: str) -> List[str]:
        import csv as _csv
        names: List[str] = []
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore', newline='') as f:
                try:
                    reader = _csv.DictReader(f)
                    headers = [h.strip() for h in (reader.fieldnames or [])]
                    candidates = [c for c in ('name', 'card', 'Card', 'card_name', 'Card Name') if c in headers]
                    if candidates:
                        key = candidates[0]
                        for row in reader:
                            val = (row.get(key) or '').strip()
                            if val:
                                names.append(val)
                    else:
                        f.seek(0)
                        reader2 = _csv.reader(f)
                        for row in reader2:
                            if not row:
                                continue
                            val = (row[0] or '').strip()
                            if val and val.lower() not in ('name', 'card', 'card name'):
                                names.append(val)
                except Exception:
                    # Fallback plain reader
                    f.seek(0)
                    for line in f:
                        if line.strip():
                            names.append(line.strip())
        except Exception:
            pass
        return names

    def _load_owned_from_files(self, files: List[str]) -> set[str]:
        names: List[str] = []
        for p in files:
            pl = p.lower()
            try:
                if pl.endswith('.txt'):
                    names.extend(self._read_txt_owned(p))
                elif pl.endswith('.csv'):
                    names.extend(self._read_csv_owned(p))
            except Exception:
                continue
        clean = {n.strip() for n in names if isinstance(n, str) and n.strip()}
        return clean

    def _prompt_use_owned_cards(self):
        # Quick existence check: only prompt if any owned files are present
        files = self._find_owned_files()
        if not files:
            # No owned lists present; skip prompting entirely
            return
        resp = self.input_func("Use only owned cards? (y/N): ").strip().lower()
        self.use_owned_only = (resp in ('y', 'yes'))
        if not self.use_owned_only:
            return
        self.output_func("Select owned card files by number (comma-separated), or press Enter to use all:")
        for i, p in enumerate(files):
            try:
                base = p.replace('\\', '/').split('/')[-1]
            except Exception:
                base = p
            self.output_func(f"  [{i}] {base}")
        raw = self.input_func("Selection: ").strip()
        selected: List[str] = []
        if not raw:
            selected = files
        else:
            seen = set()
            for tok in raw.split(','):
                tok = tok.strip()
                if tok.isdigit():
                    idx = int(tok)
                    if 0 <= idx < len(files) and idx not in seen:
                        selected.append(files[idx])
                        seen.add(idx)
        if not selected:
            self.output_func("No valid selections; using all owned files.")
            selected = files
        self.owned_files_selected = selected
        self.owned_card_names = self._load_owned_from_files(selected)
        self.output_func(f"Owned cards loaded: {len(self.owned_card_names)} unique names from {len(selected)} file(s).")

    # Public helper for headless/tests: enable/disable owned-only and optionally preload files
    def set_owned_mode(self, owned_only: bool, files: Optional[List[str]] = None):
        self.use_owned_only = bool(owned_only)
        if not self.use_owned_only:
            self.owned_card_names = set()
            self.owned_files_selected = []
            return
        if files is None:
            return
        # Normalize to existing files
        valid: List[str] = []
        for p in files:
            try:
                if os.path.isfile(p) and p.lower().endswith(('.txt', '.csv')):
                    valid.append(p)
                else:
                    # try relative to card_library
                    alt = os.path.join(self._card_library_dir(), p)
                    if os.path.isfile(alt) and alt.lower().endswith(('.txt', '.csv')):
                        valid.append(alt)
            except Exception:
                continue
        if valid:
            self.owned_files_selected = valid
            self.owned_card_names = self._load_owned_from_files(valid)

    # Internal helper: when user opts out, silently load all owned files for CSV flagging
    def _load_all_owned_silent(self):
        try:
            files = self._find_owned_files()
            if not files:
                return
            self.owned_files_selected = files
            self.owned_card_names = self._load_owned_from_files(files)
        except Exception:
            pass

    # ---------------------------
    # RNG Initialization
    # ---------------------------
    def _get_rng(self):  # lazy init
        # Delegate to seedable rng property for determinism support
        return self.rng

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
        from path_util import csv_dir as _csv_dir
        base = _csv_dir()
        for stem in self.files_to_load:
            path = f"{base}/{stem}_cards.csv"
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
        # If owned-only mode, filter combined pool to owned names (case-insensitive)
        if self.use_owned_only:
            try:
                owned_lower = {n.lower() for n in self.owned_card_names}
                name_col = None
                if 'name' in combined.columns:
                    name_col = 'name'
                elif 'Card Name' in combined.columns:
                    name_col = 'Card Name'
                if name_col is not None:
                    mask = combined[name_col].astype(str).str.lower().isin(owned_lower)
                    prev = len(combined)
                    combined = combined[mask].copy()
                    self.output_func(f"Owned-only mode: filtered card pool from {prev} to {len(combined)} records.")
                else:
                    self.output_func("Owned-only mode: no recognizable name column to filter on; skipping filter.")
            except Exception as _e:
                self.output_func(f"Owned-only mode: failed to filter combined pool: {_e}")
    # Soft prefer-owned does not filter the pool; biasing is applied later at selection time
        
        # Apply exclude card filtering (M0.5: Phase 1 - Exclude Only)
        if hasattr(self, 'exclude_cards') and self.exclude_cards:
            try:
                import time  # M5: Performance monitoring
                exclude_start_time = time.perf_counter()
                
                from deck_builder.include_exclude_utils import normalize_punctuation
                
                # Find name column
                name_col = None
                if 'name' in combined.columns:
                    name_col = 'name'
                elif 'Card Name' in combined.columns:
                    name_col = 'Card Name'
                    
                if name_col is not None:
                    excluded_matches = []
                    original_count = len(combined)
                    
                    # Normalize exclude patterns for matching (with punctuation normalization)
                    normalized_excludes = {normalize_punctuation(pattern): pattern for pattern in self.exclude_cards}
                    
                    # Create a mask to track which rows to exclude
                    exclude_mask = pd.Series([False] * len(combined), index=combined.index)
                    
                    # Check each card against exclude patterns
                    for idx, card_name in combined[name_col].items():
                        if not exclude_mask[idx]:  # Only check if not already excluded
                            normalized_card = normalize_punctuation(str(card_name))
                            
                            # Check if this card matches any exclude pattern
                            for normalized_exclude, original_pattern in normalized_excludes.items():
                                if normalized_card == normalized_exclude:
                                    excluded_matches.append({
                                        'pattern': original_pattern,
                                        'matched_card': str(card_name),
                                        'similarity': 1.0
                                    })
                                    exclude_mask[idx] = True
                                    # M5: Structured logging for exclude decisions
                                    logger.info(f"EXCLUDE_FILTER: {card_name} (pattern: {original_pattern}, pool_stage: setup)")
                                    break  # Found a match, no need to check other patterns
                    
                    # Apply the exclusions in one operation
                    if exclude_mask.any():
                        combined = combined[~exclude_mask].copy()
                        # M5: Structured logging for exclude filtering summary
                        logger.info(f"EXCLUDE_SUMMARY: filtered={len(excluded_matches)} pool_before={original_count} pool_after={len(combined)}")
                        self.output_func(f"Excluded {len(excluded_matches)} cards from pool (was {original_count}, now {len(combined)})")
                        for match in excluded_matches[:5]:  # Show first 5 matches
                            self.output_func(f"  - Excluded '{match['matched_card']}' (pattern: '{match['pattern']}', similarity: {match['similarity']:.2f})")
                        if len(excluded_matches) > 5:
                            self.output_func(f"  - ... and {len(excluded_matches) - 5} more")
                    else:
                        # M5: Structured logging for no exclude matches
                        logger.info(f"EXCLUDE_NO_MATCHES: patterns={len(self.exclude_cards)} pool_size={original_count}")
                        self.output_func(f"No cards matched exclude patterns: {', '.join(self.exclude_cards)}")
                    
                    # M5: Performance monitoring for exclude filtering
                    exclude_duration = (time.perf_counter() - exclude_start_time) * 1000  # Convert to ms
                    logger.info(f"EXCLUDE_PERFORMANCE: duration_ms={exclude_duration:.2f} pool_size={original_count} exclude_patterns={len(self.exclude_cards)}")
                else:
                    self.output_func("Exclude mode: no recognizable name column to filter on; skipping exclude filter.")
                    # M5: Structured logging for exclude filtering issues
                    logger.warning("EXCLUDE_ERROR: no_name_column_found")
            except Exception as e:
                self.output_func(f"Exclude mode: failed to filter excluded cards: {e}")
                # M5: Structured logging for exclude filtering errors
                logger.error(f"EXCLUDE_ERROR: exception={str(e)}")
                import traceback
                self.output_func(f"Exclude traceback: {traceback.format_exc()}")
        
        self._combined_cards_df = combined
        # Preserve original snapshot for enrichment across subsequent removals
        # Note: This snapshot should also exclude filtered cards to prevent them from being accessible
        if self._full_cards_df is None:
            self._full_cards_df = combined.copy()
        return combined

    # ---------------------------
    # Include/Exclude Processing (M1: Config + Validation + Persistence)
    # ---------------------------
    def _inject_includes_after_lands(self) -> None:
        """
        M2: Inject valid include cards after land selection, before creature/spell fill.
        
        This method:
        1. Processes include/exclude lists if not already done
        2. Injects valid include cards that passed validation
        3. Tracks diagnostics for category limit overrides
        4. Ensures excluded cards cannot re-enter via downstream heuristics
        """
        # Skip if no include cards specified
        if not getattr(self, 'include_cards', None):
            return
            
        # Process includes/excludes if not already done
        if not getattr(self, 'include_exclude_diagnostics', None):
            self._process_includes_excludes()
        
        # Get validated include cards
        validated_includes = self.include_cards  # Already processed by _process_includes_excludes
        if not validated_includes:
            return
            
        # Initialize diagnostics if not present
        if not self.include_exclude_diagnostics:
            self.include_exclude_diagnostics = {}
            
        # Track cards that will be injected
        injected_cards = []
        over_ideal_tracking = {}
        
        logger.info(f"INCLUDE_INJECTION: Starting injection of {len(validated_includes)} include cards")
        
        # Inject each valid include card
        for card_name in validated_includes:
            if not card_name or card_name in self.card_library:
                continue  # Skip empty names or already added cards
                
            # Attempt to find card in available pool for metadata enrichment
            card_info = self._find_card_in_pool(card_name)
            if not card_info:
                # Card not found in pool - could be missing or already excluded
                continue
                
            # Extract metadata
            card_type = card_info.get('type', card_info.get('type_line', ''))
            mana_cost = card_info.get('mana_cost', card_info.get('manaCost', ''))
            mana_value = card_info.get('mana_value', card_info.get('manaValue', card_info.get('cmc', None)))
            creature_types = card_info.get('creatureTypes', [])
            theme_tags = card_info.get('themeTags', [])
            
            # Normalize theme tags
            if isinstance(theme_tags, str):
                theme_tags = [t.strip() for t in theme_tags.split(',') if t.strip()]
            elif not isinstance(theme_tags, list):
                theme_tags = []
                
            # Determine card category for over-ideal tracking
            category = self._categorize_card_for_limits(card_type)
            if category:
                # Check if this include would exceed ideal counts
                current_count = self._count_cards_in_category(category)
                ideal_count = getattr(self, 'ideal_counts', {}).get(category, float('inf'))
                if current_count >= ideal_count:
                    if category not in over_ideal_tracking:
                        over_ideal_tracking[category] = []
                    over_ideal_tracking[category].append(card_name)
            
            # Add the include card
            self.add_card(
                card_name=card_name,
                card_type=card_type,
                mana_cost=mana_cost,
                mana_value=mana_value,
                creature_types=creature_types,
                tags=theme_tags,
                role='include',
                added_by='include_injection'
            )
            
            injected_cards.append(card_name)
            logger.info(f"INCLUDE_ADD: {card_name} (category: {category or 'unknown'})")
            
        # Update diagnostics
        self.include_exclude_diagnostics['include_added'] = injected_cards
        self.include_exclude_diagnostics['include_over_ideal'] = over_ideal_tracking
        
        # Output summary
        if injected_cards:
            self.output_func(f"\nInclude Cards Injected ({len(injected_cards)}):")
            for card in injected_cards:
                self.output_func(f"  + {card}")
            if over_ideal_tracking:
                self.output_func("\nCategory Limit Overrides:")
                for category, cards in over_ideal_tracking.items():
                    self.output_func(f"  {category}: {', '.join(cards)}")
        else:
            self.output_func("No include cards were injected (already present or invalid)")

    def _find_card_in_pool(self, card_name: str) -> Optional[Dict[str, any]]:
        """Find a card in the current card pool and return its metadata."""
        if not card_name:
            return None
            
        # Check combined cards dataframe first
        df = getattr(self, '_combined_cards_df', None)
        if df is not None and not df.empty and 'name' in df.columns:
            matches = df[df['name'].str.lower() == card_name.lower()]
            if not matches.empty:
                return matches.iloc[0].to_dict()
        
        # Fallback to full cards dataframe if no match in combined
        df_full = getattr(self, '_full_cards_df', None)
        if df_full is not None and not df_full.empty and 'name' in df_full.columns:
            matches = df_full[df_full['name'].str.lower() == card_name.lower()]
            if not matches.empty:
                return matches.iloc[0].to_dict()
                
        return None

    def _categorize_card_for_limits(self, card_type: str) -> Optional[str]:
        """Categorize a card type for ideal count tracking."""
        if not card_type:
            return None
            
        type_lower = card_type.lower()
        
        if 'creature' in type_lower:
            return 'creatures'
        elif 'land' in type_lower:
            return 'lands'
        elif any(spell_type in type_lower for spell_type in ['instant', 'sorcery', 'enchantment', 'artifact', 'planeswalker']):
            # For spells, we could get more specific, but for now group as general spells
            return 'spells'
        else:
            return 'other'

    def _count_cards_in_category(self, category: str) -> int:
        """Count cards currently in deck library by category."""
        if not category or not self.card_library:
            return 0
            
        count = 0
        for name, entry in self.card_library.items():
            card_type = entry.get('Card Type', '')
            if not card_type:
                continue
                
            entry_category = self._categorize_card_for_limits(card_type)
            if entry_category == category:
                count += entry.get('Count', 1)
                
        return count

    def _process_includes_excludes(self) -> IncludeExcludeDiagnostics:
        """
        Process and validate include/exclude card lists with fuzzy matching.
        
        Returns:
            IncludeExcludeDiagnostics: Complete diagnostics of processing results
        """
        import time  # M5: Performance monitoring
        process_start_time = time.perf_counter()
        
        # Initialize diagnostics
        diagnostics = IncludeExcludeDiagnostics(
            missing_includes=[],
            ignored_color_identity=[],
            illegal_dropped=[],
            illegal_allowed=[],
            excluded_removed=[],
            duplicates_collapsed={},
            include_added=[],
            include_over_ideal={},
            fuzzy_corrections={},
            confirmation_needed=[],
            list_size_warnings={}
        )

        # 1. Collapse duplicates for both lists
        include_unique, include_dupes = collapse_duplicates(self.include_cards)
        exclude_unique, exclude_dupes = collapse_duplicates(self.exclude_cards)
        
        # Update internal lists with unique versions
        self.include_cards = include_unique
        self.exclude_cards = exclude_unique
        
        # Track duplicates in diagnostics
        diagnostics.duplicates_collapsed.update(include_dupes)
        diagnostics.duplicates_collapsed.update(exclude_dupes)

        # 2. Validate list sizes
        size_validation = validate_list_sizes(self.include_cards, self.exclude_cards)
        if not size_validation['valid']:
            # List too long - this is a critical error
            for error in size_validation['errors']:
                self.output_func(f"List size error: {error}")
        
        diagnostics.list_size_warnings = size_validation.get('warnings', {})

        # 3. Get available card names for fuzzy matching
        available_cards = set()
        if self._combined_cards_df is not None and not self._combined_cards_df.empty:
            name_col = 'name' if 'name' in self._combined_cards_df.columns else 'Card Name'
            if name_col in self._combined_cards_df.columns:
                available_cards = set(self._combined_cards_df[name_col].astype(str))

        # 4. Process includes with fuzzy matching and color identity validation
        processed_includes = []
        for card_name in self.include_cards:
            if not card_name.strip():
                continue
                
            # Fuzzy match if enabled
            if self.fuzzy_matching and available_cards:
                match_result = fuzzy_match_card_name(card_name, available_cards)
                if match_result.auto_accepted and match_result.matched_name:
                    if match_result.matched_name != card_name:
                        diagnostics.fuzzy_corrections[card_name] = match_result.matched_name
                    processed_includes.append(match_result.matched_name)
                elif match_result.suggestions:
                    # Needs user confirmation
                    diagnostics.confirmation_needed.append({
                        "input": card_name,
                        "suggestions": match_result.suggestions,
                        "confidence": match_result.confidence
                    })
                    # M5: Metrics counter for fuzzy confirmations
                    logger.info(f"FUZZY_CONFIRMATION_NEEDED: {card_name} (confidence: {match_result.confidence:.3f})")
                else:
                    # No good matches found
                    diagnostics.missing_includes.append(card_name)
                    # M5: Metrics counter for missing includes
                    logger.info(f"INCLUDE_CARD_MISSING: {card_name} (no_matches_found)")
            else:
                # Direct matching or fuzzy disabled
                processed_includes.append(card_name)

        # 5. Color identity validation for includes
        if processed_includes and hasattr(self, 'color_identity') and self.color_identity:
            validated_includes = []
            for card_name in processed_includes:
                if self._validate_card_color_identity(card_name):
                    validated_includes.append(card_name)
                else:
                    diagnostics.ignored_color_identity.append(card_name)
                    # M5: Structured logging for color identity violations
                    logger.warning(f"INCLUDE_COLOR_VIOLATION: card={card_name} commander_colors={self.color_identity}")
                    self.output_func(f"Card '{card_name}' has invalid color identity for commander (ignored)")
            processed_includes = validated_includes

        # 6. Handle exclude conflicts (exclude overrides include)
        final_includes = []
        for include in processed_includes:
            if include in self.exclude_cards:
                diagnostics.excluded_removed.append(include)
                # M5: Structured logging for include/exclude conflicts
                logger.info(f"INCLUDE_EXCLUDE_CONFLICT: {include} (resolution: excluded)")
                self.output_func(f"Card '{include}' appears in both include and exclude lists - excluding takes precedence")
            else:
                final_includes.append(include)

        # Update processed lists
        self.include_cards = final_includes

        # Store diagnostics for later use
        self.include_exclude_diagnostics = diagnostics.__dict__
        
        # M5: Performance monitoring for include/exclude processing
        process_duration = (time.perf_counter() - process_start_time) * 1000  # Convert to ms
        total_cards = len(self.include_cards) + len(self.exclude_cards)
        logger.info(f"INCLUDE_EXCLUDE_PERFORMANCE: duration_ms={process_duration:.2f} total_cards={total_cards} includes={len(self.include_cards)} excludes={len(self.exclude_cards)}")

        return diagnostics

    def _get_fuzzy_suggestions(self, input_name: str, available_cards: Set[str], max_suggestions: int = 3) -> List[str]:
        """
        Get fuzzy match suggestions for a card name.
        
        Args:
            input_name: User input card name
            available_cards: Set of available card names
            max_suggestions: Maximum number of suggestions to return
            
        Returns:
            List of suggested card names
        """
        if not input_name or not available_cards:
            return []
            
        match_result = fuzzy_match_card_name(input_name, available_cards)
        return match_result.suggestions[:max_suggestions]

    def _enforce_includes_strict(self) -> None:
        """
        Enforce strict mode for includes - raise error if any valid includes are missing.
        
        Raises:
            RuntimeError: If enforcement_mode is 'strict' and includes are missing
        """
        if self.enforcement_mode != "strict":
            return
            
        if not self.include_exclude_diagnostics:
            return
            
        missing = self.include_exclude_diagnostics.get('missing_includes', [])
        if missing:
            missing_str = ', '.join(missing)
            # M5: Structured logging for strict mode enforcement
            logger.error(f"STRICT_MODE_FAILURE: missing_includes={len(missing)} cards={missing_str}")
            raise RuntimeError(f"Strict mode: Failed to include required cards: {missing_str}")
        else:
            # M5: Structured logging for strict mode success
            logger.info("STRICT_MODE_SUCCESS: all_includes_satisfied=true")

    def _validate_card_color_identity(self, card_name: str) -> bool:
        """
        Check if a card's color identity is legal for this commander.
        
        Args:
            card_name: Name of the card to validate
            
        Returns:
            True if card is legal for commander's color identity, False otherwise
        """
        if not hasattr(self, 'color_identity') or not self.color_identity:
            # No commander color identity set, allow all cards
            return True
            
        # Get card data from our dataframes
        if hasattr(self, '_full_cards_df') and self._full_cards_df is not None:
            # Handle both possible column names
            name_col = 'name' if 'name' in self._full_cards_df.columns else 'Name'
            card_matches = self._full_cards_df[self._full_cards_df[name_col].str.lower() == card_name.lower()]
            if not card_matches.empty:
                card_row = card_matches.iloc[0]
                card_color_identity = card_row.get('colorIdentity', '')
                
                # Parse card's color identity
                if isinstance(card_color_identity, str) and card_color_identity.strip():
                    # Handle "Colorless" as empty color identity
                    if card_color_identity.lower() == 'colorless':
                        card_colors = []
                    elif ',' in card_color_identity:
                        # Handle format like "R, U" or "W, U, B"
                        card_colors = [c.strip() for c in card_color_identity.split(',') if c.strip()]
                    elif card_color_identity.startswith('[') and card_color_identity.endswith(']'):
                        # Handle format like "['W']" or "['U','R']"
                        import ast
                        try:
                            card_colors = ast.literal_eval(card_color_identity)
                        except Exception:
                            # Fallback parsing
                            card_colors = [c.strip().strip("'\"") for c in card_color_identity.strip('[]').split(',') if c.strip()]
                    else:
                        # Handle simple format like "W" or single color
                        card_colors = [card_color_identity.strip()]
                elif isinstance(card_color_identity, list):
                    card_colors = card_color_identity
                else:
                    # No color identity or colorless
                    card_colors = []
                
                # Check if card's colors are subset of commander's colors
                commander_colors = set(self.color_identity)
                card_colors_set = set(c.upper() for c in card_colors if c)
                
                return card_colors_set.issubset(commander_colors)
        
        # If we can't find the card or determine its color identity, assume it's illegal
        # (This is safer for validation purposes)
        return False

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
        M2: Prevents re-entry of excluded cards via downstream heuristics.
        """
        # M2: Exclude re-entry prevention - check if card is in exclude list
        if not is_commander and hasattr(self, 'exclude_cards') and self.exclude_cards:
            from .include_exclude_utils import normalize_punctuation
            
            # Normalize the card name for comparison (with punctuation normalization)
            normalized_card = normalize_punctuation(card_name)
            normalized_excludes = {normalize_punctuation(exc): exc for exc in self.exclude_cards}
            
            if normalized_card in normalized_excludes:
                # Log the prevention but don't output to avoid spam
                logger.info(f"EXCLUDE_REENTRY_PREVENTED: Blocked re-addition of excluded card '{card_name}' (pattern: '{normalized_excludes[normalized_card]}')")
                return
        
        # In owned-only mode, block adding cards not in owned list (except the commander itself)
        try:
            if getattr(self, 'use_owned_only', False) and not is_commander:
                owned = getattr(self, 'owned_card_names', set()) or set()
                if owned and card_name.lower() not in {n.lower() for n in owned}:
                    # Silently skip non-owned additions
                    return
        except Exception:
            pass

        # Enforce color identity / card-pool legality: if the card is not present in the
        # current dataframes snapshot (which is filtered by color identity), skip it.
        # Allow the commander to bypass this check.
        try:
            if not is_commander:
                # Permit basic lands even if they aren't present in the current CSV pool.
                # Some distributions may omit basics from the per-color card CSVs, but they are
                # always legal within color identity. We therefore bypass pool filtering for
                # basic/snow basic lands and Wastes.
                try:
                    basic_names = bu.basic_land_names()
                except Exception:
                    basic_names = set()

                if str(card_name) not in basic_names:
                    # Use filtered pool (_combined_cards_df) instead of unfiltered (_full_cards_df)
                    # This ensures exclude filtering is respected during card addition
                    df_src = self._combined_cards_df if self._combined_cards_df is not None else self._full_cards_df
                    if df_src is not None and not df_src.empty and 'name' in df_src.columns:
                        if df_src[df_src['name'].astype(str).str.lower() == str(card_name).lower()].empty:
                            # Not in the legal pool (likely off-color or unavailable)
                            try:
                                self.output_func(f"Skipped illegal/off-pool card: {card_name}")
                            except Exception:
                                pass
                            return
        except Exception:
            # If any unexpected error occurs, fall through (do not block legitimate adds)
            pass
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
            # If no tags passed attempt enrichment from filtered pool first, then full snapshot
            if not tags:
                # Use filtered pool (_combined_cards_df) instead of unfiltered (_full_cards_df)
                # This ensures exclude filtering is respected during card enrichment
                df_src = self._combined_cards_df if self._combined_cards_df is not None else self._full_cards_df
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
            # Enrich missing type and mana_cost for accurate categorization
            if (not card_type) or (not mana_cost):
                try:
                    # Use filtered pool (_combined_cards_df) instead of unfiltered (_full_cards_df)
                    # This ensures exclude filtering is respected during card enrichment
                    df_src = self._combined_cards_df if self._combined_cards_df is not None else self._full_cards_df
                    if df_src is not None and not df_src.empty and 'name' in df_src.columns:
                        row_match2 = df_src[df_src['name'].astype(str).str.lower() == str(card_name).lower()]
                        if not row_match2.empty:
                            if not card_type:
                                card_type = str(row_match2.iloc[0].get('type', row_match2.iloc[0].get('type_line', '')) or '')
                            if not mana_cost:
                                mana_cost = str(row_match2.iloc[0].get('mana_cost', row_match2.iloc[0].get('manaCost', '')) or '')
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
        # Owned-only status
        if getattr(self, 'use_owned_only', False):
            try:
                self.output_func(f"Owned-only mode: {len(self.owned_card_names)} cards from {len(self.owned_files_selected)} file(s)")
            except Exception:
                self.output_func("Owned-only mode: enabled")
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
        # Ask if user wants to limit pool to owned cards and gather selection
        try:
            self._prompt_use_owned_cards()
        except Exception as e:
            self.output_func(f"Owned-cards prompt failed (continuing without): {e}")
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
            'fetch_lands': getattr(bc, 'FETCH_LAND_DEFAULT_COUNT', 3),
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
            ('fetch_lands', 'Fetch Lands'),
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
            ('fetch_lands', 'Fetch Lands'),
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
