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
            date_part = _dt.date.today().strftime('%Y%m%d')
            filename = f"{cmdr_slug}_{theme_slug}_{date_part}.csv"
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
            "Role","SubRole","AddedBy","TriggerTag","Synergy","Tags","Text"
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

        for name, info in self.card_library.items():
            base_type = info.get('Card Type') or info.get('Type','')
            base_mc = info.get('Mana Cost','')
            base_mv = info.get('Mana Value', info.get('CMC',''))
            role = info.get('Role','') or ''
            tags = info.get('Tags',[]) or []
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
            rows.append(((prec, name.lower()), [
                name,
                info.get('Count',1),
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
                text_field[:800] if isinstance(text_field, str) else str(text_field)[:800]
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
            date_part = _dt.date.today().strftime('%Y%m%d')
            filename = f"{cmdr_slug}_{theme_slug}_{date_part}.txt"
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
            date_part = _dt.date.today().strftime('%Y%m%d')
            filename = f"{cmdr_slug}_{theme_slug}_{date_part}.json"

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
            "use_multi_theme": True,
            "add_lands": True,
            "add_creatures": True,
            "add_non_creature_spells": True,
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
