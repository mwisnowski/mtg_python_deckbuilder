# MTG Python Deckbuilder ${VERSION}

### Summary
- Enhanced deck building workflow with improved stage ordering, granular skip controls, and one-click Quick Build automation.
- Stage execution order now prioritizes creatures and spells before lands for better mana curve analysis.
- New wizard-only skip controls allow auto-advancing through specific stages (lands, creatures, spells) without approval prompts.
- Quick Build button provides one-click full automation with clean 5-phase progress indicator.

### Added
- **Quick Build**: One-click automation button in New Deck wizard with live progress tracking (5 phases: Creatures, Spells, Lands, Final Touches, Summary).
- **Skip Controls**: Granular stage-skipping toggles in New Deck wizard (21 flags: all land steps, creature stages, spell categories).
  - Individual land step controls: basics, staples, fetches, duals, triomes, kindred, misc lands.
  - Spell category controls: ramp, removal, wipes, card advantage, protection, theme fill.
  - Creature stage controls: all creatures, primary, secondary, fill.
  - Mutual exclusivity enforcement: "Skip All Lands" disables individual land toggles; "Skip to Misc Lands" skips early land steps.
- **Stage Reordering**: New default build order executes creatures → spells → lands for improved pip analysis (configurable via `WEB_STAGE_ORDER` environment variable).
- Background task execution for Quick Build with HTMX polling progress updates.
- Mobile-friendly Quick Build with touch device confirmation dialog.

### Changed
- **Default Stage Order**: Creatures and ideal spells now execute before land stages (lands can analyze actual pip requirements instead of estimates).
- Skip controls only available in New Deck wizard (disabled during build execution for consistency).
- Skip behavior auto-advances through stages without approval prompts (cards still added, just not gated).
- Post-spell land adjustment automatically skipped when any skip flag enabled.

### Fixed
- Session context properly injected into Quick Build so skip configuration works correctly.
- HTMX polling uses continuous trigger (`every 500ms`) instead of one-time (`load delay`) for reliable progress updates.
- Progress indicator stops cleanly when build completes (out-of-band swap removes poller div).
