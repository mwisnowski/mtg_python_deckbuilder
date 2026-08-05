# MTG Python Deckbuilder

## [Unreleased]
### Added
- Manual Deck Builder: pick a commander, then build the deck yourself by browsing the legal card pool (filter/sort/search), adding and removing cards, and watching a live role-health bar (Ramp/Removal/Draw/Lands/Threats) update as you go. Save the finished deck like any other, or export it as CSV/TXT without saving.
- Manual Deck Builder: the pool now hides cards fully banned at your bracket and badges cards allowed up to a cap, plus a live pill row for Game Changers/Extra Turns/Mass Land Denial/Nonland Tutors/Two-Card Combos.
- Manual Deck Builder: an **Edit Deck** button lets you reopen any deck you own and adjust its cards, saving back over the original file.
- Manual Deck Builder: pool cards now show a "Sorted by" indicator and a "Why this card?" note, plus a new "Theme Match" sort option.
- Manual Deck Builder: a new "+ Add Land Package" button pre-adds basic lands (split by color) and standard staple lands (Command Tower, Reliquary Tower, etc.).
- Manual Deck Builder: the pool is now organized into categorized sections (New Cards, On-Brand Cards, Related Synergy, Creatures, Instants, Sorceries, Utility Artifacts, Enchantments, Battles, Planeswalkers, Utility Lands, Mana Artifacts, Lands), each searchable and paginated on its own (capped to a curated top 50, expanded by default), with a pinned table-of-contents for jumping between them and one search box covering the whole pool at once.
- Manual Deck Builder: pool cards now have a printing/foil picker, and the "Why this card?" panel lists every theme tag, highlighting deck-theme matches separately from the tag that decided its role-bar bucket.
- Manual Deck Builder: basic lands and unlimited-copy cards in the deck panel now have a quantity input to set an exact copy count directly.
- Manual Deck Builder: the search box now supports Scryfall-style query syntax (e.g. `t:creature`, `c:rg`, `mv>=4`, `pow>=4`) in addition to plain name search.
- Manual Deck Builder: cards are hidden from the pool once added to the deck (reappearing if removed), except basic lands and unlimited-copy cards.
- Manual Deck Builder: the old role/sort dropdown pool filter is replaced by the categorized layout above.
- Manual Deck Builder: the role health bar's "Threats" pill is now split into "Protection", "Board Wipe", and "On-Theme", and the bar stays pinned to the top of the page (alongside the table-of-contents) as you scroll.
- Manual Deck Builder: the inline "Why this card?"/"Other Good Options" block is replaced by a hover panel, keeping the pool grid focused on the cards themselves.
- Manual Deck Builder: the commander's card image now appears above the current deck panel, and both stay pinned to the right side as you scroll.
- Manual Deck Builder: the pinned table-of-contents/role bar no longer overlaps the commander's card image, and the Save Deck/Export buttons now stick to the deck panel instead of floating independently.
- Manual Deck Builder: removed the non-functional duplicate "Build Manually" nav link and home-page button; use the "Build Manually" option inside the New Deck modal instead.
- Manual Deck Builder: fixed the empty "Lands" category and the "Utility Lands" category incorrectly including plain mana-fixing lands.
- Manual Deck Builder: starting a new build (or using "Edit Deck") no longer carries over cards/pool/save-target from a previous unfinished session.
- Manual Deck Builder: the card hover preview no longer disappears when hovering over a card's name text in the deck panel.
- Manual Deck Builder: the Ramp/Removal/Card Draw/Board Wipes/Protection pool categories now sort by popularity like the rest of the pool, instead of favoring theme matches.
- Manual Deck Builder: the Protection category no longer counts cards whose protective ability only helps themselves; it now favors cards that actually protect the rest of your board.
- Card tagging: added a new `Graveyard Hate` tag for cards that deny opponents the use of their graveyard, separate from `Board Wipes`.
- Public API: build sessions now support a manual mode (`mode: "manual"`) for browsing the card pool, adding/removing cards, setting exact copy counts, adding a starting land package, searching, getting suggestions, and saving a deck entirely over the API, matching the Manual Deck Builder's functionality.
- Public API: manual-mode responses now include a mana overview (pip distribution, mana sources, mana curve) for the deck-in-progress, plus a new endpoint to fetch the current deck panel/role bar/mana overview without making any changes.

### Changed
- All Cards browser and Owned Library: replaced the color/type/rarity dropdowns and CMC/power/toughness range filters with a single search box supporting the same Scryfall-style syntax as the Manual Deck Builder (e.g. `t:creature`, `c:rg`, `tag:aristocrats`, `pow>=4`). Plain text search still works as before; theme filters and sorting are unchanged.

### Fixed
- Card database: refreshed the card list and recommendation data (fixes stale "New Cards" results and a few un-set/joke cards incorrectly appearing in the pool).
- Card database: fixed a handful of long-established cards (e.g. Command Tower, Fabled Passage, Jeska's Will) being incorrectly badged "New" in the pool.
- Card database: cards that are never tournament-legal in Commander (joke sets, oversized promos, etc.) are now automatically filtered out of the pool, instead of relying on a hardcoded list.
- Card database: fixed some cards getting an incorrect "Ward" tag from unrelated words (e.g. "toward", "Warden"), and improved detection of self-only protective abilities on legendary cards.
- Card tagging: fixed several cards incorrectly showing up as `Board Wipes` (e.g. Mimic Vat, Underworld Cerberus) due to overly broad text matching.

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

