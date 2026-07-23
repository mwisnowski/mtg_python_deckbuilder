"""Card browser endpoints for the public REST API (R28 Milestone 4).

Reuses `AllCardsLoader` (code/services/all_cards_loader.py), `CardSimilarity`
(code/web/services/card_similarity.py), and `get_rulings()` from R27
(code/web/services/rulings.py) -- the same building blocks as the HTML card
browser (code/web/routes/card_browser.py) -- instead of duplicating filter
logic. All endpoints here are public (no auth required).

Route ordering note: `/similar` and `/rulings` are registered before the
bare `/{name}` detail route, using `:path` converters, so double-faced card
names containing `/` (e.g. "Fire // Ice") still resolve correctly -- mirrors
the same trick used in card_browser.py.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import shlex
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder

from code.deck_builder.builder_utils import parse_theme_tags
from code.services.all_cards_loader import AllCardsLoader

from ...services.card_similarity import CardSimilarity
from ...services.rulings import get_rulings
from ...utils.api_response import err, ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])

# --- Live Scryfall fallback for cards missing from the local tagged dataset
#
# Basic lands (Plains, Island, Swamp, Mountain, Forest, Wastes, and their
# snow-covered variants) are intentionally excluded from tagging/all_cards.parquet
# -- there's nothing to tag on a card with no rules text -- but the mobile app's
# card detail/summary dialog still needs *something* to show for them. More
# generally, any card can be temporarily missing if the local database hasn't
# been refreshed yet, so this fallback applies to every miss, not just basics.
_SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
_SCRYFALL_USER_AGENT = "MTGPythonDeckbuilder/1.0 (contact via GitHub)"
_SCRYFALL_FALLBACK_RATE_LIMIT = 0.1  # 100ms between live fetches (10 req/s)
_scryfall_fallback_lock = asyncio.Lock()
_scryfall_fallback_last_fetch: float = 0.0


async def _scryfall_card_fallback(name: str) -> Optional[Dict[str, Any]]:
    """Live Scryfall lookup for a card missing from the local tagged dataset,
    shaped like _serialize_card(..., full=True). Returns None on any miss/error."""
    global _scryfall_fallback_last_fetch
    async with _scryfall_fallback_lock:
        wait = _SCRYFALL_FALLBACK_RATE_LIMIT - (time.monotonic() - _scryfall_fallback_last_fetch)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(headers={"User-Agent": _SCRYFALL_USER_AGENT}, timeout=10.0) as client:
                resp = await client.get(_SCRYFALL_NAMED_URL, params={"exact": name})
                _scryfall_fallback_last_fetch = time.monotonic()
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"Scryfall card fallback failed for '{name}': {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error in Scryfall card fallback for '{name}': {e}")
            return None

    card_faces = data.get("card_faces") or []
    primary_face = card_faces[0] if card_faces else {}
    result: Dict[str, Any] = {
        "name": data.get("name"),
        "type": data.get("type_line"),
        "manaValue": data.get("cmc"),
        "colorIdentity": ",".join(data.get("color_identity") or []),
        "rarity": data.get("rarity"),
        "themeTags": [],
        "edhrecRank": data.get("edhrec_rank"),
        "scryfallID": data.get("id"),
        "text": data.get("oracle_text") or primary_face.get("oracle_text"),
        "power": data.get("power") or primary_face.get("power"),
        "toughness": data.get("toughness") or primary_face.get("toughness"),
        "printings": None,
        "layout": data.get("layout"),
        "isNew": None,
        "faces": [
            {
                "name": face.get("name"),
                "side": chr(ord("a") + i),
                "type": face.get("type_line"),
                "text": face.get("oracle_text"),
                "manaValue": face.get("cmc"),
                "power": face.get("power"),
                "toughness": face.get("toughness"),
                "colorIdentity": ",".join(face.get("colors") or []),
            }
            for i, face in enumerate(card_faces)
        ]
        if len(card_faces) > 1
        else [],
    }
    return jsonable_encoder({k: _json_safe(v) for k, v in result.items()})

MAX_PAGE_SIZE = 100

_loader: Optional[AllCardsLoader] = None
_similarity: Optional[CardSimilarity] = None


def _get_loader() -> AllCardsLoader:
    global _loader
    if _loader is None:
        _loader = AllCardsLoader()
    return _loader


def _get_similarity() -> CardSimilarity:
    global _similarity
    if _similarity is None:
        _similarity = CardSimilarity(_get_loader().load())
    return _similarity


_RAW_CARDS_PATH = Path("card_files/raw/cards.parquet")
_raw_faces_df: Optional[pd.DataFrame] = None


def _get_raw_faces_df() -> Optional[pd.DataFrame]:
    """Lazily load + cache a deduplicated (name, side) slice of the raw
    MTGJSON card data (one row per printing), used only to recover
    secondary-face details -- type, text, mana value, power/toughness --
    for split/adventure/transform/flip/etc. cards. The tagged dataset
    (`AllCardsLoader`) collapses multi-face cards down to a single
    primary-face row during tagging (see `multi_face_merger.py`), dropping
    everything but the back face's type (for MDFC land detection).
    """
    global _raw_faces_df
    if _raw_faces_df is None:
        if not _RAW_CARDS_PATH.exists():
            return None
        cols = [
            "name", "faceName", "side", "type", "text", "faceManaValue", "power", "toughness",
            "colorIdentity",
        ]
        try:
            df = pd.read_parquet(_RAW_CARDS_PATH, columns=cols)
        except Exception:
            return None
        df = df[df["side"].notna() & (df["side"].astype(str) != "")]
        df = df.drop_duplicates(subset=["name", "side"], keep="first")
        _raw_faces_df = df
    return _raw_faces_df


def _get_card_faces(name: str) -> List[Dict[str, Any]]:
    """Per-face details (type/text/mana value/power/toughness) for a
    multi-faced card, sorted front-to-back (side a, b, c...). Returns an
    empty list for single-faced cards or if the raw dataset is unavailable.
    """
    df = _get_raw_faces_df()
    if df is None:
        return []
    rows = df[df["name"] == name]
    if len(rows) < 2:
        return []
    rows = rows.sort_values("side")
    faces: List[Dict[str, Any]] = []
    for _, row in rows.iterrows():
        faces.append(
            {
                "name": _json_safe(row.get("faceName")) or _json_safe(row.get("name")),
                "side": _json_safe(row.get("side")),
                "type": _json_safe(row.get("type")) or None,
                "text": _json_safe(row.get("text")) or None,
                "manaValue": _json_safe(row.get("faceManaValue")),
                "power": _json_safe(row.get("power")) or None,
                "toughness": _json_safe(row.get("toughness")) or None,
                "colorIdentity": _json_safe(row.get("colorIdentity")) or None,
            }
        )
    return faces


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _json_safe(value: Any) -> Any:
    """Convert NaN/Infinity floats (common for missing edhrecRank/manaValue
    values in the card data) to None -- Starlette's JSONResponse uses
    allow_nan=False, so leaving these in raises a 500 at render time."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _serialize_card(row, *, full: bool = False) -> Dict[str, Any]:
    card = row.to_dict()
    data: Dict[str, Any] = {
        "name": card.get("name"),
        "type": card.get("type"),
        "manaValue": card.get("manaValue"),
        "colorIdentity": card.get("colorIdentity"),
        "rarity": card.get("rarity"),
        "themeTags": parse_theme_tags(card.get("themeTags")),
        "edhrecRank": card.get("edhrecRank"),
        "scryfallID": card.get("scryfallID"),
    }
    if full:
        data.update(
            {
                "text": card.get("text"),
                "power": card.get("power"),
                "toughness": card.get("toughness"),
                "printings": card.get("printings"),
                "layout": card.get("layout"),
                "isNew": card.get("isNew"),
                "faces": _get_card_faces(str(card.get("name") or "")),
            }
        )
    data = {k: _json_safe(v) for k, v in data.items()}
    return jsonable_encoder(data)


