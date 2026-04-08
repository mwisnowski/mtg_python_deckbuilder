# Potential Upgrades

The **Potential Upgrades** page surfaces card suggestions for any saved deck, organized into two pools and sorted by how well each card fits your deck's themes and roles.

---

## Accessing the Page

From any finished deck's view page, click **Potential Upgrades**. The button only appears for saved decks (not mid-build previews).

---

## Two Upgrade Sections

### New Cards
Cards that are first printings from recent sets — either the last three expansion release windows or the last six months, whichever covers more ground. Reprints are excluded so you only see genuinely new cards.

The page header shows which sets are included (e.g., "New cards from: Final Fantasy Commander, Lorwyn Eclipsed, TMNT (Oct 2025 – Mar 2026)").

### General Upgrades
Cards from the full legal card pool that fit your deck's color identity and have meaningful role or theme overlap with your current build. Useful for finding upgrades from any era, not just recent sets.

---

## How Cards Are Ranked

Each suggested card shows a **synergy score** — a teal pill on the card tile:

- **New Cards pool**: `score = 2 × matched theme/role tags + 1 ÷ log₁₀(EDHREC rank + 10)`  
  More theme matches and a lower EDHREC rank both raise the score.

- **General Upgrades pool**: `score = 2 × theme tag matches + 1.5 × under-represented role fills + 1 ÷ log₁₀(EDHREC rank + 10)`  
  Cards that cover gaps in your current role spread score highest.

Cards are sorted by this score, highest first, before any deduplication.

> The score formula explainer is also available on the page itself — click **"How are the scores calculated?"** to expand it.

---

## Swap Targets

Each suggested card shows a horizontal strip of **swap target** thumbnails — cards currently in your deck that the algorithm considers reasonable candidates to cut in exchange for the suggestion.

Each swap target shows:
- Card image (hoverable for the full hover panel)
- Card name
- An **amber replaceability score** (1–10) — how swappable that deck card is

### Replaceability Score (Amber)

`score = role overlap weight + CMC savings bonus + quality adjustment`

Normalized to a 1–10 scale. A higher score means the deck card shares more roles with the suggestion and/or has a high mana cost relative to what would replace it — making it a stronger cut candidate.

**The teal synergy score and amber replaceability score are on different scales and measure different things.** A high replaceability score on a swap target does not mean that card is bad — only that the algorithm sees it as a reasonable swap-out relative to the specific suggestion.

---

## Hover Panel

Hovering any card (suggested card or swap target) opens the standard card detail panel showing:

- Card image
- Mana cost, rarity, price
- Role tags and theme tags
- For suggested cards: matched theme tags highlighted as chips; swap reason listed as a bullet
- For swap targets: the reason why the algorithm flagged this card (e.g., "Shared Board Wipes, Card Draw roles; high CMC (5)")

---

## Important Caveats

These are **algorithmic suggestions**, not prescriptions. The scoring weighs role overlap, theme tag coverage, CMC efficiency, and EDHREC popularity — but it cannot account for:

- Specific combo lines or synergy chains not captured in role tags
- Political utility or "rattlesnake" effects
- Personal card preferences (pet cards)
- Budget constraints or regional card availability
- Power-level calibration for your specific playgroup
- Cards that serve multiple subtle roles beyond their primary tag

A high replaceability score on a target card means the algorithm thinks it is a reasonable swap candidate — not that you must cut it. Always apply your own judgment before making changes to a deck you care about.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_UPGRADE_SUGGESTIONS` | `1` | Set to `0` to hide the feature entirely |
| `UPGRADE_PAGE_SIZE` | `16` | Cards shown per page (5–50) |
| `UPGRADE_WINDOW_MONTHS` | `6` | Rolling window size in months for the "New Cards" pool |

---

## See Also

- [Build Wizard](build_wizard.md) — building a new deck from scratch
- [Budget Mode](budget_mode.md) — setting per-card and total budget limits
- [Locks, Replace & Permalinks](locks_replace_permalinks.md) — locking specific cards so they are never suggested as swap targets
- [Theme Browser](theme_browser.md) — exploring available themes and their synergy cards
