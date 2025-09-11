# MTG Python Deckbuilder ${VERSION}

## Highlights
- Dynamic misc utility land variety: EDHREC keep percentage now randomly rolls between configurable min/max each build (defaults 75%–100%).
- Land alternatives overhaul: land-aware suggestions (basics→basics, non-basics→non-basics) plus randomized 12-card window (random slice of top 60–100) for per-request variety.
- Cleaner mono-color utility land pools: rainbow/any-color filler and fetch lands excluded after their dedicated phases; explicit allow-list preserves strategic exceptions.
- Theme-aware misc land weighting with configurable multipliers (base + per-extra + cap) via new environment overrides.
- Production-friendly diagnostics: misc land debug CSVs gated behind `MISC_LAND_DEBUG` or diagnostics flag (off by default).
- UI polish & stability: eliminated Step 5 bottom-of-grid scroll flicker (overscroll containment + skip virtualization for small grids <80 items).
- Documentation & compose updates: all new tuning variables surfaced in README, compose files, and sample env.

## Added
- Land alternatives: land-only mode with parity filtering (mono-color exclusions, rainbow text heuristics, fetch exclusion, World Tree legality check).
- Randomized land alternative selection: 12 suggestions from a random window size inside the top 60–100 ranked candidates (uncached for variety).
- Dynamic EDHREC keep range: `MISC_LAND_EDHREC_KEEP_PERCENT_MIN/MAX` (falls back to legacy single `MISC_LAND_EDHREC_KEEP_PERCENT` if min/max unset).
- Misc land theme weighting overrides: `MISC_LAND_THEME_MATCH_BASE`, `MISC_LAND_THEME_MATCH_PER_EXTRA`, `MISC_LAND_THEME_MATCH_CAP`.
- Debug gating: `MISC_LAND_DEBUG=1` to emit misc land candidate/post-filter CSVs (otherwise only when diagnostics enabled).

## Changed
- Fetch lands fully excluded from misc land (utility) step; they are handled earlier and no longer appear as filler.
- Mono-color pass prunes broad rainbow/any-color lands (except allow-list) using expanded text phrase heuristics.
- Alternatives endpoint skips caching for land role to preserve per-request randomness; non-land roles retain cache.
- Compose / README / .env example updated with new land tuning variables.
- Virtualization system now skips small grids (<80 items) to reduce overhead and prevent layout-induced scroll snapping.

## Fixed
- Step 5 scroll flicker / bounce when reaching bottom of short grids (overscroll containment + virtualization threshold).
- Random land alternatives previously surfacing excluded or fetch lands—now aligned with misc step filters.

## Environment Variables (new / updated)
| Variable | Purpose | Default |
|----------|---------|---------|
| MISC_LAND_EDHREC_KEEP_PERCENT_MIN | Lower bound for dynamic EDHREC keep % (0–1) | 0.75 |
| MISC_LAND_EDHREC_KEEP_PERCENT_MAX | Upper bound for dynamic EDHREC keep % (0–1) | 1.0 |
| MISC_LAND_EDHREC_KEEP_PERCENT | Legacy single fixed keep % (fallback) | 0.80 |
| MISC_LAND_DEBUG | Emit misc land debug CSVs | Off |
| MISC_LAND_THEME_MATCH_BASE | Base multiplier for first theme match | 1.4 |
| MISC_LAND_THEME_MATCH_PER_EXTRA | Increment per additional matching theme | 0.15 |
| MISC_LAND_THEME_MATCH_CAP | Cap on total theme multiplier | 2.0 |

## Upgrade Notes
1. No migration steps required; defaults mirror prior behavior but introduce controlled randomness for utility land variety.
2. To restore pre-random behavior, set MIN=MAX=1.0 (or rely on legacy `MISC_LAND_EDHREC_KEEP_PERCENT`).
3. If deterministic land alternatives are needed for testing, consider temporarily disabling randomness (future flag can be added).
4. To analyze utility land selection, enable diagnostics or set `MISC_LAND_DEBUG=1` before running a build; CSVs appear under `logs/` (or diagnostic export path) only when enabled.

## Testing & Quality
- Existing fast test suite passes (include/exclude + summary utilities). Additional targeted tests for randomized window selection can be added in a follow-up if deterministic mode is introduced.
- Manual validation: multiple builds confirm varied utility land pools and land alternatives without fetch/rainbow leakage.

## Future Follow-ups (Optional)
- Deterministic toggle for land alternative randomization (e.g., `LAND_ALTS_DETERMINISTIC=1`).
- Unit tests focusing on edge-case mono-color filtering and theme weighting bounds.
- Potential adaptive virtualization row-height measurement per column for further smoothness (currently fixed estimate works acceptably).
