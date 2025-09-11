# MTG Python Deckbuilder ${VERSION}

### Changed
- Web UI: Test Hand uses a default fanned layout on desktop with tightened arc and 40% overlap; outer cards sit lower for a full-arc look
- Desktop Test Hand card size set to 280×392; responsive sizes refined at common breakpoints
- Theme controls moved from the top banner to the bottom of the left sidebar; sidebar made a flex column with the theme block anchored at the bottom
- Mobile banner simplified to show only Menu, title; spacing and gaps tuned to prevent overflow and wrapping

### Fixed
- Prevented mobile banner overflow by hiding non-essential items and relocating theme controls
- Ensured desktop sizing wins over previous inline styles by using global CSS overrides; cards no longer shrink due to flexbox constraints