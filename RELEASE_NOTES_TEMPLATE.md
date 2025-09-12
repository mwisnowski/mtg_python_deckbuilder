# MTG Python Deckbuilder ${VERSION}

### Added
- CI improvements to increase stability and reproducibility of builds/tests.
- Expanded test coverage for validation and web flows.

### Changed
- Tests refactored to use pytest assertions and streamlined fixtures/utilities to reduce noise and deprecations.
- HTTP-dependent tests skip gracefully when the local web server is unavailable.

### Fixed
- Reduced deprecation warnings and incidental test failures; improved consistency across runs.

---