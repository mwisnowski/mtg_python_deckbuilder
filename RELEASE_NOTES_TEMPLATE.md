# MTG Python Deckbuilder

## [Unreleased]
### Added
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
  - Added parquet manipulation functions to `theme_stripper.py`: backup, filter, update, and strip operations
  - Handles multiple themeTags formats: numpy arrays, lists, and comma/pipe-separated strings
  - Stripped 97 theme tag occurrences from 30,674 cards in `all_cards.parquet`
  - Updated `stripped_themes.yml` log with 520 themes stripped from parquet source
  - **Automatic integration**: Theme stripping now runs automatically in `run_tagging()` after tagging completes (when `THEME_MIN_CARDS` > 1, default: 5)
  - Integrated into web UI setup, CLI tagging, and CI/CD workflows (build-similarity-cache)

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_
