# MTG Python Deckbuilder

## [Unreleased]
### Added
_No unreleased changes yet_

### Changed
- **Deck name no longer auto-fills on commander selection**: The deck name field in the new deck wizard stays blank when a commander is chosen. If left empty on submit, the builder defaults to the commander name as before.

### Fixed
- **Card hover preview in theme browser (#70)**: Example card thumbnails in the theme detail/browser page were showing the wrong card image (a fuzzy search for "Card") when hovered. The `<img>` elements inside `.ex-card` containers lacked `data-card-name` attributes, so the hover system fell back to the literal string "Card". Added `data-card-name`, `data-original-name`, `data-role`, and `data-tags` to example card `<img>` elements in `detail_fragment.html` to match the existing commander image pattern.
- **Enter key cancels commander search in new deck modal (#71)**: Pressing Enter while typing a commander name in the new deck wizard would submit the form before the autocomplete candidates loaded (due to the 220 ms search delay), resulting in "Commander not found". A capture-phase keydown handler now intercepts Enter on the commander field, and a direct `fetch()` call bypasses HTMX timing entirely — it fetches and auto-selects the first match immediately, then triggers the inspect/theme load. When candidates are already visible, Enter selects the highlighted one as before.
- **New Build creates a page within a page (#72)**: Clicking "New Build" from the build summary page embedded the entire build page inside the `#wizard` div instead of opening the new deck wizard. The `reset-all` endpoint was returning a `302` redirect which HTMX followed and rendered inline. "New Build" and "Start over" buttons across all wizard steps now directly open the new deck modal overlay, clearing the session server-side and presenting a fresh wizard without a full page navigation. Deck name no longer auto-fills with the commander name when a commander is selected — it remains blank and defaults to the commander name only if submitted empty.

### Removed
_No unreleased changes yet_

