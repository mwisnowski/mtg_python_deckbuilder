# MTG Python Deckbuilder

## [Unreleased]
### Added
- **RandomService**: Service wrapper for seeded RNG with validation (`code/web/services/random_service.py`)
- **Random diagnostics**: `GET /api/random/diagnostics` endpoint (requires `WEB_RANDOM_DIAGNOSTICS=1`)
- **Random Mode docs**: `docs/random_mode/` covering seed infrastructure, developer guide, and diagnostics
- **Multi-copy include dialog**: Typing a multi-copy archetype card (e.g., Hare Apparent) in Must Include now triggers a popup to choose copy count and optional Thrumming Stone inclusion
- **Multi-copy/exclude conflict dialog**: Selecting a multi-copy archetype while the same card is in the Exclude list now shows a resolution popup — keep the archetype (removes from excludes) or keep the exclude (disables archetype)

### Changed
_No unreleased changes yet_

### Fixed
- **Multi-copy include count**: Archetype cards in Must Include now inject the correct count instead of always adding 1 copy

### Removed
_No unreleased changes yet_
