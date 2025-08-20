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
    """Phase 6: Reporting, summaries, and export helpers."""

    def _wrap_cell(self, text: str, width: int = 28) -> str:
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
        type_counts: Dict[str,int] = {}
        for name, info in self.card_library.items():
            ctype = info.get('Type', 'Unknown')
            cnt = info.get('Count',1)
            type_counts[ctype] = type_counts.get(ctype,0) + cnt
        total_cards = sum(type_counts.values())
        self.output_func("\nType Summary:")
        for t, c in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.output_func(f"  {t:<15} {c:>3}  ({(c/total_cards*100 if total_cards else 0):5.1f}%)")
    def export_decklist_csv(self, directory: str = 'deck_files', filename: str | None = None) -> str:
        """Export current decklist to CSV (enriched).

        Filename pattern (default): commanderFirstWord_firstTheme_YYYYMMDD.csv
        Included columns (enriched when possible):
          Name, Count, Type, ManaCost, ManaValue, Colors, Power, Toughness, Role, Tags, Text
        Falls back gracefully if snapshot rows missing.
        """
        os.makedirs(directory, exist_ok=True)
        if filename is None:
            cmdr = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
            cmdr_first = cmdr.split()[0] if cmdr else 'deck'
            theme = getattr(self, 'primary_tag', None) or (self.selected_tags[0] if getattr(self, 'selected_tags', []) else None)
            theme_first = str(theme).split()[0] if theme else 'notheme'
            def _slug(s: str) -> str:
                s2 = _re.sub(r'[^A-Za-z0-9_]+', '', s)
                return s2 or 'x'
            cmdr_slug = _slug(cmdr_first)
            theme_slug = _slug(theme_first)
            date_part = _dt.date.today().strftime('%Y%m%d')
            filename = f"{cmdr_slug}_{theme_slug}_{date_part}.csv"
        fname = os.path.join(directory, filename)

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
        try:  # pragma: no cover - sidecar convenience
            stem = os.path.splitext(os.path.basename(fname))[0]
            # Always overwrite sidecar to reflect latest deck state
            self.export_decklist_text(directory=directory, filename=stem + '.txt')  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Plaintext sidecar export failed (non-fatal)")
        return fname

    def export_decklist_text(self, directory: str = 'deck_files', filename: str | None = None) -> str:
        """Export a simple plaintext list: one line per unique card -> "[Count] [Card Name]".

        Naming mirrors CSV export (same stem, .txt extension). Sorting follows same
        category precedence then alphabetical within category for consistency.
        """
        os.makedirs(directory, exist_ok=True)
        # Derive base filename logic (shared with CSV exporter) – intentionally duplicated to avoid refactor risk.
        if filename is None:
            cmdr = getattr(self, 'commander_name', '') or getattr(self, 'commander', '') or ''
            cmdr_first = cmdr.split()[0] if cmdr else 'deck'
            theme = getattr(self, 'primary_tag', None) or (self.selected_tags[0] if getattr(self, 'selected_tags', []) else None)
            theme_first = str(theme).split()[0] if theme else 'notheme'
            def _slug(s: str) -> str:
                s2 = _re.sub(r'[^A-Za-z0-9_]+', '', s)
                return s2 or 'x'
            cmdr_slug = _slug(cmdr_first)
            theme_slug = _slug(theme_first)
            date_part = _dt.date.today().strftime('%Y%m%d')
            filename = f"{cmdr_slug}_{theme_slug}_{date_part}.txt"
        if not filename.lower().endswith('.txt'):
            filename = filename + '.txt'
        path = os.path.join(directory, filename)

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
        self.output_func(f"Plaintext deck list exported to {path}")
        return path

    def print_card_library(self, table: bool = True):  # noqa: C901
        if table and PrettyTable is None:
            table = False
        if not table:
            self.output_func("\nCard Library:")
            for name, info in sorted(self.card_library.items()):
                self.output_func(f"  {info.get('Count',1)}x {name} [{info.get('Type','')}] ({info.get('Role','')})")
            return
        # PrettyTable mode
        pt = PrettyTable()
        pt.field_names = ["Name","Count","Type","CMC","Role","Tags","Notes"]
        pt.align = 'l'
        for name, info in sorted(self.card_library.items()):
            pt.add_row([
                self._wrap_cell(name),
                info.get('Count',1),
                info.get('Type',''),
                info.get('CMC',''),
                self._wrap_cell(info.get('Role','')), 
                self._wrap_cell(','.join(info.get('Tags',[]) or [])),
                self._wrap_cell(info.get('SourceNotes',''))
            ])
        self.output_func("\nCard Library (tabular):")
        self.output_func(pt.get_string())
