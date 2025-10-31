# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
Web UI improvements with Tailwind CSS migration, TypeScript conversion, component library, enhanced code quality standards, and optional card image caching for faster performance and better maintainability.

### Added
- **Code Quality Improvements**: Enhanced type checking and code quality standards
  - Configured gradual strict mode for Python type checking
  - Created automated utilities for maintaining clean codebase
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
- **Type Checking Configuration**: Adjusted mypy settings for better developer experience
  - Enabled gradual strict mode for incremental type safety improvements
  - Configured per-module strict checks for new code
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
- **Code Quality**: Resolved numerous type checking warnings and improved code maintainability
  - Fixed critical type annotation bugs
  - Removed outdated type ignore comments
  - Corrected dictionary type definitions

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