# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Hover-intent prefetch** (`WEB_PREFETCH=1`): Hovering over an "Open" button on the Finished Decks page now prefetches the deck view in the background after a 100 ms delay, eliminating the CSV-parse wait on click. On Chrome 108+, uses the Speculation Rules API for full prerender (`data-prerender-ok="1"`); falls back to `rel=prefetch` on other browsers. Feature-flagged and off by default; respects Data Saver / 2G connections and limits concurrent prefetches to 2.

