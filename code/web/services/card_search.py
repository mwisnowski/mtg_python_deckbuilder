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

import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from code.deck_builder.builder_utils import parse_theme_tags


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
class ParsedSearch:
    name_include: List[str] = field(default_factory=list)
    name_exclude: List[str] = field(default_factory=list)
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


def _apply_search_flag(parsed: ParsedSearch, canonical: str, op: str, value: str, *, negate: bool) -> None:
    if not value:
        return
    if canonical == "name":
        (parsed.name_exclude if negate else parsed.name_include).append(value)
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
        code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        if code:
            (parsed.set_exclude if negate else parsed.set_include).add(code)


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
    return df


def has_structured_flags(parsed: ParsedSearch) -> bool:
    """True if `parsed` contains anything beyond bare name words -- callers
    that have their own fuzzy/typo-tolerant name-only search (e.g. the card
    browser) can use this to decide whether to fall back to structured
    flag-based filtering instead."""
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
    )
