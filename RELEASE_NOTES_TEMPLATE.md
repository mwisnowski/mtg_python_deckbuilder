# MTG Python Deckbuilder ${VERSION}

## Highlights
- **Include/Exclude Cards Feature Complete**: Full implementation with enhanced web UI, intelligent fuzzy matching, and performance optimization. Users can now specify must-include and must-exclude cards with comprehensive card knowledge base and excellent performance.
- **Enhanced CLI with Type Safety**: Comprehensive CLI enhancement with type indicators, ideal count arguments, and theme tag name support making headless operation more user-friendly and discoverable.
- **Theme Tag Name Selection**: Intelligent theme selection by name instead of index numbers, automatically resolving to correct choices accounting for selection ordering.
- **Enhanced Fuzzy Matching**: Advanced algorithm with 300+ Commander-legal card knowledge base, popular/iconic card prioritization, and dark theme confirmation modal for optimal user experience.
- **Mobile Responsive Design**: Optimized mobile experience with bottom-floating build controls, two-column grid layout, and horizontal scrolling prevention for improved thumb navigation.
- **Enhanced Visual Validation**: List size validation UI with warning icons (⚠️ over-limit, ⚡ approaching limit) and color coding providing clear feedback on usage limits.
- **Performance Optimized**: All operations exceed performance targets with 100% pass rate - exclude filtering 92% under target, UI operations 70% under target, full validation cycle 95% under target.
- **Dual Architecture Support**: Seamless functionality across both web interface (staging system) and CLI (direct build) with proper include injection timing.

## What's new
- **Enhanced CLI Experience**
  - Type-safe help text with value indicators (PATH, NAME, INT, BOOL) and organized argument groups
  - Ideal count CLI arguments: `--ramp-count`, `--land-count`, `--creature-count`, etc. for deck composition control
  - Theme tag name support: `--primary-tag "Airbending"` instead of `--primary-choice 1` with intelligent resolution
  - Include/exclude CLI parity: `--include-cards`, `--exclude-cards` with semicolon support for comma-containing card names
  - Console summary output with detailed diagnostics and validation results for headless builds
  - Priority system: CLI > JSON Config > Environment Variables > Defaults
- **Enhanced Visual Validation**
  - List size validation UI with visual warning system using icons and color coding
  - Live validation badges showing count/limit status with clear visual indicators
  - Performance-optimized validation with all targets exceeded (100% pass rate)
  - Backward compatibility verification ensuring existing modals/flows unchanged
- **Include/Exclude Lists**
  - Must-include cards (max 10) and must-exclude cards (max 15) with strict/warn enforcement modes
  - Enhanced fuzzy matching algorithm with 300+ Commander-legal card knowledge base
  - Popular cards (184) and iconic cards (102) prioritization for improved matching accuracy
  - Dark theme confirmation modal with card preview and top 3 alternatives for <90% confidence matches
  - Color identity validation ensuring included cards match commander colors
  - File upload support (.txt) with deduplication and user feedback
  - JSON export/import preserving all include/exclude configuration via permalink system
- **Web Interface Enhancement**
  - Two-column layout with visual distinction: green for includes, red for excludes
  - Chips/tag UI allowing per-card removal with real-time textarea synchronization
  - Enhanced validation endpoint with comprehensive diagnostics and conflict detection
  - Debounced validation (500ms) for improved performance during typing
  - Enter key handling fixes preventing accidental form submission in textareas
  - Mobile responsive design with bottom-floating build controls and two-column grid layout
  - Mobile horizontal scrolling prevention and setup status optimization
  - Expanded mobile viewport breakpoint (720px → 1024px) for broader device compatibility
- **Engine Integration**
  - Include injection after land selection, before creature/spell fill ensuring proper deck composition
  - Exclude re-entry prevention blocking filtered cards from re-entering via downstream heuristics
  - Staging system architecture with custom `__inject_includes__` runner for web UI builds
  - Comprehensive logging and diagnostics for observability and debugging

