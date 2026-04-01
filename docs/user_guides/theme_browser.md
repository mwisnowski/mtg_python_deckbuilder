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
Automatically computed score based on four factors, normalized to 0–100:

| Factor | Max points | What it measures |
|--------|-----------|------------------|
| Card synergy quality | 30 | EDHREC rank and synergy data richness for the theme's example cards |
| Uniqueness ratio | 40 | Fraction of theme cards that appear in fewer than 25% of all themes |
| Description quality | 20 | Manual editorial description (10 pts), auto-generated rule (5 pts), generic (0 pts) |
| Curation bonus | 10 | Theme has hand-curated synergy data |

| Badge | Score threshold | Meaning |
|-------|----------------|---------|
| Excellent | ≥ 75 / 100 | Strong synergy, distinctive card pool, well-curated |
| Good | 60–74 | Solid theme with reasonable card support |
| Fair | 40–59 | Usable but limited pool or marginal synergy |
| Poor | < 40 | Sparse pool or weak theme coherence |

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

---

## See Also

- [Build Wizard](build_wizard.md) — how themes are selected and used during the build workflow
- [Random Build](random_build.md) — use themes as constraints for randomized commander selection
- [Partner Mechanics](partner_mechanics.md) — finding themes that work across both commanders' color identity
