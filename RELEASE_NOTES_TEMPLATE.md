# MTG Python Deckbuilder ${VERSION}

## Summary
- Hardened theme catalog schema to accept optional IDs and refreshed the preview performance baseline to keep CI checks green.
- Delivered multi-theme random builds with deterministic cascade, strict match support, and polished HTMX/UI flows.
- Added opt-in telemetry counters, reroll throttling safeguards, and structured diagnostics exports.
- Expanded tooling, documentation, and QA coverage for theme governance, performance profiling, and seed history management.

## Highlights
### Multi-theme random builds
- Primary/Secondary/Tertiary inputs with deterministic fallback cascade (P+S+T → P+S → P+T → P → synergy overlap → full pool).
- Strict match toggle persists across UI, API, permalink, and export flows with restored reroll parity and diagnostics integration.
- Auto-fill helpers for secondary/tertiary slots, a quick “Clear themes” control, and consistent multi-theme metadata across sessions, permalinks, exports, and metrics.

### Telemetry & throttling
- Opt-in `RANDOM_TELEMETRY` counters capturing usage, fallback reasons, and seed history with NDJSON export endpoint.
- Reroll throttle enforcement with banner/countdown messaging plus override hooks for attempts and timeout controls.
- Expanded fast tests validating telemetry counters, throttle behavior, and reroll permutations.

### Tooling & docs
- Random theme exclusion catalog with reporting script and documentation, alongside a multi-theme performance profiler and regression guard.
- Taxonomy snapshot tooling, splash penalty analytics, and governance documentation updated for strict alias and example enforcement.
- README, CHANGELOG, and release notes refreshed to cover the random modes feature set.

### Observability & QA
- Diagnostics badge polish, recent/favorite seeds panel, seed history API, and structured logging for random builds.
- Sidecar exports include multi-theme metadata and locked commander indicators with consistent artifact sets.
- Manual QA checklist updates and broader pytest coverage for multi-theme flows, reroll behavior, performance, and telemetry.

### Maintenance & CI
- Theme catalog schema now accepts optional IDs and the preview performance warm baseline was regenerated to restore the regression gate.

## Detailed changes
### Added
- **Validation & telemetry tests**
	- `test_random_reroll_throttle.py` guarding reroll throttle rules.
	- `test_random_metrics_and_seed_history.py` verifying opt-in telemetry counters and seed history API output.
	- `test_random_multi_theme_webflows.py` covering reroll-same-commander caching and permalink round-trips for multi-theme runs.
	- `test_random_multi_theme_filtering.py` ensuring deterministic cascade across success tiers and sidecar metadata.
	- `test_random_surprise_reroll_behavior.py` protecting Surprise Me input preservation and locked-commander cache reuse.
- **Random mode tooling & docs**
	- Curated theme pool exclusions at `config/random_theme_exclusions.yml`, reporting helper `code/scripts/report_random_theme_pool.py --write-exclusions`, and companion docs in `docs/random_theme_exclusions.md`.
	- Performance guard `code/scripts/check_random_theme_perf.py` comparing profiler output (`code/scripts/profile_multi_theme_filter.py`) with `config/random_theme_perf_baseline.json` (`--update-baseline` refreshes the file).
	- Sidecar metadata now records primary/secondary/tertiary themes, resolved combos, fallback reason, and locked commander flag across summary payloads, permalinks, and exports.
- **UI & diagnostics enhancements**
	- Auto-fill helpers for secondary and tertiary slots plus a single-click “Clear themes” control.
	- Diagnostics endpoint `/status/random_theme_stats` surfacing commander/theme token coverage, attempts, timeout flags, and retries exhausted indicators.
	- Diagnostics badges polished with icons/labels alongside a recent/favorite seeds panel and strict match toggle persistence.
- **Telemetry & throttling**
	- Opt-in `RANDOM_TELEMETRY` usage counters, reroll fallback reasons, NDJSON export endpoint, and reroll throttle banner/countdown enforcement.
