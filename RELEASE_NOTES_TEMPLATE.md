# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Deck visibility**: mark any deck Private, Unlisted, or Public, and control who can see or find it
  - Shareable links for Unlisted/Public decks (`/decks/<username>/<deck-name>`) with a one-click Copy Link button
  - "Other Users' Decks" section on the Finished Decks page shows Public decks shared by other accounts, with commander/theme search and a "Personal only" toggle
  - Set a default visibility on your Profile page that new builds use automatically, or override it per-build right in the New Deck wizard
  - Friendly notice page when a shared link points to a deck that's since been set to Private
- Redesigned Finished Decks filters: collapsible filter panel with separate Commander and Theme search boxes (with suggestions as you type), replacing the old single filter box and theme dropdown
- Homepage banner introducing the new account & deck visibility features (dismissible, reappears for future feature announcements)
- `robots.txt` added to keep the app out of search engine indexes

### Changed
- Finished Decks page sections reordered: your decks, then other users' public decks, then community/legacy decks
- Removed the "TXT only" filter on the Finished Decks page (wasn't behaving reliably and rarely useful)

### Fixed
- Newly built decks (including after automatic bracket-compliance fixes) could land in the shared decks folder instead of your own account folder; exports and compliance reports now consistently save to the right place

### Removed
_No unreleased changes yet_

