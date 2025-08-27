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
- Web UI: FastAPI + Jinja front-end for the builder; staged build view with per-stage reasons
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
 - Tooltip Copy action on chart tooltips (Pips/Sources) for quick sharing of per-color card lists

### Changed
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
 - List view highlight polished to wrap only the card name (no overrun of the row)
 - Total sources calculation updated to include 'C' properly

### Fixed
- Docker Hub workflow no longer publishes a `major.minor` tag (e.g., `1.1`); only full semver (e.g., `1.2.3`) and `latest`
 - Owned page internal server error resolved via hardened template context and centralized owned context builder
 - Web container crash resolved by removing invalid union type annotation in favicon route; route now returns a single Response type
 - Source highlighting consistency: charts now correctly cross-highlight corresponding cards in both list and thumbnail views
 - Basics handling: ensured basic lands and Wastes are recognized as sources; added fallback oracle text for basics in CSV export
 - Fetch lands are no longer miscounted as mana sources

---

For prior releases, see the GitHub Releases page.
