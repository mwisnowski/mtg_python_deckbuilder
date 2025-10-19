# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
Performance improvements and bug fixes for commander selection and display.

### Added
_None_

### Changed
_None_

### Removed
_None_

### Fixed
- **Color Identity Display**: Fixed commander color identity showing incorrectly as "Colorless (C)" for non-partner commanders in the summary panel

### Performance
- **Commander Selection Speed**: Dramatically improved response time from 4+ seconds to under 1 second
  - Implemented intelligent caching for card data to eliminate redundant file loading
  - Both commander data and full card database now cached with automatic refresh when data updates

### For Users
- Commander selection is now **much faster** - expect sub-second response times
- Color identity labels in deck summaries now display correctly for all commanders

### Deprecated
_None_

### Security
_None_