# -*- coding: utf-8 -*-
"""Deck import service — parse, validate, and analyse externally-built deck lists.

Supports Moxfield, Archidekt, TappedOut, EDHREC, and native .txt export formats.
Milestone 1: DeckListParser (parse raw text → ParsedDeck).
Milestone 2: validate_and_enrich (parquet lookup → EnrichedDeck).
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import urllib.parse as _urlparse
import urllib.request as _urllib
from dataclasses import dataclass, field
import dataclasses
from typing import Literal, Optional

import pandas as pd

from code import logging_util
from code.path_util import get_commander_cards_path, get_processed_cards_path

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)

# ---------------------------------------------------------------------------
# Basic land constants (not present in all_cards.parquet)
# ---------------------------------------------------------------------------

_BASIC_LAND_TYPE = {
    "forest":               "Basic Land — Forest",
    "plains":               "Basic Land — Plains",
    "island":               "Basic Land — Island",
    "swamp":                "Basic Land — Swamp",
    "mountain":             "Basic Land — Mountain",
    "wastes":               "Basic Land",
    "snow-covered forest":  "Basic Snow Land — Forest",
    "snow-covered plains":  "Basic Snow Land — Plains",
    "snow-covered island":  "Basic Snow Land — Island",
    "snow-covered swamp":   "Basic Snow Land — Swamp",
    "snow-covered mountain":"Basic Snow Land — Mountain",
}

# Strips trailing bracket/paren annotations users paste after card names,
# e.g. "Bala Ged Recovery // Bala Ged Sanctuary [MDFC: Counts as land slot]"
_TRAILING_ANNOTATION_RE = re.compile(r"\s+[\[(][^\]\)]+[\])]\s*$")

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches Archidekt-style section headers: "// Commander", "// Mainboard", etc.
_SECTION_HEADER_RE = re.compile(
    r"^//\s*(Commander|Mainboard|Sideboard|Considering|Maybeboard|Creatures|Instants|Sorceries"
    r"|Enchantments|Artifacts|Planeswalkers|Lands)\s*$",
    re.IGNORECASE,
)

# Bare section header (Moxfield Arena/plain text): "Commander", "Deck", "Sideboard", etc.
_BARE_SECTION_RE = re.compile(
    r"^(Commander|Deck|Sideboard|Considering|Maybeboard)$", re.IGNORECASE
)

# Colon-suffixed section header: "SIDEBOARD:", "Maybeboard:", etc.
# Used by MTGO, some Moxfield export variants, and other tools.
_COLON_SECTION_RE = re.compile(
    r"^(Commander|Deck|Sideboard|Considering|Maybeboard):?\s*$", re.IGNORECASE
)

# Set/collector suffix — handles:
#   (VOW) 239          standard
#   (PLST) ELD-331     reprint with hyphenated number
#   (PAER) 109p        promo with lowercase-letter suffix
#   (CMR) 570 *E*      extended art marker
#   (SLD) 1241 *F*     foil marker (one or more *X* at end)
#   (SLD) 1492★ *F*    collector number with Unicode star (Secret Lair etc.)
_SET_SUFFIX_RE = r"(?:\s+\([A-Z0-9]+\)\s+[A-Z0-9][A-Z0-9\-]*[a-z]?\u2605?(?:\s+\*[A-Z]\*)*)?\s*$"

# Commander marker line — asterisk with or without space before quantity.
# Covers: "* 1 Name (VOW) 239" and "*1 Name" and "* 1 Name (SLD) 1241 *F*"
_COMMANDER_LINE_RE = re.compile(
    r"^\*\s*(\d+)\s+(.+?)" + _SET_SUFFIX_RE
)

# Regular card line — optional 'x'/'X' after quantity, optional set/foil suffix.
# Covers: "1 Name", "1x Name", "1 Name (VOW) 239", "1 Name (PAER) 109p", "1 Name (CMR) 570 *E*"
_CARD_LINE_RE = re.compile(
    r"^(\d+)[xX]?\s+(.+?)" + _SET_SUFFIX_RE
)

# "# Commanders: Name" — native export format commander hint.
_NATIVE_COMMANDER_RE = re.compile(r"^#\s*Commanders?:\s*(.+)$", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedCard:
    """A single card entry extracted from a raw deck list line."""

    name: str
    quantity: int
    section: Literal["Commander", "Mainboard", "Sideboard", "Unknown"]


@dataclass
class ParsedDeck:
    """Output of DeckListParser.parse()."""

    commander: str | None  # None if ambiguous; confirmed by precedence rules
    cards: list[ParsedCard]
    raw_lines: int
    skipped_lines: int  # blank lines, SB:, comments
    warnings: list[str]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class DeckListParser:
    """Parse any supported deck-list text format into a normalised ParsedDeck.

    Supported formats: Moxfield (all export modes), Archidekt, TappedOut,
    EDHREC plain text, and this app's native .txt export.

    Tokeniser step order (applied per line):
        1. Blank line → skip
        2. SB: prefix → skip (TappedOut sideboard)
        3. # comment → extract "# Commanders:" hint if present, then skip
        4. // section header (Archidekt) → update current section, continue
        5. // comment (non-header) → skip
        6. Bare "Commander" or "Deck" line → update current section (Moxfield Arena)
        7. Commander line (* prefix) → strip *, strip set suffix, mark commander
        8. Regular card line → strip set suffix, add to cards
        9. Unrecognised non-blank line → warning, skip
    """

    def parse(self, text: str) -> ParsedDeck:
        """Parse raw deck-list text into a ParsedDeck.

        Args:
            text: Raw paste or decoded file content.

        Returns:
            ParsedDeck with normalised card list, detected commander, and warnings.
        """
        lines = text.splitlines()
        raw_lines = len(lines)
        skipped_lines = 0
        warnings: list[str] = []
        cards: list[ParsedCard] = []

        # Commander detection state — collected across all passes.
        star_commander: str | None = None      # highest precedence: * marker
        native_commander: str | None = None    # "# Commanders:" comment
        section_commanders: list[str] = []     # cards inside Commander section

        current_section: Literal["Commander", "Mainboard", "Sideboard", "Unknown"] = "Unknown"
        last_blank_card_idx: int = 0  # cards-list length at the most recent blank line

        for line in lines:
            stripped = line.strip()

            # Step 1: blank line
            if not stripped:
                skipped_lines += 1
                last_blank_card_idx = len(cards)
                continue

            # Step 2: TappedOut sideboard
            if stripped.startswith("SB:"):
                skipped_lines += 1
                continue

            # Step 3: # comment — extract native commander hint first
            if stripped.startswith("#"):
                m = _NATIVE_COMMANDER_RE.match(stripped)
                if m and native_commander is None:
                    native_commander = m.group(1).strip()
                skipped_lines += 1
                continue

            # Step 4: // section header (Archidekt) — must come before step 5
            m = _SECTION_HEADER_RE.match(stripped)
            if m:
                header = m.group(1).capitalize()
                if header == "Commander":
                    current_section = "Commander"
                elif header in ("Sideboard", "Considering", "Maybeboard"):
                    current_section = "Sideboard"
                    warnings.append(f"Skipping {header} cards (excluded from analysis).")
                else:
                    current_section = "Mainboard"
                skipped_lines += 1
                continue

            # Step 5: // comment (non-header)
            if stripped.startswith("//"):
                skipped_lines += 1
                continue

            # Step 6: bare / colon-suffixed section header
            m = _BARE_SECTION_RE.match(stripped) or _COLON_SECTION_RE.match(stripped)
            if m:
                header = m.group(1).capitalize()
                if header == "Commander":
                    current_section = "Commander"
                elif header in ("Sideboard", "Considering", "Maybeboard"):
                    current_section = "Sideboard"
                    warnings.append(f"Skipping {header} cards (excluded from analysis).")
                else:
                    current_section = "Mainboard"
                skipped_lines += 1
                continue

            # Step 7: commander line (* prefix — Moxfield "Copy for Moxfield" and plain text)
            m = _COMMANDER_LINE_RE.match(stripped)
            if m:
                qty = int(m.group(1))
                name = m.group(2).strip()
                if " / " in name and " // " not in name:
                    name = name.replace(" / ", " // ")
                if star_commander is None:
                    star_commander = name
                elif star_commander != name:
                    # Second * card = partner commander
                    star_commander = f"{star_commander} + {name}"
                cards.append(ParsedCard(name=name, quantity=qty, section="Commander"))
                continue

            # Step 8: regular card line
            m = _CARD_LINE_RE.match(stripped)
            if m:
                qty = int(m.group(1))
                name = m.group(2).strip()
                if " / " in name and " // " not in name:
                    name = name.replace(" / ", " // ")
                cards.append(ParsedCard(name=name, quantity=qty, section=current_section))
                if current_section == "Commander":
                    section_commanders.append(name)
                continue

            # Step 9: unrecognised non-blank line
            warnings.append(f"Unrecognised line skipped: {stripped!r}")
            skipped_lines += 1

        # Resolve commander by precedence order.
        commander = self._resolve_commander(
            star_commander, section_commanders, native_commander, cards, warnings,
            last_blank_card_idx=last_blank_card_idx,
        )

        total_cards = sum(c.quantity for c in cards if c.section != "Sideboard")
        if total_cards != 100:
            warnings.append(
                f"Deck has {total_cards} cards; expected 100 for Commander format."
            )

        return ParsedDeck(
            commander=commander,
            cards=cards,
            raw_lines=raw_lines,
            skipped_lines=skipped_lines,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_commander(
        self,
        star_commander: str | None,
        section_commanders: list[str],
        native_commander: str | None,
        cards: list[ParsedCard],
        warnings: list[str],
        last_blank_card_idx: int = 0,
    ) -> str | None:
        # 1. Explicit * marker (highest confidence)
        if star_commander is not None:
            return star_commander

        # 2. Bare "Commander" section (Moxfield Arena)
        if section_commanders:
            if len(section_commanders) == 2:
                return f"{section_commanders[0]} + {section_commanders[1]}"
            return section_commanders[0]

        # 3. # Commanders: hint (native format)
        if native_commander is not None:
            return native_commander

        # 4. Trailing group after last blank line (Moxfield "Copy Plain Text" — commander at bottom)
        if last_blank_card_idx > 0:
            trailing = [c for c in cards[last_blank_card_idx:] if c.section != "Sideboard"]
            if 1 <= len(trailing) <= 2 and all(c.quantity == 1 for c in trailing):
                for c in trailing:
                    c.section = "Commander"
                if len(trailing) == 2:
                    cmd_name = f"{trailing[0].name} + {trailing[1].name}"
                    warnings.append(
                        f"Partner commanders assumed from end of list: '{cmd_name}'. "
                        "Use the Commander field above to correct this if wrong."
                    )
                    return cmd_name
                assumed = trailing[0].name
                warnings.append(
                    f"Commander assumed to be last card in list: '{assumed}'. "
                    "Use the Commander field above to correct this if wrong."
                )
                return assumed

        # 5. First card as assumed commander (lowest confidence)
        # Most plain-text pastes without format markers place the commander first.
        mainboard_cards = [c for c in cards if c.section not in ("Sideboard",)]
        if mainboard_cards:
            assumed = mainboard_cards[0].name
            warnings.append(
                f"Commander assumed to be first card: '{assumed}'. "
                "Use the Commander field above to correct this if wrong."
            )
            return assumed

        # 6. No cards at all
        warnings.append(
            "No commander detected. Please confirm the commander in the form."
        )
        return None


# ---------------------------------------------------------------------------
# M2 data classes
# ---------------------------------------------------------------------------

@dataclass
class EnrichedCard:
    """A parsed card enriched with tag/CMC data from all_cards.parquet."""

    name: str
    quantity: int
    tags: list[str]          # from parquet "themeTags" (semicolon/comma-split)
    cmc: float               # from parquet "manaValue"
    type_line: str           # from parquet "type"
    is_new: bool             # from parquet "isNew"
    price: float | None      # from parquet "price"; None if missing
    edhrec_rank: int | None = None  # from parquet "edhrecRank"; None if missing
    section: str = "Mainboard"  # propagated from ParsedCard.section


@dataclass
class EnrichedDeck:
    """Output of validate_and_enrich()."""

    commander_row: Optional[pd.Series]  # row from commander_cards.parquet;
                                         # access via .get(): e.g. .get("colorIdentity")
                                         # None if commander undetected or not found
    cards: list[EnrichedCard]
    unrecognized: list[str]             # card names not found in all_cards.parquet


# ---------------------------------------------------------------------------
# M2 parquet helpers (module-level cache, thread-safe)
# ---------------------------------------------------------------------------

_REQUIRED_CARD_COLS = {"themeTags", "manaValue", "type", "isNew"}

_all_cards_df: Optional[pd.DataFrame] = None
_all_cards_lock = threading.Lock()
_all_card_names: Optional[list[str]] = None  # canonical names for fuzzy matching

_commander_df: Optional[pd.DataFrame] = None
_commander_lock = threading.Lock()


def _get_all_cards() -> pd.DataFrame:
    global _all_cards_df, _all_card_names
    with _all_cards_lock:
        if _all_cards_df is None:
            path = get_processed_cards_path()
            df = pd.read_parquet(path)
            missing = _REQUIRED_CARD_COLS - set(df.columns)
            if missing:
                raise RuntimeError(
                    f"all_cards.parquet missing required columns: {', '.join(sorted(missing))}"
                )
            _all_cards_df = df
            # Build canonical name list: prefer faceName when present, else name
            names: list[str] = []
            for col in ("faceName", "name"):
                if col in df.columns:
                    names = df[col].dropna().astype(str).tolist()
                    break
            _all_card_names = names
    return _all_cards_df


def _get_commander_df() -> pd.DataFrame:
    global _commander_df
    with _commander_lock:
        if _commander_df is None:
            path = get_commander_cards_path()
            _commander_df = pd.read_parquet(path)
    return _commander_df


def _parse_tags(raw: object) -> list[str]:
    """Parse themeTags from parquet — handles list, numpy array, or comma-separated string."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    try:
        import numpy as np  # noqa: PLC0415
        if isinstance(raw, np.ndarray):
            return [str(t).strip() for t in raw.tolist() if str(t).strip()]
    except ImportError:
        pass
    s = str(raw).strip()
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _normalize_name(name: str) -> str:
    """Normalize Unicode apostrophes/quotes to ASCII equivalents.

    Moxfield and other exporters sometimes use 'smart' curly apostrophes
    (U+2018/U+2019) and curly quotes (U+201C/U+201D) in card names.  Scryfall
    and our parquet both use plain ASCII apostrophes, so we normalise before
    any lookup.
    """
    return (
        name
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")  # en-dash → hyphen
        .replace("\u2014", "-")  # em-dash → hyphen
    )


