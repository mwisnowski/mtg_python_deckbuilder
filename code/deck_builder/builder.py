from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple
import pandas as pd

from . import builder_constants as bc

# Attempt to use a fast fuzzy library; fall back gracefully
try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz
    _FUZZ_BACKEND = "rapidfuzz"
except ImportError:
    try:
        from fuzzywuzzy import process as fw_process, fuzz as fw_fuzz
        _FUZZ_BACKEND = "fuzzywuzzy"
    except ImportError:
        _FUZZ_BACKEND = "difflib"

if _FUZZ_BACKEND == "rapidfuzz":
    def _full_ratio(a: str, b: str) -> float:
        return rf_fuzz.ratio(a, b)
    def _top_matches(query: str, choices: List[str], limit: int):
        return [(name, int(score)) for name, score, _ in rf_process.extract(query, choices, limit=limit)]
elif _FUZZ_BACKEND == "fuzzywuzzy":
    def _full_ratio(a: str, b: str) -> float:
        return fw_fuzz.ratio(a, b)
    def _top_matches(query: str, choices: List[str], limit: int):
        return fw_process.extract(query, choices, limit=limit)
else:
    # Very basic fallback (difflib)
    from difflib import SequenceMatcher, get_close_matches
    def _full_ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    def _top_matches(query: str, choices: List[str], limit: int):
        close = get_close_matches(query, choices, n=limit, cutoff=0.0)
        scored = [(c, int(_full_ratio(query, c))) for c in close]
        if len(scored) < limit:
            remaining = [c for c in choices if c not in close]
            extra = sorted(
                ((c, int(_full_ratio(query, c))) for c in remaining),
                key=lambda x: x[1],
                reverse=True
            )[: limit - len(scored)]
            scored.extend(extra)
        return scored

EXACT_NAME_THRESHOLD = 80
FIRST_WORD_THRESHOLD = 75
MAX_PRESENTED_CHOICES = 5

# ---------------------------
# Deck Power Bracket (Deck Building Step 1)
# ---------------------------

@dataclass(frozen=True)
class BracketDefinition:
    level: int
    name: str
    short_desc: str
    long_desc: str
    limits: Dict[str, Optional[int]]  # None = unlimited

