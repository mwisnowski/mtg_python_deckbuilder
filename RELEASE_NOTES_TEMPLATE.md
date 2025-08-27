# MTG Python Deckbuilder ${VERSION}

## Highlights
- New Web UI: FastAPI + Jinja front-end with a staged build view and clear reasons per stage. Step 2 now includes AND/OR combine mode with tooltips and selection-order display. Footer includes Scryfall attribution per their guidelines.
- AND/OR combine mode: OR (default) recommends across any selected themes with overlap preference; AND prioritizes multi-theme intersections. In creatures, an AND pre-pass selects "all selected themes" creatures first, then fills by weighted overlap. Staged reasons show which selected themes each all-theme creature hits.
- Headless improvements: `tag_mode` (AND/OR) accepted via JSON and environment; interactive exports include `tag_mode` in the run-config.
- Owned cards workflow: Prompt after commander to "Use only owned cards?"; supports `.txt`/`.csv` lists in `owned_cards/`. Owned-only builds filter the pool; if the deck can't reach 100, it remains incomplete and notes it. When not owned-only, owned cards are marked with an `Owned` column in the final CSV.
- Exports: CSV/TXT always; JSON run-config exported for interactive runs and optionally in headless (`HEADLESS_EXPORT_JSON=1`).
- Data freshness: Auto-refreshes `cards.csv` if missing or older than 7 days and re-tags when needed using `.tagging_complete.json`.
- Web setup speed: initial tagging runs in parallel by default for the Web UI. Configure with `WEB_TAG_PARALLEL=1|0` and `WEB_TAG_WORKERS=<N>` (compose default: 4). Falls back to sequential if parallel init fails.
 - Visual summaries: Mana Curve, Color Pips and Sources charts with hover-to-highlight and copyable tooltips. Sources now include non-land producers and colorless 'C' (toggle display in UI). Basic lands reliably counted; fetch lands no longer miscounted as sources.
 - Favicon support: app branding icon served at `/favicon.ico` (ICO/PNG fallback).
 - Prefer-owned option in the Web UI Review step prioritizes owned cards while allowing unowned fallback; applied across creatures and spells with stable reordering and gentle weight boosts.
 - Owned page: export TXT/CSV, sort controls, live "N shown," color identity dots, exact color-identity combo filters (incl. 4-color), viewport-filling list, and scrollbar styling. Upload-time enrichment and de-duplication speeds up page loads.
 - Staged build visibility: optional "Show skipped stages" reveals phases that added no cards with a clear annotation.

## What’s new
- Web UI: Staged run with a new "Creatures: All-Theme" phase in AND mode; shows matched selected themes per card for explainability. Step 2 UI clarifies AND/OR with a tooltip and restyled Why panel.
- Builder: AND-mode pre-pass for creatures; spells updated to prefer multi-tag overlap in AND mode.
 - Reporting: deck summary includes per-color card lists for Pips and Sources; colorless 'C' surfaced and totals corrected.
 - UI Polish: list-mode highlight wraps only the card name. Chart tooltips include a Copy action with hover persistence.
 - Exports: CSV gains fallback oracle text for basic lands (Plains/Island/Swamp/Mountain/Forest/Wastes) when missing.
- Config: `tag_mode` added to JSON and accepted from env (`DECK_TAG_MODE`).
 - Prefer-owned bias across creatures and spells selections; Review step includes a toggle next to the owned-only control.
 - Owned page features and performance improvements via upload-time enrichment and persistence.
 - Staged build UI can surface skipped stages when enabled.

## Docker
- CLI and Web UI in the same image.
- docker-compose includes a `web` service exposing port 8080 by default.
- Persistent volumes:
  - /app/deck_files
  - /app/logs
  - /app/csv_files
  - /app/owned_cards
  - /app/config

### Web UI performance tuning
- `WEB_TAG_PARALLEL=1|0` — enable/disable parallel tagging during initial setup/tagging in the Web UI
- `WEB_TAG_WORKERS=<N>` — number of worker processes (omit to auto-pick; compose default: 4)

### Quick Start
```powershell
# CLI from Docker Hub
docker run -it --rm `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  -v "${PWD}/owned_cards:/app/owned_cards" `
  -v "${PWD}/config:/app/config" `
  mwisnowski/mtg-python-deckbuilder:latest

# Web UI from Docker Hub
docker run --rm `
  -p 8080:8080 `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  -v "${PWD}/owned_cards:/app/owned_cards" `
  -v "${PWD}/config:/app/config" `
  mwisnowski/mtg-python-deckbuilder:latest `
  bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"

# From source with Compose (CLI)
docker compose build
docker compose run --rm mtg-deckbuilder

# From source with Compose (Web)
docker compose build web
docker compose up --no-deps web
```

## Changes
- Web UI: staged view, Step 2 AND/OR radios with tips, selection order display, improved Why panel readability, and Scryfall attribution footer.
- Builder: AND-mode creatures pre-pass with matched-themes reasons; spells prefer overlap in AND mode.
- Headless: `tag_mode` supported from JSON/env and exported in interactive run-config JSON.
- Docs: README, DOCKER, and Windows Docker guide updated; PowerShell-friendly examples.
- Docker: compose `web` service added; volumes clarified.
 - Visual summaries and diagnostics: added `/healthz` endpoint with version/uptime and request-id propagation on all responses.
 - Review step consolidates owned-only and prefer-owned controls; Step 5 is status-only with an "Edit in Review" link for changes.
 - Owned lists processing moved to upload-time in Web; per-request parsing removed. Enriched store powers fast Owned page and deck-building.
 - Finished Decks page uses a dropdown theme filter with shareable state.

### Tagging updates
- Explore/Map: treat "+1/+1 counter" as a literal; Explore adds Card Selection and may add +1/+1 Counters; Map adds Card Selection and Tokens Matter.
- Discard Matters theme and enrichments for Loot/Connive/Cycling/Blood.
- Newer mechanics support: Freerunning, Craft, Spree, Rad counters; Time Travel/Vanishing folded into Exile/Time Counters; Energy enriched.
- Spawn/Scion creators now map to Aristocrats and Ramp.

## Known Issues
- First run downloads card data (takes a few minutes)
- Use `docker compose run --rm` (not `up`) for interactive CLI sessions
- Ensure volumes are mounted to persist files outside the container

## Links
- Repo: https://github.com/mwisnowski/mtg_python_deckbuilder
- Issues: https://github.com/mwisnowski/mtg_python_deckbuilder/issues
