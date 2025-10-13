from __future__ import annotations

# Standard library imports
import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Set

# Third-party imports
import pandas as pd

# Local application imports
from settings import CSV_DIRECTORY, SETUP_COLORS


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


def apply_combo_tags(colors: List[str] | None = None, combos_path: str | Path = "config/card_lists/combos.json", csv_dir: str | Path | None = None) -> Dict[str, int]:
    """Apply bidirectional comboTags to per-color CSVs based on combos.json.

    Returns a dict of color->updated_row_count for quick reporting.
    """
    colors = colors or list(SETUP_COLORS)
    combos_file = Path(combos_path)
    pairs = _load_pairs(combos_file)

    updated_counts: Dict[str, int] = {}
    base_dir = Path(csv_dir) if csv_dir is not None else Path(CSV_DIRECTORY)
    for color in colors:
        csv_path = base_dir / f"{color}_cards.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, converters={
            "themeTags": _safe_list_parse,
            "creatureTypes": _safe_list_parse,
            "comboTags": _safe_list_parse,
        })

        _ensure_combo_cols(df)
        before_hash = pd.util.hash_pandas_object(df[["name", "comboTags"]].astype(str)).sum()

        # Build an index of canonicalized keys -> actual DF row names to update.
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

        for p in pairs:
            a = _canonicalize(p.a)
            b = _canonicalize(p.b)
            a_key = a.casefold()
            b_key = b.casefold()
            # Apply A<->B bidirectionally to any matching DF rows
            _apply_partner_to_names(df, name_index.get(a_key, set()), b)
            _apply_partner_to_names(df, name_index.get(b_key, set()), a)

        after_hash = pd.util.hash_pandas_object(df[["name", "comboTags"]].astype(str)).sum()
        if before_hash != after_hash:
            df.to_csv(csv_path, index=False)
            updated_counts[color] = int((df["comboTags"].apply(bool)).sum())

    return updated_counts


if __name__ == "__main__":
    counts = apply_combo_tags()
    print("Updated comboTags counts:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