def _find_card_row(df: pd.DataFrame, name: str) -> Optional[pd.Series]:
    """Case-insensitive lookup against name and faceName columns."""
    target = name.casefold()
    for col in ("name", "faceName"):
        if col not in df.columns:
            continue
        series = df[col].astype(str).str.casefold()
        matches = df[series == target]
        if not matches.empty:
            return matches.iloc[0]
    return None


def _fuzzy_match_name(name: str, candidates: list[str], cutoff: float = 0.85) -> Optional[str]:
    """Return the best fuzzy match for name from candidates, or None.

    Matching is case-insensitive; original casing is returned on success.
    """
    lower_to_orig = {c.casefold(): c for c in candidates}
    results = difflib.get_close_matches(
        name.casefold(), list(lower_to_orig.keys()), n=1, cutoff=cutoff
    )
    if not results:
        return None
    return lower_to_orig[results[0]]


def _lookup_commander_row(name: str, df: pd.DataFrame) -> Optional[pd.Series]:
    """Look up a single commander by name in commander_cards.parquet."""
    return _find_card_row(df, name)


def _merge_commander_rows(row1: pd.Series, row2: pd.Series) -> pd.Series:
    """Merge two partner commander rows into a synthetic combined row."""
    merged = row1.copy()
    # Combine names
    merged["name"] = f"{row1.get('name', '')} + {row2.get('name', '')}"
    # Union colorIdentity (normalise to sorted list of unique colour letters)
    ci1 = _parse_tags(row1.get("colorIdentity"))
    ci2 = _parse_tags(row2.get("colorIdentity"))
    merged["colorIdentity"] = sorted(set(ci1) | set(ci2))
    # Union themeTags
    tt1 = _parse_tags(row1.get("themeTags"))
    tt2 = _parse_tags(row2.get("themeTags"))
    merged["themeTags"] = sorted(set(tt1) | set(tt2))
    return merged


def _scryfall_lookup(name: str) -> Optional[dict]:
    """Fetch basic card data from Scryfall /cards/named?exact=... (JSON).

    For MDFC/split cards with ' // ' in the name, only the front face is sent
    since Scryfall rejects the double-slash form in both exact and fuzzy searches.

    Returns a dict with keys 'type_line', 'cmc', 'name' on success, or None on any
    failure (network error, 404, rate-limit, etc.).  Respects Scryfall's 50–100 ms
    guideline (sleeps 100 ms after each call).
    """
    import time  # noqa: PLC0415

    normalised = _normalize_name(name)
    # Always strip everything after " // " — Scryfall rejects MDFC double-slash names
    if " // " in normalised:
        normalised = normalised.split(" // ")[0].strip()

    for param in ("exact", "fuzzy"):
        url = "https://api.scryfall.com/cards/named?" + _urlparse.urlencode(
            {param: normalised, "format": "json"}
        )
        try:
            req = _urllib.Request(url, headers={
                "User-Agent": "MTGPythonDeckbuilder/1.0",
                "Accept": "application/json",
            })
            with _urllib.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            time.sleep(0.1)
            return {
                "name": data.get("name", normalised),
                "type_line": data.get("type_line", ""),
                "cmc": float(data.get("cmc") or 0.0),
            }
        except Exception as exc:
                logger.warning("Scryfall lookup failed for '%s' (%s): %s", normalised, param, exc)

    logger.warning("Scryfall: no result for '%s' after all attempts", name)
    return None


# ---------------------------------------------------------------------------
# M2 public API
# ---------------------------------------------------------------------------

