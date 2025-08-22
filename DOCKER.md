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
    mwisnowski/mtg-python-deckbuilder:latest
```

## Volumes
- `/app/deck_files` ↔ `./deck_files`
- `/app/logs` ↔ `./logs`
- `/app/csv_files` ↔ `./csv_files`
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
    mtg-deckbuilder
```

    ## Troubleshooting
    - No prompts? Use `docker compose run --rm` (not `up`) or add `-it` to `docker run`
    - Files not saving? Verify volume mounts and that folders exist
    - Headless not picking config? Ensure `./config` is mounted to `/app/config` and `DECK_CONFIG` points to a JSON file

## Tips
- Use `docker compose run`, not `up`, for interactive mode
- Exported decks appear in `deck_files/`
- JSON run-config is exported only in interactive runs; headless skips it
