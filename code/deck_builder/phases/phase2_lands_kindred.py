from __future__ import annotations
from typing import List, Dict
from .. import builder_constants as bc

"""Phase 2 (part 3): Kindred / tribal land additions (Land Step 3).

Extracted from `builder.py` to reduce monolith size. Focuses on lands that care
about creature types or tribal synergies when a selected tag includes 'Kindred' or 'Tribal'.

Provided by LandKindredMixin:
  - add_kindred_lands()
  - run_land_step3()

Host DeckBuilder must provide:
  - attributes: selected_tags, commander_tags, color_identity, ideal_counts, commander_row,
                card_library, _full_cards_df
  - methods: determine_color_identity(), setup_dataframes(), add_card(), _current_land_count(),
             _basic_floor(), _count_basic_lands(), _choose_basic_to_trim(), _decrement_card(),
             _enforce_land_cap(), output_func
"""

class LandKindredMixin:
    def add_kindred_lands(self):  # type: ignore[override]
        """Add kindred-oriented lands ONLY if a selected tag includes 'Kindred' or 'Tribal'.

        Baseline inclusions on kindred focus:
          - Path of Ancestry (always when kindred)
          - Cavern of Souls (<=4 colors)
          - Three Tree City (>=2 colors)
        Dynamic tribe-specific lands: derived only from selected tags (not all commander tags).
        Capacity: may swap excess basics (above 90% floor) similar to other steps.
        """
        if not getattr(self, 'files_to_load', []):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add kindred lands until color identity resolved: {e}")
                return
        if not any(('kindred' in t.lower() or 'tribal' in t.lower()) for t in (getattr(self, 'selected_tags', []) or [])):
            self.output_func("Kindred Lands: No selected kindred/tribal tag; skipping.")
            return
        if hasattr(self, 'ideal_counts') and getattr(self, 'ideal_counts'):
            land_target = self.ideal_counts.get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35))  # type: ignore[attr-defined]
        else:
            land_target = getattr(bc, 'DEFAULT_LAND_COUNT', 35)
        min_basic_cfg = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if hasattr(self, 'ideal_counts') and getattr(self, 'ideal_counts'):
            min_basic_cfg = self.ideal_counts.get('basic_lands', min_basic_cfg)  # type: ignore[attr-defined]
        basic_floor = self._basic_floor(min_basic_cfg)  # type: ignore[attr-defined]

        def ensure_capacity() -> bool:
            if self._current_land_count() < land_target:  # type: ignore[attr-defined]
                return True
            if self._count_basic_lands() <= basic_floor:  # type: ignore[attr-defined]
                return False
            target_basic = self._choose_basic_to_trim()  # type: ignore[attr-defined]
            if not target_basic:
                return False
            if not self._decrement_card(target_basic):  # type: ignore[attr-defined]
                return False
            return self._current_land_count() < land_target  # type: ignore[attr-defined]

        colors = getattr(self, 'color_identity', []) or []
        added: List[str] = []
        reasons: Dict[str, str] = {}

        def try_add(name: str, reason: str):
            if name in self.card_library:  # type: ignore[attr-defined]
                return
            if not ensure_capacity():
                return
            self.add_card(
                name,
                card_type='Land',
                role='kindred',
                sub_role='baseline' if reason.startswith('kindred focus') else 'tribe-specific',
                added_by='lands_step3',
                trigger_tag='Kindred/Tribal'
            )  # type: ignore[attr-defined]
            added.append(name)
            reasons[name] = reason

        # Baseline inclusions
        try_add('Path of Ancestry', 'kindred focus')
        if len(colors) <= 4:
            try_add('Cavern of Souls', f"kindred focus ({len(colors)} colors)")
        if len(colors) >= 2:
            try_add('Three Tree City', f"kindred focus ({len(colors)} colors)")

        # Dynamic tribe extraction
        tribe_terms: set[str] = set()
        for tag in (getattr(self, 'selected_tags', []) or []):
            lower = tag.lower()
            if 'kindred' in lower:
                base = lower.replace('kindred', '').strip()
                if base:
                    tribe_terms.add(base.split()[0])
            elif 'tribal' in lower:
                base = lower.replace('tribal', '').strip()
                if base:
                    tribe_terms.add(base.split()[0])

        snapshot = getattr(self, '_full_cards_df', None)
        if snapshot is not None and not snapshot.empty and tribe_terms:
            dynamic_limit = 5
            for tribe in sorted(tribe_terms):
                if self._current_land_count() >= land_target or dynamic_limit <= 0:  # type: ignore[attr-defined]
                    break
                tribe_lower = tribe.lower()
                matches: List[str] = []
                for _, row in snapshot.iterrows():
                    try:
                        nm = str(row.get('name', ''))
                        if not nm or nm in self.card_library:  # type: ignore[attr-defined]
                            continue
                        tline = str(row.get('type', row.get('type_line', ''))).lower()
                        if 'land' not in tline:
                            continue
                        text_field = row.get('text', row.get('oracleText', ''))
                        text_str = str(text_field).lower() if text_field is not None else ''
                        nm_lower = nm.lower()
                        if (tribe_lower in nm_lower or f" {tribe_lower}" in text_str or f"{tribe_lower} " in text_str or f"{tribe_lower}s" in text_str):
                            matches.append(nm)
                    except Exception:
                        continue
                for nm in matches[:2]:
                    if self._current_land_count() >= land_target or dynamic_limit <= 0:  # type: ignore[attr-defined]
                        break
                    if nm in added or nm in getattr(bc, 'BASIC_LANDS', []):
                        continue
                    try_add(nm, f"text/name references '{tribe}'")
                    dynamic_limit -= 1

        self.output_func("\nKindred Lands Added (Step 3):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                self.output_func(f"  {n.ljust(width)} : 1  ({reasons.get(n,'')})")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")  # type: ignore[attr-defined]

    def run_land_step3(self):  # type: ignore[override]
        """Public wrapper to add kindred-focused lands."""
        self.add_kindred_lands()
        self._enforce_land_cap(step_label="Kindred (Step 3)")  # type: ignore[attr-defined]


__all__ = [
    'LandKindredMixin'
]
