# MTG Python Deckbuilder ${VERSION}

## [Unreleased]

### Summary
- Card tagging improvements separate gameplay themes from internal metadata for cleaner deck building
- Keyword cleanup reduces specialty keyword noise by 96% while keeping important mechanics
- Protection tag now highlights cards that grant shields to your board, not just inherent protection
- **Protection System Overhaul**: Smarter card detection, scope-aware filtering, and focused pool selection deliver consistent, high-quality protection card recommendations
  - Deck builder distinguishes between board-wide protection and self-only effects using fine-grained metadata
  - Intelligent pool limiting focuses on high-quality staples while maintaining variety across builds
  - Scope-aware filtering automatically excludes self-protection and type-specific cards that don't match your deck
  - Enhanced detection handles Equipment, Auras, phasing effects, and complex triggers correctly
- Web UI responsiveness upgrades with smarter caching and streamlined loading

### Added
- Metadata partition keeps internal tags separate from gameplay themes
- Keyword normalization filters out one-off specialty mechanics while keeping evergreen abilities
- Protection grant detection identifies cards that give Hexproof, Ward, or other shields to your permanents
- Creature-type-specific protection automatically tagged (e.g., "Knights Gain Protection" for tribal strategies)
- Protection scope filtering (feature flag: `TAG_PROTECTION_SCOPE`) automatically excludes self-only protection like Svyelun
- Phasing cards with protective effects now included in protection pool (e.g., cards that phase out your permanents)
- Debug mode: Hover over cards to see metadata tags showing protection scope (e.g., "Your Permanents: Hexproof")
- Skeleton placeholders with smart timing across build wizard and commander catalog
- Must-have toggle API with telemetry tracking for include/exclude interactions
- Commander catalog lazy-loads art and caches frequently accessed views
- Collapsible sections for mana analytics defer loading until expanded
- Click-to-pin chart tooltips for easier card comparisons
- Virtualized card lists handle large decks smoothly

### Changed
- Card tags now split between themes (for deck building) and metadata (for diagnostics)
- Keywords consolidate variants (e.g., "Commander ninjutsu" → "Ninjutsu") for consistent theme matching
- Protection tag refined to focus on shield-granting cards (329 cards vs 1,166 previously)
- Deck builder protection phase filters by scope: includes "Your Permanents:", excludes "Self:" protection
- Protection card selection randomized for variety across builds (deterministic when using seeded mode)
- Theme catalog streamlined with improved quality (736 themes, down 2.3%)
- Theme catalog automatically excludes metadata tags from suggestions
- Commander search and theme picker share intelligent debounce to prevent redundant requests
- Include/exclude buttons respond immediately with optimistic updates
- Commander catalog default view loads from cache for sub-200ms response times
- Deck review loads in focused chunks for faster initial page loads
- Chart hover zones expanded for easier interaction

### Fixed
### Fixed
- Setup progress correctly displays 100% upon completion
- Theme catalog refresh stability improved after initial setup
- Server polling optimized for reduced load
- Protection detection accurately filters inherent vs granted effects
- Protection scope detection improvements for 11+ cards:
  - Dive Down, Glint no longer falsely marked as opponent grants (reminder text now stripped)
  - Drogskol Captain and similar cards with "Other X you control have Y" patterns now tagged correctly
  - 7 cards with static Phasing keyword now detected (Breezekeeper, Teferi's Drake, etc.)
  - Cloak of Invisibility and Teferi's Curse now get "Your Permanents: Phasing" tags
  - Shimmer now gets "Blanket: Phasing" for chosen type effect
  - King of the Oathbreakers reactive trigger now properly detected
- Type-specific protection (Knight Exemplar, Timber Protector) no longer added to non-matching decks
- Deck builder correctly excludes "Self:" protection cards (e.g., Svyelun) from protection pool
- Inherent protection cards (Aysen Highway, Phantom Colossus) now correctly receive scope metadata tags
- Protection pool now intelligently limited to focus on high-quality, relevant cards for your deck