def _parse_color_cell(raw: Any) -> set:
    """Parse a `colors`/`colorIdentity`-style cell into a set of color
    letters (empty set for colorless). Mirrors card_browser.py's
    "Colorless" special-case. Cells use a comma delimiter, with or without
    a following space, depending on the source column."""
    if not raw or not isinstance(raw, str):
        return set()
    if raw.strip().lower() == "colorless":
        return set()
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


# --- Scryfall-style search syntax -------------------------------------------
#
# The `q` search box supports plain text (matched against card name only,
# the default) plus real Scryfall search keywords -- see
# https://scryfall.com/docs/syntax. Only the categories relevant to this
# dataset are supported: colors/identity, card types, card text, mana costs,
# and power/toughness. Loyalty is intentionally unsupported (no loyalty data
# in this dataset); rarity/tag/is=new flags are also parsed as a bonus but
# are secondary to the `colors`/`tags`/`is_new` query params below.
#
# NOTE: bare colon (`:`) has different default semantics for color vs.
# identity, matching how each concept is actually used:
#   - `id:br` -- subset ("works with a black/red identity"): matches mono-B,
#     mono-R, BR, and colorless cards. Same logic as the deck-builder's
#     color-identity pool filtering. Use `id=br` for an exact-identity-only match.
#   - `color:br` -- superset ("includes at least black and red"): also
#     matches BRU, BRG, etc. Use `color=br` for an exact-colors-only match.
#
# Examples: `c:rg`, `id<=esper`, `t:goblin -t:creature`, `o:"draw a card"`,
# `m:2WW`, `mv>=4`, `pow>=4 tou<=2`, `pow>tou`. Any keyword may be negated
# with a leading `-` (e.g. `-t:land`); plain words without a keyword match
# (or exclude, with `-`) the card name.

