from __future__ import annotations

import math
from typing import List, Dict

from .. import builder_constants as bc
from .. import builder_utils as bu
import logging_util

logger = logging_util.logging.getLogger(__name__)

class CreatureAdditionMixin:
    """Phase 3: Creature addition logic extracted from monolithic builder.

    Responsibilities:
      - Determine per-theme allocation weights (1-3 themes supported)
      - Apply kindred/tribal multipliers when multiple themes selected
      - Prioritize cards matching multiple selected themes
      - Avoid duplicating the commander
      - Deterministic weighted sampling via builder_utils helper
    """
    def add_creatures(self):
        """Add creatures to the deck based on selected themes and allocation weights.
        Applies kindred/tribal multipliers, prioritizes multi-theme matches, and avoids commander duplication.
        Uses weighted sampling for selection and fills shortfall if needed.
        """
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            self.output_func("Card pool not loaded; cannot add creatures.")
            return
        if 'type' not in df.columns:
            self.output_func("Card pool missing 'type' column; cannot add creatures.")
            return
        themes_ordered: List[tuple[str, str]] = []
        if self.primary_tag:
            themes_ordered.append(('primary', self.primary_tag))
        if self.secondary_tag:
            themes_ordered.append(('secondary', self.secondary_tag))
        if self.tertiary_tag:
            themes_ordered.append(('tertiary', self.tertiary_tag))
        if not themes_ordered:
            self.output_func("No themes selected; skipping creature addition.")
            return
        desired_total = (self.ideal_counts.get('creatures') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_CREATURE_COUNT', 25)
        n_themes = len(themes_ordered)
        if n_themes == 1:
            base_map = {'primary': 1.0}
        elif n_themes == 2:
            base_map = {'primary': 0.6, 'secondary': 0.4}
        else:
            base_map = {'primary': 0.5, 'secondary': 0.3, 'tertiary': 0.2}
        weights: Dict[str, float] = {}
        boosted_roles: set[str] = set()
        if n_themes > 1:
            for role, tag in themes_ordered:
                w = base_map.get(role, 0.0)
                lt = tag.lower()
                if 'kindred' in lt or 'tribal' in lt:
                    mult = getattr(bc, 'WEIGHT_ADJUSTMENT_FACTORS', {}).get(f'kindred_{role}', 1.0)
                    w *= mult
                    boosted_roles.add(role)
                weights[role] = w
            total = sum(weights.values())
            if total > 1.0:
                for r in list(weights):
                    weights[r] /= total
            else:
                rem = 1.0 - total
                base_sum_unboosted = sum(base_map[r] for r,_t in themes_ordered if r not in boosted_roles)
                if rem > 1e-6 and base_sum_unboosted > 0:
                    for r,_t in themes_ordered:
                        if r not in boosted_roles:
                            weights[r] += rem * (base_map[r] / base_sum_unboosted)
        else:
            weights['primary'] = 1.0
        creature_df = df[df['type'].str.contains('Creature', case=False, na=False)].copy()
        commander_name = getattr(self, 'commander', None) or getattr(self, 'commander_name', None)
        if commander_name and 'name' in creature_df.columns:
            creature_df = creature_df[creature_df['name'] != commander_name]
        if creature_df.empty:
            self.output_func("No creature rows in dataset; skipping.")
            return
        selected_tags_lower = [t.lower() for _r,t in themes_ordered]
        if '_parsedThemeTags' not in creature_df.columns:
            creature_df['_parsedThemeTags'] = creature_df['themeTags'].apply(bu.normalize_tag_cell)
        creature_df['_normTags'] = creature_df['_parsedThemeTags']
        creature_df['_multiMatch'] = creature_df['_normTags'].apply(lambda lst: sum(1 for t in selected_tags_lower if t in lst))
        base_top = 30
        top_n = int(base_top * getattr(bc, 'THEME_POOL_SIZE_MULTIPLIER', 2.0))
        synergy_bonus = getattr(bc, 'THEME_PRIORITY_BONUS', 1.2)
        total_added = 0
        added_names: List[str] = []
        per_theme_added: Dict[str, List[str]] = {r: [] for r,_t in themes_ordered}
        for role, tag in themes_ordered:
            w = weights.get(role, 0.0)
            if w <= 0:
                continue
            remaining = max(0, desired_total - total_added)
            if remaining == 0:
                break
            target = int(math.ceil(desired_total * w * self._get_rng().uniform(1.0, 1.1)))
            target = min(target, remaining)
            if target <= 0:
                continue
            tnorm = tag.lower()
            subset = creature_df[creature_df['_normTags'].apply(lambda lst, tn=tnorm: (tn in lst) or any(tn in x for x in lst))]
            if subset.empty:
                self.output_func(f"Theme '{tag}' produced no creature candidates.")
                continue
            if 'edhrecRank' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
            elif 'manaValue' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
            pool = subset.head(top_n).copy()
            pool = pool[~pool['name'].isin(added_names)]
            if pool.empty:
                continue
            weighted_pool = [(nm, (synergy_bonus if mm >= 2 else 1.0)) for nm, mm in zip(pool['name'], pool['_multiMatch'])]
            chosen = bu.weighted_sample_without_replacement(weighted_pool, target)
            for nm in chosen:
                if commander_name and nm == commander_name:
                    continue
                row = pool[pool['name']==nm].iloc[0]
                self.add_card(
                    nm,
                    card_type=row.get('type','Creature'),
                    mana_cost=row.get('manaCost',''),
                    mana_value=row.get('manaValue', row.get('cmc','')),
                    creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                    tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                    role='creature',
                    sub_role=role,
                    added_by='creature_add',
                    trigger_tag=tag,
                    synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
                )
                added_names.append(nm)
                per_theme_added[role].append(nm)
                total_added += 1
                if total_added >= desired_total:
                    break
            self.output_func(f"Added {len(per_theme_added[role])} creatures for {role} theme '{tag}' (target {target}).")
            if total_added >= desired_total:
                break
        if total_added < desired_total:
            need = desired_total - total_added
            multi_pool = creature_df[~creature_df['name'].isin(added_names)].copy()
            multi_pool = multi_pool[multi_pool['_multiMatch'] > 0]
            if not multi_pool.empty:
                if 'edhrecRank' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
                elif 'manaValue' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
                fill = multi_pool['name'].tolist()[:need]
                for nm in fill:
                    if commander_name and nm == commander_name:
                        continue
                    row = multi_pool[multi_pool['name']==nm].iloc[0]
                    self.add_card(
                        nm,
                        card_type=row.get('type','Creature'),
                        mana_cost=row.get('manaCost',''),
                        mana_value=row.get('manaValue', row.get('cmc','')),
                        creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                        tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                        role='creature',
                        sub_role='fill',
                        added_by='creature_fill',
                        synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
                    )
                    added_names.append(nm)
                    total_added += 1
                    if total_added >= desired_total:
                        break
                self.output_func(f"Fill pass added {min(need, len(fill))} extra creatures (shortfall compensation).")
        self.output_func("\nCreatures Added:")
        for role, tag in themes_ordered:
            lst = per_theme_added.get(role, [])
            if lst:
                self.output_func(f"  {role.title()} '{tag}': {len(lst)}")
                for nm in lst:
                    self.output_func(f"    - {nm}")
            else:
                self.output_func(f"  {role.title()} '{tag}': 0")
        self.output_func(f"  Total {total_added}/{desired_total}{' (dataset shortfall)' if total_added < desired_total else ''}")

    def add_creatures_phase(self):
        """Public method for orchestration: delegates to add_creatures.
        Use this as the main entry point for the creature addition phase in deck building.
        """
        """Public method for orchestration: delegates to add_creatures."""
        return self.add_creatures()

    # ---------------------------
    # Per-theme creature sub-stages (for web UI staged confirms)
    # ---------------------------
    def _theme_weights(self, themes_ordered: List[tuple[str, str]]) -> Dict[str, float]:
        n_themes = len(themes_ordered)
        if n_themes == 1:
            base_map = {'primary': 1.0}
        elif n_themes == 2:
            base_map = {'primary': 0.6, 'secondary': 0.4}
        else:
            base_map = {'primary': 0.5, 'secondary': 0.3, 'tertiary': 0.2}
        weights: Dict[str, float] = {}
        boosted_roles: set[str] = set()
        if n_themes > 1:
            for role, tag in themes_ordered:
                w = base_map.get(role, 0.0)
                lt = tag.lower()
                if 'kindred' in lt or 'tribal' in lt:
                    mult = getattr(bc, 'WEIGHT_ADJUSTMENT_FACTORS', {}).get(f'kindred_{role}', 1.0)
                    w *= mult
                    boosted_roles.add(role)
                weights[role] = w
            total = sum(weights.values())
            if total > 1.0:
                for r in list(weights):
                    weights[r] /= total
            else:
                rem = 1.0 - total
                base_sum_unboosted = sum(base_map[r] for r,_t in themes_ordered if r not in boosted_roles)
                if rem > 1e-6 and base_sum_unboosted > 0:
                    for r,_t in themes_ordered:
                        if r not in boosted_roles:
                            weights[r] += rem * (base_map[r] / base_sum_unboosted)
        else:
            weights['primary'] = 1.0
        return weights

    def _creature_count_in_library(self) -> int:
        total = 0
        try:
            for _n, entry in getattr(self, 'card_library', {}).items():
                if str(entry.get('Role') or '').strip() == 'creature':
                    total += int(entry.get('Count', 1))
        except Exception:
            pass
        return total

    def _prepare_creature_pool(self):
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty or 'type' not in df.columns:
            return None
        creature_df = df[df['type'].str.contains('Creature', case=False, na=False)].copy()
        commander_name = getattr(self, 'commander', None) or getattr(self, 'commander_name', None)
        if commander_name and 'name' in creature_df.columns:
            creature_df = creature_df[creature_df['name'] != commander_name]
        if creature_df.empty:
            return None
        if '_parsedThemeTags' not in creature_df.columns:
            creature_df['_parsedThemeTags'] = creature_df['themeTags'].apply(bu.normalize_tag_cell)
        creature_df['_normTags'] = creature_df['_parsedThemeTags']
        selected_tags_lower: List[str] = []
        for t in [getattr(self, 'primary_tag', None), getattr(self, 'secondary_tag', None), getattr(self, 'tertiary_tag', None)]:
            if t:
                selected_tags_lower.append(t.lower())
        creature_df['_multiMatch'] = creature_df['_normTags'].apply(lambda lst: sum(1 for t in selected_tags_lower if t in lst))
        return creature_df

    def _add_creatures_for_role(self, role: str):
        """Add creatures for a single theme role ('primary'|'secondary'|'tertiary')."""
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty:
            self.output_func("Card pool not loaded; cannot add creatures.")
            return
        tag = getattr(self, f'{role}_tag', None)
        if not tag:
            return
        themes_ordered: List[tuple[str, str]] = []
        if getattr(self, 'primary_tag', None):
            themes_ordered.append(('primary', self.primary_tag))
        if getattr(self, 'secondary_tag', None):
            themes_ordered.append(('secondary', self.secondary_tag))
        if getattr(self, 'tertiary_tag', None):
            themes_ordered.append(('tertiary', self.tertiary_tag))
        weights = self._theme_weights(themes_ordered)
        desired_total = (self.ideal_counts.get('creatures') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_CREATURE_COUNT', 25)
        current_added = self._creature_count_in_library()
        remaining = max(0, desired_total - current_added)
        if remaining <= 0:
            return
        w = float(weights.get(role, 0.0))
        if w <= 0:
            return
        import math as _math
        target = int(_math.ceil(desired_total * w * self._get_rng().uniform(1.0, 1.1)))
        target = min(target, remaining)
        if target <= 0:
            return
        creature_df = self._prepare_creature_pool()
        if creature_df is None:
            self.output_func("No creature rows in dataset; skipping.")
            return
        tnorm = str(tag).lower()
        subset = creature_df[creature_df['_normTags'].apply(lambda lst, tn=tnorm: (tn in lst) or any(tn in x for x in lst))]
        if subset.empty:
            self.output_func(f"Theme '{tag}' produced no creature candidates.")
            return
        if 'edhrecRank' in subset.columns:
            subset = subset.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
        elif 'manaValue' in subset.columns:
            subset = subset.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
        base_top = 30
        top_n = int(base_top * getattr(bc, 'THEME_POOL_SIZE_MULTIPLIER', 2.0))
        pool = subset.head(top_n).copy()
        # Exclude any names already chosen
        existing_names = set(getattr(self, 'card_library', {}).keys())
        pool = pool[~pool['name'].isin(existing_names)]
        if pool.empty:
            return
        synergy_bonus = getattr(bc, 'THEME_PRIORITY_BONUS', 1.2)
        weighted_pool = [(nm, (synergy_bonus if mm >= 2 else 1.0)) for nm, mm in zip(pool['name'], pool['_multiMatch'])]
        chosen = bu.weighted_sample_without_replacement(weighted_pool, target)
        added = 0
        for nm in chosen:
            row = pool[pool['name']==nm].iloc[0]
            self.add_card(
                nm,
                card_type=row.get('type','Creature'),
                mana_cost=row.get('manaCost',''),
                mana_value=row.get('manaValue', row.get('cmc','')),
                creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                role='creature',
                sub_role=role,
                added_by='creature_add',
                trigger_tag=tag,
                synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
            )
            added += 1
            if added >= target:
                break
        self.output_func(f"Added {added} creatures for {role} theme '{tag}' (target {target}).")

    def _add_creatures_fill(self):
        desired_total = (self.ideal_counts.get('creatures') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_CREATURE_COUNT', 25)
        current_added = self._creature_count_in_library()
        need = max(0, desired_total - current_added)
        if need <= 0:
            return
        creature_df = self._prepare_creature_pool()
        if creature_df is None:
            return
        multi_pool = creature_df[~creature_df['name'].isin(set(getattr(self, 'card_library', {}).keys()))].copy()
        multi_pool = multi_pool[multi_pool['_multiMatch'] > 0]
        if multi_pool.empty:
            return
        if 'edhrecRank' in multi_pool.columns:
            multi_pool = multi_pool.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
        elif 'manaValue' in multi_pool.columns:
            multi_pool = multi_pool.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
        fill = multi_pool['name'].tolist()[:need]
        added = 0
        for nm in fill:
            row = multi_pool[multi_pool['name']==nm].iloc[0]
            self.add_card(
                nm,
                card_type=row.get('type','Creature'),
                mana_cost=row.get('manaCost',''),
                mana_value=row.get('manaValue', row.get('cmc','')),
                creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                role='creature',
                sub_role='fill',
                added_by='creature_fill',
                synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
            )
            added += 1
            if added >= need:
                break
        if added:
            self.output_func(f"Fill pass added {added} extra creatures (shortfall compensation).")

    # Public stage entry points (web orchestrator looks for these)
    def add_creatures_primary_phase(self):
        return self._add_creatures_for_role('primary')

    def add_creatures_secondary_phase(self):
        return self._add_creatures_for_role('secondary')

    def add_creatures_tertiary_phase(self):
        return self._add_creatures_for_role('tertiary')

    def add_creatures_fill_phase(self):
        return self._add_creatures_fill()
