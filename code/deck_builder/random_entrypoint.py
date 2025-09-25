from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import time
import pandas as pd

from deck_builder import builder_constants as bc
from random_util import get_random, generate_seed


class RandomBuildError(Exception):
    pass


class RandomConstraintsImpossibleError(RandomBuildError):
    def __init__(self, message: str, *, constraints: Optional[Dict[str, Any]] = None, pool_size: Optional[int] = None):
        super().__init__(message)
        self.constraints = constraints or {}
        self.pool_size = int(pool_size or 0)


@dataclass
class RandomBuildResult:
    seed: int
    commander: str
    theme: Optional[str]
    constraints: Optional[Dict[str, Any]]
    # Extended multi-theme support
    primary_theme: Optional[str] = None
    secondary_theme: Optional[str] = None
    tertiary_theme: Optional[str] = None
    resolved_themes: List[str] | None = None  # actual AND-combination used for filtering (case-preserved)
    # Diagnostics / fallback metadata
    theme_fallback: bool = False  # original single-theme fallback (legacy)
    original_theme: Optional[str] = None
    combo_fallback: bool = False  # when we had to drop one or more secondary/tertiary themes
    synergy_fallback: bool = False  # when primary itself had no matches and we broadened based on loose overlap
    fallback_reason: Optional[str] = None
    attempts_tried: int = 0
    timeout_hit: bool = False
    retries_exhausted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": int(self.seed),
            "commander": self.commander,
            "theme": self.theme,
            "constraints": self.constraints or {},
        }


def _load_commanders_df() -> pd.DataFrame:
    """Load commander CSV using the same path/converters as the builder.

    Uses bc.COMMANDER_CSV_PATH and bc.COMMANDER_CONVERTERS for consistency.
    """
    return pd.read_csv(bc.COMMANDER_CSV_PATH, converters=getattr(bc, "COMMANDER_CONVERTERS", None))


