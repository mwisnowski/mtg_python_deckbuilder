"""Detect tokens/emblems a deck's cards will create (roadmap_39, Milestone 5).

Pure functions, no builder-instance dependency -- mirrors the `combos.py`
pattern. Purely informational: never affects deck legality, card count,
price totals, or bracket compliance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from code.file_setup.token_setup import _token_text_fingerprint

DEFAULT_TOKENS_PATH = "card_files/processed/tokens.parquet"


@dataclass(frozen=True)
class TokenRef:
    name: str
    type: str
    power: Optional[str]
    toughness: Optional[str]
    text: str
    is_emblem: bool
    colors: str = ""

    def text_hash(self) -> str:
        """Short fingerprint of this identity's ability text -- disambiguates
        same name/type/stats/colors variants that differ only by text (e.g. a
        vanilla 1/1 Fish vs. one that "can't be blocked") without having to
        thread raw oracle text through client-facing URLs/forms."""
        return _token_text_fingerprint(self.text)

    def identity_key(self) -> str:
        """Stable string key for this identity, used to persist a per-deck
        printing (art) selection -- mirrors `image_cache._token_identity_key()`."""
        return "|".join([
            self.name.strip().lower(),
            self.type.strip().lower(),
            (self.power or "").strip(),
            (self.toughness or "").strip(),
            self.colors.strip().upper(),
            self.text_hash(),
        ])


@dataclass(frozen=True)
class DetectedTokenSource:
    token: TokenRef
    created_by: List[str] = field(default_factory=list)


def _canonicalize(name: str) -> str:
    return " ".join(str(name or "").strip().split())


def _clean_pt(value: object) -> Optional[str]:
    """Normalize a power/toughness value, collapsing NaN/None to None.

    Non-creature tokens (Treasure, Plot, Powerstone, etc.) have no P/T, and
    pandas represents that as float('nan') rather than None after a parquet
    round-trip -- str(nan) would otherwise leak "nan" into the UI.
    """
    if value is None:
        return None
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _clean_colors(value: object) -> str:
    """Normalize a colors array to a stable, order-independent string (e.g. "RW").

    Same-named, same-typed tokens can still be genuinely distinct identities
    that differ only by color (e.g. a plain white 1/1 Soldier vs. a red/white
    1/1 Soldier) -- type/power/toughness alone don't disambiguate those, so
    color must be part of the identity too.
    """
    if value is None:
        return ""
    try:
        items = [str(c).strip().upper() for c in list(value) if str(c or "").strip()]
    except TypeError:
        return ""
    return "".join(sorted(items))


def _load_token_reverse_index(tokens_path: str | Path = DEFAULT_TOKENS_PATH) -> Dict[str, List[TokenRef]]:
    """Build a creator-name (casefolded) -> [TokenRef, ...] map from `relatedCards`.

    Returns {} gracefully if the catalog doesn't exist yet (dev environment
    that hasn't run the token-catalog pipeline step) -- never raises.
    """
    try:
        import pandas as pd

        path = Path(tokens_path)
        if not path.exists():
            return {}
        df = pd.read_parquet(path)
    except Exception:
        return {}

    index: Dict[str, List[TokenRef]] = {}
    for row in df.itertuples(index=False):
        related = getattr(row, "relatedCards", None)
        if related is None:
            continue
        creators = [str(c) for c in list(related) if str(c or "").strip()]
        if not creators:
            continue

        token = TokenRef(
            name=str(getattr(row, "name", "") or ""),
            type=str(getattr(row, "type", "") or ""),
            power=_clean_pt(getattr(row, "power", None)),
            toughness=_clean_pt(getattr(row, "toughness", None)),
            text=str(getattr(row, "text", "") or ""),
            is_emblem=bool(getattr(row, "isEmblem", False)),
            colors=_clean_colors(getattr(row, "colors", None)),
        )
        for creator in creators:
            key = creator.strip().casefold()
            index.setdefault(key, []).append(token)
    return index


def token_ref_to_dict(token: TokenRef) -> dict:
    """Serialize a `TokenRef` into the same plain-dict shape used by
    `phase6_reporting.py`'s `tokens_created` (name/type/power/toughness/
    is_emblem/colors/key/text_hash), so templates can share one rendering
    pattern (e.g. the image query-string) regardless of source."""
    return {
        "name": token.name,
        "type": token.type,
        "power": token.power,
        "toughness": token.toughness,
        "is_emblem": token.is_emblem,
        "colors": token.colors,
        "key": token.identity_key(),
        "text_hash": token.text_hash(),
        "text": token.text,
    }


def _token_row_key(name: object, type_: object, power: object, toughness: object, colors: object, text: object) -> str:
    """Stable identity key for a token/emblem catalog row -- mirrors
    `TokenRef.identity_key()` byte-for-byte (same normalized colors/text_hash
    helpers, computed from the raw parquet `colors` array rather than the
    browser DataFrame's comma-formatted string) so a printing choice keys
    the same whether the token was reached via the card browser's search
    results or a card's "Tokens Generated" panel."""
    return "|".join([
        str(name or "").strip().lower(),
        str(type_ or "").strip().lower(),
        _clean_pt(power) or "",
        _clean_pt(toughness) or "",
        _clean_colors(colors),
        _token_text_fingerprint(str(text or "")),
    ])


def _format_color_array(value: object) -> str:
    """Normalize a `colors`/`colorIdentity` array cell into the
    comma-delimited string format `card_search.parse_color_cell()` expects
    (e.g. "R, W"), matching the format used by `all_cards.parquet`."""
    if value is None:
        return ""
    try:
        items = [str(c).strip().upper() for c in list(value) if str(c or "").strip()]
    except TypeError:
        return ""
    return ", ".join(sorted(items))


def load_tokens_browser_df(tokens_path: str | Path = DEFAULT_TOKENS_PATH):
    """Load `tokens.parquet`, normalized into rows the card browser's
    search/filter pipeline (`apply_parsed_search`/`apply_extra_clauses`,
    both built for `all_cards.parquet`'s schema) can safely process.

    Tokens/emblems have no mana cost, rarity, printings, or EDHREC rank, so
    those columns are filled with neutral defaults (never `NaN`, which is
    truthy in Jinja and would leak into badges/filters meant for real
    cards). Marks each row `is_token`/`is_emblem` so callers can identify
    and gate on them (see `card_browser.py`'s `_wants_tokens`).

    Returns an empty DataFrame gracefully if the catalog doesn't exist yet
    (dev environment that hasn't run the token-catalog pipeline step).
    """
    import pandas as pd

    path = Path(tokens_path)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    text = df["text"].fillna("").astype(str) if "text" in df.columns else ""
    return pd.DataFrame({
        "name": df["name"].astype(str),
        "type": df["type"].fillna("").astype(str) if "type" in df.columns else "",
        "text": text,
        "colors": df["colors"].apply(_format_color_array) if "colors" in df.columns else "",
        "colorIdentity": df["colorIdentity"].apply(_format_color_array) if "colorIdentity" in df.columns else "",
        "power": df.get("power"),
        "toughness": df.get("toughness"),
        "layout": df["layout"].fillna("").astype(str) if "layout" in df.columns else "",
        "themeTags": df.get("themeTags"),
        "metadataTags": df.get("metadataTags"),
        "manaValue": 0.0,
        "manaCost": "",
        "loyalty": None,
        "rarity": "",
        "artTags": None,
        "isNew": False,
        "isReprint": False,
        "printings": "",
        "edhrecRank": None,
        "is_token": True,
        "is_emblem": df["isEmblem"].astype(bool) if "isEmblem" in df.columns else False,
        "text_hash": text.apply(_token_text_fingerprint) if hasattr(text, "apply") else "",
        "key": df.apply(
            lambda row: _token_row_key(
                row.get("name"), row.get("type"), row.get("power"), row.get("toughness"),
                row.get("colors"), row.get("text"),
            ),
            axis=1,
        ),
    })


def detect_tokens_created(
    names: Iterable[str],
    tokens_path: str | Path = DEFAULT_TOKENS_PATH,
) -> List[DetectedTokenSource]:
    """Return the distinct token(s)/emblem(s) a given set of card names will create.

    Multiple creators of the identical token are merged into one entry with
    all creator names recorded. Self-token-copy effects (Offspring/Embalm/
    Eternalize -- roadmap_39 Milestone 4) have no fixed identity and are not
    covered by this detector; they're surfaced via the `Token Copy: {Ability}`
    metadataTag instead.
    """
    index = _load_token_reverse_index(tokens_path)
    if not index:
        return []

    # token identity -> (TokenRef, [creators]) -- preserves first-seen order.
    merged: Dict[tuple, DetectedTokenSource] = {}
    for raw_name in names:
        card_name = _canonicalize(raw_name)
        if not card_name:
            continue
        matches = index.get(card_name.casefold())
        if not matches:
            continue
        for token in matches:
            key = (token.name, token.type, token.power, token.toughness, token.is_emblem, token.colors)
            existing = merged.get(key)
            if existing is None:
                merged[key] = DetectedTokenSource(token=token, created_by=[card_name])
            elif card_name not in existing.created_by:
                existing.created_by.append(card_name)

    return list(merged.values())
