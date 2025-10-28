"""Utilities for merging multi-faced card entries after tagging.

This module groups card DataFrame rows that represent multiple faces of the same
card (transform, split, adventure, modal DFC, etc.) and collapses them into a
single canonical record with merged tags.
"""

from __future__ import annotations

import ast
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence, Set

import pandas as pd

# Layouts that indicate a card has multiple faces represented as separate rows.
_MULTI_FACE_LAYOUTS: Set[str] = {
    "adventure",
    "aftermath",
    "augment",
    "flip",
    "host",
    "meld",
    "modal_dfc",
    "reversible_card",
    "split",
    "transform",
}

_SIDE_PRIORITY = {
    "": 0,
    "a": 0,
    "front": 0,
    "main": 0,
    "b": 1,
    "back": 1,
    "c": 2,
}

_LIST_UNION_COLUMNS: Sequence[str] = ("themeTags", "creatureTypes", "roleTags")

_SUMMARY_PATH = Path("logs/dfc_merge_summary.json")


def _text_produces_mana(text: Any) -> bool:
    text_str = str(text or "").lower()
    if not text_str:
        return False
    if "add one mana of any color" in text_str or "add one mana of any colour" in text_str:
        return True
    if "add mana of any color" in text_str or "add mana of any colour" in text_str:
        return True
    if "mana of any one color" in text_str or "any color of mana" in text_str:
        return True
    if "add" in text_str:
        for sym in ("{w}", "{u}", "{b}", "{r}", "{g}", "{c}"):
            if sym in text_str:
                return True
    return False


def load_merge_summary() -> Dict[str, Any]:
    try:
        with _SUMMARY_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"updated_at": None, "colors": {}}


def _merge_tag_columns(work_df: pd.DataFrame, group_sorted: pd.DataFrame, primary_idx: int) -> None:
    """Merge list columns (themeTags, roleTags) into union values.
    
    Args:
        work_df: Working DataFrame to update
        group_sorted: Sorted group of faces for a multi-face card
        primary_idx: Index of primary face to update
    """
    for column in _LIST_UNION_COLUMNS:
        if column in group_sorted.columns:
            union_values = _merge_object_lists(group_sorted[column])
            work_df.at[primary_idx, column] = union_values
    
    if "keywords" in group_sorted.columns:
        keyword_union = _merge_keywords(group_sorted["keywords"])
        work_df.at[primary_idx, "keywords"] = _join_keywords(keyword_union)


def _build_face_payload(face_row: pd.Series) -> Dict[str, Any]:
    """Build face metadata payload from a single face row.
    
    Args:
        face_row: Single face row from grouped DataFrame
        
    Returns:
        Dictionary containing face metadata
    """
    text_val = face_row.get("text") or face_row.get("oracleText") or ""
    mana_cost_val = face_row.get("manaCost", face_row.get("mana_cost", "")) or ""
    mana_value_raw = face_row.get("manaValue", face_row.get("mana_value", ""))
    
    try:
        if mana_value_raw in (None, ""):
            mana_value_val = None
        else:
            mana_value_val = float(mana_value_raw)
            if math.isnan(mana_value_val):
                mana_value_val = None
    except Exception:
        mana_value_val = None
    
    type_val = face_row.get("type", "") or ""
    
    return {
        "face": str(face_row.get("faceName") or face_row.get("name") or ""),
        "side": str(face_row.get("side") or ""),
        "layout": str(face_row.get("layout") or ""),
        "themeTags": _merge_object_lists([face_row.get("themeTags", [])]),
        "roleTags": _merge_object_lists([face_row.get("roleTags", [])]),
        "type": str(type_val),
        "text": str(text_val),
        "mana_cost": str(mana_cost_val),
        "mana_value": mana_value_val,
        "produces_mana": _text_produces_mana(text_val),
        "is_land": 'land' in str(type_val).lower(),
    }


