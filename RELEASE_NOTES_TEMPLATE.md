# MTG Python Deckbuilder ${VERSION}

### Summary
New card browser for exploring and discovering cards with advanced filters, similar card recommendations, and fast performance.

### Added
- **Card Browser**: Browse and search all 29,839 Magic cards at `/browse/cards`
  - Smart autocomplete with typo tolerance for card names and themes
  - Multi-theme filtering (up to 5 themes)
  - Color, type, rarity, CMC, power/toughness filters
  - Multiple sorting options including EDHREC popularity
  - Infinite scroll with shareable URLs
- **Card Detail Pages**: Individual card pages with similar card suggestions
  - Enable with `ENABLE_CARD_DETAILS=1` environment variable
  - Full card stats, oracle text, and theme tags
  - Similar cards based on theme overlap with color-coded scores
  - Card preview on hover
- **Similarity Cache**: Pre-computed card similarities for instant page loads
  - Build cache with `python -m code.scripts.build_similarity_cache_parquet --parallel`
  - Control with `SIMILARITY_CACHE_ENABLED` environment variable
- **Keyboard Shortcuts**: Quick navigation
  - `Enter` to add autocomplete matches
  - `Shift+Enter` to apply filters  
  - Double `Esc` to clear all filters

### Changed
- **Card Database**: Expanded to 29,839 cards (from 26,427)
- **Theme Catalog**: Improved coverage and filtering

### Removed
- **Unused Scripts**: Removed redundant `regenerate_parquet.py`

### Fixed
- **Card Browser**: Improved UI consistency and image loading
- **Infinite Scroll**: No more duplicate cards when loading more
- **Sorting**: Sort order now persists correctly across pages
