# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
Backend standardization infrastructure (M1-M5 complete): response builders, telemetry, service layer, validation framework, error handling integration, and testing standards. Web UI improvements with Tailwind CSS migration, TypeScript conversion, component library, template validation tests, enhanced code quality tools, and optional card image caching. Bug fixes for image cache UI, Scryfall API compatibility, and container startup errors.

### Added
- **Testing Standards Documentation**: Developer guide and base classes for writing new tests
  - `docs/web_backend/testing.md` covers route tests, service tests, HTMX patterns, naming conventions, and coverage targets
  - `code/tests/base_test_cases.py` provides `RouteTestCase`, `ServiceTestCase`, `ErrorHandlerTestCase`, `ValidationTestMixin`
- **Error Handling Integration**: Custom exceptions now wired into the web layer
  - Typed domain exceptions get correct HTTP status codes (not always 500)
  - HTMX requests receive HTML error fragments; API requests receive JSON
  - New web-specific exceptions: `SessionExpiredError`, `BuildNotFoundError`, `FeatureDisabledError`
  - Error handling guide at `docs/web_backend/error_handling.md`
- **Backend Standardization Framework**: Improved code organization and maintainability
  - Response builder utilities for standardized HTTP/JSON/HTMX responses
  - Telemetry decorators for automatic route tracking and error logging
  - Route pattern documentation with examples and migration guide
  - Modular route organization with focused, maintainable modules
  - Step-based wizard routes consolidated into dedicated module
  - New build flow and quick build automation extracted into focused module
  - Alternative card suggestions extracted to standalone module
  - Compliance/enforcement and card replacement extracted to focused module
  - Foundation for integrating custom exception hierarchy
  - Benefits: Easier to maintain, extend, and test backend code

### Removed
- **Permalink Feature**: Removed permalink generation and restoration functionality
  - Deemed unnecessary for single-session deck building workflow
  - Simplified UI by removing "Copy Permalink" and "Open Permalink" buttons
  - Users can still export decks (CSV/TXT/JSON) or use headless JSON configs for automation
- **Template Validation Tests**: Comprehensive test suite ensuring HTML/template quality
  - Validates Jinja2 syntax and structure
  - Checks for common HTML issues (duplicate IDs, balanced tags)
  - Basic accessibility validation
  - Prevents regression in template quality
- **Code Quality Tools**: Enhanced development tooling for maintainability
  - Automated utilities for code cleanup
  - Improved type checking configuration
- **Card Image Caching**: Optional local image cache for faster card display
  - Downloads card images from Scryfall bulk data (respects API guidelines)
  - Graceful fallback to Scryfall API for uncached images
  - Enabled via `CACHE_CARD_IMAGES=1` environment variable
  - Integrated with setup/tagging process
  - Statistics endpoint with intelligent caching (weekly refresh, matching card data staleness)
- **Component Library**: Living documentation of reusable UI components at `/docs/components`
  - Interactive examples of all buttons, modals, forms, cards, and panels
  - Jinja2 macros for consistent component usage
  - Component partial templates for reuse across pages
- **TypeScript Migration**: Migrated JavaScript codebase to TypeScript for better type safety
  - Converted `components.js` (376 lines) and `app.js` (1390 lines) to TypeScript
  - Created shared type definitions for state management, telemetry, HTMX, and UI components
  - Integrated TypeScript compilation into build process (`npm run build:ts`)
  - Compiled JavaScript output in `code/web/static/js/` directory
  - Docker build automatically compiles TypeScript during image creation

### Changed
- **Inline JavaScript Cleanup**: Removed legacy card hover system (~230 lines of unused code)
- **JavaScript Consolidation**: Extracted inline scripts to TypeScript modules
  - Created `cardHover.ts` for unified hover panel functionality
  - Created `cardImages.ts` for card image loading with automatic retry fallbacks
  - Reduced inline script size in base template for better maintainability
- **Migrated CSS to Tailwind**: Consolidated and unified CSS architecture
  - Tailwind CSS v3 with custom MTG color palette
  - PostCSS build pipeline with autoprefixer
  - Reduced inline styles in templates (moved to shared CSS classes)
  - Organized CSS into functional sections with clear documentation