def _normalize_tag(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def _filter_multi(df: pd.DataFrame, primary: Optional[str], secondary: Optional[str], tertiary: Optional[str]) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Return filtered commander dataframe based on ordered fallback strategy.

    Strategy (P = primary, S = secondary, T = tertiary):
      1. If all P,S,T provided → try P&S&T
      2. If no triple match → try P&S
      3. If no P&S → try P&T (treat tertiary as secondary weight-wise)
      4. If no P+{S|T} → try P alone
      5. If P alone empty → attempt loose synergy fallback (any commander whose themeTags share a word with P)
      6. Else full pool fallback (ultimate guard)

    Returns (filtered_df, diagnostics_dict)
    diagnostics_dict keys:
      - resolved_themes: list[str]
      - combo_fallback: bool
      - synergy_fallback: bool
      - fallback_reason: str | None
    """
    diag: Dict[str, Any] = {
        "resolved_themes": None,
        "combo_fallback": False,
        "synergy_fallback": False,
        "fallback_reason": None,
    }
    # Normalize to lowercase for comparison but preserve original for reporting
    p = _normalize_tag(primary)
    s = _normalize_tag(secondary)
    t = _normalize_tag(tertiary)
    # Helper to test AND-combo
    def and_filter(req: List[str]) -> pd.DataFrame:
        if not req:
            return df
        req_l = [r.lower() for r in req]
        try:
            mask = df.get("themeTags").apply(lambda tags: all(any(str(x).strip().lower() == r for x in (tags or [])) for r in req_l))
            return df[mask]
        except Exception:
            return df.iloc[0:0]

    # 1. Triple
    if p and s and t:
        triple = and_filter([p, s, t])
        if len(triple) > 0:
            diag["resolved_themes"] = [p, s, t]
            return triple, diag
    # 2. P+S
    if p and s:
        ps = and_filter([p, s])
        if len(ps) > 0:
            if t:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No commanders matched all three themes; using Primary+Secondary"
            diag["resolved_themes"] = [p, s]
            return ps, diag
    # 3. P+T
    if p and t:
        pt = and_filter([p, t])
        if len(pt) > 0:
            if s:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No commanders matched requested combinations; using Primary+Tertiary"
            diag["resolved_themes"] = [p, t]
            return pt, diag
    # 4. P only
    if p:
        p_only = and_filter([p])
        if len(p_only) > 0:
            if s or t:
                diag["combo_fallback"] = True
                diag["fallback_reason"] = "No multi-theme combination matched; using Primary only"
            diag["resolved_themes"] = [p]
            return p_only, diag
    # 5. Synergy fallback based on primary token overlaps
    if p:
        words = [w for w in p.replace('-', ' ').split() if w]
        if words:
            try:
                mask = df.get("themeTags").apply(
                    lambda tags: any(
                        any(w == str(x).strip().lower() or w in str(x).strip().lower() for w in words)
                        for x in (tags or [])
                    )
                )
                synergy_df = df[mask]
                if len(synergy_df) > 0:
                    diag["resolved_themes"] = words  # approximate overlap tokens
                    diag["combo_fallback"] = True
                    diag["synergy_fallback"] = True
                    diag["fallback_reason"] = "Primary theme had no direct matches; using synergy overlap"
                    return synergy_df, diag
            except Exception:
                pass
    # 6. Full pool fallback
    diag["resolved_themes"] = []
    diag["combo_fallback"] = True
    diag["synergy_fallback"] = True
    diag["fallback_reason"] = "No theme matches found; using full commander pool"
    return df, diag


def _candidate_ok(candidate: str, constraints: Optional[Dict[str, Any]]) -> bool:
    """Check simple feasibility filters from constraints.

    Supported keys (lightweight, safe defaults):
      - reject_all: bool -> if True, reject every candidate (useful for retries-exhausted tests)
      - reject_names: list[str] -> reject these specific names
    """
    if not constraints:
        return True
    try:
        if constraints.get("reject_all"):
            return False
    except Exception:
        pass
    try:
        rej = constraints.get("reject_names")
        if isinstance(rej, (list, tuple)) and any(str(candidate) == str(x) for x in rej):
            return False
    except Exception:
        pass
    return True


def _check_constraints(candidate_count: int, constraints: Optional[Dict[str, Any]]) -> None:
    if not constraints:
        return
    try:
        req_min = constraints.get("require_min_candidates")  # type: ignore[attr-defined]
    except Exception:
        req_min = None
    if req_min is None:
        return
    try:
        req_min_int = int(req_min)
    except Exception:
        req_min_int = None
    if req_min_int is not None and candidate_count < req_min_int:
        raise RandomConstraintsImpossibleError(
            f"Not enough candidates to satisfy constraints (have {candidate_count}, require >= {req_min_int})",
            constraints=constraints,
            pool_size=candidate_count,
        )


def build_random_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
    # New multi-theme inputs (theme retained for backward compatibility as primary)
    primary_theme: Optional[str] = None,
    secondary_theme: Optional[str] = None,
    tertiary_theme: Optional[str] = None,
) -> RandomBuildResult:
    """Thin wrapper for random selection of a commander, deterministic when seeded.

    Contract (initial/minimal):
    - Inputs: optional theme filter, optional constraints dict, seed for determinism,
      attempts (max reroll attempts), timeout_s (wall clock cap).
    - Output: RandomBuildResult with chosen commander and the resolved seed.

    Notes:
    - This does NOT run the full deck builder yet; it focuses on picking a commander
      deterministically for tests and plumbing. Full pipeline can be layered later.
    - Determinism: when `seed` is provided, selection is stable across runs.
    - When `seed` is None, a new high-entropy seed is generated and returned.
    """
    # Resolve seed and RNG
    resolved_seed = int(seed) if isinstance(seed, int) or (isinstance(seed, str) and str(seed).isdigit()) else None
    if resolved_seed is None:
        resolved_seed = generate_seed()
    rng = get_random(resolved_seed)

    # Bounds sanitation
    attempts = max(1, int(attempts or 1))
    try:
        timeout_s = float(timeout_s)
    except Exception:
        timeout_s = 5.0
    timeout_s = max(0.1, timeout_s)

    # Resolve multi-theme inputs
    if primary_theme is None:
        primary_theme = theme  # legacy single theme becomes primary
    df_all = _load_commanders_df()
    df, multi_diag = _filter_multi(df_all, primary_theme, secondary_theme, tertiary_theme)
    used_fallback = False
    original_theme = None
    if multi_diag.get("combo_fallback") or multi_diag.get("synergy_fallback"):
        # For legacy fields
        used_fallback = bool(multi_diag.get("combo_fallback"))
        original_theme = primary_theme if primary_theme else None
    # Stable ordering then seeded selection for deterministic behavior
    names: List[str] = sorted(df["name"].astype(str).tolist()) if not df.empty else []
    if not names:
        # Fall back to entire pool by name if theme produced nothing
        names = sorted(df_all["name"].astype(str).tolist())
    if not names:
        # Absolute fallback for pathological cases
        names = ["Unknown Commander"]

    # Constraint feasibility check (based on candidate count)
    _check_constraints(len(names), constraints)

    # Simple attempt/timeout loop (placeholder for future constraints checks)
    start = time.time()
    pick = None
    attempts_tried = 0
    timeout_hit = False
    for i in range(attempts):
        if (time.time() - start) > timeout_s:
            timeout_hit = True
            break
        attempts_tried = i + 1
        idx = rng.randrange(0, len(names))
        candidate = names[idx]
        # Accept only if candidate passes simple feasibility filters
        if _candidate_ok(candidate, constraints):
            pick = candidate
            break
        # else continue and try another candidate until attempts/timeout
    retries_exhausted = (pick is None) and (not timeout_hit) and (attempts_tried >= attempts)
    if pick is None:
        # Timeout/attempts exhausted; choose deterministically based on seed modulo
        pick = names[resolved_seed % len(names)]

    return RandomBuildResult(
        seed=int(resolved_seed),
        commander=pick,
        theme=primary_theme,  # preserve prior contract
        constraints=constraints or {},
        primary_theme=primary_theme,
        secondary_theme=secondary_theme,
        tertiary_theme=tertiary_theme,
        resolved_themes=list(multi_diag.get("resolved_themes") or []),
        combo_fallback=bool(multi_diag.get("combo_fallback")),
        synergy_fallback=bool(multi_diag.get("synergy_fallback")),
        fallback_reason=multi_diag.get("fallback_reason"),
        theme_fallback=bool(used_fallback),
        original_theme=original_theme,
        attempts_tried=int(attempts_tried or (1 if pick else 0)),
        timeout_hit=bool(timeout_hit),
        retries_exhausted=bool(retries_exhausted),
    )


__all__ = [
    "RandomBuildResult",
    "build_random_deck",
]


# Full-build wrapper for deterministic end-to-end builds
@dataclass
class RandomFullBuildResult(RandomBuildResult):
    decklist: List[Dict[str, Any]] | None = None
    diagnostics: Dict[str, Any] | None = None
    summary: Dict[str, Any] | None = None
    csv_path: str | None = None
    txt_path: str | None = None
    compliance: Dict[str, Any] | None = None


def build_random_full_deck(
    theme: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
    seed: Optional[int | str] = None,
    attempts: int = 5,
    timeout_s: float = 5.0,
) -> RandomFullBuildResult:
    """Select a commander deterministically, then run a full deck build via DeckBuilder.

    Returns a compact result including the seed, commander, and a summarized decklist.
    """
    t0 = time.time()
    base = build_random_deck(theme=theme, constraints=constraints, seed=seed, attempts=attempts, timeout_s=timeout_s)

    # Run the full headless build with the chosen commander and the same seed
    try:
        from headless_runner import run as _run  # type: ignore
    except Exception as e:
        return RandomFullBuildResult(
            seed=base.seed,
            commander=base.commander,
            theme=base.theme,
            constraints=base.constraints or {},
            decklist=None,
            diagnostics={"error": f"headless runner unavailable: {e}"},
        )

    # Run the full builder once; reuse object for summary + deck extraction
    # Default behavior: suppress the initial internal export so Random build controls artifacts.
    # (If user explicitly sets RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=0 we respect that.)
    try:
        import os as _os
        if _os.getenv('RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT') is None:
            _os.environ['RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT'] = '1'
    except Exception:
        pass
    builder = _run(command_name=base.commander, seed=base.seed)

    # Build summary (may fail gracefully)
    summary: Dict[str, Any] | None = None
    try:
        if hasattr(builder, 'build_deck_summary'):
            summary = builder.build_deck_summary()  # type: ignore[attr-defined]
    except Exception:
        summary = None

    # Attempt to reuse existing export performed inside builder (headless run already exported)
    csv_path: str | None = None
    txt_path: str | None = None
    compliance: Dict[str, Any] | None = None
    try:
        import os as _os
        import json as _json
        csv_path = getattr(builder, 'last_csv_path', None)  # type: ignore[attr-defined]
        txt_path = getattr(builder, 'last_txt_path', None)  # type: ignore[attr-defined]
        if csv_path and isinstance(csv_path, str):
            base_path, _ = _os.path.splitext(csv_path)
            # If txt missing but expected, look for sibling
            if (not txt_path or not _os.path.isfile(str(txt_path))) and _os.path.isfile(base_path + '.txt'):
                txt_path = base_path + '.txt'
            # Load existing compliance if present
            comp_path = base_path + '_compliance.json'
            if _os.path.isfile(comp_path):
                try:
                    with open(comp_path, 'r', encoding='utf-8') as _cf:
                        compliance = _json.load(_cf)
                except Exception:
                    compliance = None
            else:
                # Compute compliance if not already saved
                try:
                    if hasattr(builder, 'compute_and_print_compliance'):
                        compliance = builder.compute_and_print_compliance(base_stem=_os.path.basename(base_path))  # type: ignore[attr-defined]
                except Exception:
                    compliance = None
            # Write summary sidecar if missing
            if summary:
                sidecar = base_path + '.summary.json'
                if not _os.path.isfile(sidecar):
                    meta = {
                        "commander": getattr(builder, 'commander_name', '') or getattr(builder, 'commander', ''),
                        "tags": list(getattr(builder, 'selected_tags', []) or []) or [t for t in [getattr(builder, 'primary_tag', None), getattr(builder, 'secondary_tag', None), getattr(builder, 'tertiary_tag', None)] if t],
                        "bracket_level": getattr(builder, 'bracket_level', None),
                        "csv": csv_path,
                        "txt": txt_path,
                        "random_seed": base.seed,
                        "random_theme": base.theme,
                        "random_constraints": base.constraints or {},
                    }
                    try:
                        custom_base = getattr(builder, 'custom_export_base', None)
                    except Exception:
                        custom_base = None
                    if isinstance(custom_base, str) and custom_base.strip():
                        meta["name"] = custom_base.strip()
                    try:
                        with open(sidecar, 'w', encoding='utf-8') as f:
                            _json.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
        else:
            # Fallback: export now (rare path if headless build skipped export)
            if hasattr(builder, 'export_decklist_csv'):
                try:
                    # Before exporting, attempt to find an existing same-day base file (non-suffixed) to avoid duplicate export
                    existing_base: str | None = None
                    try:
                        import glob as _glob
                        today = time.strftime('%Y%m%d')
                        # Commander slug approximation: remove non alnum underscores
                        import re as _re
                        cmdr = (getattr(builder, 'commander_name', '') or getattr(builder, 'commander', '') or '')
                        slug = _re.sub(r'[^A-Za-z0-9_]+', '', cmdr) or 'deck'
                        pattern = f"deck_files/{slug}_*_{today}.csv"
                        for path in sorted(_glob.glob(pattern)):
                            base_name = _os.path.basename(path)
                            if '_1.csv' not in base_name:  # prefer original
                                existing_base = path
                                break
                    except Exception:
                        existing_base = None
                    if existing_base and _os.path.isfile(existing_base):
                        csv_path = existing_base
                        base_path, _ = _os.path.splitext(csv_path)
                    else:
                        tmp_csv = builder.export_decklist_csv()  # type: ignore[attr-defined]
                        stem_base, ext = _os.path.splitext(tmp_csv)
                        if stem_base.endswith('_1'):
                            original = stem_base[:-2] + ext
                            if _os.path.isfile(original):
                                csv_path = original
                            else:
                                csv_path = tmp_csv
                        else:
                            csv_path = tmp_csv
                        base_path, _ = _os.path.splitext(csv_path)
                    if hasattr(builder, 'export_decklist_text'):
                        target_txt = base_path + '.txt'
                        if _os.path.isfile(target_txt):
                            txt_path = target_txt
                        else:
                            tmp_txt = builder.export_decklist_text(filename=_os.path.basename(base_path) + '.txt')  # type: ignore[attr-defined]
                            if tmp_txt.endswith('_1.txt') and _os.path.isfile(target_txt):
                                txt_path = target_txt
                            else:
                                txt_path = tmp_txt
                    if hasattr(builder, 'compute_and_print_compliance'):
                        compliance = builder.compute_and_print_compliance(base_stem=_os.path.basename(base_path))  # type: ignore[attr-defined]
                    if summary:
                        sidecar = base_path + '.summary.json'
                        if not _os.path.isfile(sidecar):
                            meta = {
                                "commander": getattr(builder, 'commander_name', '') or getattr(builder, 'commander', ''),
                                "tags": list(getattr(builder, 'selected_tags', []) or []) or [t for t in [getattr(builder, 'primary_tag', None), getattr(builder, 'secondary_tag', None), getattr(builder, 'tertiary_tag', None)] if t],
                                "bracket_level": getattr(builder, 'bracket_level', None),
                                "csv": csv_path,
                                "txt": txt_path,
                                "random_seed": base.seed,
                                "random_theme": base.theme,
                                "random_constraints": base.constraints or {},
                            }
                            with open(sidecar, 'w', encoding='utf-8') as f:
                                _json.dump({"meta": meta, "summary": summary}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
    except Exception:
        pass

    # Extract a simple decklist (name/count)
    deck_items: List[Dict[str, Any]] = []
    try:
        lib = getattr(builder, 'card_library', {}) or {}
        for name, info in lib.items():
            try:
                cnt = int(info.get('Count', 1)) if isinstance(info, dict) else 1
            except Exception:
                cnt = 1
            deck_items.append({"name": str(name), "count": cnt})
        deck_items.sort(key=lambda x: (str(x.get("name", "").lower()), int(x.get("count", 0))))
    except Exception:
        deck_items = []

    elapsed_ms = int((time.time() - t0) * 1000)
    diags: Dict[str, Any] = {
        "attempts": int(getattr(base, "attempts_tried", 1) or 1),
        "timeout_s": float(timeout_s),
        "elapsed_ms": elapsed_ms,
        "fallback": bool(base.theme_fallback),
        "timeout_hit": bool(getattr(base, "timeout_hit", False)),
        "retries_exhausted": bool(getattr(base, "retries_exhausted", False)),
    }
    return RandomFullBuildResult(
        seed=base.seed,
        commander=base.commander,
        theme=base.theme,
        constraints=base.constraints or {},
        decklist=deck_items,
        diagnostics=diags,
        summary=summary,
        csv_path=csv_path,
        txt_path=txt_path,
        compliance=compliance,
    )

