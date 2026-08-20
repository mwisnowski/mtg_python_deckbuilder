# MTG Python Deckbuilder

## [Unreleased]
### Added
- Tagging: new `code/scripts/apply_oracle_tag_adoptions.py` applies human-reviewed Scryfall Oracle Tag consolidation/adoption decisions to `all_cards.parquet`, adding 64 new theme/metadata tags (e.g. Spot Removal, Sacrifice Outlet, Pathway Lands, Group Hug, several Tutor/Theft/Removal/Sacrifice Outlet metadata tags) and merging ~1,800 additional overlap-based tag consolidations across the card pool.
- Tagging: new creature type-family groupings, mirroring the existing Outlaw mechanic: `Party` (Cleric/Rogue/Warrior/Wizard), `Sea Monster` (Kraken/Leviathan/Octopus/Serpent), `Fiend` (Demon/Devil/Imp/Tiefling), `Undead` (Zombie/Skeleton), and `Nature` (Plant/Treefolk/Fungus/Saproling). Cards with a member type now also get the synthetic family type, which surfaces as a `{Family} Kindred` theme tag.
- Data: added optional support for Scryfall's community art-illustration tags, buildable from the Setup page.
- Web: cards can now be searched by their art/illustration tags, and a collapsed "Art Tags" section appears on card detail pages when available.
- Web: search terms with dashes (e.g. `rabbit-battery`) now work the same as quoting a space-separated equivalent, everywhere search is used.
- Web: card detail pages show a collapsed "Metadata Tags (internal)" section for the deck builder's own internal/diagnostic tags, now searchable with a new `metadata:`/`mtag:`/`metatag:` flag.

### Changed
- Web: search autocomplete (`GET /cards` theme suggestions) now reads `config/themes/theme_list.json` instead of `theme_catalog.csv`, since the JSON file is regenerated automatically by every tagging run while the CSV needs a separate manual script; new/renamed themes now show up in autocomplete without an extra step.

### Fixed
- Web: fixed a theme catalog path-resolution bug where the search autocomplete's local-dev path calculation could resolve to a small committed test fixture directory instead of the real theme catalog.
- Tagging: fixed a bug where suggested example commanders for some themes could include cards that aren't actually legal commanders.

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

## [5.8.1]
### Changed
- Homepage: the "What's New" banner now advertises Rulebreaker Commanders instead of the older User Accounts & Deck Visibility promo.

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

