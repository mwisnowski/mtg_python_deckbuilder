from __future__ import annotations

from typing import Dict, List
import csv
import os
import datetime as _dt
import re as _re
import logging_util

logger = logging_util.logging.getLogger(__name__)

try:
    from prettytable import PrettyTable  # type: ignore
except Exception:  # pragma: no cover
    PrettyTable = None  # type: ignore

class ReportingMixin:
    def run_reporting_phase(self):
        """Public method for orchestration: delegates to print_type_summary and print_card_library.
            def export_decklist_text(self, directory: str = 'deck_files', filename: str | None = None, suppress_output: bool = False) -> str:
            def export_decklist_text(self, directory: str = 'deck_files', filename: str | None = None, suppress_output: bool = False) -> str:
        Use this as the main entry point for the reporting phase in deck building.
        """
        """Public method for orchestration: delegates to print_type_summary and print_card_library."""
        self.print_type_summary()
        self.print_card_library(table=True)
    """Phase 6: Reporting, summaries, and export helpers."""

    def enforce_and_reexport(self, base_stem: str | None = None, mode: str = "prompt") -> dict:
        """Run bracket enforcement, then re-export CSV/TXT and recompute compliance.

        mode: 'prompt' for CLI interactive; 'auto' for headless/web.
        Returns the final compliance report dict.
        """
        try:
            # Lazy import to avoid cycles
            from deck_builder.enforcement import enforce_bracket_compliance  # type: ignore
        except Exception:
            self.output_func("Enforcement module unavailable.")
            return {}

        # Enforce
        report = enforce_bracket_compliance(self, mode=mode)
        # If enforcement removed cards without enough replacements, top up to 100 using theme filler
        try:
            total_cards = 0
            for _n, _e in getattr(self, 'card_library', {}).items():
                try:
                    total_cards += int(_e.get('Count', 1))
                except Exception:
                    total_cards += 1
            if int(total_cards) < 100 and hasattr(self, 'fill_remaining_theme_spells'):
                before = int(total_cards)
                try:
                    self.fill_remaining_theme_spells()  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Recompute after filler
                try:
                    total_cards = 0
                    for _n, _e in getattr(self, 'card_library', {}).items():
                        try:
                            total_cards += int(_e.get('Count', 1))
                        except Exception:
                            total_cards += 1
                except Exception:
                    total_cards = before
                try:
                    self.output_func(f"Topped up deck to {total_cards}/100 after enforcement.")
                except Exception:
                    pass
        except Exception:
            pass
        # Print what changed
        try:
            enf = report.get('enforcement') or {}
            removed = list(enf.get('removed') or [])
            added = list(enf.get('added') or [])
            if removed or added:
                self.output_func("\nEnforcement Summary (swaps):")
                if removed:
                    self.output_func("Removed:")
                    for n in removed:
                        self.output_func(f"  - {n}")
                if added:
                    self.output_func("Added:")
                    for n in added:
                        self.output_func(f"  + {n}")
        except Exception:
            pass
        # Re-export using same base, if provided
        try:
            import os as _os
            import json as _json
            if isinstance(base_stem, str) and base_stem.strip():
                # Mirror CSV/TXT export naming
                csv_name = base_stem + ".csv"
                txt_name = base_stem + ".txt"
                # Overwrite exports with updated library
                self.export_decklist_csv(directory='deck_files', filename=csv_name, suppress_output=True)  # type: ignore[attr-defined]
                self.export_decklist_text(directory='deck_files', filename=txt_name, suppress_output=True)  # type: ignore[attr-defined]
                # Re-export the JSON config to reflect any changes from enforcement
                json_name = base_stem + ".json"
                self.export_run_config_json(directory='config', filename=json_name, suppress_output=True)  # type: ignore[attr-defined]
                # Recompute and write compliance next to them
                self.compute_and_print_compliance(base_stem=base_stem)  # type: ignore[attr-defined]
                # Inject enforcement details into the saved compliance JSON for UI transparency
                comp_path = _os.path.join('deck_files', f"{base_stem}_compliance.json")
                try:
                    if _os.path.exists(comp_path) and isinstance(report, dict) and report.get('enforcement'):
                        with open(comp_path, 'r', encoding='utf-8') as _f:
                            comp_obj = _json.load(_f)
                        comp_obj['enforcement'] = report.get('enforcement')
                        with open(comp_path, 'w', encoding='utf-8') as _f:
                            _json.dump(comp_obj, _f, indent=2)
                except Exception:
                    pass
            else:
                # Fall back to default export flow
                csv_path = self.export_decklist_csv()  # type: ignore[attr-defined]
                try:
                    base, _ = _os.path.splitext(csv_path)
                    base_only = _os.path.basename(base)
                except Exception:
                    base_only = None
                self.export_decklist_text(filename=(base_only + '.txt') if base_only else None)  # type: ignore[attr-defined]
                # Re-export JSON config after enforcement changes
                if base_only:
                    self.export_run_config_json(directory='config', filename=base_only + '.json', suppress_output=True)  # type: ignore[attr-defined]
                if base_only:
                    self.compute_and_print_compliance(base_stem=base_only)  # type: ignore[attr-defined]
                    # Inject enforcement into written JSON as above
                    try:
                        comp_path = _os.path.join('deck_files', f"{base_only}_compliance.json")
                        if _os.path.exists(comp_path) and isinstance(report, dict) and report.get('enforcement'):
                            with open(comp_path, 'r', encoding='utf-8') as _f:
                                comp_obj = _json.load(_f)
                            comp_obj['enforcement'] = report.get('enforcement')
                            with open(comp_path, 'w', encoding='utf-8') as _f:
                                _json.dump(comp_obj, _f, indent=2)
                    except Exception:
                        pass
        except Exception:
            pass
        return report

    def compute_and_print_compliance(self, base_stem: str | None = None) -> dict:
        """Compute bracket compliance, print a compact summary, and optionally write a JSON report.

        If base_stem is provided, writes deck_files/{base_stem}_compliance.json.
        Returns the compliance report dict.
        """
        try:
            # Late import to avoid circulars in some environments
            from deck_builder.brackets_compliance import evaluate_deck  # type: ignore
        except Exception:
            self.output_func("Bracket compliance module unavailable.")
            return {}

        try:
            bracket_key = str(getattr(self, 'bracket_name', '') or getattr(self, 'bracket_level', 'core')).lower()
            commander = getattr(self, 'commander_name', None)
            report = evaluate_deck(self.card_library, commander_name=commander, bracket=bracket_key)
        except Exception as e:
            self.output_func(f"Compliance evaluation failed: {e}")
            return {}

        # Print concise summary
        try:
            self.output_func("\nBracket Compliance:")
            self.output_func(f"  Overall: {report.get('overall', 'PASS')}")
            cats = report.get('categories', {}) or {}
            order = [
                ('game_changers', 'Game Changers'),
                ('mass_land_denial', 'Mass Land Denial'),
                ('extra_turns', 'Extra Turns'),
                ('tutors_nonland', 'Nonland Tutors'),
                ('two_card_combos', 'Two-Card Combos'),
            ]
            for key, label in order:
                c = cats.get(key, {}) or {}
                cnt = int(c.get('count', 0) or 0)
                lim = c.get('limit')
                status = str(c.get('status') or 'PASS')
                lim_txt = ('Unlimited' if lim is None else str(int(lim)))
                self.output_func(f"  {label:<16} {cnt} / {lim_txt}  [{status}]")
        except Exception:
            pass

        # Optionally write JSON report next to exports
        if isinstance(base_stem, str) and base_stem.strip():
            try:
                import os as _os
                _os.makedirs('deck_files', exist_ok=True)
                path = _os.path.join('deck_files', f"{base_stem}_compliance.json")
                import json as _json
                with open(path, 'w', encoding='utf-8') as f:
                    _json.dump(report, f, indent=2)
                self.output_func(f"Compliance report saved to {path}")
            except Exception:
                pass

        return report

    def _wrap_cell(self, text: str, width: int = 28) -> str:
        """Wraps a string to a specified width for table display.
        Used for pretty-printing card names, roles, and tags in tabular output.
        """
        words = text.split()
        lines: List[str] = []
        current_line = []
        current_len = 0
        for w in words:
            if current_len + len(w) + (1 if current_line else 0) > width:
                lines.append(' '.join(current_line))
                current_line = [w]
                current_len = len(w)
            else:
                current_line.append(w)
                current_len += len(w) + (1 if len(current_line) > 1 else 0)
        if current_line:
            lines.append(' '.join(current_line))
        return '\n'.join(lines)

    def print_type_summary(self):
        """Print a type/category distribution for the current deck library.
        Uses the stored 'Card Type' when available; otherwise enriches from the
        loaded card snapshot. Categories mirror export classification.
        """
        # Build a quick lookup from the loaded dataset to enrich type lines
        full_df = getattr(self, '_full_cards_df', None)
        combined_df = getattr(self, '_combined_cards_df', None)
        snapshot = full_df if full_df is not None else combined_df
        row_lookup: Dict[str, any] = {}
        if snapshot is not None and hasattr(snapshot, 'empty') and not snapshot.empty and 'name' in snapshot.columns:
            for _, r in snapshot.iterrows():
                nm = str(r.get('name'))
                if nm not in row_lookup:
                    row_lookup[nm] = r

        # Category precedence (purely for stable sorted output)
        precedence_order = [
            'Commander', 'Battle', 'Planeswalker', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land', 'Other'
        ]
        precedence_index = {k: i for i, k in enumerate(precedence_order)}
        commander_name = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''

        def classify(primary_type_line: str, card_name: str) -> str:
            if commander_name and card_name == commander_name:
                return 'Commander'
            tl = (primary_type_line or '').lower()
            if 'battle' in tl:
                return 'Battle'
            if 'planeswalker' in tl:
                return 'Planeswalker'
            if 'creature' in tl:
                return 'Creature'
            if 'instant' in tl:
                return 'Instant'
            if 'sorcery' in tl:
                return 'Sorcery'
            if 'artifact' in tl:
                return 'Artifact'
            if 'enchantment' in tl:
                return 'Enchantment'
            if 'land' in tl:
                return 'Land'
            return 'Other'

        # Count by classified category
        cat_counts: Dict[str, int] = {}
        for name, info in self.card_library.items():
            base_type = info.get('Card Type') or info.get('Type', '')
            if not base_type:
                row = row_lookup.get(name)
                if row is not None:
                    base_type = row.get('type', row.get('type_line', '')) or ''
            category = classify(base_type, name)
            cnt = int(info.get('Count', 1))
            cat_counts[category] = cat_counts.get(category, 0) + cnt

        total_cards = sum(cat_counts.values())
        self.output_func("\nType Summary:")
        for cat, c in sorted(cat_counts.items(), key=lambda kv: (precedence_index.get(kv[0], 999), -kv[1], kv[0])):
            pct = (c / total_cards * 100) if total_cards else 0.0
            self.output_func(f"  {cat:<15} {c:>3}  ({pct:5.1f}%)")

    # ---------------------------
    # Structured deck summary for UI (types, pips, sources, curve)
    # ---------------------------
    def build_deck_summary(self) -> dict:
        """Return a structured summary of the finished deck for UI rendering.

        Structure:
        {
          'type_breakdown': {
             'counts': { type: count, ... },
             'order': [sorted types by precedence],
             'cards': { type: [ {name, count}, ... ] },
             'total': int
          },
          'pip_distribution': {
             'counts': { 'W': n, 'U': n, 'B': n, 'R': n, 'G': n },
             'weights': { 'W': 0-1, ... },  # normalized weights (may not sum exactly to 1 due to rounding)
          },
          'mana_generation': { 'W': n, 'U': n, 'B': n, 'R': n, 'G': n, 'total_sources': n },
          'mana_curve': { '0': n, '1': n, '2': n, '3': n, '4': n, '5': n, '6+': n, 'total_spells': n }
        }
        """
        # Build lookup to enrich type and mana values
        full_df = getattr(self, '_full_cards_df', None)
        combined_df = getattr(self, '_combined_cards_df', None)
        snapshot = full_df if full_df is not None else combined_df
        row_lookup: Dict[str, any] = {}
        if snapshot is not None and not getattr(snapshot, 'empty', True) and 'name' in snapshot.columns:
            for _, r in snapshot.iterrows():  # type: ignore[attr-defined]
                nm = str(r.get('name'))
                if nm and nm not in row_lookup:
                    row_lookup[nm] = r

        # Category classification (reuse export logic)
        precedence_order = [
            'Commander', 'Battle', 'Planeswalker', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land', 'Other'
        ]
        precedence_index = {k: i for i, k in enumerate(precedence_order)}
        commander_name = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''

        def classify(primary_type_line: str, card_name: str) -> str:
            if commander_name and card_name == commander_name:
                return 'Commander'
            tl = (primary_type_line or '').lower()
            if 'battle' in tl:
                return 'Battle'
            if 'planeswalker' in tl:
                return 'Planeswalker'
            if 'creature' in tl:
                return 'Creature'
            if 'instant' in tl:
                return 'Instant'
            if 'sorcery' in tl:
                return 'Sorcery'
            if 'artifact' in tl:
                return 'Artifact'
            if 'enchantment' in tl:
                return 'Enchantment'
            if 'land' in tl:
                return 'Land'
            return 'Other'

        # Type breakdown (counts and per-type card lists)
        type_counts: Dict[str, int] = {}
        type_cards: Dict[str, list] = {}
        total_cards = 0
        for name, info in self.card_library.items():
            # Exclude commander from type breakdown per UI preference
            if commander_name and name == commander_name:
                continue
            cnt = int(info.get('Count', 1))
            base_type = info.get('Card Type') or info.get('Type', '')
            if not base_type:
                row = row_lookup.get(name)
                if row is not None:
                    base_type = row.get('type', row.get('type_line', '')) or ''
            category = classify(base_type, name)
            type_counts[category] = type_counts.get(category, 0) + cnt
            total_cards += cnt
            type_cards.setdefault(category, []).append({
                'name': name,
                'count': cnt,
                'role': info.get('Role', '') or '',
                'tags': list(info.get('Tags', []) or []),
            })
        # Sort cards within each type by name
        for cat, lst in type_cards.items():
            lst.sort(key=lambda x: (x['name'].lower(), -int(x['count'])))
        type_order = sorted(type_counts.keys(), key=lambda k: precedence_index.get(k, 999))

        # Pip distribution (counts and weights) for non-land spells only
        pip_counts = {c: 0 for c in ('W','U','B','R','G')}
        # For UI cross-highlighting: map color -> list of cards that have that color pip in their cost
        pip_cards: Dict[str, list] = {c: [] for c in ('W','U','B','R','G')}
        import re as _re_local
        total_pips = 0.0
        for name, info in self.card_library.items():
            ctype = str(info.get('Card Type', ''))
            if 'land' in ctype.lower():
                continue
            mana_cost = info.get('Mana Cost') or info.get('mana_cost') or ''
            if not isinstance(mana_cost, str):
                continue
            # Track which colors appear for this card's mana cost for card listing
            colors_for_card = set()
            for match in _re_local.findall(r'\{([^}]+)\}', mana_cost):
                sym = match.upper()
                if len(sym) == 1 and sym in pip_counts:
                    pip_counts[sym] += 1
                    total_pips += 1
                    colors_for_card.add(sym)
                elif '/' in sym:
                    parts = [p for p in sym.split('/') if p in pip_counts]
                    if parts:
                        weight_each = 1 / len(parts)
                        for p in parts:
                            pip_counts[p] += weight_each
                            total_pips += weight_each
                            colors_for_card.add(p)
                elif sym.endswith('P') and len(sym) == 2:  # e.g. WP (Phyrexian) -> treat as that color
                    base = sym[0]
                    if base in pip_counts:
                        pip_counts[base] += 1
                        total_pips += 1
                        colors_for_card.add(base)
            if colors_for_card:
                cnt = int(info.get('Count', 1))
                for c in colors_for_card:
                    pip_cards[c].append({'name': name, 'count': cnt})
        if total_pips <= 0:
            # Fallback to even distribution across color identity
            colors = [c for c in ('W','U','B','R','G') if c in (getattr(self, 'color_identity', []) or [])]
            if colors:
                share = 1 / len(colors)
                for c in colors:
                    pip_counts[c] = share
                total_pips = 1.0
        pip_weights = {c: (pip_counts[c] / total_pips if total_pips else 0.0) for c in pip_counts}

        # Mana generation from lands (color sources)
        try:
            from deck_builder import builder_utils as _bu
            matrix = _bu.compute_color_source_matrix(self.card_library, full_df)
        except Exception:
            matrix = {}
        source_counts = {c: 0 for c in ('W','U','B','R','G','C')}
        # For UI cross-highlighting: color -> list of cards that produce that color (typically lands, possibly others)
        source_cards: Dict[str, list] = {c: [] for c in ('W','U','B','R','G','C')}
        for name, flags in matrix.items():
            copies = int(self.card_library.get(name, {}).get('Count', 1))
            for c in source_counts.keys():
                if int(flags.get(c, 0)):
                    source_counts[c] += copies
                    source_cards[c].append({'name': name, 'count': copies})
        total_sources = sum(source_counts.values())

        # Mana curve (non-land spells)
        curve_bins = ['0','1','2','3','4','5','6+']
        curve_counts = {b: 0 for b in curve_bins}
        curve_cards: Dict[str, list] = {b: [] for b in curve_bins}
        total_spells = 0
        for name, info in self.card_library.items():
            ctype = str(info.get('Card Type', ''))
            if 'land' in ctype.lower():
                continue
            cnt = int(info.get('Count', 1))
            mv = info.get('Mana Value')
            if mv in (None, ''):
                row = row_lookup.get(name)
                if row is not None:
                    mv = row.get('manaValue', row.get('cmc', None))
            try:
                val = float(mv) if mv not in (None, '') else 0.0
            except Exception:
                val = 0.0
            bucket = '6+' if val >= 6 else str(int(val))
            if bucket not in curve_counts:
                bucket = '6+'
            curve_counts[bucket] += cnt
            curve_cards[bucket].append({'name': name, 'count': cnt})
            total_spells += cnt

        return {
            'type_breakdown': {
                'counts': type_counts,
                'order': type_order,
                'cards': type_cards,
                'total': total_cards,
            },
            'pip_distribution': {
                'counts': pip_counts,
                'weights': pip_weights,
                'cards': pip_cards,
            },
            'mana_generation': {
                **source_counts,
                'total_sources': total_sources,
                'cards': source_cards,
            },
            'mana_curve': {
                **curve_counts,
                'total_spells': total_spells,
                'cards': curve_cards,
            },
            'colors': list(getattr(self, 'color_identity', []) or []),
        }
    def export_decklist_csv(self, directory: str = 'deck_files', filename: str | None = None, suppress_output: bool = False) -> str:
        """Export current decklist to CSV (enriched).
        Filename pattern (default): commanderFirstWord_firstTheme_YYYYMMDD.csv
        Included columns: Name, Count, Type, ManaCost, ManaValue, Colors, Power, Toughness, Role, Tags, Text.
        Falls back gracefully if snapshot rows missing.
        """
        """Export current decklist to CSV (enriched).

        Filename pattern (default): commanderFirstWord_firstTheme_YYYYMMDD.csv
        Included columns (enriched when possible):
          Name, Count, Type, ManaCost, ManaValue, Colors, Power, Toughness, Role, Tags, Text
        Falls back gracefully if snapshot rows missing.
        """
        os.makedirs(directory, exist_ok=True)
        def _slug(s: str) -> str:
            s2 = _re.sub(r'[^A-Za-z0-9_]+', '', s)
            return s2 or 'x'
        def _unique_path(path: str) -> str:
            if not os.path.exists(path):
                return path
            base, ext = os.path.splitext(path)
            i = 1
            while True:
                candidate = f"{base}_{i}{ext}"
                if not os.path.exists(candidate):
                    return candidate
                i += 1
        if filename is None:
            # Build a filename stem from either custom export base or commander/themes
            try:
                custom_base = getattr(self, 'custom_export_base', None)
            except Exception:
                custom_base = None
            date_part = _dt.date.today().strftime('%Y%m%d')
            if isinstance(custom_base, str) and custom_base.strip():
                stem = f"{_slug(custom_base.strip())}_{date_part}"
            else:
                cmdr = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
                cmdr_slug = _slug(cmdr) if isinstance(cmdr, str) and cmdr else 'deck'
                # Collect themes in order
                themes: List[str] = []
                if getattr(self, 'selected_tags', None):
                    themes = [str(t) for t in self.selected_tags if isinstance(t, str) and t.strip()]
                else:
                    for t in [getattr(self, 'primary_tag', None), getattr(self, 'secondary_tag', None), getattr(self, 'tertiary_tag', None)]:
                        if isinstance(t, str) and t.strip():
                            themes.append(t)
                theme_parts = [_slug(t) for t in themes if t]
                if not theme_parts:
                    theme_parts = ['notheme']
                theme_slug = '_'.join(theme_parts)
                stem = f"{cmdr_slug}_{theme_slug}_{date_part}"
            filename = f"{stem}.csv"
        fname = _unique_path(os.path.join(directory, filename))

        full_df = getattr(self, '_full_cards_df', None)
        combined_df = getattr(self, '_combined_cards_df', None)
        snapshot = full_df if full_df is not None else combined_df
        row_lookup: Dict[str, any] = {}
        if snapshot is not None and not snapshot.empty and 'name' in snapshot.columns:
            for _, r in snapshot.iterrows():
                nm = str(r.get('name'))
                if nm not in row_lookup:
                    row_lookup[nm] = r

        headers = [
            "Name","Count","Type","ManaCost","ManaValue","Colors","Power","Toughness",
            "Role","SubRole","AddedBy","TriggerTag","Synergy","Tags","Text","Owned"
        ]

        # Precedence list for sorting
        precedence_order = [
            'Commander', 'Battle', 'Planeswalker', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land'
        ]
        precedence_index = {k: i for i, k in enumerate(precedence_order)}
        commander_name = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''

        def classify(primary_type_line: str, card_name: str) -> str:
            if commander_name and card_name == commander_name:
                return 'Commander'
            tl = (primary_type_line or '').lower()
            if 'battle' in tl:
                return 'Battle'
            if 'planeswalker' in tl:
                return 'Planeswalker'
            if 'creature' in tl:
                return 'Creature'
            if 'instant' in tl:
                return 'Instant'
            if 'sorcery' in tl:
                return 'Sorcery'
            if 'artifact' in tl:
                return 'Artifact'
            if 'enchantment' in tl:
                return 'Enchantment'
            if 'land' in tl:
                return 'Land'
            return 'ZZZ'

        rows: List[tuple] = []  # (sort_key, row_data)

        # Prepare owned lookup if available
        owned_set_lower = set()
        try:
            owned_set_lower = {n.lower() for n in (getattr(self, 'owned_card_names', set()) or set())}
        except Exception:
            owned_set_lower = set()

        # Fallback oracle text for basic lands to ensure CSV has meaningful text
        BASIC_TEXT = {
            'Plains': '({T}: Add {W}.)',
            'Island': '({T}: Add {U}.)',
            'Swamp': '({T}: Add {B}.)',
            'Mountain': '({T}: Add {R}.)',
            'Forest': '({T}: Add {G}.)',
            'Wastes': '({T}: Add {C}.)',
        }
        for name, info in self.card_library.items():
            base_type = info.get('Card Type') or info.get('Type', '')
            base_mc = info.get('Mana Cost', '')
            base_mv = info.get('Mana Value', info.get('CMC', ''))
            role = info.get('Role', '') or ''
            tags = info.get('Tags', []) or []
            tags_join = '; '.join(tags)
            text_field = ''
            colors = ''
            power = ''
            toughness = ''
            row = row_lookup.get(name)
            if row is not None:
                row_type = row.get('type', row.get('type_line', ''))
                if row_type:
                    base_type = row_type
                mc = row.get('manaCost', '')
                if mc:
                    base_mc = mc
                mv = row.get('manaValue', row.get('cmc', ''))
                if mv not in (None, ''):
                    base_mv = mv
                colors_raw = row.get('colorIdentity', row.get('colors', []))
                if isinstance(colors_raw, list):
                    colors = ''.join(colors_raw)
                elif colors_raw not in (None, ''):
                    colors = str(colors_raw)
                power = row.get('power', '') or ''
                toughness = row.get('toughness', '') or ''
                text_field = row.get('text', row.get('oracleText', '')) or ''
            # If still no text and this is a basic, inject fallback oracle snippet
            if (not text_field) and (str(name) in BASIC_TEXT):
                text_field = BASIC_TEXT[str(name)]
            # Normalize and coerce text
            if isinstance(text_field, str):
                cleaned = text_field
            else:
                try:
                    import math as _math
                    if isinstance(text_field, float) and (_math.isnan(text_field)):
                        cleaned = ''
                    else:
                        cleaned = str(text_field) if text_field is not None else ''
                except Exception:
                    cleaned = str(text_field) if text_field is not None else ''
            cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')
            while '  ' in cleaned:
                cleaned = cleaned.replace('  ', ' ')
            text_field = cleaned

            cat = classify(base_type, name)
            prec = precedence_index.get(cat, 999)
            # Alphabetical within category (no mana value sorting)
            owned_flag = 'Y' if (name.lower() in owned_set_lower) else ''
            rows.append(((prec, name.lower()), [
                name,
                info.get('Count', 1),
                base_type,
                base_mc,
                base_mv,
                colors,
                power,
                toughness,
                info.get('Role') or role,
                info.get('SubRole') or '',
                info.get('AddedBy') or '',
                info.get('TriggerTag') or '',
                info.get('Synergy') if info.get('Synergy') is not None else '',
                tags_join,
                text_field[:800] if isinstance(text_field, str) else str(text_field)[:800],
                owned_flag
            ]))

        # Now sort (category precedence, then alphabetical name)
        rows.sort(key=lambda x: x[0])

        with open(fname, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(headers)
            for _, data_row in rows:
                w.writerow(data_row)

        self.output_func(f"Deck exported to {fname}")
        # Auto-generate matching plaintext list (best-effort; ignore failures)
        return fname

    def export_decklist_text(self, directory: str = 'deck_files', filename: str | None = None, suppress_output: bool = False) -> str:
        """Export a simple plaintext list: one line per unique card -> "[Count] [Card Name]".
        Naming mirrors CSV export (same stem, .txt extension). Sorting follows same precedence.
        """
        """Export a simple plaintext list: one line per unique card -> "[Count] [Card Name]".

        Naming mirrors CSV export (same stem, .txt extension). Sorting follows same
        category precedence then alphabetical within category for consistency.
        """
        os.makedirs(directory, exist_ok=True)
        # Derive base filename logic (shared with CSV exporter) – intentionally duplicated to avoid refactor risk.
        def _slug(s: str) -> str:
            s2 = _re.sub(r'[^A-Za-z0-9_]+', '', s)
            return s2 or 'x'
        def _unique_path(path: str) -> str:
            if not os.path.exists(path):
                return path
            base, ext = os.path.splitext(path)
            i = 1
            while True:
                candidate = f"{base}_{i}{ext}"
                if not os.path.exists(candidate):
                    return candidate
                i += 1
        if filename is None:
            # Prefer custom export base if provided; else fall back to commander/themes
            try:
                custom_base = getattr(self, 'custom_export_base', None)
            except Exception:
                custom_base = None
            date_part = _dt.date.today().strftime('%Y%m%d')
            if isinstance(custom_base, str) and custom_base.strip():
                stem = f"{_slug(custom_base.strip())}_{date_part}"
            else:
                cmdr = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
                cmdr_slug = _slug(cmdr) if isinstance(cmdr, str) and cmdr else 'deck'
                themes: List[str] = []
                if getattr(self, 'selected_tags', None):
                    themes = [str(t) for t in self.selected_tags if isinstance(t, str) and t.strip()]
                else:
                    for t in [getattr(self, 'primary_tag', None), getattr(self, 'secondary_tag', None), getattr(self, 'tertiary_tag', None)]:
                        if isinstance(t, str) and t.strip():
                            themes.append(t)
                theme_parts = [_slug(t) for t in themes if t]
                if not theme_parts:
                    theme_parts = ['notheme']
                theme_slug = '_'.join(theme_parts)
                stem = f"{cmdr_slug}_{theme_slug}_{date_part}"
            filename = f"{stem}.txt"
        if not filename.lower().endswith('.txt'):
            filename = filename + '.txt'
        path = _unique_path(os.path.join(directory, filename))

        # Sorting reproduction
        precedence_order = [
            'Commander', 'Battle', 'Planeswalker', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land'
        ]
        precedence_index = {k: i for i, k in enumerate(precedence_order)}
        commander_name = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
        def classify(primary_type_line: str, card_name: str) -> str:
            if commander_name and card_name == commander_name:
                return 'Commander'
            tl = (primary_type_line or '').lower()
            if 'battle' in tl:
                return 'Battle'
            if 'planeswalker' in tl:
                return 'Planeswalker'
            if 'creature' in tl:
                return 'Creature'
            if 'instant' in tl:
                return 'Instant'
            if 'sorcery' in tl:
                return 'Sorcery'
            if 'artifact' in tl:
                return 'Artifact'
            if 'enchantment' in tl:
                return 'Enchantment'
            if 'land' in tl:
                return 'Land'
            return 'ZZZ'

        # We may want enriched type lines from snapshot; build quick lookup
        full_df = getattr(self, '_full_cards_df', None)
        combined_df = getattr(self, '_combined_cards_df', None)
        snapshot = full_df if full_df is not None else combined_df
        row_lookup: Dict[str, any] = {}
        if snapshot is not None and not snapshot.empty and 'name' in snapshot.columns:
            for _, r in snapshot.iterrows():
                nm = str(r.get('name'))
                if nm not in row_lookup:
                    row_lookup[nm] = r

        sortable: List[tuple] = []
        for name, info in self.card_library.items():
            base_type = info.get('Card Type') or info.get('Type','')
            row = row_lookup.get(name)
            if row is not None:
                row_type = row.get('type', row.get('type_line', ''))
                if row_type:
                    base_type = row_type
            cat = classify(base_type, name)
            prec = precedence_index.get(cat, 999)
            sortable.append(((prec, name.lower()), name, info.get('Count',1)))
        sortable.sort(key=lambda x: x[0])

        with open(path, 'w', encoding='utf-8') as f:
            for _, name, count in sortable:
                f.write(f"{count} {name}\n")
        if not suppress_output:
            self.output_func(f"Plaintext deck list exported to {path}")
        return path

    def export_run_config_json(self, directory: str = 'config', filename: str | None = None, suppress_output: bool = False) -> str:
        """Export a JSON config capturing the key choices for replaying headless.

        Filename mirrors CSV/TXT naming (same stem, .json extension).
        Fields included:
          - commander
          - primary_tag / secondary_tag / tertiary_tag
          - bracket_level (if chosen)
          - use_multi_theme (default True)
          - add_lands, add_creatures, add_non_creature_spells (defaults True)
          - fetch_count (if determined during run)
          - ideal_counts (the actual ideal composition values used)
        """
        os.makedirs(directory, exist_ok=True)

        def _slug(s: str) -> str:
            s2 = _re.sub(r'[^A-Za-z0-9_]+', '', s)
            return s2 or 'x'

        def _unique_path(path: str) -> str:
            if not os.path.exists(path):
                return path
            base, ext = os.path.splitext(path)
            i = 1
            while True:
                candidate = f"{base}_{i}{ext}"
                if not os.path.exists(candidate):
                    return candidate
                i += 1

        if filename is None:
            # Prefer a custom export base when present; else commander/themes
            try:
                custom_base = getattr(self, 'custom_export_base', None)
            except Exception:
                custom_base = None
            date_part = _dt.date.today().strftime('%Y%m%d')
            if isinstance(custom_base, str) and custom_base.strip():
                stem = f"{_slug(custom_base.strip())}_{date_part}"
            else:
                cmdr = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
                cmdr_slug = _slug(cmdr) if isinstance(cmdr, str) and cmdr else 'deck'
                themes: List[str] = []
                if getattr(self, 'selected_tags', None):
                    themes = [str(t) for t in self.selected_tags if isinstance(t, str) and t.strip()]
                else:
                    for t in [getattr(self, 'primary_tag', None), getattr(self, 'secondary_tag', None), getattr(self, 'tertiary_tag', None)]:
                        if isinstance(t, str) and t.strip():
                            themes.append(t)
                theme_parts = [_slug(t) for t in themes if t]
                if not theme_parts:
                    theme_parts = ['notheme']
                theme_slug = '_'.join(theme_parts)
                stem = f"{cmdr_slug}_{theme_slug}_{date_part}"
            filename = f"{stem}.json"

        path = _unique_path(os.path.join(directory, filename))

        # Capture ideal counts (actual chosen values)
        ideal_counts = getattr(self, 'ideal_counts', {}) or {}
        # Capture fetch count (others vary run-to-run and are intentionally not recorded)
        chosen_fetch = getattr(self, 'fetch_count', None)

        payload = {
            "commander": getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or '',
            "primary_tag": getattr(self, 'primary_tag', None),
            "secondary_tag": getattr(self, 'secondary_tag', None),
            "tertiary_tag": getattr(self, 'tertiary_tag', None),
            "bracket_level": getattr(self, 'bracket_level', None),
            "tag_mode": (getattr(self, 'tag_mode', 'AND') or 'AND'),
            "use_multi_theme": True,
            "add_lands": True,
            "add_creatures": True,
            "add_non_creature_spells": True,
            # Combos preferences (if set during build)
            "prefer_combos": bool(getattr(self, 'prefer_combos', False)),
            "combo_target_count": (int(getattr(self, 'combo_target_count', 0)) if getattr(self, 'prefer_combos', False) else None),
            "combo_balance": (getattr(self, 'combo_balance', None) if getattr(self, 'prefer_combos', False) else None),
            # Include/Exclude configuration (M1: Config + Validation + Persistence)
            "include_cards": list(getattr(self, 'include_cards', [])),
            "exclude_cards": list(getattr(self, 'exclude_cards', [])),
            "enforcement_mode": getattr(self, 'enforcement_mode', 'warn'),
            "allow_illegal": bool(getattr(self, 'allow_illegal', False)),
            "fuzzy_matching": bool(getattr(self, 'fuzzy_matching', True)),
            # chosen fetch land count (others intentionally omitted for variance)
            "fetch_count": chosen_fetch,
            # actual ideal counts used for this run
            "ideal_counts": {
                k: int(v) for k, v in ideal_counts.items() if isinstance(v, (int, float))
            }
            # seed intentionally omitted
        }

        try:
            import json as _json
            with open(path, 'w', encoding='utf-8') as f:
                _json.dump(payload, f, indent=2)
            if not suppress_output:
                self.output_func(f"Run config exported to {path}")
        except Exception as e:
            logger.warning(f"Failed to export run config: {e}")
        return path

    def print_card_library(self, table: bool = True):
        """Prints the current card library in either plain or tabular format.
        Uses PrettyTable if available, otherwise prints a simple list.
        """
    # Card library printout suppressed; use CSV and text export for card list.
    pass
