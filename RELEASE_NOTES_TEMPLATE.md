# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
Web UI improvements with Tailwind CSS migration, TypeScript conversion, component library, and optional card image caching for faster performance and better maintainability.

### Added
- **Card Image Caching**: Optional local image cache for faster card display
  - Downloads card images from Scryfall bulk data
  - Graceful fallback to Scryfall API for uncached images
  - Enable with `CACHE_CARD_IMAGES=1` environment variable
  - Intelligent statistics caching (weekly refresh, matching card data staleness)
- **Component Library**: Living documentation at `/docs/components`
  - Interactive examples of all UI components
  - Reusable Jinja2 macros for consistent design
  - Component partial templates for reuse across pages
- **TypeScript Support**: Migrated JavaScript to TypeScript for better code quality
  - Type definitions for state management, telemetry, and UI components
  - Improved IDE support with autocomplete and type checking
  - Integrated into build process (compiles during Docker build)

### Changed
- **Migrated CSS to Tailwind**: Consolidated and unified CSS architecture
  - Tailwind CSS v3 with custom MTG color palette
  - PostCSS build pipeline with autoprefixer
  - Minimized inline styles in favor of shared CSS classes
  - **Light theme visual improvements**: Warm earth tone palette with better button/panel contrast
- **JavaScript Modernization**: Updated to modern JavaScript patterns
  - Converted to TypeScript for better type safety
  - Replaced `var` with `const`/`let` throughout
  - Improved error handling and code organization
- **Docker Build Optimization**: Improved developer experience
  - Hot reload for templates and CSS (no rebuild needed)
  - TypeScript compilation integrated into build process
- **Template Modernization**: Migrated templates to use component system

### Removed
_None_

### Fixed
_None_

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

### For Developers
- TypeScript provides better IDE support and error detection
- Clear type definitions for all JavaScript utilities
- Easier onboarding with typed interfaces
- Automated build process handles TypeScript compilation

### Deprecated
_None_

### Security
_None_