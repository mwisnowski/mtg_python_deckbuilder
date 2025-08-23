# MTG Python Deckbuilder ${VERSION}

## Highlights
- Headless support: run non-interactively or via the menu's headless submenu.
- Config precedence: CLI > env > JSON > defaults; `ideal_counts` in JSON are honored.
- Exports: CSV/TXT always; JSON run-config is exported for interactive runs. In headless, JSON export is opt-in via `HEADLESS_EXPORT_JSON`.
- Power bracket: set interactively or via `bracket_level` (env: `DECK_BRACKET_LEVEL`).
- Data freshness: auto-refreshes `cards.csv` if missing or older than 7 days and re-tags when needed using `.tagging_complete.json`.
- Docker: ships a default `config/` in the image; mount `./config` to `/app/config` to use your own.

## Docker
- Single service; persistent volumes:
  - /app/deck_files
  - /app/logs
  - /app/csv_files
  - Optional: /app/config (mount `./config` for JSON configs)

### Quick Start
```powershell
# From Docker Hub
docker run -it --rm `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  mwisnowski/mtg-python-deckbuilder:latest

# From source with Compose
docker compose build
docker compose run --rm mtg-deckbuilder

# Headless (optional)
docker compose run --rm -e DECK_MODE=headless mtg-deckbuilder
# With JSON config
docker compose run --rm -e DECK_MODE=headless -e DECK_CONFIG=/app/config/deck.json mtg-deckbuilder
```

## Changes
- Simplified headless runner and integrated a headless submenu in the main menu.
- JSON export policy: headless runs skip JSON export by default; opt in with `HEADLESS_EXPORT_JSON`.
- Correct config precedence applied consistently; tag name-to-index mapping improved for multi-step selection; `bracket_level` respected.
- Data freshness enforcement with 7-day refresh and tagging completion flag.
- Documentation and Docker usage clarified; default `config/` now included in the image.

### Tagging updates
- Explore/Map: fixed a pattern issue by treating "+1/+1 counter" as a literal; Explore adds Card Selection and may add +1/+1 Counters; Map adds Card Selection and Tokens Matter.
- Discard Matters theme and enrichments for Loot/Connive/Cycling/Blood.
- Newer mechanics support: Freerunning, Craft, Spree, Rad counters; Time Travel/Vanishing folded into Exile/Time Counters mapping; Energy enriched.
- Spawn/Scion creators now map to Aristocrats and Ramp.

## Known Issues
- First run downloads card data (takes a few minutes)
- Use `docker compose run --rm` (not `up`) for interactive sessions
- Ensure volumes are mounted to persist files outside the container

## Links
- Repo: https://github.com/mwisnowski/mtg_python_deckbuilder
- Issues: https://github.com/mwisnowski/mtg_python_deckbuilder/issues
