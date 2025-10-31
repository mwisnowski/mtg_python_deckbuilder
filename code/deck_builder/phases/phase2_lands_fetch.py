from __future__ import annotations
from typing import List
import random
from .. import builder_constants as bc

"""Phase 2 (part 4): Fetch lands (Land Step 4).

Extracted logic for adding color-specific and generic fetch lands.

Provided by LandFetchMixin:
  - add_fetch_lands(requested_count=None)
  - run_land_step4(requested_count=None)

Host DeckBuilder must supply:
  - attributes: files_to_load, ideal_counts, color_identity, card_library
  - methods: determine_color_identity(), setup_dataframes(), _current_land_count(),
             _basic_floor(), _count_basic_lands(), _choose_basic_to_trim(), _decrement_card(),
             add_card(), _prompt_int_with_default(), _enforce_land_cap(), output_func
"""

class LandFetchMixin:
    def add_fetch_lands(self, requested_count: int | None = None):
        """Add fetch lands (color-specific + generic) respecting land target."""
        if not getattr(self, 'files_to_load', []):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add fetch lands until color identity resolved: {e}")
                return
        land_target = (getattr(self, 'ideal_counts', {}).get('lands') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        current = self._current_land_count()
        color_order = [c for c in getattr(self, 'color_identity', []) if c in ['W','U','B','R','G']]
        color_map = getattr(bc, 'COLOR_TO_FETCH_LANDS', {})
        candidates: List[str] = []
        for c in color_order:
            for nm in color_map.get(c, []):
                if nm not in candidates:
                    candidates.append(nm)
        generic_list = getattr(bc, 'GENERIC_FETCH_LANDS', [])
        for nm in generic_list:
            if nm not in candidates:
                candidates.append(nm)
        candidates = [n for n in candidates if n not in getattr(self, 'card_library', {})]
        if not candidates:
            self.output_func("Fetch Lands: No eligible fetch lands remaining.")
            return
        default_fetch = getattr(bc, 'FETCH_LAND_DEFAULT_COUNT', 3)
        remaining_capacity = max(0, land_target - current)
        cap_for_default = remaining_capacity if remaining_capacity > 0 else len(candidates)
        effective_default = min(default_fetch, cap_for_default, len(candidates))
        existing_fetches = sum(1 for n in getattr(self, 'card_library', {}) if n in candidates)
        fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
        remaining_fetch_slots = max(0, fetch_cap - existing_fetches)
        if requested_count is None:
            self.output_func("\nAdd Fetch Lands (Step 4):")
            self.output_func("Fetch lands help fix colors & enable landfall / graveyard synergies.")
            prompt = f"Enter desired number of fetch lands (default: {effective_default}):"
            desired = self._prompt_int_with_default(prompt + ' ', effective_default, minimum=0, maximum=20)
        else:
            desired = max(0, int(requested_count))
        if desired > remaining_fetch_slots:
            desired = remaining_fetch_slots
            if desired == 0:
                self.output_func("Fetch Lands: Global fetch cap reached; skipping.")
                return
        if desired == 0:
            self.output_func("Fetch Lands: Desired count 0; skipping.")
            return
        if remaining_capacity == 0 and desired > 0:
            min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
            if getattr(self, 'ideal_counts', None):
                min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
            floor_basics = self._basic_floor(min_basic_cfg)
            slots_needed = desired
            while slots_needed > 0 and self._count_basic_lands() > floor_basics:
                target_basic = self._choose_basic_to_trim()
                if not target_basic or not self._decrement_card(target_basic):
                    break
                slots_needed -= 1
                remaining_capacity = max(0, land_target - self._current_land_count())
                if remaining_capacity > 0 and slots_needed == 0:
                    break
            if slots_needed > 0 and remaining_capacity == 0:
                desired -= slots_needed
        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(candidates), remaining_fetch_slots)
        if desired <= 0:
            self.output_func("Fetch Lands: No capacity (after trimming) or desired reduced to 0; skipping.")
            return
        rng = getattr(self, 'rng', None)
        color_specific_all: List[str] = []
        for c in color_order:
            for n in color_map.get(c, []):
                if n in candidates and n not in color_specific_all:
                    color_specific_all.append(n)
        generic_all: List[str] = [n for n in generic_list if n in candidates]
        def sampler(pool: List[str], k: int) -> List[str]:
            if k <= 0 or not pool:
                return []
            if k >= len(pool):
                return pool.copy()
            try:
                return (rng.sample if rng else random.sample)(pool, k)
            except Exception:
                return pool[:k]
        need = desired
        chosen: List[str] = []
        take_color = min(need, len(color_specific_all))
        chosen.extend(sampler(color_specific_all, take_color))
        need -= len(chosen)
        if need > 0:
            chosen.extend(sampler(generic_all, min(need, len(generic_all))))
        if len(chosen) < desired:
            leftovers = [n for n in candidates if n not in chosen]
            chosen.extend(leftovers[: desired - len(chosen)])

        added: List[str] = []
        for nm in chosen:
            if self._current_land_count() >= land_target:
                break
            note = 'generic' if nm in generic_list else 'color-specific'
            self.add_card(
                nm,
                card_type='Land',
                role='fetch',
                sub_role=note,
                added_by='lands_step4'
            )
            added.append(nm)
        # Record actual number of fetch lands added for export/replay context
        try:
            setattr(self, 'fetch_count', len(added))
        except Exception:
            pass
        self.output_func("\nFetch Lands Added (Step 4):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                note = 'generic' if n in generic_list else 'color-specific'
                self.output_func(f"  {n.ljust(width)} : 1  ({note})")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step4(self, requested_count: int | None = None):
        """Public wrapper to add fetch lands.

        If ideal_counts['fetch_lands'] is set, it will be used to bypass the prompt in both CLI and web builds.
        """
        desired = requested_count
        try:
            if desired is None and getattr(self, 'ideal_counts', None) and 'fetch_lands' in self.ideal_counts:
                desired = int(self.ideal_counts['fetch_lands'])
        except Exception:
            desired = requested_count
        self.add_fetch_lands(requested_count=desired)
        self._enforce_land_cap(step_label="Fetch (Step 4)")
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '4')
        except Exception:
            pass

__all__ = [
    'LandFetchMixin'
]
