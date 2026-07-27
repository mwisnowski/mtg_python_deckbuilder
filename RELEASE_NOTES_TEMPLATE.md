# MTG Python Deckbuilder

## [Unreleased]
### Added
- `POST /api/v1/decks/{filename}/foil` and `POST /api/v1/builds/{id}/foil`: set a card's foil finish on a saved deck or in-progress build, mirroring the existing printing-selection endpoints
- `GET /api/v1/decks/{filename}` card entries now include `is_foil`
- `POST /api/price/batch` accepts an optional `foil_map` (per-card foil overrides); deck CSV-with-prices downloads and `GET /api/v1/decks/{filename}/analysis`'s total price now price each card at its own foil finish instead of assuming nonfoil
- Card detail page's market price panel now shows both the nonfoil and foil TCGPlayer prices together (e.g. "TCG $21.19 / ✨ $38.80") for the selected printing, and updates when the printing or foil toggle changes instead of always showing the nonfoil price
- Card detail page's foil toggle is hidden for printings with no foil version, and locked on for foil-only printings
- A static, rainbow foil overlay now shows over the card image anywhere a foil card's image is displayed: card detail page, saved deck view (commander header and card thumbnails), the new-deck and partner commander-selection previews, the deck builder's review stage (commander, partner, and card list), the owned card library, the card browser grid, and the commander directory; the printing/foil buttons are overlaid directly on the card image instead of below it
- Card browser and owned library tiles now show clickable guild/shard/wedge/nephilim color-identity names (e.g. "Bant", with "Azorius"/"Selesnya"/"Simic" sub-badges) alongside the color pips; clicking a pip or name applies a color filter, clicking the card image opens its details page, and clicking a theme tag runs a theme search
- Card browser and owned library color filters now have an "Inclusive match" toggle: exact mode (default) matches only that exact color combination, inclusive mode matches any card whose color identity contains the selected colors (e.g. searching "WU" also finds Bant, Esper, and Jeskai cards)
- Card detail page now shows a "Transform" button for double-faced/split/flip/meld cards to flip the card image (also updating when you change the printing), with both faces' type, mana cost, power/toughness, and oracle text always shown

### Changed
_No unreleased changes yet_

### Fixed
- The card browser's color filter now matches color identity regardless of the raw data's letter order (previously required an exact string match, so some valid filter selections silently returned no results)
- `GET /api/printings/{card_name}` now resolves double-faced/split/flip/meld names ("A // B") to their front face before looking up printings, instead of always returning an empty list for those names

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

