# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
- The saved JSON build-config workflow has been removed: the web `/configs` page, the full CRUD `GET/POST/DELETE /api/v1/configs` REST API, and the CLI/Docker `--config`/`DECK_CONFIG` mechanism (including the auto-export of a `<name>.json` run config after every build). Scripted/headless builds are unaffected: use `headless_runner.py`'s existing per-field CLI flags or `DECK_*` environment variables instead, e.g. `python code/headless_runner.py --commander "..." --primary-choice 1 --add-lands true` in place of `--config config/deck.json`. Existing `.json` config files on disk are left untouched, just no longer discoverable by the app.

### Security
_No unreleased changes yet_