def validate_and_enrich(parsed: ParsedDeck) -> EnrichedDeck:
    """Validate parsed card names against all_cards.parquet and enrich with tags/CMC.

    Unknown cards are listed in EnrichedDeck.unrecognized and excluded from tag
    analysis but still represented as bare EnrichedCard entries (tags=[]).

    Near-miss names are auto-corrected via difflib fuzzy matching (threshold 0.85)
    and a warning is appended to ParsedDeck.warnings.

    Args:
        parsed: Output of DeckListParser.parse().

    Returns:
        EnrichedDeck with enriched card list, commander row, and unrecognized names.
    """
    df = _get_all_cards()
    commander_df = _get_commander_df()

    enriched_cards: list[EnrichedCard] = []
    unrecognized: list[str] = []

    for card in parsed.cards:
        # Normalise Unicode apostrophes/quotes so parquet + Scryfall lookups match
        card = dataclasses.replace(card, name=_normalize_name(card.name))
        row = _find_card_row(df, card.name)
        corrected_name = card.name

        if row is None:
            # --- Fallback 1: strip trailing bracket/paren annotations ---
            # Handles lines like "Bala Ged Recovery // Bala Ged Sanctuary [MDFC: ...]"
            stripped_name = _TRAILING_ANNOTATION_RE.sub("", card.name)
            if stripped_name != card.name:
                row = _find_card_row(df, stripped_name)
                if row is not None:
                    corrected_name = stripped_name

        if row is None and " // " in card.name:
            # --- Fallback 2: try front face of MDFC/split/adventure cards ---
            front_face = card.name.split(" // ")[0].strip()
            # Also strip any annotation from the front face
            front_face = _TRAILING_ANNOTATION_RE.sub("", front_face)
            row = _find_card_row(df, front_face)
            if row is not None:
                corrected_name = front_face

        if row is None:
            # --- Fallback 3: basic land (not in parquet) ---
            basic_key = card.name.casefold().strip()
            if basic_key in _BASIC_LAND_TYPE:
                enriched_cards.append(
                    EnrichedCard(
                        name=card.name,
                        quantity=card.quantity,
                        tags=[],
                        cmc=0.0,
                        type_line=_BASIC_LAND_TYPE[basic_key],
                        is_new=False,
                        price=None,
                        section=card.section,
                    )
                )
                continue

        if row is None:
            # --- Fallback 4: fuzzy correction ---
            assert _all_card_names is not None
            fuzzy = _fuzzy_match_name(card.name, _all_card_names)
            if fuzzy is not None:
                parsed.warnings.append(
                    f"'{card.name}' matched to '{fuzzy}' (auto-corrected)."
                )
                corrected_name = fuzzy
                row = _find_card_row(df, fuzzy)

        if row is None:
            # --- Fallback 5: Scryfall API (catches Universes Beyond reprints etc.) ---
            sf_data = _scryfall_lookup(card.name)
            if sf_data is not None:
                parsed.warnings.append(
                    f"'{card.name}' not in local database; type/CMC sourced from Scryfall"
                    + (f" (found as '{sf_data['name']}')." if sf_data["name"] != card.name else ".")
                )
                enriched_cards.append(
                    EnrichedCard(
                        name=sf_data["name"],
                        quantity=card.quantity,
                        tags=[],
                        cmc=sf_data["cmc"],
                        type_line=sf_data["type_line"],
                        is_new=False,
                        price=None,
                        section=card.section,
                    )
                )
                continue

        if row is None:
            unrecognized.append(card.name)
            parsed.warnings.append(
                f"'{card.name}' was not recognized. "
                "If this is a Universes Beyond card, try the in-universe reprint name "
                "(e.g. the Universes Within version)."
            )
            enriched_cards.append(
                EnrichedCard(
                    name=card.name,
                    quantity=card.quantity,
                    tags=[],
                    cmc=0.0,
                    type_line="",
                    is_new=False,
                    price=None,
                    section=card.section,
                )
            )
            continue

        tags = _parse_tags(row.get("themeTags"))
        cmc = float(row.get("manaValue") or 0.0)
        type_line = str(row.get("type") or "")
        is_new = bool(row.get("isNew") or False)
        price_raw = row.get("price")
        price: float | None = float(price_raw) if price_raw is not None else None
        edhrec_raw = row.get("edhrecRank")
        edhrec_rank: int | None = int(edhrec_raw) if edhrec_raw is not None else None

        enriched_cards.append(
            EnrichedCard(
                name=corrected_name,
                quantity=card.quantity,
                tags=tags,
                cmc=cmc,
                type_line=type_line,
                is_new=is_new,
                price=price,
                edhrec_rank=edhrec_rank,
                section=card.section,
            )
        )

    # Resolve commander row
    commander_row: Optional[pd.Series] = None
    if parsed.commander:
        parts = [p.strip() for p in parsed.commander.split(" + ")]
        if len(parts) == 1:
            commander_row = _lookup_commander_row(parts[0], commander_df)
        else:
            # Partner commanders — merge rows
            rows = [_lookup_commander_row(p, commander_df) for p in parts]
            found = [r for r in rows if r is not None]
            if len(found) == 2:
                commander_row = _merge_commander_rows(found[0], found[1])
            elif len(found) == 1:
                commander_row = found[0]
            # If neither found, commander_row stays None

    return EnrichedDeck(
        commander_row=commander_row,
        cards=enriched_cards,
        unrecognized=unrecognized,
    )


# ===========================================================================
# M3 — Functional Analysis & Theme Detection
# ===========================================================================

from code.deck_builder import builder_constants as _bc  # noqa: E402
from code.deck_builder.theme_catalog_loader import load_theme_catalog  # noqa: E402
from code.deck_builder.theme_matcher import (  # noqa: E402
    ACCEPT_MATCH_THRESHOLD,
    ThemeMatcher,
)
from code.web.services.upgrade_suggestions_service import (  # noqa: E402
    _IDEAL_KEY_TO_TAGS,
)

# Role targets (read once at import time from builder_constants — never hardcoded)
_ROLE_TARGETS: dict[str, int] = {
    "ramp":           _bc.DEFAULT_RAMP_COUNT,
    "removal":        _bc.DEFAULT_REMOVAL_COUNT,
    "wipes":          _bc.DEFAULT_WIPES_COUNT,
    "card_advantage": _bc.DEFAULT_CARD_ADVANTAGE_COUNT,
    "protection":     _bc.DEFAULT_PROTECTION_COUNT,
}
# Lands handled separately (type_line-based count)
_LAND_TARGET: int = _bc.DEFAULT_LAND_COUNT

# Minimum card-support fraction for a tag to be an auto-detect theme candidate
_THEME_FREQ_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# M3 data classes
# ---------------------------------------------------------------------------

@dataclass
class RoleCount:
    actual: int
    target: int
    status: Literal["good", "low", "critical"]


@dataclass
class ThemeCardBreakdown:
    """Per-theme card statistics for display in the analysis panel."""
    card_count: int                           # total quantity-weighted cards matching this theme
    in_commander: bool                        # theme tag appears in commander's own themeTags
    is_user_theme: bool                       # was entered manually by the user
    top_cards: list[tuple[str, int | None]]   # (name, edhrec_rank), sorted asc, top 10


@dataclass
class ThemeDetectionResult:
    user_confirmed: list[str]         # user themes matched via ThemeMatcher
    confirmed: list[str]              # auto-detected, cross-referenced with commander
    possible: list[str]               # auto-detected, not commander-confirmed
    unmatched_user_themes: list[str]  # user themes with no fuzzy match
    signal_tags: dict[str, int]       # tag → count (top candidates before filtering)
    theme_details: dict[str, ThemeCardBreakdown] = field(default_factory=dict)
    # per-theme card breakdown; keyed by canonical theme name


@dataclass
class DeckAnalysis:
    commander_name: str
    color_identity: list[str]
    role_counts: dict[str, RoleCount]  # key matches _IDEAL_KEY_TO_TAGS / _ROLE_TARGETS
    cmc_curve: dict[int, int]          # 0–6, 7+ bucketed under key 7
    color_distribution: dict[str, int] # color pip letter → count
    themes: ThemeDetectionResult
    unrecognized: list[str]
    total_cards: int
    upgrade_token: str                 # set by M5 route; empty string until then
    type_breakdown: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # key: type bucket (Creature/Instant/…/Other); value: [(card_name, quantity), …]
    creature_subtype_counts: dict[str, int] = field(default_factory=dict)
    # subtype → total quantity; only subtypes with count >= _CREATURE_SUBTYPE_MIN_SHOW


# ---------------------------------------------------------------------------
# M3 internal helpers
# ---------------------------------------------------------------------------

def _role_status(actual: int, target: int) -> Literal["good", "low", "critical"]:
    if actual >= target:
        return "good"
    if actual >= target - 2:
        return "low"
    return "critical"


# Ordered from highest to lowest priority for multi-type disambiguation.
# E.g. an Artifact Creature counts as Creature; an Enchantment Land counts as Enchantment.
_TYPE_PRIORITY: list[str] = [
    "Creature",
    "Planeswalker",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Land",
]


def _is_land(type_line: str) -> bool:
    return "land" in type_line.lower()


def _classify_type(type_line: str) -> str:
    """Return the primary type bucket for a card, using _TYPE_PRIORITY order."""
    tl_lower = type_line.lower()
    for t in _TYPE_PRIORITY:
        if t.lower() in tl_lower:
            return t
    return "Other"


def _count_role(cards: list[EnrichedCard], tag_set: frozenset[str]) -> int:
    """Count cards whose tags intersect tag_set (quantity-aware)."""
    total = 0
    for card in cards:
        lower_tags = {t.lower() for t in card.tags}
        if lower_tags & {t.lower() for t in tag_set}:
            total += card.quantity
    return total


