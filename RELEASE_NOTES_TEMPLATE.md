# MTG Python Deckbuilder ${VERSION}

## Highlights
- Owned cards: prompt after commander to "Use only owned cards?"; supports `.txt`/`.csv` lists in `owned_cards/`.
- Owned-only builds filter the pool by your lists; if the deck can't reach 100, it remains incomplete and notes it.
- Recommendations: on incomplete owned-only builds, exports `deck_files/[stem]_recommendations.csv` and `.txt` with ~1.5× missing cards, and prints a short notice.
- Owned column: when not using owned-only, owned cards are marked with an `Owned` column in the final CSV.
- Headless support: run non-interactively or via the menu's headless submenu.
- Config precedence: CLI > env > JSON > defaults; `ideal_counts` in JSON are honored.
- Exports: CSV/TXT always; JSON run-config is exported for interactive runs. In headless, JSON export is opt-in via `HEADLESS_EXPORT_JSON`.
- Power bracket: set interactively or via `bracket_level` (env: `DECK_BRACKET_LEVEL`).
- Data freshness: auto-refreshes `cards.csv` if missing or older than 7 days and re-tags when needed using `.tagging_complete.json`.
- Docker: mount `./owned_cards` to `/app/owned_cards` to enable owned-cards features; `./config` to `/app/config` for JSON configs.

## Docker
- Single service; persistent volumes:
  - /app/deck_files
  - /app/logs
  - /app/csv_files
  - /app/owned_cards
  - /app/config (mount `./config` for JSON configs)

### Quick Start
```powershell
# From Docker Hub
docker run -it --rm `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  -v "${PWD}/owned_cards:/app/owned_cards" `
  -v "${PWD}/config:/app/config" `
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
- Added owned-cards workflow, CSV Owned column, and recommendations export when owned-only builds are incomplete.
- Docker assets updated to include `/app/owned_cards` volume and mount examples.
- Windows release workflow now attaches a PyInstaller-built EXE to GitHub Releases.

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
