# MTG Python Deckbuilder

## [Unreleased]
### Added
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
_No unreleased changes yet_

### Removed
_No unreleased changes yet_
