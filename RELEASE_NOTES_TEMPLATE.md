# MTG Python Deckbuilder

## [Unreleased]
### Added
- Web: decks that include cards which create tokens or emblems now show a new "Tokens & Emblems Created" section in the deck summary (collapsed by default, like the Mana Overview/Test Hand sections) and a matching section in CSV/TXT exports, listing each token/emblem, its stats, and which card(s) create it; the public API's deck detail/export endpoints correctly treat this as an informational section and exclude it from the card list.
- Web: each token/emblem in that new section shows a thumbnail image (using the same cached artwork as regular cards) and a "Choose Printing" button to pick a specific alternate art/printing, just like the picker already available for regular cards; tokens that share a name and power/toughness but have different abilities (e.g. two different 1/1 Fish tokens) are correctly kept separate instead of mixing their artwork together.
- Public API: the deck analysis endpoint (`GET /api/v1/decks/{filename}/analysis`) now includes a `tokens_created` field with the same token/emblem and creator-card data shown in the web UI.
- Public API: a new `POST /api/v1/decks/{filename}/token-printing` endpoint lets clients (e.g. the mobile app) persist a chosen alternate printing for a token/emblem a deck creates, mirroring the web UI's own "Choose Printing" button; `GET /api/v1/decks/{filename}/analysis` reflects that choice via `tokens_created`'s `scryfall_id` field.
- Web: tokens and emblems are now searchable in the card browser, hidden by default and surfaced only with an explicit `type:token` or `type:emblem` search so normal browsing is unaffected. Card detail pages for cards that create tokens/emblems now show a collapsed-by-default "Tokens Generated" section with each token's thumbnail image, type line, and ability text. Both of these now also include the same "Choose Printing" button already available elsewhere, so an alternate art/set can be picked for a token directly from the card browser. The public REST API (`GET /api/v1/cards`) supports the same `type:token`/`type:emblem` search and now returns `isToken`/`isEmblem`/`power`/`toughness`/`colors`/`textHash` fields, plus a new `GET /api/token-printings/{name}` endpoint, so clients like the mobile app can show a token's own artwork and alternate printings instead of a same-named real card's.

### Changed
- Web: the card browser now supports classic page-based pagination (default 50 cards per page, with Previous/Next links and a "go to page" box), configurable via the new `CARD_BROWSER_PAGE_SIZE` environment variable; setting it to `0` or leaving it empty reverts to the previous infinite-scroll "Load More" experience. The hover-preview popup on grid tiles is unchanged in both modes.

### Fixed
- Web: card browser grid tiles had a large, unintended horizontal gap between columns because their outer element accidentally picked up an unrelated `width: 170px` rule (meant for the deck builder's own card tiles, kept only for shared hover-preview compatibility). Cards now stretch to fill their grid column, matching how token/emblem tiles already displayed, and the grid's horizontal gap was also narrowed slightly relative to its row spacing.

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_