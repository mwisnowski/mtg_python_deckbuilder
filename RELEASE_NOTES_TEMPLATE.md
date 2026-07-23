# MTG Python Deckbuilder

## [Unreleased]
### Added
- Guided (stage-by-stage) deck building for the public REST API: `POST /api/v1/builds` accepts `mode: "guided"` to pause after each build stage instead of running straight through; `POST /api/v1/builds/{id}/advance` runs the next stage and returns the cards it added for review, `GET /api/v1/builds/{id}/alternatives` suggests role-based swap candidates for a card already in the deck-in-progress, and `POST /api/v1/builds/{id}/replace` swaps a card in place and locks the replacement so later stages won't remove it
- CORS support for the public REST API, open to any origin by default so browser-based clients (e.g. the mobile companion app's web dev build) work with no configuration; restrict via `CORS_ALLOWED_ORIGINS` (comma-separated allow-list) or disable entirely with `CORS_ALLOWED_ORIGINS=none`
- `/api/images/{size}/{card_name}` now accepts `art_crop` as an image size, for clients that want just the illustration rather than the full card
- `GET /api/v1/decks/{filename}/analysis`: commander, color identity, mana curve, pip distribution, mana source breakdown, land summary (including MDFC lands counted as extra land slots), and total price for a saved deck, for clients (like the mobile app) that want the same "Mana Overview"/"Land Summary" data as the web deck view without re-deriving it from the CSV export
- `GET /api/v1/decks/{filename}`: card entries now include a `layout` field (Scryfall layout, e.g. `transform`, `modal_dfc`, `split`), so clients can tell double-faced cards with separate front/back images apart from split/adventure/aftermath cards that share one combined image
- `GET /api/v1/cards/{name}` now includes a `faces` array with per-face details (name, side, type, text, mana value, power/toughness, color identity) for split, adventure, transform, modal DFC, flip, and aftermath cards, letting clients show the "other side" of a multi-faced card, which the tagged card dataset otherwise omits

### Changed
_No unreleased changes yet_

### Fixed
- Fixed basic lands (Plains, Island, Swamp, Mountain, Forest, Wastes) showing up as "not found" in the card detail API; they now fall back to Scryfall for their info and art

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

