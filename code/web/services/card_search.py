"""Scryfall-style search query parser/filter, shared by the public REST API
card browser (`code/web/routes/api_v1/cards.py`, used by the mobile app) and
the manual deck builder's off-pool card search (`manual_builder_service.py`).

The `q` search box supports plain text (matched against card name only,
the default) plus real Scryfall search keywords -- see
https://scryfall.com/docs/syntax. Only the categories relevant to this
dataset are supported: colors/identity, card types, card text, mana costs,
power/toughness, and loyalty; rarity/tag/is=new flags are also parsed as a
bonus but are secondary to any explicit `colors`/`tags`/`is_new` query params
a caller may also apply.

NOTE: bare colon (`:`) has different default semantics for color vs.
identity, matching how each concept is actually used:
  - `id:br` -- subset ("works with a black/red identity"): matches mono-B,
    mono-R, BR, and colorless cards. Same logic as the deck-builder's
    color-identity pool filtering. Use `id=br` for an exact-identity-only match.
  - `color:br` -- superset ("includes at least black and red"): also
    matches BRU, BRG, etc. Use `color=br` for an exact-colors-only match.

Examples: `c:rg`, `id<=esper`, `t:goblin -t:creature`, `o:"draw a card"`,
`m:2WW`, `mv>=4`, `pow>=4 tou<=2`, `pow>tou`, `loy>=5`. Any keyword may be
negated with a leading `-` (e.g. `-t:land`); plain words without a keyword
match (or exclude, with `-`) the card name.
"""
from __future__ import annotations

import os
import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from code.deck_builder.builder_utils import parse_theme_tags
from code.deck_builder.tokens import load_tokens_browser_df
from code.path_util import card_files_processed_dir


def parse_color_cell(raw: Any) -> set:
    """Parse a `colors`/`colorIdentity`-style cell into a set of color
    letters (empty set for colorless). Cells use a comma delimiter, with or
    without a following space, depending on the source column."""
    if not raw or not isinstance(raw, str):
        return set()
    if raw.strip().lower() == "colorless":
        return set()
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def _hyphen_flex_pattern(term: str) -> str:
    """Build a regex from a substring search term that treats `-` and
    whitespace as interchangeable, so e.g. `t:legendary-creature` also
    matches "Legendary Creature" without needing quotes. Cards whose real
    name/type/text already contains a literal hyphen (e.g. Krark-Clan Ogre)
    still match normally, since a hyphen in the term also matches a hyphen
    in the target text."""
    parts = [re.escape(p) for p in re.split(r"[-\s]+", term.strip()) if p]
    return r"[-\s]+".join(parts) if parts else re.escape(term)


def normalize_word_sep(value: str) -> str:
    """Collapse `-`/whitespace runs to a single space and lowercase, so
    exact-match tag values (theme/art tags) can be typed with hyphens
    instead of quoted spaces, e.g. `tag:spot-removal` == `tag:"Spot Removal"`.
    Used on both the parsed search value and the card's own tag strings, so
    it's symmetric regardless of which one uses a hyphen vs. a space."""
    return re.sub(r"[-\s]+", " ", value.strip()).lower()


_FLAG_TOKEN_RE = re.compile(r"^(-)?([A-Za-z]+)(:|>=|<=|!=|>|<|=)(.+)$")

_KEY_ALIASES: Dict[str, str] = {
    "name": "name", "n": "name",
    "type": "type", "t": "type",
    "oracle": "oracle", "text": "oracle", "o": "oracle",
    "color": "color", "c": "color",
    "identity": "identity", "id": "identity",
    "power": "power", "pow": "power",
    "toughness": "toughness", "tou": "toughness", "tough": "toughness",
    "loyalty": "loyalty", "loy": "loyalty",
    "mana": "manacost", "m": "manacost",
    "manavalue": "cmc", "mv": "cmc", "cmc": "cmc",
    "rarity": "rarity", "r": "rarity",
    "tag": "tag", "theme": "tag",
    "art": "arttag", "atag": "arttag", "arttag": "arttag",
    "metadata": "metadatatag", "mtag": "metadatatag", "metatag": "metadatatag",
    "is": "is",
    "set": "set", "s": "set", "e": "set", "edition": "set",
    "cn": "collector_number", "number": "collector_number",
}

_COLOR_LETTERS = set("WUBRG")
_STAT_VALUE_ALIASES = {
    "power": "power", "pow": "power",
    "toughness": "toughness", "tou": "toughness", "tough": "toughness",
    "loyalty": "loyalty", "loy": "loyalty",
}
_BRACED_SYMBOL_RE = re.compile(r"\{([^}]+)\}")

