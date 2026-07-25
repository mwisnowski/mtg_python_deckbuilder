# MTG Python Deckbuilder

## [Unreleased]
### Added
- Land build steps now show descriptive labels (e.g. "Fetch Lands", "Kindred/Tribal Lands", "Misc/Utility Lands") instead of generic "Step 3", "Step 7" numbering
- "Remove Card" button in the web build review, next to the Alternatives suggestions: remove any card from the deck-in-progress at any point during the build for that run, freeing the slot for later steps (e.g. land backfill) to fill; Undo restores the card immediately
- Guided (stage-by-stage) deck building for the public REST API: `POST /api/v1/builds` accepts `mode: "guided"` to pause after each build stage instead of running straight through; `POST /api/v1/builds/{id}/advance` runs the next stage and returns the cards it added for review, `GET /api/v1/builds/{id}/alternatives` suggests role-based swap candidates for a card already in the deck-in-progress, and `POST /api/v1/builds/{id}/replace` swaps a card in place and locks the replacement so later stages won't remove it
- `POST /api/v1/builds/{id}/remove-card` and `POST /api/v1/builds/{id}/remove-card/undo`: mirrors the web build review's "Remove Card"/Undo for guided-mode API clients (like the mobile app)
- `POST /api/v1/builds/{id}/rerun`: re-runs the most recently completed guided-mode stage to pull a fresh batch of cards without advancing further
- CORS support for the public REST API, open to any origin by default so browser-based clients (e.g. the mobile companion app's web dev build) work with no configuration; restrict via `CORS_ALLOWED_ORIGINS` (comma-separated allow-list) or disable entirely with `CORS_ALLOWED_ORIGINS=none`
- `/api/images/{size}/{card_name}` now accepts `art_crop` as an image size, for clients that want just the illustration rather than the full card
- `GET /api/v1/decks/{filename}/analysis`: commander, color identity, mana curve, pip distribution, mana source breakdown, land summary (including MDFC lands counted as extra land slots), and total price for a saved deck, for clients (like the mobile app) that want the same "Mana Overview"/"Land Summary" data as the web deck view without re-deriving it from the CSV export
- `GET /api/v1/decks/{filename}`: card entries now include a `layout` field (Scryfall layout, e.g. `transform`, `modal_dfc`, `split`), so clients can tell double-faced cards with separate front/back images apart from split/adventure/aftermath cards that share one combined image
- `GET /api/v1/cards/{name}` now includes a `faces` array with per-face details (name, side, type, text, mana value, power/toughness, color identity) for split, adventure, transform, modal DFC, flip, and aftermath cards, letting clients show the "other side" of a multi-faced card, which the tagged card dataset otherwise omits
- Loyalty is now tracked in the tagged card dataset and searchable via `loy:`/`loyalty:` (e.g. `loy>=4`), matching the existing power/toughness/cmc search operators
- Fetch lands are now tagged with their mechanical shape (`Fetchland`, `Panorama Land`, `New Capenna Land`, `Landscape Land`, `Alt Fetchland`) and the specific basic/land types they can search for, laying the groundwork for color-identity-aware fetch land filtering
- Groundwork for multi-printing card images: images can now be cached per-printing instead of just one per card name; `IMAGE_CACHE_MODE=default|full` controls whether only the best printing or every printing gets downloaded (default: same footprint as before). New `GET /api/printings/{card_name}` lists a card's known printings, and `/api/images/{size}/{card_name}` accepts an optional `printing` parameter.
- A "Choose Printing" button on card tiles across the web build review, Finished Decks (list and thumbnail views), Card Browser, Owned Library, and the Card Details page opens a picker of that card's known printings so you can swap to a different art/set; the selection is remembered and shared across all pages (choose it in one place, it shows up in the others too), and included in permalinks. On the Owned Library it's just a visual preview and doesn't change which cards count as owned. The picker opens as a floating popup next to the button so it's never squished on a narrow card tile.
- Per-printing pricing: the web build review's price display now reflects the specific printing you've selected, instead of always showing the cheapest printing's price

### Changed
_No unreleased changes yet_

### Fixed
- Fixed basic lands (Plains, Island, Swamp, Mountain, Forest, Wastes) showing up as "not found" in the card detail API; they now fall back to Scryfall for their info and art
- Fetch lands are no longer auto-added (or suggested as swap alternatives) unless they can actually search for a basic land type in your deck's colors, so a mono-red deck won't get a Plains-fetching land
- Tribal ("kindred") lands tied to a specific creature type (e.g. an Angel land) are no longer added to decks that aren't actually built around that tribe
- Fixed missing "Tokens Matter" tag on cards that create a token via a copy effect without saying "creature token" (e.g. `Hashaton, Scarab's Fist`, `Kiki-Jiki, Mirror Breaker`)
- "Ramp" is now correctly detected for cards that grant a mana ability to other permanents or word out mana amounts instead of using mana symbols (e.g. `A Realm Reborn`); mana filters/batteries that don't net more mana than they cost (e.g. `Golden Egg`, `Gemstone Array`) are intentionally excluded

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

