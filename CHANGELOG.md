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
- (placeholder)

### Changed
- (placeholder)

### Fixed
- (placeholder)

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