# Full color names, guild names (2-color), and shard/wedge names (3-color) --
# resolve to the same letter set regardless of which order the name/letters
# are given in, e.g. `rg`, `gr`, and `gruul` are all equivalent.
_COLOR_NICKNAMES: Dict[str, Set[str]] = {
    "white": {"W"}, "blue": {"U"}, "black": {"B"}, "red": {"R"}, "green": {"G"},
    # Guilds
    "azorius": {"W", "U"}, "dimir": {"U", "B"}, "rakdos": {"B", "R"},
    "gruul": {"R", "G"}, "selesnya": {"G", "W"}, "orzhov": {"W", "B"},
    "izzet": {"U", "R"}, "golgari": {"B", "G"}, "boros": {"R", "W"},
    "simic": {"G", "U"},
    # Shards and wedges
    "bant": {"G", "W", "U"}, "esper": {"W", "U", "B"}, "grixis": {"U", "B", "R"},
    "jund": {"B", "R", "G"}, "naya": {"R", "G", "W"}, "abzan": {"W", "B", "G"},
    "jeskai": {"U", "R", "W"}, "sultai": {"B", "G", "U"}, "mardu": {"R", "W", "B"},
    "temur": {"G", "U", "R"},
    # Five-color
    "wubrg": set(_COLOR_LETTERS), "rainbow": set(_COLOR_LETTERS), "five-color": set(_COLOR_LETTERS),
}


@dataclass
class ColorClause:
    op: str
    letters: Set[str] = field(default_factory=set)
    count: Optional[int] = None
    special: Optional[str] = None  # "colorless" | "multicolor" | None
    negate: bool = False


@dataclass
class NumericClause:
    op: str
    value: Optional[float] = None
    compare_to: Optional[str] = None  # cross-field, e.g. "pow>tou"
    negate: bool = False


@dataclass
class ManaCostClause:
    op: str
    generic: int = 0
    symbols: Counter = field(default_factory=Counter)
    negate: bool = False


@dataclass
class CollectorNumberClause:
    """A `cn:`/`number:` clause. `:`/`=`/`!=` compare the raw (leading-zero-
    normalized) string, so suffixed numbers like `123a`/`123*` still work;
    `>`/`<`/`>=`/`<=` require a numeric prefix (non-numeric values are
    excluded from the comparison, not errored -- same convention as
    power/toughness `*`)."""
    op: str
    value: str
    negate: bool = False


@dataclass
class ParsedSearch:
    name_include: List[str] = field(default_factory=list)
    name_exclude: List[str] = field(default_factory=list)
    explicit_name_flag: bool = False
    type_include: List[str] = field(default_factory=list)
    type_exclude: List[str] = field(default_factory=list)
    oracle_include: List[str] = field(default_factory=list)
    oracle_exclude: List[str] = field(default_factory=list)
    color_clauses: List[ColorClause] = field(default_factory=list)
    identity_clauses: List[ColorClause] = field(default_factory=list)
    power_clauses: List[NumericClause] = field(default_factory=list)
    toughness_clauses: List[NumericClause] = field(default_factory=list)
    loyalty_clauses: List[NumericClause] = field(default_factory=list)
    cmc_clauses: List[NumericClause] = field(default_factory=list)
    mana_cost_clauses: List[ManaCostClause] = field(default_factory=list)
    rarity: Optional[Set[str]] = None
    tags: Optional[Set[str]] = None
    tags_exclude: Optional[Set[str]] = None
    art_tags: Optional[Set[str]] = None
    art_tags_exclude: Optional[Set[str]] = None
    metadata_tags: Optional[Set[str]] = None
    metadata_tags_exclude: Optional[Set[str]] = None
    is_new: Optional[bool] = None
    set_include: Set[str] = field(default_factory=set)
    set_exclude: Set[str] = field(default_factory=set)
    collector_number_clauses: List[CollectorNumberClause] = field(default_factory=list)
    notices: List[str] = field(default_factory=list)


def _parse_color_value(value: str) -> Tuple[Set[str], Optional[int], Optional[str]]:
    """Parse a color/identity flag value into (letters, count, special).
    Only one of the three will be populated -- e.g. `c` (colorless), `m`
    (multicolor), a bare number (color count), color letters (any order,
    e.g. `rg`/`gr`), or a full name/guild/shard/wedge nickname (e.g.
    `green`, `gruul`, `esper` -- see _COLOR_NICKNAMES)."""
    v = value.strip().lower()
    if v in ("c", "colorless"):
        return set(), None, "colorless"
    if v in ("m", "multicolor"):
        return set(), None, "multicolor"
    if v.lstrip("-").isdigit():
        return set(), int(v), None
    if v in _COLOR_NICKNAMES:
        return set(_COLOR_NICKNAMES[v]), None, None
    letters = {ch for ch in v.upper() if ch in _COLOR_LETTERS}
    return letters, None, None


def _compare_numeric(actual: Any, op: str, expected: Any) -> Any:
    """Apply a comparison operator; works for both scalars and pandas Series."""
    if op in (":", "="):
        return actual == expected
    if op == ">":
        return actual > expected
    if op == "<":
        return actual < expected
    if op == ">=":
        return actual >= expected
    if op == "<=":
        return actual <= expected
    if op == "!=":
        return actual != expected
    return False


