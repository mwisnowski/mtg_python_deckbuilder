# Random Mode Theme Exclusions

The curated random theme pool keeps auto-fill suggestions focused on themes that lead to actionable Commander builds. This document summarizes the heuristics and manual exclusions that shape the pool and explains how to discover every theme when you want to override the curated list.

## Heuristics applied automatically

We remove a theme token from the curated pool when any of the following conditions apply:

1. **Insufficient examples** – fewer than five unique commanders in the catalog advertise the token.
2. **Kindred and species-specific labels** – anything matching keywords such as `kindred`, `tribal`, `clan`, or endings like `" tribe"` is treated as commander-specific and filtered out.
3. **Global catch-alls** – broad phrases (for example `goodstuff`, `legendary matter`, `historic matter`) offer little guidance for theme selection, so they are excluded.
4. **Over-represented themes** – if 30% or more of the commander catalog advertises a token, it is removed from the surprise pool to keep suggestions varied.

These rules are codified in `code/deck_builder/random_entrypoint.py` and surfaced via the diagnostics panel and the reporting script.

## Manual exclusions

Some descriptors are technically valid tokens but still degrade the surprise experience. They live in `config/random_theme_exclusions.yml` so we can document why they are hidden and keep the list reviewable.

| Category | Why it is excluded | Tokens |
| --- | --- | --- |
| `ubiquitous_baseline` | Baseline game actions every deck performs; surfacing them would be redundant. | `card advantage`, `card draw`, `removal`, `interaction` |
| `degenerate_catchall` | Generic "good stuff" style descriptors that do not communicate a coherent plan. | `value`, `good stuff`, `goodstuff`, `good-stuff`, `midrange value` |
| `non_theme_qualifiers` | Power-level or budget qualifiers; these belong in settings, not theme suggestions. | `budget`, `competitive`, `cedh`, `high power` |

Themes removed here still resolve just fine when you type them manually into any theme field or when you import them from permalinks, sessions, or the CLI.

### Keeping the list discoverable

The reporting script can export the manual list alongside the curated pool:

```powershell
# Markdown summary with exclusions
python code/scripts/report_random_theme_pool.py --format markdown

# Structured exclusions for tooling
python code/scripts/report_random_theme_pool.py --write-exclusions logs/random_theme_exclusions.json
```

Both commands refresh the commander catalog on demand and mirror the exact heuristics used by the web UI and API.

## Surfacing the information in the app

When diagnostics are enabled (`SHOW_DIAGNOSTICS=1`), the `/diagnostics` panel shows:

- Total curated pool size and coverage.
- Counts per exclusion reason (including manual categories).
- Sample tokens and the manual categories that removed them.
- Tag index telemetry (build count, cache hit rate) for performance monitoring.

This makes it easy to audit the pool after catalog or heuristic changes.

## Updating the manual list

1. Edit `config/random_theme_exclusions.yml` and add or adjust entries (keep tokens lowercase; normalization happens automatically).
2. Run `python code/scripts/report_random_theme_pool.py --format markdown --refresh` to verify the pool summary.
3. Commit the YAML update together with the regenerated documentation when you are satisfied.

The curated pool will pick up the change automatically thanks to the file timestamp watcher in `random_entrypoint.py`.
