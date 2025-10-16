# MTG Python Deckbuilder ${VERSION}

### Summary
Improved colorless commander support with automatic card filtering and display fixes.

### Added
- **Colorless Commander Filtering**: 25 cards that don't work in colorless decks are now automatically excluded
  - Filters out cards like Arcane Signet, Commander's Sphere, and medallions that reference "commander's color identity" or colored spells
  - Only applies to colorless identity commanders (Karn, Kozilek, Liberator, etc.)

### Fixed
- **Colorless Commander Display**: Fixed three bugs affecting colorless commander decks
  - Color identity now displays correctly (grey "C" button with "Colorless" label)
  - Wastes now correctly added as basic lands in colorless decks
  - Colored basics (Plains, Island, etc.) no longer incorrectly added to colorless decks
