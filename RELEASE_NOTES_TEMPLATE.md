# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
- Manual Deck Builder: pool categories start collapsed and show every curated card at once, no more page-by-page browsing.

### Fixed
- Manual Deck Builder: a pool category's card cap no longer keeps refilling as you add cards to your deck.
- Cards that return or cast cards from a graveyard (Eternal Witness, Bala Ged Recovery, Flashback, Unearth, and similar effects) are no longer mislabeled as `Removal`; they now get a dedicated `Graveyard Recursion` tag.
- Cards that return a creature from your graveyard to the battlefield (e.g. Alesha, Who Laughs at Fate) were missing the `Reanimate` tag in some cases; fixed.
- The card browser's theme search now reliably finds newly added or renamed themes right after a retag.
- The Setup page's "Refresh Themes Only" button now always does its job when clicked.

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