_FLAG_TOKEN_RE = re.compile(r"^(-)?([A-Za-z]+)(:|>=|<=|!=|>|<|=)(.+)$")

_KEY_ALIASES: Dict[str, str] = {
    "name": "name", "n": "name",
    "type": "type", "t": "type",
    "oracle": "oracle", "text": "oracle", "o": "oracle",
    "color": "color", "c": "color",
    "identity": "identity", "id": "identity",
    "power": "power", "pow": "power",
    "toughness": "toughness", "tou": "toughness", "tough": "toughness",
    "mana": "manacost", "m": "manacost",
    "manavalue": "cmc", "mv": "cmc", "cmc": "cmc",
    "rarity": "rarity", "r": "rarity",
    "tag": "tag", "theme": "tag",
    "is": "is",
}

_COLOR_LETTERS = set("WUBRG")
_STAT_VALUE_ALIASES = {
    "power": "power", "pow": "power",
    "toughness": "toughness", "tou": "toughness", "tough": "toughness",
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
    cmc_clauses: List[NumericClause] = field(default_factory=list)
    mana_cost_clauses: List[ManaCostClause] = field(default_factory=list)
    rarity: Optional[Set[str]] = None
    tags: Optional[Set[str]] = None
    is_new: Optional[bool] = None


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


def _apply_color_clauses(df: "pd.DataFrame", column: str, clauses: List[ColorClause]) -> "pd.DataFrame":
    if not clauses or column not in df.columns:
        return df

    def _row_matches(raw: Any) -> bool:
        card_letters = _parse_color_cell(raw)
        return all(_color_matches(card_letters, clause) for clause in clauses)

    return df[df[column].apply(_row_matches)]


def _apply_numeric_clauses(df: "pd.DataFrame", column: str, clauses: List[NumericClause]) -> "pd.DataFrame":
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


def _parse_mana_cost(cost: str) -> Tuple[int, Counter]:
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
    card = _parse_mana_cost(cost)
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


def _apply_mana_cost_clauses(df: "pd.DataFrame", clauses: List[ManaCostClause]) -> "pd.DataFrame":
    if not clauses or "manaCost" not in df.columns:
        return df
    return df[df["manaCost"].apply(lambda raw: all(_mana_cost_matches(raw, c) for c in clauses))]


def _apply_text_clauses(df: "pd.DataFrame", column: str, include: List[str], exclude: List[str]) -> "pd.DataFrame":
    if column not in df.columns:
        return df
    for term in include:
        df = df[df[column].str.contains(term, case=False, na=False, regex=False)]
    for term in exclude:
        df = df[~df[column].str.contains(term, case=False, na=False, regex=False)]
    return df


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
    elif canonical in ("power", "toughness", "cmc"):
        target = {
            "power": parsed.power_clauses,
            "toughness": parsed.toughness_clauses,
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
        generic, symbols = _parse_mana_cost(value)
        parsed.mana_cost_clauses.append(ManaCostClause(op=op, generic=generic, symbols=symbols, negate=negate))
    elif canonical == "rarity":
        rarities = {v.strip().lower() for v in value.split(",") if v.strip()}
        if rarities:
            parsed.rarity = (parsed.rarity or set()) | rarities
    elif canonical == "tag":
        tags = {v.strip().lower() for v in value.split(",") if v.strip()}
        if tags:
            parsed.tags = (parsed.tags or set()) | tags
    elif canonical == "is" and value.lower() == "new":
        parsed.is_new = False if negate else True


def _parse_search_query(q: str) -> ParsedSearch:
    """Parse the free-text search box into structured filters using real
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


@router.get("", summary="Search cards")
async def list_cards(
    request: Request,
    q: str = Query(
        "",
        description=(
            "Search box text. Plain words match the card name (default). "
            "Also supports real Scryfall search keywords (see "
            "https://scryfall.com/docs/syntax): c:/color:, id:/identity:, "
            "t:/type:, o:/oracle:, m:/mana:, mv:/cmc:/manavalue:, pow:/power:, "
            "tou:/toughness: -- each accepts :, =, >, <, >=, <=, or != and may be "
            "negated with a leading -. Note: bare `id:br` matches anything playable "
            "with a black/red identity (subset, incl. colorless), while `id=br` "
            "matches only exact black/red; bare `color:br` matches cards including "
            "at least black and red (superset), while `color=br` is exact-only. "
            "e.g. `c:rg t:creature o:\"draw a card\" pow>=4`"
        ),
    ),
    colors: str = Query("", description="Comma-separated colors, e.g. W,U -- cards whose color identity is a subset of these are matched; include C to also allow colorless"),
    tags: str = Query("", description="Comma-separated theme tags (AND logic)"),
    is_new: bool = Query(False, description="Only recently released cards"),
    min_cmc: Optional[float] = Query(None, ge=0),
    max_cmc: Optional[float] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Search/filter cards. Mirrors card_browser.py's filters, simplified for JSON I/O."""
    df = _get_loader().load()

    parsed = _parse_search_query(q) if q else ParsedSearch()

    df = _apply_text_clauses(df, "name", parsed.name_include, parsed.name_exclude)
    df = _apply_text_clauses(df, "type", parsed.type_include, parsed.type_exclude)
    df = _apply_text_clauses(df, "text", parsed.oracle_include, parsed.oracle_exclude)

    # Colors (c:/color:) match the card's own mana cost colors; identity
    # (id:/identity:) matches its commander color identity -- two separate
    # columns/concepts.
    df = _apply_color_clauses(df, "colors", parsed.color_clauses)
    df = _apply_color_clauses(df, "colorIdentity", parsed.identity_clauses)

    df = _apply_numeric_clauses(df, "power", parsed.power_clauses)
    df = _apply_numeric_clauses(df, "toughness", parsed.toughness_clauses)
    df = _apply_numeric_clauses(df, "manaValue", parsed.cmc_clauses)
    df = _apply_mana_cost_clauses(df, parsed.mana_cost_clauses)

    if parsed.rarity and "rarity" in df.columns:
        df = df[df["rarity"].str.lower().isin(parsed.rarity)]

    if "isNew" in df.columns:
        if parsed.is_new is True or is_new:
            df = df[df["isNew"] == True]  # noqa: E712
        elif parsed.is_new is False:
            df = df[df["isNew"] == False]  # noqa: E712

    # Colors -- the explicit `colors` param (used by the mobile app's chip
    # filter UI) is a simple subset-match against colorIdentity, separate
    # from the id:/identity: flag syntax parsed above.
    requested_colors = {c.strip().upper() for c in colors.split(",") if c.strip()}
    if requested_colors and "colorIdentity" in df.columns:
        allow_colorless = "C" in requested_colors
        color_letters = requested_colors - {"C"}

        def _matches_colors(raw: Any) -> bool:
            card_colors = _parse_color_cell(raw)
            if not card_colors:
                return allow_colorless
            return card_colors.issubset(color_letters)

        df = df[df["colorIdentity"].apply(_matches_colors)]

    # Theme tags -- combine the explicit `tags` param with any `tag=` flags
    # parsed out of `q`; AND logic (a card must have all requested tags).
    requested_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}
    if parsed.tags:
        requested_tags |= parsed.tags
    if requested_tags and "themeTags" in df.columns:
        # themeTags may be stored as a string, list, or numpy array depending on
        # source (raw CSV vs. Parquet) -- parse_theme_tags() normalizes all of them.
        card_tag_sets = df["themeTags"].apply(lambda v: {t.lower() for t in parse_theme_tags(v)})
        mask = card_tag_sets.apply(lambda card_tags: all(tag in card_tags for tag in requested_tags))
        df = df[mask]


    if min_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] >= min_cmc]
    if max_cmc is not None and "manaValue" in df.columns:
        df = df[df["manaValue"] <= max_cmc]

    # Default sort: Name A-Z, matching the HTML card browser's default sort
    # (card_browser.py's "name_asc"), so results aren't left in arbitrary
    # data-file order.
    if "name" in df.columns and len(df):
        sort_key = df["name"].str.replace('"', "", regex=False).str.replace("'", "", regex=False)
        sort_key = sort_key.apply(lambda x: x.replace("_", " ") if isinstance(x, str) and x.startswith("_") else x)
        df = df.assign(_sort_key=sort_key).sort_values("_sort_key", key=lambda col: col.str.lower()).drop(columns="_sort_key")

    total = len(df)
    start = (page - 1) * page_size
    page_df = df.iloc[start : start + page_size]

    return ok(
        {
            "cards": [_serialize_card(row) for _, row in page_df.iterrows()],
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        _rid(request),
    )


@router.get("/{name:path}/similar", summary="Find similar cards")
async def get_card_similar(name: str, request: Request, limit: int = Query(10, ge=1, le=50)):
    """Similar cards by theme-tag overlap (reuses CardSimilarity)."""
    row = _get_loader().get_by_name(name)
    if row is None:
        return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
    similar = _get_similarity().find_similar(name, limit=limit)
    return ok(jsonable_encoder(similar), _rid(request))


@router.get("/{name:path}/rulings", summary="Get card rulings")
async def get_card_rulings(name: str, request: Request):
    """Card rulings, cache-first with a live Scryfall fallback (R27)."""
    row = _get_loader().get_by_name(name)
    if row is None:
        return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
    scryfall_id = row.get("scryfallID") or ""
    rulings = await get_rulings(scryfall_id) if scryfall_id else []
    return ok(jsonable_encoder(rulings), _rid(request))


@router.get("/{name:path}", summary="Get card detail")
async def get_card_detail(name: str, request: Request):
    """Card detail: stats, tags, oracle text, scryfall_id.

    Falls back to a live Scryfall lookup when the card isn't in the local
    tagged dataset (e.g. basic lands, which are excluded from tagging).
    """
    row = _get_loader().get_by_name(name)
    if row is not None:
        return ok(_serialize_card(row, full=True), _rid(request))
    fallback = await _scryfall_card_fallback(name)
    if fallback is not None:
        return ok(fallback, _rid(request))
    return err("Card not found.", "CARD_NOT_FOUND", 404, _rid(request))
