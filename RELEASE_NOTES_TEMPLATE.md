# MTG Pyt### Added
- Keywo### Changed
- Keywords consolidate variants (e.g., "Commander ninjutsu" → "Ninjutsu") for consistent theme matching
- Protection tag refined to focus on shield-granting cards (329 cards vs 1,166 previously)
- Theme catalog streamlined with improved quality (736 themes, down 2.3%)
- Commander search and theme picker now share an intelligent debounce to prevent redundant requests while typing
- Card grids adopt modern containment rules to minimize layout recalculations on large decks
- Include/exclude buttons respond immediately with optimistic updates, reconciling gracefully if the server disagrees
- Frequently accessed views, like the commander catalog default, now pull from an in-memory cache for sub-200 ms reloads
- Deck review loads in focused chunks, keeping the initial page lean while analytics stream progressively
- Chart hover zones expand to full column width for easier interactionnup filters out one-off specialty mechanics (like set-specific ability words) while keeping evergreen abilities
- Protection grant detection identifies cards that give Hexproof, Ward, or other shields to your permanents
- Creature-type-specific protection automatically tagged (e.g., "Knights Gain Protection" for tribal strategies)
- Skeleton placeholders accept `data-skeleton-label` microcopy and only surface after ~400 ms across the build wizard, stage navigator, and alternatives panel
- Must-have toggle API (`/build/must-haves/toggle`), telemetry ingestion route (`/telemetry/events`), and structured logging helpers capture include/exclude beacons
- Commander catalog results wrap in a deferred skeleton list while commander art lazy-loads via a new `IntersectionObserver` helper in `code/web/static/app.js`
- Collapsible accordions for Mana Overview and Test Hand sections defer heavy analytics until they are expanded
- Click-to-pin chart tooltips keep comparisons anchored and add copy-friendly working buttons
- Virtualized card lists automatically render only visible items once 12+ cards are presentkbuilder ${VERSION}

### Summary
- Smarter card tagging: Keywords are cleaner (96% noise reduction) and Protection now highlights cards that actually grant shields to your board
- Builder responsiveness upgrades: smarter HTMX caching, shared debounce helpers, and virtualization hints keep long card lists responsive
- Commander catalog now ships skeleton placeholders, lazy commander art loading, and cached default results for faster repeat visits
- Deck summary streams via an HTMX fragment while virtualization powers summary lists without loading every row up front
- Mana analytics load on demand with collapsible sections and interactive chart tooltips that support click-to-pin comparisons

### Added
- Skeleton placeholders accept `data-skeleton-label` microcopy and only surface after ~400 ms across the build wizard, stage navigator, and alternatives panel.
- Must-have toggle API (`/build/must-haves/toggle`), telemetry ingestion route (`/telemetry/events`), and structured logging helpers capture include/exclude beacons.
- Commander catalog results wrap in a deferred skeleton list while commander art lazy-loads via a new `IntersectionObserver` helper in `code/web/static/app.js`.
- Collapsible accordions for Mana Overview and Test Hand sections defer heavy analytics until they are expanded.
- Click-to-pin chart tooltips keep comparisons anchored and add copy-friendly working buttons.
- Virtualized card lists automatically render only visible items once 12+ cards are present.

### Changed
- Commander search and theme picker now share an intelligent debounce to prevent redundant requests while typing.
- Card grids adopt modern containment rules to minimize layout recalculations on large decks.
- Include/exclude buttons respond immediately with optimistic updates, reconciling gracefully if the server disagrees.
- Frequently accessed views, like the commander catalog default, now pull from an in-memory cache for sub-200 ms reloads.
- Deck review loads in focused chunks, keeping the initial page lean while analytics stream progressively.
- Chart hover zones expand to full column width for easier interaction.

### Fixed
- _None_
