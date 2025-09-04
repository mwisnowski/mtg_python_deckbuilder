from __future__ import annotations

import math
from typing import List, Dict
import os

from .. import builder_utils as bu
from .. import builder_constants as bc
import logging_util

logger = logging_util.logging.getLogger(__name__)

class SpellAdditionMixin:
    """Phase 4: Non-creature spell additions (ramp, removal, wipes, draw, protection, thematic filler).

    Extracted intact from monolithic builder. Logic intentionally unchanged; future refinements
    (e.g., further per-category sub-mixins) can split this class if complexity grows.
    """

    def _apply_bracket_pre_filters(self, df):
        """Preemptively filter disallowed categories for the current bracket.

        Excludes when bracket limit == 0 for a category:
        - Game Changers
        - Extra Turns
        - Mass Land Denial (MLD)
        - Nonland Tutors
        """
        try:
            if df is None or getattr(df, 'empty', False):
                return df
            limits = getattr(self, 'bracket_limits', {}) or {}
            # Determine which categories are hard-disallowed
            disallow = {
                'game_changers': (limits.get('game_changers') is not None and int(limits.get('game_changers')) == 0),
                'extra_turns': (limits.get('extra_turns') is not None and int(limits.get('extra_turns')) == 0),
                'mass_land_denial': (limits.get('mass_land_denial') is not None and int(limits.get('mass_land_denial')) == 0),
                'tutors_nonland': (limits.get('tutors_nonland') is not None and int(limits.get('tutors_nonland')) == 0),
            }
            if not any(disallow.values()):
                return df
            # Normalize tags helper
            def norm_tags(val):
                try:
                    return [str(t).strip().lower() for t in (val or [])]
                except Exception:
                    return []
            # Build predicate masks only if column exists
            if '_ltags' not in df.columns:
                try:
                    from .. import builder_utils as _bu
                    if 'themeTags' in df.columns:
                        df = df.copy()
                        df['_ltags'] = df['themeTags'].apply(_bu.normalize_tag_cell)
                except Exception:
                    pass
            def has_any(tags, needles):
                return any((nd in t) for t in tags for nd in needles)
            tag_col = '_ltags' if '_ltags' in df.columns else ('themeTags' if 'themeTags' in df.columns else None)
            if not tag_col:
                return df
            # Define synonyms per category
            syn = {
                'game_changers': { 'bracket:gamechanger', 'gamechanger', 'game-changer', 'game changer' },
                'extra_turns': { 'bracket:extraturn', 'extra turn', 'extra turns', 'extraturn' },
                'mass_land_denial': { 'bracket:masslanddenial', 'mass land denial', 'mld', 'masslanddenial' },
                'tutors_nonland': { 'bracket:tutornonland', 'tutor', 'tutors', 'nonland tutor', 'non-land tutor' },
            }
            # Build exclusion mask
            mask_keep = [True] * len(df)
            tags_series = df[tag_col].apply(norm_tags)
            for cat, dis in disallow.items():
                if not dis:
                    continue
                needles = syn.get(cat, set())
                drop_idx = tags_series.apply(lambda lst, nd=needles: any(any(n in t for n in nd) for t in lst))
                # Combine into keep mask
                mask_keep = [mk and (not di) for mk, di in zip(mask_keep, drop_idx.tolist())]
            try:
                import pandas as _pd  # type: ignore
                mask_keep = _pd.Series(mask_keep, index=df.index)
            except Exception:
                pass
            return df[mask_keep]
        except Exception:
            return df

    def _debug_dump_pool(self, df, label: str) -> None:
        """If DEBUG_SPELL_POOLS_WRITE is set, write the pool to logs/pool_{label}_{timestamp}.csv"""
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS_WRITE', '')).strip().lower() not in {"1","true","yes","on"}:
                return
            import os as _os
            from datetime import datetime as _dt
            _os.makedirs('logs', exist_ok=True)
            ts = getattr(self, 'timestamp', _dt.now().strftime('%Y%m%d%H%M%S'))
            path = _os.path.join('logs', f"pool_{label}_{ts}.csv")
            cols = [c for c in ['name','type','manaValue','manaCost','edhrecRank','themeTags'] if c in df.columns]
            try:
                if cols:
                    df[cols].to_csv(path, index=False, encoding='utf-8')
                else:
                    df.to_csv(path, index=False, encoding='utf-8')
            except Exception:
                df.to_csv(path, index=False)
            try:
                self.output_func(f"[DEBUG] Wrote pool CSV: {path} ({len(df)})")
            except Exception:
                pass
        except Exception:
            pass

    # ---------------------------
    # Ramp
    # ---------------------------
    def add_ramp(self):  # noqa: C901
        """Add ramp pieces in three phases: mana rocks (~1/3), mana dorks (~1/4), then general/other.

        Selection is deterministic priority based: lowest edhrecRank then lowest mana value.
        No theme weighting – simple best-available filtering while avoiding duplicates.
        """
        if not self._combined_cards_df is not None:  # preserve original logic
            return
        target_total = self.ideal_counts.get('ramp', 0)
        if target_total <= 0:
            return
        already = {n.lower() for n in self.card_library.keys()}
        df = self._combined_cards_df
        if 'name' not in df.columns:
            return

        work = df.copy()
        work['_ltags'] = work.get('themeTags', []).apply(bu.normalize_tag_cell)
        work = work[work['_ltags'].apply(lambda tags: any('ramp' in t for t in tags))]
        if work.empty:
            self.output_func('No ramp-tagged cards found in dataset.')
            return
        existing_ramp = 0
        for name, entry in self.card_library.items():
            if any(isinstance(t, str) and 'ramp' in t.lower() for t in entry.get('Tags', [])):
                existing_ramp += 1
        to_add, _bonus = bu.compute_adjusted_target('Ramp', target_total, existing_ramp, self.output_func, plural_word='ramp spells')
        if existing_ramp >= target_total and to_add == 0:
            return
        if existing_ramp < target_total:
            target_total = to_add
        else:
            target_total = to_add
        work = work[~work['type'].fillna('').str.contains('Land', case=False, na=False)]
        commander_name = getattr(self, 'commander', None)
        if commander_name:
            work = work[work['name'] != commander_name]
        work = self._apply_bracket_pre_filters(work)
        work = bu.sort_by_priority(work, ['edhrecRank','manaValue'])
        self._debug_dump_pool(work, 'ramp_all')
        # Debug: print ramp pool details
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                names = work['name'].astype(str).head(30).tolist()
                self.output_func(f"[DEBUG][Ramp] Total pool (non-lands): {len(work)}; top {len(names)}: {', '.join(names)}")
        except Exception:
            pass
        # Prefer-owned bias: stable reorder to put owned first while preserving prior sort
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                owned_lower = {str(n).lower() for n in owned_set}
                work = bu.prefer_owned_first(work, owned_lower)

        rocks_target = min(target_total, math.ceil(target_total/3))
        dorks_target = min(target_total - rocks_target, math.ceil(target_total/4))

        added_rocks: List[str] = []
        added_dorks: List[str] = []
        added_general: List[str] = []

        def add_from_pool(pool, remaining_needed, added_list, phase_name):
            added_now = 0
            for _, r in pool.iterrows():
                nm = r['name']
                if nm.lower() in already:
                    continue
                self.add_card(
                    nm,
                    card_type=r.get('type',''),
                    mana_cost=r.get('manaCost',''),
                    mana_value=r.get('manaValue', r.get('cmc','')),
                    tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                    role='ramp',
                    sub_role=phase_name.lower(),
                    added_by='spell_ramp'
                )
                already.add(nm.lower())
                added_list.append(nm)
                added_now += 1
                if added_now >= remaining_needed:
                    break
            if added_now:
                self.output_func(f"Ramp phase {phase_name}: added {added_now}/{remaining_needed} target.")
            return added_now

        rocks_pool = work[work['type'].fillna('').str.contains('Artifact', case=False, na=False)]
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                rnames = rocks_pool['name'].astype(str).head(25).tolist()
                self.output_func(f"[DEBUG][Ramp] Rocks pool: {len(rocks_pool)}; sample: {', '.join(rnames)}")
        except Exception:
            pass
        self._debug_dump_pool(rocks_pool, 'ramp_rocks')
        if rocks_target > 0:
            add_from_pool(rocks_pool, rocks_target, added_rocks, 'Rocks')

        dorks_pool = work[work['type'].fillna('').str.contains('Creature', case=False, na=False)]
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                dnames = dorks_pool['name'].astype(str).head(25).tolist()
                self.output_func(f"[DEBUG][Ramp] Dorks pool: {len(dorks_pool)}; sample: {', '.join(dnames)}")
        except Exception:
            pass
        self._debug_dump_pool(dorks_pool, 'ramp_dorks')
        if dorks_target > 0:
            add_from_pool(dorks_pool, dorks_target, added_dorks, 'Dorks')

        current_total = len(added_rocks) + len(added_dorks)
        remaining = target_total - current_total
        if remaining > 0:
            general_pool = work[~work['name'].isin(added_rocks + added_dorks)]
            try:
                if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                    gnames = general_pool['name'].astype(str).head(25).tolist()
                    self.output_func(f"[DEBUG][Ramp] General pool (remaining): {len(general_pool)}; sample: {', '.join(gnames)}")
            except Exception:
                pass
            self._debug_dump_pool(general_pool, 'ramp_general')
            add_from_pool(general_pool, remaining, added_general, 'General')

        total_added_now = len(added_rocks)+len(added_dorks)+len(added_general)
        self.output_func(f"Total Ramp Added This Pass: {total_added_now}/{target_total}")
        if total_added_now < target_total:
            self.output_func('Ramp shortfall due to limited dataset.')
        if total_added_now:
            self.output_func("Ramp Cards Added:")
            for nm in added_rocks:
                self.output_func(f"  [Rock] {nm}")
            for nm in added_dorks:
                self.output_func(f"  [Dork] {nm}")
            for nm in added_general:
                self.output_func(f"  [General] {nm}")

    # ---------------------------
    # Removal
    # ---------------------------
    def add_removal(self):
        """Add spot removal spells to the deck, avoiding board wipes and lands.
        Selects cards tagged as 'removal' or 'spot removal', prioritizing by EDHREC rank and mana value.
        Avoids duplicates and commander card.
        """
        target = self.ideal_counts.get('removal', 0)
        if target <= 0 or self._combined_cards_df is None:
            return
        already = {n.lower() for n in self.card_library.keys()}
        df = self._combined_cards_df.copy()
        if 'name' not in df.columns:
            return
        df['_ltags'] = df.get('themeTags', []).apply(bu.normalize_tag_cell)
        def is_removal(tags):
            return any('removal' in t or 'spot removal' in t for t in tags)
        def is_wipe(tags):
            return any('board wipe' in t or 'mass removal' in t for t in tags)
        pool = df[df['_ltags'].apply(is_removal) & ~df['_ltags'].apply(is_wipe)]
        pool = pool[~pool['type'].fillna('').str.contains('Land', case=False, na=False)]
        commander_name = getattr(self, 'commander', None)
        if commander_name:
            pool = pool[pool['name'] != commander_name]
        pool = self._apply_bracket_pre_filters(pool)
        pool = bu.sort_by_priority(pool, ['edhrecRank','manaValue'])
        self._debug_dump_pool(pool, 'removal')
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                names = pool['name'].astype(str).head(40).tolist()
                self.output_func(f"[DEBUG][Removal] Pool size: {len(pool)}; top {len(names)}: {', '.join(names)}")
        except Exception:
            pass
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                pool = bu.prefer_owned_first(pool, {str(n).lower() for n in owned_set})
        existing = 0
        for name, entry in self.card_library.items():
            lt = [str(t).lower() for t in entry.get('Tags', [])]
            if any(('removal' in t or 'spot removal' in t) for t in lt) and not any(('board wipe' in t or 'mass removal' in t) for t in lt):
                existing += 1
        to_add, _bonus = bu.compute_adjusted_target('Removal', target, existing, self.output_func, plural_word='removal spells')
        if existing >= target and to_add == 0:
            return
        target = to_add if existing < target else to_add
        added = 0
        added_names: List[str] = []
        for _, r in pool.iterrows():
            if added >= target:
                break
            nm = r['name']
            if nm.lower() in already:
                continue
            self.add_card(
                nm,
                card_type=r.get('type',''),
                mana_cost=r.get('manaCost',''),
                mana_value=r.get('manaValue', r.get('cmc','')),
                tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                role='removal',
                sub_role='spot',
                added_by='spell_removal'
            )
            already.add(nm.lower())
            added += 1
            added_names.append(nm)
        self.output_func(f"Added Spot Removal This Pass: {added}/{target}{' (dataset shortfall)' if added < target else ''}")
        if added_names:
            self.output_func('Removal Cards Added:')
            for nm in added_names:
                self.output_func(f"  - {nm}")

    # ---------------------------
    # Board Wipes
    # ---------------------------
    def add_board_wipes(self):
        """Add board wipe spells to the deck.
        Selects cards tagged as 'board wipe' or 'mass removal', prioritizing by EDHREC rank and mana value.
        Avoids duplicates and commander card.
        """
        target = self.ideal_counts.get('wipes', 0)
        if target <= 0 or self._combined_cards_df is None:
            return
        already = {n.lower() for n in self.card_library.keys()}
        df = self._combined_cards_df.copy()
        df['_ltags'] = df.get('themeTags', []).apply(bu.normalize_tag_cell)
        def is_wipe(tags):
            return any('board wipe' in t or 'mass removal' in t for t in tags)
        pool = df[df['_ltags'].apply(is_wipe)]
        pool = pool[~pool['type'].fillna('').str.contains('Land', case=False, na=False)]
        commander_name = getattr(self, 'commander', None)
        if commander_name:
            pool = pool[pool['name'] != commander_name]
        pool = self._apply_bracket_pre_filters(pool)
        pool = bu.sort_by_priority(pool, ['edhrecRank','manaValue'])
        self._debug_dump_pool(pool, 'wipes')
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                names = pool['name'].astype(str).head(30).tolist()
                self.output_func(f"[DEBUG][Wipes] Pool size: {len(pool)}; sample: {', '.join(names)}")
        except Exception:
            pass
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                pool = bu.prefer_owned_first(pool, {str(n).lower() for n in owned_set})
        existing = 0
        for name, entry in self.card_library.items():
            tags = [str(t).lower() for t in entry.get('Tags', [])]
            if any(('board wipe' in t or 'mass removal' in t) for t in tags):
                existing += 1
        to_add, _bonus = bu.compute_adjusted_target('Board wipe', target, existing, self.output_func, plural_word='wipes')
        if existing >= target and to_add == 0:
            return
        target = to_add if existing < target else to_add
        added = 0
        added_names: List[str] = []
        for _, r in pool.iterrows():
            if added >= target:
                break
            nm = r['name']
            if nm.lower() in already:
                continue
            self.add_card(
                nm,
                card_type=r.get('type',''),
                mana_cost=r.get('manaCost',''),
                mana_value=r.get('manaValue', r.get('cmc','')),
                tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                role='wipe',
                sub_role='board',
                added_by='spell_wipe'
            )
            already.add(nm.lower())
            added += 1
            added_names.append(nm)
        self.output_func(f"Added Board Wipes This Pass: {added}/{target}{' (dataset shortfall)' if added < target else ''}")
        if added_names:
            self.output_func('Board Wipes Added:')
            for nm in added_names:
                self.output_func(f"  - {nm}")

    # ---------------------------
    # Card Advantage
    # ---------------------------
    def add_card_advantage(self):
        """Add card advantage spells to the deck.
        Selects cards tagged as 'draw' or 'card advantage', splits between conditional and unconditional draw.
        Prioritizes by EDHREC rank and mana value, avoids duplicates and commander card.
        """
        total_target = self.ideal_counts.get('card_advantage', 0)
        if total_target <= 0 or self._combined_cards_df is None:
            return
        existing = 0
        for name, entry in self.card_library.items():
            tags = [str(t).lower() for t in entry.get('Tags', [])]
            if any(('draw' in t) or ('card advantage' in t) for t in tags):
                existing += 1
        to_add_total, _bonus = bu.compute_adjusted_target('Card advantage', total_target, existing, self.output_func, plural_word='draw spells')
        if existing >= total_target and to_add_total == 0:
            return
        total_target = to_add_total if existing < total_target else to_add_total
        conditional_target = min(total_target, math.ceil(total_target * 0.2))
        already = {n.lower() for n in self.card_library.keys()}
        df = self._combined_cards_df.copy()
        df['_ltags'] = df.get('themeTags', []).apply(bu.normalize_tag_cell)
        def is_draw(tags):
            return any(('draw' in t) or ('card advantage' in t) for t in tags)
        df = df[df['_ltags'].apply(is_draw)]
        df = self._apply_bracket_pre_filters(df)
        df = df[~df['type'].fillna('').str.contains('Land', case=False, na=False)]
        commander_name = getattr(self, 'commander', None)
        if commander_name:
            df = df[df['name'] != commander_name]
        CONDITIONAL_KEYS = ['conditional', 'situational', 'attacks', 'combat damage', 'when you cast']
        def is_conditional(tags):
            return any(any(k in t for k in CONDITIONAL_KEYS) for t in tags)
        conditional_df = df[df['_ltags'].apply(is_conditional)]
        unconditional_df = df[~df.index.isin(conditional_df.index)]
        def sortit(d):
            return bu.sort_by_priority(d, ['edhrecRank','manaValue'])
        conditional_df = sortit(conditional_df)
        unconditional_df = sortit(unconditional_df)
        self._debug_dump_pool(conditional_df, 'card_advantage_conditional')
        self._debug_dump_pool(unconditional_df, 'card_advantage_unconditional')
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                c_names = conditional_df['name'].astype(str).head(30).tolist()
                u_names = unconditional_df['name'].astype(str).head(30).tolist()
                self.output_func(f"[DEBUG][CardAdv] Total pool: {len(df)}; conditional: {len(conditional_df)}; unconditional: {len(unconditional_df)}")
                if c_names:
                    self.output_func(f"[DEBUG][CardAdv] Conditional sample: {', '.join(c_names)}")
                if u_names:
                    self.output_func(f"[DEBUG][CardAdv] Unconditional sample: {', '.join(u_names)}")
        except Exception:
            pass
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                owned_lower = {str(n).lower() for n in owned_set}
                conditional_df = bu.prefer_owned_first(conditional_df, owned_lower)
                unconditional_df = bu.prefer_owned_first(unconditional_df, owned_lower)
        added_cond = 0
        added_cond_names: List[str] = []
        for _, r in conditional_df.iterrows():
            if added_cond >= conditional_target:
                break
            nm = r['name']
            if nm.lower() in already:
                continue
            self.add_card(
                nm,
                card_type=r.get('type',''),
                mana_cost=r.get('manaCost',''),
                mana_value=r.get('manaValue', r.get('cmc','')),
                tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                role='card_advantage',
                sub_role='conditional',
                added_by='spell_draw'
            )
            already.add(nm.lower())
            added_cond += 1
            added_cond_names.append(nm)
        remaining = total_target - added_cond
        added_uncond = 0
        added_uncond_names: List[str] = []
        if remaining > 0:
            for _, r in unconditional_df.iterrows():
                if added_uncond >= remaining:
                    break
                nm = r['name']
                if nm.lower() in already:
                    continue
                self.add_card(
                    nm,
                    card_type=r.get('type',''),
                    mana_cost=r.get('manaCost',''),
                    mana_value=r.get('manaValue', r.get('cmc','')),
                    tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                    role='card_advantage',
                    sub_role='unconditional',
                    added_by='spell_draw'
                )
                already.add(nm.lower())
                added_uncond += 1
                added_uncond_names.append(nm)
        self.output_func(f"Added Card Advantage This Pass: conditional {added_cond}/{conditional_target}, total {(added_cond+added_uncond)}/{total_target}{' (dataset shortfall)' if (added_cond+added_uncond) < total_target else ''}")
        if added_cond_names or added_uncond_names:
            self.output_func('Card Advantage Cards Added:')
            for nm in added_cond_names:
                self.output_func(f"  [Conditional] {nm}")
            for nm in added_uncond_names:
                self.output_func(f"  [Unconditional] {nm}")

    # ---------------------------
    # Protection
    # ---------------------------
    def add_protection(self):
        """Add protection spells to the deck.
        Selects cards tagged as 'protection', prioritizing by EDHREC rank and mana value.
        Avoids duplicates and commander card.
        """
        target = self.ideal_counts.get('protection', 0)
        if target <= 0 or self._combined_cards_df is None:
            return
        already = {n.lower() for n in self.card_library.keys()}
        df = self._combined_cards_df.copy()
        df['_ltags'] = df.get('themeTags', []).apply(bu.normalize_tag_cell)
        pool = df[df['_ltags'].apply(lambda tags: any('protection' in t for t in tags))]
        pool = pool[~pool['type'].fillna('').str.contains('Land', case=False, na=False)]
        commander_name = getattr(self, 'commander', None)
        if commander_name:
            pool = pool[pool['name'] != commander_name]
        pool = self._apply_bracket_pre_filters(pool)
        pool = bu.sort_by_priority(pool, ['edhrecRank','manaValue'])
        self._debug_dump_pool(pool, 'protection')
        try:
            if str(os.getenv('DEBUG_SPELL_POOLS', '')).strip().lower() in {"1","true","yes","on"}:
                names = pool['name'].astype(str).head(30).tolist()
                self.output_func(f"[DEBUG][Protection] Pool size: {len(pool)}; sample: {', '.join(names)}")
        except Exception:
            pass
        if getattr(self, 'prefer_owned', False):
            owned_set = getattr(self, 'owned_card_names', None)
            if owned_set:
                pool = bu.prefer_owned_first(pool, {str(n).lower() for n in owned_set})
        existing = 0
        for name, entry in self.card_library.items():
            tags = [str(t).lower() for t in entry.get('Tags', [])]
            if any('protection' in t for t in tags):
                existing += 1
        to_add, _bonus = bu.compute_adjusted_target('Protection', target, existing, self.output_func, plural_word='protection spells')
        if existing >= target and to_add == 0:
            return
        target = to_add if existing < target else to_add
        added = 0
        added_names: List[str] = []
        for _, r in pool.iterrows():
            if added >= target:
                break
            nm = r['name']
            if nm.lower() in already:
                continue
            self.add_card(
                nm,
                card_type=r.get('type',''),
                mana_cost=r.get('manaCost',''),
                mana_value=r.get('manaValue', r.get('cmc','')),
                tags=r.get('themeTags', []) if isinstance(r.get('themeTags', []), list) else [],
                role='protection',
                added_by='spell_protection'
            )
            already.add(nm.lower())
            added += 1
            added_names.append(nm)
        self.output_func(f"Added Protection This Pass: {added}/{target}{' (dataset shortfall)' if added < target else ''}")
        if added_names:
            self.output_func('Protection Cards Added:')
            for nm in added_names:
                self.output_func(f"  - {nm}")

    # ---------------------------
    # Theme Spell Filler to 100
    # ---------------------------
    def fill_remaining_theme_spells(self):
        """Fill remaining deck slots with theme spells to reach 100 cards.
        Uses primary, secondary, and tertiary tags to select spells matching deck themes.
        Applies weighted selection and fallback to general utility spells if needed.
        """
        total_cards = sum(entry.get('Count', 1) for entry in self.card_library.values())
        remaining = 100 - total_cards
        if remaining <= 0:
            return
        df = getattr(self, '_combined_cards_df', None)
        if df is None or df.empty or 'type' not in df.columns:
            return
        themes_ordered: List[tuple[str, str]] = []
        if self.primary_tag:
            themes_ordered.append(('primary', self.primary_tag))
        if self.secondary_tag:
            themes_ordered.append(('secondary', self.secondary_tag))
        if self.tertiary_tag:
            themes_ordered.append(('tertiary', self.tertiary_tag))
        if not themes_ordered:
            return
        n_themes = len(themes_ordered)
        if n_themes == 1:
            base_map = {'primary': 1.0}
        elif n_themes == 2:
            base_map = {'primary': 0.6, 'secondary': 0.4}
        else:
            base_map = {'primary': 0.5, 'secondary': 0.3, 'tertiary': 0.2}
        weights: Dict[str, float] = {}
        boosted: set[str] = set()
        if n_themes > 1:
            for role, tag in themes_ordered:
                w = base_map.get(role, 0.0)
                lt = tag.lower()
                if 'kindred' in lt or 'tribal' in lt:
                    mult = getattr(bc, 'WEIGHT_ADJUSTMENT_FACTORS', {}).get(f'kindred_{role}', 1.0)
                    w *= mult
                    boosted.add(role)
                weights[role] = w
            tot = sum(weights.values())
            if tot > 1.0:
                for r in weights:
                    weights[r] /= tot
            else:
                rem = 1.0 - tot
                base_sum_unboosted = sum(base_map[r] for r, _ in themes_ordered if r not in boosted)
                if rem > 1e-6 and base_sum_unboosted > 0:
                    for r, _ in themes_ordered:
                        if r not in boosted:
                            weights[r] += rem * (base_map[r] / base_sum_unboosted)
        else:
            weights['primary'] = 1.0
        spells_df = df[
            ~df['type'].str.contains('Land', case=False, na=False)
            & ~df['type'].str.contains('Creature', case=False, na=False)
        ].copy()
        spells_df = self._apply_bracket_pre_filters(spells_df)
        if spells_df.empty:
            return
        selected_tags_lower = [t.lower() for _r, t in themes_ordered]
        if '_parsedThemeTags' not in spells_df.columns:
            spells_df['_parsedThemeTags'] = spells_df['themeTags'].apply(bu.normalize_tag_cell)
        spells_df['_normTags'] = spells_df['_parsedThemeTags']
        spells_df['_multiMatch'] = spells_df['_normTags'].apply(
            lambda lst: sum(1 for t in selected_tags_lower if t in lst)
        )
        combine_mode = getattr(self, 'tag_mode', 'AND')
        base_top = 40
        top_n = int(base_top * getattr(bc, 'THEME_POOL_SIZE_MULTIPLIER', 2.0))
        synergy_bonus = getattr(bc, 'THEME_PRIORITY_BONUS', 1.2)
        per_theme_added: Dict[str, List[str]] = {r: [] for r, _t in themes_ordered}
        total_added = 0
        for role, tag in themes_ordered:
            if remaining - total_added <= 0:
                break
            w = weights.get(role, 0.0)
            if w <= 0:
                continue
            target = int(math.ceil(remaining * w * self._get_rng().uniform(1.0, 1.1)))
            target = min(target, remaining - total_added)
            if target <= 0:
                continue
            tnorm = tag.lower()
            subset = spells_df[
                spells_df['_normTags'].apply(
                    lambda lst, tn=tnorm: (tn in lst) or any(tn in x for x in lst)
                )
            ]
            if combine_mode == 'AND' and len(selected_tags_lower) > 1:
                if (spells_df['_multiMatch'] >= 2).any():
                    subset = subset[subset['_multiMatch'] >= 2]
            if subset.empty:
                continue
            if 'edhrecRank' in subset.columns:
                subset = subset.sort_values(
                    by=['_multiMatch', 'edhrecRank', 'manaValue'],
                    ascending=[False, True, True],
                    na_position='last',
                )
            elif 'manaValue' in subset.columns:
                subset = subset.sort_values(
                    by=['_multiMatch', 'manaValue'],
                    ascending=[False, True],
                    na_position='last',
                )
            # Prefer-owned: stable reorder before trimming to top_n
            if getattr(self, 'prefer_owned', False):
                owned_set = getattr(self, 'owned_card_names', None)
                if owned_set:
                    subset = bu.prefer_owned_first(subset, {str(n).lower() for n in owned_set})
            pool = subset.head(top_n).copy()
            pool = self._apply_bracket_pre_filters(pool)
            pool = pool[~pool['name'].isin(self.card_library.keys())]
            if pool.empty:
                continue
            # Build weighted pool with optional owned multiplier
            owned_lower = {str(n).lower() for n in getattr(self, 'owned_card_names', set())} if getattr(self, 'prefer_owned', False) else set()
            owned_mult = getattr(bc, 'PREFER_OWNED_WEIGHT_MULTIPLIER', 1.25)
            base_pairs = list(zip(pool['name'], pool['_multiMatch']))
            weighted_pool: list[tuple[str, float]] = []
            if combine_mode == 'AND':
                for nm, mm in base_pairs:
                    base_w = (synergy_bonus*1.3 if mm >= 2 else (1.1 if mm == 1 else 0.8))
                    if owned_lower and str(nm).lower() in owned_lower:
                        base_w *= owned_mult
                    weighted_pool.append((nm, base_w))
            else:
                for nm, mm in base_pairs:
                    base_w = (synergy_bonus if mm >= 2 else 1.0)
                    if owned_lower and str(nm).lower() in owned_lower:
                        base_w *= owned_mult
                    weighted_pool.append((nm, base_w))
            chosen = bu.weighted_sample_without_replacement(weighted_pool, target)
            for nm in chosen:
                row = pool[pool['name'] == nm].iloc[0]
                self.add_card(
                    nm,
                    card_type=row.get('type', ''),
                    mana_cost=row.get('manaCost', ''),
                    mana_value=row.get('manaValue', row.get('cmc', '')),
                    tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                    role='theme_spell',
                    sub_role=role,
                    added_by='spell_theme_fill',
                    trigger_tag=tag,
                    synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
                )
                per_theme_added[role].append(nm)
                total_added += 1
                if total_added >= remaining:
                    break
        if total_added < remaining:
            need = remaining - total_added
            multi_pool = spells_df[~spells_df['name'].isin(self.card_library.keys())].copy()
            multi_pool = self._apply_bracket_pre_filters(multi_pool)
            if combine_mode == 'AND' and len(selected_tags_lower) > 1:
                prioritized = multi_pool[multi_pool['_multiMatch'] >= 2]
                if prioritized.empty:
                    prioritized = multi_pool[multi_pool['_multiMatch'] > 0]
                multi_pool = prioritized
            else:
                multi_pool = multi_pool[multi_pool['_multiMatch'] > 0]
            if not multi_pool.empty:
                if 'edhrecRank' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(
                        by=['_multiMatch', 'edhrecRank', 'manaValue'],
                        ascending=[False, True, True],
                        na_position='last',
                    )
                elif 'manaValue' in multi_pool.columns:
                    multi_pool = multi_pool.sort_values(
                        by=['_multiMatch', 'manaValue'],
                        ascending=[False, True],
                        na_position='last',
                    )
                if getattr(self, 'prefer_owned', False):
                    owned_set = getattr(self, 'owned_card_names', None)
                    if owned_set:
                        multi_pool = bu.prefer_owned_first(multi_pool, {str(n).lower() for n in owned_set})
                fill = multi_pool['name'].tolist()[:need]
                for nm in fill:
                    row = multi_pool[multi_pool['name'] == nm].iloc[0]
                    self.add_card(
                        nm,
                        card_type=row.get('type', ''),
                        mana_cost=row.get('manaCost', ''),
                        mana_value=row.get('manaValue', row.get('cmc', '')),
                        tags=row.get('themeTags', []) if isinstance(row.get('themeTags', []), list) else [],
                        role='theme_spell',
                        sub_role='fill_multi',
                        added_by='spell_theme_fill',
                        synergy=int(row.get('_multiMatch', 0)) if '_multiMatch' in row else None
                    )
                    total_added += 1
                    if total_added >= remaining:
                        break
        if total_added < remaining:
            extra_needed = remaining - total_added
            leftover = spells_df[~spells_df['name'].isin(self.card_library.keys())].copy()
            leftover = self._apply_bracket_pre_filters(leftover)
            if not leftover.empty:
                if '_normTags' not in leftover.columns:
                    leftover['_normTags'] = leftover['themeTags'].apply(
                        lambda x: [str(t).lower() for t in x] if isinstance(x, list) else []
                    )
                def has_any(tag_list, needles):
                    return any(any(nd in t for nd in needles) for t in tag_list)
                def classify(row):
                    tags = row['_normTags']
                    if has_any(tags, ['ramp']):
                        return 'ramp'
                    if has_any(tags, ['card advantage', 'draw']):
                        return 'card_advantage'
                    if has_any(tags, ['protection']):
                        return 'protection'
                    if has_any(tags, ['board wipe', 'mass removal']):
                        return 'board_wipe'
                    if has_any(tags, ['removal']):
                        return 'removal'
                    return ''
                leftover['_fillerCat'] = leftover.apply(classify, axis=1)
                random_added: List[str] = []
                for _ in range(extra_needed):
                    candidates_by_cat: Dict[str, any] = {}
                    for cat in ['ramp','card_advantage','protection','board_wipe','removal']:
                        subset = leftover[leftover['_fillerCat'] == cat]
                        if not subset.empty:
                            candidates_by_cat[cat] = subset
                    if not candidates_by_cat:
                        subset = leftover
                    else:
                        cat_choice = self._get_rng().choice(list(candidates_by_cat.keys()))
                        subset = candidates_by_cat[cat_choice]
                    if 'edhrecRank' in subset.columns:
                        subset = subset.sort_values(by=['edhrecRank','manaValue'], ascending=[True, True], na_position='last')
                    elif 'manaValue' in subset.columns:
                        subset = subset.sort_values(by=['manaValue'], ascending=[True], na_position='last')
                    if getattr(self, 'prefer_owned', False):
                        owned_set = getattr(self, 'owned_card_names', None)
                        if owned_set:
                            subset = bu.prefer_owned_first(subset, {str(n).lower() for n in owned_set})
                    row = subset.head(1)
                    if row.empty:
                        break
                    r0 = row.iloc[0]
                    nm = r0['name']
                    self.add_card(
                        nm,
                        card_type=r0.get('type',''),
                        mana_cost=r0.get('manaCost',''),
                        mana_value=r0.get('manaValue', r0.get('cmc','')),
                        tags=r0.get('themeTags', []) if isinstance(r0.get('themeTags', []), list) else [],
                        role='filler',
                        sub_role=r0.get('_fillerCat',''),
                        added_by='spell_general_filler'
                    )
                    random_added.append(nm)
                    leftover = leftover[leftover['name'] != nm]
                    total_added += 1
                    if total_added >= remaining:
                        break
                if random_added:
                    self.output_func("  General Utility Filler Added:")
                    for nm in random_added:
                        self.output_func(f"    - {nm}")
        if total_added:
            self.output_func("\nFinal Theme Spell Fill:")
            for role, tag in themes_ordered:
                lst = per_theme_added.get(role, [])
                if lst:
                    self.output_func(f"  {role.title()} '{tag}': {len(lst)}")
                    for nm in lst:
                        self.output_func(f"    - {nm}")
            self.output_func(f"  Total Theme Spells Added: {total_added}")

    # ---------------------------
    # Orchestrator
    # ---------------------------
    def add_non_creature_spells(self):
        """Orchestrate addition of all non-creature spell categories and theme filler.
        Calls ramp, removal, board wipes, card advantage, protection, and theme filler methods in order.
        """
        """Convenience orchestrator calling remaining non-creature spell categories then thematic fill."""
        self.add_ramp()
        self.add_removal()
        self.add_board_wipes()
        self.add_card_advantage()
        self.add_protection()
        self.fill_remaining_theme_spells()
        self.print_type_summary()
    
    def add_spells_phase(self):
        """Public method for orchestration: delegates to add_non_creature_spells.
        Use this as the main entry point for the spell addition phase in deck building.
        """
        """Public method for orchestration: delegates to add_non_creature_spells."""
        return self.add_non_creature_spells()
    