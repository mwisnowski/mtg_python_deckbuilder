# Build X and Compare User Guide

## Overview

The **Build X and Compare** feature allows you to build multiple decks using the same configuration and compare the results side-by-side. This is useful for:

- **Seeing variance**: Understand which cards are consistent vs. which cards vary due to RNG
- **Finding optimal builds**: Compare multiple results to pick the best deck
- **Analyzing synergies**: Use the Synergy Builder to create an optimized "best-of" deck

## Quick Start

### 1. Build Multiple Decks

1. Click **New Deck** to open the deck builder modal
2. Configure your commander, themes, ideals, and bracket as normal
3. At the bottom of the modal, adjust the **"Number of decks to build"** slider (1-10)
   - Setting this to 2 or more enables batch build mode
4. Click **Quick Build** - the "Create" button is hidden for batch builds

**Note**: All builds use the exact same configuration. There are no variations in commander, themes, or ideals - you're simply running the same build multiple times to see different card selections.

### 2. Track Progress

After starting a batch build, you'll see a progress screen showing:

- **Progress bar**: Visual indicator of completion
- **Build status**: "Completed X of Y builds..."
- **Time estimate**: Dynamically adjusted based on commander color count
  - 1-2 colors: 1-3 minutes
  - 3 colors: 2-4 minutes
  - 4-5 colors: 3-5 minutes
- **First deck time**: The first deck takes ~55-60% of total time

### 3. Compare Results

Once all builds complete, you'll be redirected to the **Comparison View** with:

#### Overview Stats
- **Unique Cards Total**: All different cards across all builds
- **In All Builds**: Cards that appear in every single deck
- **In Most Builds (80%+)**: High-frequency cards
- **In Some Builds**: Medium-frequency cards
- **In Few Builds**: Low-frequency cards

#### Most Common Cards
Shows the top 20 cards by appearance frequency, excluding guaranteed cards like:
- Basic lands
- Staple lands (Command Tower, Reliquary Tower, etc.)
- Must-include cards (if using the include/exclude feature)
- Fetch lands

**Tip**: Hover over any card name to see the card image!

#### Individual Build Summaries
Each build shows:
- Total card count and breakdown (Creatures, Lands, Artifacts, etc.)
- Expandable card list with full deck contents

## Using the Synergy Builder

The **Synergy Builder** analyzes all builds and creates an optimized "best-of" deck using the most synergistic cards.

### How It Works

The Synergy Builder scores each card based on:

1. **Frequency (50%)**: How often the card appears across builds
   - Cards in 80%+ of builds get a 10% bonus
2. **EDHREC Rank (25%)**: Community popularity data
3. **Theme Tags (25%)**: Alignment with your chosen themes

### Building a Synergy Deck

1. From the comparison view, click **✨ Build Synergy Deck**
2. Wait a few seconds while the synergy deck is generated
3. Review the results:
   - **Synergy Preview**: Shows the full deck with color-coded synergy scores
     - 🟢 Green (80-100): High synergy
     - 🔵 Blue (60-79): Good synergy
     - 🟡 Yellow (40-59): Medium synergy
     - 🟠 Orange (20-39): Low synergy
     - 🔴 Red (0-19): Very low synergy
   - Cards are organized by type (Creature, Artifact, Enchantment, etc.)
   - Each section can be expanded/collapsed for easier viewing

### Exporting the Synergy Deck

1. Click **Export Synergy Deck** at the bottom of the synergy preview
2. **Warning**: This will delete the individual batch build files and disable batch export
3. Confirm the export to download a ZIP containing:
   - **SynergyDeck_CommanderName.csv**: Deck list in CSV format
   - **SynergyDeck_CommanderName.txt**: Plain text deck list
   - **summary.json**: Deck statistics and metadata
   - **compliance.json**: Bracket compliance information
   - **synergy_metadata.json**: Synergy scores and build source data

## Additional Actions

### Rebuild X Times
Click **🔄 Rebuild Xx** to run the same configuration again with the same build count. This creates a new batch and redirects to the progress page.

### Export All Decks
Click **Export All Decks as ZIP** to download all individual build files as a ZIP archive containing:
- CSV and TXT files for each build (Build_1_CommanderName.csv, etc.)
- `batch_summary.json` with metadata

**Note**: This button is disabled after exporting a synergy deck.

## Performance Notes

- **Parallel execution**: Builds run concurrently (max 5 at a time) for faster results
- **Build time scales**: More colors = longer build times
  - Mono/dual color: ~1 minute per 10 builds
  - 3 colors: ~2-3 minutes per 10 builds
  - 4-5 colors: ~3-4 minutes per 10 builds
- **First deck overhead**: The first deck in a batch takes longer due to setup

## Feature Flag

To disable this feature entirely, set `ENABLE_BATCH_BUILD=0` in your environment variables or `.env` file. This will:

- Hide the "Number of decks to build" slider
- Force all builds to be single-deck builds
- Hide comparison and synergy features

## Tips & Best Practices

1. **Start small**: Try 3-5 builds first to get a feel for variance
2. **Use for optimization**: Build 5-10 decks and pick the best result
3. **Check consistency**: Cards appearing in 80%+ of builds are core to your strategy
4. **Analyze variance**: Cards appearing in <50% of builds might be too situational
5. **Synergy builder**: Best results with 5-10 source builds
6. **Export early**: Export individual builds before creating synergy deck if you want both

## Troubleshooting

### Builds are slow
- Check your commander's color count - 4-5 color decks take longer
- System resources - close other applications
- First build takes longest - wait for completion before judging speed

### All builds look identical
- Rare but possible - try adjusting themes or ideals for more variety
- Check if you're using strict constraints (e.g., "owned cards only" with limited pool)

### Synergy deck doesn't meet ideals
- The synergy builder aims for ±2 cards per category
- If source builds don't have enough variety, it may relax constraints
- Try building more source decks (7-10) for better card pool

### Export button disabled
- You've already exported a synergy deck, which deletes individual batch files
- Click "Rebuild Xx" to create a new batch if you need the files again

## See Also

- [Docker Setup Guide](../DOCKER.md) - Environment variables and configuration
- [README](../../README.md) - General project documentation
- [Changelog](../../CHANGELOG.md) - Feature updates and changes