BRACKET_DEFINITIONS: List[BracketDefinition] = [
    BracketDefinition(
        1,
        "Exhibition",
        "Ultra-casual / novelty; long games; focus on fun.",
        ("Throw down with your ultra‑casual deck. Winning isn't primary—show off something unusual. "
         "Games go long and end slowly."),
        {
            "game_changers": 0,
            "mass_land_denial": 0,
            "extra_turns": 0,
            "tutors_nonland": 3,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        2,
        "Core",
        "Precon baseline; splashy turns; 9+ turn games.",
        ("Average modern precon: tuned engines & splashy turns, some pet/theme cards, usually longer games."),
        {
            "game_changers": 0,
            "mass_land_denial": 0,
            "extra_turns": 3,
            "tutors_nonland": 3,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        3,
        "Upgraded",
        "Refined beyond precon; faster; selective power.",
        ("Carefully selected cards; may include up to three Game Changers. Avoids cheap fast infinite two‑card combos."),
        {
            "game_changers": 3,
            "mass_land_denial": 0,
            "extra_turns": 3,
            "tutors_nonland": None,
            "two_card_combos": 0
        }
    ),
    BracketDefinition(
        4,
        "Optimized",
        "High power, explosive, not meta-focused.",
        ("Strong, explosive builds; any number of powerful effects, tutors, combos, and denial."),
        {
            "game_changers": None,
            "mass_land_denial": None,
            "extra_turns": None,
            "tutors_nonland": None,
            "two_card_combos": None
        }
    ),
    BracketDefinition(
        5,
        "cEDH",
        "Competitive, meta-driven mindset.",
        ("Metagame/tournament mindset; precision choices; winning prioritized over expression."),
        {
            "game_changers": None,
            "mass_land_denial": None,
            "extra_turns": None,
            "tutors_nonland": None,
            "two_card_combos": None
        }
    ),
]


@dataclass
class DeckBuilder:
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

    # IO injection for testing
    input_func: Callable[[str], str] = field(default=lambda prompt: input(prompt))
    output_func: Callable[[str], None] = field(default=lambda msg: print(msg))

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
        import math

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

    # ---------------------------
    # Commander Selection
    # ---------------------------
    def choose_commander(self) -> str:
        df = self.load_commander_data()
        names = df["name"].tolist()
        while True:
            query = self.input_func("Enter commander name: ").strip()
            if not query:
                self.output_func("No input provided. Try again.")
                continue

            direct_hits = [n for n in names if self._auto_accept(query, n)]
            if len(direct_hits) == 1:
                candidate = direct_hits[0]
                self.output_func(f"(Auto match candidate) {candidate}")
                if self._present_commander_and_confirm(df, candidate):
                    self.output_func(f"Confirmed: {candidate}")
                    return candidate
                else:
                    self.output_func("Not confirmed. Starting over.\n")
                    continue

            candidates = self._gather_candidates(query, names)
            if not candidates:
                self.output_func("No close matches found. Try again.")
                continue

            self.output_func("\nTop matches:")
            for idx, (n, score) in enumerate(candidates, start=1):
                self.output_func(f"  {idx}. {n}  (score {score})")
            self.output_func("Enter number to inspect, 'r' to retry, or type a new name:")

            choice = self.input_func("Selection: ").strip()
            if choice.lower() == 'r':
                continue
            if choice.isdigit():
                i = int(choice)
                if 1 <= i <= len(candidates):
                    nm = candidates[i - 1][0]
                    if self._present_commander_and_confirm(df, nm):
                        self.output_func(f"Confirmed: {nm}")
                        return nm
                    else:
                        self.output_func("Not confirmed. Search again.\n")
                        continue
                else:
                    self.output_func("Invalid index.")
                    continue
            # Treat as new query
            query = choice

    def _apply_commander_selection(self, row: pd.Series):
        self.commander_name = row["name"]
        self.commander_row = row
        self.commander_tags = list(row.get("themeTags", []) or [])
        self._initialize_commander_dict(row)

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
                 is_commander: bool = False) -> None:
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
                    import re
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
            entry['Count'] += 1
        else:
            self.card_library[card_name] = {
                'Card Name': card_name,
                'Card Type': card_type,
                'Mana Cost': mana_cost,
                'Mana Value': mana_value,
                'Creature Types': creature_types,
                'Tags': tags,
                'Commander': is_commander,
                'Count': 1
            }
        # Keep commander dict CMC up to date if adding commander
        if is_commander and self.commander_dict:
            if mana_value is not None:
                self.commander_dict['CMC'] = mana_value
        # Remove this card from combined pool if present
        self._remove_from_pool(card_name)

    def _remove_from_pool(self, card_name: str):
        if self._combined_cards_df is None:
            return
        df = self._combined_cards_df
        if 'name' in df.columns:
            self._combined_cards_df = df[df['name'] != card_name]
        elif 'Card Name' in df.columns:
            self._combined_cards_df = df[df['Card Name'] != card_name]

    # ---------------------------
    # Land Building Step 1: Basic Lands
    # ---------------------------
    def add_basic_lands(self):
        """Add basic (or snow basic) lands based on color identity.

        Logic:
          - Determine target basics = ceil(1.3 * ideal_basic_min) (rounded) but capped by total land target
          - Evenly distribute among colored identity letters (W,U,B,R,G)
          - If commander/selected tags include 'Snow' (case-insensitive) use snow basics mapping
          - Colorless commander: use Wastes for the entire basic allocation
        """
        # Ensure color identity determined
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add basics until color identity resolved: {e}")
                return

        # Ensure ideal counts (for min basics & total lands)
        basic_min = None
        land_total = None
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            basic_min = self.ideal_counts.get('basic_lands')
            land_total = self.ideal_counts.get('lands')
        if basic_min is None:
            basic_min = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if land_total is None:
            land_total = getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        # Target basics = 1.3 * minimum (rounded) but not exceeding total lands
        target_basics = int(round(1.3 * basic_min))
        if target_basics > land_total:
            target_basics = land_total
        if target_basics <= 0:
            self.output_func("Target basic land count is zero; skipping basics.")
            return

        colors = [c for c in self.color_identity if c in ['W','U','B','R','G']]
        if not colors:
            # Colorless
            colors = []  # special case: use Wastes only

        # Determine if snow preferred
        tag_pool = (self.selected_tags or []) + (self.commander_tags if hasattr(self, 'commander_tags') else [])
        use_snow = any('snow' in str(t).lower() for t in tag_pool)
        snow_map = getattr(bc, 'SNOW_BASIC_LAND_MAPPING', {})
        basic_map = getattr(bc, 'COLOR_TO_BASIC_LAND', {})

        allocation: Dict[str, int] = {}
        if not colors:  # colorless
            allocation_name = snow_map.get('C', 'Wastes') if use_snow else 'Wastes'
            allocation[allocation_name] = target_basics
        else:
            n = len(colors)
            base = target_basics // n
            rem = target_basics % n
            for idx, c in enumerate(sorted(colors)):  # sorted for deterministic distribution
                count = base + (1 if idx < rem else 0)
                land_name = snow_map.get(c) if use_snow else basic_map.get(c)
                if not land_name:
                    continue
                allocation[land_name] = allocation.get(land_name, 0) + count

        # Add to library
        for land_name, count in allocation.items():
            for _ in range(count):
                self.add_card(land_name, card_type='Land')

        # Summary output
        self.output_func("\nBasic Lands Added:")
        width = max(len(n) for n in allocation.keys()) if allocation else 0
        for name, cnt in allocation.items():
            self.output_func(f"  {name.ljust(width)} : {cnt}")
        self.output_func(f"  Total Basics : {sum(allocation.values())} (Target {target_basics}, Min {basic_min})")

    def run_land_step1(self):
        """Public wrapper to execute land building step 1 (basics)."""
        self.add_basic_lands()

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

    def add_staple_lands(self):
        """Add generic staple lands defined in STAPLE_LAND_CONDITIONS (excluding kindred lands).

        Respects total land target (ideal_counts['lands']). Skips additions once target reached.
        Conditions may use commander tags (all available, not just selected), color identity, and commander power.
        """
        # Ensure color identity and card pool loaded
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add staple lands until color identity resolved: {e}")
                return

        # Determine land target
        land_target = None
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            land_target = self.ideal_counts.get('lands')
        if land_target is None:
            land_target = getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        # Early exit if already at or above target
        if self._current_land_count() >= land_target:
            self.output_func("Staple Lands: Land target already met; skipping step 2.")
            return

        commander_tags_all = set(getattr(self, 'commander_tags', []) or []) | set(getattr(self, 'selected_tags', []) or [])
        colors = self.color_identity or []
        # Commander power for conditions
        commander_power = 0
        try:
            if self.commander_row is not None:
                raw_power = self.commander_row.get('power')
                if isinstance(raw_power, (int, float)):
                    commander_power = int(raw_power)
                elif isinstance(raw_power, str) and raw_power.isdigit():
                    commander_power = int(raw_power)
        except Exception:
            commander_power = 0

        added: List[str] = []
        reasons: Dict[str, str] = {}
        for land_name, cond in getattr(bc, 'STAPLE_LAND_CONDITIONS', {}).items():
            # Stop if land target reached
            if self._current_land_count() >= land_target:
                break
            # Skip if already in library
            if land_name in self.card_library:
                continue
            try:
                include = cond(list(commander_tags_all), colors, commander_power)
            except Exception:
                include = False
            if include:
                self.add_card(land_name, card_type='Land')
                added.append(land_name)
                # Basic reason heuristics for transparency
                if land_name == 'Command Tower':
                    reasons[land_name] = f"multi-color ({len(colors)} colors)"
                elif land_name == 'Exotic Orchard':
                    reasons[land_name] = f"multi-color ({len(colors)} colors)"
                elif land_name == 'War Room':
                    reasons[land_name] = f"<=2 colors ({len(colors)})"
                elif land_name == 'Reliquary Tower':
                    reasons[land_name] = 'always include'
                elif land_name == 'Ash Barrens':
                    reasons[land_name] = 'no Landfall tag'
                elif land_name == "Rogue's Passage":
                    reasons[land_name] = f"commander power {commander_power} >=5"

        self.output_func("\nStaple Lands Added (Step 2):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                reason = reasons.get(n, '')
                self.output_func(f"  {n.ljust(width)} : 1  {('(' + reason + ')') if reason else ''}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step2(self):
        """Public wrapper for adding generic staple nonbasic lands (excluding kindred)."""
        self.add_staple_lands()

    # ---------------------------
    # Tag Prioritization
    # ---------------------------
    def select_commander_tags(self) -> List[str]:
        if not self.commander_name:
            self.output_func("No commander chosen yet. Selecting commander first...")
            self.choose_commander()

        tags = list(dict.fromkeys(self.commander_tags))
        if not tags:
            self.output_func("Commander has no theme tags available.")
            self.selected_tags = []
            self.primary_tag = self.secondary_tag = self.tertiary_tag = None
            self._update_commander_dict_with_selected_tags()
            return self.selected_tags

        self.output_func("\nAvailable Theme Tags:")
        for i, t in enumerate(tags, 1):
            self.output_func(f"  {i}. {t}")

        self.selected_tags = []
        # Primary (required)
        self.primary_tag = self._prompt_tag_choice(tags, "Select PRIMARY tag (required):", allow_stop=False)
        self.selected_tags.append(self.primary_tag)

        remaining = [t for t in tags if t not in self.selected_tags]

        # Secondary (optional)
        if remaining:
            self.secondary_tag = self._prompt_tag_choice(
                remaining,
                "Select SECONDARY tag (or 0 to stop here):",
                allow_stop=True
            )
            if self.secondary_tag:
                self.selected_tags.append(self.secondary_tag)
                remaining = [t for t in remaining if t != self.secondary_tag]

        # Tertiary (optional)
        if remaining and self.secondary_tag:
            self.tertiary_tag = self._prompt_tag_choice(
                remaining,
                "Select TERTIARY tag (or 0 to stop here):",
                allow_stop=True
            )
            if self.tertiary_tag:
                self.selected_tags.append(self.tertiary_tag)

        self.output_func("\nChosen Tags (in priority order):")
        if not self.selected_tags:
            self.output_func("  (None)")
        else:
            for idx, tag in enumerate(self.selected_tags, 1):
                label = ["Primary", "Secondary", "Tertiary"][idx - 1] if idx <= 3 else f"Tag {idx}"
                self.output_func(f"  {idx}. {tag} ({label})")

        self._update_commander_dict_with_selected_tags()
        return self.selected_tags

    def _prompt_tag_choice(self, available: List[str], prompt_text: str, allow_stop: bool) -> Optional[str]:
        while True:
            self.output_func("\nCurrent options:")
            for i, t in enumerate(available, 1):
                self.output_func(f"  {i}. {t}")
            if allow_stop:
                self.output_func("  0. Stop (no further tags)")
            raw = self.input_func(f"{prompt_text} ").strip()
            if allow_stop and raw == "0":
                return None
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(available):
                    return available[idx - 1]
            matches = [t for t in available if t.lower() == raw.lower()]
            if matches:
                return matches[0]
            self.output_func("Invalid selection. Try again.")

    def _update_commander_dict_with_selected_tags(self):
        if not self.commander_dict and self.commander_row is not None:
            self._initialize_commander_dict(self.commander_row)
        if not self.commander_dict:
            return
        self.commander_dict["Primary Tag"] = self.primary_tag
        self.commander_dict["Secondary Tag"] = self.secondary_tag
        self.commander_dict["Tertiary Tag"] = self.tertiary_tag
        self.commander_dict["Selected Tags"] = self.selected_tags.copy()

    # ---------------------------
    # Power Bracket Selection (Deck Building Step 1)
    # ---------------------------
    def select_power_bracket(self) -> BracketDefinition:
        if self.bracket_definition:
            return self.bracket_definition

        self.output_func("\nChoose Deck Power Bracket:")
        for bd in BRACKET_DEFINITIONS:
            self.output_func(f"  {bd.level}. {bd.name} - {bd.short_desc}")

        while True:
            raw = self.input_func("Enter bracket number (1-5) or 'info' for details: ").strip().lower()
            if raw == "info":
                self._print_bracket_details()
                continue
            if raw.isdigit():
                num = int(raw)
                match = next((bd for bd in BRACKET_DEFINITIONS if bd.level == num), None)
                if match:
                    self.bracket_definition = match
                    self.bracket_level = match.level
                    self.bracket_name = match.name
                    self.bracket_limits = match.limits.copy()
                    self.output_func(f"\nSelected Bracket {match.level}: {match.name}")
                    self._print_selected_bracket_summary()
                    return match
            self.output_func("Invalid input. Type 1-5 or 'info'.")

    def _print_bracket_details(self):
        self.output_func("\nBracket Details:")
        for bd in BRACKET_DEFINITIONS:
            self.output_func(f"\n[{bd.level}] {bd.name}")
            self.output_func(bd.long_desc)
            self.output_func(self._format_limits(bd.limits))

    def _print_selected_bracket_summary(self):
        if not self.bracket_definition:
            return
        self.output_func("\nBracket Constraints:")
        self.output_func(self._format_limits(self.bracket_limits))

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

    # ---------------------------
    # Card Library Reporting
    # ---------------------------
    def print_card_library(self, truncate_text: bool = True, text_limit: int = 80):
        """Pretty print the current card library using PrettyTable.

        Columns: Name | Color Identity | Colors | Mana Cost | Mana Value | Type | Creature Types | Power | Toughness | Keywords | Theme Tags | Text
        Commander appears first, then cards in insertion order. Shows total & remaining slots (to 100).
        """
        total_cards = sum(entry.get('Count', 1) for entry in self.card_library.values())
        remaining = max(0, 100 - total_cards)
        self.output_func(f"\nCard Library: {total_cards} cards (Commander included). Remaining slots: {remaining}")

        try:
            from prettytable import PrettyTable
        except ImportError:
            self.output_func("PrettyTable not installed. Run 'pip install prettytable' to enable formatted library output.")
            for name, entry in self.card_library.items():
                self.output_func(f"- {name} x{entry.get('Count',1)}")
            return

        cols = [
            'Name', 'Color Identity', 'Colors', 'Mana Cost', 'Mana Value', 'Type',
            'Creature Types', 'Power', 'Toughness', 'Keywords', 'Theme Tags', 'Text'
        ]  # Name will include duplicate count suffix (e.g., "Plains x13") if Count>1
        table = PrettyTable(field_names=cols)
        table.align = 'l'

        # Build lookup from combined df for enrichment (prefer full snapshot so removed rows still enrich)
        combined = self._full_cards_df if self._full_cards_df is not None else self._combined_cards_df
        combined_lookup: Dict[str, pd.Series] = {}
        if combined is not None and 'name' in combined.columns:
            for _, r in combined.iterrows():
                nm = str(r.get('name'))
                if nm not in combined_lookup:
                    combined_lookup[nm] = r

        def limit(txt: str):
            if not truncate_text or txt is None:
                return txt
            if len(txt) <= text_limit:
                return txt
            return txt[: text_limit - 3] + '...'

        # Commander first
        ordered_items = list(self.card_library.items())
        ordered_items.sort(key=lambda kv: (0 if kv[1].get('Commander') else 1))

        basic_names = set(getattr(bc, 'BASIC_LANDS', []))
        snow_basic_names = set(getattr(bc, 'SNOW_BASIC_LAND_MAPPING', {}).values())
        rev_basic = {v: k for k, v in getattr(bc, 'COLOR_TO_BASIC_LAND', {}).items()}
        rev_snow = {v: k for k, v in getattr(bc, 'SNOW_BASIC_LAND_MAPPING', {}).items()}

        for name, entry in ordered_items:
            row_source = combined_lookup.get(name)
            count = entry.get('Count', 1)
            display_name = f"{name} x{count}" if count > 1 else name

            if entry.get('Commander') and self.commander_dict:
                ci_list = self.commander_dict.get('Color Identity', [])
                ci = ''.join(ci_list) if isinstance(ci_list, list) else str(ci_list)
                colors_list = self.commander_dict.get('Colors', [])
                colors = ''.join(colors_list) if isinstance(colors_list, list) else str(colors_list)
                mana_cost = self.commander_dict.get('Mana Cost', '')
                mana_value = self.commander_dict.get('Mana Value', '')
                type_line = self.commander_dict.get('Type', '')
                creature_types_val = self.commander_dict.get('Creature Types', [])
                creature_types = ', '.join(creature_types_val) if isinstance(creature_types_val, list) else str(creature_types_val)
                power = self.commander_dict.get('Power', '')
                toughness = self.commander_dict.get('Toughness', '')
                # Enrich keywords from snapshot if present
                if row_source is not None:
                    kw_val = row_source.get('keywords', [])
                    if isinstance(kw_val, list):
                        keywords = ', '.join(str(x) for x in kw_val)
                    else:
                        keywords = '' if kw_val in (None, '') else str(kw_val)
                else:
                    keywords = ''
                theme_tags_val = self.commander_dict.get('Themes', [])
                theme_tags = ', '.join(theme_tags_val) if isinstance(theme_tags_val, list) else str(theme_tags_val)
                text_field = limit(self.commander_dict.get('Text', ''))
            else:
                # Default blanks
                ci = colors = mana_cost = ''
                mana_value = ''
                type_line = entry.get('Card Type', '')
                creature_types = power = toughness = keywords = theme_tags = text_field = ''
                if row_source is not None:
                    # Basic enrichment fields
                    mana_cost = row_source.get('manaCost', '')
                    mana_value = row_source.get('manaValue', row_source.get('cmc', ''))
                    type_line = row_source.get('type', row_source.get('type_line', type_line or ''))
                    ct_raw = row_source.get('creatureTypes', [])
                    if isinstance(ct_raw, list):
                        creature_types = ', '.join(ct_raw)
                    else:
                        creature_types = str(ct_raw) if ct_raw not in (None, '') else ''
                    power = row_source.get('power', '')
                    toughness = row_source.get('toughness', '')
                    kw_raw = row_source.get('keywords', [])
                    if isinstance(kw_raw, list):
                        keywords = ', '.join(kw_raw)
                    elif kw_raw not in (None, ''):
                        keywords = str(kw_raw)
                    tg_raw = row_source.get('themeTags', [])
                    if isinstance(tg_raw, list):
                        theme_tags = ', '.join(tg_raw)
                    text_field = limit(str(row_source.get('text', row_source.get('oracleText', ''))).replace('\n', ' '))

                    # Only apply color identity/colors if NOT a land or is a basic/snow basic
                    type_lower = str(type_line).lower()
                    if 'land' in type_lower:
                        if name in basic_names:
                            letter = rev_basic.get(name, '')
                            ci = letter
                            colors = letter
                        elif name in snow_basic_names:
                            letter = rev_snow.get(name, '')
                            ci = letter
                            colors = letter
                        else:
                            ci = ''
                            colors = ''
                    else:
                        ci_raw = row_source.get('colorIdentity', row_source.get('colors', []))
                        if isinstance(ci_raw, list):
                            ci = ''.join(ci_raw)
                        else:
                            ci = str(ci_raw) if ci_raw not in (None, '') else ''
                        colors_raw = row_source.get('colors', [])
                        if isinstance(colors_raw, list):
                            colors = ''.join(colors_raw)
                        elif colors_raw not in (None, ''):
                            colors = str(colors_raw)
                else:
                    # No row source (likely a basic we added or manual staple missing from CSV)
                    type_line = type_line or 'Land'
                    if name in basic_names:
                        letter = rev_basic.get(name, '')
                        ci = letter
                        colors = letter
                    elif name in snow_basic_names:
                        letter = rev_snow.get(name, '')
                        ci = letter
                        colors = letter
                    elif 'land' in str(type_line).lower():
                        ci = colors = ''  # nonbasic land => blank

                # Ensure nonbasic land override even if CSV has color identity
                if 'land' in str(type_line).lower() and name not in basic_names and name not in snow_basic_names:
                    ci = ''
                    colors = ''

            table.add_row([
                display_name,
                ci,
                colors,
                mana_cost,
                mana_value,
                type_line,
                creature_types,
                power,
                toughness,
                keywords,
                theme_tags,
                text_field
            ])

        self.output_func(table.get_string())

    # Convenience to run Step 1 & 2 sequentially (future orchestrator)
    def run_deck_build_steps_1_2(self):
        self.run_deck_build_step1()
        self.run_deck_build_step2()