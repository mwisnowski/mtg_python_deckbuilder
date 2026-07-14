# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Card Detail Page** (`/cards/{name}`): Fully redesigned with a 2-column grid layout
  - Card image with "New" badge for recently released cards
  - Stats table: card type, mana value, power/toughness, rarity, EDHREC rank, color identity pips
  - Oracle text with inline mana symbol rendering
  - Theme tag chips
  - External links to Scryfall, Gatherer, and EDHREC
  - Market price panel with live TCG + CK prices via `/api/price/`
  - **Official rulings** panel: first 3 rulings shown, expandable "Show all / Show fewer" toggle; mana symbols rendered in ruling text
  - Similar cards section
- **Rulings service** (`code/web/services/rulings.py`): cache-first lookup (loads `rulings_cache.json` at startup); falls back to a rate-limited live Scryfall fetch (≤10 req/s) on cache miss
- **Rulings cache builder** (`code/file_setup/rulings_cache.py`): downloads the Scryfall bulk rulings file (one request, ~25 MB), maps oracle_id → rulings, then writes `card_files/processed/rulings_cache.json` keyed by scryfallID; integrated into the setup pipeline
- **Owned Library overhaul**: Full redesign matching the card browser layout and filter UX
  - Server-side filtering: search, card type, color identity, themes (multi-select, AND logic), CMC/Power/Toughness range
  - Sticky filter bar (same `position: sticky` behavior as card browser)
  - Card name autocomplete via new `/owned/search-autocomplete` endpoint
  - Theme multi-select with chip UI, reusing the `/cards/theme-autocomplete` endpoint
  - CMC, Power, and Toughness range inputs; `owned_store.get_stats_map()` enriches values from stored meta, falling back to a batch parquet lookup
  - Full-page scroll replacing the old fixed-height scroll box
- **Card browser sticky filter bar**: `.card-browser-filters` is now `position: sticky` so filters remain visible while scrolling through results
- **Collapsible filter panel**: Both the card browser and owned library have a "Filters ▼" toggle button; collapsed state persists per page via `localStorage`; active filter count shown in the button label while collapsed (e.g., "Filters (2 active)")
- **Owned Library → Card Details link**: Each owned library card tile now has a "Card Details" button linking to `/cards/{name}?ref=owned`
- **Smart back button on card detail page**: The "Back" button reads the `ref` query param; arriving from the owned library shows "Back to Owned Library" (→ `/owned`), all other sources show "Back to Card Browser" (→ `/cards`)
- **Similar cards expanded**: Card detail page now shows up to 15 similar cards (was 5)

### Changed
- **Card browser filter bar**: `position: relative` inline style removed from template; stickiness now comes from the CSS class

### Fixed
- **Similar cards refresh button**: `/{card_name:path}/similar` HTMX endpoint now registered before the `/{card_name:path}` catch-all route; previously the greedy `:path` matcher captured `/similar` as part of the card name, returning a 404

### Removed
_No unreleased changes yet_
