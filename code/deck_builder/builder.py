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
            # Increment only count; tag counts track unique card presence so unchanged
            entry['Count'] += 1
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
                'Role': None  # placeholder for 'flex', 'suggested', etc.
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

        # We allow swapping basics (above 90% min floor) to fit staple lands.
        # If already at target, we'll attempt to free slots on-demand while iterating.
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        def ensure_capacity() -> bool:
            """Try to free one land slot by trimming a basic (if above floor). Return True if capacity exists after call."""
            if self._current_land_count() < land_target:
                return True
            # Need to free one slot
            if self._count_basic_lands() <= basic_floor:
                return False
            target_basic = self._choose_basic_to_trim()
            if not target_basic:
                return False
            if not self._decrement_card(target_basic):
                return False
            return self._current_land_count() < land_target
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
            # Ensure we have a slot (attempt to free basics if necessary)
            if not ensure_capacity():
                self.output_func("Staple Lands: Cannot free capacity without violating basic floor; stopping additions.")
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
        self._enforce_land_cap(step_label="Staples (Step 2)")

    # ---------------------------
    # Land Building Step 3: Kindred / Creature-Type Focused Lands
    # ---------------------------
    def add_kindred_lands(self):
        """Add kindred-oriented lands ONLY if a selected tag includes 'Kindred' or 'Tribal'.

        Baseline inclusions on kindred focus:
          - Path of Ancestry (always when kindred)
          - Cavern of Souls (<=4 colors)
          - Three Tree City (>=2 colors)
        Dynamic tribe-specific lands: derived only from selected tags (not all commander tags).
        Capacity: may swap excess basics (above 90% floor) similar to other steps.
        """
        # Ensure color identity loaded
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add kindred lands until color identity resolved: {e}")
                return

        # Gate: only run if user-selected tag has kindred/tribal
        if not any(('kindred' in t.lower() or 'tribal' in t.lower()) for t in (self.selected_tags or [])):
            self.output_func("Kindred Lands: No selected kindred/tribal tag; skipping.")
            return

        # Land target
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            land_target = self.ideal_counts.get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35))
        else:
            land_target = getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        def ensure_capacity() -> bool:
            if self._current_land_count() < land_target:
                return True
            if self._count_basic_lands() <= basic_floor:
                return False
            target_basic = self._choose_basic_to_trim()
            if not target_basic:
                return False
            if not self._decrement_card(target_basic):
                return False
            return self._current_land_count() < land_target

        colors = self.color_identity or []
        added: list[str] = []
        reasons: dict[str, str] = {}

        def try_add(name: str, reason: str):
            if name in self.card_library:
                return
            if not ensure_capacity():
                return
            self.add_card(name, card_type='Land')
            added.append(name)
            reasons[name] = reason

        # Baseline
        try_add('Path of Ancestry', 'kindred focus')
        if len(colors) <= 4:
            try_add('Cavern of Souls', f"kindred focus ({len(colors)} colors)")
        if len(colors) >= 2:
            try_add('Three Tree City', f"kindred focus ({len(colors)} colors)")

        # Dynamic tribe references
        tribe_terms: set[str] = set()
        for tag in (self.selected_tags or []):
            lower = tag.lower()
            if 'kindred' in lower:
                base = lower.replace('kindred', '').strip()
                if base:
                    tribe_terms.add(base.split()[0])
            elif 'tribal' in lower:
                base = lower.replace('tribal', '').strip()
                if base:
                    tribe_terms.add(base.split()[0])

        snapshot = self._full_cards_df
        if snapshot is not None and not snapshot.empty and tribe_terms:
            dynamic_limit = 5
            for tribe in sorted(tribe_terms):
                if self._current_land_count() >= land_target or dynamic_limit <= 0:
                    break
                tribe_lower = tribe.lower()
                matches: list[str] = []
                for _, row in snapshot.iterrows():
                    try:
                        nm = str(row.get('name', ''))
                        if not nm or nm in self.card_library:
                            continue
                        tline = str(row.get('type', row.get('type_line', ''))).lower()
                        if 'land' not in tline:
                            continue
                        text_field = row.get('text', row.get('oracleText', ''))
                        text_str = str(text_field).lower() if text_field is not None else ''
                        nm_lower = nm.lower()
                        if (tribe_lower in nm_lower or f" {tribe_lower}" in text_str or f"{tribe_lower} " in text_str or f"{tribe_lower}s" in text_str):
                            matches.append(nm)
                    except Exception:
                        continue
                for nm in matches[:2]:
                    if self._current_land_count() >= land_target or dynamic_limit <= 0:
                        break
                    if nm in added or nm in getattr(bc, 'BASIC_LANDS', []):
                        continue
                    try_add(nm, f"text/name references '{tribe}'")
                    dynamic_limit -= 1

        self.output_func("\nKindred Lands Added (Step 3):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1  ({reasons.get(n,'')})")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step3(self):
        """Public wrapper to add kindred-focused lands."""
        self.add_kindred_lands()
        self._enforce_land_cap(step_label="Kindred (Step 3)")

    # ---------------------------
    # Land Building Step 4: Fetch Lands
    # ---------------------------
    def add_fetch_lands(self, requested_count: Optional[int] = None):
        """Add fetch lands (color-specific + generic) respecting land target.

        Steps:
          1. Ensure color identity loaded.
          2. Build candidate list (color-specific first, then generic) excluding existing.
          3. Determine desired count (prompt or provided) respecting global fetch cap.
          4. If no capacity, attempt to trim basics down to floor to free slots.
          5. Sample color-specific first, then generic; add until satisfied.
        """
        # 1. Ensure color identity context
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add fetch lands until color identity resolved: {e}")
                return
        # 2. Land target
        land_target = (self.ideal_counts.get('lands') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        current = self._current_land_count()
        color_order = [c for c in self.color_identity if c in ['W','U','B','R','G']]
        color_map = getattr(bc, 'COLOR_TO_FETCH_LANDS', {})
        candidates: list[str] = []
        for c in color_order:
            for nm in color_map.get(c, []):
                if nm not in candidates:
                    candidates.append(nm)
        generic_list = getattr(bc, 'GENERIC_FETCH_LANDS', [])
        for nm in generic_list:
            if nm not in candidates:
                candidates.append(nm)
        candidates = [n for n in candidates if n not in self.card_library]
        if not candidates:
            self.output_func("Fetch Lands: No eligible fetch lands remaining.")
            return
        # 3. Desired count & caps
        default_fetch = getattr(bc, 'FETCH_LAND_DEFAULT_COUNT', 3)
        remaining_capacity = max(0, land_target - current)
        cap_for_default = remaining_capacity if remaining_capacity > 0 else len(candidates)
        effective_default = min(default_fetch, cap_for_default, len(candidates))
        existing_fetches = sum(1 for n in self.card_library if n in candidates)
        fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
        remaining_fetch_slots = max(0, fetch_cap - existing_fetches)
        if requested_count is None:
            self.output_func("\nAdd Fetch Lands (Step 4):")
            self.output_func("Fetch lands help fix colors & enable landfall / graveyard synergies.")
            prompt = f"Enter desired number of fetch lands (default: {effective_default}):"
            desired = self._prompt_int_with_default(prompt + ' ', effective_default, minimum=0, maximum=20)
        else:
            desired = max(0, int(requested_count))
        if desired > remaining_fetch_slots:
            desired = remaining_fetch_slots
            if desired == 0:
                self.output_func("Fetch Lands: Global fetch cap reached; skipping.")
                return
        if desired == 0:
            self.output_func("Fetch Lands: Desired count 0; skipping.")
            return
        # 4. Free capacity via basic trimming if needed
        if remaining_capacity == 0 and desired > 0:
            min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
            if getattr(self, 'ideal_counts', None):
                min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
            floor_basics = self._basic_floor(min_basic_cfg)
            slots_needed = desired
            while slots_needed > 0 and self._count_basic_lands() > floor_basics:
                target_basic = self._choose_basic_to_trim()
                if not target_basic or not self._decrement_card(target_basic):
                    break
                slots_needed -= 1
                remaining_capacity = max(0, land_target - self._current_land_count())
                if remaining_capacity > 0 and slots_needed == 0:
                    break
            if slots_needed > 0 and remaining_capacity == 0:
                desired -= slots_needed
        # 5. Clamp & add
        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(candidates), remaining_fetch_slots)
        if desired <= 0:
            self.output_func("Fetch Lands: No capacity (after trimming) or desired reduced to 0; skipping.")
            return
        import random
        rng = getattr(self, 'rng', None)
        color_specific_all: list[str] = []
        for c in color_order:
            for n in color_map.get(c, []):
                if n in candidates and n not in color_specific_all:
                    color_specific_all.append(n)
        generic_all: list[str] = [n for n in generic_list if n in candidates]
        def sampler(pool: list[str], k: int) -> list[str]:
            if k <= 0 or not pool:
                return []
            if k >= len(pool):
                return pool.copy()
            try:
                return (rng.sample if rng else random.sample)(pool, k)
            except Exception:
                return pool[:k]
        need = desired
        chosen: list[str] = []
        take_color = min(need, len(color_specific_all))
        chosen.extend(sampler(color_specific_all, take_color))
        need -= len(chosen)
        if need > 0:
            chosen.extend(sampler(generic_all, min(need, len(generic_all))))
        if len(chosen) < desired:  # fill leftovers
            leftovers = [n for n in candidates if n not in chosen]
            chosen.extend(leftovers[: desired - len(chosen)])
        added: list[str] = []
        for nm in chosen:
            if self._current_land_count() >= land_target:
                break
            self.add_card(nm, card_type='Land')
            added.append(nm)
        self.output_func("\nFetch Lands Added (Step 4):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                note = 'generic' if n in generic_list else 'color-specific'
                self.output_func(f"  {n.ljust(width)} : 1  ({note})")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")
        # Land cap enforcement handled in run_land_step4 wrapper

    def run_land_step4(self, requested_count: Optional[int] = None):
        """Public wrapper to add fetch lands. Optional requested_count to bypass prompt."""
        self.add_fetch_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Fetch (Step 4)")

    # ---------------------------
    # Internal Helper: Basic Land Floor
    # ---------------------------
    def _basic_floor(self, min_basic_cfg: int) -> int:
        """Return the minimum number of basics we will not trim below.

        Currently defined as ceil(bc.BASIC_FLOOR_FACTOR * configured_basic_count). Centralizing here so
        future tuning (e.g., dynamic by color count, bracket, or pip distribution) only
        needs a single change. min_basic_cfg already accounts for ideal_counts override.
        """
        import math
        try:
            return max(0, int(math.ceil(bc.BASIC_FLOOR_FACTOR * float(min_basic_cfg))))
        except Exception:
            return max(0, min_basic_cfg)

    # ---------------------------
    # Land Building Step 5: Dual Lands (Two-Color Typed Lands)
    # ---------------------------
    def add_dual_lands(self, requested_count: Optional[int] = None):
        """Add two-color 'typed' dual lands based on color identity.

        Strategy:
          - Build a pool of candidate duals whose basic land types both appear in color identity.
          - Avoid duplicates or already-added lands.
          - Prioritize untapped / fetchable typed duals first (simple heuristic via name substrings).
          - Respect total land target; if at capacity attempt basic swaps (90% floor) like other steps.
          - If requested_count provided, cap additions to that number; else use constant default per colors.
        """
        # Ensure context
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add dual lands until color identity resolved: {e}")
                return
        colors = [c for c in self.color_identity if c in ['W','U','B','R','G']]
        if len(colors) < 2:
            self.output_func("Dual Lands: Not multi-color; skipping step 5.")
            return

        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        # Candidate sourcing: search combined DF for lands whose type line includes exactly two relevant basic types
        # Build mapping from frozenset({colorA,colorB}) -> list of candidate names
        pool: list[str] = []
        type_to_card = {}
        pair_buckets: dict[frozenset[str], list[str]] = {}
        df = self._combined_cards_df
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
                        # Basic type presence count
                        types_present = [basic for basic in ['plains','island','swamp','mountain','forest'] if basic in tline]
                        if len(types_present) < 2:
                            continue
                        # Map basic types to colors
                        mapped_colors = set()
                        for tp in types_present:
                            if tp == 'plains':
                                mapped_colors.add('W')
                            elif tp == 'island':
                                mapped_colors.add('U')
                            elif tp == 'swamp':
                                mapped_colors.add('B')
                            elif tp == 'mountain':
                                mapped_colors.add('R')
                            elif tp == 'forest':
                                mapped_colors.add('G')
                        if len(mapped_colors) != 2:  # strictly dual typed
                            continue
                        if not mapped_colors.issubset(set(colors)):
                            continue
                        pool.append(name)
                        type_to_card[name] = tline
                        key = frozenset(mapped_colors)
                        pair_buckets.setdefault(key, []).append(name)
                    except Exception:
                        continue
            except Exception:
                pass

        # De-duplicate
        pool = list(dict.fromkeys(pool))
        if not pool:
            self.output_func("Dual Lands: No candidate dual typed lands found in dataset.")
            return

        # Heuristic ranking inside each pair bucket: shocks > untapped > other > tapped ETB
        def rank(name: str) -> int:
            lname = name.lower()
            tline = type_to_card.get(name,'')
            score = 0
            if any(kw in lname for kw in ['temple garden','sacred foundry','stomping ground','hallowed fountain','watery grave','overgrown tomb','breeding pool','godless shrine','steam vents','blood crypt']):
                score += 10  # shocks
            if 'enters the battlefield tapped' not in tline:
                score += 2
            if 'snow' in tline:
                score += 1
            # Penalize gainlands / taplands
            if 'enters the battlefield tapped' in tline and 'you gain' in tline:
                score -= 1
            return score
        for key, names in pair_buckets.items():
            names.sort(key=lambda n: rank(n), reverse=True)
            # After deterministic ranking, perform a weighted shuffle so higher-ranked
            # lands still tend to appear earlier, but we get variety across runs.
            # This prevents always selecting the exact same first few duals when
            # capacity is limited (e.g., consistently only the top 4 of 7 available).
            if len(names) > 1:
                try:
                    rng_obj = getattr(self, 'rng', None)
                    weighted: list[tuple[str, int]] = []
                    for n in names:
                        # Base weight derived from rank() (ensure >=1) and mildly amplified
                        w = max(1, rank(n)) + 1
                        weighted.append((n, w))
                    shuffled: list[str] = []
                    import random as _rand
                    while weighted:
                        total = sum(w for _, w in weighted)
                        r = (rng_obj.random() if rng_obj else _rand.random()) * total
                        acc = 0.0
                        for idx, (n, w) in enumerate(weighted):
                            acc += w
                            if r <= acc:
                                shuffled.append(n)
                                del weighted[idx]
                                break
                    pair_buckets[key] = shuffled
                except Exception:
                    pair_buckets[key] = names  # fallback to deterministic order
            else:
                pair_buckets[key] = names

        import random
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        # Desired count heuristic: min(default/requested, capacity, size of all candidates)
        default_dual_target = getattr(bc, 'DUAL_LAND_DEFAULT_COUNT', 6)
        remaining_capacity = max(0, land_target - self._current_land_count())
        effective_default = min(default_dual_target, remaining_capacity if remaining_capacity>0 else len(pool), len(pool))
        if requested_count is None:
            desired = effective_default
        else:
            desired = max(0, int(requested_count))
        if desired == 0:
            self.output_func("Dual Lands: Desired count 0; skipping.")
            return

        # If at capacity attempt to free slots (basic swapping)
        if remaining_capacity == 0 and desired > 0:
            slots_needed = desired
            freed_slots = 0
            while freed_slots < slots_needed and self._count_basic_lands() > basic_floor:
                target_basic = self._choose_basic_to_trim()
                if not target_basic:
                    break
                if not self._decrement_card(target_basic):
                    break
                freed_slots += 1
            if freed_slots == 0:
                desired = 0
        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(pool))
        if desired<=0:
            self.output_func("Dual Lands: No capacity after trimming; skipping.")
            return

        # Build weighted candidate list using round-robin across color pairs
        chosen: list[str] = []
        bucket_keys = list(pair_buckets.keys())
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
                names = pair_buckets.get(k, [])
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

        self.output_func("\nDual Lands Added (Step 5):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")
        # Enforcement via wrapper

    def run_land_step5(self, requested_count: Optional[int] = None):
        self.add_dual_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Duals (Step 5)")

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
                try:
                    rng_obj = getattr(self, 'rng', None)
                    weighted = [(n, max(1, rank(n))+1) for n in names]
                    import random as _rand
                    shuffled: list[str] = []
                    while weighted:
                        total = sum(w for _, w in weighted)
                        r = (rng_obj.random() if rng_obj else _rand.random()) * total
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
        import random
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
    def add_misc_utility_lands(self, requested_count: Optional[int] = None):
        """Add miscellaneous utility lands chosen from the top N (default 30) remaining lands by EDHREC rank.

        Process:
          1. Build candidate set of remaining lands (not already in library, excluding basics & prior staples if desired).
          2. Filter out lands already added in earlier specialized steps.
          3. Sort by ascending edhrecRank (lower = more popular) and take top N (constant).
          4. Apply weighting: color-fixing lands (produce 2+ colors, have basic types, or include "add one mana of any color") get extra weight.
          5. Randomly select up to desired_count (or available capacity) using weighted sampling without replacement.
          6. Capacity aware: may trim basics down to 90% floor like other steps; stops when capacity or desired reached.

        requested_count overrides default. Default target is remaining nonbasic slots or heuristic 3-5 depending on colors.
        """
        # Ensure dataframes loaded
        if not self.files_to_load:
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add misc utility lands until color identity resolved: {e}")
                return
        df = self._combined_cards_df
        if df is None or df.empty:
            self.output_func("Misc Lands: No card pool loaded.")
            return

        # Land target and capacity
        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        current = self._current_land_count()
        remaining_capacity = max(0, land_target - current)
        if remaining_capacity <= 0:
            # We'll attempt basic swaps below if needed
            remaining_capacity = 0

        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        # Determine desired count
        if requested_count is not None:
            desired = max(0, int(requested_count))
        else:
            # Fill all remaining land capacity (goal: reach land_target this step)
            desired = max(0, land_target - current)
        if desired == 0:
            self.output_func("Misc Lands: No remaining land capacity; skipping.")
            return

        # Build candidate pool using helper
        basics = self._basic_land_names()
        already = set(self.card_library.keys())
        from . import builder_utils as bu
        top_n = getattr(bc, 'MISC_LAND_TOP_POOL_SIZE', 30)
        top_candidates = bu.select_top_land_candidates(df, already, basics, top_n)
        if not top_candidates:
            self.output_func("Misc Lands: No remaining candidate lands.")
            return

        # Weight calculation for color fixing
        weighted_pool: list[tuple[str,int]] = []
        base_weight_fix = getattr(bc, 'MISC_LAND_COLOR_FIX_PRIORITY_WEIGHT', 2)
        fetch_names = set()
        # Build a union of known fetch candidates from constants to recognize them in Step 7
        for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
            for nm in seq:
                fetch_names.add(nm)
        for nm in getattr(bc, 'GENERIC_FETCH_LANDS', []):
            fetch_names.add(nm)

        existing_fetch_count = bu.count_existing_fetches(self.card_library)
        fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
        remaining_fetch_slots = max(0, fetch_cap - existing_fetch_count)

        for edh_val, name, tline, text_lower in top_candidates:
            w = 1
            if bu.is_color_fixing_land(tline, text_lower):
                w *= base_weight_fix
            # If this candidate is a fetch but we've hit the fetch cap, zero weight it so it won't be chosen
            if name in fetch_names and remaining_fetch_slots <= 0:
                continue
            weighted_pool.append((name, w))

        # Capacity freeing if needed
        if self._current_land_count() >= land_target and desired > 0:
            slots_needed = desired
            freed = 0
            while freed < slots_needed and self._count_basic_lands() > basic_floor:
                target_basic = self._choose_basic_to_trim()
                if not target_basic or not self._decrement_card(target_basic):
                    break
                freed += 1
            if freed == 0 and self._current_land_count() >= land_target:
                self.output_func("Misc Lands: Cannot free capacity; skipping.")
                return

        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(weighted_pool))
        if desired <= 0:
            self.output_func("Misc Lands: No capacity after trimming; skipping.")
            return

        # Weighted random selection without replacement
        rng = getattr(self, 'rng', None)
        chosen = bu.weighted_sample_without_replacement(weighted_pool, desired, rng=rng)

        added: list[str] = []
        for nm in chosen:
            if self._current_land_count() >= land_target:
                break
            self.add_card(nm, card_type='Land')
            added.append(nm)

        self.output_func("\nMisc Utility Lands Added (Step 7):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                note = ''
                row = next((r for r in top_candidates if r[1] == n), None)
                if row:
                    for edh_val, name2, tline2, text_lower2 in top_candidates:
                        if name2 == n and bu.is_color_fixing_land(tline2, text_lower2):
                            note = '(fixing)'
                            break
                self.output_func(f"  {n.ljust(width)} : 1  {note}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step7(self, requested_count: Optional[int] = None):
        self.add_misc_utility_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Utility (Step 7)")
        # Build and attempt to apply tag-driven suggestions (light augmentation)
        self._build_tag_driven_land_suggestions()
        self._apply_land_suggestions_if_room()

    # ---------------------------
    # Land Building Step 8: ETB Tapped Minimization / Optimization Pass
    # ---------------------------
    def optimize_tapped_lands(self):
        """Attempt to reduce number of slow ETB tapped lands if exceeding bracket threshold.

        Logic:
          1. Determine threshold from power bracket (defaults if absent).
          2. Classify each land in current library as tapped or untapped (heuristic via text).
             - Treat shocks ("you may pay 2 life") as untapped potential (not counted towards tapped threshold).
             - Treat conditional untap ("unless you control", "if you control") as half-penalty (still counted but lower priority to remove).
          3. If tapped_count <= threshold: exit.
          4. Score tapped lands by penalty; higher penalty = more likely swap out.
             Penalty factors:
               +8 base if always tapped.
               -3 if provides 3+ basic types (tri land) or adds any color.
               -2 if cycling.
               -2 if conditional untap ("unless you control", "if you control", "you may pay 2 life").
               +1 if only colorless production.
               +1 if minor upside (gain life) instead of speed.
          5. Build candidate replacement pool of untapped or effectively fast lands not already in deck:
               - Prioritize dual typed lands we missed, pain lands, shocks (if missing), basics if needed as fallback.
          6. Swap worst offenders until tapped_count <= threshold or replacements exhausted.
          7. Report swaps.
        """
        # Need card pool dataframe
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            return
        # Gather threshold
        bracket_level = getattr(self, 'bracket_level', None)
        threshold_map = getattr(bc, 'TAPPED_LAND_MAX_THRESHOLDS', {5:6,4:8,3:10,2:12,1:14})
        threshold = threshold_map.get(bracket_level, 10)

        # Build quick lookup for card rows by name (first occurrence)
        name_to_row: dict[str, dict] = {}
        for _, row in df.iterrows():
            nm = str(row.get('name',''))
            if nm and nm not in name_to_row:
                name_to_row[nm] = row.to_dict()

        tapped_info: list[tuple[str,int,int]] = []  # (name, penalty, tapped_flag 1/0)
        total_tapped = 0
        from . import builder_utils as bu
        for name, entry in list(self.card_library.items()):
            # Only consider lands
            row = name_to_row.get(name)
            if not row:
                continue
            tline = str(row.get('type', row.get('type_line',''))).lower()
            if 'land' not in tline:
                continue
            text_field = str(row.get('text', row.get('oracleText',''))).lower()
            tapped_flag, penalty = bu.tapped_land_penalty(tline, text_field)
            if tapped_flag:
                total_tapped += 1
                tapped_info.append((name, penalty, tapped_flag))

        if total_tapped <= threshold:
            self.output_func(f"Tapped Optimization (Step 8): {total_tapped} tapped/conditional lands (threshold {threshold}); no changes.")
            return

        # Determine how many to replace
        over = total_tapped - threshold
        swap_min_penalty = getattr(bc, 'TAPPED_LAND_SWAP_MIN_PENALTY', 6)
        # Sort by penalty descending
        tapped_info.sort(key=lambda x: x[1], reverse=True)
        to_consider = [t for t in tapped_info if t[1] >= swap_min_penalty]
        if not to_consider:
            self.output_func(f"Tapped Optimization (Step 8): Over threshold ({total_tapped}>{threshold}) but no suitable swaps (penalties too low).")
            return

        # Build replacement candidate pool: untapped multi-color first
        replacement_candidates: list[str] = []
        seen = set(self.card_library.keys())
        colors = [c for c in self.color_identity if c in ['W','U','B','R','G']]
        for _, row in df.iterrows():
            try:
                name = str(row.get('name',''))
                if not name or name in seen or name in replacement_candidates:
                    continue
                tline = str(row.get('type', row.get('type_line',''))).lower()
                if 'land' not in tline:
                    continue
                text_field = str(row.get('text', row.get('oracleText',''))).lower()
                if 'enters the battlefield tapped' in text_field and 'you may pay 2 life' not in text_field and 'unless you control' not in text_field:
                    # Hard tapped, skip as replacement
                    continue
                # Color relevance: if produces at least one deck color or has matching basic types
                produces_color = any(sym in text_field for sym in ['{w}','{u}','{b}','{r}','{g}'])
                basic_types = [b for b in ['plains','island','swamp','mountain','forest'] if b in tline]
                mapped = set()
                for b in basic_types:
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
                if not produces_color and not (mapped & set(colors)):
                    continue
                replacement_candidates.append(name)
            except Exception:
                continue

        # Simple ranking: prefer shocks / pain / dual typed, then any_color, then others
        def repl_rank(name: str) -> int:
            row = name_to_row.get(name, {})
            tline = str(row.get('type', row.get('type_line','')))
            text_field = str(row.get('text', row.get('oracleText','')))
            return bu.replacement_land_score(name, tline, text_field)
        replacement_candidates.sort(key=repl_rank, reverse=True)

        swaps_made: list[tuple[str,str]] = []
        idx_rep = 0
        for name, penalty, _ in to_consider:
            if over <= 0:
                break
            # Remove this tapped land
            if not self._decrement_card(name):
                continue
            # Find replacement
            replacement = None
            while idx_rep < len(replacement_candidates):
                cand = replacement_candidates[idx_rep]
                idx_rep += 1
                # Skip if would exceed fetch cap
                if cand in getattr(bc, 'GENERIC_FETCH_LANDS', []) or any(cand in lst for lst in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values()):
                    # Count existing fetches
                    fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
                    existing_fetches = sum(1 for n in self.card_library if n in getattr(bc, 'GENERIC_FETCH_LANDS', []))
                    for lst in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
                        existing_fetches += sum(1 for n in self.card_library if n in lst)
                    if existing_fetches >= fetch_cap:
                        continue
                replacement = cand
                break
            # Fallback to a basic if no candidate
            if replacement is None:
                # Choose most needed basic by current counts vs color identity
                basics = self._basic_land_names()
                basic_counts = {b: self.card_library.get(b, {}).get('Count',0) for b in basics}
                # pick basic with lowest count among colors we use
                color_basic_map = {'W':'Plains','U':'Island','B':'Swamp','R':'Mountain','G':'Forest'}
                usable_basics = [color_basic_map[c] for c in colors if color_basic_map[c] in basics]
                usable_basics.sort(key=lambda b: basic_counts.get(b,0))
                replacement = usable_basics[0] if usable_basics else 'Wastes'
            self.add_card(replacement, card_type='Land')
            swaps_made.append((name, replacement))
            over -= 1

        if not swaps_made:
            self.output_func(f"Tapped Optimization (Step 8): Could not perform swaps; over threshold {total_tapped}>{threshold}.")
            return
        self.output_func("\nTapped Optimization (Step 8) Swaps:")
        for old, new in swaps_made:
            self.output_func(f"  Replaced {old} -> {new}")
        new_tapped = 0
        # Recount tapped
        for name, entry in self.card_library.items():
            row = name_to_row.get(name)
            if not row:
                continue
            text_field = str(row.get('text', row.get('oracleText',''))).lower()
            if 'enters the battlefield tapped' in text_field and 'you may pay 2 life' not in text_field:
                new_tapped += 1
        self.output_func(f"  Tapped Lands After : {new_tapped} (threshold {threshold})")

    def run_land_step8(self):
        self.optimize_tapped_lands()
        # Land count unchanged; still enforce cap to be safe
        self._enforce_land_cap(step_label="Tapped Opt (Step 8)")
        # Capture color source baseline after land optimization (once)
        if self.color_source_matrix_baseline is None:
            self.color_source_matrix_baseline = self._compute_color_source_matrix()

    # ---------------------------
    # Tag-driven utility suggestions
    # ---------------------------
    def _build_tag_driven_land_suggestions(self):
        from . import builder_utils as bu
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
    # Color source matrix & post-spell adjustment stub
    # ---------------------------
    def _compute_color_source_matrix(self) -> Dict[str, Dict[str,int]]:
        # Cached: recompute only if dirty
        if self._color_source_matrix_cache is not None and not self._color_source_cache_dirty:
            return self._color_source_matrix_cache
        from . import builder_utils as bu
        matrix = bu.compute_color_source_matrix(self.card_library, getattr(self, '_full_cards_df', None))
        self._color_source_matrix_cache = matrix
        self._color_source_cache_dirty = False
        return matrix

    # ---------------------------
    # Spell pip analysis helpers
    # ---------------------------
    def _compute_spell_pip_weights(self) -> Dict[str, float]:
        if self._spell_pip_weights_cache is not None and not self._spell_pip_cache_dirty:
            return self._spell_pip_weights_cache
        from . import builder_utils as bu
        weights = bu.compute_spell_pip_weights(self.card_library, self.color_identity)
        self._spell_pip_weights_cache = weights
        self._spell_pip_cache_dirty = False
        return weights

    def _current_color_source_counts(self) -> Dict[str,int]:
        matrix = self._compute_color_source_matrix()
        counts = {c:0 for c in ['W','U','B','R','G']}
        for name, colors in matrix.items():
            entry = self.card_library.get(name, {})
            copies = entry.get('Count',1)
            for c, v in colors.items():
                if v:
                    counts[c] += copies
        return counts

    def post_spell_land_adjust(self,
                               pip_weights: Optional[Dict[str,float]] = None,
                               color_shortfall_threshold: float = 0.15,
                               perform_swaps: bool = False,
                               max_swaps: int = 3):
        # Compute pip weights if not supplied
        if pip_weights is None:
            pip_weights = self._compute_spell_pip_weights()
        if self.color_source_matrix_baseline is None:
            self.color_source_matrix_baseline = self._compute_color_source_matrix()
        current_counts = self._current_color_source_counts()
        total_sources = sum(current_counts.values()) or 1
        source_share = {c: current_counts[c]/total_sources for c in current_counts}
        deficits: list[tuple[str,float,float,float]] = []  # color, pip_share, source_share, gap
        for c in ['W','U','B','R','G']:
            pip_share = pip_weights.get(c,0.0)
            s_share = source_share.get(c,0.0)
            gap = pip_share - s_share
            if gap > color_shortfall_threshold and pip_share > 0.0:
                deficits.append((c,pip_share,s_share,gap))
        self.output_func("\nPost-Spell Color Distribution Analysis:")
        self.output_func("  Color | Pip% | Source% | Diff%")
        for c in ['W','U','B','R','G']:
            self.output_func(f"   {c:>1}    {pip_weights.get(c,0.0)*100:5.1f}%   {source_share.get(c,0.0)*100:6.1f}%   {(pip_weights.get(c,0.0)-source_share.get(c,0.0))*100:6.1f}%")
        if not deficits:
            self.output_func("  No color deficits above threshold.")
        else:
            self.output_func("  Deficits (need more sources):")
            for c, pip_share, s_share, gap in deficits:
                self.output_func(f"    {c}: need +{gap*100:.1f}% sources (pip {pip_share*100:.1f}% vs sources {s_share*100:.1f}%)")
        if not perform_swaps or not deficits:
            self.output_func("  (No land swaps performed.)")
            return

        # ---------------------------
        # Simple swap engine: attempt to add lands for deficit colors
        # ---------------------------
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            self.output_func("  Swap engine: card pool unavailable; aborting swaps.")
            return

        # Rank deficit colors by largest gap first
        deficits.sort(key=lambda x: x[3], reverse=True)
        swaps_done: list[tuple[str,str]] = []  # (removed, added)

        # Precompute overrepresented colors to target for removal
        overages: Dict[str,float] = {}
        for c in ['W','U','B','R','G']:
            over = source_share.get(c,0.0) - pip_weights.get(c,0.0)
            if over > 0:
                overages[c] = over

        def removal_candidate(exclude_colors: set[str]) -> Optional[str]:
            from . import builder_utils as bu
            return bu.select_color_balance_removal(self, exclude_colors, overages)

        def addition_candidates(target_color: str) -> List[str]:
            from . import builder_utils as bu
            return bu.color_balance_addition_candidates(self, target_color, df)

        for color, _, _, gap in deficits:
            if len(swaps_done) >= max_swaps:
                break
            adds = addition_candidates(color)
            if not adds:
                continue
            to_add = adds[0]
            to_remove = removal_candidate({color})
            if not to_remove:
                continue
            if not self._decrement_card(to_remove):
                continue
            self.add_card(to_add, card_type='Land')
            self.card_library[to_add]['Role'] = 'color-fix'
            swaps_done.append((to_remove, to_add))

        if swaps_done:
            self.output_func("\nColor Balance Swaps Performed:")
            for old, new in swaps_done:
                self.output_func(f"  Replaced {old} -> {new}")
        else:
            self.output_func("  (No viable swaps executed.)")

    # ---------------------------
    # Land Cap Enforcement (applies after every non-basic step)
    # ---------------------------
    def _basic_land_names(self) -> set:
        """Return set of all basic (and snow basic) land names plus Wastes."""
        from . import builder_utils as bu
        return bu.basic_land_names()

    def _count_basic_lands(self) -> int:
        """Count total copies of basic lands currently in the library."""
        from . import builder_utils as bu
        return bu.count_basic_lands(self.card_library)

    def _choose_basic_to_trim(self) -> Optional[str]:
        """Return a basic land name to trim (highest count) or None."""
        from . import builder_utils as bu
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
        from . import builder_utils as bu
        bu.enforce_land_cap(self, step_label)

    # ===========================
    # Non-Land Addition: Creatures
    # ===========================
    def add_creatures(self):
        """Add creature cards distributed across selected themes (1-3).

        Unified logic replacing previous add_creatures_primary / add_creatures_by_themes.
        Weight scheme:
          1 theme: 100%
          2 themes: 60/40
          3 themes: 50/30/20
        Kindred multipliers applied only when >1 theme.
        Synergy prioritizes cards matching multiple selected themes.
        """
        import re
        import ast
        import math
        import random
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            self.output_func("Card pool not loaded; cannot add creatures.")
            return
        if 'type' not in df.columns:
            self.output_func("Card pool missing 'type' column; cannot add creatures.")
            return
        themes_ordered: list[tuple[str, str]] = []
        if self.primary_tag:
            themes_ordered.append(('primary', self.primary_tag))
        if self.secondary_tag:
            themes_ordered.append(('secondary', self.secondary_tag))
        if self.tertiary_tag:
            themes_ordered.append(('tertiary', self.tertiary_tag))
        if not themes_ordered:
            self.output_func("No themes selected; skipping creature addition.")
            return
        desired_total = (self.ideal_counts.get('creatures') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_CREATURE_COUNT', 25)
        n_themes = len(themes_ordered)
        if n_themes == 1:
            base_map = {'primary': 1.0}
        elif n_themes == 2:
            base_map = {'primary': 0.6, 'secondary': 0.4}
        else:
            base_map = {'primary': 0.5, 'secondary': 0.3, 'tertiary': 0.2}
        weights: dict[str, float] = {}
        boosted_roles: set[str] = set()
        if n_themes > 1:
            for role, tag in themes_ordered:
                w = base_map.get(role, 0.0)
                lt = tag.lower()
                if 'kindred' in lt or 'tribal' in lt:
                    mult = getattr(bc, 'WEIGHT_ADJUSTMENT_FACTORS', {}).get(f'kindred_{role}', 1.0)
                    w *= mult
                    boosted_roles.add(role)
                weights[role] = w
            total = sum(weights.values())
            if total > 1.0:
                for r in list(weights):
                    weights[r] /= total
            else:
                rem = 1.0 - total
                base_sum_unboosted = sum(base_map[r] for r,_t in themes_ordered if r not in boosted_roles)
                if rem > 1e-6 and base_sum_unboosted > 0:
                    for r,_t in themes_ordered:
                        if r not in boosted_roles:
                            weights[r] += rem * (base_map[r] / base_sum_unboosted)
        else:
            weights['primary'] = 1.0
        def _parse_theme_tags(val) -> list[str]:
            if isinstance(val, list):
                out: list[str] = []
                for v in val:
                    if isinstance(v, list):
                        out.extend(str(x) for x in v)
                    else:
                        out.append(str(v))
                return [s.strip() for s in out if s and s.strip()]
            if isinstance(val, str):
                s = val.strip()
                try:
                    parsed = ast.literal_eval(s)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
                if s.startswith('[') and s.endswith(']'):
                    s = s[1:-1]
                parts = [p.strip().strip("'\"") for p in s.split(',')]
                cleaned = []
                for p in parts:
                    if not p:
                        continue
                    q = re.sub(r"^[\[\s']+|[\]\s']+$", '', p)
                    if q:
                        cleaned.append(q)
                return cleaned
            return []
        creature_df = df[df['type'].str.contains('Creature', case=False, na=False)].copy()
        if creature_df.empty:
            self.output_func("No creature rows in dataset; skipping.")
            return
        selected_tags_lower = [t.lower() for _r,t in themes_ordered]
        if '_parsedThemeTags' not in creature_df.columns:
            creature_df['_parsedThemeTags'] = creature_df['themeTags'].apply(_parse_theme_tags)
        creature_df['_normTags'] = creature_df['_parsedThemeTags'].apply(lambda lst: [s.lower() for s in lst])
        creature_df['_multiMatch'] = creature_df['_normTags'].apply(lambda lst: sum(1 for t in selected_tags_lower if t in lst))
        base_top = 30
        top_n = int(base_top * getattr(bc, 'THEME_POOL_SIZE_MULTIPLIER', 2.0))
        synergy_bonus = getattr(bc, 'THEME_PRIORITY_BONUS', 1.2)
        total_added = 0
        added_names: list[str] = []
        per_theme_added: dict[str, list[str]] = {r: [] for r,_t in themes_ordered}
        for role, tag in themes_ordered:
            w = weights.get(role, 0.0)
            if w <= 0:
                continue
            remaining = max(0, desired_total - total_added)
            if remaining == 0:
                break
            target = int(math.ceil(desired_total * w * random.uniform(1.0, 1.1)))
            target = min(target, remaining)
            if target <= 0:
                continue
            tnorm = tag.lower()
            subset = creature_df[creature_df['_normTags'].apply(lambda lst, tn=tnorm: (tn in lst) or any(tn in x for x in lst))]
            if subset.empty:
                self.output_func(f"Theme '{tag}' produced no creature candidates.")
                continue
            if 'edhrecRank' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
            elif 'manaValue' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
            pool = subset.head(top_n).copy()
            pool = pool[~pool['name'].isin(added_names)]
            if pool.empty:
                continue
            weights_vec = [synergy_bonus if mm >= 2 else 1.0 for mm in pool['_multiMatch']]
            names_vec = pool['name'].tolist()
            chosen: list[str] = []
            try:
                for _ in range(min(target, len(names_vec))):
                    totw = sum(weights_vec)
                    if totw <= 0:
                        break
                    r = random.random() * totw
                    acc = 0.0
                    idx = 0
                    for i, wv in enumerate(weights_vec):
                        acc += wv
                        if r <= acc:
                            idx = i
                            break
                    chosen.append(names_vec.pop(idx))
                    weights_vec.pop(idx)
            except Exception:
                chosen = names_vec[:target]
            for nm in chosen:
                row = pool[pool['name']==nm].iloc[0]
                self.add_card(nm,
                              card_type=row.get('type','Creature'),
                              mana_cost=row.get('manaCost',''),
                              mana_value=row.get('manaValue', row.get('cmc','')),
                              creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                              tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [])
                added_names.append(nm)
                per_theme_added[role].append(nm)
                total_added += 1
                if total_added >= desired_total:
                    break
            self.output_func(f"Added {len(per_theme_added[role])} creatures for {role} theme '{tag}' (target {target}).")
            if total_added >= desired_total:
                break
        if total_added < desired_total:
            need = desired_total - total_added
            multi_pool = creature_df[~creature_df['name'].isin(added_names)].copy()
            multi_pool = multi_pool[multi_pool['_multiMatch'] > 0]
            if not multi_pool.empty:
                if 'edhrecRank' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
                elif 'manaValue' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
                fill = multi_pool['name'].tolist()[:need]
                for nm in fill:
                    row = multi_pool[multi_pool['name']==nm].iloc[0]
                    self.add_card(nm,
                                  card_type=row.get('type','Creature'),
                                  mana_cost=row.get('manaCost',''),
                                  mana_value=row.get('manaValue', row.get('cmc','')),
                                  creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                                  tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [])
                    added_names.append(nm)
                    total_added += 1
                    if total_added >= desired_total:
                        break
                self.output_func(f"Fill pass added {min(need, len(fill))} extra creatures (shortfall compensation).")
        self.output_func("\nCreatures Added:")
        for role, tag in themes_ordered:
            lst = per_theme_added.get(role, [])
            if lst:
                self.output_func(f"  {role.title()} '{tag}': {len(lst)}")
                for nm in lst:
                    self.output_func(f"    - {nm}")
            else:
                self.output_func(f"  {role.title()} '{tag}': 0")
        self.output_func(f"  Total {total_added}/{desired_total}{' (dataset shortfall)' if total_added < desired_total else ''}")

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
            from prettytable import PrettyTable, ALL
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
        # Add horizontal rules between all rows for clearer separation
        try:
            table.hrules = ALL  # type: ignore[attr-defined]
        except Exception:
            pass

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

                # Enrich basics (and snow basics) with canonical type line and oracle text
                basic_detail_map = {
                    'Plains': ('Basic Land — Plains', '{T}: Add {W}.'),
                    'Island': ('Basic Land — Island', '{T}: Add {U}.'),
                    'Swamp': ('Basic Land — Swamp', '{T}: Add {B}.'),
                    'Mountain': ('Basic Land — Mountain', '{T}: Add {R}.'),
                    'Forest': ('Basic Land — Forest', '{T}: Add {G}.'),
                    'Wastes': ('Basic Land', '{T}: Add {C}.'),
                    'Snow-Covered Plains': ('Basic Snow Land — Plains', '{T}: Add {W}.'),
                    'Snow-Covered Island': ('Basic Snow Land — Island', '{T}: Add {U}.'),
                    'Snow-Covered Swamp': ('Basic Snow Land — Swamp', '{T}: Add {B}.'),
                    'Snow-Covered Mountain': ('Basic Snow Land — Mountain', '{T}: Add {R}.'),
                    'Snow-Covered Forest': ('Basic Snow Land — Forest', '{T}: Add {G}.'),
                }
                if name in basic_detail_map:
                    canonical_type, canonical_text = basic_detail_map[name]
                    type_line = canonical_type
                    if not text_field:
                        text_field = canonical_text
                    # Ensure ci/colors set (if missing due to csv NaN)
                    if name in basic_names:
                        ci = rev_basic.get(name, ci)
                        colors = rev_basic.get(name, colors)
                    elif name in snow_basic_names:
                        ci = rev_snow.get(name, ci)
                        colors = rev_snow.get(name, colors)

                # Sanitize NaN / 'nan' strings for display cleanliness
                import math
                def _sanitize(val):
                    if val is None:
                        return ''
                    if isinstance(val, float) and math.isnan(val):
                        return ''
                    if isinstance(val, str) and val.lower() == 'nan':
                        return ''
                    return val
                mana_cost = _sanitize(mana_cost)
                mana_value = _sanitize(mana_value)
                type_line = _sanitize(type_line)
                creature_types = _sanitize(creature_types)
                power = _sanitize(power)
                toughness = _sanitize(toughness)
                keywords = _sanitize(keywords)
                theme_tags = _sanitize(theme_tags)
                text_field = _sanitize(text_field)
                ci = _sanitize(ci)
                colors = _sanitize(colors)

                # Strip embedded newline characters/sequences from text and theme tags for cleaner single-row display
                if text_field:
                    text_field = text_field.replace('\\n', ' ').replace('\n', ' ')
                    # Collapse multiple spaces
                    while '  ' in text_field:
                        text_field = text_field.replace('  ', ' ')
                if theme_tags:
                    theme_tags = theme_tags.replace('\n', ' ').replace('\\n', ' ')

            table.add_row([
                display_name,
                ci,
                colors,
                mana_cost,
                mana_value,
                self._wrap_cell(type_line, width=30),
                creature_types,
                power,
                toughness,
                keywords,
                self._wrap_cell(theme_tags, width=60),
                self._wrap_cell(text_field, prefer_long=True)
            ])

        self.output_func(table.get_string())

        # Tag summary (unique card counts per tag)
        if self.tag_counts:
            self.output_func("\nTag Summary (unique cards per tag):")

            def _clean_tag_key(tag: str) -> str:
                import re
                if not isinstance(tag, str):
                    tag = str(tag)
                s = tag.strip()
                # Remove common leading list artifacts like [', [" or ['
                s = re.sub(r"^\[+['\"]?", "", s)
                # Remove common trailing artifacts like '], ] or '] etc.
                s = re.sub(r"['\"]?\]+$", "", s)
                # Strip stray quotes again
                s = s.strip("'\"")
                # Collapse internal excessive whitespace
                s = ' '.join(s.split())
                return s

            # Aggregate counts by cleaned key to merge duplicates created by formatting artifacts
            aggregated: Dict[str, int] = {}
            for raw_tag, cnt in self.tag_counts.items():
                cleaned = _clean_tag_key(raw_tag)
                if not cleaned:
                    continue
                aggregated[cleaned] = aggregated.get(cleaned, 0) + cnt

            min_count = getattr(bc, 'TAG_SUMMARY_MIN_COUNT', 1)
            always_show_subs = [s.lower() for s in getattr(bc, 'TAG_SUMMARY_ALWAYS_SHOW_SUBSTRS', [])]
            printed = 0
            hidden = 0
            for tag, cnt in sorted(aggregated.items(), key=lambda kv: (-kv[1], kv[0].lower())):
                tag_l = tag.lower()
                force_show = any(sub in tag_l for sub in always_show_subs) if always_show_subs else False
                if cnt >= min_count or force_show:
                    self.output_func(f"  {tag}: {cnt}{' (low freq)' if force_show and cnt < min_count else ''}")
                    printed += 1
                else:
                    hidden += 1
            if hidden:
                self.output_func(f"  (+ {hidden} low-frequency tags hidden < {min_count})")

    # Internal helper for wrapping cell contents to keep table readable
    def _wrap_cell(self, text: str, width: int = 60, prefer_long: bool = False) -> str:
        """Word-wrap a cell's text.

        prefer_long: if True, uses a slightly larger width (e.g. for oracle text).
        """
        if not text:
            return ''
        if prefer_long:
            width = 80
        # Normalize whitespace but preserve existing newlines (treat each paragraph separately)
        import textwrap
        paragraphs = str(text).split('\n')
        wrapped_parts = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                wrapped_parts.append('')
                continue
            # If already shorter than width, keep
            if len(p) <= width:
                wrapped_parts.append(p)
                continue
            wrapped_parts.append('\n'.join(textwrap.wrap(p, width=width)))
        return '\n'.join(wrapped_parts)

    # Convenience to run Step 1 & 2 sequentially (future orchestrator)
    def run_deck_build_steps_1_2(self):
        self.run_deck_build_step1()
        self.run_deck_build_step2()
