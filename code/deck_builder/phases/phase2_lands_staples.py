from __future__ import annotations
from typing import List, Dict
from .. import builder_constants as bc

"""Phase 2 (part 2): Staple nonbasic lands (Land Step 2).

Extracted logic for adding generic staple lands (excluding kindred / tribal, fetches, etc.).

Provided by LandStaplesMixin:
  - _current_land_count(): counts land cards currently in library.
  - add_staple_lands(): core staple inclusion logic with capacity management.
  - run_land_step2(): public wrapper invoked by orchestrator.

Expected host DeckBuilder attributes / methods:
  - card_library (dict), output_func
  - files_to_load, determine_color_identity(), setup_dataframes()
  - ideal_counts (dict) possibly present
  - commander_tags, selected_tags, commander_row
  - helper methods: _basic_floor, _count_basic_lands, _choose_basic_to_trim, _decrement_card, _enforce_land_cap
  - builder_constants imported as bc in host package (we import locally for clarity)
"""

 # (Imports moved to top for lint compliance)


class LandStaplesMixin:
    # ---------------------------
    # Land Building Step 2: Staple Nonbasic Lands (NO Kindred yet)
    # ---------------------------
    def _current_land_count(self) -> int:  # type: ignore[override]
        """Return total number of land cards currently in the library (counts duplicates)."""
        total = 0
        for name, entry in self.card_library.items():  # type: ignore[attr-defined]
            ctype = entry.get('Card Type', '')
            if ctype and 'land' in ctype.lower():
                total += entry.get('Count', 1)
                continue
            df = getattr(self, '_combined_cards_df', None)
            if df is not None and 'name' in getattr(df, 'columns', []):
                try:
                    row = df[df['name'] == name]
                    if not row.empty:
                        type_field = str(row.iloc[0].get('type', '')).lower()
                        if 'land' in type_field:
                            total += entry.get('Count', 1)
                except Exception:
                    continue
        return total

    def add_staple_lands(self):  # type: ignore[override]
        """Add generic staple lands defined in STAPLE_LAND_CONDITIONS (excluding kindred lands).

        Respects total land target (ideal_counts['lands']). Skips additions once target reached.
        Conditions may use commander tags (all available, not just selected), color identity, and commander power.
        """
        if not getattr(self, 'files_to_load', []):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add staple lands until color identity resolved: {e}")
                return
        land_target = None
        if hasattr(self, 'ideal_counts') and getattr(self, 'ideal_counts'):
            land_target = self.ideal_counts.get('lands')  # type: ignore[attr-defined]
        if land_target is None:
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

        commander_tags_all = set(getattr(self, 'commander_tags', []) or []) | set(getattr(self, 'selected_tags', []) or [])
        colors = getattr(self, 'color_identity', []) or []
        commander_power = 0
        try:
            row = getattr(self, 'commander_row', None)
            if row is not None:
                raw_power = row.get('power')
                if isinstance(raw_power, (int, float)):
                    commander_power = int(raw_power)
                elif isinstance(raw_power, str) and raw_power.isdigit():
                    commander_power = int(raw_power)
        except Exception:
            commander_power = 0

        added: List[str] = []
        reasons: Dict[str, str] = {}
        for land_name, cond in getattr(bc, 'STAPLE_LAND_CONDITIONS', {}).items():
            if not ensure_capacity():
                self.output_func("Staple Lands: Cannot free capacity without violating basic floor; stopping additions.")
                break
            if land_name in self.card_library:  # type: ignore[attr-defined]
                continue
            try:
                include = cond(list(commander_tags_all), colors, commander_power)
            except Exception:
                include = False
            if include:
                self.add_card(
                    land_name,
                    card_type='Land',
                    role='staple',
                    sub_role='generic-staple',
                    added_by='lands_step2'
                )  # type: ignore[attr-defined]
                added.append(land_name)
                if land_name == 'Command Tower':
                    reasons[land_name] = f"multi-color ({len(colors)} colors)"
                elif land_name == 'Exotic Orchard':
                    reasons[land_name] = f"multi-color ({len(colors)} colors)"
                elif land_name == 'War Room':
                    reasons[land_name] = f"<=2 colors ({len(colors)})"
                elif land_name == 'Reliquary Tower':
                    reasons[land_name] = 'always include'
                elif land_name == 'Ash Barrens':
                    reasons[land_name] = 'no Landfall tag'
                elif land_name == "Rogue's Passage":
                    reasons[land_name] = f"commander power {commander_power} >=5"
        self.output_func("\nStaple Lands Added (Step 2):")
        if not added:
            self.output_func("  (None added)")
        else:
            width = max(len(n) for n in added)
            for n in added:
                reason = reasons.get(n, '')
                self.output_func(f"  {n.ljust(width)} : 1  {('(' + reason + ')') if reason else ''}")
        self.output_func(f"  Land Count Now : {self._current_land_count()} / {land_target}")  # type: ignore[attr-defined]

    def run_land_step2(self):  # type: ignore[override]
        """Public wrapper for adding generic staple nonbasic lands (excluding kindred)."""
        self.add_staple_lands()
        self._enforce_land_cap(step_label="Staples (Step 2)")  # type: ignore[attr-defined]
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '2')
        except Exception:
            pass


__all__ = [
    'LandStaplesMixin'
]
