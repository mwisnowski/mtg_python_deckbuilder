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
- Mobile commander rows now feature larger thumbnails and a centered preview modal with expanded card art for improved readability.

## Fixed
- Documented friendly handling for missing `commander_cards.csv` data during manual QA drills to prevent white-screen failures.