- **Governance & taxonomy tooling**
	- Random theme exclusion catalog sidecars, taxonomy snapshot CLI (`code/scripts/snapshot_taxonomy.py`), splash penalty analytics, and governance docs covering strict alias enforcement and example minimums.
	- Theme whitelist governance at `config/themes/theme_whitelist.yml`, curated+inferred synergy expansion, and tests such as `test_theme_whitelist_and_synergy_cap.py`.
	- Editorial scripts for normalization, example padding, governance lint, and catalog merge pipeline (`code/scripts/build_theme_catalog.py`).
- **Dependencies & infrastructure**
	- PyYAML optional dependency for governance parsing.

### Changed
- Multi-theme filtering now pre-computes lowercase token indices and reuses cached columns, reducing pandas `.apply` overhead (profiling mean ~9.3 ms / p95 ~21 ms at seed 42).
- Strict theme match toggle and auto-fill state persist across HTMX rerolls, API responses, full builds, sessions, permalinks, and exports.
- Random full builds enforce `RANDOM_BUILD_SUPPRESS_INITIAL_EXPORT=1` by default, eliminating duplicate suffixed decklists.
- Preview assembly pins curated `example_cards` and `synergy_example_cards` before heuristic sampling with diversity quotas; hover UI consolidated to one panel with resized thumbnails (110→165→230px) and keyboard-accessible DFC flip.
- List/API filtering path migrated to optimized fast filter (`filter_slugs_fast`) avoiding repeated concatenation and case folding per request.
- Splash analytics count both static and adaptive penalty reasons and share prefixes for continuity with existing dashboards.
- Cache bust hooks now clear filter/preview caches on catalog refresh or tagging completion; metrics expose `preview_last_bust_at` and warm cache stats.
- Theme normalization standardizes terms (ETB → Enter the Battlefield, Pillow Fort → Pillowfort, etc.), with synergy output capped at five entries (curated > enforced > inferred ordering).
- README, CHANGELOG, and governance docs updated to reflect new workflows, taxonomy snapshots, and telemetry controls.
- Theme catalog schema now allows optional `id` fields on entries so regenerated catalogs validate cleanly.

### Deprecated
- Price/legality snippet integration remains deferred to the future Budget Mode rollout (`logs/roadmaps/roadmap_9_budget_mode.md`).
- Legacy client-side mana and color identity parsers are deprecated in favor of server-authoritative fields included in preview/export payloads.

### Fixed
- Resolved duplicate template environment instantiation that caused inconsistent navigation globals in picker fragments.
- Ensured preview cache keys include catalog ETag to avoid stale samples after catalog reloads.
- Suppressed legacy double-export path to prevent creation of `*_1.csv` / `*_1.txt` artifacts.
- Removed ultra-rare themes (frequency ≤1) unless protected via whitelist, keeping results focused on supported experiences.
- Corrected commander eligibility rules to restrict non-creature legendary permanents and honor “can be your commander” text.
- Refreshed `logs/perf/theme_preview_warm_baseline.json` to fix preview performance CI failures stemming from malformed baseline data.

## Upgrade notes
- Enable multi-theme random builds via existing Random Mode flags; strict matching persists automatically across UI, API, permalink, and export contexts.
- Opt into telemetry by setting `RANDOM_TELEMETRY=1`; reroll throttle defaults are active but can be tuned through environment overrides.
- Refresh performance baselines with `code/scripts/check_random_theme_perf.py --update-baseline` when catalog changes materially affect timings.

## Testing
```pwsh
pytest -q code/tests/test_random_reroll_throttle.py code/tests/test_random_metrics_and_seed_history.py
pytest -q code/tests/test_random_determinism.py code/tests/test_random_build_api.py code/tests/test_seeded_builder_minimal.py code/tests/test_builder_rng_seeded_stream.py
```