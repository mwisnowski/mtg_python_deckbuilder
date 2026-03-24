# Theme Browser & Quality System

Explore, filter, and evaluate the theme catalog before building.

---

## Overview

The Theme Browser at `/themes` displays all available themes with synergy data, editorial quality scores, and pool size information. Use it to discover themes, understand what cards a theme covers, and filter by quality before selecting themes for a build.

Enable the theme selector and browser with `ENABLE_THEMES=1` (default: on).

---

## Badge System

Each theme card in the browser displays up to three badge types:

### Quality Badge (`SHOW_THEME_QUALITY_BADGES=1`)
Editorial quality score based on synergy depth, card count, and thematic coherence. Assigned during catalog curation.

| Badge | Meaning |
|-------|---------|
| Excellent | Strong synergy, large pool, well-curated |
| Good | Solid theme with reasonable card support |
| Fair | Usable but limited pool or marginal synergy |
| Poor | Sparse pool or weak theme coherence |

### Pool Size Badge (`SHOW_THEME_POOL_BADGES=1`)
Number of on-theme cards available in the catalog.

| Badge | Approximate range |
|-------|------------------|
| Vast | 200+ cards |
| Large | 100–199 cards |
| Moderate | 50–99 cards |
| Small | 20–49 cards |
| Tiny | Under 20 cards |

Pool size is affected by `THEME_MIN_CARDS`: themes with fewer cards than this threshold are stripped from the catalog entirely during setup/tagging (default: `5`).

### Popularity Badge (`SHOW_THEME_POPULARITY_BADGES=1`)
How frequently the theme appears across builds in the system. Higher popularity themes have more real-world data behind their synergy rankings.

---

## Filtering

Filter chips appear above the theme grid when `SHOW_THEME_FILTERS=1` (default: on). You can combine filters:

- Filter by Quality: Excellent, Good, Fair, Poor (multi-select)
- Filter by Pool Size: Vast, Large, Moderate, Small, Tiny (multi-select)
- Filter by Popularity

Multiple active filters use AND logic — a theme must match all active badge filters to appear.

---

## Theme Detail Pages

Click any theme card to open its detail page. Each page shows:

- The full on-theme card list with EDHREC rank, CMC, and synergy score
- Badge explanations for that theme
- Related themes (by tag overlap)

---

## Quality Dashboard

`/diagnostics/quality` (requires `SHOW_DIAGNOSTICS=1`) provides a catalog-level health overview:

- Distribution of themes by quality tier
- Average pool size per quality tier
- Themes flagged for editorial review (e.g., very low card count, no quality score)

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_THEMES` | `1` | Keep the theme browser and theme selector active. |
| `SHOW_THEME_QUALITY_BADGES` | `1` | Show quality badges in the theme catalog. |
| `SHOW_THEME_POOL_BADGES` | `1` | Show pool size badges in the theme catalog. |
| `SHOW_THEME_POPULARITY_BADGES` | `1` | Show popularity badges in the theme catalog. |
| `SHOW_THEME_FILTERS` | `1` | Show filter chips in the theme catalog. |
| `THEME_MIN_CARDS` | `5` | Minimum cards required for a theme to appear in the catalog. |
| `WEB_THEME_PICKER_DIAGNOSTICS` | `1` | Unlock `/themes/metrics`, uncapped synergies, and extra metadata. |
| `THEME_MATCH_MODE` | `permissive` | Fuzzy match mode for supplemental themes: `permissive` continues on unresolved themes, `strict` stops the build. |

---

## Rebuilding the Theme Catalog

If you update card data or theme YAML files, rebuild the merged catalog:

```powershell
# Docker Compose:
docker compose run --rm --entrypoint bash web -lc "python -m code.scripts.build_theme_catalog"

# Local:
python -m code.scripts.build_theme_catalog
```
