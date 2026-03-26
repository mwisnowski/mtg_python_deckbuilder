from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from .. import builder_constants as bc
from .. import builder_utils as bu

"""Phase 2 (pre-step): Smart land base analysis (Roadmap 14, M1).

LandAnalysisMixin.run_land_analysis() is called from run_deck_build_step2()
AFTER ideal_counts defaults are seeded, so ENABLE_SMART_LANDS, LAND_PROFILE,
and LAND_COUNT env overrides win over the calculated values.

Responsibilities:
  - compute_pip_density(): delegate to builder_utils
  - analyze_curve(): delegate to builder_utils
  - determine_profile(): basics / mid / fixing rules from Profile Definitions
  - run_land_analysis(): orchestrates analysis, sets ideal_counts, self._land_profile
"""

logger = logging.getLogger(__name__)


class LandAnalysisMixin:

    # ------------------------------------------------------------------
    # Public entry point — called from run_deck_build_step2()
    # ------------------------------------------------------------------

    def run_land_analysis(self) -> None:
        """Analyse the commander and color identity to set a smart land profile.

        Sets:
            self._land_profile      'basics' | 'mid' | 'fixing'  (default: 'mid')
            self._speed_category    'fast' | 'mid' | 'slow'
            self._land_report_data  dict persisted for M3 diagnostics export
        Mutates:
            self.ideal_counts['lands'] and self.ideal_counts['basic_lands']
            (only when ENABLE_SMART_LANDS=1; env overrides honoured after)
        """
        if not os.environ.get('ENABLE_SMART_LANDS'):
            return

        try:
            self._run_land_analysis_inner()
        except Exception as exc:
            logger.warning('run_land_analysis failed (%s); defaulting to mid profile', exc)
            self._land_profile = 'mid'
            self._speed_category = 'mid'

    def _run_land_analysis_inner(self) -> None:
        color_identity = getattr(self, 'color_identity', []) or []
        colors = [c for c in color_identity if c in ('W', 'U', 'B', 'R', 'G')]
        color_count = len(colors)

        # --- Card pool DataFrame (available at step 2; card_library is still empty) ---
        pool_df = getattr(self, '_combined_cards_df', None)

        # --- Curve analysis: commander CMC + pool average CMC (weighted) ---
        _cdict = getattr(self, 'commander_dict', None) or {}
        commander_cmc = float(_cdict.get('CMC') or _cdict.get('Mana Value') or 3.5)
        effective_cmc = commander_cmc
        avg_pool_cmc: Optional[float] = None
        if pool_df is not None and not pool_df.empty:
            try:
                non_land = pool_df[~pool_df['type'].str.lower().str.contains('land', na=False)]
                if not non_land.empty and 'manaValue' in non_land.columns:
                    avg_pool_cmc = float(non_land['manaValue'].mean())
                    # Weight commander CMC more heavily (it's the clearest intent signal)
                    effective_cmc = commander_cmc * 0.6 + avg_pool_cmc * 0.4
            except Exception as exc:
                logger.debug('Pool average CMC failed (%s); using commander CMC only', exc)
        curve_stats = bu.analyze_curve(effective_cmc, color_count)
        speed: str = curve_stats['speed_category']
        # Apply the speed-based offset relative to the user's configured ideal land count.
        # e.g. if the user set 40 lands: fast gets 38, mid stays 40, slow gets 42-44.
        # This respects custom ideals instead of always using the hardcoded 33/35/37-39.
        mid_default = getattr(bc, 'LAND_COUNT_MID', 35)
        _user_land_base = int((getattr(self, 'ideal_counts', None) or {}).get('lands', mid_default))
        _speed_offset = curve_stats['land_target'] - mid_default
        land_target: int = max(1, _user_land_base + _speed_offset)
        _orig_land_target = curve_stats['land_target']
        basic_target: int = (
            max(color_count, int(round(curve_stats['basic_target'] * land_target / _orig_land_target)))
            if _orig_land_target > 0
            else curve_stats['basic_target']
        )

        # --- Pip density analysis from pool (card_library is empty at step 2) ---
        pip_density: Dict[str, Dict[str, int]] = {}
        try:
            if pool_df is not None and not pool_df.empty:
                # Convert pool to minimal dict format for compute_pip_density
                records = pool_df[['manaCost', 'type']].fillna('').to_dict('records')
                pool_dict = {
                    str(i): {
                        'Mana Cost': str(r.get('manaCost') or ''),
                        'Card Type': str(r.get('type') or ''),
                    }
                    for i, r in enumerate(records)
                }
                pip_density = bu.compute_pip_density(pool_dict, colors)
            else:
                # Fallback for tests / headless contexts without a loaded DataFrame
                card_library = getattr(self, 'card_library', {})
                pip_density = bu.compute_pip_density(card_library, colors)
        except Exception as exc:
            logger.warning('compute_pip_density failed (%s); profile from curve only', exc)

        # --- Profile determination ---
        profile = self._determine_profile(pip_density, color_count)

        # --- Budget override ---
        budget_total = getattr(self, 'budget_total', None)
        if budget_total is not None and color_count >= 3:
            budget_threshold = getattr(bc, 'BUDGET_FORCE_BASICS_THRESHOLD', 50.0)
            if float(budget_total) < budget_threshold:
                prev_profile = profile
                profile = 'basics'
                self.output_func(
                    f'[Smart Lands] Budget ${budget_total:.0f} < ${budget_threshold:.0f} '
                    f'with {color_count} colors: forcing basics-heavy profile '
                    f'(was {prev_profile}).'
                )

        # --- LAND_PROFILE env override (highest priority) ---
        env_profile = os.environ.get('LAND_PROFILE', '').strip().lower()
        if env_profile in ('basics', 'mid', 'fixing'):
            profile = env_profile

        # --- Compute basic count for profile ---
        basics = self._basics_for_profile(profile, color_count, land_target)

        # --- LAND_COUNT env override ---
        env_land_count = os.environ.get('LAND_COUNT', '').strip()
        if env_land_count.isdigit():
            land_target = int(env_land_count)
            # Re-clamp basics against (possibly overridden) land target
            min_headroom = getattr(bc, 'BASICS_MIN_HEADROOM', 5)
            basics = min(basics, land_target - min_headroom)
            basics = max(basics, color_count)

        # --- Apply to ideal_counts ---
        ideal: Dict[str, int] = getattr(self, 'ideal_counts', {})
        ideal['lands'] = land_target
        ideal['basic_lands'] = basics

        # --- Pip summary for reporting ---
        total_double = sum(v.get('double', 0) for v in pip_density.values())
        total_triple = sum(v.get('triple', 0) for v in pip_density.values())
        # Pips were a deciding factor when they pushed profile away from the default
        pip_was_deciding = (
            (color_count >= 3 and (total_double >= 15 or total_triple >= 3))
            or (color_count <= 2 and total_double < 5 and total_triple == 0)
        )

        # --- Persist analysis state ---
        self._land_profile = profile
        self._speed_category = speed
        self._land_report_data: Dict[str, Any] = {
            'profile': profile,
            'speed_category': speed,
            'commander_cmc': commander_cmc,
            'effective_cmc': effective_cmc,
            'avg_pool_cmc': avg_pool_cmc,
            'color_count': color_count,
            'land_target': land_target,
            'basic_target': basics,
            'pip_density': pip_density,
            'total_double_pips': total_double,
            'total_triple_pips': total_triple,
            'pip_was_deciding': pip_was_deciding,
            'budget_total': budget_total,
            'env_overrides': {
                'LAND_PROFILE': env_profile or None,
                'LAND_COUNT': env_land_count or None,
            },
        }

        rationale = self._build_rationale(profile, speed, commander_cmc, effective_cmc, color_count, pip_density, budget_total)
        self._land_report_data['rationale'] = rationale

        self.output_func(
            f'\n[Smart Lands] Profile: {profile} | Speed: {speed} | '
            f'Lands: {land_target} | Basics: {basics}'
        )
        self.output_func(f'  Rationale: {rationale}')

        # --- Earmark land slots: scale non-land ideals to fit within the remaining budget ---
        # Commander takes 1 slot, so there are 99 slots for non-commander cards.
        # If non-land ideal counts sum to more than (99 - land_target), the spell phases
        # will fill those slots first (in spells-first builds) leaving no room for lands.
        self._earmark_land_slots(land_target)

    def _earmark_land_slots(self, land_target: int) -> None:
        """Scale non-land ideal_counts down so they fit within 99 - land_target slots.

        This ensures the spell phases never consume the slots reserved for lands,
        making backfill unnecessary in the normal case.
        """
        NON_LAND_KEYS = ['creatures', 'ramp', 'removal', 'wipes', 'card_advantage', 'protection']
        # 99 = total deck slots minus commander
        deck_slots = getattr(bc, 'DECK_NON_COMMANDER_SLOTS', 99)
        budget = deck_slots - land_target
        if budget <= 0:
            return
        ideal: Dict[str, int] = getattr(self, 'ideal_counts', {})
        current_sum = sum(int(ideal.get(k, 0)) for k in NON_LAND_KEYS)
        if current_sum <= budget:
            return  # already fits; nothing to do

        # Scale each key down proportionally (floor), then top up from the largest key first.
        scale = budget / current_sum
        new_vals: Dict[str, int] = {}
        for k in NON_LAND_KEYS:
            new_vals[k] = max(0, int(int(ideal.get(k, 0)) * scale))
        remainder = budget - sum(new_vals.values())
        # Distribute leftover slots to the largest keys first (preserves relative proportion)
        for k in sorted(NON_LAND_KEYS, key=lambda x: -int(ideal.get(x, 0))):
            if remainder <= 0:
                break
            new_vals[k] += 1
            remainder -= 1
        # Apply and report
        adjustments: list[str] = []
        for k in NON_LAND_KEYS:
            old = int(ideal.get(k, 0))
            new = new_vals[k]
            if old != new:
                ideal[k] = new
                adjustments.append(f'{k}: {old}→{new}')
        if adjustments:
            self.output_func(
                f'  [Smart Lands] Earmarked {land_target} land slots; '
                f'scaled non-land targets to fit {budget} remaining: {", ".join(adjustments)}'
            )

    # ------------------------------------------------------------------
    # Profile determination
    # ------------------------------------------------------------------

    def _determine_profile(
        self,
        pip_density: Dict[str, Dict[str, int]],
        color_count: int,
    ) -> str:
        """Determine the land profile from pip density and color count.

        Rules (in priority order):
          1. 5-color → fixing
          2. 1-color → basics
          3. High pip density (≥15 double-pips or ≥3 triple-pips) AND 3+ colors → fixing
          4. Low pip density (<5 double-pips, 0 triple-pips) AND 1-2 colors → basics
          5. Otherwise → mid
        """
        if color_count >= 5:
            return 'fixing'
        if color_count <= 1:
            return 'basics'

        total_double = sum(v.get('double', 0) for v in pip_density.values())
        total_triple = sum(v.get('triple', 0) for v in pip_density.values())

        if color_count >= 3 and (total_double >= 15 or total_triple >= 3):
            return 'fixing'
        if color_count <= 2 and total_double < 5 and total_triple == 0:
            return 'basics'
        return 'mid'

    # ------------------------------------------------------------------
    # Basics count per profile
    # ------------------------------------------------------------------

    def _basics_for_profile(self, profile: str, color_count: int, land_target: int) -> int:
        min_headroom = getattr(bc, 'BASICS_MIN_HEADROOM', 5)
        if profile == 'basics':
            ratio = getattr(bc, 'BASICS_HEAVY_RATIO', 0.60)
            count = int(round(land_target * ratio))
        elif profile == 'fixing':
            per_color = getattr(bc, 'BASICS_FIXING_PER_COLOR', 2)
            count = max(color_count * per_color, color_count)
        else:  # mid
            # Default ratio preserved — same as current behavior
            count = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 15)
        # Clamp
        count = min(count, land_target - min_headroom)
        count = max(count, color_count)
        return count

    # ------------------------------------------------------------------
    # Rationale string
    # ------------------------------------------------------------------

    def _build_rationale(
        self,
        profile: str,
        speed: str,
        commander_cmc: float,
        effective_cmc: float,
        color_count: int,
        pip_density: Dict[str, Dict[str, int]],
        budget: Optional[float],
    ) -> str:
        total_double = sum(v.get('double', 0) for v in pip_density.values())
        total_triple = sum(v.get('triple', 0) for v in pip_density.values())
        if abs(effective_cmc - commander_cmc) >= 0.2:
            cmc_label = f'commander CMC {commander_cmc:.0f}, effective {effective_cmc:.1f} (with pool avg)'
        else:
            cmc_label = f'commander CMC {commander_cmc:.1f}'
        parts = [
            f'{color_count}-color identity',
            f'{cmc_label} ({speed} deck)',
        ]
        if pip_density:
            parts.append(f'{total_double} double-pips, {total_triple} triple-or-more-pips')
        if budget is not None:
            parts.append(f'budget ${budget:.0f}')
        profile_desc = {
            'basics': 'basics-heavy (minimal fixing)',
            'mid': 'balanced (moderate fixing)',
            'fixing': 'fixing-heavy (extensive duals/fetches)',
        }.get(profile, profile)
        return f'{profile_desc} — {", ".join(parts)}'

    # ------------------------------------------------------------------
    # Post-build diagnostics (M3) — called from build_deck_summary()
    # ------------------------------------------------------------------

    def generate_diagnostics(self) -> None:
        """Update _land_report_data with post-build actuals from card_library.

        Runs after all land/spell phases have added cards so card_library is
        fully populated.  Safe to call even when ENABLE_SMART_LANDS is off —
        initialises _land_report_data with basic actuals if missing.
        """
        if not hasattr(self, '_land_report_data'):
            self._land_report_data = {}

        library = getattr(self, 'card_library', {})
        if not library:
            return

        # Build a name → row dict for type/oracle text lookups
        df = getattr(self, '_combined_cards_df', None)
        name_to_row: Dict[str, Any] = {}
        if df is not None and not getattr(df, 'empty', True):
            try:
                for _, row in df.iterrows():
                    nm = str(row.get('name', '') or '')
                    if nm and nm not in name_to_row:
                        name_to_row[nm] = row.to_dict()
            except Exception as exc:
                logger.debug('generate_diagnostics: df scan failed (%s)', exc)

        total_lands = 0
        tapped_count = 0
        fixing_count = 0
        basic_count = 0

        for name, info in library.items():
            ctype = str(info.get('Card Type', '') or '')
            if 'land' not in ctype.lower():
                continue
            total_lands += 1
            if 'basic' in ctype.lower():
                basic_count += 1
            row = name_to_row.get(name, {})
            tline = str(row.get('type', ctype) or ctype).lower()
            text_field = str(row.get('text', '') or '').lower()
            tapped_flag, _ = bu.tapped_land_penalty(tline, text_field)
            if tapped_flag:
                tapped_count += 1
            if bu.is_color_fixing_land(tline, text_field):
                fixing_count += 1

        tapped_pct = round(tapped_count / total_lands * 100, 1) if total_lands else 0.0
        self._land_report_data.update({
            'actual_land_count': total_lands,
            'actual_tapped_count': tapped_count,
            'actual_fixing_count': fixing_count,
            'actual_basic_count': basic_count,
            'tapped_pct': tapped_pct,
        })
