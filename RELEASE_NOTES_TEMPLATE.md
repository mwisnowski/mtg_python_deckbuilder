# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Theme Editorial Quality & Standards**: Complete editorial system for theme catalog curation
  - **Editorial Metadata Fields**: `description_source` (tracks provenance: official/inferred/custom) and `popularity_pinned` (manual tier override)
  - **Heuristics Externalization**: Theme classification rules moved to `config/themes/editorial_heuristics.yml` for maintainability
  - **Enhanced Quality Scoring**: Four-tier system (Excellent/Good/Fair/Poor) with 0.0-1.0 numerical scores based on uniqueness, duplication, description quality, and metadata completeness
  - **CLI Linter**: `validate_theme_catalog.py --lint` flag with configurable thresholds for duplication and quality warnings, provides actionable improvement suggestions
  - **Editorial Documentation**: Comprehensive guide at `docs/theme_editorial_guide.md` covering quality scoring, best practices, linter usage, and workflow examples

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_
