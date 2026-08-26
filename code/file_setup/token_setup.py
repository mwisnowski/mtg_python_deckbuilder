"""Build the canonical token/emblem catalog parquet from MTGJSON's raw tokens.parquet.

Produces `card_files/processed/tokens.parquet`, a deduplicated catalog of every
token and emblem (analogous to `all_cards.parquet` but for tokens/emblems),
with a `relatedCards` column listing the known creator card(s) for each
identity. See `logs/roadmaps/roadmap_39_tokens_and_emblems.md` (Milestone 1).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_RAW_PATH = "card_files/raw/tokens.parquet"
DEFAULT_OUTPUT_PATH = "card_files/processed/tokens.parquet"

# Layouts in scope per the roadmap; art_series/front_card/normal/reversible_card
# are confirmed noise (checklist/helper cards, art-series duplicates) and are
# excluded.
_IN_SCOPE_LAYOUTS = ("token", "double_faced_token", "flip", "emblem")

# Columns compared to identify distinct face content when pairing side a/b
# rows of a dual-faced token (double_faced_token or flip layout). "colors" is
# included because two faces can otherwise share type/text/power/toughness
# and differ only by color (e.g. a red vs. white 1/1 Soldier face).
_FACE_CONTENT_COLS = ["type", "text", "power", "toughness", "colors"]

_OUTPUT_COLUMNS = [
    "name", "layout", "type", "text", "power", "toughness",
    "colors", "colorIdentity", "subtypes", "keywords", "isEmblem", "relatedCards",
    "faceName_a", "faceName_b",
    "face_a_type", "face_a_text", "face_a_power", "face_a_toughness", "face_a_keywords",
    "face_b_type", "face_b_text", "face_b_power", "face_b_toughness", "face_b_keywords",
]

_SMART_QUOTES = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
}


def _normalize_str(value: Any) -> str:
    """Normalize whitespace/smart-quotes so cosmetic reprint differences don't split identities."""
    if not isinstance(value, str):
        return ""
    text = value
    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)
    return re.sub(r"\s+", " ", text).strip()


def _token_text_fingerprint(text: Any) -> str:
    """Short, URL/attribute-safe stand-in for a token's ability text.

    Same-named/typed/stat/color tokens can still be distinct identities that
    differ only by ability text (e.g. a vanilla 1/1 Fish vs. one that "can't
    be blocked") -- raw oracle text is unsafe to thread through client-facing
    URLs/hx-vals JSON (quotes, apostrophes, newlines), so a stable hash is
    used everywhere instead of the text itself.
    """
    import hashlib

    return hashlib.sha1(_normalize_str(text).encode("utf-8")).hexdigest()[:12]