def _build_theme_matcher() -> tuple[ThemeMatcher, set[str]]:
    """Load theme catalog and return (ThemeMatcher, set-of-lowercase-theme-names)."""
    entries, _ = load_theme_catalog()
    matcher = ThemeMatcher.from_entries(entries)
    known_lower = {e.theme.lower() for e in entries}
    return matcher, known_lower


# ---------------------------------------------------------------------------
# M3 public API
# ---------------------------------------------------------------------------

def analyze_composition(deck: EnrichedDeck) -> DeckAnalysis:
    """Compute role counts, CMC curve, color distribution, and theme detection.

    Args:
        deck: Output of validate_and_enrich().

    Returns:
        DeckAnalysis with all metrics populated.  upgrade_token is left empty
        (set later by the M5 route after session storage).
    """
    mainboard = [c for c in deck.cards if c.section != "Sideboard"]
    non_land_cards = [c for c in mainboard if not _is_land(c.type_line)]
    land_cards = [c for c in mainboard if _is_land(c.type_line)]

    # --- Role counts (non-land only) ---
    role_counts: dict[str, RoleCount] = {}
    for role_key, tag_set in _IDEAL_KEY_TO_TAGS.items():
        if role_key not in _ROLE_TARGETS:
            continue
        actual = _count_role(non_land_cards, tag_set)
        target = _ROLE_TARGETS[role_key]
        role_counts[role_key] = RoleCount(
            actual=actual,
            target=target,
            status=_role_status(actual, target),
        )
    # Lands counted separately via type_line
    land_actual = sum(c.quantity for c in land_cards)
    role_counts["lands"] = RoleCount(
        actual=land_actual,
        target=_LAND_TARGET,
        status=_role_status(land_actual, _LAND_TARGET),
    )

    # --- CMC curve (non-land cards, 7+ bucketed under key 7) ---
    cmc_curve: dict[int, int] = {i: 0 for i in range(8)}
    for card in non_land_cards:
        bucket = min(int(card.cmc), 7)
        cmc_curve[bucket] += card.quantity

    # --- Color distribution: count pips in colorIdentity fields ---
    color_dist: dict[str, int] = {}
    if deck.commander_row is not None:
        ci_raw = deck.commander_row.get("colorIdentity")
        for pip in _parse_tags(ci_raw):
            letter = pip.strip().upper()
            if letter and len(letter) == 1:
                color_dist[letter] = color_dist.get(letter, 0) + 1

    # --- Type breakdown ---
    type_breakdown: dict[str, list[tuple[str, int]]] = {}
    for card in mainboard:
        bucket = _classify_type(card.type_line)
        type_breakdown.setdefault(bucket, []).append((card.name, card.quantity))
    # Sort each bucket by name; preserve _TYPE_PRIORITY order for keys
    ordered_breakdown: dict[str, list[tuple[str, int]]] = {}
    for t in _TYPE_PRIORITY + ["Other"]:
        if t in type_breakdown:
            ordered_breakdown[t] = sorted(type_breakdown[t], key=lambda x: x[0])

    # --- Creature subtype breakdown ---
    _CREATURE_SUBTYPE_MIN_SHOW = 5
    subtype_raw: dict[str, int] = {}
    for card in mainboard:
        if "creature" not in (card.type_line or "").lower():
            continue
        tl = (card.type_line or "").lower()
        dash_pos = max(tl.find("\u2014"), tl.find("-"))
        if dash_pos == -1:
            continue
        for sub in tl[dash_pos + 1:].split():
            sub = sub.strip()
            if sub:
                subtype_raw[sub] = subtype_raw.get(sub, 0) + card.quantity
    creature_subtype_counts = {
        sub.capitalize(): count
        for sub, count in sorted(subtype_raw.items(), key=lambda x: -x[1])
        if count >= _CREATURE_SUBTYPE_MIN_SHOW
    }

    # --- Theme detection ---
    themes = detect_themes(deck)

    # --- Commander metadata ---
    commander_name = ""
    color_identity: list[str] = []
    if deck.commander_row is not None:
        commander_name = str(deck.commander_row.get("name") or "")
        ci = _parse_tags(deck.commander_row.get("colorIdentity"))
        color_identity = [c.strip().upper() for c in ci if c.strip()]

    return DeckAnalysis(
        commander_name=commander_name,
        color_identity=color_identity,
        role_counts=role_counts,
        cmc_curve=cmc_curve,
        color_distribution=color_dist,
        themes=themes,
        unrecognized=list(deck.unrecognized),
        total_cards=sum(c.quantity for c in mainboard),
        upgrade_token="",
        type_breakdown=ordered_breakdown,
        creature_subtype_counts=creature_subtype_counts,
    )


def detect_themes(
    deck: EnrichedDeck,
    user_themes: Optional[list[str]] = None,
    auto_detect: bool = True,
) -> ThemeDetectionResult:
    """Infer themes from card tag frequency and optional user input.

    Auto-detection:
      - Exclude land cards (type_line contains 'land').
      - Build tag frequency map across non-land non-commander cards.
      - Filter candidates against known theme catalog names.
      - Tags at >=15% frequency → candidate signals; take top 3, plus 4th if
        count_4th >= count_3rd * 0.9.
      - Cross-reference against commander_row.get("themeTags") for confirmed vs possible.

    User themes:
      - Fuzzy-match via ThemeMatcher (accept threshold >= 80.0).
      - Matched → user_confirmed; unmatched → unmatched_user_themes.

    Args:
        deck: Enriched deck from validate_and_enrich().
        user_themes: Optional list of raw theme strings from the user form.
        auto_detect: Whether to run auto-detection alongside user themes.

    Returns:
        ThemeDetectionResult with user_confirmed, confirmed, possible, and signal_tags.
    """
    matcher, known_lower = _build_theme_matcher()

    # --- Shared setup (used by both auto-detection and theme_details) ---
    _cmd_name_lower = ""
    if deck.commander_row is not None:
        _cmd_name_lower = str(deck.commander_row.get("name") or "").lower()

    _analysis_cards = [
        c for c in deck.cards
        if not _is_land(c.type_line) and c.name.lower() != _cmd_name_lower
    ]

    _commander_themes_lower: set[str] = set()
    if deck.commander_row is not None:
        for _ct in _parse_tags(deck.commander_row.get("themeTags")):
            _commander_themes_lower.add(_ct.lower())

    # --- User theme resolution ---
    user_confirmed: list[str] = []
    unmatched_user_themes: list[str] = []
    if user_themes:
        for raw in user_themes:
            result = matcher.resolve(raw)
            if result.matched_theme is not None and result.score >= ACCEPT_MATCH_THRESHOLD:
                user_confirmed.append(result.matched_theme)
            else:
                unmatched_user_themes.append(raw)

    # --- Auto-detection ---
    confirmed: list[str] = []
    possible: list[str] = []
    signal_tags: dict[str, int] = {}

    if auto_detect:
        total_cards = sum(c.quantity for c in _analysis_cards)

        if total_cards > 0:
            # Build tag frequency
            tag_freq: dict[str, int] = {}
            for card in _analysis_cards:
                for tag in card.tags:
                    tag_freq[tag] = tag_freq.get(tag, 0) + card.quantity

            # --- Kindred detection ---
            # Count creature subtypes across all creature cards (quantity-weighted).
            # If a single subtype appears on ≥15 creatures it strongly suggests a
            # Kindred deck.  We check the theme catalog for a matching "X Kindred"
            # or "X Tribal" entry and inject it as a high-signal candidate.
            _KINDRED_THRESHOLD = 15
            subtype_counts: dict[str, int] = {}
            for card in _analysis_cards:
                if "creature" not in (card.type_line or "").lower():
                    continue
                # Subtypes follow the em-dash in the type line: "Creature — Elf Druid"
                type_lower = (card.type_line or "").lower()
                dash_pos = max(type_lower.find("—"), type_lower.find("-"))
                if dash_pos == -1:
                    continue
                subtypes_raw = type_lower[dash_pos + 1:].strip()
                for sub in subtypes_raw.split():
                    sub = sub.strip()
                    if sub:
                        subtype_counts[sub] = subtype_counts.get(sub, 0) + card.quantity

            # Find the dominant subtype (if any clears the threshold)
            dominant = max(subtype_counts, key=lambda s: subtype_counts[s], default=None)
            if dominant and subtype_counts[dominant] >= _KINDRED_THRESHOLD:
                # Try to find a matching theme in the catalog
                dominant_cap = dominant.capitalize()
                kindred_candidates = [
                    name for name in known_lower
                    if dominant in name and ("kindred" in name or "tribal" in name)
                ]
                if kindred_candidates:
                    # Resolve back to properly-cased catalog name
                    matched_theme = next(
                        (t for t in (matcher._theme_names if hasattr(matcher, "_theme_names") else [])
                         if t.lower() in kindred_candidates),
                        None,
                    )
                    if matched_theme is None:
                        # Fall back: build name and fuzzy-resolve
                        for attempt in (f"{dominant_cap} Kindred", f"{dominant_cap} Tribal"):
                            res = matcher.resolve(attempt)
                            if res.matched_theme and res.score >= ACCEPT_MATCH_THRESHOLD:
                                matched_theme = res.matched_theme
                                break
                    if matched_theme:
                        # Inject as a high-priority candidate (above the tag-freq threshold)
                        tag_freq[matched_theme] = max(
                            tag_freq.get(matched_theme, 0),
                            subtype_counts[dominant],
                        )
            # --- End kindred detection ---

            # Filter to known theme catalog names only
            threshold_count = int(total_cards * _THEME_FREQ_THRESHOLD)
            candidates = [
                (tag, count)
                for tag, count in tag_freq.items()
                if tag.lower() in known_lower and count >= threshold_count
            ]
            candidates.sort(key=lambda x: -x[1])

            # Top 3 + optional 4th
            selected: list[tuple[str, int]] = []
            for i, item in enumerate(candidates):
                if i < 3:
                    selected.append(item)
                elif i == 3 and selected:
                    _, count_3rd = selected[-1]
                    if item[1] >= count_3rd * 0.9:
                        selected.append(item)
                else:
                    break

            signal_tags = {tag: count for tag, count in selected}

            # Cross-reference with commander's own themes
            for tag, _ in selected:
                if tag.lower() in _commander_themes_lower:
                    confirmed.append(tag)
                else:
                    possible.append(tag)

    # Deduplicate: user_confirmed takes precedence; remove duplicates from auto results
    user_confirmed_lower = {t.lower() for t in user_confirmed}
    confirmed = [t for t in confirmed if t.lower() not in user_confirmed_lower]
    possible = [t for t in possible if t.lower() not in user_confirmed_lower]

    # --- Theme card breakdown ---
    theme_details: dict[str, ThemeCardBreakdown] = {}
    for _theme in user_confirmed + confirmed + possible:
        _tl = _theme.lower()
        _matching = [c for c in _analysis_cards if any(tg.lower() == _tl for tg in c.tags)]
        _count = sum(c.quantity for c in _matching)
        _sorted = sorted(_matching, key=lambda c: (c.edhrec_rank is None, c.edhrec_rank or 0))
        _top10: list[tuple[str, int | None]] = [(c.name, c.edhrec_rank) for c in _sorted[:10]]
        theme_details[_theme] = ThemeCardBreakdown(
            card_count=_count,
            in_commander=(_tl in _commander_themes_lower),
            is_user_theme=(_theme in user_confirmed),
            top_cards=_top10,
        )

    return ThemeDetectionResult(
        user_confirmed=user_confirmed,
        confirmed=confirmed,
        possible=possible,
        unmatched_user_themes=unmatched_user_themes,
        signal_tags=signal_tags,
        theme_details=theme_details,
    )


