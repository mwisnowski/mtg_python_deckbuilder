# MTG Python Deckbuilder

## [Unreleased]
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
