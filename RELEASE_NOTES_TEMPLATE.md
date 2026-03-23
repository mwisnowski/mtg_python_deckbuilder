# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_

## [4.2.0] - 2026-03-23
### Highlights
- **Budget Mode**: Set a budget cap and per-card ceiling when building a deck. Prices are shown throughout the build flow, over-budget cards are highlighted, and a post-build review panel lets you swap in cheaper alternatives live.
- **Pickups List**: New page (`/decks/pickups?name=`) listing affordable cards you don't own yet, sorted by theme-match priority.
- **Price Charts**: Donut chart and histogram showing deck spend by card role (9 categories) and cost distribution.
- **Stale Price Warnings**: Cards with price data older than 24 hours are flagged with a clock indicator; a banner appears when more than half the deck's prices are stale.
- **Price Cache Refresh**: Setup page Refresh button now downloads fresh Scryfall bulk data before rebuilding the cache.
- **Multi-copy Dialogs**: Conflict dialogs for Must Include and Must Exclude when using multi-copy archetypes (e.g., Hare Apparent).
- **RandomService & Diagnostics**: Seeded RNG service with optional diagnostics endpoint (`WEB_RANDOM_DIAGNOSTICS=1`).

### Changed
- **Build Deck button**: "Create" renamed to "Build Deck" in the New Deck modal.

### Fixed
- **Stale price banner after refresh**: Refreshing prices on the Setup page now correctly clears the stale warning.
- **Multi-copy include count**: Archetype card count is now correctly applied when confirmed from the conflict dialog.