## Performance Benchmarks (Complete)
- **Exclude filtering**: 4.0ms (target: ≤50ms) - 92% under target ✅
- **Fuzzy matching**: 0.1ms (target: ≤200ms) - 99.9% under target ✅
- **Include injection**: 14.8ms (target: ≤100ms) - 85% under target ✅
- **Full validation cycle**: 26.0ms (target: ≤500ms) - 95% under target ✅
- **UI operations**: 15.0ms (target: ≤50ms) - 70% under target ✅
- **Overall pass rate**: 5/5 (100%) with excellent performance margins

## Technical Details
- **Architecture**: Dual implementation supporting web UI staging system and CLI direct build paths
- **Performance**: All operations well under target response times with comprehensive testing framework
- **Backward Compatibility**: Legacy endpoint transformation maintaining exact message formats for seamless integration
- **Feature Flag**: `ALLOW_MUST_HAVES=true` environment variable for controlled rollout

## Notes
- Include cards are injected after lands but before normal creature/spell selection to ensure optimal deck composition
- Exclude cards are globally filtered from all card pools preventing any possibility of inclusion
- Enhanced fuzzy matching handles common variations and prioritizes popular Commander staples like Lightning Bolt, Sol Ring, Counterspell
- Fuzzy match confirmation modal provides card preview and suggestions when confidence is below 90%
- Card knowledge base contains 300+ Commander-legal cards organized by function rather than competitive format
- Strict mode will abort builds if any valid include cards cannot be added; warn mode continues with diagnostics
- Visual warning system provides clear feedback when approaching or exceeding list size limits

## Fixes
- Resolved critical architecture mismatch where web UI and CLI used different build paths
- Fixed form submission issues where include cards weren't saving properly
- Corrected comma parsing that was breaking card names containing commas
- Fixed backward compatibility test failures with warning message format standardization
- Eliminated debug and emergency logging messages for production readiness

## Highlights
- Mobile UI polish: collapsible left sidebar with persisted state, sticky controls that respect the header, and banner subtitle that stays inline when the menu is collapsed.
- Multi-Copy is now opt-in from the New Deck modal, and suggestions are filtered to match selected themes (e.g., Rabbit Kindred → Hare Apparent).
- New Deck modal improvements: integrated commander preview, theme selection, and optional Multi-Copy in one flow.

## What’s new
- Mobile & layout
  - Sidebar toggle button (persisted in localStorage), smooth hide/show.
  - Sticky build controls offset via CSS variables to avoid overlap in emulators and mobile.
  - Banner subtitle stays within the header and remains inline with the title when the sidebar is collapsed.
- Multi-Copy
  - Moved to Commander selection now instead of happening during building.
  - Opt-in checkbox in the New Deck modal; disabled by default.
  - Suggestions only appear when at least one theme is selected and are limited to archetypes whose matched tags intersect the themes.
  - Multi-Copy runs first when selected, with an applied marker to avoid redundant rebuilds.
- New Deck & Setup
  - Setup/Refresh prompt modal if the environment is missing or stale, with a clear path to run/refresh setup before building.
  - Centralized staged context creation and error/render helpers for a more robust Step 5 flow.

## Notes
- Multi-Copy selection is part of the interactive New Deck modal (not a JSON field); it remains off unless explicitly enabled.
- Setup helpers: `is_setup_ready()` and `is_setup_stale()` inform the modal prompt and can be tuned with `WEB_AUTO_SETUP` and `WEB_AUTO_REFRESH_DAYS`.
- Headless parity: `tag_mode` (AND/OR) remains supported in JSON/env and exported in interactive run-config JSON.

## Fixes
- Continue responsiveness and click reliability on mobile/emulators; sticky overlap eliminated.
- Multi-Copy application preserved across New Deck submit; duplicate re-application avoided with an applied marker.
- Banner subtitle alignment fixed in collapsed-menu mode (no overhang, no line-wrap into a new row).
- Docker: normalized line endings for entrypoint to avoid Windows checkout issues.