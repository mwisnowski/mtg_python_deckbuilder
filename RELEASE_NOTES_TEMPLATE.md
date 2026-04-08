# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Potential Upgrades page**: New page accessible from any saved deck's view, surfacing card suggestions in two pools:
  - **New Cards** — first printings only (no reprints) from the last three expansion release windows or the last six months, whichever covers more ground; excludes cards already in your deck
  - **General Upgrades** — full legal card pool filtered to your deck's color identity, with meaningful theme and role overlap; cards that fill gaps in your current role spread rank higher
  - Each suggestion shows 3+ swap targets from your current deck — cards the algorithm considers reasonable cuts based on role overlap and mana cost; commander and locked cards are never suggested as swap targets
  - Synergy fit score (teal pill) on each suggestion; amber replaceability score (1–10) on each swap target — the two scores measure different things and are not directly comparable
  - Hover any card for the full detail panel: matched tags, role overlap, swap reasoning, price, and card image
  - Expandable score formula explainer at the top of the page, with a plain-English disclaimer about what the algorithm can and cannot account for
  - New Cards window label shows full set names and date range, updated dynamically (e.g., at time of implementation: "Final Fantasy Commander, Lorwyn Eclipsed, TMNT (Oct 2025 – Mar 2026)")
  - Paginated display (16 cards per page by default)
  - Configurable via `ENABLE_UPGRADE_SUGGESTIONS`, `UPGRADE_PAGE_SIZE`, and `UPGRADE_WINDOW_MONTHS` environment variables
- **User guide**: `docs/user_guides/suggested_upgrades.md` covering both pools, scoring formulas, swap target interpretation, caveats, and environment variables; accessible via the in-app help portal at `/help`

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_

