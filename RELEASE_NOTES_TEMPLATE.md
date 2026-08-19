# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

## [5.8.0]
### Added
- Rulebreaker Commanders: added support for 8 commanders whose oracle text bends normal deckbuilding rules:
  - Grizzlegom, Hurloon Hero: any basic land type, regardless of color identity, split evenly across all five basics.
  - Maular, the Next Evolution: creatures with mana value 7 or greater can be any color.
  - Seluma, Light of Aysen: Angels can be any color.
  - The Everforger: Artifact Creatures and Equipment can be any color.
  - The Unluckiest Planeswalker: Auras can be any color.
  - Tolabow, Loch Rascal: Instants and Sorceries can be your color identity plus one additional color of your choice.
  - Valko Indorian: cards with the Phyrexian subtype can be any color.
  - Whtz, the Bibliophile: no maximum deck size (a 100-card minimum still applies); the Ideal Counts sliders in "Build a New Deck" scale their recommended defaults live as you change the deck size, and stay fully adjustable afterward instead of being silently re-scaled behind the scenes at build time.
- The Manual Deck Builder's role health bar (Lands/Ramp/Removal/etc.) now shows targets based on the deck's actual chosen ideal counts, so a larger Whtz deck shows an accurate land target instead of a stale "X/35".
- The mobile app's build wizard now shows the same optional color picker and target-deck-size field the web UI does when a Rulebreaker commander is selected.
- Setup/Tagging now flags any Commander-legal card that looks like it may carry the Rulebreaker mechanic but isn't yet recognized (e.g. a newly spoiled card), with a review banner and ready-to-copy issue report on the Setup/Tagging page.

### Changed
- The "Build a New Deck" default power bracket is now Bracket 4 (Optimized) instead of Bracket 3 (Upgraded).

### Fixed
- Fixed an issue where card images could fall back to loading from Scryfall instead of your local cache after a fresh install.

### Removed
_No changes_

### Security
_No changes_

