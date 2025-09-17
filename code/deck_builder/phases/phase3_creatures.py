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
        combine_mode = getattr(self, 'tag_mode', 'AND')
        base_top = 30
        top_n = int(base_top * getattr(bc, 'THEME_POOL_SIZE_MULTIPLIER', 2.0))
        synergy_bonus = getattr(bc, 'THEME_PRIORITY_BONUS', 1.2)
        total_added = 0
        added_names: List[str] = []
        # AND pre-pass: pick creatures that hit all selected themes first (if 2+ themes)
        all_theme_added: List[tuple[str, List[str]]] = []
        if combine_mode == 'AND' and len(selected_tags_lower) >= 2:
            all_cnt = len(selected_tags_lower)
            pre_cap_ratio = getattr(bc, 'AND_ALL_THEME_CAP_RATIO', 0.6)
            hard_cap = max(0, int(math.floor(desired_total * float(pre_cap_ratio))))
            remaining_capacity = max(0, desired_total - total_added)
            target_cap = min(hard_cap if hard_cap > 0 else remaining_capacity, remaining_capacity)
            if target_cap > 0:
                subset_all = creature_df[creature_df['_multiMatch'] >= all_cnt].copy()
                subset_all = subset_all[~subset_all['name'].isin(added_names)]
                if not subset_all.empty:
                    if 'edhrecRank' in subset_all.columns:
                        subset_all = subset_all.sort_values(by=['edhrecRank','manaValue'], ascending=[True, True], na_position='last')
                    elif 'manaValue' in subset_all.columns:
                        subset_all = subset_all.sort_values(by=['manaValue'], ascending=[True], na_position='last')
                    # Bias owned names ahead before weighting
                    if getattr(self, 'prefer_owned', False):
                        owned_set = getattr(self, 'owned_card_names', None)
                        if owned_set:
                            subset_all = bu.prefer_owned_first(subset_all, {str(n).lower() for n in owned_set})
                    weight_strong = getattr(bc, 'AND_ALL_THEME_WEIGHT', 1.7)
                    owned_lower = {str(n).lower() for n in getattr(self, 'owned_card_names', set())} if getattr(self, 'prefer_owned', False) else set()
                    owned_mult = getattr(bc, 'PREFER_OWNED_WEIGHT_MULTIPLIER', 1.25)
                    weighted_pool = []
                    for nm in subset_all['name'].tolist():
                        w = weight_strong
                        if owned_lower and str(nm).lower() in owned_lower:
                            w *= owned_mult
                        weighted_pool.append((nm, w))
                    chosen_all = bu.weighted_sample_without_replacement(weighted_pool, target_cap, rng=getattr(self, 'rng', None))
                    for nm in chosen_all:
                        if commander_name and nm == commander_name:
                            continue
                        row = subset_all[subset_all['name'] == nm].iloc[0]
                        # Which selected themes does this card hit?
                        selected_display_tags = [t for _r, t in themes_ordered]
                        norm_tags = row.get('_normTags', []) if isinstance(row.get('_normTags', []), list) else []
                        try:
                            hits = [t for t in selected_display_tags if str(t).lower() in norm_tags]
                        except Exception:
                            hits = selected_display_tags
                        self.add_card(
                            nm,
                            card_type=row.get('type','Creature'),
                            mana_cost=row.get('manaCost',''),
                            mana_value=row.get('manaValue', row.get('cmc','')),
                            creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                            tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                            role='creature',
                            sub_role='all_theme',
                            added_by='creature_all_theme',
                            trigger_tag=", ".join(hits) if hits else None,
                            synergy=int(row.get('_multiMatch', all_cnt)) if '_multiMatch' in row else all_cnt
                        )
                        added_names.append(nm)
                        all_theme_added.append((nm, hits))
                        total_added += 1
                        if total_added >= desired_total:
                            break
                    self.output_func(f"All-Theme AND Pre-Pass: added {len(all_theme_added)} / {target_cap} (matching all {all_cnt} themes)")
        # Per-theme distribution
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
            if combine_mode == 'AND' and len(selected_tags_lower) > 1:
                if (creature_df['_multiMatch'] >= 2).any():
                    subset = subset[subset['_multiMatch'] >= 2]
            if subset.empty:
                self.output_func(f"Theme '{tag}' produced no creature candidates.")
                continue
            if 'edhrecRank' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
            elif 'manaValue' in subset.columns:
                subset = subset.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
            if getattr(self, 'prefer_owned', False):
                owned_set = getattr(self, 'owned_card_names', None)
                if owned_set:
                    subset = bu.prefer_owned_first(subset, {str(n).lower() for n in owned_set})
            pool = subset.head(top_n).copy()
            pool = pool[~pool['name'].isin(added_names)]
            if pool.empty:
                continue
            owned_lower = {str(n).lower() for n in getattr(self, 'owned_card_names', set())} if getattr(self, 'prefer_owned', False) else set()
            owned_mult = getattr(bc, 'PREFER_OWNED_WEIGHT_MULTIPLIER', 1.25)
            if combine_mode == 'AND':
                weighted_pool = []
                for nm, mm in zip(pool['name'], pool['_multiMatch']):
                    base_w = (synergy_bonus*1.3 if mm >= 2 else (1.1 if mm == 1 else 0.8))
                    if owned_lower and str(nm).lower() in owned_lower:
                        base_w *= owned_mult
                    weighted_pool.append((nm, base_w))
            else:
                weighted_pool = []
                for nm, mm in zip(pool['name'], pool['_multiMatch']):
                    base_w = (synergy_bonus if mm >= 2 else 1.0)
                    if owned_lower and str(nm).lower() in owned_lower:
                        base_w *= owned_mult
                    weighted_pool.append((nm, base_w))
            chosen = bu.weighted_sample_without_replacement(weighted_pool, target, rng=getattr(self, 'rng', None))
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
        # Fill remaining if still short
        if total_added < desired_total:
            need = desired_total - total_added
            multi_pool = creature_df[~creature_df['name'].isin(added_names)].copy()
            if combine_mode == 'AND' and len(selected_tags_lower) > 1:
                prioritized = multi_pool[multi_pool['_multiMatch'] >= 2]
                if prioritized.empty:
                    prioritized = multi_pool[multi_pool['_multiMatch'] > 0]
                multi_pool = prioritized
            else:
                multi_pool = multi_pool[multi_pool['_multiMatch'] > 0]
            if not multi_pool.empty:
                if 'edhrecRank' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','edhrecRank','manaValue'], ascending=[False, True, True], na_position='last')
                elif 'manaValue' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(by=['_multiMatch','manaValue'], ascending=[False, True], na_position='last')
                if getattr(self, 'prefer_owned', False):
                    owned_set = getattr(self, 'owned_card_names', None)
                    if owned_set:
                        multi_pool = bu.prefer_owned_first(multi_pool, {str(n).lower() for n in owned_set})
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
        # Summary output
        self.output_func("\nCreatures Added:")
        if all_theme_added:
            self.output_func(f"  All-Theme overlap: {len(all_theme_added)}")
            for nm, hits in all_theme_added:
                if hits:
                    self.output_func(f"    - {nm} (tags: {', '.join(hits)})")
                else:
                    self.output_func(f"    - {nm}")
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
            lib = getattr(self, 'card_library', {}) or {}
            for name, entry in lib.items():
                # Skip the commander from creature counts to preserve historical behavior
                try:
                    if bool(entry.get('Commander')):
                        continue
                except Exception:
                    pass
                is_creature = False
                # Prefer explicit Card Type recorded on the entry
                try:
                    ctype = str(entry.get('Card Type') or '')
                    if ctype:
                        is_creature = ('creature' in ctype.lower())
                except Exception:
                    is_creature = False
                # Fallback: look up type from the combined dataframe snapshot
                if not is_creature:
                    try:
                        df = getattr(self, '_combined_cards_df', None)
                        if df is not None and not getattr(df, 'empty', True) and 'name' in df.columns:
                            row = df[df['name'].astype(str).str.lower() == str(name).strip().lower()]
                            if not row.empty:
                                tline = str(row.iloc[0].get('type', row.iloc[0].get('type_line', '')) or '')
                                if 'creature' in tline.lower():
                                    is_creature = True
                    except Exception:
                        pass
                if is_creature:
                    try:
                        total += int(entry.get('Count', 1))
                    except Exception:
                        total += 1
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
        # Apply bracket-based pre-filters (e.g., disallow game changers or tutors when bracket limit == 0)
        creature_df = self._apply_bracket_pre_filters(creature_df)
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

    def _apply_bracket_pre_filters(self, df):
        """Preemptively filter disallowed categories for the current bracket for creatures.

        Excludes when bracket limit == 0 for a category:
        - Game Changers
        - Nonland Tutors

        Note: Extra Turns and Mass Land Denial generally don't apply to creature cards,
        but if present as tags, they'll be respected too.
        """
        try:
            if df is None or getattr(df, 'empty', False):
                return df
            limits = getattr(self, 'bracket_limits', {}) or {}
            disallow = {
                'game_changers': (limits.get('game_changers') is not None and int(limits.get('game_changers')) == 0),
                'tutors_nonland': (limits.get('tutors_nonland') is not None and int(limits.get('tutors_nonland')) == 0),
                'extra_turns': (limits.get('extra_turns') is not None and int(limits.get('extra_turns')) == 0),
                'mass_land_denial': (limits.get('mass_land_denial') is not None and int(limits.get('mass_land_denial')) == 0),
            }
            if not any(disallow.values()):
                return df
            def norm_tags(val):
                try:
                    return [str(t).strip().lower() for t in (val or [])]
                except Exception:
                    return []
            if '_ltags' not in df.columns:
                try:
                    if 'themeTags' in df.columns:
                        df = df.copy()
                        df['_ltags'] = df['themeTags'].apply(bu.normalize_tag_cell)
                except Exception:
                    pass
            tag_col = '_ltags' if '_ltags' in df.columns else ('themeTags' if 'themeTags' in df.columns else None)
            if not tag_col:
                return df
            syn = {
                'game_changers': { 'bracket:gamechanger', 'gamechanger', 'game-changer', 'game changer' },
                'tutors_nonland': { 'bracket:tutornonland', 'tutor', 'tutors', 'nonland tutor', 'non-land tutor' },
                'extra_turns': { 'bracket:extraturn', 'extra turn', 'extra turns', 'extraturn' },
                'mass_land_denial': { 'bracket:masslanddenial', 'mass land denial', 'mld', 'masslanddenial' },
            }
            tags_series = df[tag_col].apply(norm_tags)
            mask_keep = [True] * len(df)
            for cat, dis in disallow.items():
                if not dis:
                    continue
                needles = syn.get(cat, set())
                drop_idx = tags_series.apply(lambda lst, nd=needles: any(any(n in t for n in nd) for t in lst))
                mask_keep = [mk and (not di) for mk, di in zip(mask_keep, drop_idx.tolist())]
            try:
                import pandas as _pd  # type: ignore
                mask_keep = _pd.Series(mask_keep, index=df.index)
            except Exception:
                pass
            return df[mask_keep]
        except Exception:
            return df

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
        chosen = bu.weighted_sample_without_replacement(weighted_pool, target, rng=getattr(self, 'rng', None))
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

    def add_creatures_all_theme_phase(self):
        """Staged pre-pass: when AND mode and 2+ tags, add creatures matching all selected themes first."""
        combine_mode = getattr(self, 'tag_mode', 'AND')
        tags = [t for t in [getattr(self, 'primary_tag', None), getattr(self, 'secondary_tag', None), getattr(self, 'tertiary_tag', None)] if t]
        if combine_mode != 'AND' or len(tags) < 2:
            return
        desired_total = (self.ideal_counts.get('creatures') if getattr(self, 'ideal_counts', None) else None) or getattr(bc, 'DEFAULT_CREATURE_COUNT', 25)
        current_added = self._creature_count_in_library()
        remaining_capacity = max(0, desired_total - current_added)
        if remaining_capacity <= 0:
            return
        creature_df = self._prepare_creature_pool()
        if creature_df is None or creature_df.empty:
            return
        all_cnt = len(tags)
        pre_cap_ratio = getattr(bc, 'AND_ALL_THEME_CAP_RATIO', 0.6)
        hard_cap = max(0, int(math.floor(desired_total * float(pre_cap_ratio))))
        target_cap = min(hard_cap if hard_cap > 0 else remaining_capacity, remaining_capacity)
        subset_all = creature_df[creature_df['_multiMatch'] >= all_cnt].copy()
        existing_names = set(getattr(self, 'card_library', {}).keys())
        subset_all = subset_all[~subset_all['name'].isin(existing_names)]
        if subset_all.empty or target_cap <= 0:
            return
        if 'edhrecRank' in subset_all.columns:
            subset_all = subset_all.sort_values(by=['edhrecRank','manaValue'], ascending=[True, True], na_position='last')
        elif 'manaValue' in subset_all.columns:
            subset_all = subset_all.sort_values(by=['manaValue'], ascending=[True], na_position='last')
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                subset_all = bu.prefer_owned_first(subset_all, {str(n).lower() for n in owned_set})
        weight_strong = getattr(bc, 'AND_ALL_THEME_WEIGHT', 1.7)
        owned_lower = {str(n).lower() for n in getattr(self, 'owned_card_names', set())} if getattr(self, 'prefer_owned', False) else set()
        owned_mult = getattr(bc, 'PREFER_OWNED_WEIGHT_MULTIPLIER', 1.25)
        weighted_pool = []
        for nm in subset_all['name'].tolist():
            w = weight_strong
            if owned_lower and str(nm).lower() in owned_lower:
                w *= owned_mult
            weighted_pool.append((nm, w))
        chosen_all = bu.weighted_sample_without_replacement(weighted_pool, target_cap, rng=getattr(self, 'rng', None))
        added = 0
        for nm in chosen_all:
            row = subset_all[subset_all['name'] == nm].iloc[0]
            # Determine which selected themes this card hits for display
            norm_tags = row.get('_normTags', []) if isinstance(row.get('_normTags', []), list) else []
            hits: List[str] = []
            try:
                hits = [t for t in tags if str(t).lower() in norm_tags]
            except Exception:
                hits = list(tags)
            self.add_card(
                nm,
                card_type=row.get('type','Creature'),
                mana_cost=row.get('manaCost',''),
                mana_value=row.get('manaValue', row.get('cmc','')),
                creature_types=row.get('creatureTypes', []) if isinstance(row.get('creatureTypes', []), list) else [],
                tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                role='creature',
                sub_role='all_theme',
                added_by='creature_all_theme',
                trigger_tag=", ".join(hits) if hits else None,
                synergy=int(row.get('_multiMatch', all_cnt)) if '_multiMatch' in row else all_cnt
            )
            added += 1
            if added >= target_cap:
                break
        if added:
            self.output_func(f"All-Theme AND Pre-Pass: added {added}/{target_cap} creatures (matching all {all_cnt} themes)")
