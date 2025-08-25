# Changelog

All notable changes to this project will be documented in this file.

This format follows Keep a Changelog principles and aims for Semantic Versioning.

## How we version
- Semantic Versioning: MAJOR.MINOR.PATCH (e.g., v1.2.3). Pre-releases use -alpha/-beta/-rc.
- Tags are created as `vX.Y.Z` on the default branch; releases and Docker images use that exact version and `latest`.
- Change entries prefer the Keep a Changelog types: Added, Changed, Fixed, Removed, Deprecated, Security.
- Link PRs/issues inline when helpful, e.g., (#123) or [#123]. Reference-style links at the bottom are encouraged for readability.

## [Unreleased]

### Added
- Owned-cards workflow:
  - Prompt (only if lists exist) to "Use only owned cards?"
  - Support multiple file selection; parse `.txt` (1 per line) and `.csv` (any `name` column)
  - Owned-only mode filters the pool to owned names; commander exempt
  - Recommendations export when owned-only deck is incomplete (~1.5× missing) to `deck_files/[stem]_recommendations.csv` and `.txt`
- CSV export includes an `Owned` column when not using owned-only
- Windows EXE build via PyInstaller is produced on tag and attached to GitHub Releases

### Changed
- Rename folder from `card_library` to `owned_cards` (env override: `OWNED_CARDS_DIR`; back-compat respected)
- Docker assets and docs updated:
  - New volume mounts: `./owned_cards:/app/owned_cards` and `./config:/app/config`
  - Compose and helper scripts updated accordingly
- Release notes source is `RELEASE_NOTES_TEMPLATE.md`; `RELEASE_NOTES.md` ignored

### Fixed
- Docker Hub workflow no longer publishes a `major.minor` tag (e.g., `1.1`); only full semver (e.g., `1.2.3`) and `latest`

---

For prior releases, see the GitHub Releases page.
