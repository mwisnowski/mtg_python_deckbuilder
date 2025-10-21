# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
Major new feature: Build X and Compare with Intelligent Synergy Builder. Run the same deck configuration multiple times to see variance, compare results side-by-side, and create optimized "best-of" decks.

### Added
- **Build X and Compare**: Build 1-10 decks in parallel with same configuration
  - Side-by-side comparison with card overlap statistics
  - Smart filtering of guaranteed cards
  - Rebuild button for quick iterations
  - ZIP export of all builds
- **Synergy Builder**: Create optimized deck from multiple builds
  - Intelligent scoring (frequency + EDHREC + themes)
  - Color-coded synergy preview
  - Full metadata export (CSV/TXT/JSON)
  - Partner commander support
- Feature flag: `ENABLE_BATCH_BUILD` (default: on)
- User guide: `docs/user_guides/batch_build_compare.md`

### Changed
_None_

### Removed
_None_

### Fixed
_None_

### Performance
_None_

### For Users
_No changes yet_

### Deprecated
_None_

### Security
_None_