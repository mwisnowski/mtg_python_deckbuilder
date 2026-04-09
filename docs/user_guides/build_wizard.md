# Build a Deck - Step-by-Step Guide

Walk through the deck building wizard to create a Commander deck.

---

## Overview

The deck builder guides you through a multi-step modal wizard that helps you configure and build a complete Commander deck. Each step lets you customize your deck's strategy, budget, and power level before generating the final list.

Access the builder at `/build` or click **Build** in the sidebar.

---

## Step 1: Choose a Commander

Select your commander from the search field in the modal. Type the commander's name to see matches.

**Partner Commanders**: If your commander has Partner, Choose a Partner, or has a Background, you'll be prompted to select a second commander in a follow-up step.

**Learn more**: [Partner Mechanics Guide](partner_mechanics.md)

---

## Step 2: Select Primary Themes

Choose 1–3 core themes that define your deck's strategy by clicking theme chips in the modal. Themes are organized by pool size:

- **Recommended**: Themes that work well with your commander (marked with ★)
- **Pool Size Sections**: Themes grouped by available card count (Vast, Large, Moderate, Small, Tiny)

Each theme displays a badge showing the approximate number of cards available for that theme in your commander's colors.

**Tips**:
- Start with 2–3 themes for focused strategies
- Mix creature-tribal and mechanical themes for depth
- Larger pool sizes give the builder more card options
- Use AND mode for tighter synergy (cards match multiple themes)
- Use OR mode for broader pools (cards match any theme)

**Learn more**: [Theme Browser & Quality System](theme_browser.md)

---

## Step 3: Add Secondary/Synergy Themes (Optional)

After selecting your primary themes, you can add additional themes using the "Additional Themes" textbox:

- Enter theme names separated by commas
- Add utility packages (e.g., card draw, removal)
- Incorporate combo pieces or win conditions

**Multi-Theme Fallback**: If you select multiple themes, the builder uses a fallback cascade to find cards that synergize across themes. If no exact matches exist, it expands to broader combinations.

