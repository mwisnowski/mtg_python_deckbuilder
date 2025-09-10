from __future__ import annotations

from typing import List

from .. import builder_constants as bc
from .. import builder_utils as bu


class LandOptimizationMixin:
    """Mixin for Land Building Step 8: ETB Tapped Minimization / Optimization Pass.

    Provides optimize_tapped_lands and run_land_step8 (moved from monolithic builder).
    """

    def optimize_tapped_lands(self):  # type: ignore[override]
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            return
        bracket_level = getattr(self, 'bracket_level', None)
        threshold_map = getattr(bc, 'TAPPED_LAND_MAX_THRESHOLDS', {5:6,4:8,3:10,2:12,1:14})
        threshold = threshold_map.get(bracket_level, 10)

        name_to_row = {}
        for _, row in df.iterrows():
            nm = str(row.get('name',''))
            if nm and nm not in name_to_row:
                name_to_row[nm] = row.to_dict()

        tapped_info = []  # (name, penalty, tapped_flag)
        total_tapped = 0
        for name, entry in list(self.card_library.items()):
            row = name_to_row.get(name)
            if not row:
                continue
            tline = str(row.get('type', row.get('type_line',''))).lower()
            if 'land' not in tline:
                continue
            text_field = str(row.get('text', row.get('oracleText',''))).lower()
            tapped_flag, penalty = bu.tapped_land_penalty(tline, text_field)
            if tapped_flag:
                total_tapped += 1
                tapped_info.append((name, penalty, tapped_flag))

        if total_tapped <= threshold:
            self.output_func(f"Tapped Optimization (Step 8): {total_tapped} tapped/conditional lands (threshold {threshold}); no changes.")
            return

        over = total_tapped - threshold
        swap_min_penalty = getattr(bc, 'TAPPED_LAND_SWAP_MIN_PENALTY', 6)
        tapped_info.sort(key=lambda x: x[1], reverse=True)
        to_consider = [t for t in tapped_info if t[1] >= swap_min_penalty]
        if not to_consider:
            self.output_func(f"Tapped Optimization (Step 8): Over threshold ({total_tapped}>{threshold}) but no suitable swaps (penalties too low).")
            return

        replacement_candidates: List[str] = []
        seen = set(self.card_library.keys())
        colors = [c for c in getattr(self, 'color_identity', []) if c in ['W','U','B','R','G']]
        for _, row in df.iterrows():
            try:
                name = str(row.get('name',''))
                if not name or name in seen or name in replacement_candidates:
                    continue
                tline = str(row.get('type', row.get('type_line',''))).lower()
                if 'land' not in tline:
                    continue
                text_field = str(row.get('text', row.get('oracleText',''))).lower()
                if 'enters the battlefield tapped' in text_field and 'you may pay 2 life' not in text_field and 'unless you control' not in text_field:
                    continue
                produces_color = any(sym in text_field for sym in ['{w}','{u}','{b}','{r}','{g}'])
                basic_types = [b for b in ['plains','island','swamp','mountain','forest'] if b in tline]
                mapped = set()
                for b in basic_types:
                    if b == 'plains':
                        mapped.add('W')
                    elif b == 'island':
                        mapped.add('U')
                    elif b == 'swamp':
                        mapped.add('B')
                    elif b == 'mountain':
                        mapped.add('R')
                    elif b == 'forest':
                        mapped.add('G')
                if not produces_color and not (mapped & set(colors)):
                    continue
                replacement_candidates.append(name)
            except Exception:
                continue

        def repl_rank(name: str) -> int:
            row = name_to_row.get(name, {})
            tline = str(row.get('type', row.get('type_line','')))
            text_field = str(row.get('text', row.get('oracleText','')))
            return bu.replacement_land_score(name, tline, text_field)
        replacement_candidates.sort(key=repl_rank, reverse=True)

        swaps_made = []
        idx_rep = 0
        for name, penalty, _ in to_consider:
            if over <= 0:
                break
            if not self._decrement_card(name):
                continue
            replacement = None
            while idx_rep < len(replacement_candidates):
                cand = replacement_candidates[idx_rep]
                idx_rep += 1
                if cand in getattr(bc, 'GENERIC_FETCH_LANDS', []) or any(cand in lst for lst in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values()):
                    fetch_cap = getattr(bc, 'FETCH_LAND_MAX_CAP', 99)
                    existing_fetches = bu.count_existing_fetches(self.card_library)
                    if existing_fetches >= fetch_cap:
                        continue
                replacement = cand
                break
            if replacement is None:
                basics = self._basic_land_names()
                basic_counts = {b: self.card_library.get(b, {}).get('Count',0) for b in basics}
                color_basic_map = {'W':'Plains','U':'Island','B':'Swamp','R':'Mountain','G':'Forest'}
                usable_basics = [color_basic_map[c] for c in colors if color_basic_map[c] in basics]
                usable_basics.sort(key=lambda b: basic_counts.get(b,0))
                replacement = usable_basics[0] if usable_basics else 'Wastes'
            self.add_card(
                replacement,
                card_type='Land',
                role='optimized',
                sub_role='swap-in',
                added_by='lands_step8',
                trigger_tag='tapped_optimization'
            )
            swaps_made.append((name, replacement))
            over -= 1

        if not swaps_made:
            self.output_func(f"Tapped Optimization (Step 8): Could not perform swaps; over threshold {total_tapped}>{threshold}.")
            return
        self.output_func("\nTapped Optimization (Step 8) Swaps:")
        for old, new in swaps_made:
            self.output_func(f"  Replaced {old} -> {new}")
        new_tapped = 0
        for name, entry in self.card_library.items():
            row = name_to_row.get(name)
            if not row:
                continue
            text_field = str(row.get('text', row.get('oracleText',''))).lower()
            if 'enters the battlefield tapped' in text_field and 'you may pay 2 life' not in text_field:
                new_tapped += 1
        self.output_func(f"  Tapped Lands After : {new_tapped} (threshold {threshold})")

    def run_land_step8(self):  # type: ignore[override]
        self.optimize_tapped_lands()
        self._enforce_land_cap(step_label="Tapped Opt (Step 8)")
        if self.color_source_matrix_baseline is None:
            self.color_source_matrix_baseline = self._compute_color_source_matrix()
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '8')
        except Exception:
            pass
