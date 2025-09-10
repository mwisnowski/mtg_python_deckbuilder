from __future__ import annotations
from typing import Dict, Optional
from .. import builder_constants as bc
import os

"""Phase 2 (part 1): Basic land addition logic (Land Step 1).

Extracted from the monolithic `builder.py` to begin modularizing land building.

Responsibilities provided by this mixin:
  - add_basic_lands(): core allocation & addition of basic (or snow) lands.
  - run_land_step1(): public wrapper invoked by the deck build orchestrator.

Expected attributes / methods on the host DeckBuilder:
  - color_identity, selected_tags, commander_tags, ideal_counts
  - determine_color_identity(), setup_dataframes(), add_card()
  - output_func for user messaging
  - bc (builder_constants) imported in builder module; we import locally here.
"""

 # (Imports moved to top for lint compliance)


class LandBasicsMixin:
    def add_basic_lands(self):  # type: ignore[override]
        """Add basic (or snow basic) lands based on color identity.

        Logic:
          - Determine target basics = ceil(1.3 * ideal_basic_min) (rounded) but capped by total land target
          - Evenly distribute among colored identity letters (W,U,B,R,G)
          - If commander/selected tags include 'Snow' (case-insensitive) use snow basics mapping
          - Colorless commander: use Wastes for the entire basic allocation
        """
        # Ensure color identity determined
        if not getattr(self, 'files_to_load', []):
            try:
                self.determine_color_identity()
                self.setup_dataframes()
            except Exception as e:  # pragma: no cover - defensive
                self.output_func(f"Cannot add basics until color identity resolved: {e}")
                return

        # DEBUG EXPORT: write full land pool snapshot the first time basics are added
        # Purpose: allow inspection of all candidate land cards before other land steps mutate state.
        try:  # pragma: no cover (diagnostic aid)
            full_df = getattr(self, '_combined_cards_df', None)
            marker_attr = '_land_debug_export_done'
            if full_df is not None and not getattr(self, marker_attr, False):
                land_df = full_df
                # Prefer 'type' column (common) else attempt 'type_line'
                col = 'type' if 'type' in land_df.columns else ('type_line' if 'type_line' in land_df.columns else None)
                if col:
                    work = land_df[land_df[col].fillna('').str.contains('Land', case=False, na=False)].copy()
                    if not work.empty:
                        os.makedirs(os.path.join('logs', 'debug'), exist_ok=True)
                        export_cols = [c for c in ['name','type','type_line','manaValue','edhrecRank','colorIdentity','manaCost','themeTags','oracleText'] if c in work.columns]
                        path = os.path.join('logs','debug','land_test.csv')
                        try:
                            if export_cols:
                                work[export_cols].to_csv(path, index=False, encoding='utf-8')
                            else:
                                work.to_csv(path, index=False, encoding='utf-8')
                        except Exception:
                            work.to_csv(path, index=False)
                        self.output_func(f"[DEBUG] Wrote land_test.csv ({len(work)} rows)")
                        setattr(self, marker_attr, True)
        except Exception:
            pass

        # Ensure ideal counts (for min basics & total lands)
        basic_min: Optional[int] = None
        land_total: Optional[int] = None
        if hasattr(self, 'ideal_counts') and getattr(self, 'ideal_counts'):
            basic_min = self.ideal_counts.get('basic_lands')  # type: ignore[attr-defined]
            land_total = self.ideal_counts.get('lands')  # type: ignore[attr-defined]
        if basic_min is None:
            basic_min = getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20)
        if land_total is None:
            land_total = getattr(bc, 'DEFAULT_LAND_COUNT', 35)

        # Target basics = 1.3 * minimum (rounded) but not exceeding total lands
        target_basics = int(round(1.3 * basic_min))
        if target_basics > land_total:
            target_basics = land_total
        if target_basics <= 0:
            self.output_func("Target basic land count is zero; skipping basics.")
            return

        colors = [c for c in getattr(self, 'color_identity', []) if c in ['W', 'U', 'B', 'R', 'G']]
        if not colors:  # colorless special case -> Wastes only
            colors = []

        # Determine if snow preferred
        selected_tags = getattr(self, 'selected_tags', []) or []
        commander_tags = getattr(self, 'commander_tags', []) or []
        tag_pool = selected_tags + commander_tags
        use_snow = any('snow' in str(t).lower() for t in tag_pool)
        snow_map = getattr(bc, 'SNOW_BASIC_LAND_MAPPING', {})
        basic_map = getattr(bc, 'COLOR_TO_BASIC_LAND', {})

        allocation: Dict[str, int] = {}
        if not colors:  # colorless
            allocation_name = snow_map.get('C', 'Wastes') if use_snow else 'Wastes'
            allocation[allocation_name] = target_basics
        else:
            n = len(colors)
            base = target_basics // n
            rem = target_basics % n
            for idx, c in enumerate(sorted(colors)):  # sorted for deterministic distribution
                count = base + (1 if idx < rem else 0)
                land_name = snow_map.get(c) if use_snow else basic_map.get(c)
                if not land_name:
                    continue
                allocation[land_name] = allocation.get(land_name, 0) + count

        # Add to library
        for land_name, count in allocation.items():
            for _ in range(count):
                # Role metadata: basics (or snow basics)
                self.add_card(
                    land_name,
                    card_type='Land',
                    role='basic',
                    sub_role='snow-basic' if use_snow else 'basic',
                    added_by='lands_step1',
                    trigger_tag='Snow' if use_snow else None
                )

        # Summary output
        self.output_func("\nBasic Lands Added:")
        width = max((len(n) for n in allocation.keys()), default=0)
        for name, cnt in allocation.items():
            self.output_func(f"  {name.ljust(width)} : {cnt}")
        self.output_func(f"  Total Basics : {sum(allocation.values())} (Target {target_basics}, Min {basic_min})")

    def run_land_step1(self):  # type: ignore[override]
        """Public wrapper to execute land building step 1 (basics)."""
        self.add_basic_lands()
        try:
            from .. import builder_utils as _bu
            _bu.export_current_land_pool(self, '1')
        except Exception:
            pass


__all__ = [
    'LandBasicsMixin'
]
