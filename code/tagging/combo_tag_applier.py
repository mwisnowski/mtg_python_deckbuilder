from __future__ import annotations

# Standard library imports
import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Set

# Third-party imports
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ComboPair:
    a: str
    b: str
    cheap_early: bool = False
    setup_dependent: bool = False
    tags: List[str] | None = None


def _load_pairs(path: Path) -> List[ComboPair]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = []
    for entry in data.get("pairs", []):
        pairs.append(
            ComboPair(
                a=entry["a"].strip(),
                b=entry["b"].strip(),
                cheap_early=bool(entry.get("cheap_early", False)),
                setup_dependent=bool(entry.get("setup_dependent", False)),
                tags=list(entry.get("tags", [])),
            )
        )
    return pairs


def _canonicalize(name: str) -> str:
    # Canonicalize for matching: trim, unify punctuation/quotes, collapse spaces, casefold later
    if name is None:
        return ""
    s = str(name).strip()
    # Normalize common unicode punctuation variants
    s = s.replace("\u2019", "'")  # curly apostrophe to straight
    s = s.replace("\u2018", "'")
    s = s.replace("\u201C", '"').replace("\u201D", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")  # en/em dash -> hyphen
    # Collapse multiple spaces
    s = " ".join(s.split())
    return s


def _ensure_combo_cols(df: pd.DataFrame) -> None:
    if "comboTags" not in df.columns:
        df["comboTags"] = [[] for _ in range(len(df))]


def _apply_partner_to_names(df: pd.DataFrame, target_names: Set[str], partner: str) -> None:
    if not target_names:
        return
    mask = df["name"].isin(target_names)
    if not mask.any():
        return
    current = df.loc[mask, "comboTags"]
    df.loc[mask, "comboTags"] = current.apply(
        lambda tags: sorted(list({*tags, partner})) if isinstance(tags, list) else [partner]
    )


def _safe_list_parse(s: object) -> List[str]:
    if isinstance(s, list):
        return s
    if not isinstance(s, str) or not s.strip():
        return []
    txt = s.strip()
    # Try JSON first
    try:
        v = json.loads(txt)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    # Fallback to Python literal
    try:
        v = ast.literal_eval(txt)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    return []


def apply_combo_tags(
    df: pd.DataFrame | None = None,
    combos_path: str | Path = "config/card_lists/combos.json"
) -> Dict[str, int]:
    """Apply bidirectional comboTags to DataFrame based on combos.json.
    
    This function modifies the DataFrame in-place when called from the tagging pipeline.
    It can also be called standalone without a DataFrame for legacy/CLI usage.

    Args:
        df: DataFrame to modify in-place (from tagging pipeline), or None for standalone usage
        combos_path: Path to combos.json file

    Returns:
        Dict with 'total' key showing count of cards with combo tags
    """
    combos_file = Path(combos_path)
    pairs = _load_pairs(combos_file)
    
    # If no DataFrame provided, load from Parquet (standalone mode)
    standalone_mode = df is None
    if standalone_mode:
        parquet_path = "card_files/processed/all_cards.parquet"
        parquet_file = Path(parquet_path)
        if not parquet_file.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_file}")
        df = pd.read_parquet(parquet_file)
    
    _ensure_combo_cols(df)
    before_hash = pd.util.hash_pandas_object(df[["name", "comboTags"]].astype(str)).sum()
    
    # Build an index of canonicalized keys -> actual DF row names to update
    name_index: DefaultDict[str, Set[str]] = defaultdict(set)
    for nm in df["name"].astype(str).tolist():
        canon = _canonicalize(nm)
        cf = canon.casefold()
        name_index[cf].add(nm)
        # If split/fused faces exist, map each face to the combined row name as well
        if " // " in canon:
            for part in canon.split(" // "):
                p = part.strip().casefold()
                if p:
                    name_index[p].add(nm)
    
    # Apply all combo pairs
    for p in pairs:
        a = _canonicalize(p.a)
        b = _canonicalize(p.b)
        a_key = a.casefold()
        b_key = b.casefold()
        # Apply A<->B bidirectionally to any matching DF rows
        _apply_partner_to_names(df, name_index.get(a_key, set()), b)
        _apply_partner_to_names(df, name_index.get(b_key, set()), a)
    
    after_hash = pd.util.hash_pandas_object(df[["name", "comboTags"]].astype(str)).sum()
    
    # Calculate updated counts
    updated_counts: Dict[str, int] = {}
    if before_hash != after_hash:
        # Use len() > 0 to handle arrays properly (avoid ambiguous truth value)
        updated_counts["total"] = int((df["comboTags"].apply(lambda x: len(x) > 0 if isinstance(x, (list, np.ndarray)) else bool(x))).sum())
    else:
        updated_counts["total"] = 0
    
    # Only write back to Parquet in standalone mode
    if standalone_mode and before_hash != after_hash:
        df.to_parquet(parquet_file, index=False)
    
    return updated_counts


if __name__ == "__main__":
    counts = apply_combo_tags()
    print("Updated comboTags counts:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
