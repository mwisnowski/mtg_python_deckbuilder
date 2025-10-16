# MTG Python Deckbuilder ${VERSION}

### Summary
Theme catalog improvements with faster processing, tag search features, regeneration fixes, and browser performance optimizations.

### Added
- **Theme Catalog Optimization**:
  - Consolidated theme enrichment pipeline
  - Tag search API for theme-based card discovery
  - Commander browser theme autocomplete with keyboard navigation
  - Tag index for faster queries
- **Theme Browser Keyboard Navigation**: Arrow keys navigate search results (ArrowUp/Down, Enter, Escape)
- **Card Data Consolidation** (from previous release):
  - Optimized format with smaller file sizes
  - "Rebuild Card Files" button in Setup page
  - Automatic updates after tagging/setup

### Changed
- **Theme Browser Performance**: Theme pages now load much faster
- **Theme Browser UI**: Removed color filter for cleaner interface

### Fixed
- **Theme Regeneration**: Theme catalog can now be fully rebuilt from scratch
  - Fixed placeholder data appearing in fresh installations
  - Examples now generated from actual card data