def _color_matches(card_letters: Set[str], clause: ColorClause) -> bool:
    if clause.special == "colorless":
        matched = len(card_letters) == 0
    elif clause.special == "multicolor":
        matched = len(card_letters) >= 2
    elif clause.count is not None:
        matched = bool(_compare_numeric(len(card_letters), clause.op, clause.count))
    else:
        req = clause.letters
        op = clause.op
        if op in (":", "="):
            matched = card_letters == req
        elif op == ">=":
            matched = req.issubset(card_letters)
        elif op == "<=":
            matched = card_letters.issubset(req)
        elif op == ">":
            matched = req.issubset(card_letters) and card_letters != req
        elif op == "<":
            matched = card_letters.issubset(req) and card_letters != req
        elif op == "!=":
            matched = card_letters != req
        else:
            matched = False
    return (not matched) if clause.negate else matched


def apply_color_clauses(df: "pd.DataFrame", column: str, clauses: List[ColorClause]) -> "pd.DataFrame":
    if not clauses or column not in df.columns:
        return df

    def _row_matches(raw: Any) -> bool:
        card_letters = parse_color_cell(raw)
        return all(_color_matches(card_letters, clause) for clause in clauses)

    return df[df[column].apply(_row_matches)]


def apply_numeric_clauses(df: "pd.DataFrame", column: str, clauses: List[NumericClause]) -> "pd.DataFrame":
    """Filter `df` by numeric comparisons on `column`, coercing non-numeric
    values (e.g. "*" power/toughness) to NaN and excluding them. Supports
    cross-field comparisons like `pow>tou` via `compare_to`."""
    if not clauses or column not in df.columns:
        return df
    numeric = pd.to_numeric(df[column], errors="coerce")
    mask = pd.Series(True, index=df.index)
    for clause in clauses:
        if clause.compare_to and clause.compare_to in df.columns:
            other = pd.to_numeric(df[clause.compare_to], errors="coerce")
        else:
            other = clause.value
        clause_mask = _compare_numeric(numeric, clause.op, other).fillna(False)
        if clause.negate:
            clause_mask = ~clause_mask
        mask &= clause_mask
    return df[mask]


def _tokenize_mana_shorthand(text: str) -> List[str]:
    """Tokenize non-braced mana shorthand (e.g. "2WW") into symbols,
    grouping consecutive digits into one generic-mana symbol."""
    tokens: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(text[i:j])
            i = j
        elif ch.isalpha():
            tokens.append(ch.upper())
            i += 1
        else:
            i += 1
    return tokens


def parse_mana_cost(cost: str) -> Tuple[int, Counter]:
    """Parse a mana cost string -- braced like "{2}{W}{W}" (as stored in the
    dataset) or Scryfall shorthand like "2WW" (as typed by a user) -- into
    (generic_total, Counter of other symbols)."""
    generic = 0
    symbols: Counter = Counter()
    if not cost or not isinstance(cost, str):
        return generic, symbols
    braced = _BRACED_SYMBOL_RE.findall(cost)
    remainder = _BRACED_SYMBOL_RE.sub("", cost)
    tokens = list(braced) + _tokenize_mana_shorthand(remainder)
    for tok in tokens:
        if tok.isdigit():
            generic += int(tok)
        else:
            symbols[tok.upper()] += 1
    return generic, symbols


def _mana_cost_superset(card: Tuple[int, Counter], query: Tuple[int, Counter]) -> bool:
    card_generic, card_symbols = card
    query_generic, query_symbols = query
    if card_generic < query_generic:
        return False
    return all(card_symbols.get(sym, 0) >= count for sym, count in query_symbols.items())


def _mana_cost_equal(card: Tuple[int, Counter], query: Tuple[int, Counter]) -> bool:
    card_generic, card_symbols = card
    query_generic, query_symbols = query
    return card_generic == query_generic and dict(card_symbols) == dict(query_symbols)


def _mana_cost_matches(cost: Any, clause: ManaCostClause) -> bool:
    card = parse_mana_cost(cost)
    query = (clause.generic, clause.symbols)
    op = clause.op
    if op in (":", ">="):
        matched = _mana_cost_superset(card, query)
    elif op == ">":
        matched = _mana_cost_superset(card, query) and not _mana_cost_equal(card, query)
    elif op == "<=":
        matched = _mana_cost_superset(query, card)
    elif op == "<":
        matched = _mana_cost_superset(query, card) and not _mana_cost_equal(card, query)
    elif op == "=":
        matched = _mana_cost_equal(card, query)
    elif op == "!=":
        matched = not _mana_cost_equal(card, query)
    else:
        matched = False
    return (not matched) if clause.negate else matched


def apply_mana_cost_clauses(df: "pd.DataFrame", clauses: List[ManaCostClause]) -> "pd.DataFrame":
    if not clauses or "manaCost" not in df.columns:
        return df
    return df[df["manaCost"].apply(lambda raw: all(_mana_cost_matches(raw, c) for c in clauses))]


def apply_text_clauses(df: "pd.DataFrame", column: str, include: List[str], exclude: List[str]) -> "pd.DataFrame":
    if column not in df.columns:
        return df
    for term in include:
        df = df[df[column].str.contains(_hyphen_flex_pattern(term), case=False, na=False, regex=True)]
    for term in exclude:
        df = df[~df[column].str.contains(_hyphen_flex_pattern(term), case=False, na=False, regex=True)]
    return df


