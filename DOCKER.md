# Docker Guide (concise)

Run the MTG Deckbuilder in Docker with persistent volumes and optional headless mode.

## Quick start

### PowerShell (recommended)
```powershell
docker compose build
docker compose run --rm mtg-deckbuilder
```

### From Docker Hub (PowerShell)
```powershell
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
## Web UI (new)

The web UI runs the same deckbuilding logic behind a browser-based interface.

### PowerShell (recommended)
```powershell
docker compose build web
docker compose up --no-deps web
```

Then open http://localhost:8080

Volumes are the same as the CLI service, so deck exports/logs/configs persist in your working folder.

### From Docker Hub (PowerShell)
If you prefer not to build locally, pull `mwisnowski/mtg-python-deckbuilder:latest` and run uvicorn:
```powershell
docker run --rm `
    -p 8080:8080 `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mwisnowski/mtg-python-deckbuilder:latest `
    bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"
```

---
    -v "${PWD}/config:/app/config" `
    mwisnowski/mtg-python-deckbuilder:latest
```

## Volumes
- `/app/deck_files` ↔ `./deck_files`
- `/app/logs` ↔ `./logs`
- `/app/csv_files` ↔ `./csv_files`
- `/app/owned_cards` ↔ `./owned_cards` (owned cards lists: .txt/.csv)
- Optional: `/app/config` ↔ `./config` (JSON configs for headless)

## Interactive vs headless
- Interactive: attach a TTY (compose run or `docker run -it`)
- Headless auto-run:
    ```powershell
    docker compose run --rm -e DECK_MODE=headless mtg-deckbuilder
    ```
- Headless with JSON config:
    ```powershell
    docker compose run --rm `
        -e DECK_MODE=headless `
        -e DECK_CONFIG=/app/config/deck.json `
        mtg-deckbuilder
    ```

### Common env vars
- DECK_MODE=headless
- DECK_CONFIG=/app/config/deck.json
- DECK_COMMANDER, DECK_PRIMARY_CHOICE
- DECK_ADD_LANDS, DECK_FETCH_COUNT

## Manual build/run
```powershell
docker build -t mtg-deckbuilder .
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    -v "${PWD}/owned_cards:/app/owned_cards" `
    -v "${PWD}/config:/app/config" `
    mtg-deckbuilder
```

    ## Troubleshooting
    - No prompts? Use `docker compose run --rm` (not `up`) or add `-it` to `docker run`
    - Files not saving? Verify volume mounts and that folders exist
    - Headless not picking config? Ensure `./config` is mounted to `/app/config` and `DECK_CONFIG` points to a JSON file
    - Owned-cards prompt not seeing files? Ensure `./owned_cards` is mounted to `/app/owned_cards`

## Tips
- Use `docker compose run`, not `up`, for interactive mode
- Exported decks appear in `deck_files/`
- JSON run-config is exported only in interactive runs; headless skips it
