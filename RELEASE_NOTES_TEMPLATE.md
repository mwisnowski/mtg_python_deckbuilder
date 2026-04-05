# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Card Kingdom prices**: All price displays now show both TCGPlayer (TCG) and Card Kingdom (CK) prices side by side
  - Card tile overlays and inline pricing in deck summary, build wizard, and Pickups page
  - Card hover panel
  - Upgrade Suggestions table
  - Alternatives and budget review panels
  - Card browser grid tiles
  - Theme detail example cards and commanders
  - Similar cards panel on card detail pages
  - Price stat block on individual card detail pages (fetched live via API)
- **Price source legend**: "TCG = TCGPlayer · CK = Card Kingdom" label added to the deck summary and Pickups pages for clarity
- **Shopping cart export**: One-click deck purchasing via TCGPlayer and Card Kingdom
  - **Upgrade Suggestions page**: Per-card checkboxes with select-all toggle; "Open in TCGPlayer" and "Open in Card Kingdom" buttons copy the selected card list to the clipboard and open the vendor's mass-entry page in a new tab
  - **Finished deck view**: "Buy This Deck" toolbar with the same TCGPlayer and Card Kingdom buttons for the full deck list
  - Clipboard copy shows a confirmation toast; falls back to a copyable text area if clipboard API is unavailable

### Changed
- **"Upgrade Suggestions" rename**: The Pickups page and its button in the deck view are now labelled "Upgrade Suggestions" for clarity

### Fixed
- **Commander hover panel triggered by entire sidebar**: Hovering any element inside the left-hand card preview column (buttons, text, etc.) incorrectly triggered the commander card hover panel; panel now only activates when hovering the commander image or its direct container
- **Commander hover panel missing prices**: Price information was not shown in the commander card hover panel on the finished deck and run-result views; a price overlay is now attached to the commander image so TCG and CK prices load into the hover panel