_FUZZY_NAME_THRESHOLD = 0.6


def _normalize_fuzzy_name(value: str) -> str:
    """Lowercase, alphanumeric-only tokens, so punctuation differences
    (apostrophes, commas, hyphens) don't block a name match."""
    if not value:
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def apply_name_clauses(df: "pd.DataFrame", include: List[str], exclude: List[str]) -> "pd.DataFrame":
    """Filter by card name: each `include` term must appear as a substring
    (AND'd together, case-insensitive), each `exclude` term must not.

    Falls back to typo/punctuation-tolerant fuzzy matching (SequenceMatcher
    on alphanumeric-only tokens) when the strict substring filter yields
    zero rows, so e.g. "Rogues Passage" still finds "Rogue's Passage".
    """
    if "name" not in df.columns:
        return df
    strict = df
    for term in include:
        strict = strict[strict["name"].str.contains(_hyphen_flex_pattern(term), case=False, na=False, regex=True)]
    for term in exclude:
        strict = strict[~strict["name"].str.contains(_hyphen_flex_pattern(term), case=False, na=False, regex=True)]
    if not include or not strict.empty:
        return strict

    query = _normalize_fuzzy_name(" ".join(include))
    if not query:
        return strict

    scores = df["name"].astype(str).apply(lambda n: SequenceMatcher(None, query, _normalize_fuzzy_name(n)).ratio())
    fuzzy = df[scores >= _FUZZY_NAME_THRESHOLD]
    for term in exclude:
        fuzzy = fuzzy[~fuzzy["name"].str.contains(_hyphen_flex_pattern(term), case=False, na=False, regex=True)]
    return fuzzy


def filter_names_fuzzy(names: List[str], include: List[str], exclude: List[str]) -> List[str]:
    """List-based sibling of `apply_name_clauses`, for callers (the Owned
    Library) that filter a plain list of names rather than a DataFrame.
    Same strict-substring-then-fuzzy-fallback behavior."""
    def _strict(pool: List[str]) -> List[str]:
        for term in include:
            regex = re.compile(_hyphen_flex_pattern(term), re.IGNORECASE)
            pool = [n for n in pool if regex.search(n)]
        for term in exclude:
            regex = re.compile(_hyphen_flex_pattern(term), re.IGNORECASE)
            pool = [n for n in pool if not regex.search(n)]
        return pool

    strict = _strict(names)
    if not include or strict:
        return strict

    query = _normalize_fuzzy_name(" ".join(include))
    if not query:
        return strict

    fuzzy = [n for n in names if SequenceMatcher(None, query, _normalize_fuzzy_name(n)).ratio() >= _FUZZY_NAME_THRESHOLD]
    for term in exclude:
        regex = re.compile(_hyphen_flex_pattern(term), re.IGNORECASE)
        fuzzy = [n for n in fuzzy if not regex.search(n)]
    return fuzzy


_SET_NAME_MAP: Optional[Dict[str, str]] = None  # normalized set name -> uppercase code
_SET_CODES: Optional[Set[str]] = None  # every known uppercase code
_SET_RELEASE_BY_CODE: Optional[Dict[str, str]] = None  # code -> most recent released_at string


def _load_set_index() -> Tuple[Dict[str, str], Set[str], Dict[str, str]]:
    """Lazily build (and cache for the process lifetime) a set-name/code index
    from `card_files/processed/card_printings.parquet`'s `set`/`set_name`/
    `released_at` columns, so `set:` can resolve full set names in addition
    to codes without a new Scryfall bulk-data fetch. Returns empty
    structures (never raises) if the printings index hasn't been built yet."""
    global _SET_NAME_MAP, _SET_CODES, _SET_RELEASE_BY_CODE
    if _SET_NAME_MAP is not None and _SET_CODES is not None and _SET_RELEASE_BY_CODE is not None:
        return _SET_NAME_MAP, _SET_CODES, _SET_RELEASE_BY_CODE

    name_map: Dict[str, str] = {}
    codes: Set[str] = set()
    release_by_code: Dict[str, str] = {}
    try:
        path = os.path.join(card_files_processed_dir(), "card_printings.parquet")
        df = pd.read_parquet(path, columns=["set", "set_name", "released_at"])
        grouped = df.dropna(subset=["set"]).groupby("set").agg({"set_name": "first", "released_at": "max"})
        for code, row in grouped.iterrows():
            code_upper = str(code).strip().upper()
            if not code_upper:
                continue
            codes.add(code_upper)
            release_by_code[code_upper] = str(row["released_at"] or "")
            set_name = row["set_name"]
            if set_name:
                name_map[normalize_word_sep(str(set_name))] = code_upper
    except Exception:
        name_map, codes, release_by_code = {}, set(), {}

    _SET_NAME_MAP, _SET_CODES, _SET_RELEASE_BY_CODE = name_map, codes, release_by_code
    return name_map, codes, release_by_code