def resolve_user_themes(raw_themes: list[str]) -> tuple[list[str], list[str]]:
    """Fuzzy-match raw user theme strings against the theme catalog.

    Args:
        raw_themes: Raw theme strings from user input.

    Returns:
        (matched, unmatched) — matched uses canonical catalog casing.
    """
    matcher, _ = _build_theme_matcher()
    matched: list[str] = []
    unmatched: list[str] = []
    for raw in raw_themes:
        result = matcher.resolve(raw)
        if result.matched_theme is not None and result.score >= ACCEPT_MATCH_THRESHOLD:
            matched.append(result.matched_theme)
        else:
            unmatched.append(raw)
    return matched, unmatched


def build_deck_cards_from_enriched(deck: "EnrichedDeck") -> list:
    """Map EnrichedDeck cards to DeckCard objects for UpgradeSuggestionsService.

    Args:
        deck: Enriched deck with cards and optional commander_row.

    Returns:
        list[DeckCard] — one entry per card (not per quantity).
    """
    from code.web.services.upgrade_suggestions_service import DeckCard  # noqa: PLC0415

    commander_name: str | None = None
    if deck.commander_row is not None:
        try:
            commander_name = deck.commander_row.get("name") or deck.commander_row.get("faceName")
        except Exception:
            pass

    result: list = []
    for card in deck.cards:
        is_commander = bool(commander_name and card.name == commander_name)
        result.append(
            DeckCard(
                name=card.name,
                roles=list(card.tags),
                cmc=card.cmc,
                is_commander=is_commander,
                is_locked=False,
                card_type=card.type_line,
                is_dfc=(" // " in (card.type_line or "")),
            )
        )
    return result


# ===========================================================================
# M6 — Temp-file persistence helpers
# ===========================================================================

import time as _time  # noqa: E402

_TEMP_DIR = "deck_files/temp"
_TEMP_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours


def _temp_path(token: str) -> str:
    return f"{_TEMP_DIR}/{token}.json"


