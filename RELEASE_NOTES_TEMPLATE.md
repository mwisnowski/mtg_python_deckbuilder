# MTG Python Deckbuilder ${VERSION}

## Summary
- Introduced the Commander Browser with HTMX-powered pagination, theme surfacing, and direct Create Deck integration.
- Shared color-identity macro and accessible theme chips power the new commander rows.
- Manual QA walkthrough (desktop + mobile) recorded on 2025‑09‑30 with edge-case checks.
- Home dashboard aligns its quick actions with feature flags, exposing Commanders, Diagnostics, Random, Logs, and Setup where enabled.

## Added
- Commander browser skeleton page at `/commanders` with catalog-backed rows and accessible theme chips.
- Documented QA checklist and results for the commander browser launch in `docs/qa/commander_browser_walkthrough.md`.
- Shared color-identity macro for reusable mana dots across commander rows and other templates.
- Home dashboard Commander/Diagnostics shortcuts gated by feature flags so all primary destinations have quick actions.
- Manual QA pass entered into project docs (2025-09-30) outlining desktop, mobile, and edge-case validations.

## Changed
- Commander list paginates in 20-item pages, with navigation controls mirrored above and below the results and automatic scroll-to-top.
- Commander hover preview shows card-only panel in browser context and removes the “+ more” overflow badge from theme chips.
- Content Security Policy upgrade directive ensures HTMX pagination requests remain HTTPS-safe behind proxies.
- Commander thumbnails adopt a fixed-width 160px frame (responsive on small screens) for consistent layout.
- Commander browser now separates name vs theme search, adds fuzzy theme suggestions, and tightens commander name matching to near-exact results.
- Commander search results stay put while filtering; typing no longer auto-scrolls the page away from the filter controls.
- Commander theme chips are larger, wrap cleanly, and display an accessible summary dialog when tapped on mobile.
- Theme dialogs now surface the full editorial description when available, improving longer summaries on small screens.
- Commander theme names unescape leading punctuation (e.g., +2/+2 Counters) so labels render without stray backslashes.
- Theme summary dialog also opens on desktop clicks, giving parity with mobile behavior.
- Mobile commander rows now feature larger thumbnails and a centered preview modal with expanded card art for improved readability.
- Preview performance CI check now waits for service health and retries catalog pagination fetches to smooth out transient 500s on cold boots.

## Fixed
- Documented friendly handling for missing `commander_cards.csv` data during manual QA drills to prevent white-screen failures.
- Headless runner commander validation now accepts fuzzy commander prefixes so automated builds using short commander names keep working.