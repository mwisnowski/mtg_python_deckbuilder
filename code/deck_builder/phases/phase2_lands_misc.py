from __future__ import annotations

from typing import Optional, List, Dict

from .. import builder_constants as bc
from .. import builder_utils as bu


class LandMiscUtilityMixin:
    """Mixin for Land Building Step 7: Misc / Utility Lands.

    Provides:
      - add_misc_utility_lands
      - run_land_step7
      - tag-driven suggestion queue helpers (_build_tag_driven_land_suggestions, _apply_land_suggestions_if_room)

    Extracted verbatim (with light path adjustments) from original monolithic builder.
    """

    def add_misc_utility_lands(self, requested_count: Optional[int] = None):  # type: ignore[override]
        if not getattr(self, 'files_to_load', None):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:
                self.output_func(f"Cannot add misc utility lands until color identity resolved: {e}")
                return
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            self.output_func("Misc Lands: No card pool loaded.")
            return

        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        current = self._current_land_count()
        remaining_capacity = max(0, land_target - current)
        if remaining_capacity <= 0:
            remaining_capacity = 0

        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        if requested_count is not None:
            desired = max(0, int(requested_count))
        else:
            desired = max(0, land_target - current)
        if desired == 0:
            self.output_func("Misc Lands: No remaining land capacity; skipping.")
            return

        basics = self._basic_land_names()
        already = set(self.card_library.keys())
        top_n = getattr(bc, 'MISC_LAND_TOP_POOL_SIZE', 30)
        top_candidates = bu.select_top_land_candidates(df, already, basics, top_n)
        if not top_candidates:
            self.output_func("Misc Lands: No remaining candidate lands.")
            return

        weighted_pool: List[tuple[str,int]] = []
        base_weight_fix = getattr(bc, 'MISC_LAND_COLOR_FIX_PRIORITY_WEIGHT', 2)
        fetch_names = set()
        for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
            for nm in seq:
                fetch_names.add(nm)
        for nm in getattr(bc, 'GENERIC_FETCH_LANDS', []):
            fetch_names.add(nm)
        existing_fetch_count = bu.count_existing_fetches(self.card_library)
        fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
        remaining_fetch_slots = max(0, fetch_cap - existing_fetch_count)

        for edh_val, name, tline, text_lower in top_candidates:
            w = 1
            if bu.is_color_fixing_land(tline, text_lower):
                w *= base_weight_fix
            if name in fetch_names and remaining_fetch_slots <= 0:
                continue
            weighted_pool.append((name, w))

        if self._current_land_count() >= land_target and desired > 0:
            slots_needed = desired
            freed = 0
            while freed < slots_needed and self._count_basic_lands() > basic_floor:
                target_basic = self._choose_basic_to_trim()
                if not target_basic or not self._decrement_card(target_basic):
                    break
                freed += 1
            if freed == 0 and self._current_land_count() >= land_target:
                self.output_func("Misc Lands: Cannot free capacity; skipping.")
                return

        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(weighted_pool))
        if desired <= 0:
            self.output_func("Misc Lands: No capacity after trimming; skipping.")
            return

        rng = getattr(self, 'rng', None)
        chosen = bu.weighted_sample_without_replacement(weighted_pool, desired, rng=rng)

        added: List[str] = []
        for nm in chosen:
            if self._current_land_count() >= land_target:
                break
            # Misc utility lands baseline role
            self.add_card(nm, card_type='Land', role='utility', sub_role='misc', added_by='lands_step7')
            added.append(nm)

        self.output_func("\nMisc Utility Lands Added (Step 7):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                note = ''
                row = next((r for r in top_candidates if r[1] == n), None)
                if row:
                    for edh_val, name2, tline2, text_lower2 in top_candidates:
                        if name2 == n and bu.is_color_fixing_land(tline2, text_lower2):
                            note = '(fixing)'
                            break
                self.output_func(f"  {n.ljust(width)} : 1  {note}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step7(self, requested_count: Optional[int] = None):  # type: ignore[override]
        self.add_misc_utility_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Utility (Step 7)")
        self._build_tag_driven_land_suggestions()
        self._apply_land_suggestions_if_room()

    # ---- Tag-driven suggestion helpers (used after Step 7) ----
    def _build_tag_driven_land_suggestions(self):  # type: ignore[override]
        suggestions = bu.build_tag_driven_suggestions(self)
        if suggestions:
            self.suggested_lands_queue.extend(suggestions)

    def _apply_land_suggestions_if_room(self):  # type: ignore[override]
        if not self.suggested_lands_queue:
            return
        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        applied: List[Dict] = []
        remaining: List[Dict] = []
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)
        for sug in self.suggested_lands_queue:
            name = sug['name']
            if name in self.card_library:
                continue
            if not sug['condition'](self):
                remaining.append(sug)
                continue
            if self._current_land_count() >= land_target:
                if sug.get('defer_if_full'):
                    if self._count_basic_lands() > basic_floor:
                        target_basic = self._choose_basic_to_trim()
                        if not target_basic or not self._decrement_card(target_basic):
                            remaining.append(sug)
                            continue
                    else:
                        remaining.append(sug)
                        continue
            # Tag suggestion additions (flex if marked)
            self.add_card(
                name,
                card_type='Land',
                role=('flex' if sug.get('flex') else 'utility'),
                sub_role='tag-suggested',
                added_by='tag_suggestion',
                trigger_tag=sug.get('reason')
            )
            applied.append(sug)
        self.suggested_lands_queue = remaining
        if applied:
            self.output_func("\nTag-Driven Utility Lands Added:")
            width = max(len(s['name']) for s in applied)
            for s in applied:
                role = ' (flex)' if s.get('flex') else ''
                self.output_func(f"  {s['name'].ljust(width)} : 1  {s['reason']}{role}")