def _build_merge_detail(name: str, group_sorted: pd.DataFrame, faces_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build detailed merge information for a multi-face card group.
    
    Args:
        name: Card name
        group_sorted: Sorted group of faces
        faces_payload: List of face metadata dictionaries
        
    Returns:
        Dictionary containing merge details
    """
    layout_set = sorted({f.get("layout", "") for f in faces_payload if f.get("layout")})
    removed_faces = faces_payload[1:] if len(faces_payload) > 1 else []
    
    return {
        "name": name,
        "total_faces": len(group_sorted),
        "dropped_faces": max(len(group_sorted) - 1, 0),
        "layouts": layout_set,
        "primary_face": faces_payload[0] if faces_payload else {},
        "removed_faces": removed_faces,
        "theme_tags": sorted({tag for face in faces_payload for tag in face.get("themeTags", [])}),
        "role_tags": sorted({tag for face in faces_payload for tag in face.get("roleTags", [])}),
        "faces": faces_payload,
    }


def _log_merge_summary(color: str, merged_count: int, drop_count: int, multi_face_count: int, logger) -> None:
    """Log merge summary with structured and human-readable formats.
    
    Args:
        color: Color being processed
        merged_count: Number of card groups merged
        drop_count: Number of face rows dropped
        multi_face_count: Total multi-face rows processed
        logger: Logger instance
    """
    try:
        logger.info(
            "dfc_merge_summary %s",
            json.dumps(
                {
                    "event": "dfc_merge_summary",
                    "color": color,
                    "groups_merged": merged_count,
                    "faces_dropped": drop_count,
                    "multi_face_rows": multi_face_count,
                },
                sort_keys=True,
            ),
        )
    except Exception:
        logger.info(
            "dfc_merge_summary event=%s groups=%d dropped=%d rows=%d",
            color,
            merged_count,
            drop_count,
            multi_face_count,
        )
    
    logger.info(
        "Merged %d multi-face card groups for %s (dropped %d extra faces)",
        merged_count,
        color,
        drop_count,
    )


def merge_multi_face_rows(
    df: pd.DataFrame,
    color: str,
    logger=None,
    recorder: Callable[[Dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Merge multi-face card rows into canonical entries with combined tags.

    Args:
        df: DataFrame containing tagged card data for a specific color.
        color: Color name, used for logging context.
        logger: Optional logger instance. When provided, debug information is emitted.

    Returns:
        DataFrame with multi-face entries collapsed and combined tag data.
    """
    if df.empty or "layout" not in df.columns or "name" not in df.columns:
        return df

    work_df = df.copy()
    layout_series = work_df["layout"].fillna("").astype(str).str.lower()
    multi_mask = layout_series.isin(_MULTI_FACE_LAYOUTS)

    if not multi_mask.any():
        return work_df

    drop_indices: List[int] = []
    merged_count = 0
    merge_details: List[Dict[str, Any]] = []

    for name, group in work_df.loc[multi_mask].groupby("name", sort=False):
        if len(group) <= 1:
            continue

        group_sorted = _sort_faces(group)
        primary_idx = group_sorted.index[0]

        _merge_tag_columns(work_df, group_sorted, primary_idx)

        faces_payload = [_build_face_payload(row) for _, row in group_sorted.iterrows()]

        # M9: Capture back face type for MDFC land detection
        if len(group_sorted) >= 2 and "type" in group_sorted.columns:
            back_face_row = group_sorted.iloc[1]
            back_type = str(back_face_row.get("type", "") or "")
            if back_type:
                work_df.at[primary_idx, "backType"] = back_type

        drop_indices.extend(group_sorted.index[1:])
        
        merged_count += 1
        merge_details.append(_build_merge_detail(name, group_sorted, faces_payload))

    if drop_indices:
        work_df = work_df.drop(index=drop_indices)

    summary_payload = {
        "color": color,
        "group_count": merged_count,
        "faces_dropped": len(drop_indices),
        "multi_face_rows": int(multi_mask.sum()),
        "entries": merge_details,
    }

    if recorder is not None:
        try:
            maybe_payload = recorder(summary_payload)
            if isinstance(maybe_payload, dict):
                summary_payload = maybe_payload
        except Exception as exc:
            if logger is not None:
                logger.warning("Failed to record DFC merge summary for %s: %s", color, exc)

    if logger is not None:
        _log_merge_summary(color, merged_count, len(drop_indices), int(multi_mask.sum()), logger)

    _persist_merge_summary(color, summary_payload, logger)

    return work_df.reset_index(drop=True)


def _persist_merge_summary(color: str, summary_payload: Dict[str, Any], logger=None) -> None:
    try:
        _SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = load_merge_summary()
        colors = existing.get("colors")
        if not isinstance(colors, dict):
            colors = {}
        summary_payload = dict(summary_payload)
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        summary_payload["timestamp"] = timestamp
        colors[color] = summary_payload
        existing["colors"] = colors
        existing["updated_at"] = timestamp
        with _SUMMARY_PATH.open("w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=2, sort_keys=True)
    except Exception as exc:
        if logger is not None:
            logger.warning("Failed to persist DFC merge summary: %s", exc)


def _sort_faces(group: pd.DataFrame) -> pd.DataFrame:
    side_series = group.get("side", pd.Series(["" for _ in range(len(group))], index=group.index))
    priority = side_series.fillna("").astype(str).str.lower().map(_SIDE_PRIORITY).fillna(3)
    return group.assign(__face_order=priority).sort_values(
        by=["__face_order", "faceName"], kind="mergesort"
    ).drop(columns=["__face_order"], errors="ignore")


def _merge_object_lists(values: Iterable[Any]) -> List[str]:
    merged: Set[str] = set()
    for value in values:
        merged.update(_coerce_list(value))
    return sorted(merged)


def _merge_keywords(values: Iterable[Any]) -> Set[str]:
    merged: Set[str] = set()
    for value in values:
        merged.update(_split_keywords(value))
    return merged


def _join_keywords(keywords: Set[str]) -> str:
    if not keywords:
        return ""
    return ", ".join(sorted(keywords))


def _coerce_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, list):
            return [str(v) for v in parsed if str(v)]
        return [part for part in (s.strip() for s in stripped.split(',')) if part]
    return [str(value)]


def _split_keywords(value: Any) -> Set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    if isinstance(value, list):
        return {str(v).strip() for v in value if str(v).strip()}
    if isinstance(value, str):
        return {part.strip() for part in value.split(',') if part.strip()}
        return {str(value).strip()}