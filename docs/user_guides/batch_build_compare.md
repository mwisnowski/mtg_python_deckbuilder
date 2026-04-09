# Build X and Compare

Generate multiple deck variants from the same configuration and compare them side by side.

---

## Overview

Build X and Compare lets you run 1–10 deck builds with the same commander, themes, and settings in parallel. Use it to explore variance across builds, find the most consistent card inclusions, and produce an optimized "best-of" deck via the Synergy Builder.

Enable with `ENABLE_BATCH_BUILD=1` (default: on).

---

## Starting a Batch Build

1. In the **New Deck modal**, increase the **Build count** slider from 1 to your desired number (max 10).
2. Configure the rest of the build (commander, themes, bracket, budget) as normal.
3. Click **Build**. Builds run in parallel (max 5 concurrent) with a real-time progress bar and dynamic time estimates.

---

## Results View

After all builds complete, the results page shows:

- Individual build cards, each with a summary (card count, estimated cost, theme coverage).
- **Card overlap statistics**: how many cards appeared in N of N builds, sorted by frequency.
- A **Rebuild** button to re-run with the same configuration (locks and include/exclude lists are preserved).
- A **ZIP export** button to download all builds (CSV, TXT, and summary JSON for each).

---

## Synergy Builder

The Synergy Builder analyzes all builds in the batch and produces an optimized single deck scored by three factors:

| Factor | Description |
|--------|-------------|
| Frequency | Cards that appeared in more builds score higher |
| EDHREC rank | Lower EDHREC rank (more popular) scores higher |
| Theme tags | Cards matching more of the selected themes score higher |

### How to Use
1. From the batch results view, click **Synergy Builder**.
2. Review the scored card list. The top candidates per category are pre-selected.
3. Adjust selections if needed, then click **Build Synergy Deck**.
4. The result is a standard deck that can be exported, locked, and permalinked like any other build.

---

## Compare View

Access the compare view from **Finished Decks** to diff any two completed builds:

- Card overlap count and percentage.
- Cards unique to Build A, cards unique to Build B, cards in both.
- Individual build summaries side by side.
- **Copy summary** button for plain-text export of the diff.
- **Swap A/B** to reverse the comparison direction.
- **Latest two** quick action selects the two most recent builds automatically.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_BATCH_BUILD` | `1` | Show the build count slider in the New Deck modal. Set to `0` to hide and restrict to single builds. |

---

## See Also

- [Build Wizard](build_wizard.md) — step-by-step walkthrough of a single build
- [Quick Build & Skip Controls](quick_build_skip_controls.md) — automate individual stages to speed up batch runs
- [Potential Upgrades](suggested_upgrades.md) — find new cards and swap targets for a saved deck