def _normalize_oracle_templating(name: Any, text: Any) -> str:
    """Fold known WotC oracle-templating rewordings (self-referential card
    name -> "this token", "enters the battlefield" -> "enters") into one
    comparable form, so a token reprinted with only a wording update (not a
    functional change) isn't treated as a distinct catalog identity. Used
    for grouping only -- the original wording is preserved for display.
    """
    normalized = _normalize_str(text)
    name_norm = _normalize_str(name)
    if name_norm:
        normalized = re.sub(re.escape(name_norm), "this token", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("enters the battlefield", "enters")
    return normalized.lower()


def _split_list_field(value: Any) -> list[str]:
    """Split MTGJSON's comma-separated string fields (colors, subtypes, ...) into a list."""
    if not isinstance(value, str) or not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_related_cards(raw: Any) -> list[str]:
    """Parse the `relatedCards` JSON string into a list of reverse-related creator names."""
    if not raw or not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Skipping malformed relatedCards JSON (%s): %s", exc, raw[:80])
        return []
    related = parsed.get("reverseRelated") if isinstance(parsed, dict) else None
    if not isinstance(related, list):
        return []
    return [str(r).strip() for r in related if isinstance(r, str) and r.strip()]


def _empty_face_fields() -> dict[str, Any]:
    return {
        "faceName_a": None, "faceName_b": None,
        "face_a_type": None, "face_a_text": None, "face_a_power": None, "face_a_toughness": None,
        "face_a_keywords": None,
        "face_b_type": None, "face_b_text": None, "face_b_power": None, "face_b_toughness": None,
        "face_b_keywords": None,
    }


def _build_emblem_rows(emblem_df: pd.DataFrame) -> list[dict]:
    """Dedup emblem rows by (name, text, colors), unioning relatedCards across reprints."""
    rows: list[dict] = []
    if emblem_df.empty:
        return rows

    for (name, text, colors), group in emblem_df.groupby(["name", "text", "colors"], dropna=False, sort=False):
        related: list[str] = []
        for raw in group["relatedCards"]:
            related.extend(_parse_related_cards(raw))
        first = group.iloc[0]
        rows.append({
            "name": name,
            "layout": "emblem",
            "type": first["type"],
            "text": text,
            "power": None,
            "toughness": None,
            "colors": _split_list_field(first["colors"]),
            "colorIdentity": _split_list_field(first["colorIdentity"]),
            "subtypes": _split_list_field(first["subtypes"]),
            "keywords": _split_list_field(first["keywords"]),
            "isEmblem": True,
            "relatedCards": sorted(set(related)),
            **_empty_face_fields(),
        })
    return rows


def _build_single_face_rows(token_df: pd.DataFrame) -> list[dict]:
    """Dedup single-sided token rows by (name, power, toughness, colors,
    normalized text).

    Colors must be part of the key: two otherwise-identical tokens (e.g. a red
    1/1 Soldier and a white 1/1 Soldier with no rules text) can share every
    other field and are still genuinely distinct identities.

    `type` is intentionally excluded from the key and normalized text (see
    `_normalize_oracle_templating`) is used instead of raw text: reprints of
    the same token sometimes carry a corrected creature subtype or an updated
    oracle-text template (e.g. "enters the battlefield" -> "enters") despite
    being functionally identical, and grouping on the raw values would show
    these as separate near-duplicate catalog entries.
    """
    rows: list[dict] = []
    if token_df.empty:
        return rows

    token_df = token_df.copy()
    token_df["_group_text"] = token_df.apply(
        lambda row: _normalize_oracle_templating(row["name"], row["text"]), axis=1
    )
    # Prefer the modern, non-self-referential wording ("this token enters")
    # as the displayed variant when a group spans a templating change.
    token_df["_self_ref"] = token_df.apply(
        lambda row: str(row["name"]).strip().lower() in str(row["text"]).lower(), axis=1
    )

    group_cols = ["name", "power", "toughness", "colors", "_group_text"]
    for key, group in token_df.groupby(group_cols, dropna=False, sort=False):
        name, power, toughness, _colors, _group_text = key
        related: list[str] = []
        for raw in group["relatedCards"]:
            related.extend(_parse_related_cards(raw))
        first = group.sort_values("_self_ref").iloc[0]
        rows.append({
            "name": name,
            "layout": "token",
            "type": first["type"],
            "text": first["text"],
            "power": power,
            "toughness": toughness,
            "colors": _split_list_field(first["colors"]),
            "colorIdentity": _split_list_field(first["colorIdentity"]),
            "subtypes": _split_list_field(first["subtypes"]),
            "keywords": _split_list_field(first["keywords"]),
            "isEmblem": False,
            "relatedCards": sorted(set(related)),
            **_empty_face_fields(),
        })
    return rows


def _build_dual_face_rows(dual_df: pd.DataFrame) -> list[dict]:
    """Collapse double_faced_token/flip side a/b rows into one logical row per name.

    Faces are paired by matching content (type/text/power/toughness) rather than
    `otherFaceIds`, since some reprints omit `otherFaceIds` entirely -- content-based
    pairing works uniformly for both cases and degrades gracefully (falls back to
    independent single-sided rows) when a name's faces can't be cleanly paired.
    """
    rows: list[dict] = []
    if dual_df.empty:
        return rows

    for name, group in dual_df.groupby("name", sort=False):
        layout = group["layout"].iloc[0]
        related: list[str] = []
        for raw in group["relatedCards"]:
            related.extend(_parse_related_cards(raw))
        related = sorted(set(related))

        a_variants = group[group["side"] == "a"].drop_duplicates(subset=_FACE_CONTENT_COLS)
        b_variants = group[group["side"] == "b"].drop_duplicates(subset=_FACE_CONTENT_COLS)

        if len(a_variants) == 1 and len(b_variants) == 1:
            a = a_variants.iloc[0]
            b = b_variants.iloc[0]
            rows.append({
                "name": name,
                "layout": layout,
                "type": a["type"],
                "text": a["text"],
                "power": a["power"],
                "toughness": a["toughness"],
                "colors": _split_list_field(a["colors"]),
                "colorIdentity": _split_list_field(a["colorIdentity"]),
                "subtypes": _split_list_field(a["subtypes"]),
                "keywords": _split_list_field(a["keywords"]),
                "isEmblem": False,
                "relatedCards": related,
                "faceName_a": a["faceName"],
                "faceName_b": b["faceName"],
                "face_a_type": a["type"], "face_a_text": a["text"],
                "face_a_power": a["power"], "face_a_toughness": a["toughness"],
                "face_a_keywords": _split_list_field(a["keywords"]),
                "face_b_type": b["type"], "face_b_text": b["text"],
                "face_b_power": b["power"], "face_b_toughness": b["toughness"],
                "face_b_keywords": _split_list_field(b["keywords"]),
            })
        else:
            logger.warning(
                "Could not cleanly pair faces for dual-face token '%s' (%d 'a' variant(s), "
                "%d 'b' variant(s)); keeping each variant as an independent single-sided row.",
                name, len(a_variants), len(b_variants),
            )
            for _, variant in pd.concat([a_variants, b_variants]).iterrows():
                rows.append({
                    "name": name,
                    "layout": layout,
                    "type": variant["type"],
                    "text": variant["text"],
                    "power": variant["power"],
                    "toughness": variant["toughness"],
                    "colors": _split_list_field(variant["colors"]),
                    "colorIdentity": _split_list_field(variant["colorIdentity"]),
                    "subtypes": _split_list_field(variant["subtypes"]),
                    "keywords": _split_list_field(variant["keywords"]),
                    "isEmblem": False,
                    "relatedCards": related,
                    **_empty_face_fields(),
                })
    return rows


def build_tokens_parquet(
    raw_path: str = DEFAULT_RAW_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> pd.DataFrame:
    """Build the canonical token/emblem catalog and write it to `output_path`.

    Args:
        raw_path: Path to MTGJSON's raw tokens.parquet (already downloaded).
        output_path: Path to write the processed token/emblem catalog to.

    Returns:
        The resulting catalog DataFrame (also written to `output_path`).

    Raises:
        FileNotFoundError: If `raw_path` doesn't exist.
    """
    raw_file = Path(raw_path)
    if not raw_file.exists():
        raise FileNotFoundError(
            f"Raw tokens parquet not found at '{raw_path}'. Download MTGJSON's "
            "tokens.parquet before building the token/emblem catalog."
        )

    df = pd.read_parquet(raw_file)
    df = df[df["layout"].isin(_IN_SCOPE_LAYOUTS)].copy()
    df["name"] = df["name"].apply(_normalize_str)
    df["type"] = df["type"].apply(_normalize_str)
    df["text"] = df["text"].apply(_normalize_str)

    rows = (
        _build_emblem_rows(df[df["layout"] == "emblem"])
        + _build_single_face_rows(df[df["layout"] == "token"])
        + _build_dual_face_rows(df[df["layout"].isin(("double_faced_token", "flip"))])
    )

    # Identities with no known creator card (mostly convention/game-night promos and
    # special-event tokens, e.g. bundle checklist tokens) have no practical use for
    # deck-building token surfacing (Milestone 5), so they're dropped entirely.
    rows = [row for row in rows if row["relatedCards"]]

    result = pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_file, index=False)

    token_count = int((~result["isEmblem"]).sum())
    emblem_count = int(result["isEmblem"].sum())
    logger.info(
        "Built token/emblem catalog: %d token rows, %d emblem rows -> %s",
        token_count, emblem_count, out_file,
    )
    return result


def _subtypes_from_type(type_str: Any) -> list[str]:
    """Extract creature subtype words from a token 'type' string (e.g. 'Token Creature
    — Human Soldier' -> ['Human', 'Soldier'])."""
    text = str(type_str or "")
    if "\u2014" not in text:
        return []
    return text.split("\u2014")[-1].strip().split()


def _token_type_label(type_str: Any) -> str:
    """Extract a non-creature token's type label from its 'type' string (e.g. 'Token
    Artifact — Treasure' -> 'Treasure')."""
    text = str(type_str or "")
    if "\u2014" in text:
        return text.split("\u2014")[-1].strip()
    return text.replace("Token", "").strip()


def tag_token_catalog_own_fields(tokens_df: pd.DataFrame) -> pd.DataFrame:
    """Populate `metadataTags`/`themeTags` on the token catalog itself, using each row's
    own clean fields (no regex needed) via `format_token_detail_tag()` (Roadmap 39,
    Milestone 2). Dual-faced rows are tagged per-face independently.

    Emblems are skipped here (no `Token Detail:` tag applies to them); their tagging
    (`Emblem: {creator}` on the creator card) happens in `apply_emblem_backreferences()`
    against `all_cards.parquet` instead.
    """
    from tagging.tag_utils import format_token_detail_tag

    result = tokens_df.copy()
    metadata_col: list[list[str]] = []
    theme_col: list[list[str]] = []

    for _, row in result.iterrows():
        if row.get("isEmblem"):
            metadata_col.append([])
            theme_col.append(["Emblem"])
            continue

        if row.get("face_b_type"):
            faces = [
                (row.get("face_a_type"), row.get("face_a_power"), row.get("face_a_toughness"), row.get("face_a_keywords"), row.get("face_a_text")),
                (row.get("face_b_type"), row.get("face_b_power"), row.get("face_b_toughness"), row.get("face_b_keywords"), row.get("face_b_text")),
            ]
        else:
            faces = [(row.get("type"), row.get("power"), row.get("toughness"), row.get("keywords"), row.get("text"))]

        metadata_tags: list[str] = []
        theme_tags: set[str] = set()
        for type_str, power, toughness, keywords, text in faces:
            if not type_str:
                continue
            is_creature = "creature" in str(type_str).lower()
            creature_type = _subtypes_from_type(type_str) if is_creature else None
            token_type_label = None if is_creature else _token_type_label(type_str)

            tag = format_token_detail_tag(
                is_creature=is_creature, power=power, toughness=toughness,
                colors=row.get("colors"), creature_type=creature_type,
                token_type=token_type_label, keywords=keywords, text=text,
            )
            if tag not in metadata_tags:
                metadata_tags.append(tag)

            if is_creature:
                theme_tags.add("Creature Token")
                for subtype in creature_type or []:
                    theme_tags.add(f"{subtype} Token")
            else:
                theme_tags.add(f"{token_type_label} Token")

        metadata_col.append(metadata_tags)
        theme_col.append(sorted(theme_tags))

    result["metadataTags"] = metadata_col
    result["themeTags"] = theme_col
    return result


def apply_emblem_backreferences(all_cards_df: pd.DataFrame, tokens_df: pd.DataFrame) -> pd.DataFrame:
    """Write an `Emblem: {creator card name}` metadataTag and a generic `Emblem`
    themeTag onto each emblem's creator row(s) in `all_cards.parquet` (Roadmap 39,
    Milestone 2). Runs after `run_tagging()`, per the pipeline's revised ordering.

    Cards not found in `all_cards_df` (e.g. a name mismatch) are skipped silently --
    this is purely additive metadata, never fatal to the pipeline.
    """
    result = all_cards_df.copy()
    if "name" not in result.columns:
        return result
    if "metadataTags" not in result.columns:
        result["metadataTags"] = pd.Series([[] for _ in range(len(result))], index=result.index)
    if "themeTags" not in result.columns:
        result["themeTags"] = pd.Series([[] for _ in range(len(result))], index=result.index)

    emblems = tokens_df[tokens_df["isEmblem"] == True]  # noqa: E712
    if emblems.empty:
        return result

    name_to_indices: dict[str, list[int]] = {}
    for idx, name in result["name"].items():
        key = str(name or "").strip().casefold()
        if key:
            name_to_indices.setdefault(key, []).append(idx)

    for _, emblem in emblems.iterrows():
        emblem_name = emblem.get("name")
        related = emblem.get("relatedCards")
        related_list = list(related) if related is not None and hasattr(related, "__iter__") and not isinstance(related, str) else []
        for creator in related_list:
            key = str(creator or "").strip().casefold()
            for idx in name_to_indices.get(key, []):
                detail_tag = f"Emblem: {emblem_name}"
                metadata_tags = list(result.at[idx, "metadataTags"])
                if detail_tag not in metadata_tags:
                    metadata_tags.append(detail_tag)
                result.at[idx, "metadataTags"] = metadata_tags

                theme_tags = list(result.at[idx, "themeTags"])
                if "Emblem" not in theme_tags:
                    theme_tags.append("Emblem")
                result.at[idx, "themeTags"] = theme_tags

    return result
