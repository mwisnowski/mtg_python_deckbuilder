from __future__ import annotations

from typing import Dict, Optional, List
import logging_util
from .. import builder_utils as bu
from .. import builder_constants as bc  # noqa: F401 (future use / constants reference)

logger = logging_util.logging.getLogger(__name__)

class ColorBalanceMixin:
    """Phase 5A: Post-spell color source analysis & basic land rebalance.

    Provides helper computations for color source matrix & spell pip weights plus
    the post-spell adjustment routine that can (optionally) swap lands and
    rebalance basics to better align mana sources with spell pip demand.
    """

    # ---------------------------
    # Color / pip computation helpers (cached)
    # ---------------------------
    def _compute_color_source_matrix(self) -> Dict[str, Dict[str,int]]:
        """Compute the color source matrix for the current deck library.
        Returns a mapping of card names to color sources, cached for efficiency.
        """
        if self._color_source_matrix_cache is not None and not self._color_source_cache_dirty:
            return self._color_source_matrix_cache
        matrix = bu.compute_color_source_matrix(self.card_library, getattr(self, '_full_cards_df', None))
        self._color_source_matrix_cache = matrix
        self._color_source_cache_dirty = False
        return matrix

    def _compute_spell_pip_weights(self) -> Dict[str, float]:
        """Compute the spell pip weights for the current deck library.
        Returns a mapping of color letters to pip weight, cached for efficiency.
        """
        if self._spell_pip_weights_cache is not None and not self._spell_pip_cache_dirty:
            return self._spell_pip_weights_cache
        weights = bu.compute_spell_pip_weights(self.card_library, self.color_identity)
        self._spell_pip_weights_cache = weights
        self._spell_pip_cache_dirty = False
        return weights

    def _current_color_source_counts(self) -> Dict[str,int]:
        """Return the current counts of color sources in the deck library.
        Uses the color source matrix to aggregate counts for each color.
        """
        matrix = self._compute_color_source_matrix()
        counts = {c:0 for c in ['W','U','B','R','G']}
        for name, colors in matrix.items():
            entry = self.card_library.get(name, {})
            copies = entry.get('Count',1)
            for c, v in colors.items():
                if v:
                    counts[c] += copies
        return counts

    # ---------------------------
    # Post-spell land adjustment & basic rebalance
    # ---------------------------
    def post_spell_land_adjust(
        self,
        pip_weights: Optional[Dict[str, float]] = None,
        color_shortfall_threshold: float = 0.15,
        perform_swaps: bool = False,
        max_swaps: int = 5,
        rebalance_basics: bool = True
    ):
        """Post-spell land adjustment and basic rebalance.
        Analyzes color deficits after spell addition and optionally swaps lands and rebalances basics
        to better align mana sources with spell pip demand.
        """
        if pip_weights is None:
            pip_weights = self._compute_spell_pip_weights()
        if self.color_source_matrix_baseline is None:
            self.color_source_matrix_baseline = self._compute_color_source_matrix()
        current_counts = self._current_color_source_counts()
        total_sources = sum(current_counts.values()) or 1
        source_share = {c: current_counts[c]/total_sources for c in current_counts}
        deficits: List[tuple[str,float,float,float]] = []
        for c in ['W','U','B','R','G']:
            pip_share = pip_weights.get(c,0.0)
            s_share = source_share.get(c,0.0)
            gap = pip_share - s_share
            if gap > color_shortfall_threshold and pip_share > 0.0:
                deficits.append((c,pip_share,s_share,gap))
        self.output_func("\nPost-Spell Color Distribution Analysis:")
        self.output_func("  Color | Pip% | Source% | Diff%")
        for c in ['W','U','B','R','G']:
            self.output_func(f"   {c:>1}    {pip_weights.get(c,0.0)*100:5.1f}%   {source_share.get(c,0.0)*100:6.1f}%   {(pip_weights.get(c,0.0)-source_share.get(c,0.0))*100:6.1f}%")
        if not deficits:
            self.output_func("  No color deficits above threshold.")
        else:
            self.output_func("  Deficits (need more sources):")
            for c, pip_share, s_share, gap in deficits:
                self.output_func(f"    {c}: need +{gap*100:.1f}% sources (pip {pip_share*100:.1f}% vs sources {s_share*100:.1f}%)")
        # We'll conditionally perform swaps; but even when skipping swaps we continue to basic rebalance.
        do_swaps = bool(perform_swaps and deficits)
        if not do_swaps:
            self.output_func("  (No land swaps performed.)")

        swaps_done: List[tuple[str,str,str]] = []
        if do_swaps:
            df = getattr(self, '_combined_cards_df', None)
            if df is None or df.empty:
                self.output_func("  Swap engine: card pool unavailable; aborting swaps.")
            else:
                deficits.sort(key=lambda x: x[3], reverse=True)
                overages: Dict[str,float] = {}
                for c in ['W','U','B','R','G']:
                    over = source_share.get(c,0.0) - pip_weights.get(c,0.0)
                    if over > 0:
                        overages[c] = over

                def removal_candidate(exclude_colors: set[str]) -> Optional[str]:
                    return bu.select_color_balance_removal(self, exclude_colors, overages)

                def addition_candidates(target_color: str) -> List[str]:
                    return bu.color_balance_addition_candidates(self, target_color, df)

                for color, _, _, gap in deficits:
                    if len(swaps_done) >= max_swaps:
                        break
                    adds = addition_candidates(color)
                    if not adds:
                        continue
                    to_add = None
                    for cand in adds:
                        if cand not in self.card_library:
                            to_add = cand
                            break
                    if not to_add:
                        continue
                    to_remove = removal_candidate({color})
                    if not to_remove:
                        continue
                    if not self._decrement_card(to_remove):
                        continue
                    self.add_card(to_add, card_type='Land', role='color-fix', sub_role='swap-add', added_by='color_balance')
                    swaps_done.append((to_remove, to_add, color))
                    current_counts = self._current_color_source_counts()
                    total_sources = sum(current_counts.values()) or 1
                    source_share = {c: current_counts[c]/total_sources for c in current_counts}
                    new_gap = pip_weights.get(color,0.0) - source_share.get(color,0.0)
                    if new_gap <= color_shortfall_threshold:
                        continue

        if swaps_done:
            self.output_func("\nColor Balance Swaps Performed:")
            for old, new, col in swaps_done:
                self.output_func(f"  [{col}] Replaced {old} -> {new}")
            final_counts = self._current_color_source_counts()
            final_total = sum(final_counts.values()) or 1
            final_source_share = {c: final_counts[c]/final_total for c in final_counts}
            self.output_func("  Updated Source Shares:")
            for c in ['W','U','B','R','G']:
                self.output_func(f"    {c}: {final_source_share.get(c,0.0)*100:5.1f}% (pip {pip_weights.get(c,0.0)*100:5.1f}%)")
        elif do_swaps:
            self.output_func("  (No viable swaps executed.)")

        # Always consider basic-land rebalance when requested
        if rebalance_basics:
            try:
                basic_map = getattr(bc, 'COLOR_TO_BASIC_LAND', {})
                basics_present = {nm: entry for nm, entry in self.card_library.items() if nm in basic_map.values()}
                if basics_present:
                    total_basics = sum(e.get('Count',1) for e in basics_present.values())
                    if total_basics > 0:
                        desired_per_color: Dict[str,int] = {}
                        for c, basic_name in basic_map.items():
                            if c not in ['W','U','B','R','G']:
                                continue
                            desired = pip_weights.get(c,0.0) * total_basics
                            desired_per_color[c] = int(round(desired))
                        drift = total_basics - sum(desired_per_color.values())
                        if drift != 0:
                            ordered = sorted(desired_per_color.items(), key=lambda kv: pip_weights.get(kv[0],0.0), reverse=(drift>0))
                            i = 0
                            while drift != 0 and ordered:
                                c,_ = ordered[i % len(ordered)]
                                desired_per_color[c] += 1 if drift>0 else -1
                                drift += -1 if drift>0 else 1
                                i += 1
                        changes: List[tuple[str,int,int]] = []
                        for c, basic_name in basic_map.items():
                            if c not in ['W','U','B','R','G']:
                                continue
                            target = max(0, desired_per_color.get(c,0))
                            entry = self.card_library.get(basic_name)
                            old = entry.get('Count',0) if entry else 0
                            if old == 0 and target>0:
                                for _ in range(target):
                                    self.add_card(basic_name, card_type='Land')
                                changes.append((basic_name, 0, target))
                            elif entry and old != target:
                                if target > old:
                                    for _ in range(target-old):
                                        self.add_card(basic_name, card_type='Land')
                                else:
                                    for _ in range(old-target):
                                        self._decrement_card(basic_name)
                                changes.append((basic_name, old, target))
                        if changes:
                            self.output_func("\nBasic Land Rebalance (toward pip distribution):")
                            for nm, old, new in changes:
                                self.output_func(f"  {nm}: {old} -> {new}")
            except Exception as e:  # pragma: no cover (defensive)
                self.output_func(f"  Basic rebalance skipped (error: {e})")
