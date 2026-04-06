# Changelog
This format follows Keep a Changelog principles and aims for Semantic Versioning.

## How we version
- Semantic Versioning: MAJOR.MINOR.PATCH (e.g., v1.2.3). Pre-releases use -alpha/-beta/-rc.
- Tags are created as `vX.Y.Z` on the default branch; releases and Docker images use that exact version and `latest`.
- Change entries prefer the Keep a Changelog types: Added, Changed, Fixed, Removed, Deprecated, Security.
- Link PRs/issues inline when helpful, e.g., (#123) or [#123]. Reference-style links at the bottom are encouraged for readability.

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
_No unreleased changes yet_

### Fixed
- **Card hover preview in theme browser (#70)**: Example card thumbnails in the theme detail/browser page were showing the wrong card image (a fuzzy search for "Card") when hovered. The `<img>` elements inside `.ex-card` containers lacked `data-card-name` attributes, so the hover system fell back to the literal string "Card". Added `data-card-name`, `data-original-name`, `data-role`, and `data-tags` to example card `<img>` elements in `detail_fragment.html` to match the existing commander image pattern.

### Removed
_No unreleased changes yet_

## [4.6.3] - 2026-04-04
### Fixed
- **CK prices not loading after GitHub cache download**: The `PriceService` singleton sets `_ck_loaded = True` as a graceful fallback when `ck_prices_cache.json` is missing at startup, preventing it from reloading the file if it is later written to disk. Added `invalidate_ck_cache()` to `PriceService`; the `Download from GitHub` route and the orchestrator auto-download now call it after successfully downloading `ck_prices_cache.json`, so CK prices appear immediately without a container restart.

## [4.6.2] - 2026-04-04
### Fixed
- **CK prices missing after GitHub cache download**: `ck_prices_cache.json` was not included in the files committed to `similarity-cache-data` by the build workflow, nor fetched by the `Download from GitHub` button or the orchestrator auto-download flow. All three paths now include the file (graceful 404 handling preserves backward compatibility with existing cache branches).
- **`commander_cards.parquet` missing from orchestrator download**: The orchestrator's auto-download list was missing `commander_cards.parquet`, which the route handler already included. Both lists are now consistent.

## [4.6.1] - 2026-04-04
### Added
- **Card Kingdom prices**: All price displays now show both TCGPlayer (TCG) and Card Kingdom (CK) prices side by side
  - Card tile overlays and inline pricing in deck summary, build wizard, and Pickups page
  - Card hover panel
  - Upgrade Suggestions table
  - Alternatives and budget review panels
  - Card browser grid tiles
  - Theme detail example cards and commanders
  - Similar cards panel on card detail pages
  - Price stat block on individual card detail pages (fetched live via API)
- **Price source legend**: "TCG = TCGPlayer · CK = Card Kingdom" label added to the deck summary and Pickups pages for clarity
- **Shopping cart export**: One-click deck purchasing via TCGPlayer and Card Kingdom
  - **Upgrade Suggestions page**: Per-card checkboxes with select-all toggle; "Open in TCGPlayer" and "Open in Card Kingdom" buttons copy the selected card list to the clipboard and open the vendor's mass-entry page in a new tab
  - **Finished deck view**: "Buy This Deck" toolbar with the same TCGPlayer and Card Kingdom buttons for the complete deck list (commander + all 99 cards)
  - Clipboard copy shows a confirmation toast; falls back to a copyable text area if clipboard API is unavailable

### Changed
- **"Upgrade Suggestions" rename**: The Pickups page and its button in the deck view are now labelled "Upgrade Suggestions" for clarity

### Fixed
- **Commander hover panel triggered by entire sidebar**: Hovering any element inside the left-hand card preview column (buttons, text, etc.) incorrectly triggered the commander card hover panel; panel now only activates when hovering the commander image or its direct container
- **Commander hover panel missing prices**: Price information was not shown in the commander card hover panel on the finished deck and run-result views; a price overlay is now attached to the commander image so TCG and CK prices load into the hover panel

## [4.5.3] - 2026-04-02
### Added
- **SBOM & supply chain provenance**: Every tagged release now attaches source SBOMs (SPDX + CycloneDX JSON) for Python dependencies and a CycloneDX container image SBOM to the GitHub Release assets. Build provenance attestations (SLSA-style) are published for the multi-arch Docker image via the GitHub Attestations API. `provenance: mode=max` is enabled on all arch builds.

## [4.5.2] - 2026-04-01
### Added
- **Hover-intent prefetch** (`WEB_PREFETCH=1`): Hovering over an "Open" button on the Finished Decks page now prefetches the deck view in the background after a 100 ms delay, eliminating the CSV-parse wait on click. Falls back to `rel=prefetch` on all browsers (Speculation Rules API infrastructure included for future side-effect-free GET routes). Feature-flagged and off by default; respects Data Saver / 2G connections.

## [4.5.1] - 2026-04-01
### Added
- **Web documentation portal**: All 13 user guides are now accessible at `/help` directly in the app — no need to navigate to GitHub. A guide index lists every guide with a description; each guide page renders full markdown with heading anchors for deep linking.
- **In-guide table of contents**: Each guide page displays a sidebar with an auto-generated "On This Page" section linking to all headings in the current guide. Collapses to a hamburger toggle on mobile.
- **Contextual help links**: Small help icons throughout the build wizard, bracket selector, owned cards mode, partner selection, and other UI areas link directly to the relevant guide section in a new tab — without interrupting the current workflow.
- **Documentation: Multi-Copy Package guide**: New dedicated guide covers all multi-copy card archetypes, count recommendations, exclusive groups, bracket interaction, and FAQ.
- **Documentation: See Also cross-links**: All 13 user guides end with a See Also section linking to related guides.
- **Documentation: FAQ sections**: FAQ sections added to 5 guides (Bracket Compliance, Include/Exclude, Locks/Replace/Permalinks, Owned Cards, Budget Mode).
- **Documentation: quality scoring and enforcement detail**: `theme_browser.md` documents the 4-factor badge scoring formula; `bracket_compliance.md` includes a full enforcement matrix.
- **Consistent page headers**: All pages now share a unified header style — same font size, description line, and separator — replacing the previous mix of different heading sizes and layouts.
- **"Help & Guides" button on home page**: Quick link to the documentation portal from the home page.

### Changed
- **Docker: `docs/` volume mount added**: `docker-compose.yml` and `dockerhub-docker-compose.yml` now mount `./docs` so documentation edits reflect immediately without a container rebuild.

### Fixed
- **Bug: missing `idx` argument** in `project_detail()` call inside `theme_preview.py` caused theme preview pages to crash.
- **Bug: `build_permalinks` router not mounted** in `app.py` caused all permalink-related endpoints to return 404.
- **Pydantic V2 deprecation warning** silenced: `DeckExportRequest` now uses `model_config = ConfigDict(...)` instead of the deprecated inner `class Config`.

### Removed
- **16 test files deleted**: 5 stale/broken tests and 11 single-test files merged into their domain equivalents to reduce fragmentation.
- **7 permanently-skipped tests removed**: 3 obsolete `apply_combo_tags` tests (API changed), 2 obsolete commander catalog tests (parquet architecture), and 2 "run manually" performance tests that never ran in CI.

## [4.4.2] - 2026-03-26
### Added
- **Community links**: GitHub repo, issue tracker, feature request, and DockerHub links now appear in the site footer and on the home page.
- **Feature request templates**: Three GitHub issue templates added — General Theme Request, Commander-Specific Theme Request, and Other Feature Request — accessible directly from the Themes page, Commanders page, and home page respectively.
- **Theme & Commander feedback prompts**: A short prompt linking to the appropriate feature request template appears at the top of the Themes catalog and Commanders pages.

## [4.3.2] - 2026-03-25
### Added
- **Smart Land Bases checkbox**: The New Deck modal Preferences section now has a **Smart Land Bases** checkbox (checked by default) to enable or disable smart land analysis per-build, replacing the `ENABLE_SMART_LANDS` environment variable.

### Removed
- **`ENABLE_SMART_LANDS` environment variable**: Removed in favor of the per-build checkbox in the New Deck modal. Use `LAND_PROFILE` or `LAND_COUNT` for headless/CLI control.

## [4.3.1] - 2026-03-25
### Added
- **Smart Land Bases**: Land count and basic-to-dual ratio are now adjusted automatically based on the commander's speed and color-pip intensity. Controlled by `ENABLE_SMART_LANDS=1` (default on in Docker).
  - **Speed detection**: Commander CMC determines a speed category applied as an offset to the user's configured ideal land count. Fast decks (CMC < 3) get −2 lands, mid decks stay at ±0, slow decks (CMC > 4) get +2 to +4 lands scaling with color count (e.g. a user-set ideal of 40 yields 38 / 40 / 42–44).
  - **Profile selection**: Three mana-base profiles are available — *Basics-heavy* (~60% basics, for 1–2 color or low-pip decks), *Balanced* (standard ratios, 2–3 colors with moderate pip density), and *Fixing-heavy* (minimal basics, more duals/fetches, for 3+ color decks or pools with ≥15 double-pip or ≥3 triple-or-more-pip cards).
  - **ETB tapped tolerance**: Automatically tightened for fast decks and loosened for slow decks so the land selection step respects the chosen speed profile.
  - **Budget override**: Decks with a low budget cap and 3+ colors are automatically pushed to the basics-heavy profile to keep non-basic land costs down.
  - **Slot earmarking**: After setting the land target, non-land ideal counts (creatures, spells, etc.) are scaled down proportionally to fit within the remaining slots, ensuring land phases always have room to fill their target.
  - **Backfill**: A final land step pads with basics if any land phase falls short, guaranteeing the deck reaches the configured target.
  - **Overrides**: Force a specific profile with `LAND_PROFILE=basics|mid|fixing` or a fixed total with `LAND_COUNT=<n>` to bypass auto-detection entirely.
  - A **Smart Lands** notice in the Land Summary section explains the chosen profile and targets in plain English.

### Changed
_No changes_

### Fixed
_No changes_

### Removed
_No changes_

## [4.2.1] - 2026-03-23
### Fixed
- **Budget/price CSS missing from DockerHub builds**: Budget badges, price chart bars, stale price indicators, and card price overlays were invisible when pulling the image from DockerHub because the CSS was only in the compiled `styles.css` output and not in the `tailwind.css` source; the Docker build deletes and regenerates `styles.css`, wiping all custom classes. All budget/price CSS now lives in `tailwind.css` so it survives the rebuild.
- **Workflow price cache build**: `_rebuild_cache()` raised `AttributeError: 'PriceService' has no attribute '_lazy_ts'` in CI because `_lazy_ts` is only initialized by `start_lazy_refresh()`, which the web app calls on startup but the CI setup script does not. Added a `hasattr` guard to lazy-initialize `_lazy_ts` on first use inside `_rebuild_cache()`.

## [4.2.0] - 2026-03-23
### Added
- **RandomService**: New `code/web/services/random_service.py` service class wrapping seeded RNG operations with input validation and the R9 `BaseService` pattern
- **InvalidSeedError**: New `InvalidSeedError` exception in `code/exceptions.py` for seed validation failures
- **Random diagnostics endpoint**: `GET /api/random/diagnostics` behind `WEB_RANDOM_DIAGNOSTICS=1` flag, returning seed derivation test vectors for cross-platform consistency checks
- **Random Mode documentation**: New `docs/random_mode/` directory with `seed_infrastructure.md`, `developer_guide.md`, and `diagnostics.md`
- **Multi-copy / Include conflict dialog**: When a known multi-copy archetype card (e.g., Hare Apparent) is typed in the Must Include field of the New Deck modal, a popup now appears asking how many copies to include, with an optional Thrumming Stone checkbox
- **Multi-copy / Exclude conflict dialog**: When a multi-copy archetype is selected via the Multi-Copy Package selector and the same card also appears in the Must Exclude field, a conflict popup lets you choose to keep the multi-copy (removing it from excludes) or keep the exclude (disabling the archetype selection)
- **Budget Mode**: Full budget-aware deck building with price integration
  - Budget configuration on the New Deck modal: set a total budget cap, optional per-card ceiling, and soft/hard enforcement mode
  - Price display during building: card prices shown next to card names in list and thumbnail views throughout the build pipeline
  - Running budget counter chip updates as each build stage completes
  - Over-budget card highlight: cards exceeding the per-card ceiling are marked with a yellow/gold border
  - Basic lands excluded from all budget calculations
  - Budget summary bar in the deck summary view with under/over color coding
  - Budget badge and over-budget panel on the saved deck view
  - Pickups list page (`/decks/pickups?name=`) sorted by priority tier
  - Pool budget filter: cards exceeding the per-card ceiling by more than the pool tolerance (default 15%, configurable per build in the New Deck modal) are excluded from the candidate pool before building begins
  - Card price shown in the hover and tap popup for all card tiles with a cached price
  - Price shown inline on each alternative card suggestion in the alternatives panel
  - Post-build budget review panel appears when the final deck total exceeds the budget cap by more than 10%; lists over-budget cards sorted by overage with up to 3 cheaper alternatives each
  - Alternatives in the review panel are matched by card type (lands suggest land alternatives, creatures suggest creature alternatives) and sorted by role similarity using shared strategy tags
  - Each alternative has a Swap button that replaces the card in the finalized deck and re-evaluates the budget live; the panel auto-dismisses when the total drops within tolerance
  - "Accept deck as-is" button in soft mode lets you bypass the review and proceed to export
  - Build complete screen shows a minimal action bar (Restart build / New build / Back) instead of the full stage ribbon
  - Controlled by `ENABLE_BUDGET_MODE` environment variable (default: enabled)
- **Price Cache Infrastructure**: Improved price data lifecycle
  - `price` and `price_updated` columns added to parquet card database via `refresh_prices_parquet()`
  - `PRICE_AUTO_REFRESH=1`: optional daily 1 AM UTC scheduled price cache rebuild
  - `PRICE_LAZY_REFRESH=1`: background per-card price refresh for cards not updated in 7 days (default: enabled)
  - `POST /api/price/refresh`: manual price cache rebuild trigger
  - "Card Price Cache Status" section on the Setup page with last-updated date and Refresh button
  - Footer now shows the price data date alongside the Scryfall attribution
- **Price charts**: Visual cost breakdown added to the deck summary and build complete screens
  - Donut/bar chart showing total deck spend by card role category (9 categories: Land, Ramp, Creature, Card Draw, Removal, Wipe, Protection, Synergy, Other)
  - Price histogram showing card count distribution across cost buckets
  - Basic lands excluded from all chart calculations
- **Stale price warnings**: Cards with price data older than 24 hours are flagged with a subtle clock indicator (⏱) on card tiles, the hover popup, the budget review panel, and the Pickups page; if more than half the deck's prices are stale a single banner is shown instead of per-card indicators; controlled by `PRICE_STALE_WARNING_HOURS` (default: 24; set to 0 to disable)

### Changed
- **Create Button in New Deck Modal**: Button has been renamed to "Build Deck" for consistency with phrasing on the "Quick Build" button

### Fixed
- **Multi-copy include count**: Typing an archetype card in Must Include no longer adds only 1 copy — the archetype count is now respected when the dialog is confirmed
- **Stale price banner after refresh**: Refreshing the price cache on the Setup page now correctly clears the stale price warning

### Removed
_No changes_

## [4.1.0] - 2026-03-20
### Added
- **Deck Builder Theme Selection**: Enhanced theme picker with pool size indicators, smart sorting, and optional grouping
  - **Pool Size Badges**: Numeric card count displayed on all theme chips (recommended + general)
  - **Smart Sorting**: Themes automatically sorted by pool size (descending), then alphabetically
  - **Visual Separator**: Clear separation between recommended and general themes with section headers
  - **Pool Size Sections**: Optional grouping of themes into Vast/Large/Moderate/Small/Tiny sections, controlled by `THEME_POOL_SECTIONS` environment variable (default: off)
  - **Popup Wizard Parity**: New Deck modal has full feature parity with the legacy builder (badges, sorting, sections)
  - **Partner-Aware Sections**: When a partner commander is selected, partner themes are bucketed into the correct pool size section rather than appended flat
  - **Pool Size Tooltips**: Section headers and the "All Available Themes" label include tooltips explaining what the card count badge means and the tier thresholds
  - **Badge Styling**: Muted, compact pool size badges integrated seamlessly into chip design
- **Theme Quality Dashboard**: Diagnostic dashboard for monitoring catalog health at `/diagnostics/quality`
  - **Quality Distribution**: Visual breakdown of theme counts by tier (Excellent/Good/Fair/Poor)
  - **Catalog Statistics**: Total themes, average quality score displayed prominently
  - **Top 10 Highest Quality**: Best-curated themes with links to theme pages
  - **Bottom 10 Lowest Quality**: Themes needing improvement with actionable suggestions
  - **Improvement Tools**: Direct links to linter CLI command and editorial documentation
  - **Protected Access**: Dashboard gated behind SHOW_DIAGNOSTICS=1 flag for admin use
  - **Main Diagnostics Integration**: Quality stats preview card on main diagnostics page with link to full dashboard
- **Theme Badge Explanations**: Detailed reasoning for quality, pool size, and popularity badges on individual theme pages
  - **Quality Explanations**: Multi-factor breakdown showing synergy breakdown (curated/enforced/inferred counts), deck archetype classification, description curation status, and editorial quality status
  - **Pool Size Explanations**: Card count with contextual guidance on flexibility and optimization potential
  - **Popularity Explanations**: Adoption pattern descriptions explaining why themes have their popularity tier
  - **Collapsible Display**: Badge details in collapsible section (open by default), matching catalog page badge legend pattern
  - **Feature Flag Respects**: Explanations only show for enabled badge types (respects SHOW_THEME_QUALITY_BADGES, SHOW_THEME_POOL_BADGES, SHOW_THEME_POPULARITY_BADGES)
  - **Dynamic Reasoning**: Explanations generated based on actual theme data (quality score, synergy counts, editorial status, archetype metadata)
- **Theme Catalog Badge System**: Comprehensive metric visualization with granular display control
  - **Quality Badges**: Editorial quality indicators (Excellent/Good/Fair/Poor) with semantic colors
  - **Pool Size Badges**: Card availability indicators (Vast/Large/Moderate/Small/Tiny) showing total cards per theme
  - **Popularity Badges**: Usage frequency indicators (Very Common/Common/Uncommon/Niche/Rare) based on theme adoption
  - **Badge Feature Flags**: Individual toggle flags for each badge type (SHOW_THEME_QUALITY_BADGES, SHOW_THEME_POOL_BADGES, SHOW_THEME_POPULARITY_BADGES)
  - **Filter Controls**: Dropdown filters and quick-select chips for all three metrics with master toggle (SHOW_THEME_FILTERS)
- **Theme Pool Size Display**: Visual indicators showing total card availability per theme
  - **Pool Size Calculation**: Automatic counting of cards with each theme tag from parquet data
  - **Pool Tier Badges**: Color-coded badges (Vast/Large/Moderate/Small/Tiny) showing pool size categories
  - **Pool Data in API**: Theme pool size (card count) and tier included in all theme API responses
  - **Pool Badges CSS**: New badge styles with distinct colors (violet/teal/cyan/orange/gray for pool tiers)
  - **Dual Metric System**: Quality badges (editorial completeness) + Pool size badges (card availability) shown together
- **Theme Quality Score Display**: Visual quality indicators in web UI for theme catalog
  - **Quality Tier Badges**: Color-coded badges (Excellent/Good/Fair/Poor) shown in theme lists and detail pages
  - **Quality Scoring**: Automatic calculation during theme loading based on completeness, uniqueness, and curation quality
  - **Quality Data in API**: Theme quality tier and normalized score (0.0-1.0) included in all theme API responses
  - **Quality Badges CSS**: New badge styles with semantic colors (green/blue/yellow/red for quality tiers)
- **Theme Catalog Filtering**: Advanced filtering system for quality, pool size, and popularity
  - **Filter Dropdowns**: Select-based filters for precise tier selection (Quality: E/G/F/P, Pool: V/L/M/S/T, Popularity: VC/C/U/N/R)
  - **Quick Filter Chips**: Single-click filter activation with letter-based shortcuts
  - **Combined Filtering**: Multiple filter types work together with AND logic (e.g., Good quality + Vast pool + Common popularity)
  - **Active Filter Display**: Visual chips showing applied filters with individual remove buttons
  - **Filter Performance**: Backend filtering in both fast path (theme_list.json) and fallback (full index) with sub-200ms response times
- **Theme Editorial Quality & Standards**: Complete editorial system for theme catalog curation
  - **Editorial Metadata Fields**: `description_source` (tracks provenance: official/inferred/custom) and `popularity_pinned` (manual tier override)
  - **Heuristics Externalization**: Theme classification rules moved to `config/themes/editorial_heuristics.yml` for maintainability
  - **Enhanced Quality Scoring**: Four-tier system (Excellent/Good/Fair/Poor) with 0.0-1.0 numerical scores based on uniqueness, duplication, description quality, and metadata completeness
  - **CLI Linter**: `validate_theme_catalog.py --lint` flag with configurable thresholds for duplication and quality warnings, provides actionable improvement suggestions
  - **Editorial Documentation**: Comprehensive guide at `docs/theme_editorial_guide.md` covering quality scoring, best practices, linter usage, and workflow examples
- **Theme Stripping Configuration**: Configurable minimum card threshold for theme retention
  - **THEME_MIN_CARDS Setting**: Environment variable (default: 5) to strip themes with too few cards from catalogs and card metadata
  - **Analysis Tooling**: `analyze_theme_distribution.py` script to visualize theme distribution and identify stripping candidates
  - **Core Threshold Logic**: `theme_stripper.py` module with functions to identify and filter low-card-count themes
  - **Catalog Stripping**: Automated removal of low-card themes from YAML catalog with backup/logging via `strip_catalog_themes.py` script

### Changed
- **Build Process Modernization**: Theme catalog generation now reads from parquet files instead of obsolete CSV format
  - Updated `build_theme_catalog.py` and `extract_themes.py` to use parquet data (matches rest of codebase)
  - Removed silent CSV exception handling (build now fails loudly if parquet read fails)
  - Added THEME_MIN_CARDS filtering directly in build pipeline (themes below threshold excluded during generation)
  - `theme_list.json` now auto-generated from stripped parquet data after theme stripping
  - Eliminated manual JSON stripping step (JSON is derived artifact, not source of truth)
- **Parquet Theme Stripping**: Strip low-card themes directly from card data files
  - Added `strip_parquet_themes.py` script with dry-run, verbose, and backup modes
  - Added parquet manipulation functions to `theme_stripper.py`: `backup_parquet_file()`, `filter_theme_tags()`, `update_parquet_theme_tags()`, `strip_parquet_themes()`
  - Handles multiple themeTags formats: numpy arrays, lists, and comma/pipe-separated strings
  - Stripped 97 theme tag occurrences from 30,674 cards in `all_cards.parquet`
  - Updated `stripped_themes.yml` log with 520 themes stripped from parquet source
  - **Automatic integration**: Theme stripping now runs automatically in `run_tagging()` after tagging completes (when `THEME_MIN_CARDS` > 1, default: 5)
  - Integrated into web UI setup, CLI tagging, and CI/CD workflows (build-similarity-cache)

### Fixed
- **Counter Type Tags**: Fixed leading spaces in theme names for Blood and Hone counter types
  - Corrected ` Blood` to `Blood` and ` Hone` to `Hone` in `tag_constants.py` COUNTER_TYPES list
  - Prevents creation of malformed theme names like ` Blood Counters` (with leading space)
  - Requires re-tagging to regenerate parquet files and theme catalog with corrected names

### Removed
_No unreleased changes yet_

## [4.0.1] - 2026-03-17
### Added
- **Testing Standards Documentation**: Standards guide and base classes for new tests
  - `docs/web_backend/testing.md` — patterns for route, service, validation, and error handler tests
  - `code/tests/base_test_cases.py` — `RouteTestCase`, `ServiceTestCase`, `ErrorHandlerTestCase`, `ValidationTestMixin`
  - Covers naming conventions, fixture setup, coverage targets, and what not to test
- **Error Handling Integration**: Custom exceptions now wired into the web layer
  - `DeckBuilderError` handler in `app.py` — typed exceptions get correct HTTP status (not always 500)
  - `deck_builder_error_response()` utility: JSON responses for API, HTML fragments for HTMX
  - Status code mapping for 50+ exception classes (400/401/404/503/500)
  - Web-specific exceptions: `SessionExpiredError` (401), `BuildNotFoundError` (404), `FeatureDisabledError` (404)
  - `partner_suggestions.py` converted from raw `HTTPException` to typed exceptions
  - Fixed pre-existing bug: `CommanderValidationError.__init__` now accepts optional `code` kwarg
  - Error handling guide: `docs/web_backend/error_handling.md`
- **Backend Standardization Framework**: Improved code organization and maintainability
  - Response builder utilities for consistent HTTP responses
  - Telemetry decorators for route access tracking and error logging
  - Route pattern documentation defining standards for all routes
  - Split monolithic build route handler into focused, maintainable modules
  - Step-based wizard routes consolidated into dedicated module
  - New build flow and quick build automation extracted into focused module
  - Alternative card suggestions extracted to standalone module
  - Compliance/enforcement and card replacement extracted to focused module
  - Foundation for integrating custom exceptions into web layer
- **Service Layer Architecture**: Base classes, interfaces, and registry for service standardization
  - `BaseService`, `StateService`, `DataService`, `CachedService` abstract base classes
  - Service protocols/interfaces for type-safe dependency injection
  - `ServiceRegistry` for singleton/factory/lazy service patterns
  - `SessionManager` refactored from global dict to thread-safe `StateService`
- **Validation Framework**: Centralized Pydantic models and validators
  - Pydantic models for all key request types (`BuildRequest`, `CommanderSearchRequest`, etc.)
  - `CardNameValidator` with normalization for diacritics, punctuation, multi-face cards
  - `ThemeValidator`, `PowerBracketValidator`, `ColorIdentityValidator`
  - `ValidationMessages` class for consistent user-facing error messages

### Fixed
- **Image Cache Status UI**: Setup page status stuck on "Checking…"
  - Stale `.download_status.json` from a failed run caused indefinite spinner
  - Added error state handling in JS to show "Last download failed" with message
  - Status endpoint now auto-cleans stale file after download completion/failure
  - Last download result persisted to `.last_download_result.json` across restarts
  - Card count now shown correctly (was double-counting by summing both size variants)
  - Shows "+N new cards" from last download run
- **Scryfall Bulk Data API**: HTTP 400 error when triggering image download
  - Scryfall now requires `Accept: application/json` on API endpoints
  - Fixed `ScryfallBulkDataClient._make_request()` to include the header

### Removed
- **Permalink Feature**: Removed permalink generation and restoration functionality
  - Deemed unnecessary for single-session deck building workflow
  - Users can still export decks (CSV/TXT/JSON) or use headless configs for automation
- **Template Validation Tests**: Comprehensive test suite for HTML/Jinja2 templates
  - Validates Jinja2 syntax across all templates
  - Checks HTML structure (balanced tags, unique IDs, proper attributes)
  - Basic accessibility validation (alt text, form labels, button types)
  - Regression prevention thresholds to maintain code quality
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
- **Test Suite Consolidation**: Streamlined test infrastructure for better maintainability
  - Consolidated 148 test files down to 87 (41% reduction)
  - Merged overlapping and redundant test coverage into comprehensive test modules
  - Maintained 100% pass rate (582 passing tests, 12 intentional skips)
  - Updated CI/CD workflows to reference consolidated test files
  - Improved test organization and reduced cognitive overhead for contributors
- **Template Modernization**: Migrated templates to use component system
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

### Changed
- Migrated 5 templates to new component system (home, 404, 500, setup, commanders)
- **Type Checking Configuration**: Improved Python code quality tooling
  - Configured type checker for better error detection
  - Optimized linting rules for development workflow

### Fixed
- **Deck Summary Display**: Fixed issue where deck summary cards would not display correctly in manual builds
  - Card images and names now appear properly in both List and Thumbnails views
  - Commander card displayed correctly in Step 5 sidebar
  - Summary data now properly persists across wizard stages
- **Multi-Copy Package Detection**: Fixed bug preventing multi-copy suggestions from appearing in New Deck wizard
  - Corrected key mismatch between archetype definitions ('tagsAny') and detection code ('tags_any')
  - Multi-copy panel now properly displays when commander and theme tags match supported archetypes (e.g., Hare Apparent for Rabbit Kindred + Tokens Matter)
  - Updated panel background color to match theme (now uses CSS variable instead of hardcoded value)
  - Affects all 12 multi-copy archetypes (Hare Apparent, Slime Against Humanity, Dragon's Approach, etc.)
- **Card Data Auto-Refresh**: Fixed stale data issue when new sets are released
  - Auto-refresh now deletes cached raw parquet file before downloading fresh data
  - Ensures new sets are included instead of reprocessing old cached data
  - Resolves issue where Docker volumes would retain outdated raw files
- **Template Quality**: Resolved HTML structure issues found by validation tests
  - Fixed duplicate ID attributes in build wizard and theme picker templates
  - Removed erroneous block tags from component documentation
  - Corrected template structure for HTMX fragments
- **Code Quality**: Resolved type checking warnings and improved code maintainability
  - Fixed type annotation inconsistencies
  - Cleaned up redundant code quality suppressions
  - Corrected configuration conflicts

### Removed
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

### Deprecated
_None_

### Security
_None_

## [3.0.1] - 2025-10-19
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

### Deprecated
_None_

### Security
_None_

## [3.0.0] - 2025-10-19
### Summary
Major infrastructure upgrade to Parquet format with comprehensive performance improvements, simplified data management, and instant setup via GitHub downloads.

### Added
- **Parquet Migration (M4)**: Unified `card_files/processed/all_cards.parquet` replaces multiple CSV files
  - Single source of truth for all card data (29,857 cards, 2,751 commanders, 31 backgrounds)
  - Native support for lists and complex data types
  - Faster loading (binary columnar format vs text parsing)
  - Automatic deduplication and data validation
- **Performance**: Parallel tagging option provides 4.2x speedup (22s → 5.2s)
- **Combo Tags**: 226 cards tagged with combo-enabling abilities for better deck building
- **Data Quality**: Built-in commander/background detection using boolean flags instead of separate files
- **GitHub Downloads**: Pre-tagged card database and similarity cache available for instant setup
  - Auto-download on first run (seconds instead of 15-20 minutes)
  - Manual download button in web UI
  - Updated weekly via automated workflow

### Changed
- **CLI & Web**: Both interfaces now load from unified Parquet data source
- **Deck Builder**: Simplified data loading, removed CSV file juggling
- **Web Services**: Updated card browser, commander catalog, and owned cards to use Parquet
- **Setup Process**: Streamlined initial setup with fewer file operations
- **Module Execution**: Use `python -m code.main` / `python -m code.headless_runner` for proper imports

### Removed
- Dependency on separate `commander_cards.csv` and `background_cards.csv` files
- Multiple color-specific CSV file loading logic
- CSV parsing overhead from hot paths

### Technical Details
- DataLoader class provides consistent Parquet I/O across codebase
- Boolean filters (`isCommander`, `isBackground`) replace file-based separation
- Numpy array conversion ensures compatibility with existing list-checking code
- GitHub Actions updated to use processed Parquet path
- Docker containers benefit from smaller, faster data files

## [2.9.1] - 2025-10-17
### Summary
Improved similar cards section with refresh button and reduced sidebar animation distractions.

### Added
- Similar cards now have a refresh button to see different recommendations without reloading the page
- Explanation text clarifying that similarities are based on shared themes and tags

### Changed
- Sidebar generally no longer animates during page loads and partial updates, reducing visual distractions

### Removed
_None_

### Fixed
_None_

## [2.9.0] - 2025-10-17
### Summary
New card browser for exploring 29,839 Magic cards with advanced filters, similar card recommendations, and performance optimizations.

### Added
- **Card Browser**: Browse and search all Magic cards at `/browse/cards`
  - Smart autocomplete for card names and themes with typo tolerance
  - Multi-theme filtering (up to 5 themes)
  - Color, type, rarity, CMC, power/toughness filters
  - Multiple sorting options including EDHREC popularity
  - Infinite scroll with shareable filter URLs
- **Card Detail Pages**: Individual card pages with similar card suggestions
  - Full card stats, oracle text, and theme tags
  - Similar cards based on theme overlap
  - Color-coded similarity scores
  - Card preview on hover
  - Enable with `ENABLE_CARD_DETAILS=1` environment variable
- **Similarity Cache**: Pre-computed card similarities for fast page loads
  - Build cache with parallel processing script
  - Automatically used when available
  - Control with `SIMILARITY_CACHE_ENABLED` environment variable
- **Keyboard Shortcuts**: Quick navigation in card browser
  - `Enter` to add autocomplete matches
  - `Shift+Enter` to apply filters
  - Double `Esc` to clear all filters

### Changed
- **Card Database**: Expanded to 29,839 cards (updated from 26,427)
- **Theme Catalog**: Improved coverage with better filtering

### Removed
- **Unused Scripts**: Removed `regenerate_parquet.py` (functionality now in web UI setup)

### Fixed
- **Card Browser UI**: Improved styling consistency and card image loading
- **Infinite Scroll**: Fixed cards appearing multiple times when loading more results
- **Sorting**: Sort order now persists correctly when scrolling through all pages

## [2.8.1] - 2025-10-16
### Summary
Improved colorless commander support with automatic card filtering and display fixes.

### Added
- **Colorless Commander Filtering**: 25 cards that don't work in colorless decks are now automatically excluded
  - Filters out cards like Arcane Signet, Commander's Sphere, and medallions that reference "commander's color identity" or colored spells
  - Only applies to colorless identity commanders (Karn, Kozilek, Liberator, etc.)

### Fixed
- **Colorless Commander Display**: Fixed three bugs affecting colorless commander decks
  - Color identity now displays correctly (grey "C" button with "Colorless" label)
  - Wastes now correctly added as basic lands in colorless decks
  - Colored basics (Plains, Island, etc.) no longer incorrectly added to colorless decks

## [2.8.0] - 2025-10-15
### Summary
Theme catalog improvements with faster processing, new tag search features, regeneration fixes, and browser performance optimizations.

### Added
- **Theme Catalog Optimization**:
  - Consolidated theme enrichment pipeline (single pass instead of 7 separate scripts)
  - Tag index for fast theme-based card queries
  - Tag search API with new endpoints for card search, autocomplete, and popular tags
  - Commander browser theme autocomplete with keyboard navigation
  - Tag loading infrastructure for batch operations
- **Theme Browser Keyboard Navigation**: Arrow keys now navigate search results (ArrowUp/Down, Enter to select, Escape to close)

### Changed
- **Theme Browser Performance**: Theme detail pages now load much faster
  - Disabled YAML file scanning in production (use `THEME_CATALOG_CHECK_YAML_CHANGES=1` during theme authoring)
  - Cache invalidation now checks theme_list.json instead of scanning all files
- **Theme Browser UI**: Removed color filter from theme catalog

### Fixed
- **Theme Regeneration**: Theme catalog can now be fully rebuilt from scratch without placeholder data
  - Fixed "Anchor" placeholder issue when regenerating catalog
  - Examples now generated from actual card data
  - Theme export preserves all metadata fields

## [2.7.1] - 2025-10-14
### Summary
Quick Build UI refinements for improved desktop display.

### Fixed
- Quick Build progress display now uses full desktop width instead of narrow mobile-like layout
- Quick Build completion screen properly transitions to full-width Step 5 layout matching manual build experience

## [2.7.0] - 2025-10-14
### Summary
- Enhanced deck building workflow with improved stage ordering, granular skip controls, and one-click Quick Build automation.
- New Ideal Counts section with interactive sliders or text inputs for customizing deck composition targets.
- Stage execution order now prioritizes creatures and spells before lands for better mana curve analysis.
- New wizard-only skip controls allow auto-advancing through specific stages (lands, creatures, spells) without approval prompts.
- Quick Build button provides one-click full automation with clean 5-phase progress indicator.

### Added
- **Ideal Counts UI**: Dedicated section in New Deck wizard for setting ideal card counts (ramp, lands, creatures, removal, wipes, card advantage, protection).
  - **Slider Mode** (default): Interactive range sliders with live value display and expanded ranges (e.g., creatures: 0-70, lands: 25-45).
  - **Input Mode**: Text input boxes with placeholder defaults (e.g., "10 (Default)").
  - Smart validation warns when estimated total exceeds 99 cards (accounts for overlap: `Lands + Creatures + Spells/2`).
  - Sliders start at recommended defaults and remember user preferences across builds.
  - Configurable via `WEB_IDEALS_UI` environment variable (`slider` or `input`).
- **Quick Build**: One-click automation button in New Deck wizard with live progress tracking (5 phases: Creatures, Spells, Lands, Final Touches, Summary).
- **Skip Controls**: Granular stage-skipping toggles in New Deck wizard (21 flags: all land steps, creature stages, spell categories).
  - Individual land step controls: basics, staples, fetches, duals, triomes, kindred, misc lands.
  - Spell category controls: ramp, removal, wipes, card advantage, protection, theme fill.
  - Creature stage controls: all creatures, primary, secondary, fill.
  - Mutual exclusivity enforcement: "Skip All Lands" disables individual land toggles; "Skip to Misc Lands" skips early land steps.
- **Stage Reordering**: New default build order executes creatures → spells → lands for improved pip analysis (configurable via `WEB_STAGE_ORDER` environment variable).
- Background task execution for Quick Build with HTMX polling progress updates.
- Mobile-friendly Quick Build with touch device confirmation dialog.
- Commander session cleanup: Commander selection automatically cleared after build completes.

### Changed
- **Default Stage Order**: Creatures and ideal spells now execute before land stages (lands can analyze actual pip requirements instead of estimates).
- **Ideal Counts Display**: Removed collapsible "Advanced options (ideals)" section; replaced with prominent fieldset with slider/input modes.
- Slider ranges expanded to support edge-case strategies (e.g., creature-heavy tribal, spell-heavy control).
- Skip controls only available in New Deck wizard (disabled during build execution for consistency).
- Skip behavior auto-advances through stages without approval prompts (cards still added, just not gated).
- Post-spell land adjustment automatically skipped when any skip flag enabled.

### Fixed
- Session context properly injected into Quick Build so skip configuration works correctly.
- HTMX polling uses continuous trigger (`every 500ms`) instead of one-time (`load delay`) for reliable progress updates.
- Progress indicator stops cleanly when build completes (out-of-band swap removes poller div).
- Ideal counts now properly populate from session state, allowing sliders to start at defaults and remember user preferences.
- Commander and commander_name cleared from session after build completes to prevent carryover to next build.

## [2.6.1] - 2025-10-13
### Summary
- Fixed issues with custom themes in the web UI.
- Added non-basic land type tagging (i.e. Caves, Deserts, Gates, etc...) in the tagging module.
- Improved alternatives panel UX with dismissible header and cleaner owned card indicators.

### Added
- Non-basic land type tagging (i.e. Caves, Deserts, Gates, etc...) in the tagging module.
- Close button to alternatives panel header so it can be dismissed.

### Changed
- Removed the owned badge from each alternative and moved owned metadata to a data attribute on the button.

### Fixed
- Custom theme fuzzy matching now accepts selection.
- Custom themes may now be removed from the list.

## [2.6.0] - 2025-10-13
### Summary
- Card tagging system improvements split metadata from gameplay themes for cleaner deck building experience
- Keyword normalization reduces specialty keyword noise by 96% while maintaining theme catalog quality
- Protection tag now focuses on cards that grant shields to others, not just those with inherent protection
- Web UI improvements: faster polling, fixed progress display, and theme refresh stability
- **Protection System Overhaul**: Comprehensive enhancement to protection card detection, classification, and deck building
  - Fine-grained scope metadata distinguishes self-protection from board-wide effects ("Your Permanents: Hexproof" vs "Self: Hexproof")
  - Enhanced grant detection with Equipment/Aura patterns, phasing support, and complex trigger handling
  - Intelligent deck builder filtering includes board-relevant protection while excluding self-only and type-specific cards
  - Tiered pool limiting focuses on high-quality staples while maintaining variety across builds
  - Improved scope tagging for cards with keyword-only protection effects (no grant text, just inherent keywords)
- **Tagging Module Refactoring**: Large-scale refactor to improve code quality and maintainability
  - Centralized regex patterns, extracted reusable utilities, decomposed complex functions
  - Improved code organization and readability while maintaining 100% tagging accuracy

### Added
- Metadata partition system separates diagnostic tags from gameplay themes in card data
- Keyword normalization system with smart filtering of one-off specialty mechanics
- Allowlist preserves important keywords like Flying, Myriad, and Transform
- Protection grant detection identifies cards that give Hexproof, Ward, or Indestructible to other permanents
- Automatic tagging for creature-type-specific protection (e.g., "Knights Gain Protection")
- New `metadataTags` column in card data for bracket annotations and internal diagnostics
- Static phasing keyword detection from keywords field (catches creatures like Breezekeeper)
- "Other X you control have Y" protection pattern for static ability grants
- "Enchanted creature has phasing" pattern detection
- Chosen type blanket phasing patterns
- Complex trigger phasing patterns (reactive, consequent, end-of-turn)
- Protection scope filtering in deck builder (feature flag: `TAG_PROTECTION_SCOPE`) intelligently selects board-relevant protection
- Phasing cards with "Your Permanents:" or "Targeted:" metadata now tagged as Protection and included in protection pool
- Metadata tags temporarily visible in card hover previews for debugging (shows scope like "Your Permanents: Hexproof")
- Web-slinging tagger function to identify cards with web-slinging mechanics

### Changed
- Card tags now split between themes (for deck building) and metadata (for diagnostics)
- Keywords now consolidate variants (e.g., "Commander ninjutsu" becomes "Ninjutsu")
- Setup progress polling reduced from 3s to 5-10s intervals for better performance
- Theme catalog streamlined from 753 to 736 themes (-2.3%) with improved quality
- Protection tag refined to focus on 329 cards that grant shields (down from 1,166 with inherent effects)
- Protection tag renamed to "Protective Effects" throughout web interface to avoid confusion with the Magic keyword "protection"
- Theme catalog automatically excludes metadata tags from theme suggestions
- Grant detection now strips reminder text before pattern matching to avoid false positives
- Deck builder protection phase now filters by scope metadata: includes "Your Permanents:", excludes "Self:" protection
- Protection card selection now randomized per build for variety (using seeded RNG when deterministic mode enabled)
- Protection pool now limited to ~40-50 high-quality cards (tiered selection: top 3x target + random 10-20 extras)
- Tagging module imports standardized with consistent organization and centralized constants

### Fixed
- Setup progress now shows 100% completion instead of getting stuck at 99%
- Theme catalog no longer continuously regenerates after setup completes
- Health indicator polling optimized to reduce server load
- Protection detection now correctly excludes creatures with only inherent keywords
- Dive Down, Glint no longer falsely identified as granting to opponents (reminder text fix)
- Drogskol Captain, Haytham Kenway now correctly get "Your Permanents" scope tags
- 7 cards with static Phasing keyword now properly detected (Breezekeeper, Teferi's Drake, etc.)
- Type-specific protection grants (e.g., "Knights Gain Indestructible") now correctly excluded from general protection pool
- Protection scope filter now properly prioritizes exclusions over inclusions (fixes Knight Exemplar in non-Knight decks)
- Inherent protection cards (Aysen Highway, Phantom Colossus, etc.) now correctly get "Self: Protection" metadata tags
- Scope tagging now applies to ALL cards with protection effects, not just grant cards
- Cloak of Invisibility, Teferi's Curse now get "Your Permanents: Phasing" tags
- Shimmer now gets "Blanket: Phasing" tag for chosen type effect
- King of the Oathbreakers now gets "Self: Phasing" tag for reactive trigger
- Cards with static keywords (Protection, Hexproof, Ward, Indestructible) in their keywords field now get proper scope metadata tags
- Cards with X in their mana cost now properly identified and tagged with "X Spells" theme for better deck building accuracy
- Card tagging system enhanced with smarter pattern detection and more consistent categorization

## [2.5.2] - 2025-10-08
### Summary
- Responsiveness tweaks: shared HTMX debounce helper, deferred skeleton microcopy, and containment rules for long card lists.
- Optimistic include/exclude experience with HTMX caching, prefetch hints, and telemetry instrumentation for must-have interactions.
- Commander catalog skeleton placeholders and lazy commander art loading to smooth catalog fetch latency.
- Commander catalog default view now prewarms and pulls from an in-memory cache so repeat visits respond in under 200 ms.
- Virtualization helper now respects `data-virtualize-*` hints and powers deck summary lists without loading all rows at once.
- Step 5 deck summary now streams via an HTMX fragment so the main review payload stays lean while virtualization kicks in post-swap.
- Mana analytics now load on-demand with collapsible sections, reducing initial deck review time by ~30-40%.
- Interactive chart tooltips with click-to-pin highlighting make cross-referencing cards between charts and deck lists easier.

### Added
- Skeleton placeholders now accept `data-skeleton-label` microcopy and only surface after ~400 ms on the build wizard, stage navigator, and alternatives panel.
- Must-have toggle API (`/build/must-haves/toggle`), telemetry ingestion route (`/telemetry/events`), and structured logging helpers for include/exclude state changes and frontend beacons.
- Commander catalog results wrap in a deferred skeleton list, and commander art lazy-loads via a new `IntersectionObserver` helper in `code/web/static/app.js`.
- Collapsible accordions for Mana Overview and Test Hand sections defer content loading until expanded.
- Click-to-pin chart tooltips with consistent corner positioning (lower-left desktop, lower-right mobile) and working copy buttons.
- Virtualized card lists automatically render only visible items when 12+ cards are present.

### Changed
- Commander search and theme picker now intelligently debounce keystrokes, preventing redundant requests while you type.
- Card grids use modern browser containment rules to minimize layout recalculations on large decks.
- Include/exclude buttons now respond immediately with optimistic updates, falling back gracefully if the server disagrees.
- Frequently-accessed views (like the commander catalog default) now load from memory, responding in under 200ms.
- Deck review now loads in focused chunks, keeping the initial page lean while analytics stream in progressively.
- Chart hover zones expanded to full column width for easier interaction.

### Fixed
- _None_

## [2.5.1] - 2025-10-06
### Summary
- Alternative suggestions in the build wizard now surface the replacement card preview immediately and reload the list after a swap.

### Added
- Alternatives panel includes a "New pool" button so you can request a fresh batch of suggestions without rerunning the stage.

### Changed
- Alternative suggestion buttons expose role, mana, and rarity metadata to hover previews for better at-a-glance context.

### Fixed
- Previewing an alternative card now shows the replacement instead of the currently slotted card, and the list refreshes automatically after choosing an alternative.

## [2.5.0] - 2025-10-06
### Summary
- Partner suggestion service and API power Step 2 suggestion chips for partner, background, and Doctor pairings when `ENABLE_PARTNER_SUGGESTIONS` is active.
- Headless runner now honors partner/background inputs behind the `ENABLE_PARTNER_MECHANICS` feature flag and carries regression coverage for dry-run resolution.
- Web builder Step 2 exposes partner/background pairing when `ENABLE_PARTNER_MECHANICS` is active, including live previews and warnings for invalid combinations.
- Quick-start modal mirrors the Step 2 partner/background controls so fast deck builds can choose a secondary commander or background without leaving the modal.
- Partner mechanics UI auto-enables for eligible commanders, renames the secondary picker to “Partner commander,” layers in Partner With defaults with opt-out chips, adds Doctor/Doctor’s Companion pairing, and keeps modal/theme previews in sync.
- Deck exports now surface combined commander metadata across CSV/TXT headers and JSON summaries so dual-command builds stay in sync for downstream tooling.

### Added
- Partner suggestion dataset loader, scoring service (`code/web/services/partner_suggestions.py`), FastAPI endpoint, UI chips, dataset override env (`PARTNER_SUGGESTIONS_DATASET`), auto-regeneration when the dataset is missing, and tests covering dataset flattening plus API responses.
- CLI regression coverage (`code/tests/test_cli_partner_config.py`) verifying partner/background dry-run payloads and `ENABLE_PARTNER_MECHANICS` env gating in the headless runner.
- Web build wizard toggle for partner mechanics with partner/background selectors, auto-pair hints, warnings, and combined color preview behind the feature flag.
- Partner and background selections now render card art previews (with Scryfall links) in the quick-start wizard, Step 2 form, and deck summary so builders can confirm the secondary pick at a glance.
- Quick-start modal now renders shared partner/background controls (reusing `_partner_controls.html`) whenever a commander that supports the mechanic is inspected.
- Background catalog loader (`code/deck_builder/background_loader.py`) with memoized parsing, typed entries, and a generator utility (`python -m code.scripts.generate_background_cards`) plus coverage to ensure only legal backgrounds enter the catalog.
- Shared `CombinedCommander` aggregation and partner/background selection helper wired through deck builds, exports, and partner preview endpoints with accompanying regression tests.
- Script `python -m code.scripts.build_partner_suggestions` materializes commander metadata, theme indexes, and observed pairings into `config/analytics/partner_synergy.json` to seed the partner suggestion engine.
- Partner suggestion scoring helper (`code/deck_builder/suggestions.py`) with mode-specific weights and regression tests ensuring canonical pairings rank highest across partner, background, and Doctor flows.
- Export regression coverage (`code/tests/test_export_commander_metadata.py`) verifies commander metadata is embedded in CSV/TXT headers and summary payloads while preserving existing columns.
- Partner suggestion telemetry emits `partner_suggestions.generated` and `partner_suggestions.selected` logs (via `code/web/services/telemetry.py`) so adoption metrics and dataset diagnostics can be monitored.

### Changed
- Partner controls hydrate suggestion chips on the web builder and quick-start modal, fetching ranked partner/backdrop recommendations while respecting active partner mode and session locks when `ENABLE_PARTNER_SUGGESTIONS=1`.
- Partner suggestion scoring now filters out broad "Legends Matter", "Historics Matter", and Kindred themes when computing overlap or synergy so recommendations emphasize distinctive commander pairings.
- Headless runner parsing now resolves `--secondary-commander` and `--background` inputs (mutually exclusive), applies the shared partner selection helper ahead of deck assembly, and surfaces flag-controlled behavior in exported dry-run payloads.
- Step 2 submission now validates partner inputs, stores combined commander previews/warnings in the session, and clears prior partner state when the toggle is disabled.
- Quick-start `/build/new` submission resolves partner selections, persists the combined commander payload, and re-renders the modal with inline partner errors when inputs conflict.
- Partner controls mount automatically for eligible commanders, replace the manual toggle with a hidden enable flag, rename the select to “Partner commander,” and expose an opt-out chip when Partner With suggests a default.
- Commander catalog metadata now flags Doctors and Doctor’s Companions so selectors present only legal pairings and annotate each option with its role.
- Partner detection now distinguishes the standalone “Partner” keyword from Partner With/Doctor’s Companion/restricted variants, and the web selector filters plain-partner pools to exclude those mechanics while keeping direct Partner With pairings intact.
- Structured partner selection logs now emit `partner_mode_selected` with commander color deltas, capturing colors before and after pairing for diagnostics parity.
- Structured partner selection logs now tag suggestion-driven selections with a `selection_source` attribute to differentiate manual picks from suggestion chip adoption.
- Commander setup now regenerates `background_cards.csv` alongside `commander_cards.csv`, ensuring the background picker stays synchronized after catalog refreshes or fresh installs.
- Setup/tagging auto-refresh now runs the partner suggestion dataset builder so `config/analytics/partner_synergy.json` tracks the latest commander catalog and deck exports without manual scripts.
- CSV/TXT deck exports append commander metadata columns, text headers include partner mode and colors, and summary sidecars embed serialized combined commander details without breaking legacy consumers.
- Partner commander previews in Step 2 and the build summary now mirror the primary commander card layout (including hover metadata and high-res art) so both selections share identical interactions.
- Editorial governance CI stages lightweight catalog fixtures when `EDITORIAL_TEST_USE_FIXTURES=1`, avoiding the need to sync `config/themes/catalog` into source control.

### Fixed
- Regenerated `background_cards.csv` and tightened background detection so the picker only lists true Background enchantments, preventing "Choose a Background" commanders from appearing as illegal partners and restoring background availability when the CSV was missing.
- Restricted partner commanders with dash-based keywords (e.g., Partner - Survivors, Partner - Father & Son) now register as partners and surface their matching group pairings in the web selector.
- Quick-start modal partner previews now merge theme tags with Step 2 so chips stay consistent after commander inspection.
- Step 5 summary and quick-start commander preview now surface merged partner color identity and theme tags so pairings like Halana + Alena display both colors.
- Partner and background builds now inject the secondary commander card automatically, keeping deck libraries, exports, and Step 5 summaries in sync with the chosen pairing.
- Partner With commanders now restrict the dropdown to their canon companion and the preview panel adopts the wizard theme colors for better readability while live-selection previews render immediately.
- Manual partner selections now persist across the wizard and quick-start modal, keeping recommendations and theme chips in sync without needing an extra apply step.
- Background picker now falls back to the commander catalog when `background_cards.csv` is missing so “Choose a Background” commanders remain selectable in the web UI.
- Partner hover previews now respect the secondary commander data so the popup matches the card you’re focusing.
- Step 5 summary and finished deck views now surface the deck’s chosen themes (and commander hover metadata) without flooding the UI with every commander tag.
- Doctor’s Companion commanders now surface only legal Doctor pairings, direct Partner With matches (e.g., Amy & Rory) remain available, and escaped newline text no longer breaks partner detection.
- Partner suggestion refresh now re-attempts dataset generation when triggered from the UI and ensures the builder script loads project packages inside Docker, so missing `partner_synergy.json` files can be recreated without restarting the web app.

## [2.4.1] - 2025-10-03
### Summary
- Theme catalog groundwork for supplemental/custom themes now ships with a generator script and focused test coverage.
- Web builder gains an Additional Themes section with fuzzy suggestions and strict/permissive toggles for user-supplied tags.
- Compose manifests and docs include new environment toggles for random reroll throttling, telemetry/logging, homepage commander tile, and optional random rate limiting.

### Added
- Script `python -m code.scripts.generate_theme_catalog` emits a normalized `theme_catalog.csv` with commander/card counts, deterministic ordering, and a reproducible version hash for supplemental theme inputs.
- Unit tests cover catalog generation on fixture CSVs and verify normalization removes duplicate theme variants.
- Loader `load_theme_catalog()` memoizes CSV parsing, validates required columns, and exposes typed entries plus version metadata for runtime integrations.
- Unit tests exercise loader success, empty-file fallback, and malformed-column scenarios.
- Fuzzy theme matcher builds a trigram-backed index with Levenshtein + Sequence similarity scoring, threshold constants, and resolution utilities for supplemental theme inputs.
- Unit tests validate normalization, typo recovery, suggestion quality, and enforce a basic performance ceiling for 400+ theme catalogs.
- Headless configs accept `additional_themes` + `theme_match_mode` with catalog-backed fuzzy resolution, strict/permissive enforcement, and persistence into exported run configs and diagnostics.
- Added targeted tests for additional theme parsing, strict failure handling, and permissive warning coverage.
- Web New Deck modal renders an “Additional Themes” HTMX partial supporting add/remove, suggestion adoption, mode switching, limit enforcement, and accessible live messaging (gated by `ENABLE_CUSTOM_THEMES`).
- Supplemental theme telemetry now records commander/user/merged theme payloads, exposes `/status/theme_metrics` for diagnostics, and surfaces user theme weighting via structured `user_theme_applied` logs and the diagnostics dashboard panel.
  - Environment variables surfaced in compose, `.env.example`, and docs:
    - `SHOW_COMMANDERS` (default `1`): show the Commanders browser tile.
    - `RANDOM_REROLL_THROTTLE_MS` (default `350`): client guard to prevent rapid rerolls.
    - `RANDOM_STRUCTURED_LOGS` (default `0`): emit structured JSON logs for random builds.
    - `RANDOM_TELEMETRY` (default `0`): enable lightweight timing/attempt counters for diagnostics.
    - `RATE_LIMIT_ENABLED` (default `0`), `RATE_LIMIT_WINDOW_S` (`10`), `RATE_LIMIT_RANDOM` (`10`), `RATE_LIMIT_BUILD` (`10`), `RATE_LIMIT_SUGGEST` (`30`): optional server-side rate limiting for random endpoints.

### Changed
- Run-config exports now surface `userThemes` and `themeCatalogVersion` metadata while retaining legacy fields; headless imports accept both aliases without changing hash-equivalent payloads when no user themes are present.

### Fixed
- Additional Themes now falls back to `theme_list.json` when `theme_catalog.csv` is absent, restoring resolution, removal, and build application for user-supplied themes across web and headless flows.

## [2.4.0] - 2025-10-02
### Summary
- Wrapped the Multi-Faced Card Handling roadmap (tag merge, commander eligibility, land accounting) so double-faced cards now share tags, respect primary-face commander legality, and surface accurate land/MDFC diagnostics across web, CLI, and exports.
- Closed out MDFC follow-ups: deck summary now highlights double-faced lands with badges, per-face mana metadata flows through reporting, exports include annotations, and diagnostics can emit per-face snapshots for catalog QA.
- Surfaced commander exclusion warnings and automatic corrections in the builder so players are guided toward the legal front face whenever only a secondary face meets commander rules.
- Diagnostics dashboard now displays a multi-face merge snapshot plus live MDFC telemetry so catalog rebuilds and deck summaries can be verified in one place.
- Automated commander catalog refresh now ships with `python -m code.scripts.refresh_commander_catalog`, producing merged and compatibility snapshots alongside updated documentation for downstream consumers.
### Added
- Deck exporter regression coverage ensuring MDFC annotations (`DFCNote`) appear in CSV/TXT outputs, plus documentation for adding new double-faced cards to authoring workflows.
- Optional MDFC diagnostics snapshot toggled via `DFC_PER_FACE_SNAPSHOT` (with `DFC_PER_FACE_SNAPSHOT_PATH` override) to capture merged per-face metadata for observability.
- Structured observability for DFC merges: `multi_face_merger.py` now captures merge metrics and persists `logs/dfc_merge_summary.json` for troubleshooting.
- Land accounting coverage: `test_land_summary_totals.py` exercises MDFC totals, CLI output, and the deck summary HTMX fragment; shared fixtures added to `code/tests/conftest.py` for reuse.
- Tests: added `test_commander_primary_face_filter.py` to cover primary-face commander eligibility and secondary-face exclusions.
- Tests: added `test_commander_exclusion_warnings.py` to ensure commander exclusion guidance appears in the web builder and protects against regressions.
- Diagnostics: added a multi-face merge panel (with MDFC telemetry counters) to `/diagnostics`, powered by `summary_telemetry.py` and new land summary hooks.
- Commander browser skeleton page at `/commanders` with HTMX-capable filtering and catalog-backed commander rows.
- Shared color-identity macro and accessible theme chips powering the commander browser UI.
- Commander browser QA walkthrough documenting desktop and mobile validation steps (`docs/qa/commander_browser_walkthrough.md`).
- Home screen actions now surface Commander Browser and Diagnostics shortcuts when the corresponding feature flags are enabled.
- Manual QA pass (2025-09-30) recorded in project docs, covering desktop/mobile flows and edge cases.
- Commander wizard toggle to swap a matching basic land whenever modal double-faced lands are added, plus regression coverage in `test_mdfc_basic_swap.py`.
- Automation: `python -m code.scripts.refresh_commander_catalog` refreshes commander catalogs with MDFC-aware tagging, writing both merged output and `csv_files/compat_faces/commander_cards_unmerged.csv` for downstream validation; README and commander onboarding docs updated with migration guidance.
- Documentation: added `docs/qa/mdfc_staging_checklist.md` outlining MDFC staging QA (now updated for the always-on merge with optional compatibility snapshots).

### Changed
- Deck summary UI renders modal double-faced land badges and per-face face details so builders can audit mana contributions at-a-glance.
- MDFC merge flag removed: `ENABLE_DFC_MERGE` no longer gates the multi-face merge; the merge now runs unconditionally with optional `DFC_COMPAT_SNAPSHOT` compatibility snapshots.
- New Deck modal commander search now flags secondary-face-only entries, shows inline guidance, and auto-fills the eligible face before starting a build.
- New Deck modal Preferences block now surfaces "Use only owned", "Prefer owned", and "Swap basics for MDFC lands" checkboxes with session-backed defaults so the wizard mirrors Step 4 behavior.
- Deck summary now surfaces "Lands: X (Y with DFC)" with an MDFC breakdown panel, and CLI summaries mirror the same copy so web/CLI diagnostics stay in sync.
- Deck summary builder now records MDFC land telemetry for diagnostics snapshots, enabling quick verification of land contributions across builds.
- Roadmap documentation now summarizes remaining DFC follow-ups (observability, rollout gating, and exporter/UI enhancements) with next steps and ownership notes.
- Commander CSV enrichment now backfills `themeTags`, `creatureTypes`, and `roleTags` from the color-tagged catalogs so primary-face enforcement keeps merged tag coverage for multi-face commanders.
- Commander CSV generation now enforces primary-face legality, dropping secondary-face-only records, writing `.commander_exclusions.json` diagnostics, and surfacing actionable headless errors when configs reference removed commanders.
- Commander browser now paginates results in 20-commander pages with accessible navigation controls and range summaries to keep the catalog responsive.
- Commander hover preview collapses to a card-only view when browsing commanders, and all theme chips display without the previous “+ more” overflow badge.
- Added a Content Security Policy upgrade directive so proxied HTTPS deployments safely rewrite commander pagination requests to HTTPS, preventing mixed-content blocks.
- Commander thumbnails use a fixed-width 160px frame (scaling down on small screens) to eliminate inconsistent image sizing across the catalog.
- Commander browser search now separates commander name and theme inputs, introduces fuzzy theme suggestions, and tightens commander name matching to near-exact results.
- Commander browser no longer auto-scrolls when typing in search fields, keeping focus anchored near the filters.
- Commander theme chips feature larger typography, multi-line wrapping, and a mobile-friendly tap dialog for reading summaries.
- Theme dialog now prefers full editorial descriptions, so longer summaries display completely on mobile.
- Commander theme labels now unescape leading punctuation (e.g., +2/+2 Counters) to avoid stray backslashes in the UI.
- Theme summary dialog now opens when clicking theme chips on desktop as well as mobile.
- Commander list pagination controls now appear above and below the results and automatically scroll to the top when switching pages for quicker navigation.
- Mobile commander rows now feature larger thumbnails and a centered preview modal with expanded card art for improved readability.
- Preview performance CI check now waits for `/healthz` and retries theme catalog pagination fetches to dodge transient 500s during cold starts.
- Documentation now captures the MDFC staging plan: README and DOCKER guide highlight the always-on MDFC merge and the optional `DFC_COMPAT_SNAPSHOT=1` workflow for downstream QA.

### Fixed
- Setup filtering now applies security-stamp exclusions case-insensitively so Acorn and Heart promo cards stay out of Commander-legal pools, with a regression test covering the behavior.
- Commander browser thumbnails now surface the double-faced flip control so MDFC commanders can swap faces directly from the catalog.

### Removed
- Preview performance GitHub Actions workflow (`.github/workflows/preview-perf-ci.yml`) retired after persistent cold-start failures; run the regression helper script manually as needed.

## [2.3.2] - 2025-09-30
### Fixed
- Theme catalog pagination reprocesses HTMX fragments after Ajax loads so the “Next” button behaves correctly in the picker and simple catalog views.
- Docker entrypoint now seeds the default `config/themes` files (e.g., `synergy_pairs.yml`, `theme_clusters.yml`, `theme_whitelist.yml`) into mounted volumes so Docker Hub images start with the expected theme catalog baseline.

## [2.3.1] - 2025-09-29
### Added
- Headless runner parity: added `--random-mode` and accompanying `--random-*` flags to mirror the web Surprise/Reroll builder (multi-theme inputs, auto-fill overrides, deterministic seeds, constraints, and optional JSON payload export).
- Tests: added `test_headless_skips_owned_prompt_when_files_present` to guard the headless runner against regressions when owned card lists are present.
- Included the tiny `csv_files/testdata` fixture set so CI fast determinism tests have consistent sample data.

### Changed
- Configuration docs: docker compose manifests, `.env.example`, and README now enumerate all supported random-mode environment variables with sensible defaults and refreshed flag documentation for the headless runner.
- Owned Cards library tiles now use larger thumbnails and wider columns, and virtualization only activates when more than 800 cards are present to keep scrolling smooth.
- Theme catalog schema now accepts optional `id` values on entries so refreshed catalogs validate cleanly.
- CI installs `httpx` with the rest of the web stack and runs pytest via `python -m pytest` so FastAPI tests resolve the local `code` package correctly.
- Relaxed fast-path catalog validation to allow empty synergy lists while still warning on missing or malformed data types.
- Deck summary list view now includes inline flip controls for double-faced cards, keeping text mode feature parity with thumbnail mode.
- Hover panel theme chips now highlight only the themes that triggered a card’s inclusion while the full theme list displays as a muted footer without legacy bracket formatting.
- Finished deck summaries now surface overlap chips using sanitized saved metadata with a themed fallback so exported decks match the live builder UI, and hover overlap pills adopt larger, higher-contrast styling on desktop and mobile.
- Builder card tiles now reserve the card art tap/click for previewing; locking is handled exclusively by the dedicated 🔒 button so mobile users can open the hover panel without accidentally changing locks.
- Builder hover tags now surface normalized theme labels (e.g., “Card Advantage”) and suppress internal `creature_add • tag:` prefixes so build-stage pills match the final deck experience.
- Builder Step 5 commander preview now reuses the in-app hover panel (removing the external Scryfall link) and the hover reasons list auto-expands without an embedded scrollbar for easier reading on desktop and mobile.
- Finished deck commander preview now mirrors builder hover behavior with deck-selected overlap chips, the full commander theme list, and suppresses the external Scryfall link so tapping the thumbnail consistently opens the in-app panel across desktop and mobile.

### Fixed
- Editorial governance workflow now installs development dependencies (including pytest) so editorial tests run in CI.
- Hover card role badge is hidden when no role metadata is available, eliminating the empty pill shown in owned library popovers.
- Random Mode fallback warning no longer displays when all theme inputs are blank.
- Reinstated flip controls for double-faced cards in the hover preview and ensured the overlay button stays in sync with card faces.
- Hover card panel adapts for tap-to-open mobile use with centered positioning, readable scaling, and an explicit close control.
- Mobile hover layout now stacks theme chips beneath the artwork for better readability and cleans up theme formatting.
- Duplicate overlap highlighting on desktop hover has been removed; theme pills now render once without stray bullets even when multiple overlaps are present.
- Headless runner no longer loops on the power bracket prompt when owned card files exist; scripted responses now auto-select defaults with optional `HEADLESS_USE_OWNED_ONLY` / `HEADLESS_OWNED_SELECTION` overrides for automation flows.
- Regenerated `logs/perf/theme_preview_warm_baseline.json` to repair preview performance CI regressions caused by a malformed baseline file and verified the regression gate passes with the refreshed data.
- File setup now keeps cards with the Hero creature type; previously they were filtered out alongside the non-Commander-legal Hero card type.

## [2.3.0] - 2025-09-26
### Added
- Tests: added `test_random_reroll_throttle.py` to enforce reroll throttle behavior and `test_random_metrics_and_seed_history.py` to validate opt-in telemetry counters plus seed history exposure.
- Random Mode curated theme pool now documents manual exclusions (`config/random_theme_exclusions.yml`) and ships a reporting script `code/scripts/report_random_theme_pool.py` (`--write-exclusions` emits Markdown/JSON) alongside `docs/random_theme_exclusions.md`. Diagnostics now show manual categories and tag index telemetry.
- Performance guard: `code/scripts/check_random_theme_perf.py` compares the multi-theme profiler output to `config/random_theme_perf_baseline.json` and fails if timings regress beyond configurable thresholds (`--update-baseline` refreshes the file).
- Random Modes UI/API: separate auto-fill controls for Secondary and Tertiary themes with full session, permalink, HTMX, and JSON API support (per-slot state persists across rerolls and exports, and Tertiary auto-fill now automatically enables Secondary to keep combinations valid).
- Random Mode UI gains a lightweight “Clear themes” button that resets all theme inputs and stored preferences in one click for fast Surprise Me reruns.
- Diagnostics: `/status/random_theme_stats` exposes cached commander theme token metrics and the diagnostics dashboard renders indexed commander coverage plus top tokens for multi-theme debugging.
- Random Mode sidecar metadata now records multi-theme details (`primary_theme`, `secondary_theme`, `tertiary_theme`, `resolved_themes`, `combo_fallback`, `synergy_fallback`, `fallback_reason`, plus legacy aliases) in both the summary payload and exported `.summary.json` files.
- Tests: added `test_random_multi_theme_filtering.py` covering triple success, fallback tiers (P+S, P+T, Primary-only, synergy, full pool) and sidecar metadata emission for multi-theme builds.
- Tests: added `test_random_multi_theme_webflows.py` to exercise reroll-same-commander caching and permalink roundtrips for multi-theme runs across HTMX and API layers.
- Random Mode multi-theme groundwork: backend now supports `primary_theme`, `secondary_theme`, `tertiary_theme` with deterministic AND-combination cascade (P+S+T → P+S → P+T → P → synergy-overlap → full pool). Diagnostics fields (`resolved_themes`, `combo_fallback`, `synergy_fallback`, `fallback_reason`) added to `RandomBuildResult` (UI wiring pending).
- Tests: added `test_random_surprise_reroll_behavior.py` covering Surprise Me input preservation and locked commander reroll cache reuse.
- Locked commander reroll path now produces full artifact parity (CSV, TXT, compliance JSON, summary JSON) identical to Surprise builds.
- Random reroll tests for: commander lock invariance, artifact presence, duplicate export prevention, and form vs JSON submission.
- Roadmap document `logs/roadmaps/random_multi_theme_roadmap.md` capturing design, fallback strategy, diagnostics, and incremental delivery plan.
- Random Modes diagnostics: surfaced attempts, timeout_hit, and retries_exhausted in API responses and the HTMX result fragment (gated by SHOW_DIAGNOSTICS); added tests covering retries-exhausted and timeout paths and enabled friendly labels in the UI.
- Random Full Build export parity: random full deck builds now produce the standard artifact set — `<stem>.csv`, `<stem>.txt`, `<stem>_compliance.json` (bracket policy report), and `<stem>.summary.json` (summary with `meta.random` seed/theme/constraints). The random full build API response now includes `csv_path`, `txt_path`, and `compliance` keys (paths) for immediate consumption.
- Environment toggle (opt-out) `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT` (defaults to active automatically) lets you revert to legacy double-export behavior for debugging by setting `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=0`.
- Tests: added random full build export test ensuring exactly one CSV/TXT pair (no `_1` duplicates) plus sidecar JSON artifacts.
- Taxonomy snapshot CLI (`code/scripts/snapshot_taxonomy.py`): writes an auditable JSON snapshot of BRACKET_DEFINITIONS to `logs/taxonomy_snapshots/` with a deterministic SHA-256 hash; skips duplicates unless forced.
- Optional adaptive splash penalty (feature flag): enable with `SPLASH_ADAPTIVE=1`; tuning via `SPLASH_ADAPTIVE_SCALE` (default `1:1.0,2:1.0,3:1.0,4:0.6,5:0.35`).
- Splash penalty analytics: counters now include total off-color cards and penalty reason events; structured logs include event details to support tuning.
- Tests: color identity edge cases (hybrid, colorless/devoid, MDFC single, adventure, color indicator) using synthetic CSV injection via `CARD_INDEX_EXTRA_CSV`.
- Core Refactor Phase A (initial): extracted sampling pipeline (`sampling.py`) and preview cache container (`preview_cache.py`) from `theme_preview.py` with stable public API re-exports.
 - Adaptive preview cache eviction heuristic replacing FIFO with env-tunable weights (`THEME_PREVIEW_EVICT_W_HITS`, `_W_RECENCY`, `_W_COST`, `_W_AGE`) and cost thresholds (`THEME_PREVIEW_EVICT_COST_THRESHOLDS`); metrics include eviction counters and last event metadata.
 - Performance CI gate: warm-only p95 regression threshold (default 5%) enforced via `preview_perf_ci_check.py`; baseline refresh policy documented.
- ETag header for basic client-side caching of catalog fragments.
- Theme catalog performance optimizations: precomputed summary maps, lowercase search haystacks, memoized filtered slug cache (keyed by `(etag, params)`) for sub‑50ms warm queries.
- Theme preview endpoint: `GET /themes/api/theme/{id}/preview` (and HTML fragment) returning representative sample (curated examples, curated synergy examples, heuristic roles: payoff / enabler / support / wildcard / synthetic).
- Commander bias heuristics (color identity restriction, diminishing synergy overlap bonus, direct theme match bonus).
- In‑memory TTL cache (default 600s) for previews with build time tracking.
- Metrics endpoint `GET /themes/metrics` (diagnostics gated) exposing preview & catalog counters, cache stats, percentile build times.
- Governance metrics: `example_enforcement_active`, `example_enforce_threshold_pct` surfaced once curated coverage passes threshold (default 90%).
- Skeleton loading states for picker list, preview modal, and initial shell.
- Diagnostics flag `WEB_THEME_PICKER_DIAGNOSTICS=1` enabling fallback description flag, editorial quality badges, uncapped synergy toggle, YAML fetch, metrics endpoint.
- Cache bust hooks on catalog refresh & tagging completion clearing filter & preview caches (metrics include `preview_last_bust_at`).
- Optional filter cache prewarm (`WEB_THEME_FILTER_PREWARM=1`) priming common filter combinations; metrics include `filter_prewarmed`.
- Preview modal UX: role chips, condensed reasons line, hover tooltip with multiline heuristic reasons, export bar (CSV/JSON) honoring curated-only toggle.
- Server authoritative mana & color identity ingestion (exposes `mana_cost`, `color_identity_list`, `pip_colors`) replacing client-side parsing.
 - Adaptive preview cache eviction heuristic replacing FIFO: protection score combines log(hit_count), recency, build cost bucket, and age penalty with env-tunable weights (`THEME_PREVIEW_EVICT_W_HITS`, `_W_RECENCY`, `_W_COST`, `_W_AGE`) plus cost thresholds (`THEME_PREVIEW_EVICT_COST_THRESHOLDS`). Metrics now include total evictions, by-reason counts (`low_score`, `emergency_overflow`), and last eviction metadata.
 - Scryfall name normalization regression test (`test_scryfall_name_normalization.py`) ensuring synergy annotation suffix (` - Synergy (...)`) never leaks into fuzzy/image queries.
 - Optional multi-pass performance CI variant (`preview_perf_ci_check.py --multi-pass`) to collect cold vs warm pass stats when diagnosing divergence.

### Changed
- Deck builder theme spell filler now consumes the shared ThemeContext weighting so user-supplied supplemental themes influence both creature and non-creature selections, with user weight multipliers boosting spell picks in parity with creatures.
- Random theme pool builder loads manual exclusions and always emits `auto_filled_themes` as a list (empty when unused), while enhanced metadata powers diagnostics telemetry.
- Random build summaries normalize multi-theme metadata before embedding in summary payloads and sidecar exports (trimming whitespace, deduplicating/normalizing resolved theme lists).
- Random Mode strict-theme toggle is now fully stateful: the checkbox and hidden field keep session/local storage in sync, HTMX rerolls reuse the flag, and API/full-build responses plus permalinks carry `strict_theme_match` through exports and sidecars.
- Multi-theme filtering now pre-caches lowercase tag lists and builds a reusable token index so AND-combos and synergy fallback avoid repeated pandas `.apply` passes; profiling via `code/scripts/profile_multi_theme_filter.py` shows mean ~9.3 ms / p95 ~21 ms for cascade checks (seed 42, 300 iterations).
- Random reroll (locked commander) export flow: now reuses builder-exported artifacts when present and records `last_csv_path` / `last_txt_path` inside the headless runner to avoid duplicate suffixed files.
- Summary sidecars for random builds include `locked_commander` flag when rerolling same commander.
- Splash analytics recognize both static and adaptive penalty reasons (shared prefix handling), so existing dashboards continue to work when `SPLASH_ADAPTIVE=1`.
- Random full builds now internally force `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=1` (if unset) ensuring only the orchestrated export path executes (eliminates historical duplicate `*_1.csv` / `*_1.txt`). Set `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=0` to intentionally restore the legacy double-export (not recommended outside debugging).
- Multi-theme Random UI polish: fallback notices now surface high-contrast icons, focus outlines, and aria-friendly copy; diagnostics badges gain icons/labels; help tooltip converted to an accessible popover with keyboard support; Secondary/Tertiary inputs persist across sessions.
- Picker list & API use optimized fast filtering path (`filter_slugs_fast`) replacing per-request linear scans.
- Preview sampling: curated examples pinned first, diversity quotas (~40% payoff / 40% enabler+support / 20% wildcard), synthetic placeholders only if underfilled.
- Sampling refinements: rarity diminishing weight, splash leniency (single off-color allowance with penalty for 4–5 color commanders), role saturation penalty, refined commander overlap scaling curve.
- Hover / DFC UX unified: single hover panel, overlay flip control (keyboard + persisted face), enlarged thumbnails (110px→165px→230px), activation limited to thumbnails.
- Removed legacy client-side mana & color identity parsers (now server authoritative fields included in preview items and export endpoints).
- Core Refactor Phase A continued: separated sampling + cache container; card index & adaptive TTL/background refresh extraction planned (roadmap updated) to further reduce `theme_preview.py` responsibilities.
 - Eviction: removed hard 50-entry minimum to support low-limit unit tests; production should set `THEME_PREVIEW_CACHE_MAX` accordingly.
 - Governance: README governance appendix now documents taxonomy snapshot usage and rationale.
 - Removed hard minimum (50) floor in eviction capacity logic to allow low-limit unit tests; operational environments should set `THEME_PREVIEW_CACHE_MAX` appropriately.
 - Performance gating formalized: CI fails if warm p95 regression > configured threshold (default 5%). Baseline refresh policy: only update committed warm baseline when (a) intentional performance improvement >10% p95, or (b) unavoidable drift exceeds threshold and is justified in CHANGELOG entry.

### Fixed
- Random UI Surprise Me rerolls now keep user-supplied theme inputs instead of adopting fallback combinations, and reroll-same-commander builds reuse cached resolved themes without re-running the filter cascade.
- Removed redundant template environment instantiation causing inconsistent navigation state.
- Ensured preview cache key includes catalog ETag to prevent stale sample reuse after catalog reload.
- Explicit cache bust after tagging/catalog rebuild prevents stale preview exposure.
- Random build duplicate export issue resolved: suppression of the initial builder auto-export prevents creation of suffixed duplicate decklists.
- Random Mode UI regressions (deck summary toggle & hover preview) fixed by replacing deferred script execution with inline handlers and an HTMX load hook.

### Editorial / Themes
- Enforce minimum `example_commanders` threshold (>=5) in CI; lint fails builds when a non-alias theme drops below threshold.
- Added enforcement test `test_theme_editorial_min_examples_enforced.py` to guard regression.
- Governance workflow updated to pass `--enforce-min-examples` and set `EDITORIAL_MIN_EXAMPLES_ENFORCE=1`.
- Clarified lint script docstring and behavior around enforced minimums.
- (Planned next) Removal of deprecated alias YAMLs & promotion of strict alias validation to hard fail (post grace window).

### Added
- Phase D close-out: strict alias enforcement promoted to hard fail in CI (`validate_theme_catalog.py --strict-alias`) removing previous soft warning behavior.
- Phase D close-out: minimum example commander enforcement (>=5) now mandatory; failing themes block CI.
- Tagging: Added archetype detection for Pillowfort, Politics, Midrange, and Toolbox with new pattern & specific card heuristics.
- Tagging orchestration: Extended `tag_by_color` to execute new archetype taggers in sequence before bracket policy application.
- Governance workflows: Introduced `.github/workflows/editorial_governance.yml` and `.github/workflows/editorial_lint.yml` for isolated lint + governance checks.
- Editorial schema: Added `editorial_quality` to both YAML theme model and catalog ThemeEntry Pydantic schemas.
- Editorial data artifacts: Added `config/themes/description_mapping.yml`, `synergy_pairs.yml`, `theme_clusters.yml`, `theme_popularity_metrics.json`, `description_fallback_history.jsonl`.
- Editorial tooling: New scripts for enrichment & governance: `augment_theme_yaml_from_catalog.py`, `autofill_min_examples.py`, `pad_min_examples.py`, `cleanup_placeholder_examples.py`, `purge_anchor_placeholders.py`, `ratchet_description_thresholds.py`, `report_editorial_examples.py`, `validate_description_mapping.py`, `synergy_promote_fill.py` (extension), `run_build_with_fallback.py`, `migrate_provenance_to_metadata_info.py`, `theme_example_cards_stats.py`.
- Tests: Added governance + regression suite (`test_theme_editorial_min_examples_enforced.py`, `test_theme_description_fallback_regression.py`, `test_description_mapping_validation.py`, `test_editorial_governance_phase_d_closeout.py`, `test_synergy_pairs_and_metadata_info.py`, `test_synergy_pairs_and_provenance.py`, `test_theme_catalog_generation.py`, updated `test_theme_merge_phase_b.py` & validation Phase C test) for editorial pipeline stability.

- Editorial tooling: `synergy_promote_fill.py` new flags `--no-generic-pad` (allow intentionally short example_cards without color/generic padding), `--annotate-color-fallback-commanders` (explain color fallback commander selections), and `--use-master-cards` (opt-in to consolidated `cards.csv` sourcing; shard `[color]_cards.csv` now default).
- Name canonicalization for card ingestion: duplicate split-face variants like `Foo // Foo` collapse to `Foo`; when master enabled, prefers `faceName`.
- Commander rebuild annotation: base-first rebuild now appends ` - Color Fallback (no on-theme commander available)` to any commander added purely by color identity.
- Roadmap: Added `logs/roadmaps/theme_editorial_roadmap.md` documenting future enhancements & migration plan.
- Theme catalog Phase B: new unified merge script `code/scripts/build_theme_catalog.py` (opt-in via THEME_CATALOG_MODE=merge) combining analytics + curated YAML + whitelist governance with metadata block output.
- Theme metadata: `theme_list.json` now includes `metadata_info` (formerly `provenance`) capturing generation context (mode, generated_at, curated_yaml_files, synergy_cap, inference version). Legacy key still parsed for backward compatibility.
- Theme governance: whitelist configuration `config/themes/theme_whitelist.yml` (normalization, always_include, protected prefixes/suffixes, enforced synergies, synergy_cap).
- Theme extraction: dynamic ingestion of CSV-only tags (e.g., Kindred families) and PMI-based inferred synergies (positive PMI, co-occurrence threshold) blended with curated pairs.
- Enforced synergy injection for counters/tokens/graveyard clusters (e.g., Proliferate, Counters Matter, Graveyard Matters) before capping.
- Test coverage: `test_theme_whitelist_and_synergy_cap.py` ensuring enforced synergies present and cap (5) respected.
- Dependency: added PyYAML (optional runtime dependency for governance file parsing).
- CI: additional checks to improve stability and reproducibility.
- Tests: broader coverage for validation and web flows.
- Randomizer groundwork: added a small seeded RNG utility (`code/random_util.py`) and determinism unit tests; threaded RNG through Phase 3 (creatures) and Phase 4 (spells) for deterministic sampling when seeded.
- Random Modes (alpha): thin wrapper entrypoint `code/deck_builder/random_entrypoint.py` to select a commander deterministically by seed, plus a tiny frozen dataset under `csv_files/testdata/` and tests `code/tests/test_random_determinism.py`.
- Theme Editorial: automated example card/commander suggestion + enrichment (`code/scripts/generate_theme_editorial_suggestions.py`).
- Synergy commanders: derive 3/2/1 candidates from top three synergies with legendary fallback; stored in `synergy_commanders` (annotated) separate from `example_commanders`.
- Per-synergy annotations: `Name - Synergy (Synergy Theme)` applied to promoted example commanders and retained in synergy list for transparency.
- Augmentation flag `--augment-synergies` to repair sparse `synergies` arrays (e.g., inject `Counters Matter`, `Proliferate`).
- Lint upgrades (`code/scripts/lint_theme_editorial.py`): validates annotation correctness, filtered synergy duplicates, minimum example_commanders, and base-name deduping.
- Pydantic schema extension (`type_definitions_theme_catalog.py`) adding `synergy_commanders` and editorial fields to catalog model.
- Phase D (Deferred items progress): enumerated `deck_archetype` list + validation, derived `popularity_bucket` classification (frequency -> Rare/Niche/Uncommon/Common/Very Common), deterministic editorial seed (`EDITORIAL_SEED`) for stable inference ordering, aggressive fill mode (`EDITORIAL_AGGRESSIVE_FILL=1`) to pad ultra-sparse themes, env override `EDITORIAL_POP_BOUNDARIES` for bucket thresholds.
- Catalog backfill: build script can now write auto-generated `description` and derived/pinned `popularity_bucket` back into individual YAML files via `--backfill-yaml` (or `EDITORIAL_BACKFILL_YAML=1`) with optional overwrite `--force-backfill-yaml`.
- Catalog output override: new `--output <path>` flag on `build_theme_catalog.py` enables writing an alternate JSON (used by tests) without touching the canonical `theme_list.json` or performing YAML backfill.
- Editorial lint escalation: new flags `--require-description` / `--require-popularity` (or env `EDITORIAL_REQUIRE_DESCRIPTION=1`, `EDITORIAL_REQUIRE_POPULARITY=1`) to enforce presence of description and popularity buckets; strict mode also treats them as errors.
- Tests: added `test_theme_catalog_generation.py` covering deterministic seed reproducibility, popularity boundary overrides, absence of YAML backfill on alternate output, and presence of descriptions.
- Editorial fallback summary: optional inclusion of `description_fallback_summary` in `theme_list.json` via `EDITORIAL_INCLUDE_FALLBACK_SUMMARY=1` for coverage metrics (generic vs specialized descriptions) and prioritization.
- External description mapping (Phase D): curators can now add/override auto-description rules via `config/themes/description_mapping.yml` without editing code (first match wins, `{SYNERGIES}` placeholder supported).

### Changed
- Archetype presence test now gracefully skips when generated catalog YAML assets are absent, avoiding false negatives in minimal environments.
- Tag constants and tagger extended; ordering ensures new archetype tags applied after interaction tagging but before bracket policy enforcement.
- CI strict alias step now fails the build instead of continuing on error.
- Example card population now sources exclusively from shard color CSV files by default (avoids variant noise from master `cards.csv`). Master file usage is explicit opt-in via `--use-master-cards`.
- Heuristic text index aligned with shard-only sourcing and canonical name normalization to prevent duplicate staple leakage.
- Terminology migration: internal model field `provenance` fully migrated to `metadata_info` across code, tests, and 700+ YAML catalog files via automated script (`migrate_provenance_to_metadata_info.py`). Backward-compatible aliasing retained temporarily; deprecation window documented.
- Example card duplication suppression: `synergy_promote_fill.py` adds `--common-card-threshold` and `--print-dup-metrics` to filter overly common generic staples based on a pre-run global frequency map.
- Synergy lists for now capped at 5 entries (precedence: curated > enforced > inferred) to improve UI scannability.
- Curated synergy matrix expanded (tokens, spells, artifacts/enchantments, counters, lands, graveyard, politics, life, tribal umbrellas) with noisy links (e.g., Burn on -1/-1 Counters) suppressed via denylist + PMI filtering.
- Synergy noise suppression: "Legends Matter" / "Historics Matter" pairs are now stripped from every other theme (they were ubiquitous due to all legendary & historic cards carrying both tags). Only mutual linkage between the two themes themselves is retained.
- Theme merge build now always forces per-theme YAML export so `config/themes/catalog/*.yml` stays synchronized with `theme_list.json`. New env `THEME_YAML_FAST_SKIP=1` allows skipping YAML regeneration only on fast-path refreshes (never on full builds) if desired.
- Tests: refactored to use pytest assertions and cleaned up fixtures/utilities to reduce noise and deprecations.
- Tests: HTTP-dependent tests now skip gracefully when the local web server is unavailable.
- `synergy_commanders` now excludes any commanders already promoted into `example_commanders` (deduped by base name after annotation).
- Promotion logic ensures a configurable minimum (default 5) example commanders via annotated synergy promotions.
- Regenerated per-theme YAML files are environment-dependent (card pool + tags); README documents that bulk committing the entire regenerated catalog is discouraged to avoid churn.
- Lint enhancements: archetype enumeration expanded (Combo, Aggro, Control, Midrange, Stax, Ramp, Toolbox); strict mode now promotes cornerstone missing examples to errors; popularity bucket value validation.
- Regression thresholds tightened for generic description fallback usage (see `test_theme_description_fallback_regression.py`), lowering allowed generic total & percentage to drive continued specialization.
- build script now auto-exports Phase A YAML catalog if missing before attempting YAML backfill (safeguard against accidental directory deletion).

### Fixed
- Commander eligibility logic was overly permissive. Now only:
- Missing secondary synergies (e.g., `Proliferate` on counter subthemes) restored via augmentation heuristic preventing empty synergy follow-ons.
  - Legendary Creatures (includes Artifact/Enchantment Creatures)
  - Legendary Artifact Vehicles / Spacecraft that have printed power & toughness
  - Any card whose rules text contains "can be your commander" (covers specific planeswalkers, artifacts, others)
  are auto‑eligible. Plain Legendary Enchantments (non‑creature), Legendary Planeswalkers without the explicit text, and generic Legendary Artifacts are no longer incorrectly included.
- Removed one-off / low-signal themes (global frequency <=1) except those protected or explicitly always included via whitelist configuration.
- Tests: reduced deprecation warnings and incidental failures; improved consistency and reliability across runs.

### Deprecated
- `provenance` catalog/YAML key: retained as read-only alias; will be removed after two minor releases in favor of `metadata_info`. Warnings to be added prior to removal.

## [2.2.10] - 2025-09-11

### Changed
- Web UI: Test Hand uses a default fanned layout on desktop with tightened arc and 40% overlap; outer cards sit lower for a full-arc look
- Desktop Test Hand card size set to 280×392; responsive sizes refined at common breakpoints
- Theme controls moved from the top banner to the bottom of the left sidebar; sidebar made a flex column with the theme block anchored at the bottom
- Mobile banner simplified to show only Menu, title; spacing and gaps tuned to prevent overflow and wrapping

### Fixed
- Prevented mobile banner overflow by hiding non-essential items and relocating theme controls
- Ensured desktop sizing wins over previous inline styles by using global CSS overrides; cards no longer shrink due to flex

## [2.2.9] - 2025-09-10

### Added
- Dynamic misc utility land EDHREC keep range env docs and theme weighting overrides
- Land alternatives randomization (12 suggestions from random top 60–100 window) and land-only parity filtering

### Changed
- Compose and README updated with new misc land tuning environment variables

### Fixed
- Step 5 scroll flicker at bottom for small grids (virtualization skip <80 items + overscroll containment)
- Fetch lands excluded from misc land step; mono-color rainbow filtering improvements

## [2.2.8] - 2025-09-10

## [2.2.7] - 2025-09-10

### Added
- Comprehensive structured logging for include/exclude operations with event tracking
- Include/exclude card lists feature with `ALLOW_MUST_HAVES=true` environment variable flag
- Phase 1 exclude-only implementation: filter cards from deck building pool before construction
- Web UI "Advanced Options" section with exclude cards textarea and file upload (.txt)
- Live validation for exclude cards with count and limit warnings (max 15 excludes)
- JSON export/import support preserving exclude_cards in permalink system
- Fuzzy card name matching with punctuation/spacing normalization
- Comprehensive backward compatibility tests ensuring existing workflows unchanged
- Performance benchmarks: exclude filtering <50ms for 20k+ cards, validation API <100ms
- File upload deduplication and user feedback for exclude lists
- Extended DeckBuilder schema with full include/exclude configuration support
- Include/exclude validation with fuzzy matching, strict enforcement, and comprehensive diagnostics
- Full JSON round-trip functionality preserving all include/exclude configuration in headless and web modes
- Comprehensive test suite covering validation, persistence, fuzzy matching, and backward compatibility
- Engine integration with include injection after lands, before creatures/spells with ordering tests
- Exclude re-entry prevention ensuring blocked cards cannot re-enter via downstream heuristics
- Web UI enhancement with two-column layout, chips/tag UI, and real-time validation
- EDH format compliance checking for include/exclude cards against commander color identity

### Changed
- **Test organization**: Moved all test files from project root to centralized `code/tests/` directory for better structure
- **CLI enhancement: Enhanced help text with type indicators** - All CLI arguments now show expected value types (PATH, NAME, INT, BOOL) and organized into logical groups
- **CLI enhancement: Ideal count arguments** - New CLI flags for deck composition: `--ramp-count`, `--land-count`, `--basic-land-count`, `--creature-count`, `--removal-count`, `--wipe-count`, `--card-advantage-count`, `--protection-count`
- **CLI enhancement: Theme tag name support** - Theme selection by name instead of index: `--primary-tag`, `--secondary-tag`, `--tertiary-tag` as alternatives to numeric choices
- **CLI enhancement: Include/exclude CLI support** - Full CLI parity for include/exclude with `--include-cards`, `--exclude-cards`, `--enforcement-mode`, `--allow-illegal`, `--fuzzy-matching`
- **CLI enhancement: Console summary printing** - Detailed include/exclude summary output for headless builds with diagnostics and validation results
- Enhanced fuzzy matching with 300+ Commander-legal card knowledge base and popular/iconic card prioritization
- Card constants refactored to dedicated `builder_constants.py` with functional organization
- Fuzzy match confirmation modal with dark theme support and card preview functionality
- Include/exclude summary panel showing build impact with success/failure indicators and validation issues
- Comprehensive Playwright end-to-end test suite covering all major user flows and mobile layouts
- Mobile responsive design with bottom-floating build controls for improved thumb navigation
- Two-column grid layout for mobile build controls reducing vertical space usage by ~50%
- Mobile horizontal scrolling prevention with viewport overflow controls and setup status optimization
- Enhanced visual feedback with warning indicators (⚠️ over-limit, ⚡ approaching limit) and color coding
- Performance test framework tracking validation and UI response times
- Advanced list size validation with live count displays and visual warnings
- Enhanced validation endpoint with comprehensive diagnostics and conflict detection
- Chips/tag UI for per-card removal with visual distinction (green includes, red excludes)
- Staging system architecture support with custom include injection runner for web UI
- Complete include/exclude functionality working end-to-end across both web UI and CLI interfaces
- Enhanced list size validation UI with visual warning system (⚠️ over-limit, ⚡ approaching limit) and color coding
- Legacy endpoint transformation maintaining exact message formats for seamless integration with existing workflows

### Fixed
- JSON config files are now properly re-exported after bracket compliance enforcement and auto-swapping
- Mobile horizontal scrolling issues resolved with global viewport overflow controls
- Mobile UI setup status stuttering eliminated by removing temporary "Setup complete" message displays
- Mobile build controls accessibility improved with bottom-floating positioning for thumb navigation
- Mobile viewport breakpoint expanded from 720px to 1024px for broader device compatibility
- Docker image: expanded entrypoint seeding now copies all default card list JSON files (extra_turns, game_changers, mass_land_denial, tutors_nonland, etc.) and brackets.yml when missing, preventing missing list issues with mounted blank config volumes

## [2.2.6] - 2025-09-04

### Added
- Bracket policy enforcement: global pool-level prune for disallowed categories when limits are 0 (e.g., Game Changers in Brackets 1–2). Applies to both Web and headless runs.
- Inline enforcement UI: violations surface before the summary; Continue/Rerun disabled until you replace or remove flagged cards. Alternatives are role-consistent and exclude commander/locked/in-deck cards.
- Auto-enforce option: `WEB_AUTO_ENFORCE=1` to apply the enforcement plan and re-export when compliance fails.

### Changed
- Spells and creatures phases apply bracket-aware pre-filters to reduce violations proactively.
- Compliance detection for Game Changers falls back to in-code constants when `config/card_lists/game_changers.json` is empty.
- Data refresh: updated static lists used by bracket compliance/enforcement with current card names and metadata:
  - `config/card_lists/extra_turns.json`
  - `config/card_lists/game_changers.json`
  - `config/card_lists/mass_land_denial.json`
  - `config/card_lists/tutors_nonland.json`
  Each list includes `list_version: "manual-2025-09-04"` and `generated_at`.

### Fixed
- Summary/export mismatch in headless JSON runs where disallowed cards could be pruned from exports but appear in summaries; global prune ensures consistent state across phases and reports.

### Notes
- These lists underpin the bracket enforcement feature introduced in 2.2.5; shipping them as a follow-up release ensures consistent results across Web and headless runs.

## [2.2.5] - 2025-09-03

### Added
- Bracket WARN thresholds: `config/brackets.yml` supports optional `<category>_warn` keys (e.g., `tutors_nonland_warn`, `extra_turns_warn`). Compliance now returns PASS/WARN/FAIL; low brackets (1–2) conservatively WARN on presence of tutors/extra_turns when thresholds aren’t provided.
- Web UI compliance polish: the panel auto-opens on non-compliance (WARN/FAIL) and shows a colored overall status chip (green/WARN amber/red). WARN items now render as tiles with a subtle amber style and a WARN badge; tiles and enforcement actions remain FAIL-only.
- Tests: added coverage to ensure WARN thresholds from YAML are applied and that fallback WARN behavior appears for low brackets.

### Changed
- Web: flagged metadata now includes WARN categories with a `severity` field to support softer UI rendering for advisory cases.

## [2.2.4] - 2025-09-02

### Added
- Mobile: Collapsible left sidebar with persisted state; sticky build controls adjusted for mobile header.
- New Deck modal integrates Multi-Copy suggestions (opt-in) and commander/theme preview.
- Web: Setup/Refresh prompt modal shown on Create when environment is missing or stale; routes to `/setup/running` (force on stale) and transitions into the progress view. Template: `web/templates/build/_setup_prompt_modal.html`.
- Orchestrator helpers: `is_setup_ready()` and `is_setup_stale()` for non-invasive readiness/staleness checks from the UI.
- Env flags for setup behavior: `WEB_AUTO_SETUP` (default 1) to enable/disable auto setup, and `WEB_AUTO_REFRESH_DAYS` (default 7) to tune staleness.
- Step 5 error context helper: `web/services/build_utils.step5_error_ctx()` to standardize error payloads for `_step5.html`.
- Templates: reusable lock/unlock button macro at `web/templates/partials/_macros.html`.
- Templates: Alternatives panel partial at `web/templates/build/_alternatives.html` (renders candidates with Owned-only toggle and Replace actions).

### Tests
- Added smoke/unit tests covering:
  - `summary_utils.summary_ctx()`
  - `build_utils.start_ctx_from_session()` (monkeypatched orchestrator)
  - `orchestrator` staleness/setup paths
  - `build_utils.step5_error_ctx()` shape and flags

### Changed
- Mobile UI scaling and layout fixed across steps; overlap in DevTools emulation resolved with CSS variable offsets for sticky elements.
- Multi-Copy is now explicitly opt-in from the New Deck modal; suggestions are filtered to only show archetypes whose matched tags intersect the user-selected themes (e.g., Rabbit Kindred shows only Hare Apparent).
- Web cleanup: centralized combos/synergies detection and model/version loading in `web/services/combo_utils.py` and refactored routes to use it:
  - `routes/build.py` (Combos panel), `routes/configs.py` (run results), `routes/decks.py` (finished/compare), and diagnostics endpoint in `app.py`.
- Create (New Deck) flow: no longer auto-runs setup on submit; instead presents a modal prompt to run setup/refresh when needed.
- Step 5 builder flow: deduplicated template context assembly via `web/services/build_utils.py` helpers and refactored `web/routes/build.py` accordingly (fewer repeated dicts, consistent fields).
- Staged build context creation centralized via `web/services/build_utils.start_ctx_from_session` and applied across Step 5 flows in `web/routes/build.py` (New submit, Continue, Start, Rerun, Rewind).
- Owned-cards set creation centralized via `web/services/build_utils.owned_set()` and used in `web/routes/build.py`, `web/routes/configs.py`, and `web/routes/decks.py`.
 - Step 5: replaced ad-hoc empty context assembly with `web/services/build_utils.step5_empty_ctx()` in GET `/build/step5` and `reset-stage`.
 - Builder introspection: adopted `builder_present_names()` and `builder_display_map()` helpers in `web/routes/build.py` for locked-cards and alternatives, reducing duplication and improving casing consistency.
 - Alternatives endpoint now renders the new partial (`build/_alternatives.html`) via Jinja and caches the HTML (no more string-built HTML in the route).

### Added
- Deck summary: introduced `web/services/summary_utils.summary_ctx()` to unify summary context (owned_set, game_changers, combos/synergies, versions).
 - Alternatives cache helper extracted to `web/services/alts_utils.py`.

### Changed
- Decks and Configs routes now use `summary_ctx()` to render deck summaries, reducing duplication and ensuring consistent fields.
- Build: routed owned names via helper and fixed `_rebuild_ctx_with_multicopy` context indentation.
 - Build: moved alternatives TTL cache into `services/alts_utils` for readability.
 - Build: Step 5 start error path now uses `step5_error_ctx()` for a consistent UI.
  - Build: Extended Step 5 error handling to Continue, Rerun, and Rewind using `step5_error_ctx()`.

### Fixed
- Continue button responsiveness on mobile fixed (eliminated sticky overlap); Multi-Copy application preserved across New Deck submit; emulator misclicks resolved.
- Banner subtitle now stays inline inside the header when the menu is collapsed (no overhang/wrap to a new row).
- Docker: normalized line endings for `entrypoint.sh` during image build to avoid `env: 'sh\r': No such file or directory` on Windows checkouts.

### Removed
- Duplicate root route removed: `web/routes/home.py` was deleted; the app root is served by `web/app.py`.

## [2.2.3] - 2025-09-01
### Fixes
- Bug causing basic lands to no longer be added due to combined dataframe not including basics

### Changed
- Logic for removal tagging causing self-targetting cards (e.g. Conjurer's Closet) to be tagged as removal

## [2.2.2] - 2025-09-01
### Fixed
- Ensure default config files are available when running with bind-mounted config directories:
  - Dockerfile now preserves a copy of defaults at `/.defaults/config` in the image.
  - Entrypoint seeds missing files into `/app/config` on container start (`deck.json`, `card_lists/combos.json`, `card_lists/synergies.json`).
  - Adds a back-compat symlink `combo.json -> combos.json` if missing.
  This resolves cases where a blank host `config/` overlay made files appear missing.

### Changed
- Example compose files updated to use `APP_VERSION=v2.2.2`.

## [2.2.1] - 2025-09-01
### Added
- Combos & Synergies: detect curated two-card combos/synergies and surface them in a chip-style panel with badges (cheap/early, setup) on Step 5 and Finished Decks.
- Dual hover previews for combo rows: hovering a combo shows both cards side-by-side in the standard preview popout; individual names still preview a single card.
- Headless (Web Configs): JSON configs now persist and honor combo preferences:
  - `prefer_combos` (bool)
  - `combo_target_count` (int)
  - `combo_balance` ("early" | "late" | "mix")
  Exported interactive run-config JSON includes these fields when used.
- Finished Deck summary includes detected combos/synergies and curated list version badges.
- When `prefer_combos` is enabled, Auto-Complete Combos runs before theme fill/monolithic spells so partners aren’t clamped away. Existing completed pairs count toward the target before adding partners.
- Step 5 Combos panel updated to the same chip-style as Finished Decks for consistency.
- Auto-combos respect color identity by resolving from the filtered pool only; off-color/unavailable partners are skipped.
- Added type/mana enrichment for auto-added partners and lock placeholders to avoid “Other” category leakage.

## [2.1.1] - 2025-08-29
### Added
- Multi-copy archetypes (Web): opt-in modal suggests packages like Persistent Petitioners, Dragon's Approach, and Shadowborn Apostle when viable; choose quantity and optionally add Thrumming Stone. Applied as the first stage with ideal count adjustments and a per-stage 100-card safety clamp. UI surfaces adjustments and a clamp chip.

### Changed
- Multi-copy modal now appears immediately after commander selection (pre-build) in Step 2. This reduces surprise and lets users make a choice earlier.
- Stage order updated so the Multi-Copy package is applied first in Step 5, with land steps following on the next Continue. Lands now account for the package additions when filling.

### Fixed
- Ensured apostrophes in multi-copy card names remain safe in templates while rendering correctly in the UI.

## [2.0.1] - 2025-08-28

### Added
- Web UI performance: optional virtualized grids/lists in Step 5 and Owned (enable with `WEB_VIRTUALIZE=1`).
- Virtualization diagnostics overlay (when `SHOW_DIAGNOSTICS=1`); press `v` to toggle per‑grid overlays and a global summary bubble with visible range, totals, render time, and counters.
- Image polish: lazy‑loading with responsive `srcset/sizes` and LQIP blur/fade‑in for Step 5 and Owned thumbnails and the commander preview image.
- Short‑TTL fragment caching for template partials (e.g., finished deck summaries and config run summaries) to reduce re‑render cost.
- Web UI: FastAPI + Jinja front-end for the builder; staged build view with per-stage reasons
- New Deck modal consolidating steps 1–3 with optional Name for exports, Enter-to-select commander, and disabled browser autofill
- Locks, Replace flow, Compare builds, and shareable permalinks for finished decks
- Compare page: Copy summary action to copy diffs (Only in A/B and Changed counts) to clipboard
 - Finished Decks multi-select → Compare with fallback to "Latest two"; options carry modified-time for ordering
 - Permalinks include locks; global "Open Permalink…" entry exposed in header and Finished Decks
 - Replace flow supports session-local Undo and lock-aware validation
- New Deck modal: inline summary of selected themes with order (1, 2, 3)
- Theme combine mode (AND/OR) with tooltips and selection-order display in the Web UI
- AND-mode creatures pre-pass: select "all selected themes" creatures first, then fill by weighted overlap; staged reasons show matched themes
- Scryfall attribution footer in the Web UI
- Owned-cards workflow:
  - Prompt (only if lists exist) to "Use only owned cards?"
  - Support multiple file selection; parse `.txt` (1 per line) and `.csv` (any `name` column)
  - Owned-only mode filters the pool to owned names; commander exempt
  - Recommendations export when owned-only deck is incomplete (~1.5× missing) to `deck_files/[stem]_recommendations.csv` and `.txt`
- CSV export includes an `Owned` column when not using owned-only
- Windows EXE build via PyInstaller is produced on tag and attached to GitHub Releases
 - Prefer-owned option in Review: bias selection toward owned cards while allowing unowned fallback (stable reorder + gentle weight boosts applied across creatures and spells)
 - Owned page enhancements: export TXT/CSV, sort controls, live "N shown," color identity dots, exact color-identity combo filters (incl. 4-color), viewport-filling list, and scrollbar styling
 - Finished Decks: theme filters converted to a dropdown with shareable state
 - Staged build: optional "Show skipped stages" toggle to surface stages that added no cards with a clear annotation
 - Owned/Not-owned badges visible across views; consolidated CSS for consistent placement
 - Visual summaries: Mana Curve, Color Pips and Sources charts with cross-highlighting to cards; tooltips show per-color card lists and include a Copy action
 - Source detection: include non-land mana producers and colorless 'C'; basic lands reliably counted; fetch lands excluded as sources
 - Favicon support: `/favicon.ico` served (ICO with PNG fallback)
 - Diagnostics: `/healthz` endpoint returns `{status, version, uptime_seconds}`; responses carry `X-Request-ID`; unhandled errors return JSON with request_id
 - Diagnostics page and tools gated by `SHOW_DIAGNOSTICS`; Logs page gated by `SHOW_LOGS`; both off by default
 - Global error handling: friendly HTML templates for 404/4xx/500 with Request-ID and "Go home" link; JSON structure for HTMX/API
 - Request-ID middleware assigns `X-Request-ID` to all responses and includes it in JSON error payloads
 - `/status/logs?tail=N` endpoint (read-only) to fetch a recent log tail for quick diagnostics
 - Tooltip Copy action on chart tooltips (Pips/Sources) for quick sharing of per-color card lists
- Theme UX: Header includes a Reset Theme control to clear browser preference and reapply server default (THEME) or system mapping. Diagnostics page shows resolved theme and stored preference with a reset action.

Roadmap and usage for Web UI features are tracked in `logs/web-ui-upgrade-outline.md`.

### Changed
- Accessibility: respect OS “reduced motion” by disabling blur/fade transitions and smooth scrolling.
- Static asset caching and compression tuned for the web service (cache headers + gzip) to improve load performance.
- Rename folder from `card_library` to `owned_cards` (env override: `OWNED_CARDS_DIR`; back-compat respected)
- Docker assets and docs updated:
  - New volume mounts: `./owned_cards:/app/owned_cards` and `./config:/app/config`
  - Compose and helper scripts updated accordingly
- Release notes source is `RELEASE_NOTES_TEMPLATE.md`; `RELEASE_NOTES.md` ignored
- README/DOCKER/WINDOWS_DOCKER_GUIDE updated for Web UI, headless examples, and PowerShell-friendly commands
- Headless: tag_mode (AND/OR) accepted from JSON and environment and exported in interactive run-config JSON
 - Owned lists are enriched at upload-time and persisted in an internal store; header rows skipped and duplicates deduped; per-request parsing removed
 - Builder Review (Step 4): "Use only owned cards" toggle moved here; Step 5 is status-only with "Edit in Review" for changes
 - Minor UI/CSS polish and consolidation across builder/owned pages
 - Deck summary reporting now includes colorless 'C' in totals and cards; UI adds a Show C toggle for Sources
 - New Deck modal submits directly to build, removing the intermediate review step
 - Finished Decks banner and lists now prefer the custom Name provided in the modal
 - Step 5 Replace toggle now includes a tooltip clarifying that reruns will replace picks in that stage when enabled
 - Locks are enforced on rerun; the Locked section live-updates on unlock (row removal and chip refresh)
 - Compare page shows ▲/▼ indicators on Changed counts and preserves the "Changed only" toggle across interactions
 - Bracket selector shows numbered labels (e.g., "Bracket 3: Upgraded") and defaults to bracket 3 on new deck creation
 - List view highlight polished to wrap only the card name (no overrun of the row)
 - Total sources calculation updated to include 'C' properly
 - 404s from Starlette now render the HTML 404 page when requested from a browser (Accept: text/html)
 - Owned page UX: full-size preview now pops on thumbnail hover (not the name); selection highlight tightened to the thumbnail only and changed to white for better contrast; Themes in the hover popout render as a larger bullet list with a brighter "THEMES" label
 - Image robustness: standardized `data-card-name` on all Scryfall images and centralized retry logic (thumbnails + previews) with version fallbacks (small/normal/large) and a single cache-bust refresh on final failure; removed the previous hover-image cache to reduce complexity and overhead
- Layout polish: fixed sidebar remains full-height under the banner with a subtle right-edge shadow for depth; grid updated to prevent content squish; extra scroll removed; footer pinned when content is short.
 - Deck Summary list view: rows use fixed tracks for count, ×, name, and owned columns (monospace tabular numerals) to ensure perfect alignment; highlight is an inset box-shadow on the name to avoid layout shifts; long names ellipsize with a tooltip; list starts directly under the type header and remains stable on full-screen widths

### Fixed
- Docker Hub workflow no longer publishes a `major.minor` tag (e.g., `1.1`); only full semver (e.g., `1.2.3`) and `latest`
 - Owned page internal server error resolved via hardened template context and centralized owned context builder
 - Web container crash resolved by removing invalid union type annotation in favicon route; route now returns a single Response type
 - Source highlighting consistency: charts now correctly cross-highlight corresponding cards in both list and thumbnail views
 - Basics handling: ensured basic lands and Wastes are recognized as sources; added fallback oracle text for basics in CSV export
 - Fetch lands are no longer miscounted as mana sources
 - Web 404s previously returned JSON to browsers in some cases; now correctly render HTML via a Starlette HTTPException handler
 - Windows PowerShell curl parsing issue documented with guidance in README
 - Deck summary alignment issues in some sections (e.g., Enchantments) fixed by splitting the count and the × into separate columns and pinning the owned flag to a fixed width; prevents drift across responsive breakpoints
 - Banned list filtering applied consistently to all color/guild CSV generation paths with exact, case-insensitive matching on name/faceName (e.g., Hullbreacher, Dockside Extortionist, and Lutri are excluded)

---

For prior releases, see the GitHub Releases page.
