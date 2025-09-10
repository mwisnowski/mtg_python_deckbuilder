from __future__ import annotations

from typing import Optional, List, Dict
import os
import csv

from .. import builder_constants as bc
from .. import builder_utils as bu


class LandMiscUtilityMixin:
    """Mixin for Land Building Step 7: Misc / Utility Lands.

    Clean, de-duplicated implementation with:
      - Dynamic EDHREC percent (roll between MIN/MAX for variety)
      - Theme weighting
      - Mono-color rainbow text filtering
      - Exclusion of all fetch lands (fetch step handles them earlier)
      - Diagnostics & CSV exports
    """

    def add_misc_utility_lands(self, requested_count: Optional[int] = None):  # type: ignore[override]
        # --- Initialization & candidate collection ---
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
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and self.ideal_counts:
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)
        basic_floor = self._basic_floor(min_basic_cfg)
        desired = max(0, int(requested_count)) if requested_count is not None else max(0, land_target - current)
        if desired == 0:
            self.output_func("Misc Lands: No remaining land capacity; skipping.")
            return
        basics = self._basic_land_names()
        already = set(self.card_library.keys())
        top_n = getattr(bc, 'MISC_LAND_TOP_POOL_SIZE', 30)
        use_full = getattr(bc, 'MISC_LAND_USE_FULL_POOL', False)
        effective_n = 999999 if use_full else top_n
        top_candidates = bu.select_top_land_candidates(df, already, basics, effective_n)
        # Dynamic EDHREC keep percent
        pct_min = getattr(bc, 'MISC_LAND_EDHREC_KEEP_PERCENT_MIN', None)
        pct_max = getattr(bc, 'MISC_LAND_EDHREC_KEEP_PERCENT_MAX', None)
        if isinstance(pct_min, float) and isinstance(pct_max, float) and 0 < pct_min <= pct_max <= 1:
            rng = getattr(self, 'rng', None)
            keep_pct = rng.uniform(pct_min, pct_max) if rng else (pct_min + pct_max) / 2.0
        else:
            keep_pct = getattr(bc, 'MISC_LAND_EDHREC_KEEP_PERCENT', 1.0)
        if 0 < keep_pct < 1 and top_candidates:
            orig_len = len(top_candidates)
            trimmed_len = max(1, int(orig_len * keep_pct))
            if trimmed_len < orig_len:
                top_candidates = top_candidates[:trimmed_len]
                if getattr(self, 'show_diagnostics', False):
                    self.output_func(f"[Diagnostics] Misc Step EDHREC top% applied: kept {trimmed_len}/{orig_len} (rolled pct={keep_pct:.3f})")
        if use_full and getattr(self, 'show_diagnostics', False):
            self.output_func(f"[Diagnostics] Misc Step using FULL pool (size request={effective_n}, actual candidates={len(top_candidates)})")
        if not top_candidates:
            self.output_func("Misc Lands: No remaining candidate lands.")
            return
        # --- Setup weighting state ---
        base_weight_fix = getattr(bc, 'MISC_LAND_COLOR_FIX_PRIORITY_WEIGHT', 2)
        fetch_names: set[str] = set()
        for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
            for nm in seq:
                fetch_names.add(nm)
        for nm in getattr(bc, 'GENERIC_FETCH_LANDS', []):
            fetch_names.add(nm)
        colors = list(getattr(self, 'color_identity', []) or [])
        mono = len(colors) <= 1
        selected_tags_lower = [t.lower() for t in (getattr(self, 'selected_tags', []) or [])]
        kindred_deck = any('kindred' in t or 'tribal' in t for t in selected_tags_lower)
        mono_exclude = set(getattr(bc, 'MONO_COLOR_MISC_LAND_EXCLUDE', []))
        mono_keep_always = set(getattr(bc, 'MONO_COLOR_MISC_LAND_KEEP_ALWAYS', []))
        kindred_all = set(getattr(bc, 'KINDRED_ALL_LAND_NAMES', []))
        text_rainbow_enabled = getattr(bc, 'MONO_COLOR_EXCLUDE_RAINBOW_TEXT', True)
        extra_rainbow_terms = [s.lower() for s in getattr(bc, 'MONO_COLOR_RAINBOW_TEXT_EXTRA', [])]
        any_color_phrases = [s.lower() for s in getattr(bc, 'ANY_COLOR_MANA_PHRASES', [])]
        weighted_pool: List[tuple[str,int]] = []
        detail_rows: List[Dict[str,str]] = []
        filtered_out: List[str] = []
        considered = 0
        debug_entries: List[tuple[str,int,str]] = []
        dump_pool = getattr(self, 'show_diagnostics', False) or bool(os.getenv('SHOW_MISC_POOL'))
        # Pre-filter export
        debug_enabled = getattr(self, 'show_diagnostics', False) or bool(os.getenv('MISC_LAND_DEBUG'))
        if debug_enabled:
            try:  # pragma: no cover
                os.makedirs(os.path.join('logs','debug'), exist_ok=True)
                cand_path = os.path.join('logs','debug','land_step7_candidates.csv')
                with open(cand_path, 'w', newline='', encoding='utf-8') as fh:
                    wcsv = csv.writer(fh)
                    wcsv.writerow(['name','edhrecRank','type_line','has_color_fixing_terms'])
                    for edh_val, cname, ctline, ctext_lower in top_candidates:
                        wcsv.writerow([cname, edh_val, ctline, int(bu.is_color_fixing_land(ctline, ctext_lower))])
            except Exception:
                pass
        deck_theme_tags = [t.lower() for t in (getattr(self, 'selected_tags', []) or [])]
        theme_enabled = getattr(bc, 'MISC_LAND_THEME_MATCH_ENABLED', True) and bool(deck_theme_tags)
        for edh_val, name, tline, text_lower in top_candidates:
            considered += 1
            note_parts: List[str] = []
            if name in self.card_library:
                note_parts.append('already-added')
            if mono and name in mono_exclude and name not in mono_keep_always and name not in kindred_all:
                filtered_out.append(name)
                detail_rows.append({'name': name,'status':'filtered','reason':'mono-exclude','weight':'0'})
                continue
            if mono and text_rainbow_enabled and name not in mono_keep_always and name not in kindred_all:
                if any(p in text_lower for p in any_color_phrases + extra_rainbow_terms):
                    filtered_out.append(name)
                    detail_rows.append({'name': name,'status':'filtered','reason':'mono-rainbow-text','weight':'0'})
                    continue
            if name == 'The World Tree' and set(colors) != {'W','U','B','R','G'}:
                filtered_out.append(name)
                detail_rows.append({'name': name,'status':'filtered','reason':'world-tree-illegal','weight':'0'})
                continue
            # Exclude all fetch lands entirely in this phase
            if name in fetch_names:
                filtered_out.append(name)
                detail_rows.append({'name': name,'status':'filtered','reason':'fetch-skip-misc','weight':'0'})
                continue
            w = 1
            if bu.is_color_fixing_land(tline, text_lower):
                w *= base_weight_fix
                note_parts.append('fixing')
            if 'already-added' in note_parts:
                w = max(1, int(w * 0.2))
            if (not kindred_deck) and name in kindred_all and name not in mono_keep_always:
                original = w
                w = max(1, int(w * 0.3))
                if w < original:
                    note_parts.append('kindred-down')
            if name == 'Yavimaya, Cradle of Growth' and 'G' not in colors:
                original = w
                w = max(1, int(w * 0.25))
                if w < original:
                    note_parts.append('offcolor-yavimaya')
            if name == 'Urborg, Tomb of Yawgmoth' and 'B' not in colors:
                original = w
                w = max(1, int(w * 0.25))
                if w < original:
                    note_parts.append('offcolor-urborg')
            adj = bu.adjust_misc_land_weight(self, name, w)
            if adj != w:
                note_parts.append('helper-adj')
            w = adj
            if theme_enabled:
                try:
                    crow = df.loc[df['name'] == name].head(1)
                    if not crow.empty and 'themeTags' in crow.columns:
                        raw_tags = crow.iloc[0].get('themeTags', []) or []
                        norm_tags: List[str] = []
                        if isinstance(raw_tags, list):
                            for v in raw_tags:
                                s = str(v).strip().lower()
                                if s:
                                    norm_tags.append(s)
                        elif isinstance(raw_tags, str):
                            rt = raw_tags.lower()
                            for ch in '[]"':
                                rt = rt.replace(ch, ' ')
                            norm_tags = [p.strip().strip("'\"") for p in rt.replace(';', ',').split(',') if p.strip()]
                        matches = [t for t in norm_tags if t in deck_theme_tags]
                        if matches:
                            base_mult = getattr(bc, 'MISC_LAND_THEME_MATCH_BASE', 1.4)
                            per_extra = getattr(bc, 'MISC_LAND_THEME_MATCH_PER_EXTRA', 0.15)
                            cap_mult = getattr(bc, 'MISC_LAND_THEME_MATCH_CAP', 2.0)
                            extra = max(0, len(matches) - 1)
                            mult = base_mult + extra * per_extra
                            if mult > cap_mult:
                                mult = cap_mult
                            themed_w = int(max(1, w * mult))
                            if themed_w != w:
                                w = themed_w
                                note_parts.append(f"theme+{len(matches)}")
                except Exception:
                    pass
            weighted_pool.append((name, w))
            if dump_pool:
                debug_entries.append((name, w, ','.join(note_parts) if note_parts else ''))
            detail_rows.append({'name': name,'status':'kept','reason':','.join(note_parts) if note_parts else '', 'weight':str(w)})
        if dump_pool:
            debug_entries.sort(key=lambda x: (-x[1], x[0]))
            self.output_func("\nMisc Lands Pool (post-filter, top {} shown):".format(len(debug_entries)))
            width = max((len(n) for n,_,_ in debug_entries), default=0)
            for n, w, notes in debug_entries[:80]:
                suffix = f" [{notes}]" if notes else ''
                self.output_func(f"  {n.ljust(width)}  w={w}{suffix}")
        if debug_enabled:
            try:  # pragma: no cover
                os.makedirs(os.path.join('logs','debug'), exist_ok=True)
                detail_path = os.path.join('logs','debug','land_step7_postfilter.csv')
                kept = [r for r in detail_rows if r['status']=='kept']
                filt = [r for r in detail_rows if r['status']=='filtered']
                other = [r for r in detail_rows if r['status'] not in {'kept','filtered'}]
                if detail_rows:
                    kept.sort(key=lambda r: (-int(r.get('weight','1')), r['name']))
                    ordered = kept + filt + other
                    with open(detail_path,'w',newline='',encoding='utf-8') as fh:
                        wcsv = csv.writer(fh)
                        wcsv.writerow(['name','status','reason','weight'])
                        for r in ordered:
                            wcsv.writerow([r['name'], r['status'], r.get('reason',''), r.get('weight','')])
            except Exception:
                pass
        if getattr(self, 'show_diagnostics', False):
            self.output_func(f"Misc Lands Debug: considered={considered} kept={len(weighted_pool)} filtered={len(filtered_out)}")
        # Capacity adjustment (trim basics if needed)
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
            self.add_card(nm, card_type='Land', role='utility', sub_role='misc', added_by='lands_step7')
            added.append(nm)
        if debug_enabled:
            try:  # pragma: no cover
                os.makedirs(os.path.join('logs','debug'), exist_ok=True)
                final_path = os.path.join('logs','debug','land_step7_final_selection.csv')
                with open(final_path,'w',newline='',encoding='utf-8') as fh:
                    wcsv = csv.writer(fh)
                    wcsv.writerow(['name','weight','selected','reason'])
                    reason_map = {r['name']:(r.get('weight',''), r.get('reason','')) for r in detail_rows if r['status']=='kept'}
                    chosen_set = set(added)
                    for name, w in weighted_pool:
                        wt, rsn = reason_map.get(name,(str(w),''))
                        wcsv.writerow([name, wt, 1 if name in chosen_set else 0, rsn])
                    wcsv.writerow([])
                    wcsv.writerow(['__meta__','desired', desired])
                    wcsv.writerow(['__meta__','pool_size', len(weighted_pool)])
                    wcsv.writerow(['__meta__','considered', considered])
                    wcsv.writerow(['__meta__','filtered_out', len(filtered_out)])
            except Exception:
                pass
        self.output_func("\nMisc Utility Lands Added (Step 7):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                note = ''
                for edh_val, name2, tline2, text_lower2 in top_candidates:
                    if name2 == n and bu.is_color_fixing_land(tline2, text_lower2):
                        note = '(fixing)'
                        break
                self.output_func(f"  {n.ljust(width)} : 1  {note}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")
        if getattr(self, 'show_diagnostics', False) and filtered_out:
            self.output_func(f"  (Excluded candidates: {', '.join(filtered_out)})")
            width = max(len(n) for n in added)
            for n in added:
                note = ''
                for edh_val, name2, tline2, text_lower2 in top_candidates:
                    if name2 == n and bu.is_color_fixing_land(tline2, text_lower2):
                        note = '(fixing)'
                        break
                self.output_func(f"  {n.ljust(width)} : 1  {note}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")
        if getattr(self, 'show_diagnostics', False) and filtered_out:
            self.output_func(f"  (Mono-color excluded candidates: {', '.join(filtered_out)})")

    def run_land_step7(self, requested_count: Optional[int] = None):  # type: ignore[override]
        self.add_misc_utility_lands(requested_count=requested_count)
        self._enforce_land_cap(step_label="Utility (Step 7)")
        self._build_tag_driven_land_suggestions()
        self._apply_land_suggestions_if_room()
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '7')
        except Exception:
            pass

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
