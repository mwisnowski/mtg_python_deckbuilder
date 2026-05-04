# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
_No unreleased changes yet_

### Fixed
- **Image download 404 fallback**: When the Scryfall CDN serves a Cloudflare-cached 404 for the `default_cards` bulk data file, the image download now automatically retries with `unique_artwork` then `all_cards` before failing.

### Removed
_No unreleased changes yet_