def _resolve_set_value(value: str) -> Tuple[str, Optional[str]]:
    """Resolve a `set:` flag's raw value into a set code, accepting either a
    real set code (e.g. `khm`) or a full set name (e.g. `kaldheim`), using
    `card_files/processed/card_printings.parquet` as the name/code index.

    Returns `(code, notice)`: `code` is always populated (falls back to the
    raw alnum-stripped-uppercase value if nothing resolves, so an unknown or
    unindexed code still behaves exactly as before); `notice` is a human-
    readable "Did you mean" message when a name substring matched more than
    one set, else `None`.
    """
    raw_code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    name_map, codes, release_by_code = _load_set_index()

    if raw_code and raw_code in codes:
        return raw_code, None

    normalized = normalize_word_sep(value)
    if normalized in name_map:
        return name_map[normalized], None

    candidates = sorted({(name, code) for name, code in name_map.items() if normalized and normalized in name})
    if candidates:
        # Stable-sort least-significant-key-first: most recent release wins
        # ties, then shortest (closest-to-exact) name wins overall.
        candidates.sort(key=lambda pair: release_by_code.get(pair[1], ""), reverse=True)
        candidates.sort(key=lambda pair: len(pair[0]))
        chosen_name, chosen_code = candidates[0]
        if len(candidates) > 1:
            alternates = ", ".join(f"{n.title()} ({c})" for n, c in candidates[1:6])
            notice = (
                f"'{value}' matched multiple sets -- using '{chosen_name.title()}' ({chosen_code}). "
                f"Also matched: {alternates}. Use set:CODE to be specific."
            )
            return chosen_code, notice
        return chosen_code, None

    return raw_code, None


_PRINTINGS_INDEX_DF: Optional["pd.DataFrame"] = None
_PRINTINGS_INDEX_LOADED: bool = False


def _load_printings_index_df() -> Optional["pd.DataFrame"]:
    """Lazily load (and cache for the process lifetime)
    `card_files/processed/card_printings.parquet`'s per-printing rows, used
    to resolve `cn:`/`number:` clauses (collector number is per-printing,
    not on the collapsed `all_cards.parquet` row). Returns `None` (never
    raises) if the printings index hasn't been built yet."""
    global _PRINTINGS_INDEX_DF, _PRINTINGS_INDEX_LOADED
    if _PRINTINGS_INDEX_LOADED:
        return _PRINTINGS_INDEX_DF
    try:
        path = os.path.join(card_files_processed_dir(), "card_printings.parquet")
        _PRINTINGS_INDEX_DF = pd.read_parquet(
            path, columns=["face_name", "set", "collector_number", "scryfall_id", "score", "released_at"]
        )
    except Exception:
        _PRINTINGS_INDEX_DF = None
    _PRINTINGS_INDEX_LOADED = True
    return _PRINTINGS_INDEX_DF


def _collector_number_numeric_prefix(value: str) -> Optional[float]:
    m = re.match(r"^0*(\d+)", str(value).strip())
    return float(m.group(1)) if m else None


def _collector_number_normalized(value: str) -> str:
    """Strip leading zeros while keeping any suffix, e.g. `007` -> `7`,
    `007a` -> `7a`, so formatting differences between sets don't break an
    exact-equality match."""
    s = str(value).strip()
    m = re.match(r"^0*(\d+)(.*)$", s)
    return (m.group(1) + m.group(2)) if m else s


def _collector_number_match_mask(subset: "pd.DataFrame", clauses: List[CollectorNumberClause]) -> "pd.Series":
    """Boolean mask over a `card_printings.parquet` slice (`subset`) marking
    rows satisfying every clause in `clauses` (ANDed)."""
    actual_raw = subset["collector_number"].astype(str)
    actual_norm = actual_raw.apply(_collector_number_normalized)
    actual_num = actual_raw.apply(_collector_number_numeric_prefix)

    mask = pd.Series(True, index=subset.index)
    for clause in clauses:
        if clause.op in (":", "=", "!="):
            target = _collector_number_normalized(clause.value)
            matched = (actual_norm != target) if clause.op == "!=" else (actual_norm == target)
        else:
            expected = _collector_number_numeric_prefix(clause.value)
            matched = pd.Series(False, index=subset.index)
            if expected is not None:
                valid = actual_num.notna()
                matched.loc[valid] = _compare_numeric(actual_num[valid], clause.op, expected)
        if clause.negate:
            matched = ~matched
        mask &= matched
    return mask


def resolve_collector_number_printings(parsed: ParsedSearch) -> Dict[str, str]:
    """For a query combining `set:` with `cn:`/`number:`, resolve each
    matching card to one specific printing's `scryfall_id` -- an exact-
    equality clause naturally narrows to a single printing; a range clause
    (`cn>50`) narrows to the best-scored printing among the matched range
    (highest `score`, tie-broken by most recent `released_at`, mirroring
    `ImageCache.get_default_printing_id()`'s convention). Returns
    `{card-name-lower: scryfall_id}`, empty if `cn:`/`number:` wasn't used,
    has no `set:` to pair with, or the printings index is unavailable."""
    if not parsed.collector_number_clauses or not parsed.set_include:
        return {}
    printings = _load_printings_index_df()
    if printings is None or printings.empty:
        return {}
    subset = printings[printings["set"].astype(str).str.upper().isin(parsed.set_include)]
    if subset.empty:
        return {}
    matched = subset.loc[_collector_number_match_mask(subset, parsed.collector_number_clauses)]
    if matched.empty:
        return {}
    matched = matched.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
    overlay: Dict[str, str] = {}
    for _, row in matched.iterrows():
        overlay.setdefault(str(row["face_name"]).lower(), str(row["scryfall_id"]))
    return overlay


