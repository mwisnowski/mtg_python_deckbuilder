# Theme Catalog Advanced Guide

Additional details for developers and power users working with the theme catalog, editorial tooling, and diagnostics.

## Table of contents
- [theme_catalog.csv schema](#theme_catalogcsv-schema)
- [HTMX API endpoints](#htmx-api-endpoints)
- [Caching, diagnostics, and metrics](#caching-diagnostics-and-metrics)
- [Governance principles](#governance-principles)
- [Operational tooling](#operational-tooling)
  - [Refreshing catalogs](#refreshing-catalogs)
  - [Snapshotting taxonomy](#snapshotting-taxonomy)
  - [Adaptive splash penalty experiments](#adaptive-splash-penalty-experiments)
- [Editorial pipeline](#editorial-pipeline)
  - [Script summary](#script-summary)
  - [Example configuration](#example-configuration)
  - [Duplicate suppression controls](#duplicate-suppression-controls)
  - [Coverage metrics and KPIs](#coverage-metrics-and-kpis)
  - [Description mapping overrides](#description-mapping-overrides)
- [Validation and schema tooling](#validation-and-schema-tooling)


## theme_catalog.csv schema
`theme_catalog.csv` is the normalized artifact consumed by headless builds, supplemental themes, and diagnostics panels. The file starts with a header comment in the format `# theme_catalog version=<hash>` followed by a standard CSV header with these columns:

| Column | Description |
| --- | --- |
| `theme` | Normalized display label used across the app and JSON exports. |
| `commander_count` | Number of commanders tagged with the theme in `commander_cards.csv`. |
| `card_count` | Number of non-commander cards carrying the theme tag across primary CSVs. |
| `source_count` | Combined count (`commander_count + card_count`) to simplify weighting heuristics. |
| `last_generated_at` | ISO-8601 timestamp captured at generation time (UTC). Useful for verifying stale catalogs in diagnostics. |
| `version` | Deterministic SHA-256 prefix derived from the ordered theme list; this value flows into exports as `themeCatalogVersion` and `/status/theme_metrics`. |

Consumers should treat additional columns as experimental. If you add new fields, update this table and the supplemental theme tests that assert schema coverage.

## HTMX API endpoints
The upcoming theme picker UI is powered by two FastAPI endpoints.

### `GET /themes/api/themes`
Parameters:
- `q`: substring search across theme names and synergies.
- `archetype`: filter by `deck_archetype`.
- `bucket`: popularity bucket (Very Common, Common, Uncommon, Niche, Rare).
- `colors`: comma-separated color initials (e.g. `G,W`).
- `limit` / `offset`: pagination (limit defaults to 50, max 200).
- `diagnostics=1`: surfaces `has_fallback_description` and `editorial_quality` (requires `WEB_THEME_PICKER_DIAGNOSTICS=1`).

The response includes `count`, the filtered `items`, and `next_offset` for subsequent requests. Diagnostic mode adds extra telemetry fields.

### `GET /themes/api/theme/{id}`
Parameters:
- `uncapped=1`: (diagnostics) returns `uncapped_synergies`, combining curated, enforced, and inferred sets.
- `diagnostics=1`: exposes editorial metadata such as `editorial_quality` and `has_fallback_description`.

The payload merges curated data with editorial artifacts (`example_cards`, `example_commanders`, etc.) and respects the same diagnostic feature flag.

## Caching, diagnostics, and metrics
- Responses include an `ETag` header derived from catalog metadata so consumers can perform conditional GETs.
- `/themes/status` reports freshness and stale indicators; `/themes/refresh` (POST) triggers a background rebuild.
- When `WEB_THEME_PICKER_DIAGNOSTICS=1` is set, the app records:
  - Filter cache hits/misses and duration (`X-ThemeCatalog-Filter-Duration-ms`).
  - Preview cache metrics (`/themes/metrics` exposes counts, hit rates, TTL, and average build time).
- Skeleton loaders ship with the HTMX fragments to keep perceived latency low.

## Governance principles
To keep the catalog healthy, the project follows a lightweight governance checklist:

1. **Minimum examples** – target at least two example cards and one commander per established theme.
2. **Deterministic preview assembly** – curated examples first, then role-based samples (payoff/enabler/support/wildcard), then placeholders if needed.
3. **Splash relax policy** – four- and five-color commanders may include a single off-color enabler with a small penalty, preventing over-pruning.
4. **Popularity buckets are advisory** – they guide filters and UI hints but never directly influence scoring.
5. **Taxonomy expansion bar** – new high-level archetypes require a distinct pattern, at least eight representative cards, and no overlap with existing themes.
6. **Editorial quality tiers** – optional `editorial_quality: draft|reviewed|final` helps prioritize review passes.
7. **Deterministic sampling** – seeds derive from `theme|commander` hashes; scoring code should emit `reasons[]` to explain decisions and remain regression-test friendly.

See `docs/theme_taxonomy_rationale.md` for the underlying rationale and roadmap.

## Operational tooling

### Refreshing catalogs
- Primary builder: `python code/scripts/build_theme_catalog.py`
- Options:
  - `--limit N`: preview a subset without overwriting canonical outputs (unless `--allow-limit-write`).
  - `--output path`: write to an alternate path; suppresses YAML backfill to avoid mutating tracked files.
  - `--backfill-yaml` or `EDITORIAL_BACKFILL_YAML=1`: fill missing descriptions and popularity buckets in YAML files.
  - `--force-backfill-yaml`: overwrite existing description/popularity fields.
  - `EDITORIAL_SEED=<int>`: force a deterministic ordering when heuristics use randomness.
  - `EDITORIAL_AGGRESSIVE_FILL=1`: pad sparse themes with inferred synergies.
  - `EDITORIAL_POP_BOUNDARIES="a,b,c,d"`: tune popularity thresholds.
  - `EDITORIAL_POP_EXPORT=1`: emit `theme_popularity_metrics.json` summaries.

### Snapshotting taxonomy
`python -m code.scripts.snapshot_taxonomy` writes `logs/taxonomy_snapshots/taxonomy_<timestamp>.json` with a SHA-256 hash. Identical content is skipped unless you supply `--force`. Use snapshots before experimenting with taxonomy-aware sampling.

### Adaptive splash penalty experiments
Set `SPLASH_ADAPTIVE=1` to scale off-color enabler penalties based on commander color count. Tune with `SPLASH_ADAPTIVE_SCALE` (e.g. `1:1.0,2:1.0,3:1.0,4:0.6,5:0.35`). Analytics aggregate both static and adaptive reasons for comparison.

## Editorial pipeline

### Script summary
- `code/scripts/generate_theme_editorial_suggestions.py`
  - Proposes `example_cards`, `example_commanders`, and `synergy_commanders` using card CSVs and tagging heuristics.
  - `--augment-synergies` can pad sparse `synergies` arrays prior to suggestion.
  - `--apply` writes results; dry runs print suggestions for review.
- `code/scripts/lint_theme_editorial.py`
  - Validates annotation formats, min/max counts, and deduplication. Combine with environment toggles (`EDITORIAL_REQUIRE_DESCRIPTION`, `EDITORIAL_REQUIRE_POPULARITY`) for stricter gating.

### Example configuration
```powershell
# Dry run on the first 25 themes
python code/scripts/generate_theme_editorial_suggestions.py

# Apply across the catalog with augmentation and min example commanders set to 5
python code/scripts/generate_theme_editorial_suggestions.py --apply --augment-synergies --min-examples 5

# Lint results
python code/scripts/lint_theme_editorial.py
```

Editorial output depends on current CSV data. Expect ordering or composition changes after upstream dataset refreshes—treat full-catalog regeneration as an operational task and review diffs carefully.

### Duplicate suppression controls
`code/scripts/synergy_promote_fill.py` can rebalance example cards:

```powershell
python code/scripts/synergy_promote_fill.py --fill-example-cards --common-card-threshold 0.18 --print-dup-metrics
```

- `--common-card-threshold`: filters cards appearing in more than the specified fraction of themes (default `0.18`).
- Use metrics output to tune thresholds so staple utility cards stay in check without removing legitimate thematic cards.

### Coverage metrics and KPIs
- `EDITORIAL_INCLUDE_FALLBACK_SUMMARY=1` embeds a `description_fallback_summary` block in the generated catalog (`generic_total`, `generic_plain`, `generic_pct`, etc.).
- Regression tests use these metrics to ratchet down generic descriptions over time.
- Historical trends are appended to `config/themes/description_fallback_history.jsonl` for analysis.

### Description mapping overrides
Customize automatic descriptions without editing code:

- Add `config/themes/description_mapping.yml` with entries:
  ```yaml
  - triggers: ["sacrifice", "aristocrat"]
    description: "Leans on sacrifice loops and {SYNERGIES}."
  ```
- The first matching trigger wins (case-insensitive substring search).
- `{SYNERGIES}` expands to a short clause listing the top synergies when available, and disappears gracefully if not.
- Internal defaults remain as fallbacks when the mapping file is absent.

## Validation and schema tooling

Run validators to maintain catalog quality:

```powershell
python code/scripts/validate_theme_catalog.py
python code/scripts/validate_theme_catalog.py --rebuild-pass
python code/scripts/validate_theme_catalog.py --schema
python code/scripts/validate_theme_catalog.py --yaml-schema
python code/scripts/validate_theme_catalog.py --strict-alias
```

Per-theme YAML files (under `config/themes/catalog/`) are tracked in source control. Keys such as `metadata_info` replace the legacy `provenance`; the validator treats missing migrations as warnings until the deprecation completes.
