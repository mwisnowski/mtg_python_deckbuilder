# MTG Python Deckbuilder ${VERSION}

## Highlights
- Headless mode with a submenu in the main menu (auto-runs single config; lists multiple as "Commander - Theme1, Theme2, Theme3"; `deck.json` labeled "Default")
- Config precedence: CLI > env > JSON > defaults; honors `ideal_counts` in JSON
- Exports: CSV/TXT always; JSON run-config only for interactive runs (headless skips it)
- Smarter filenames: commander + ordered themes + date, with auto-increment when exists

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
- Added headless runner and main menu headless submenu
- JSON export is suppressed in headless; interactive runs export replayable JSON to `config/`
- `ideal_counts` supported and honored by prompts; only `fetch_count` tracked for lands
- Documentation simplified and focused; Docker guide trimmed and PowerShell examples updated

### Tagging updates
- New: Discard Matters theme – detects your discard effects and triggers; includes Madness and Blood creators; Loot/Connive/Cycling/Blood also add Discard Matters.
- New taggers:
  - Freerunning → adds Freerunning and Cost Reduction.
  - Craft → adds Transform; conditionally Artifacts Matter, Exile Matters, Graveyard Matters.
  - Spree → adds Modal and Cost Scaling.
  - Explore/Map → adds Card Selection; Explore may add +1/+1 Counters; Map adds Tokens Matter.
  - Rad counters → adds Rad Counters.
- Exile Matters expanded to cover Warp and Time Counters/Time Travel/Vanishing.
- Energy enriched to also tag Resource Engine.
- Eldrazi Spawn/Scion creators now tag Aristocrats and Ramp (replacing prior Sacrifice Fodder mapping).

## Known Issues
- First run downloads card data (takes a few minutes)
- Use `docker compose run --rm` (not `up`) for interactive sessions
- Ensure volumes are mounted to persist files outside the container

## Links
- Repo: https://github.com/mwisnowski/mtg_python_deckbuilder
- Issues: https://github.com/mwisnowski/mtg_python_deckbuilder/issues