**Learn more**: [Random Build (Multi-Theme Cascade)](random_build.md#multi-theme-fallback-cascade)

---

## Step 4: Bracket Compliance

Set power-level restrictions with bracket policies (required, defaults to Bracket 3):

- **Bracket 1–4**: WOTC-defined power tiers
- **Enforcement Modes**: Advisory, Strict, or Custom
- **Banned Lists**: Automatically enforced per format rules

Enable bracket enforcement with `ENABLE_BRACKETS=1` (default: on).

**Learn more**: [Bracket Compliance Guide](bracket_compliance.md)

---

## Step 5: Preferences

Configure optional build behaviors and card priorities:

### Combo Preferences
- **Prioritize combos**: Automatically include combo pieces near the end of the build
  - **Combo count**: How many combos to include (default: 2)
  - **Balance**: Early game, late game, or mix

### Multi-Copy Package
- **Enable Multi-Copy package**: Include multiple copies of cards for token/tribal strategies
  - Works with archetypes like Rat Colony, Relentless Rats, Dragon's Approach
  - Automatically suggests Thrumming Stone synergy when applicable
  - **Learn more**: [Multi-Copy Package](multi_copy.md)

### Owned Card Preferences
- **Use only owned cards**: Limit the pool to cards you already own
- **Prefer owned cards**: Still allow unowned cards, but rank owned cards higher

Upload your collection at `/owned` or before starting a build.

**Learn more**: [Owned Cards Guide](owned_cards.md)

### Land Base Options
- **Swap basics for MDFC lands**: Modal DFC lands replace matching basic lands automatically
- **Smart Land Bases**: Auto-adjust land count and mana curve based on commander speed and color complexity

**Learn more**: [Land Bases Guide](land_bases.md)

---

## Step 6: Ideal Counts

Set target counts for key card categories using sliders or number inputs:

- **Ramp**: 0–30 cards (default varies by commander)
- **Lands**: 25–45 cards (default varies by commander speed)
- **Basic Lands**: 0–40 cards (subset of total lands)
- **Creatures**: 0–70 cards
- **Removal**: 0–30 cards (spot removal)
- **Wipes**: 0–15 cards (board wipes)
- **Card Advantage**: 0–30 cards (draw/recursion)
- **Protection**: 0–20 cards (counterspells, indestructible effects)

**Warning**: The builder validates your totals. If ideal counts exceed 99 cards, reduce totals to avoid build issues.

**Tips**:
- Start with default recommendations
- Adjust based on your deck's strategy
- Category totals may overlap (e.g., a creature that ramps counts in both)

---

## Step 7: Include/Exclude Specific Cards (Optional)

Fine-tune your deck with must-have or must-avoid lists:

- **Include List**: Guarantee specific cards in the deck (max 10)
- **Exclude List**: Prevent certain cards from being chosen (max 15)
- **File Upload**: Upload .txt files with one card name per line
- **Fuzzy Matching**: Card names are validated with approximate matching

Enable with `ALLOW_MUST_HAVES=true`.

**Learn more**: [Include/Exclude Cards Guide](include_exclude.md)

---

## Step 8: Budget Constraints (Optional)

Control deck cost with budget limits:

- **Total Budget ($)**: Set a deck cost ceiling — cards over budget will be flagged
- **Per-Card Ceiling ($)**: Flag individual cards above this price
- **Pool Filter Tolerance (%)**: Cards exceeding the per-card ceiling by more than this % are excluded from the card pool (default: 15%)
  - Set to 0 to hard-cap at the ceiling exactly

Budget filtering uses cached Scryfall prices and respects owned card preferences.

Enable with `ENABLE_BUDGET_MODE=1`.

**Learn more**: [Budget Mode Guide](budget_mode.md)

---

## Step 9: Advanced Build Options

### Quick Build / Skip Controls
Skip building specific card types to speed up the process:
- Skip lands (use with external manabase tools)
- Skip ramp/removal/draw
- Customize card type distribution

**Learn more**: [Quick Build & Skip Controls](quick_build_skip_controls.md)

### Batch Build Mode
Generate multiple deck variations at once:
- Build 1–10 decks with the same configuration
- Compare results to see variance in card selection

Enable with `ENABLE_BATCH_BUILD=1`.

**Learn more**: [Batch Build & Compare](batch_build_compare.md)

---

## Step 10: Build & Review

Once configured, click **Build Deck** to generate your decklist. The builder will:

1. Select cards based on your themes and synergies
2. Apply budget and bracket constraints
3. Optimize the manabase for your color identity
4. Balance card types (creatures, spells, lands)

### After Building

The results page shows:

- **Full Decklist**: All 100 cards with images and prices
- **Summary Stats**: Mana curve, color distribution, card types
- **Export Options**: CSV, TXT, JSON, or Arena format
- **Deck Actions**: Lock cards, replace specific cards, rebuild with changes

**Lock & Replace**: Found a card you want to keep? Lock it, then replace others without losing your favorites.

**Learn more**: [Locks, Replace & Permalinks](locks_replace_permalinks.md)

---

## Alternative Build Modes

### Random Build Mode
Let the builder choose themes, budget, and configuration automatically with seeded randomization.

**Learn more**: [Random Build Guide](random_build.md)

### Batch Build & Compare
Generate multiple deck variations at once and compare strategies side-by-side.

**Learn more**: [Batch Build & Compare](batch_build_compare.md)

---

## Tips for Success

1. **Start Simple**: Choose 2–3 strong themes for your first build
2. **Check Quality Badges**: Higher quality themes have better curation
3. **Review Theme Pool Sizes**: Larger pools give the builder more options
4. **Use Permalinks**: Save your deck configurations for tweaking later
5. **Iterate**: Lock good cards and rebuild to refine your strategy

---

## Environment Variables

Key settings for the build wizard:

- `ENABLE_THEMES=1` - Enable theme selection (default: on)
- `ENABLE_BUDGET_MODE=1` - Enable budget constraints
- `ENABLE_BRACKETS=1` - Enable bracket compliance (default: on)
- `ALLOW_MUST_HAVES=true` - Enable include/exclude lists
- `THEME_MIN_CARDS=5` - Minimum cards per theme

---

## Need More Help?

- Browse other guides for detailed feature documentation
- Check diagnostics at `/diagnostics` for system status
- Visit the theme browser at `/themes` to explore available strategies

---

## See Also

- [Theme Browser](theme_browser.md) — explore and evaluate available themes before building
- [Partner Mechanics](partner_mechanics.md) — two-commander builds and color identity rules
- [Bracket Compliance](bracket_compliance.md) — power level tiers and enforcement modes
- [Budget Mode](budget_mode.md) — filter the card pool by per-card price ceiling
- [Multi-Copy Package](multi_copy.md) — build with many copies of a single archetype card
- [Random Build](random_build.md) — spin up a randomized deck with one click
- [Batch Build & Compare](batch_build_compare.md) — generate and compare multiple builds at once
- [Potential Upgrades](suggested_upgrades.md) — find new cards and swap targets for a saved deck