def get_set_collector_number_sort_map(set_code: str) -> Dict[str, float]:
    """Maps each card name (lowercase) with a printing in `set_code` to that
    printing's collector number (numeric prefix), for ordering a single-set
    search by collector number instead of alphabetically. When a card has
    more than one printing in the set, uses the best-scored one (same
    tie-break as `ImageCache.get_printing_id_for_set()`). Returns `{}` if
    the printings index is unavailable."""
    printings = _load_printings_index_df()
    if printings is None or printings.empty:
        return {}
    subset = printings[printings["set"].astype(str).str.upper() == set_code]
    if subset.empty:
        return {}
    subset = subset.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
    sort_map: Dict[str, float] = {}
    for _, row in subset.iterrows():
        key = str(row["face_name"]).lower()
        if key in sort_map:
            continue
        num = _collector_number_numeric_prefix(row["collector_number"])
        sort_map[key] = num if num is not None else float("inf")
    return sort_map


def get_set_scoped_collector_number_sort_map(
    set_codes: "Set[str] | List[str]",
    collector_number_clauses: Optional[List["CollectorNumberClause"]] = None,
) -> Dict[str, Tuple[float, str]]:
    """Like `get_set_collector_number_sort_map()`, but for one or more sets
    at once and aware of any `cn:`/`number:` clauses already applied to the
    query. Maps each card name (lowercase) to `(numeric collector number,
    set code)` so results can be ordered by collector number first, then by
    set code alphabetically (a tiebreaker for multi-set queries, e.g. `set:msc
    set:msh cn>50`). When `collector_number_clauses` is given, only
    printings satisfying those clauses are considered, so the sort reflects
    the actual matching printing (e.g. `set:msc cn>200` sorts by each card's
    printing in the 200+ range, not its overall best-scored printing in the
    set, which may fall outside that range). Returns `{}` if the printings
    index is unavailable or no printing matches any of `set_codes`."""
    codes = {str(c).upper() for c in set_codes}
    if not codes:
        return {}
    printings = _load_printings_index_df()
    if printings is None or printings.empty:
        return {}
    subset = printings[printings["set"].astype(str).str.upper().isin(codes)]
    if subset.empty:
        return {}
    if collector_number_clauses:
        matched = subset.loc[_collector_number_match_mask(subset, collector_number_clauses)]
        if not matched.empty:
            subset = matched
    subset = subset.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
    sort_map: Dict[str, Tuple[float, str]] = {}
    for _, row in subset.iterrows():
        key = str(row["face_name"]).lower()
        if key in sort_map:
            continue
        num = _collector_number_numeric_prefix(row["collector_number"])
        sort_map[key] = (num if num is not None else float("inf"), str(row["set"]).upper())
    return sort_map


