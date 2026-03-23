# MTG Python Deckbuilder

## [Unreleased]
### Added
- **RandomService**: New `code/web/services/random_service.py` service class wrapping seeded RNG operations with input validation and the R9 `BaseService` pattern
- **InvalidSeedError**: New `InvalidSeedError` exception in `code/exceptions.py` for seed validation failures
- **Random diagnostics endpoint**: `GET /api/random/diagnostics` behind `WEB_RANDOM_DIAGNOSTICS=1` flag, returning seed derivation test vectors for cross-platform consistency checks
- **Random Mode documentation**: New `docs/random_mode/` directory with `seed_infrastructure.md`, `developer_guide.md`, and `diagnostics.md`
- **Multi-copy / Include conflict dialog**: When a known multi-copy archetype card (e.g., Hare Apparent) is typed in the Must Include field of the New Deck modal, a popup now appears asking how many copies to include, with an optional Thrumming Stone checkbox
- **Multi-copy / Exclude conflict dialog**: When a multi-copy archetype is selected via the Multi-Copy Package selector and the same card also appears in the Must Exclude field, a conflict popup lets you choose to keep the multi-copy (removing it from excludes) or keep the exclude (disabling the archetype selection)
- **Budget Mode**: Full budget-aware deck building with price integration
  - Budget configuration on the New Deck modal: set a total budget cap, optional per-card ceiling, and soft/hard enforcement mode
  - Price display during building: card prices shown next to card names in list and thumbnail views throughout the build pipeline
  - Running budget counter chip updates as each build stage completes
  - Over-budget card highlight: cards exceeding the per-card ceiling are marked with a yellow/gold border
  - Basic lands excluded from all budget calculations
  - Budget summary bar in the deck summary view with under/over color coding
  - Budget badge and over-budget panel on the saved deck view
  - Pickups list page (`/decks/{name}/pickups`) sorted by priority tier
  - Pool budget filter: cards exceeding the per-card ceiling by more than the pool tolerance (default 15%, configurable per build in the New Deck modal) are excluded from the candidate pool before building begins
  - Card price shown in the hover and tap popup for all card tiles with a cached price
  - Price shown inline on each alternative card suggestion in the alternatives panel
  - Post-build budget review panel appears when the final deck total exceeds the budget cap by more than 10%; lists over-budget cards sorted by overage with up to 3 cheaper alternatives each
  - Alternatives in the review panel are matched by card type (lands suggest land alternatives, creatures suggest creature alternatives) and sorted by role similarity using shared strategy tags
  - Each alternative has a Swap button that replaces the card in the finalized deck and re-evaluates the budget live; the panel auto-dismisses when the total drops within tolerance
  - "Accept deck as-is" button in soft mode lets you bypass the review and proceed to export
  - Build complete screen shows a minimal action bar (Restart build / New build / Back) instead of the full stage ribbon
  - Controlled by `ENABLE_BUDGET_MODE` environment variable (default: enabled)
- **Price Cache Infrastructure**: Improved price data lifecycle
  - `price` and `price_updated` columns added to parquet card database via `refresh_prices_parquet()`
  - `PRICE_AUTO_REFRESH=1`: optional daily 1 AM UTC scheduled price cache rebuild
  - `PRICE_LAZY_REFRESH=1`: background per-card price refresh for cards not updated in 7 days (default: enabled)
  - `POST /api/price/refresh`: manual price cache rebuild trigger
  - "Card Price Cache Status" section on the Setup page with last-updated date and Refresh button
  - Footer now shows the price data date alongside the Scryfall attribution
- **Price charts**: Visual cost breakdown added to the deck summary and build complete screens
  - Donut/bar chart showing total deck spend by card role category (commander, ramp, card draw, lands, etc.)
  - Price histogram showing card count distribution across cost buckets
  - Basic lands excluded from all chart calculations
- **Stale price warnings**: Cards with price data older than 24 hours are flagged with a subtle clock indicator (⏱) on card tiles, the hover popup, the budget review panel, and the Pickups page; if more than half the deck's prices are stale a single banner is shown instead of per-card indicators; controlled by `PRICE_STALE_WARNING_HOURS` (default: 24; set to 0 to disable)

### Changed
- **Create Button in New Dock Panel**: Button has been renamed to "Build Deck" for consistency with phrasing on the "Quick Build" button

### Fixed
- **Multi-copy include count**: Typing an archetype card in Must Include no longer adds only 1 copy — the archetype count is now respected when the dialog is confirmed

### Removed
_No unreleased changes yet_
