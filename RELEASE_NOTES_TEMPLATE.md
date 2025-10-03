# MTG Python Deckbuilder ${VERSION}

## Summary
- Theme catalog groundwork for supplemental/custom themes now ships with a generator script and focused test coverage.
- Web builder gains an Additional Themes section with fuzzy suggestions and strict/permissive toggles for user-supplied tags.
	- Compose manifests and docs include new environment toggles for random reroll throttling, telemetry/logging, homepage commander tile, and optional random rate limiting.

## Added
- Script `python -m code.scripts.generate_theme_catalog` emits a normalized `theme_catalog.csv` with commander/card counts, deterministic ordering, and a reproducible version hash for supplemental theme inputs.
- Unit tests cover catalog generation on fixture CSVs and verify normalization removes duplicate theme variants.
- Loader `load_theme_catalog()` memoizes CSV parsing, validates required columns, and exposes typed entries plus version metadata for runtime integrations.
- Unit tests exercise loader success, empty-file fallback, and malformed-column scenarios.
- Fuzzy theme matcher builds a trigram-backed index with Levenshtein + Sequence similarity scoring, threshold constants, and resolution utilities for supplemental theme inputs.
- Unit tests validate normalization, typo recovery, suggestion quality, and enforce a basic performance ceiling for 400+ theme catalogs.
- Headless configs accept `additional_themes` + `theme_match_mode` with catalog-backed fuzzy resolution, strict/permissive enforcement, and persistence into exported run configs and diagnostics.
- Added targeted tests for additional theme parsing, strict failure handling, and permissive warning coverage.
- Web New Deck modal renders an “Additional Themes” HTMX partial supporting add/remove, suggestion adoption, mode switching, limit enforcement, and accessible live messaging (gated by `ENABLE_CUSTOM_THEMES`).
- Supplemental theme telemetry now records commander/user/merged theme payloads, exposes `/status/theme_metrics` for diagnostics, and surfaces user theme weighting via structured `user_theme_applied` logs and the diagnostics dashboard panel.
	- Environment variables surfaced in compose, `.env.example`, and docs:
		- `SHOW_COMMANDERS` (default `1`): show the Commanders browser tile.
		- `RANDOM_REROLL_THROTTLE_MS` (default `350`): client guard to prevent rapid rerolls.
		- `RANDOM_STRUCTURED_LOGS` (default `0`): emit structured JSON logs for random builds.
		- `RANDOM_TELEMETRY` (default `0`): enable lightweight timing/attempt counters for diagnostics.
		- `RATE_LIMIT_ENABLED` (default `0`), `RATE_LIMIT_WINDOW_S` (`10`), `RATE_LIMIT_RANDOM` (`10`), `RATE_LIMIT_BUILD` (`10`), `RATE_LIMIT_SUGGEST` (`30`): optional server-side rate limiting for random endpoints.

## Changed
- Run-config exports now surface `userThemes` and `themeCatalogVersion` metadata while retaining legacy fields; headless imports accept both aliases without changing hash-equivalent payloads when no user themes are present.

## Fixed
- Additional Themes now falls back to `theme_list.json` when `theme_catalog.csv` is absent, restoring resolution, removal, and build application for user-supplied themes across web and headless flows.
