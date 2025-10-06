from __future__ import annotations

from typing import Any, Dict, List
import csv
import os
import datetime as _dt
import re as _re
import logging_util

from code.deck_builder.summary_telemetry import record_land_summary, record_theme_summary, record_partner_summary
from code.deck_builder.color_identity_utils import normalize_colors, canon_color_code, color_label_from_code
from code.deck_builder.shared_copy import build_land_headline, dfc_card_note

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

    def get_commander_export_metadata(self) -> Dict[str, Any]:
        """Return metadata describing the active commander configuration for export surfaces."""

        def _clean(value: object) -> str:
            try:
                text = str(value).strip()
            except Exception:
                text = ""
            return text

        metadata: Dict[str, Any] = {
            "primary_commander": None,
            "secondary_commander": None,
            "commander_names": [],
            "partner_mode": None,
            "color_identity": [],
        }

        combined = getattr(self, 'combined_commander', None)

        commander_names: list[str] = []
        primary_name = None
        secondary_name = None

        if combined is not None:
            primary_name = _clean(getattr(combined, 'primary_name', '')) or None
            secondary_name = _clean(getattr(combined, 'secondary_name', '')) or None
            partner_mode_obj = getattr(combined, 'partner_mode', None)
            partner_mode_val = getattr(partner_mode_obj, 'value', None)
            if isinstance(partner_mode_val, str) and partner_mode_val.strip():
                metadata["partner_mode"] = partner_mode_val.strip()
            elif isinstance(partner_mode_obj, str) and partner_mode_obj.strip():
                metadata["partner_mode"] = partner_mode_obj.strip()
            if primary_name:
                commander_names.append(primary_name)
            if secondary_name and all(secondary_name.casefold() != n.casefold() for n in commander_names):
                commander_names.append(secondary_name)
            combined_identity_raw = list(getattr(combined, 'color_identity', []) or [])
            combined_colors = normalize_colors(combined_identity_raw)
            primary_colors = normalize_colors(getattr(combined, 'primary_color_identity', ()))
            secondary_colors = normalize_colors(getattr(combined, 'secondary_color_identity', ()))
            color_code = getattr(combined, 'color_code', '') or canon_color_code(combined_identity_raw)
            color_label = getattr(combined, 'color_label', '') or color_label_from_code(color_code)

            mode_lower = (metadata["partner_mode"] or "").lower() if metadata.get("partner_mode") else ""
            if mode_lower == "background":
                secondary_role = "background"
            elif mode_lower == "doctor_companion":
                secondary_role = "companion"
            elif mode_lower == "partner_with":
                secondary_role = "partner_with"
            elif mode_lower == "partner":
                secondary_role = "partner"
            else:
                secondary_role = "secondary"

            secondary_role_label_map = {
                "background": "Background",
                "companion": "Doctor pairing",
                "partner_with": "Partner With",
                "partner": "Partner commander",
            }
            secondary_role_label = secondary_role_label_map.get(secondary_role, "Partner commander")

            color_sources: list[Dict[str, Any]] = []
            for color in combined_colors:
                providers: list[Dict[str, Any]] = []
                if primary_name and color in primary_colors:
                    providers.append({"name": primary_name, "role": "primary"})
                if secondary_name and color in secondary_colors:
                    providers.append({"name": secondary_name, "role": secondary_role})
                if not providers and primary_name:
                    providers.append({"name": primary_name, "role": "primary"})
                color_sources.append({"color": color, "providers": providers})

            added_colors = [c for c in combined_colors if c not in primary_colors]
            removed_colors = [c for c in primary_colors if c not in combined_colors]

            combined_payload = {
                "primary_name": primary_name,
                "secondary_name": secondary_name,
                "partner_mode": metadata["partner_mode"],
                "color_identity": combined_identity_raw,
                "theme_tags": list(getattr(combined, 'theme_tags', []) or []),
                "raw_tags_primary": list(getattr(combined, 'raw_tags_primary', []) or []),
                "raw_tags_secondary": list(getattr(combined, 'raw_tags_secondary', []) or []),
                "warnings": list(getattr(combined, 'warnings', []) or []),
                "color_code": color_code,
                "color_label": color_label,
                "primary_color_identity": primary_colors,
                "secondary_color_identity": secondary_colors,
                "secondary_role": secondary_role,
                "secondary_role_label": secondary_role_label,
                "color_sources": color_sources,
                "color_delta": {
                    "added": added_colors,
                    "removed": removed_colors,
                    "primary": primary_colors,
                    "secondary": secondary_colors,
                },
            }
            metadata["combined_commander"] = combined_payload
        else:
            primary_attr = _clean(getattr(self, 'commander_name', '') or getattr(self, 'commander', ''))
            if primary_attr:
                primary_name = primary_attr
                commander_names.append(primary_attr)
            secondary_attr = _clean(getattr(self, 'secondary_commander', ''))
            if secondary_attr and all(secondary_attr.casefold() != n.casefold() for n in commander_names):
                secondary_name = secondary_attr
                commander_names.append(secondary_attr)
            partner_mode_attr = getattr(self, 'partner_mode', None)
            partner_mode_val = getattr(partner_mode_attr, 'value', None)
            if isinstance(partner_mode_val, str) and partner_mode_val.strip():
                metadata["partner_mode"] = partner_mode_val.strip()
            elif isinstance(partner_mode_attr, str) and partner_mode_attr.strip():
                metadata["partner_mode"] = partner_mode_attr.strip()

        metadata["primary_commander"] = primary_name
        metadata["secondary_commander"] = secondary_name
        metadata["commander_names"] = commander_names

        if metadata["partner_mode"]:
            metadata["partner_mode"] = metadata["partner_mode"].lower()

        # Prefer combined color identity when available
        color_source = None
        if combined is not None:
            color_source = getattr(combined, 'color_identity', None)
        if not color_source:
            color_source = getattr(self, 'combined_color_identity', None)
        if not color_source:
            color_source = getattr(self, 'color_identity', None)
        if color_source:
            metadata["color_identity"] = [str(c).strip().upper() for c in color_source if str(c).strip()]

        return metadata
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

        # Surface land vs. MDFC counts for CLI users to mirror web summary copy
        try:
            summary = self.build_deck_summary()  # type: ignore[attr-defined]
        except Exception:
            summary = None
        if isinstance(summary, dict):
            land_summary = summary.get('land_summary') or {}
            if isinstance(land_summary, dict) and land_summary:
                traditional = int(land_summary.get('traditional', 0))
                dfc_bonus = int(land_summary.get('dfc_lands', 0))
                with_dfc = int(land_summary.get('with_dfc', traditional + dfc_bonus))
                headline = land_summary.get('headline')
                if not headline:
                    headline = build_land_headline(traditional, dfc_bonus, with_dfc)
                self.output_func(f"  {headline}")
                dfc_cards = land_summary.get('dfc_cards') or []
                if isinstance(dfc_cards, list) and dfc_cards:
                    self.output_func("  MDFC sources:")
                    for entry in dfc_cards:
                        try:
                            name = str(entry.get('name', ''))
                            count = int(entry.get('count', 1))
                        except Exception:
                            name, count = str(entry.get('name', '')), 1
                        colors = entry.get('colors') or []
                        colors_txt = ', '.join(colors) if colors else '-'
                        adds_extra = bool(entry.get('adds_extra_land') or entry.get('counts_as_extra'))
                        note = entry.get('note') or dfc_card_note(adds_extra)
                        self.output_func(f"    - {name} ×{count} ({colors_txt}) — {note}")

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

        builder_utils_module = None
        try:
            from deck_builder import builder_utils as _builder_utils  # type: ignore
            builder_utils_module = _builder_utils
            color_matrix = builder_utils_module.compute_color_source_matrix(self.card_library, full_df)
        except Exception:
            color_matrix = {}
        dfc_land_lookup: Dict[str, Dict[str, Any]] = {}
        if color_matrix:
            for name, flags in color_matrix.items():
                if not bool(flags.get('_dfc_land')):
                    continue
                counts_as_extra = bool(flags.get('_dfc_counts_as_extra'))
                note_text = dfc_card_note(counts_as_extra)
                card_colors = [color for color in ('W', 'U', 'B', 'R', 'G', 'C') if flags.get(color)]
                faces_meta: list[Dict[str, Any]] = []
                layout_val = None
                if builder_utils_module is not None:
                    try:
                        mf_info = builder_utils_module.multi_face_land_info(name)
                    except Exception:
                        mf_info = {}
                    faces_meta = list(mf_info.get('faces', [])) if isinstance(mf_info, dict) else []
                    layout_val = mf_info.get('layout') if isinstance(mf_info, dict) else None
                dfc_land_lookup[name] = {
                    'adds_extra_land': counts_as_extra,
                    'counts_as_land': not counts_as_extra,
                    'note': note_text,
                    'colors': card_colors,
                    'faces': faces_meta,
                    'layout': layout_val,
                }
        else:
            color_matrix = {}

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
            card_entry = {
                'name': name,
                'count': cnt,
                'role': info.get('Role', '') or '',
                'tags': list(info.get('Tags', []) or []),
            }
            dfc_meta = dfc_land_lookup.get(name)
            if dfc_meta:
                card_entry['dfc'] = True
                card_entry['dfc_land'] = True
                card_entry['dfc_adds_extra_land'] = bool(dfc_meta.get('adds_extra_land'))
                card_entry['dfc_counts_as_land'] = bool(dfc_meta.get('counts_as_land'))
                card_entry['dfc_note'] = dfc_meta.get('note', '')
                card_entry['dfc_colors'] = list(dfc_meta.get('colors', []))
                card_entry['dfc_faces'] = list(dfc_meta.get('faces', []))
            type_cards.setdefault(category, []).append(card_entry)
        # Sort cards within each type by name
        for cat, lst in type_cards.items():
            lst.sort(key=lambda x: (x['name'].lower(), -int(x['count'])))
        type_order = sorted(type_counts.keys(), key=lambda k: precedence_index.get(k, 999))

        # Track multi-face land contributions for later summary display
        dfc_details: list[dict] = []
        dfc_extra_total = 0

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
        matrix = color_matrix
        source_counts = {c: 0 for c in ('W','U','B','R','G','C')}
        # For UI cross-highlighting: color -> list of cards that produce that color (typically lands, possibly others)
        source_cards: Dict[str, list] = {c: [] for c in ('W','U','B','R','G','C')}
        for name, flags in matrix.items():
            copies = int(self.card_library.get(name, {}).get('Count', 1))
            is_dfc_land = bool(flags.get('_dfc_land'))
            counts_as_extra = bool(flags.get('_dfc_counts_as_extra'))
            dfc_meta = dfc_land_lookup.get(name)
            for c in source_counts.keys():
                if int(flags.get(c, 0)):
                    source_counts[c] += copies
                    entry = {'name': name, 'count': copies, 'dfc': is_dfc_land}
                    if dfc_meta:
                        entry['dfc_note'] = dfc_meta.get('note', '')
                        entry['dfc_adds_extra_land'] = bool(dfc_meta.get('adds_extra_land'))
                    source_cards[c].append(entry)
            if is_dfc_land:
                card_colors = list(dfc_meta.get('colors', [])) if dfc_meta else [color for color in ('W','U','B','R','G','C') if flags.get(color)]
                note_text = dfc_meta.get('note') if dfc_meta else dfc_card_note(counts_as_extra)
                adds_extra = bool(dfc_meta.get('adds_extra_land')) if dfc_meta else counts_as_extra
                counts_as_land = bool(dfc_meta.get('counts_as_land')) if dfc_meta else not counts_as_extra
                faces_meta = list(dfc_meta.get('faces', [])) if dfc_meta else []
                layout_val = dfc_meta.get('layout') if dfc_meta else None
                dfc_details.append({
                    'name': name,
                    'count': copies,
                    'colors': card_colors,
                    'counts_as_land': counts_as_land,
                    'adds_extra_land': adds_extra,
                    'counts_as_extra': adds_extra,
                    'note': note_text,
                    'faces': faces_meta,
                    'layout': layout_val,
                })
                if adds_extra:
                    dfc_extra_total += copies
        total_sources = sum(source_counts.values())
        traditional_lands = type_counts.get('Land', 0)
        land_summary = {
            'traditional': traditional_lands,
            'dfc_lands': dfc_extra_total,
            'with_dfc': traditional_lands + dfc_extra_total,
            'dfc_cards': dfc_details,
            'headline': build_land_headline(traditional_lands, dfc_extra_total, traditional_lands + dfc_extra_total),
        }

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

        # Include/exclude impact summary (M3: Include/Exclude Summary Panel)
        include_exclude_summary = {}
        diagnostics = getattr(self, 'include_exclude_diagnostics', None)
        if diagnostics:
            include_exclude_summary = {
                'include_cards': list(getattr(self, 'include_cards', [])),
                'exclude_cards': list(getattr(self, 'exclude_cards', [])),
                'include_added': diagnostics.get('include_added', []),
                'missing_includes': diagnostics.get('missing_includes', []),
                'excluded_removed': diagnostics.get('excluded_removed', []),
                'fuzzy_corrections': diagnostics.get('fuzzy_corrections', {}),
                'illegal_dropped': diagnostics.get('illegal_dropped', []),
                'illegal_allowed': diagnostics.get('illegal_allowed', []),
                'ignored_color_identity': diagnostics.get('ignored_color_identity', []),
                'duplicates_collapsed': diagnostics.get('duplicates_collapsed', {}),
            }

        summary_payload = {
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
            'land_summary': land_summary,
            'colors': list(getattr(self, 'color_identity', []) or []),
            'include_exclude_summary': include_exclude_summary,
        }

        try:
            commander_meta = self.get_commander_export_metadata()
        except Exception:
            commander_meta = {}
        commander_names = commander_meta.get('commander_names') or []
        if commander_names:
            summary_payload['commander'] = {
                'names': commander_names,
                'primary': commander_meta.get('primary_commander'),
                'secondary': commander_meta.get('secondary_commander'),
                'partner_mode': commander_meta.get('partner_mode'),
                'color_identity': commander_meta.get('color_identity') or list(getattr(self, 'color_identity', []) or []),
            }
            combined_payload = commander_meta.get('combined_commander')
            if combined_payload:
                summary_payload['commander']['combined'] = combined_payload
                try:
                    record_partner_summary(summary_payload['commander'])
                except Exception:  # pragma: no cover - diagnostics only
                    logger.debug("Failed to record partner telemetry", exc_info=True)
        try:
            record_land_summary(land_summary)
        except Exception:  # pragma: no cover - diagnostics only
            logger.debug("Failed to record MDFC telemetry", exc_info=True)
        try:
            theme_payload = self.get_theme_summary_payload() if hasattr(self, "get_theme_summary_payload") else None
            if theme_payload:
                record_theme_summary(theme_payload)
        except Exception:  # pragma: no cover - diagnostics only
            logger.debug("Failed to record theme telemetry", exc_info=True)
        return summary_payload
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

        builder_utils_module = None
        try:
            from deck_builder import builder_utils as builder_utils_module  # type: ignore
            color_matrix = builder_utils_module.compute_color_source_matrix(self.card_library, full_df)
        except Exception:
            color_matrix = {}
        dfc_land_lookup: Dict[str, Dict[str, Any]] = {}
        for card_name, flags in color_matrix.items():
            if not bool(flags.get('_dfc_land')):
                continue
            counts_as_extra = bool(flags.get('_dfc_counts_as_extra'))
            note_text = dfc_card_note(counts_as_extra)
            dfc_land_lookup[card_name] = {
                'note': note_text,
                'adds_extra_land': counts_as_extra,
            }

        headers = [
            "Name","Count","Type","ManaCost","ManaValue","Colors","Power","Toughness",
            "Role","SubRole","AddedBy","TriggerTag","Synergy","Tags","Text","DFCNote","Owned"
        ]

        header_suffix: List[str] = []
        try:
            commander_meta = self.get_commander_export_metadata()
        except Exception:
            commander_meta = {}
        commander_names = commander_meta.get('commander_names') or []
        if commander_names:
            header_suffix.append(f"Commanders: {', '.join(commander_names)}")
        header_row = headers + header_suffix
        suffix_padding = [''] * len(header_suffix)

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
            dfc_meta = dfc_land_lookup.get(name)
            dfc_note = ''
            if dfc_meta:
                note_text = dfc_meta.get('note')
                if note_text:
                    dfc_note = f"MDFC: {note_text}"
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
                dfc_note,
                owned_flag
            ]))

        # Now sort (category precedence, then alphabetical name)
        rows.sort(key=lambda x: x[0])

        with open(fname, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(header_row)
            for _, data_row in rows:
                if suffix_padding:
                    w.writerow(data_row + suffix_padding)
                else:
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

        try:
            from deck_builder import builder_utils as _builder_utils  # type: ignore
            color_matrix = _builder_utils.compute_color_source_matrix(self.card_library, full_df)
        except Exception:
            color_matrix = {}
        dfc_land_lookup: Dict[str, str] = {}
        for card_name, flags in color_matrix.items():
            if not bool(flags.get('_dfc_land')):
                continue
            counts_as_extra = bool(flags.get('_dfc_counts_as_extra'))
            dfc_land_lookup[card_name] = dfc_card_note(counts_as_extra)

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
            dfc_note = dfc_land_lookup.get(name)
            sortable.append(((prec, name.lower()), name, info.get('Count',1), dfc_note))
        sortable.sort(key=lambda x: x[0])

        try:
            commander_meta = self.get_commander_export_metadata()
        except Exception:
            commander_meta = {}
        header_lines: List[str] = []
        commander_names = commander_meta.get('commander_names') or []
        if commander_names:
            header_lines.append(f"# Commanders: {', '.join(commander_names)}")
        partner_mode = commander_meta.get('partner_mode')
        if partner_mode and partner_mode not in (None, '', 'none'):
            header_lines.append(f"# Partner Mode: {partner_mode}")
        color_identity = commander_meta.get('color_identity') or []
        if color_identity:
            header_lines.append(f"# Colors: {', '.join(color_identity)}")

        with open(path, 'w', encoding='utf-8') as f:
            if header_lines:
                f.write("\n".join(header_lines) + "\n\n")
            for _, name, count, dfc_note in sortable:
                line = f"{count} {name}"
                if dfc_note:
                    line += f" [MDFC: {dfc_note}]"
                f.write(line + "\n")
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
          - secondary_commander (when partner mechanics apply)
          - background (when Choose a Background is used)
          - enable_partner_mechanics flag (bool, default False)
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

        def _clean_text(value: object | None) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return None
                if text.lower() == "none":
                    return None
                return text
            try:
                text = str(value).strip()
            except Exception:
                return None
            if not text:
                return None
            if text.lower() == "none":
                return None
            return text

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

        user_themes: List[str] = [
            str(theme)
            for theme in getattr(self, 'user_theme_requested', [])
            if isinstance(theme, str) and theme.strip()
        ]
        theme_catalog_version = getattr(self, 'theme_catalog_version', None)

        partner_enabled_flag = bool(getattr(self, 'partner_feature_enabled', False))
        requested_secondary = _clean_text(getattr(self, 'requested_secondary_commander', None))
        requested_background = _clean_text(getattr(self, 'requested_background', None))
        stored_secondary = _clean_text(getattr(self, 'secondary_commander', None))
        stored_background = _clean_text(getattr(self, 'background', None))

        metadata: Dict[str, Any] = {}
        try:
            metadata_candidate = self.get_commander_export_metadata()
        except Exception:
            metadata_candidate = {}
        if isinstance(metadata_candidate, dict):
            metadata = metadata_candidate

        partner_mode = str(metadata.get("partner_mode") or "").strip().lower() if metadata else ""
        metadata_secondary = _clean_text(metadata.get("secondary_commander")) if metadata else None
        combined_secondary = None
        combined_info = metadata.get("combined_commander") if metadata else None
        if isinstance(combined_info, dict):
            combined_secondary = _clean_text(combined_info.get("secondary_name"))

        if partner_mode and partner_mode not in {"none", ""}:
            partner_enabled_flag = True if not partner_enabled_flag else partner_enabled_flag

        secondary_for_export = None
        background_for_export = None
        if partner_mode == "background":
            background_for_export = (
                combined_secondary
                or requested_background
                or metadata_secondary
                or stored_background
                or stored_secondary
            )
        else:
            secondary_for_export = (
                combined_secondary
                or requested_secondary
                or metadata_secondary
                or stored_secondary
            )
            background_for_export = requested_background or stored_background

        secondary_for_export = _clean_text(secondary_for_export)
        background_for_export = _clean_text(background_for_export)

        if partner_mode == "background":
            secondary_for_export = None

        enable_partner_flag = bool(partner_enabled_flag)

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
            "additional_themes": user_themes,
            "theme_match_mode": getattr(self, 'theme_match_mode', 'permissive'),
            "theme_catalog_version": theme_catalog_version,
            # CamelCase aliases for downstream consumers (web diagnostics, external tooling)
            "userThemes": user_themes,
            "themeCatalogVersion": theme_catalog_version,
            "secondary_commander": secondary_for_export,
            "background": background_for_export,
            "enable_partner_mechanics": enable_partner_flag,
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