def _apply_search_flag(parsed: ParsedSearch, canonical: str, op: str, value: str, *, negate: bool) -> None:
    if not value:
        return
    if canonical == "name":
        (parsed.name_exclude if negate else parsed.name_include).append(value)
        parsed.explicit_name_flag = True
    elif canonical == "type":
        (parsed.type_exclude if negate else parsed.type_include).append(value)
    elif canonical == "oracle":
        (parsed.oracle_exclude if negate else parsed.oracle_include).append(value)
    elif canonical in ("color", "identity"):
        letters, count, special = _parse_color_value(value)
        effective_op = op
        if op == ":" and count is None and special is None:
            # Bare colon has different default semantics for color vs.
            # identity: `id:br` means "works with a black/red identity"
            # (subset -- mono-B, mono-R, BR, and colorless all match, same
            # as the deck-builder's pool filtering), while `color:br` means
            # "includes at least black and red" (superset -- BRU, BRG,
            # etc. also match). Use `=` for an exact-match-only search.
            effective_op = "<=" if canonical == "identity" else ">="
        clause = ColorClause(op=effective_op, letters=letters, count=count, special=special, negate=negate)
        (parsed.color_clauses if canonical == "color" else parsed.identity_clauses).append(clause)
    elif canonical in ("power", "toughness", "loyalty", "cmc"):
        target = {
            "power": parsed.power_clauses,
            "toughness": parsed.toughness_clauses,
            "loyalty": parsed.loyalty_clauses,
            "cmc": parsed.cmc_clauses,
        }[canonical]
        compare_to = _STAT_VALUE_ALIASES.get(value.lower()) if canonical != "cmc" else None
        if compare_to:
            target.append(NumericClause(op=op, compare_to=compare_to, negate=negate))
        else:
            try:
                target.append(NumericClause(op=op, value=float(value), negate=negate))
            except ValueError:
                pass
    elif canonical == "manacost":
        generic, symbols = parse_mana_cost(value)
        parsed.mana_cost_clauses.append(ManaCostClause(op=op, generic=generic, symbols=symbols, negate=negate))
    elif canonical == "rarity":
        rarities = {v.strip().lower() for v in value.split(",") if v.strip()}
        if rarities:
            parsed.rarity = (parsed.rarity or set()) | rarities
    elif canonical == "tag":
        tags = {normalize_word_sep(v) for v in value.split(",") if v.strip()}
        if tags:
            if negate:
                parsed.tags_exclude = (parsed.tags_exclude or set()) | tags
            else:
                parsed.tags = (parsed.tags or set()) | tags
    elif canonical == "arttag":
        art_tags = {normalize_word_sep(v) for v in value.split(",") if v.strip()}
        if art_tags:
            if negate:
                parsed.art_tags_exclude = (parsed.art_tags_exclude or set()) | art_tags
            else:
                parsed.art_tags = (parsed.art_tags or set()) | art_tags
    elif canonical == "metadatatag":
        metadata_tags = {normalize_word_sep(v) for v in value.split(",") if v.strip()}
        if metadata_tags:
            if negate:
                parsed.metadata_tags_exclude = (parsed.metadata_tags_exclude or set()) | metadata_tags
            else:
                parsed.metadata_tags = (parsed.metadata_tags or set()) | metadata_tags
    elif canonical == "is" and value.lower() == "new":
        parsed.is_new = False if negate else True
    elif canonical == "set":
        code, notice = _resolve_set_value(value)
        if code:
            (parsed.set_exclude if negate else parsed.set_include).add(code)
        if notice:
            parsed.notices.append(notice)
    elif canonical == "collector_number":
        parsed.collector_number_clauses.append(CollectorNumberClause(op=op, value=value, negate=negate))


def parse_search_query(q: str) -> ParsedSearch:
    """Parse a free-text search box into structured filters using real
    Scryfall keyword syntax (see module-level comment above)."""
    parsed = ParsedSearch()
    try:
        tokens = shlex.split(q)
    except ValueError:
        # Unbalanced quotes -- fall back to naive whitespace splitting
        # rather than erroring out the whole search.
        tokens = q.split()

    for token in tokens:
        m = _FLAG_TOKEN_RE.match(token)
        if m:
            neg_prefix, key, op, value = m.groups()
            canonical = _KEY_ALIASES.get(key.lower())
            if canonical:
                _apply_search_flag(parsed, canonical, op, value.strip(), negate=bool(neg_prefix))
                continue
        # Bare word -- matches the card name by default; "-word" excludes it.
        if token.startswith("-") and len(token) > 1:
            parsed.name_exclude.append(token[1:])
        else:
            parsed.name_include.append(token)

    return parsed


def apply_parsed_search(df: "pd.DataFrame", parsed: ParsedSearch) -> "pd.DataFrame":
    """Apply every clause of a `ParsedSearch` to `df` (name/type/oracle text,
    colors/identity, power/toughness/loyalty/mana value, mana cost). Does
    NOT apply `rarity`/`tags`/`is_new`/`set` -- use `apply_extra_clauses` for
    those, or apply explicit query params separately (see `list_cards` in
    `api_v1/cards.py` for that pattern)."""
    df = apply_name_clauses(df, parsed.name_include, parsed.name_exclude)
    df = apply_text_clauses(df, "type", parsed.type_include, parsed.type_exclude)
    df = apply_text_clauses(df, "text", parsed.oracle_include, parsed.oracle_exclude)
    df = apply_color_clauses(df, "colors", parsed.color_clauses)
    df = apply_color_clauses(df, "colorIdentity", parsed.identity_clauses)
    df = apply_numeric_clauses(df, "power", parsed.power_clauses)
    df = apply_numeric_clauses(df, "toughness", parsed.toughness_clauses)
    df = apply_numeric_clauses(df, "loyalty", parsed.loyalty_clauses)
    df = apply_numeric_clauses(df, "manaValue", parsed.cmc_clauses)
    df = apply_mana_cost_clauses(df, parsed.mana_cost_clauses)
    return df


