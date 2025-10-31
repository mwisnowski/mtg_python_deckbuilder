from __future__ import annotations

# Standard library imports
import json
from pathlib import Path
from typing import Dict, Iterable, Set

# Third-party imports
import pandas as pd

def _ensure_norm_series(df: pd.DataFrame, source_col: str, norm_col: str) -> pd.Series:
    """Minimal normalized string cache (subset of tag_utils)."""
    if norm_col in df.columns:
        return df[norm_col]
    series = df[source_col].fillna('') if source_col in df.columns else pd.Series([''] * len(df), index=df.index)
    series = series.astype(str)
    df[norm_col] = series
    return df[norm_col]


def _apply_tag_vectorized(df: pd.DataFrame, mask: pd.Series, tags):
    """Minimal tag applier (subset of tag_utils)."""
    if not isinstance(tags, list):
        tags = [tags]
    current = df.loc[mask, 'themeTags']
    df.loc[mask, 'themeTags'] = current.apply(lambda x: sorted(list(set((x if isinstance(x, list) else []) + tags))))


try:
    import logging_util
except Exception:
    # Fallback for direct module loading
    import importlib.util
    root = Path(__file__).resolve().parents[1]
    lu_path = root / 'logging_util.py'
    spec = importlib.util.spec_from_file_location('logging_util', str(lu_path))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    logging_util = mod

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)


POLICY_FILES: Dict[str, str] = {
    'Bracket:GameChanger': 'config/card_lists/game_changers.json',
    'Bracket:ExtraTurn': 'config/card_lists/extra_turns.json',
    'Bracket:MassLandDenial': 'config/card_lists/mass_land_denial.json',
    'Bracket:TutorNonland': 'config/card_lists/tutors_nonland.json',
}


def _canonicalize(name: str) -> str:
    """Normalize names for robust matching.

    - casefold
    - strip spaces
    - normalize common unicode apostrophes
    - drop Alchemy/Arena prefix "A-"
    """
    if name is None:
        return ''
    s = str(name).strip().replace('\u2019', "'")
    if s.startswith('A-') and len(s) > 2:
        s = s[2:]
    return s.casefold()


def _load_names_from_list(file_path: str | Path) -> Set[str]:
    p = Path(file_path)
    if not p.exists():
        logger.warning('Bracket policy list missing: %s', p)
        return set()
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        names: Iterable[str] = data.get('cards', []) or []
        return { _canonicalize(n) for n in names }
    except Exception as e:
        logger.error('Failed to read policy list %s: %s', p, e)
        return set()


def _build_name_series(df: pd.DataFrame) -> pd.Series:
    # Combine name and faceName if available, prefer exact name but fall back to faceName text
    name_series = _ensure_norm_series(df, 'name', '__name_s')
    if 'faceName' in df.columns:
        face_series = _ensure_norm_series(df, 'faceName', '__facename_s')
        # Use name when present, else facename
        combined = name_series.copy()
        combined = combined.where(name_series.astype(bool), face_series)
        return combined
    return name_series


def apply_bracket_policy_tags(df: pd.DataFrame) -> None:
    """Apply Bracket:* tags to rows whose name is present in policy lists.

    Mutates df['themeTags'] in place.
    """
    if len(df) == 0:
        return

    name_series = _build_name_series(df)
    canon_series = name_series.apply(_canonicalize)

    total_tagged = 0
    for tag, file in POLICY_FILES.items():
        names = _load_names_from_list(file)
        if not names:
            continue
        mask = canon_series.isin(names)
        if mask.any():
            _apply_tag_vectorized(df, mask, [tag])
            count = int(mask.sum())
            total_tagged += count
            logger.info('Applied %s to %d cards', tag, count)

    if total_tagged == 0:
        logger.info('No Bracket:* tags applied (no matches or lists empty).')
