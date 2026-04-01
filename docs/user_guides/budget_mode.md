# Budget Mode

Build decks within a price target using per-card cost filtering and a soft-review summary.

---

## Overview

Budget Mode filters the card selection pool to cards at or near a per-card price ceiling you set. Cards that exceed the ceiling are excluded from the randomized pool, but the final deck is never hard-rejected — over-budget cards that slip through are flagged for your review in the build summary.

Enable with `ENABLE_BUDGET_MODE=1` (default: on).

---

## Setting a Budget

In the **New Deck modal**, enter a per-card price ceiling in the Budget field. This ceiling is a UI input — it is not set via an environment variable.

- Leave the field blank or set it to `0` to disable per-card filtering for that build.
- The ceiling applies to all non-land cards drawn from the selection pool.

---

## How Filtering Works

1. Price data is loaded from a local cache sourced from Scryfall bulk data.
2. Cards whose price exceeds `ceiling * (1 + BUDGET_POOL_TOLERANCE)` are excluded from the pool before selection begins.
3. `BUDGET_POOL_TOLERANCE` (default `0.15`) adds a 15% headroom above the ceiling. This smooths results for borderline-priced cards and avoids over-aggressive filtering.
4. Selection then runs normally on the filtered pool — locked cards and Must Include cards are inserted before filtering.

**Example:** Ceiling = $2.00, tolerance = 0.15 → cards priced above $2.30 are excluded from the pool.

---

## Build Summary

After a build completes, the budget summary panel shows:

- Total estimated deck cost
- Per-category cost breakdown (creatures, spells, lands, etc.)
- Cards flagged as over-budget (above the ceiling, not the tolerance threshold)
- Price badges on individual card rows: green (under ceiling), yellow (at ceiling), red (over ceiling)
- A stale price indicator (clock icon) when a cached price is older than `PRICE_STALE_WARNING_HOURS`

The summary JSON export (`deck_files/*.summary.json`) includes the price breakdown per category.

---

## Price Data & Caching

Prices are sourced from the Scryfall bulk data API and cached locally.

| Behavior | Setting |
|----------|---------|
| Background per-card refresh (7-day TTL) | `PRICE_LAZY_REFRESH=1` (default) |
| Full cache rebuild daily at 01:00 UTC | `PRICE_AUTO_REFRESH=1` |
| Stale indicator threshold | `PRICE_STALE_WARNING_HOURS=24` (set to `0` to disable) |

If a card has no price data, it is treated as free (fail-open) and selected normally. No card is hard-rejected due to a missing price.

To manually check cache status: `/api/price/stats` (when `SHOW_DIAGNOSTICS=1`).

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_BUDGET_MODE` | `1` | Enable budget controls and price display. Set to `0` to hide all budget UI. |
| `BUDGET_POOL_TOLERANCE` | `0.15` | Fractional overhead above the per-card ceiling before exclusion. |
| `PRICE_AUTO_REFRESH` | `0` | Rebuild the full price cache daily at 01:00 UTC. |
| `PRICE_LAZY_REFRESH` | `1` | Refresh stale per-card prices in the background. |
| `PRICE_STALE_WARNING_HOURS` | `24` | Hours before a cached price shows a stale indicator. `0` = disable. |

---

## FAQ

**Why is a card over my ceiling still in the deck?**
The pool tolerance allows cards slightly above the ceiling into the selection pool to avoid overly thin pools. Cards that land in your deck despite being over ceiling are flagged in red in the budget summary. You can swap them using the Replace feature in Step 5.

**Prices look stale — how do I refresh?**
Set `PRICE_LAZY_REFRESH=1` (default) to refresh automatically in the background. For an immediate full refresh, set `PRICE_AUTO_REFRESH=1` and restart the container, or trigger a manual refresh via the price stats API.

**Does budget mode affect the commander?**
No. The commander is never filtered by price — only cards drawn from the selection pool are subject to the ceiling.

**Can I use budget mode with Must Include cards?**
Yes. Must Include cards bypass the pool filter and are always added. They may appear as over-budget in the summary if they exceed the ceiling.

**Why is the price shown different from what I see on a store site?**
Prices are sourced from Scryfall bulk data and cached locally. They reflect a recent market median, not real-time retail or buylist prices. Check the stale indicator (clock icon) in the summary for cache age.

**Can I set separate ceilings for different card types?**
Not directly — the per-card ceiling applies to the full pool. To approximate type-specific limits, use Must Exclude to block expensive cards in a category before the build runs.

---

## See Also

- [Build Wizard](build_wizard.md) — budget step in context of the full build workflow
- [Locks, Replace & Permalinks](locks_replace_permalinks.md) — use Replace to swap out over-budget cards after building
- [Land Bases](land_bases.md) — land counts and profile choices that affect overall deck cost