def apply_extra_clauses(df: "pd.DataFrame", parsed: ParsedSearch) -> "pd.DataFrame":
    """Apply the `rarity`/`tag`/`is:new`/`set` flags parsed out of a search
    box -- separate from `apply_parsed_search` since some callers (the
    public REST API) apply their own explicit `rarity=`/`tags=`/`is_new=`
    query params instead and don't want the `q` flags double-applied."""
    if parsed.rarity and "rarity" in df.columns:
        df = df[df["rarity"].astype(str).str.lower().isin(parsed.rarity)]
    if (parsed.tags or parsed.tags_exclude) and "themeTags" in df.columns:
        card_tag_sets = df["themeTags"].apply(lambda v: {normalize_word_sep(t) for t in parse_theme_tags(v)})
        if parsed.tags:
            df = df[card_tag_sets.loc[df.index].apply(lambda card_tags: all(tag in card_tags for tag in parsed.tags))]
        if parsed.tags_exclude:
            df = df[card_tag_sets.loc[df.index].apply(lambda card_tags: not any(tag in card_tags for tag in parsed.tags_exclude))]
    if (parsed.art_tags or parsed.art_tags_exclude) and "artTags" in df.columns:
        art_tag_sets = df["artTags"].apply(lambda v: {normalize_word_sep(t) for t in parse_theme_tags(v)})
        if parsed.art_tags:
            df = df[art_tag_sets.loc[df.index].apply(lambda card_tags: all(tag in card_tags for tag in parsed.art_tags))]
        if parsed.art_tags_exclude:
            df = df[art_tag_sets.loc[df.index].apply(lambda card_tags: not any(tag in card_tags for tag in parsed.art_tags_exclude))]
    if (parsed.metadata_tags or parsed.metadata_tags_exclude) and "metadataTags" in df.columns:
        metadata_tag_sets = df["metadataTags"].apply(lambda v: {normalize_word_sep(t) for t in parse_theme_tags(v)})
        if parsed.metadata_tags:
            df = df[metadata_tag_sets.loc[df.index].apply(lambda card_tags: all(tag in card_tags for tag in parsed.metadata_tags))]
        if parsed.metadata_tags_exclude:
            df = df[metadata_tag_sets.loc[df.index].apply(lambda card_tags: not any(tag in card_tags for tag in parsed.metadata_tags_exclude))]
    if parsed.is_new is not None and "isNew" in df.columns:
        df = df[df["isNew"] == parsed.is_new]
    if parsed.set_include and "printings" in df.columns:
        for code in parsed.set_include:
            df = df[df["printings"].astype(str).str.contains(rf"\b{re.escape(code)}\b", na=False, regex=True)]
    if parsed.set_exclude and "printings" in df.columns:
        for code in parsed.set_exclude:
            df = df[~df["printings"].astype(str).str.contains(rf"\b{re.escape(code)}\b", na=False, regex=True)]
    if parsed.collector_number_clauses:
        if not parsed.set_include:
            parsed.notices.append("cn:/number: requires a set: filter and was ignored.")
        else:
            printings = _load_printings_index_df()
            if printings is not None and not printings.empty:
                subset = printings[printings["set"].astype(str).str.upper().isin(parsed.set_include)]
                if subset.empty:
                    df = df.iloc[0:0]
                else:
                    matched_names = set(
                        subset.loc[_collector_number_match_mask(subset, parsed.collector_number_clauses), "face_name"].astype(str)
                    )
                    df = df[df["name"].astype(str).isin(matched_names)]
    return df


def wants_tokens(parsed: ParsedSearch) -> bool:
    """True if a structured `type:`/`t:` query explicitly asks for tokens
    or emblems (e.g. `type:token`, `t:emblem`). Tokens are otherwise never
    included in search results -- see `merge_tokens_for_search`."""
    return any(
        "token" in term.lower() or "emblem" in term.lower()
        for term in parsed.type_include
    )


def merge_tokens_for_search(df: "pd.DataFrame") -> "pd.DataFrame":
    """Concat the normalized tokens/emblems catalog (`load_tokens_browser_df`)
    onto `df` so a `type:token`/`type:emblem` search can surface them. Only
    call when `wants_tokens()` is true; the subsequent `type:` substring
    filter naturally excludes real cards (whose `type` never contains
    "token"/"emblem"), so no separate real-card exclusion is needed here.
    """
    token_df = load_tokens_browser_df()
    if token_df.empty:
        return df
    columns = list(dict.fromkeys(list(df.columns) + list(token_df.columns)))
    merged = pd.concat(
        [df.reindex(columns=columns), token_df.reindex(columns=columns)],
        ignore_index=True,
    )
    merged["is_token"] = merged["is_token"].fillna(False).astype(bool)
    merged["is_emblem"] = merged["is_emblem"].fillna(False).astype(bool)
    return merged


def has_structured_flags(parsed: ParsedSearch) -> bool:
    """True if `parsed` contains anything beyond bare name words -- callers
    that have their own fuzzy/typo-tolerant name-only search (e.g. the card
    browser) can use this to decide whether to fall back to structured
    flag-based filtering instead. An explicit `name:`/`n:` flag also counts
    as structured (so quoted phrases and hyphen-for-space both work), even
    though it only populates `name_include`/`name_exclude` like bare words."""
    return bool(
        parsed.type_include or parsed.type_exclude
        or parsed.oracle_include or parsed.oracle_exclude
        or parsed.color_clauses or parsed.identity_clauses
        or parsed.power_clauses or parsed.toughness_clauses
        or parsed.loyalty_clauses or parsed.cmc_clauses
        or parsed.mana_cost_clauses
        or parsed.rarity or parsed.tags or parsed.tags_exclude
        or parsed.art_tags or parsed.art_tags_exclude
        or parsed.metadata_tags or parsed.metadata_tags_exclude or parsed.is_new is not None
        or parsed.set_include or parsed.set_exclude
        or parsed.collector_number_clauses
        or parsed.explicit_name_flag
    )
