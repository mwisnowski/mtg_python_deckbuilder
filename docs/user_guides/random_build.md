# Random Build

Generate surprise Commander decks with a single click — deterministic when you need repeatability.

---

## Overview

The Random Build tile spins up a fully randomized deck: a random commander is picked, then themes are assigned randomly from the catalog and matched to that commander's color identity and tag profile. All normal build rules (bracket, budget, owned filters, include/exclude) still apply.

Enable:
- `RANDOM_MODES=1` — expose backend random endpoints
- `RANDOM_UI=1` — show the Random Build tile on the homepage

---

## Using Random Build

1. Click the **Random Build** tile on the homepage.
2. Optionally set a theme override in the tile's inputs (primary, secondary, tertiary). Leave blank for fully random.
3. Click **Surprise me**. The builder picks a commander and fills theme slots automatically.
4. Use the **Reroll** button to generate a fresh random combination without leaving the tile.
5. Confirm to proceed through the normal build stages (or use Quick Build for one-click automation).

---

## Theme Auto-Fill

When theme slots are left blank, `RANDOM_AUTO_FILL=1` (default) fills them automatically from themes compatible with the randomly selected commander. Set `RANDOM_AUTO_FILL_SECONDARY` or `RANDOM_AUTO_FILL_TERTIARY` to override auto-fill behavior for individual slots while leaving others random.

If a specific theme combination cannot be satisfied (too few on-theme cards for the selected commander), the builder tries alternative themes up to `RANDOM_MAX_ATTEMPTS` times before surfacing an error.

---

## Reproducible Builds (Seeds)

Set `RANDOM_SEED` to any integer or string to produce the same commander + theme combination every time:

```
RANDOM_SEED=my_deck_seed_2026
```

Seeds are also shareable — include the seed in the permalink or pass it via the UI seed input to reproduce a specific random outcome.

---

## Reroll Throttle

To prevent accidental rapid-fire rerolls, a minimum interval of `RANDOM_REROLL_THROTTLE_MS` (default: `350` ms) is enforced client-side between reroll requests.

---

## Constraints

Theme and commander constraints can be passed as inline JSON or a JSON file for headless random builds:

```
RANDOM_CONSTRAINTS='{"colors": ["G","W"], "max_cmc": 4}'
RANDOM_CONSTRAINTS_PATH=/app/config/random_constraints.json
```

File path takes precedence over the inline `RANDOM_CONSTRAINTS` value.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RANDOM_MODES` | _(unset)_ | Enable random build endpoints. |
| `RANDOM_UI` | _(unset)_ | Show the Random Build tile. |
| `RANDOM_MAX_ATTEMPTS` | `5` | Retry budget when theme constraints cannot be satisfied. |
| `RANDOM_TIMEOUT_MS` | `5000` | Per-attempt timeout in milliseconds. |
| `RANDOM_REROLL_THROTTLE_MS` | `350` | Minimum ms between reroll requests (client guard). |
| `RANDOM_SEED` | _(blank)_ | Deterministic seed for reproducible builds. |
| `RANDOM_AUTO_FILL` | `1` | Auto-fill missing theme slots. |
| `RANDOM_AUTO_FILL_SECONDARY` | _(blank)_ | Override secondary slot auto-fill behavior. |
| `RANDOM_AUTO_FILL_TERTIARY` | _(blank)_ | Override tertiary slot auto-fill behavior. |
| `RANDOM_PRIMARY_THEME` | _(blank)_ | Fix the primary theme (random commander still selected). |
| `RANDOM_SECONDARY_THEME` | _(blank)_ | Fix the secondary theme. |
| `RANDOM_TERTIARY_THEME` | _(blank)_ | Fix the tertiary theme. |
| `RANDOM_STRICT_THEME_MATCH` | `0` | Require strict theme matching for commanders (1=strict). |
| `RANDOM_CONSTRAINTS` | _(blank)_ | Inline JSON constraints (e.g., color limits). |
| `RANDOM_CONSTRAINTS_PATH` | _(blank)_ | Path to a JSON constraints file (takes precedence). |
| `RANDOM_OUTPUT_JSON` | _(blank)_ | Path or directory for outputting the random build payload (headless). |
| `RANDOM_STRUCTURED_LOGS` | `0` | Emit structured JSON logs for random builds. |
| `RANDOM_TELEMETRY` | `0` | Enable lightweight timing and attempt count metrics. |

For rate limiting random endpoints see the [Docker guide](../../DOCKER.md) — Random rate limiting section.
