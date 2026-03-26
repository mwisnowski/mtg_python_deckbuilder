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

## [4.3.2] - 2026-03-25
### Added
- **Smart Land Bases checkbox**: The New Deck modal now has a **Smart Land Bases** checkbox in the Preferences section (checked by default). Enables or disables smart land analysis per-build without needing environment variables.

### Removed
- **`ENABLE_SMART_LANDS` environment variable**: Replaced by the per-build checkbox. Use `LAND_PROFILE` or `LAND_COUNT` for headless overrides.

## [4.3.1] - 2026-03-25
### Added
- **Smart Land Bases**: Land count and basic-to-dual ratio are now adjusted automatically based on the commander's speed and color-pip intensity. Controlled by `ENABLE_SMART_LANDS=1` (default on in Docker).
  - **Speed detection**: Commander CMC determines a speed category applied as an offset to the user's configured ideal land count. Fast (CMC < 3) = −2 lands, mid = ±0, slow (CMC > 4) = +2 to +4 scaling with color count.
  - **Profile selection**: Basics-heavy (~60% basics) for 1–2 color / low-pip decks; Balanced for moderate pip density; Fixing-heavy (minimal basics, more duals/fetches) for 3+ color or high-pip pools (≥15 double-pip or ≥3 triple-or-more-pip cards).
  - **ETB tapped tolerance** is automatically tightened for fast decks and loosened for slow decks.
  - **Budget override**: Low-budget 3+ color decks are pushed to basics-heavy automatically.
  - **Slot earmarking**: Non-land ideal counts are scaled to fit within the remaining slots after the land target is set.
  - **Backfill**: A final land step pads with basics if any land phase falls short.
  - Override with `LAND_PROFILE=basics|mid|fixing` or `LAND_COUNT=<n>`. A **Smart Lands** notice in the Land Summary explains the chosen profile.

### Changed
_No changes_

### Fixed
_No changes_

### Removed
_No changes_
