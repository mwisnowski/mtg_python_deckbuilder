# MTG Python Deckbuilder ${VERSION}

## Highlights
- Combos & Synergies: detect curated two-card combos and synergies, surface them in a unified chip-style panel on Step 5 and Finished Decks, and preview both cards on hover.
- Auto-Complete Combos: optional mode that adds missing partners up to a target before theme fill/monolithic spells so added pairs persist.

## What’s new
- Detection: exact two-card combos and curated synergies with list version badges (combos.json/synergies.json).
- UI polish:
  - Chip-style rows with compact badges (cheap/early, setup) in both the end-of-build panel and finished deck summary.
  - Dual-card hover: moving your mouse over a combo row previews both cards side-by-side; hovering a single name shows that card alone.
- Ordering: when enabled, Auto-Complete Combos runs earlier (before theme fill and monolithic spells) to retain partners.
- Enforcement:
  - Color identity respected via the filtered pool; off-color or unavailable partners are skipped gracefully.
  - Honors Locks, Owned-only, and Replace toggles.
- Persistence & Headless parity:
  - Interactive runs export these JSON fields and Web headless runs accept them:
    - prefer_combos (bool)
    - combo_target_count (int)
    - combo_balance ("early" | "late" | "mix")

## JSON (Web Configs) — example
```json
{
  "prefer_combos": true,
  "combo_target_count": 3,
  "combo_balance": "mix"
}
```

## Notes
- Curated list versions are displayed in the UI for transparency.
- Existing completed pairs are counted toward the target; only missing partners are added.
- No changes to CLI inputs for this feature in this release.
- Headless: `tag_mode` supported from JSON/env and exported in interactive run-config JSON.

## Fixes
- Fixed an issue with the Docker Hub image not having the config files for combos/synergies/default deck json example