- **Theme Visual Improvements**: Enhanced readability and consistency across all theme modes
  - Light mode: Darker text for improved readability, warm earth tone color palette
  - Dark mode: Refined contrast for better visual hierarchy
  - High-contrast mode: Optimized for maximum accessibility
  - Consistent hover states across all interactive elements
  - Improved visibility of form inputs and controls
- **JavaScript Modernization**: Updated to modern JavaScript patterns
  - Converted `var` declarations to `const`/`let`
  - Added TypeScript type annotations for better IDE support and error catching
  - Consolidated event handlers and utility functions
- **Docker Build Optimization**: Improved developer experience
  - Hot reload enabled for templates and static files
  - Volume mounts for rapid iteration without rebuilds
- **Template Modernization**: Migrated templates to use component system
- **Type Checking Configuration**: Improved Python code quality tooling
  - Configured type checker for better error detection
- **Test Suite Consolidation**: Streamlined test infrastructure for better maintainability
  - Consolidated 148 test files down to 87 (41% reduction)
  - Merged overlapping and redundant test coverage into comprehensive test modules
  - Maintained 100% pass rate (582 passing tests, 12 intentional skips)
  - Updated CI/CD workflows to reference consolidated test files
  - Improved test organization and reduced cognitive overhead for contributors
  - Optimized linting rules for development workflow
- **Intelligent Synergy Builder**: Analyze multiple builds and create optimized "best-of" deck
  - Scores cards by frequency (50%), EDHREC rank (25%), and theme tags (25%)
  - 10% bonus for cards appearing in 80%+ of builds
  - Color-coded synergy scores in preview (green=high, red=low)
  - Partner commander support with combined color identity
  - Multi-copy card tracking (e.g., 8 Mountains, 7 Islands)
  - Export synergy deck with full metadata (CSV, TXT, JSON files)
- `ENABLE_BATCH_BUILD` environment variable to toggle feature (default: enabled)
- Detailed progress logging for multi-build orchestration
- User guide: `docs/user_guides/batch_build_compare.md`
- **Web UI Component Library**: Standardized UI components for consistent design across all pages
  - 5 component partial template files (buttons, modals, forms, cards, panels)
  - ~900 lines of component CSS styles
  - Interactive JavaScript utilities (components.js)
  - Living component library page at `/docs/components`
  - 1600+ lines developer documentation (component_catalog.md)
- **Custom UI Enhancements**:
  - Darker gray styling for home page buttons
  - Visual highlighting for selected theme chips in deck builder

### Removed
_None_

### Fixed
- **Image Cache Status UI**: Setup page status stuck on "Checking…" after a failed download
  - Error state now shown correctly with failure message
  - Card count display fixed (was double-counting by summing both size variants)
  - Last download run stats ("+N new cards") persist across container restarts
- **Scryfall Bulk Data API**: HTTP 400 error fixed by adding required `Accept: application/json` header
- **Deck Summary Display**: Fixed issue where deck summary cards would not display correctly in manual builds
  - Card images and names now appear properly in both List and Thumbnails views
  - Commander card displayed correctly in Step 5 sidebar
  - Summary data now properly persists across wizard stages
- **Multi-Copy Package Detection**: Fixed multi-copy suggestions not appearing in New Deck wizard
  - Multi-copy panel now properly displays when commander and theme tags match supported archetypes
  - Example: Hare Apparent now appears when building with Rabbit Kindred + Tokens Matter themes
  - Panel styling now matches current theme (dark/light mode support)
  - Affects all 12 multi-copy archetypes in the system
- **Card Data Auto-Refresh**: Fixed stale data issue when new sets are released
  - Auto-refresh now deletes cached raw parquet file before downloading fresh data
  - Ensures new sets are included instead of reprocessing old cached data
- **Template Quality**: Resolved HTML structure issues
  - Fixed duplicate ID attributes in templates
  - Removed erroneous template block tags
  - Corrected structure for HTMX fragments
- **Code Quality**: Resolved type checking warnings and improved code maintainability
  - Fixed type annotation inconsistencies
  - Cleaned up redundant code quality suppressions
  - Corrected configuration conflicts

### Performance
- Hot reload for CSS/template changes (no Docker rebuild needed)
- Optional image caching reduces Scryfall API calls
- Faster page loads with optimized CSS
- TypeScript compilation produces optimized JavaScript

### For Users
- Faster card image loading with optional caching
- Cleaner, more consistent web UI design
- Improved page load performance
- More reliable JavaScript behavior

### Deprecated
_None_

### Security
_None_