def write_temp_session(
    token: str,
    enriched: "EnrichedDeck",
    analysis: "DeckAnalysis",
    parsed_warnings: list[str],
) -> None:
    """Serialize enriched+analysis to deck_files/temp/{token}.json.

    Silently no-ops on any error (temp persistence is best-effort).
    """
    import os  # noqa: PLC0415

    try:
        os.makedirs(_TEMP_DIR, exist_ok=True)

        commander_row_dict: dict | None = None
        if enriched.commander_row is not None:
            try:
                commander_row_dict = {
                    k: (v.tolist() if hasattr(v, "tolist") else v)
                    for k, v in enriched.commander_row.to_dict().items()
                }
            except Exception:
                pass

        data = {
            "token": token,
            "created_at": _time.time(),
            "parsed_warnings": parsed_warnings,
            "enriched": {
                "commander_row": commander_row_dict,
                "cards": [dataclasses.asdict(c) for c in enriched.cards],
                "unrecognized": enriched.unrecognized,
            },
            "analysis": {
                "commander_name": analysis.commander_name,
                "color_identity": analysis.color_identity,
                "role_counts": {
                    k: dataclasses.asdict(v) for k, v in analysis.role_counts.items()
                },
                "cmc_curve": {str(k): v for k, v in analysis.cmc_curve.items()},
                "color_distribution": analysis.color_distribution,
                "themes": dataclasses.asdict(analysis.themes),
                "unrecognized": analysis.unrecognized,
                "total_cards": analysis.total_cards,
                "upgrade_token": analysis.upgrade_token,
                "type_breakdown": {
                    k: [list(t) for t in v]
                    for k, v in analysis.type_breakdown.items()
                },
                "creature_subtype_counts": analysis.creature_subtype_counts,
            },
        }
        with open(_temp_path(token), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_temp_session(
    token: str,
) -> "tuple[EnrichedDeck, DeckAnalysis, list[str]] | None":
    """Load a previously written temp session.

    Returns (enriched, analysis, parsed_warnings), or None if missing/expired/corrupt.
    """
    import os  # noqa: PLC0415

    path = _temp_path(token)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        # Reject if older than max age
        age = _time.time() - float(data.get("created_at", 0))
        if age > _TEMP_MAX_AGE_SECONDS:
            return None

        # Reconstruct EnrichedDeck
        cr_dict = data["enriched"].get("commander_row")
        if cr_dict is not None:
            try:
                import pandas as pd  # noqa: PLC0415
                commander_row: Optional[pd.Series] = pd.Series(cr_dict)
            except Exception:
                commander_row = None
        else:
            commander_row = None

        cards = [EnrichedCard(**c) for c in data["enriched"]["cards"]]
        enriched = EnrichedDeck(
            commander_row=commander_row,
            cards=cards,
            unrecognized=data["enriched"]["unrecognized"],
        )

        # Reconstruct DeckAnalysis
        a = data["analysis"]
        _td_raw = a["themes"].get("theme_details", {})
        themes = ThemeDetectionResult(
            user_confirmed=a["themes"].get("user_confirmed", []),
            confirmed=a["themes"].get("confirmed", []),
            possible=a["themes"].get("possible", []),
            unmatched_user_themes=a["themes"].get("unmatched_user_themes", []),
            signal_tags=a["themes"].get("signal_tags", {}),
            theme_details={
                k: ThemeCardBreakdown(
                    card_count=v["card_count"],
                    in_commander=v["in_commander"],
                    is_user_theme=v["is_user_theme"],
                    top_cards=[(t[0], t[1]) for t in v.get("top_cards", [])],
                )
                for k, v in _td_raw.items()
            },
        )
        role_counts = {k: RoleCount(**v) for k, v in a["role_counts"].items()}
        cmc_curve = {int(k): v for k, v in a["cmc_curve"].items()}
        type_breakdown: dict[str, list[tuple[str, int]]] = {
            k: [tuple(t) for t in v]  # type: ignore[misc]
            for k, v in a.get("type_breakdown", {}).items()
        }
        analysis = DeckAnalysis(
            commander_name=a["commander_name"],
            color_identity=a["color_identity"],
            role_counts=role_counts,
            cmc_curve=cmc_curve,
            color_distribution=a["color_distribution"],
            themes=themes,
            unrecognized=a["unrecognized"],
            total_cards=a["total_cards"],
            upgrade_token=a["upgrade_token"],
            type_breakdown=type_breakdown,
            creature_subtype_counts=a.get("creature_subtype_counts", {}),
        )

        parsed_warnings: list[str] = data.get("parsed_warnings", [])
        return enriched, analysis, parsed_warnings

    except Exception:
        return None


def purge_old_temp_sessions() -> None:
    """Delete temp session files older than _TEMP_MAX_AGE_SECONDS.

    Called on each new import POST; silently no-ops on any error.
    """
    import os  # noqa: PLC0415

    try:
        cutoff = _time.time() - _TEMP_MAX_AGE_SECONDS
        for fname in os.listdir(_TEMP_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(_TEMP_DIR, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Card pruning helpers
# ---------------------------------------------------------------------------

# Staple roles that are always valuable regardless of deck themes.
# Any card covering one of these tags gets a bonus to prevent it being cut.
_STAPLE_ROLE_GROUPS: dict[str, frozenset[str]] = {
    "Ramp":         frozenset({"Ramp", "Mana Dork", "Mana Rock"}),
    "Removal":      frozenset({"Removal", "Spot Removal", "Interaction"}),
    "Board Wipe":   frozenset({"Board Wipes"}),
    "Card Draw":    frozenset({"Card Draw", "Unconditional Draw", "Card Advantage"}),
    "Protection":   frozenset({"Protective Effects"}),
}
_STAPLE_ROLE_BONUS = 2.5   # per matched staple role group

# Role order for fill suggestions section 1 — (analysis_key, display_label, tag_set_lower)
_ROLE_ORDER: list[tuple[str, str, set[str]]] = [
    ("ramp",           "Ramp",        {"ramp", "mana rock", "mana dork"}),
    ("removal",        "Removal",     {"removal", "spot removal"}),
    ("wipes",          "Board Wipes", {"board wipes"}),
    ("card_advantage", "Card Draw",   {"card draw", "card advantage", "unconditional draw"}),
    ("protection",     "Protection",  {"protective effects"}),
]

# Narrower set used only for replacement matching — excludes broad tags like
# "Interaction" that appear on equipment, stax, and many off-role cards.
_FUNCTIONAL_ROLE_TAGS: frozenset[str] = frozenset({
    "Removal", "Spot Removal", "Board Wipes",
    "Counterspells",
    "Card Draw", "Unconditional Draw", "Card Advantage",
    "Ramp", "Mana Dork", "Mana Rock",
    "Protective Effects",
    "Tutors", "Token Generation", "Reanimation",
    "Extra Turns", "Graveyard Recursion",
})


@dataclass
class CutCandidate:
    """A card ranked as a potential cut, with score breakdown for display."""

    card: EnrichedCard
    score: float
    theme_hits: list[str]       # which active deck themes the card matches
    role_hits: list[str]        # which staple roles (e.g. "Removal") the card covers
    weakness_reasons: list[str] # why it was flagged despite any positives


def _is_land(type_line: str) -> bool:
    """Return True if the type_line indicates a land."""
    return "land" in (type_line or "").lower()


_HIGH_CMC_THRESHOLD = 5       # CMC >= this is flagged as expensive
_RARE_EDHREC_THRESHOLD = 8000  # rank > this (or None) means rarely played


def _card_score_details(
    card: EnrichedCard,
    theme_tags: set[str],
) -> tuple[float, list[str], list[str], list[str]]:
    """Compute weakness score and return (score, theme_hits, role_hits, weakness_reasons).

    Higher score = stronger card = less likely to cut.
    - +3 per matched deck theme tag
    - +2.5 per staple role group covered (Ramp, Removal, Board Wipe, etc.)
    - +1 / log10(edhrec_rank + 10) for EDHREC popularity

    weakness_reasons explains WHY the card was flagged despite any positives:
    - "High CMC" if cmc >= _HIGH_CMC_THRESHOLD
    - "Rarely played" if edhrec_rank > _RARE_EDHREC_THRESHOLD
    - "Not on EDHREC" if edhrec_rank is None
    - "Fills no key role" if on-theme but covers no staple role
    """
    import math  # noqa: PLC0415

    tag_set = {t.lower() for t in card.tags}
    theme_tags_lower = {t.lower() for t in theme_tags}

    # Theme hits
    theme_hits = [t for t in card.tags if t.lower() in theme_tags_lower]
    score = len(theme_hits) * 3.0

    # Staple role hits
    role_hits: list[str] = []
    for role_name, role_tags in _STAPLE_ROLE_GROUPS.items():
        if tag_set & {t.lower() for t in role_tags}:
            role_hits.append(role_name)
            score += _STAPLE_ROLE_BONUS

    # EDHREC popularity
    if card.edhrec_rank is not None:
        score += 1.0 / math.log10(card.edhrec_rank + 10)

    # Weakness reasons — explain why the card is still a cut candidate
    weakness_reasons: list[str] = []
    if (card.cmc or 0) >= _HIGH_CMC_THRESHOLD:
        weakness_reasons.append(f"High CMC ({int(card.cmc)})")
    if card.edhrec_rank is None:
        weakness_reasons.append("Not on EDHREC")
    elif card.edhrec_rank > _RARE_EDHREC_THRESHOLD:
        weakness_reasons.append(f"Rarely played (#{card.edhrec_rank:,})")
    if theme_hits and not role_hits:
        weakness_reasons.append("Fills no key role")

    return score, theme_hits, role_hits, weakness_reasons


def rank_cut_candidates(
    enriched: EnrichedDeck,
    analysis: "DeckAnalysis",
    n_to_cut: int,
) -> list[CutCandidate]:
    """Return the n_to_cut weakest non-land, non-commander cards sorted worst-first.

    Each item is a CutCandidate with score breakdown for display in the UI.
    Lands and the commander are always excluded.
    """
    commander_name_lower = ""
    if enriched.commander_row is not None:
        commander_name_lower = str(enriched.commander_row.get("name") or "").lower()
    elif analysis.commander_name:
        commander_name_lower = analysis.commander_name.lower()

    theme_tags: set[str] = set(
        analysis.themes.user_confirmed + analysis.themes.confirmed + analysis.themes.possible
    )

    candidates = [
        c for c in enriched.cards
        if c.section != "Sideboard"
        and not _is_land(c.type_line)
        and c.name.lower() != commander_name_lower
    ]

    scored: list[CutCandidate] = []
    for card in candidates:
        score, theme_hits, role_hits, weakness_reasons = _card_score_details(card, theme_tags)
        scored.append(CutCandidate(card=card, score=score, theme_hits=theme_hits, role_hits=role_hits, weakness_reasons=weakness_reasons))

    scored.sort(key=lambda x: x.score)  # ascending: weakest first
    return scored[:n_to_cut]


def apply_prune(enriched: EnrichedDeck, names_to_remove: list[str]) -> EnrichedDeck:
    """Return a copy of enriched with the named cards removed.

    Quantity-1 cards are fully removed; quantity>1 cards are decremented by 1 per
    occurrence in names_to_remove (each name in the list removes one copy).
    """
    import dataclasses as _dc  # noqa: PLC0415

    removal_counts: dict[str, int] = {}
    for n in names_to_remove:
        removal_counts[n.lower()] = removal_counts.get(n.lower(), 0) + 1

    new_cards: list[EnrichedCard] = []
    for card in enriched.cards:
        key = card.name.lower()
        to_remove = removal_counts.get(key, 0)
        if to_remove == 0:
            new_cards.append(card)
        elif card.quantity > to_remove:
            new_cards.append(_dc.replace(card, quantity=card.quantity - to_remove))
        # else: fully removed
    return _dc.replace(enriched, cards=new_cards)


# ---------------------------------------------------------------------------
# Duplicate resolution — replacement suggestions per card
# ---------------------------------------------------------------------------

@dataclass
class ReplacementCandidate:
    """A suggested replacement for a duplicate card."""
    name: str
    roles: list[str]          # matching role tags
    matched_roles: list[str]  # roles overlapping with the original card
    cmc: float
    edhrec_rank: int | None
    price: float | None


def get_replacements_for_card(
    card: EnrichedCard,
    enriched: EnrichedDeck,
    color_identity: list[str],
    top_n: int = 8,
) -> list[ReplacementCandidate]:
    """Return up to top_n replacement candidates for a duplicate card.

    Tiers (filled in order until top_n is reached):
    1. Same primary card type  AND  ≥1 functional role tag match
    2. Same primary card type  OR   ≥2 functional role tag matches
    3. ≥1 functional role tag match (any type)
    4. ≥2 overlapping theme tags (any type) — broad fallback

    Within each tier results are sorted by EDHREC rank (most popular first).
    Cards already in the deck are excluded.
    """
    df = _get_all_cards()
    if df is None or df.empty:
        return []

    card_tags_lower = {t.lower() for t in card.tags}
    card_type_lower = (card.type_line or "").lower()

    # Functional roles: narrow set that excludes broad tags like "Interaction"
    functional_lower = {t.lower() for t in _FUNCTIONAL_ROLE_TAGS}
    card_func_roles: set[str] = card_tags_lower & functional_lower

    # If no functional roles, fall back to staple-group tag expansion
    if not card_func_roles:
        for role_name, role_tags in _STAPLE_ROLE_GROUPS.items():
            if card_tags_lower & {t.lower() for t in role_tags}:
                card_func_roles |= {t.lower() for t in role_tags}

    # Build exclusion set: all cards currently in the deck
    existing_lower = {c.name.lower() for c in enriched.cards}

    # Color identity filter — colorless fits anywhere
    allowed_colors = {c.upper() for c in color_identity}

    def _color_ok(ci_raw: object) -> bool:
        tags = _parse_tags(ci_raw)
        if not tags:
            return True
        return {c.strip().upper() for c in tags} <= allowed_colors

    def _type_match(type_raw: object) -> bool:
        """Type-matching rules:
        - Instant  ↔  Sorcery  (freely interchangeable)
        - Artifact—Equipment  ↔  Enchantment—Aura  (same on-body-buff role)
        - General Artifact (no Equipment subtype) matches only Artifacts
        - General Enchantment (no Aura subtype) matches only Enchantments
        - Everything else: exact primary-type match
        """
        ct = str(type_raw).lower()
        # Instant/Sorcery group
        if "instant" in card_type_lower or "sorcery" in card_type_lower:
            return "instant" in ct or "sorcery" in ct
        # Equipment/Aura group (strict — only when original has the subtype)
        if "equipment" in card_type_lower:
            return "equipment" in ct or "aura" in ct
        if "aura" in card_type_lower:
            return "equipment" in ct or "aura" in ct
        # Artifact (non-Equipment): match Artifact but exclude Equipment (different role)
        if "artifact" in card_type_lower:
            return "artifact" in ct and "equipment" not in ct
        # Enchantment (non-Aura): match Enchantment but exclude Aura
        if "enchantment" in card_type_lower:
            return "enchantment" in ct and "aura" not in ct
        # Creature, Planeswalker, etc.: exact primary type match
        primary = next(
            (t for t in ("creature", "planeswalker", "battle")
             if t in card_type_lower),
            None,
        )
        return primary is not None and primary in ct

    def _func_overlap_count(theme_tags_raw: object) -> int:
        tags_lower = {t.lower() for t in _parse_tags(theme_tags_raw)}
        return len(tags_lower & card_func_roles)

    def _any_tag_overlap_count(theme_tags_raw: object) -> int:
        tags_lower = {t.lower() for t in _parse_tags(theme_tags_raw)}
        return len(tags_lower & card_tags_lower)

    def _not_in_deck(name: object) -> bool:
        return str(name).lower() not in existing_lower

    def _not_land(type_raw: object) -> bool:
        return "land" not in str(type_raw).lower()

    try:
        base_mask = (
            df["colorIdentity"].apply(_color_ok)
            & df["name"].apply(_not_in_deck)
            & df["type"].apply(_not_land)
        )
        base = df[base_mask].copy()
        base["_type_match"] = base["type"].apply(_type_match)
        base["_func_overlap"] = base["themeTags"].apply(_func_overlap_count)
        base["_tag_overlap"] = base["themeTags"].apply(_any_tag_overlap_count)
    except Exception:
        return []

    # Define tiers as boolean masks on `base`
    tier1 = base[base["_type_match"] & (base["_func_overlap"] >= 1)]
    tier2 = base[base["_type_match"] | (base["_func_overlap"] >= 2)]
    tier3 = base[base["_func_overlap"] >= 1]
    tier4 = base[base["_tag_overlap"] >= 2]

    def _build_results(frame: "pd.DataFrame", limit: int, seen: set[str]) -> list[ReplacementCandidate]:
        if frame.empty or limit <= 0:
            return []
        frame = frame[~frame["name"].isin(seen)]
        if frame.empty:
            return []
        if "edhrecRank" in frame.columns:
            frame = frame.sort_values("edhrecRank", na_position="last")
        out: list[ReplacementCandidate] = []
        for _, row in frame.iterrows():
            if len(out) >= limit:
                break
            name = str(row.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            roles = _parse_tags(row.get("themeTags"))
            if card_func_roles:
                matched = [r for r in roles if r.lower() in card_func_roles]
            else:
                matched = [r for r in roles if r.lower() in card_tags_lower]
            rank_raw = row.get("edhrecRank")
            rank: int | None = int(rank_raw) if rank_raw is not None and str(rank_raw) != "nan" else None
            price_raw = row.get("price")
            price: float | None = float(price_raw) if price_raw is not None and str(price_raw) != "nan" else None
            out.append(ReplacementCandidate(
                name=name,
                roles=roles,
                matched_roles=matched,
                cmc=float(row.get("manaValue") or 0.0),
                edhrec_rank=rank,
                price=price,
            ))
        return out

    seen_names: set[str] = set()
    results: list[ReplacementCandidate] = []
    for tier in (tier1, tier2, tier3, tier4):
        if len(results) >= top_n:
            break
        results += _build_results(tier, top_n - len(results), seen_names)

    return results


# ---------------------------------------------------------------------------
# Fill suggestions — under-100 decks
# ---------------------------------------------------------------------------

# Role key → display name map (used by fill scoring)
role_key_to_name: dict[str, str] = {
    "ramp": "Ramp",
    "removal": "Removal",
    "wipes": "Board Wipe",
    "card_advantage": "Card Draw",
    "protection": "Protection",
}


@dataclass
class FillSuggestion:
    """A card recommended to fill a gap in an under-100 deck."""
    name: str
    fill_reason: str          # primary reason (role shortfall / theme / general)
    roles: list[str]          # all staple roles this card covers
    matched_roles: list[str]  # roles that are *shortfalls* in the deck (highlighted)
    cmc: float
    edhrec_rank: int | None
    price: float | None
    score: float = 0.0        # composite fitness score (higher = better)


def _fill_score(
    card_tags: list[str],
    needed_roles: dict[str, int],  # role_name → shortfall
    deck_themes: list[str],
) -> tuple[float, list[str], list[str]]:
    """Score a candidate card for fill suggestions.

    Returns (score, matched_roles, matched_themes) where:
    - matched_roles: staple roles the card covers that have a shortfall
    - matched_themes: deck themes the card shares

    Scoring mirrors _card_score_details / sampling._score_card:
    - +3.0 per matched deck theme tag
    - +2.5 per shortfall staple role the card covers
    - +1.0 per additional staple role (no shortfall but still useful)
    - +1.0 / log10(edhrec_rank + 10) for EDHREC popularity (applied by caller)
    """
    import math  # noqa: PLC0415
    tag_lower = {t.lower() for t in card_tags}
    deck_themes_lower = {t.lower() for t in deck_themes}

    theme_hits = [t for t in card_tags if t.lower() in deck_themes_lower]
    score = len(theme_hits) * 3.0

    matched_roles: list[str] = []
    all_covered: list[str] = []
    for role_name, role_tags in _STAPLE_ROLE_GROUPS.items():
        if tag_lower & {t.lower() for t in role_tags}:
            all_covered.append(role_name)
            if role_name in needed_roles:
                matched_roles.append(role_name)
                score += _STAPLE_ROLE_BONUS
            else:
                score += 1.0  # still useful, just not a shortfall role

    return score, matched_roles, all_covered


def get_fill_suggestions(
    enriched: "EnrichedDeck",
    analysis: "DeckAnalysis",
    color_identity: list[str],
    n_to_add: int,
) -> list[FillSuggestion]:
    """Return scored suggestions to fill an under-100 deck.

    Scoring mirrors the upgrade/cut logic:
    - +3 per matched deck theme tag
    - +2.5 per shortfall staple role covered
    - +1 per non-shortfall staple role covered
    - +1/log10(edhrec_rank+10) for EDHREC popularity
    Cards are sorted by score descending within each section so multi-role
    cards naturally float to the top. Three independent sections, merged
    with cross-section deduplication:
    - Role shortfalls: (shortfall + 5) per role
    - Theme fit: (n_to_add + 5) per theme
    - General fit: (n_to_add + 10) with >=2 deck-tag overlap

    Sections are collected independently then merged in order with
    cross-section deduplication, so every section always contributes.
    Cards already in the deck are excluded.
    """
    import math  # noqa: PLC0415

    df = _get_all_cards()
    if df is None or df.empty:
        return []

    existing_lower = {c.name.lower() for c in enriched.cards}
    allowed_colors = {c.upper() for c in color_identity}
    deck_tags_lower: set[str] = {t.lower() for c in enriched.cards for t in c.tags}
    all_themes = (
        list(analysis.themes.user_confirmed)
        + list(analysis.themes.confirmed)
        + list(analysis.themes.possible)
    )

    # Roles with a shortfall: role_name → shortfall count
    needed_roles: dict[str, int] = {
        role_key_to_name[k]: rc.target - rc.actual
        for k, rc in analysis.role_counts.items()
        if rc.actual < rc.target
    }
    # Map role analysis keys → display names matching _STAPLE_ROLE_GROUPS
    # (analysis keys: "ramp", "removal", "wipes", "card_advantage", "protection")

    def _color_ok(ci_raw: object) -> bool:
        tags = _parse_tags(ci_raw)
        return not tags or {c.strip().upper() for c in tags} <= allowed_colors

    def _not_land(type_raw: object) -> bool:
        return "land" not in str(type_raw).lower()

    try:
        base_mask = (
            df["colorIdentity"].apply(_color_ok)
            & ~df["name"].apply(lambda n: str(n).lower() in existing_lower)
            & df["type"].apply(_not_land)
        )
        base = df[base_mask]
    except Exception:
        return []

    def _score_row(row: "pd.Series") -> tuple[float, list[str], list[str]]:
        """Compute (score, matched_roles, all_roles) for a parquet row."""
        card_tags = _parse_tags(row.get("themeTags"))
        base_score, matched_roles, all_roles = _fill_score(card_tags, needed_roles, all_themes)
        rank_raw = row.get("edhrecRank")
        rank: int | None = int(rank_raw) if rank_raw is not None and str(rank_raw) != "nan" else None
        if rank is not None:
            base_score += 1.0 / math.log10(rank + 10)
        return base_score, matched_roles, all_roles

    def _make_suggestion(row: "pd.Series", reason: str) -> "FillSuggestion":
        score, matched_roles, all_roles = _score_row(row)
        name = str(row.get("name") or "")
        rank_raw = row.get("edhrecRank")
        rank: int | None = int(rank_raw) if rank_raw is not None and str(rank_raw) != "nan" else None
        price_raw = row.get("price")
        price: float | None = float(price_raw) if price_raw is not None and str(price_raw) != "nan" else None
        return FillSuggestion(
            name=name,
            fill_reason=reason,
            roles=all_roles,
            matched_roles=matched_roles,
            cmc=float(row.get("manaValue") or 0.0),
            edhrec_rank=rank,
            price=price,
            score=score,
        )

    def _collect_scored(
        frame: "pd.DataFrame",
        reason: str,
        limit: int,
        seen: set[str],
    ) -> list["FillSuggestion"]:
        """Score, sort descending, pull up to `limit` cards from `frame`."""
        suggestions: list[FillSuggestion] = []
        for _, row in frame.iterrows():
            name = str(row.get("name") or "")
            if not name or name.lower() in seen:
                continue
            suggestions.append(_make_suggestion(row, reason))
        suggestions.sort(key=lambda s: -s.score)
        out: list[FillSuggestion] = []
        for s in suggestions:
            if len(out) >= limit:
                break
            if s.name not in seen:
                seen.add(s.name.lower())
                out.append(s)
        return out

    section_results: list[list[FillSuggestion]] = []

    # ------------------------------------------------------------------
    # Section 1 — Staple role shortfalls
    # ------------------------------------------------------------------
    role_section: list[FillSuggestion] = []
    role_seen: set[str] = set()
    for role_key, label, role_tags_lower_set in _ROLE_ORDER:
        rc = analysis.role_counts.get(role_key)
        if rc is None or rc.actual >= rc.target:
            continue
        shortfall = rc.target - rc.actual
        reason = f"{label} (need {shortfall} more)"

        def _has_role(theme_tags_raw: object, _rtl: set = role_tags_lower_set) -> bool:
            return bool({t.lower() for t in _parse_tags(theme_tags_raw)} & _rtl)

        role_section += _collect_scored(
            base[base["themeTags"].apply(_has_role)],
            reason,
            shortfall + 5,
            role_seen,
        )
    section_results.append(role_section)

    # ------------------------------------------------------------------
    # Section 2 — Theme fit
    # ------------------------------------------------------------------
    theme_section: list[FillSuggestion] = []
    theme_seen: set[str] = set()
    for theme in all_themes:
        theme_lower = theme.lower()

        def _has_theme(theme_tags_raw: object, _tl: str = theme_lower) -> bool:
            return _tl in {t.lower() for t in _parse_tags(theme_tags_raw)}

        theme_section += _collect_scored(
            base[base["themeTags"].apply(_has_theme)],
            f"Theme: {theme}",
            n_to_add + 5,
            theme_seen,
        )
    section_results.append(theme_section)

    # ------------------------------------------------------------------
    # Section 3 — General fit (≥2 deck-tag overlap)
    # ------------------------------------------------------------------
    def _general_overlap(theme_tags_raw: object) -> bool:
        return len({t.lower() for t in _parse_tags(theme_tags_raw)} & deck_tags_lower) >= 2

    general_seen: set[str] = set()
    general_section = _collect_scored(
        base[base["themeTags"].apply(_general_overlap)],
        "General Fit",
        n_to_add + 10,
        general_seen,
    )
    section_results.append(general_section)

    # ------------------------------------------------------------------
    # Merge with cross-section dedup, preserve within-section score order
    # ------------------------------------------------------------------
    final_seen: set[str] = set()
    merged: list[FillSuggestion] = []
    for section in section_results:
        for item in section:
            key = item.name.lower()
            if key not in final_seen:
                final_seen.add(key)
                merged.append(item)

    return merged


# ---------------------------------------------------------------------------
# M6 — save_imported_deck
# ---------------------------------------------------------------------------

import csv as _csv  # noqa: E402
import re as _re  # noqa: E402
from datetime import date as _date  # noqa: E402

_DECK_FILES_DIR = "deck_files"

# CSV column order matching existing built-deck schema (as read by upgrade_suggestions._load_deck)
_CSV_HEADERS = [
    "Name", "Count", "Type", "ManaCost", "ManaValue", "Colors",
    "Power", "Toughness", "Role", "SubRole", "AddedBy", "TriggerTag",
    "Synergy", "Tags", "MetadataTags", "Text", "DFCNote", "Owned",
    "Price (TCGPlayer)",
]


def _safe_slug(name: str) -> str:
    """Convert a card name to a filesystem-safe slug (removes punctuation, collapses spaces)."""
    slug = _re.sub(r"[^\w\s-]", "", name)
    slug = _re.sub(r"[\s]+", "_", slug.strip())
    return slug[:60]  # cap length


def save_imported_deck(
    token: str,
    enriched: "EnrichedDeck",
    analysis: "DeckAnalysis",
    deck_dir: Optional[str] = None,
) -> tuple[str, str, str]:
    """Write permanent deck files for an imported deck.

    Creates three files atomically in ``deck_dir`` (defaults to the shared
    ``deck_files/`` root when omitted; callers should pass the importing
    user's own per-user directory, e.g. ``deck_files/{user_id}/``):
      - ``{slug}_{date}.csv``   - full card list in built-deck CSV schema
      - ``{slug}_{date}.txt``   - one-line-per-card plain text list
      - ``{slug}_{date}.summary.json`` - metadata sidecar (source="imported")

    Returns (csv_name, txt_name, summary_name) - bare filenames (no directory).

    Raises RuntimeError on any write failure.
    """
    import os  # noqa: PLC0415

    deck_dir = deck_dir or _DECK_FILES_DIR
    commander_name = analysis.commander_name or "Unknown"
    slug = _safe_slug(commander_name)
    today = _date.today().strftime("%Y%m%d")
    base = f"{slug}_{today}"

    # Avoid clobbering an existing file for same commander on same day
    os.makedirs(deck_dir, exist_ok=True)
    counter = 0
    while True:
        suffix = f"_{counter}" if counter else ""
        csv_name = f"{base}{suffix}.csv"
        csv_path = os.path.join(deck_dir, csv_name)
        if not os.path.exists(csv_path):
            break
        counter += 1

    txt_name = csv_name.replace(".csv", ".txt")
    summary_name = csv_name.replace(".csv", ".summary.json")
    txt_path = os.path.join(deck_dir, txt_name)
    summary_path = os.path.join(deck_dir, summary_name)

    themes = (
        analysis.themes.user_confirmed
        + [t for t in analysis.themes.confirmed if t not in analysis.themes.user_confirmed]
    )

    # Derive colorIdentity as a simple string for Colors column (e.g. "WUBR")
    color_str = "".join(analysis.color_identity)

    # --- CSV ---
    try:
        # Commander note in last header column (matches builder convention)
        commander_col = f"Commanders: {commander_name}"
        headers_with_note = _CSV_HEADERS + [commander_col]

        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = _csv.writer(fh)
            writer.writerow(headers_with_note)

            for card in enriched.cards:
                if card.section == "Sideboard":
                    continue
                is_cmd = card.name == commander_name
                role = "commander" if is_cmd else "creature" if "Creature" in (card.type_line or "") else "spell"
                tags_str = "; ".join(card.tags) if card.tags else ""
                dfc_note = "DFC" if (" // " in (card.type_line or "") or " // " in card.name) else ""
                price_str = f"{card.price:.2f}" if card.price is not None else ""
                writer.writerow([
                    card.name,          # Name
                    card.quantity,      # Count
                    card.type_line or "",  # Type
                    "",                 # ManaCost (not stored in import pipeline)
                    card.cmc if card.cmc else "",  # ManaValue
                    color_str if is_cmd else "",   # Colors (commander row only)
                    "",                 # Power
                    "",                 # Toughness
                    role,               # Role
                    "",                 # SubRole
                    "",                 # AddedBy
                    "",                 # TriggerTag
                    "",                 # Synergy
                    tags_str,           # Tags
                    "",                 # MetadataTags
                    "",                 # Text
                    dfc_note,           # DFCNote
                    "",                 # Owned
                    price_str,          # Price (TCGPlayer)
                    "",                 # commander_col (blank for non-header rows)
                ])
    except Exception as exc:
        raise RuntimeError(f"Failed to write CSV: {exc}") from exc

    # --- TXT ---
    try:
        lines: list[str] = [f"# Commanders: {commander_name}", ""]
        for card in enriched.cards:
            if card.section == "Sideboard":
                continue
            lines.append(f"{card.quantity} {card.name}")
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception as exc:
        # Clean up CSV on partial failure
        try:
            os.remove(csv_path)
        except Exception:
            pass
        raise RuntimeError(f"Failed to write TXT: {exc}") from exc

    # --- Summary JSON ---
    try:
        from .deck_visibility import resolve_visibility_for_write  # noqa: PLC0415

        meta = {
            "commander": commander_name,
            "commander_names": [commander_name],
            "name": commander_name,
            "tags": themes,
            "color_identity": analysis.color_identity,
            "source": "imported",
            "csv": csv_name,
            "txt": txt_name,
            "import_token": token,
            "visibility": resolve_visibility_for_write(csv_path, deck_dir=deck_dir),
        }
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "summary": {}}, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        try:
            os.remove(csv_path)
            os.remove(txt_path)
        except Exception:
            pass
        raise RuntimeError(f"Failed to write summary JSON: {exc}") from exc

    # Delete temp file on success (best-effort)
    try:
        temp = _temp_path(token)
        if os.path.isfile(temp):
            os.remove(temp)
    except Exception:
        pass

    return csv_name, txt_name, summary_name
