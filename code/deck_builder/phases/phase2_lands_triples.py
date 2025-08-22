from __future__ import annotations

from typing import Optional, List, Dict, Set
import re

from .. import builder_constants as bc


class LandTripleMixin:
    """Mixin providing logic for adding three-color (triple) lands (Step 6).

    Extraction rationale:
      - Isolates a coherent land selection concern from the monolithic builder.
      - Mirrors earlier land step mixins with add_* and run_land_step6 methods.

    Strategy:
      1. Determine if the deck's color identity has at least 3 colors; else skip.
      2. Build a pool of candidate triple lands whose type line / name indicates they
         produce at least three of the deck colors (heuristic; full rules parsing is
         intentionally avoided for speed / simplicity with CSV data).
      3. Avoid adding duplicates or previously selected lands.
      4. Trim basics (above a computed floor) if capacity is reached and we still
         desire triple lands.
      5. Respect user-provided requested_count if supplied; otherwise fall back to
         default constant and capacity.
      6. Apply a simple ranking + slight randomization for determinism + variety.
    """

    def add_triple_lands(self, requested_count: Optional[int] = None):
        # Preconditions: color identity & dataframes
        if not getattr(self, 'files_to_load', None):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add triple lands until setup complete: {e}")
                return

        colors = [c for c in getattr(self, 'color_identity', []) if c in ['W','U','B','R','G']]
        if len(colors) < 3:
            self.output_func("Triple Lands: Fewer than three colors; skipping step 6.")
            return

        land_target = getattr(self, 'ideal_counts', {}).get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35)) if getattr(self, 'ideal_counts', None) else getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty or not {'name','type'}.issubset(df.columns):
            self.output_func("Triple Lands: No combined card dataframe or missing columns; skipping.")
            return

        pool: List[str] = []
        meta: Dict[str, str] = {}
        wanted: Set[str] = set(colors)
        basic_map = {
            'plains': 'W',
            'island': 'U',
            'swamp': 'B',
            'mountain': 'R',
            'forest': 'G',
        }

        for _, row in df.iterrows():  # type: ignore
            try:
                name = str(row.get('name',''))
                if not name or name in self.card_library:
                    continue
                tline = str(row.get('type','')).lower()
                if 'land' not in tline:
                    continue
                # Heuristic: count unique basic types in type line
                types_present = [b for b in basic_map if b in tline]
                mapped = {basic_map[b] for b in types_present}

                # Extract color production from rules text if present
                text_field = str(row.get('text', row.get('oracleText',''))).lower()
                color_syms = set(re.findall(r'\{([wubrg])\}', text_field))
                color_syms_mapped = {c.upper() for c in color_syms}

                lname = name.lower()
                tri_keywords = [
                    'triome','panorama','citadel','tower','hub','garden','headquarters','sanctuary',
                    'stronghold','outpost','campus','shrine','domain','estate'
                ]

                # Decide if candidate qualifies:
                qualifies_by_types = len(mapped) >= 3
                qualifies_by_text = len(color_syms_mapped) >= 3 and color_syms_mapped.issubset(wanted)
                qualifies_by_name = any(kw in lname for kw in tri_keywords)

                if not (qualifies_by_types or qualifies_by_text or (qualifies_by_name and (len(mapped) >= 2 or len(color_syms_mapped) >= 2))):
                    continue

                # Consolidate produced colors for validation (prefer typed, else text)
                produced = mapped if mapped else color_syms_mapped
                if not produced.issubset(wanted):
                    continue

                if qualifies_by_types or len(produced) >= 3:
                    pool.append(name)
                    meta[name] = tline
                else:
                    pool.append(name)
                    meta[name] = tline + ' (heuristic-tri)'
            except Exception:  # pragma: no cover - defensive
                continue

        # De-duplicate while preserving order
        pool = list(dict.fromkeys(pool))
        if not pool:
            self.output_func("Triple Lands: No candidates found.")
            return

        # Ranking heuristic: fully triple-typed > untapped > others; penalize ETB tapped
        def rank(name: str) -> int:
            tline = meta.get(name, '')
            score = 0
            if '(heuristic-tri)' not in tline:
                score += 5
            if 'enters the battlefield tapped' not in tline:
                score += 2
            if 'cycling' in tline:
                score += 1
            if 'enters the battlefield tapped' in tline and 'you gain' in tline:
                score -= 1
            return score

        pool.sort(key=lambda n: rank(n), reverse=True)

        # Slight randomized shuffle weighted by rank for variety
        rng = getattr(self, 'rng', None) or self._get_rng()
        try:
            weighted = []
            for n in pool:
                w = max(1, rank(n)) + 1
                weighted.append((n, w))
            shuffled: List[str] = []
            while weighted:
                total = sum(w for _, w in weighted)
                r = rng.random() * total
                acc = 0.0
                for idx, (n, w) in enumerate(weighted):
                    acc += w
                    if r <= acc:
                        shuffled.append(n)
                        del weighted[idx]
                        break
            pool = shuffled
        except Exception:  # pragma: no cover - fallback
            pass

        # Capacity handling
        remaining_capacity = max(0, land_target - self._current_land_count())
        default_triple_target = getattr(bc, 'TRIPLE_LAND_DEFAULT_COUNT', 3)
        effective_default = min(default_triple_target, remaining_capacity if remaining_capacity>0 else len(pool), len(pool))
        if requested_count is None:
            desired = effective_default
        else:
            desired = max(0, int(requested_count))
        if desired == 0:
            self.output_func("Triple Lands: Desired count 0; skipping.")
            return

        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)

        if remaining_capacity == 0 and desired > 0:
            slots_needed = desired
            freed = 0
            while freed < slots_needed and self._count_basic_lands() > basic_floor:
                target_basic = self._choose_basic_to_trim()
                if not target_basic:
                    break
                if not self._decrement_card(target_basic):
                    break
                freed += 1
            if freed == 0:
                desired = 0
        remaining_capacity = max(0, land_target - self._current_land_count())
        desired = min(desired, remaining_capacity, len(pool))
        if desired <= 0:
            self.output_func("Triple Lands: No capacity after trimming; skipping.")
            return

        added: List[str] = []
        for name in pool:
            if len(added) >= desired or self._current_land_count() >= land_target:
                break
            # Infer color trio from type line basic types
            try:
                row_match = df[df['name'] == name]
                tline = ''
                text_field = ''
                sub_role = None
                if not row_match.empty:
                    rw = row_match.iloc[0]
                    tline = str(rw.get('type','')).lower()
                    text_field = str(rw.get('text', rw.get('oracleText',''))).lower()
                trio = []
                for basic, col in [('plains','W'),('island','U'),('swamp','B'),('mountain','R'),('forest','G')]:
                    if basic in tline:
                        trio.append(col)
                if len(trio) < 3:
                    color_syms = set(re.findall(r'\{([wubrg])\}', text_field))
                    trio = [c.upper() for c in color_syms]
                if len(trio) >= 2:
                    sub_role = ''.join(sorted(set(trio)))
            except Exception:
                sub_role = None
            self.add_card(
                name,
                card_type='Land',
                role='triple',
                sub_role=sub_role,
                added_by='lands_step6'
            )
            added.append(name)


        self.output_func("\nTriple Lands Added (Step 6):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")

    def run_land_step6(self, requested_count: Optional[int] = None):
        self.add_triple_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Triples (Step 6)")
