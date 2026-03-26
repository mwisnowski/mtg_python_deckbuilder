# Smart Land Bases

Automatically adjust land count and basic-to-dual ratios based on your commander's speed and how color-intensive your spells are.

---

## Overview

By default every deck gets exactly 35 lands regardless of CMC curve or color density. Smart Lands replaces that fixed number with a profile-driven calculation that asks three questions:

1. **How fast is the deck?** (commander CMC + pool average → speed category)
2. **How color-intensive are your spells?** (double-pip and triple-or-more-pip counts by color)
3. **How many colors does the deck run?** (1-color gets more basics; 5-color gets more fixing)

From those three signals it picks a **land count** (33–39), a **basics count**, and an **ETB tapped tolerance**, then passes those targets to every existing land-selection step — no other logic changes.

Enable Smart Land Bases per-build via the **Smart Land Bases** checkbox in the Preferences section of the New Deck modal (checked by default). Disable it for a single build by unchecking the box.

---

## Speed Categories & Land Counts

Smart Lands applies a **speed offset** to your configured ideal land count rather than overwriting it with a fixed number.

| Speed | Effective CMC | Offset from your ideal | Example (ideal = 40) |
|-------|--------------|------------------------|----------------------|
| Fast  | < 3.0        | −2                     | 38 |
| Mid   | 3.0 – 4.0    | ±0                     | 40 |
| Slow  | > 4.0        | +2 to +4 (scales with color count) | 42–44 |

**Effective CMC** is a weighted blend: `commander_cmc × 0.6 + pool_avg_cmc × 0.4`. This means a 1-CMC commander leading a mid-range pool will show an effective CMC around 1.9, which still lands firmly in the "fast" band.

---

## Land Profiles

### Basics-Heavy
Recommended for 1–2 color decks and decks with low pip density (< 5 double-pip cards, 0 triple-or-more-pip cards). Also forced automatically for budget builds with < $50 allocated to lands in 3+ color decks.

- **Basics**: ~60% of land target
- **ETB tapped tolerance**: reduced by 4 percentage points vs. bracket default
- **Good for**: mono-color aggro, 2-color tempo, budget lists

### Balanced (Mid)
The default for 2–3 color decks with moderate pip density. Keeps existing bracket-level ETB tapped thresholds unchanged.

- **Basics**: current default ratio
- **ETB tapped tolerance**: bracket default (unchanged)
- **Good for**: most 2–3 color Commander decks

### Fixing-Heavy
Triggered by 3+ colors with high pip density (≥ 15 double-pip cards or ≥ 3 triple-or-more-pip cards), or automatically for 5-color decks.

- **Basics**: `color_count × 2` (minimal, roughly 6–10)
- **ETB tapped tolerance**: raised by 4 percentage points vs. bracket default (slow decks can afford tapped sources)
- **Good for**: 4–5 color goodstuff, high-pip Grixis/Abzan builds, decks relying on colored activations

---

## Pip Density

Pips are the colored mana symbols in a card's mana cost. Smart Lands counts them per color across your full card pool:

- **Single-pip**: one symbol of a color (e.g., `{1}{W}`)
- **Double-pip**: two symbols of the same color on one card (e.g., `{W}{W}`)
- **Triple-or-more-pip**: three or more symbols of the same color on one card (e.g., `{B}{B}{B}` or `{5}{R}{R}{R}`)

Cards with pips outside your commander's color identity are ignored (they would never be selected). Lands are excluded from pip counting.

When pip density pushes the profile away from the color-count default, the build summary explains this in the **Smart Lands** notice.

---

## Build Summary Notice

After each build, the **Land Summary** section shows a **Smart Lands** banner when the analysis ran:

> **Smart Lands** adjusted your land targets: **35 lands** / **8 basics** — **Fixing-heavy (extensive duals/fetches)** profile, Mid-paced deck.

The **Why:** section explains in plain English what drove the decision — single color, 5-color identity, heavy pip density, light pip density, or moderate pip density based on color count. Double-pip and triple-or-more-pip counts are only shown when pip density was the deciding factor.

---

## Overrides

| Variable | Values | Effect |
|----------|--------|--------|
| `LAND_PROFILE` | `basics`, `mid`, `fixing` | Force a specific profile, skip auto-detection. |
| `LAND_COUNT` | integer (e.g. `36`) | Force total land count, skip curve calculation. |

Env overrides are applied **after** the analysis, so they always win over the calculated values. For headless/CLI builds these are the primary way to control land behaviour.

---

## Budget Interaction

When [Budget Mode](budget_mode.md) is active and the land budget is under $50 with 3+ colors, the profile is automatically overridden to `basics-heavy` and a warning is logged. This prevents the tool from recommending expensive fetch/shock lands you cannot afford. Override with `LAND_PROFILE=mid` if needed.

---

## Slot Earmarking

After Smart Lands sets the land target, it proportionally scales down non-land ideal counts (creatures, ramp, removal, etc.) so they fit within the remaining 99 − `land_target` deck slots. This prevents spell phases from consuming land slots before lands get a chance to fill them.

For example, with a 43-land target the non-land budget is 56 slots. If the combined non-land ideals sum to 63, each category is scaled down proportionally (e.g. 25 creatures → 22, 10 removal → 9, etc.).

A **backfill** step at the end of all land phases adds basics from the color identity if any land phase still falls short — so the deck always reaches the configured target.

---

## Notes

- Smart Lands only adjusts **counts** — the existing land-selection steps (duals, fetches, triples, ETB optimization, etc.) run unchanged on the updated targets.
- Colorless commanders fall back to `mid` profile with 35 lands (no color identity to analyze).
- If the analysis fails for any reason, it silently falls back to `mid` profile and fixed 35-land target — builds are never blocked.
