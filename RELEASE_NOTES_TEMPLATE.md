# MTG Python Deckbuilder ${VERSION}

## Highlights
- Mobile UI polish: collapsible left sidebar with persisted state, sticky controls that respect the header, and banner subtitle that stays inline when the menu is collapsed.
- Multi-Copy is now opt-in from the New Deck modal, and suggestions are filtered to match selected themes (e.g., Rabbit Kindred → Hare Apparent).
- New Deck modal improvements: integrated commander preview, theme selection, and optional Multi-Copy in one flow.

## What’s new
- Mobile & layout
  - Sidebar toggle button (persisted in localStorage), smooth hide/show.
  - Sticky build controls offset via CSS variables to avoid overlap in emulators and mobile.
  - Banner subtitle stays within the header and remains inline with the title when the sidebar is collapsed.
- Multi-Copy
  - Moved to Commander selection now instead of happening during building.
  - Opt-in checkbox in the New Deck modal; disabled by default.
  - Suggestions only appear when at least one theme is selected and are limited to archetypes whose matched tags intersect the themes.
  - Multi-Copy runs first when selected, with an applied marker to avoid redundant rebuilds.
- New Deck & Setup
  - Setup/Refresh prompt modal if the environment is missing or stale, with a clear path to run/refresh setup before building.
  - Centralized staged context creation and error/render helpers for a more robust Step 5 flow.

## Notes
- Multi-Copy selection is part of the interactive New Deck modal (not a JSON field); it remains off unless explicitly enabled.
- Setup helpers: `is_setup_ready()` and `is_setup_stale()` inform the modal prompt and can be tuned with `WEB_AUTO_SETUP` and `WEB_AUTO_REFRESH_DAYS`.
- Headless parity: `tag_mode` (AND/OR) remains supported in JSON/env and exported in interactive run-config JSON.

## Fixes
- Continue responsiveness and click reliability on mobile/emulators; sticky overlap eliminated.
- Multi-Copy application preserved across New Deck submit; duplicate re-application avoided with an applied marker.
- Banner subtitle alignment fixed in collapsed-menu mode (no overhang, no line-wrap into a new row).
- Docker: normalized line endings for entrypoint to avoid Windows checkout issues.