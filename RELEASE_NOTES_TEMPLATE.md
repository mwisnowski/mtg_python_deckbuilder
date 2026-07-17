# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
- "Popular in your past builds" theme recommendations now consider every past build across all accounts, not just the shared pre-accounts folder; a deck's visibility (private/unlisted/public) has no bearing on this signal

### Fixed
- **Potential Upgrades page** (`/decks/upgrades`) returned "Page Not Found" for any logged-in user because it always looked for decks in the shared guest folder instead of the account's own folder; viewing upgrade suggestions on another account's public deck now also works, while applying a swap remains restricted to the deck's owner (or an admin)
- **Imported decks** (via Deck Import & Analysis) were always saved to the shared root folder instead of the importing account's own folder; also fixed the saved sidecar file's format so imported decks display correctly and respect your default visibility preference
- **Synergy deck export** (Batch Build & Compare) had the same shared-root-folder and sidecar-format issue as imported decks; fixed the same way

### Removed
_No unreleased changes yet_

### Security
- **File download endpoint hardening**: the internal file-download link used by CSV/TXT export buttons validated access with a loose check on the file path that could be manipulated to read another account's deck files. It now only serves files that resolve to the current account's own deck folder or the public pre-accounts folder

