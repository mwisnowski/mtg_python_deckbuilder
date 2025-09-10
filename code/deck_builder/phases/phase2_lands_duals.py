from __future__ import annotations
from typing import List, Dict
import random
from .. import builder_constants as bc

"""Phase 2 (part 5): Dual typed lands (Land Step 5).

Extracted from `builder.py` to modularize land building. Handles addition of two-color
basic-typed dual lands (e.g., Shock lands, typed cycle) with basic land type detection
and heuristic ranking plus a weighted shuffle for variety.

Provided by LandDualsMixin:
  - add_dual_lands(requested_count: int | None = None)
  - run_land_step5(requested_count: int | None = None)

Host DeckBuilder must provide:
  - attributes: files_to_load, color_identity, ideal_counts, card_library, _combined_cards_df
  - methods: determine_color_identity(), setup_dataframes(), _current_land_count(),
             _basic_floor(), _count_basic_lands(), _choose_basic_to_trim(), _decrement_card(),
             add_card(), _enforce_land_cap(), output_func
"""

class LandDualsMixin:
    def add_dual_lands(self, requested_count: int | None = None):  # type: ignore[override]
        """Add two-color 'typed' dual lands based on color identity."""
        if not getattr(self, 'files_to_load', []):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add dual lands until color identity resolved: {e}")
                return
        colors = [c for c in getattr(self, 'color_identity', []) if c in ['W','U','B','R','G']]
        if len(colors) < 2:
            self.output_func("Dual Lands: Not multi-color; skipping step 5.")
            return
        land_target = (getattr(self, 'ideal_counts', {}) or {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35))
        df = getattr(self, '_combined_cards_df', None)
        pool: List[str] = []
        type_to_card: Dict[str,str] = {}
        pair_buckets: Dict[frozenset[str], List[str]] = {}
        if df is not None and not df.empty and {'name','type'}.issubset(df.columns):
            try:
                for _, row in df.iterrows():
                    try:
                        name = str(row.get('name',''))
                        if not name or name in getattr(self, 'card_library', {}):
                            continue
                        tline = str(row.get('type','')).lower()
                        if 'land' not in tline:
                            continue
                        types_present = [basic for basic in ['plains','island','swamp','mountain','forest'] if basic in tline]
                        if len(types_present) < 2:
                            continue
                        mapped_colors = set()
                        for tp in types_present:
                            if tp == 'plains':
                                mapped_colors.add('W')
                            elif tp == 'island':
                                mapped_colors.add('U')
                            elif tp == 'swamp':
                                mapped_colors.add('B')
                            elif tp == 'mountain':
                                mapped_colors.add('R')
                            elif tp == 'forest':
                                mapped_colors.add('G')
                        if len(mapped_colors) != 2:
                            continue
                        if not mapped_colors.issubset(set(colors)):
                            continue
                        pool.append(name)
                        type_to_card[name] = tline
                        key = frozenset(mapped_colors)
                        pair_buckets.setdefault(key, []).append(name)
                    except Exception:
                        continue
            except Exception:
                pass
        pool = list(dict.fromkeys(pool))
        if not pool:
            self.output_func("Dual Lands: No candidate dual typed lands found in dataset.")
            return
        def rank(name: str) -> int:
            lname = name.lower()
            tline = type_to_card.get(name,'')
            score = 0
            if any(kw in lname for kw in ['temple garden','sacred foundry','stomping ground','hallowed fountain','watery grave','overgrown tomb','breeding pool','godless shrine','steam vents','blood crypt']):
                score += 10
            if 'enters the battlefield tapped' not in tline:
                score += 2
            if 'snow' in tline:
                score += 1
            if 'enters the battlefield tapped' in tline and 'you gain' in tline:
                score -= 1
            return score
        for key, names in pair_buckets.items():
            names.sort(key=lambda n: rank(n), reverse=True)
            if len(names) > 1:
                rng_obj = getattr(self, 'rng', None)
                try:
                    weighted = [(n, max(1, rank(n))+1) for n in names]
                    shuffled: List[str] = []
                    while weighted:
                        total = sum(w for _n, w in weighted)
                        r = (rng_obj.random() if rng_obj else random.random()) * total
                        acc = 0.0
                        for idx, (n, w) in enumerate(weighted):
                            acc += w
                            if r <= acc:
                                shuffled.append(n)
                                del weighted[idx]
                                break
                    pair_buckets[key] = shuffled
                except Exception:
                    pair_buckets[key] = names
            else:
                pair_buckets[key] = names
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if getattr(self, 'ideal_counts', None):
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)  # type: ignore[attr-defined]
        basic_floor = self._basic_floor(min_basic_cfg)  # type: ignore[attr-defined]
        default_dual_target = getattr(bc, 'DUAL_LAND_DEFAULT_COUNT', 6)
        remaining_capacity = max(0, land_target - self._current_land_count())  # type: ignore[attr-defined]
        effective_default = min(default_dual_target, remaining_capacity if remaining_capacity>0 else len(pool), len(pool))
        desired = effective_default if requested_count is None else max(0, int(requested_count))
        if desired == 0:
            self.output_func("Dual Lands: Desired count 0; skipping.")
            return
        if remaining_capacity == 0 and desired > 0:
            slots_needed = desired
            freed_slots = 0
            while freed_slots < slots_needed and self._count_basic_lands() > basic_floor:  # type: ignore[attr-defined]
                target_basic = self._choose_basic_to_trim()  # type: ignore[attr-defined]
                if not target_basic or not self._decrement_card(target_basic):  # type: ignore[attr-defined]
                    break
                freed_slots += 1
            if freed_slots == 0:
                desired = 0
        remaining_capacity = max(0, land_target - self._current_land_count())  # type: ignore[attr-defined]
        desired = min(desired, remaining_capacity, len(pool))
        if desired <= 0:
            self.output_func("Dual Lands: No capacity after trimming; skipping.")
            return
        chosen: List[str] = []
        bucket_keys = list(pair_buckets.keys())
        rng = getattr(self, 'rng', None)
        try:
            if rng:
                rng.shuffle(bucket_keys)  # type: ignore
            else:
                random.shuffle(bucket_keys)
        except Exception:
            pass
        indices = {k:0 for k in bucket_keys}
        while len(chosen) < desired and bucket_keys:
            progressed = False
            for k in list(bucket_keys):
                idx = indices[k]
                names = pair_buckets.get(k, [])
                if idx >= len(names):
                    continue
                name = names[idx]
                indices[k] += 1
                if name in chosen:
                    continue
                chosen.append(name)
                progressed = True
                if len(chosen) >= desired:
                    break
            if not progressed:
                break
        added: List[str] = []
        for name in chosen:
            if self._current_land_count() >= land_target:  # type: ignore[attr-defined]
                break
            # Determine sub_role as concatenated color pair for traceability
            try:
                tline = type_to_card.get(name, '')
                types_present = [basic for basic in ['plains','island','swamp','mountain','forest'] if basic in tline]
                mapped_colors = []
                for tp in types_present:
                    if tp == 'plains':
                        mapped_colors.append('W')
                    elif tp == 'island':
                        mapped_colors.append('U')
                    elif tp == 'swamp':
                        mapped_colors.append('B')
                    elif tp == 'mountain':
                        mapped_colors.append('R')
                    elif tp == 'forest':
                        mapped_colors.append('G')
                sub_role = ''.join(sorted(set(mapped_colors))) if mapped_colors else None
            except Exception:
                sub_role = None
            self.add_card(
                name,
                card_type='Land',
                role='dual',
                sub_role=sub_role,
                added_by='lands_step5'
            )  # type: ignore[attr-defined]
            added.append(name)
        self.output_func("\nDual Lands Added (Step 5):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")  # type: ignore[attr-defined]

    def run_land_step5(self, requested_count: int | None = None):  # type: ignore[override]
        self.add_dual_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Duals (Step 5)")  # type: ignore[attr-defined]
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '5')
        except Exception:
            pass

__all__ = [
    'LandDualsMixin'
]
