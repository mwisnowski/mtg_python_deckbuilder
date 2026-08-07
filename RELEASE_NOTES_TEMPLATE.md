# MTG Python Deckbuilder

## [Unreleased]
### Added
- Manual Deck Builder: press Shift+Enter in the card search box to instantly add the best-guess match; the search results now show which card that would be.
- Card Browser: typing a tag search flag now suggests matching tag names to fill in, so you don't have to know the exact spelling.

### Changed
- Manual Deck Builder: card name search feels a bit snappier while typing.

### Fixed
- Manual Deck Builder: the pool no longer jumps to a different section when adding or removing a card.
- Manual Deck Builder: finished decks built manually now show correct mana pip/source charts instead of blank ones.
- Manual Deck Builder: picking a printing for a searched card no longer affects other cards in the search results.
- Manual Deck Builder: cards you add from search results now disappear from the list right away.
- Tagging: fixed duplicate "bending" theme tags on Avatar-style cards (e.g. Airbend and Airbending on the same card).
- Search: excluding a tag (e.g. `-tag:"Spellslinger"`) alongside another tag filter now actually excludes it instead of being ignored.

### Removed
- Card Browser and Owned Library: removed the separate "Themes" filter bar; you can already filter by theme/tag from the main search box.

### Security
_No unreleased changes yet_

